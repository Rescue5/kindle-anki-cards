from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import httpx
import pytest
from openai import OpenAI

from kindle_vocab_app.export_cards import _workspace_export_lock
from kindle_vocab_app.llm import LLMError
from kindle_vocab_app.llm.openai_compatible import OpenAICompatibleClient
from kindle_vocab_app.tauri_bridge import dispatch
from kindle_vocab_app.workspace_lock import enrichment_run_lock


def test_enrichment_lock_excludes_second_process_and_recovers_after_exit(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    script = """
import sys
from pathlib import Path
from kindle_vocab_app.workspace_lock import enrichment_run_lock

workspace, ready = map(Path, sys.argv[1:])
with enrichment_run_lock(workspace):
    ready.touch()
    sys.stdin.read()
"""
    with subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), str(ready)],
        stdin=subprocess.PIPE,
    ) as child:
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.025)
            assert ready.exists() and child.poll() is None, "Child did not acquire the enrichment lock"
            with pytest.raises(RuntimeError, match="Перевод уже выполняется в этой библиотеке"):
                dispatch("enrich_lexemes", {}, tmp_path)
            with enrichment_run_lock(tmp_path / "other-profile"), _workspace_export_lock(tmp_path):
                assert (tmp_path / ".app-data" / "export.lock").exists()
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
    with enrichment_run_lock(tmp_path):
        assert (tmp_path / ".app-data" / "enrichment.lock").exists()


@contextmanager
def _client_for(handler: Callable[[httpx.Request], httpx.Response]) -> Iterator[OpenAICompatibleClient]:
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        with patch("openai.OpenAI", side_effect=lambda **options: OpenAI(http_client=transport, **options)):
            client = OpenAICompatibleClient(
                base_url="https://sdk-test.invalid/v1", api_key="unit-test", model="test", max_retries=0,
            )
        yield client


def test_concurrent_rejections_of_same_format_do_not_skip_next_format() -> None:
    schema_requests = Barrier(2)

    def reply(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        mode = body.get("response_format", {}).get("type")
        if mode == "json_schema":
            schema_requests.wait(timeout=5)
            return httpx.Response(400, json={"error": {"message": "unsupported response_format"}})
        assert mode == "json_object"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"items": []}'}}]})

    with _client_for(reply) as client, ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(client.complete_json, "system", "user", {}) for _ in range(2)]
        assert [call.result(timeout=10) for call in calls] == [{"items": []}, {"items": []}]
        assert client.complete_json("system", "user", {}) == {"items": []}


@pytest.mark.parametrize(
    ("status", "fatal", "transient"),
    [(408, False, True), (409, False, True), (500, False, True), (503, False, True),
     (429, True, False), (401, True, False), (422, False, False)],
)
def test_http_error_classification(status: int, fatal: bool, transient: bool) -> None:
    def reply(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "Test error"}})

    with _client_for(reply) as client, pytest.raises(LLMError) as failure:
        client.complete_json("system", "user", {})
    assert (failure.value.fatal, failure.value.transient) == (fatal, transient)
