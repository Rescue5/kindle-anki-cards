"""Minimal client for the AnkiConnect add-on (https://ankiweb.net/shared/info/2055492159).

Decks are delivered through ``importPackage`` with the same ``.apkg`` the file
export produces, so a note keeps one GUID whichever way it reached Anki and
re-sending updates notes instead of duplicating them.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
API_VERSION = 6
ADDON_CODE = "2055492159"


class AnkiConnectError(RuntimeError):
    pass


def invoke(action: str, *, url: str | None = None, timeout: float = 5.0, **params: Any) -> Any:
    body = json.dumps({"action": action, "version": API_VERSION, "params": params}).encode("utf-8")
    request = urllib.request.Request(url or ANKI_CONNECT_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise AnkiConnectError("Anki не отвечает. Откройте Anki с дополнением AnkiConnect") from exc
    except json.JSONDecodeError as exc:
        raise AnkiConnectError("AnkiConnect вернул непонятный ответ") from exc
    if not isinstance(payload, dict) or set(payload) != {"result", "error"}:
        raise AnkiConnectError("По адресу AnkiConnect отвечает что-то другое")
    if payload["error"]:
        raise AnkiConnectError(f"Anki: {payload['error']}")
    return payload["result"]


def status(*, url: str | None = None) -> dict[str, Any]:
    """Cheap presence check used by connector probing; never raises."""
    try:
        version = invoke("version", url=url, timeout=1.5)
    except AnkiConnectError:
        return {"state": "disconnected", "label": "Anki"}
    return {"state": "connected", "label": "Anki", "version": version}


def import_package(path: Path, *, url: str | None = None) -> None:
    # Large decks take a while to import; Anki answers only when done.
    result = invoke("importPackage", url=url, timeout=300.0, path=str(path.resolve()))
    if result is False:
        raise AnkiConnectError("Anki не смог импортировать колоду")
    logger.info("Imported Anki package through AnkiConnect path=%s", path)
