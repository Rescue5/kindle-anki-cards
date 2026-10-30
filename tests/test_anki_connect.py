from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from kindle_vocab_app import anki_connect, anki_export, vocab_cache
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.tauri_bridge import dispatch
from tests.test_anki_export import _lexeme


class FakeAnki:
    """Records AnkiConnect calls and answers like the add-on."""

    def __init__(self, *, fail_import: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail_import = fail_import
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.calls.append(request)
                if request["action"] == "version":
                    body = {"result": 6, "error": None}
                elif request["action"] == "importPackage":
                    exists = Path(request["params"]["path"]).is_file()
                    body = {"result": None, "error": "import failed"} if fake.fail_import or not exists else {"result": True, "error": None}
                else:
                    body = {"result": None, "error": "unsupported action"}
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class AnkiConnectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.anki = FakeAnki()
        self.addCleanup(self.anki.close)
        url_patch = patch.object(anki_connect, "ANKI_CONNECT_URL", self.anki.url)
        url_patch.start()
        self.addCleanup(url_patch.stop)

    def _workspace(self, temporary: str) -> Path:
        workspace = Path(temporary)
        catalog = vocab_cache.empty_catalog()
        catalog["lexemes"] = [_lexeme("glimpse"), _lexeme("dread")]
        repository_for(workspace).save_catalog(catalog)
        return workspace

    def test_status_reports_connected_and_missing_anki(self) -> None:
        self.assertEqual(anki_connect.status()["state"], "connected")
        self.assertEqual(anki_connect.status(url="http://127.0.0.1:9")["state"], "disconnected")

    def test_push_imports_the_deck_and_marks_words(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self._workspace(temporary)
            result = dispatch("push_anki", {}, workspace)
            self.assertEqual(result["exported"], 2)
            self.assertTrue(result["pushed"])
            imports = [call for call in self.anki.calls if call["action"] == "importPackage"]
            self.assertEqual(len(imports), 1)
            self.assertTrue(imports[0]["params"]["path"].endswith(".apkg"))
            states = {item["destinations"]["anki"]["state"] for item in repository_for(workspace).load_catalog()["lexemes"]}
            self.assertEqual(states, {"exported"})

    def test_failed_import_keeps_words_pending(self) -> None:
        self.anki.fail_import = True
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self._workspace(temporary)
            with self.assertRaisesRegex(ValueError, "Колода сохранена в файл"):
                dispatch("push_anki", {}, workspace)
            states = {item["destinations"]["anki"]["state"] for item in repository_for(workspace).load_catalog()["lexemes"]}
            self.assertEqual(states, {"not_exported"})

    def test_translation_after_export_queues_the_card_again(self) -> None:
        exported = {**_lexeme("glimpse"), "destinations": {"anki": {"state": "exported", "last_exported_at": "2026-10-01T00:00:00+00:00"}}}
        self.assertFalse(anki_export.needs_anki_update(exported))
        older = {**exported, "enrichment": {"status": "ready", "updated_at": "2026-09-01T00:00:00+00:00"}}
        self.assertFalse(anki_export.needs_anki_update(older))
        newer = {**exported, "enrichment": {"status": "ready", "updated_at": "2026-10-02T00:00:00+00:00"}}
        self.assertTrue(anki_export.needs_anki_update(newer))


if __name__ == "__main__":
    unittest.main()
