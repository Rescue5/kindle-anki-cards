"""Offline English -> Russian meanings from the bundled Wiktionary dictionary.

The dictionary is a small read-only SQLite file built by
``packaging/build_dictionary.py`` from the Russian Wiktionary (CC BY-SA 4.0).
Every lexeme gets dictionary meanings without a network connection or an API
key; a context-specific translation from the optional LLM enrichment, when
present, takes priority over it everywhere it is shown.

Meanings are looked up when the library is read, not stored in analyses, so
words processed before the dictionary existed get them without reprocessing.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DICTIONARY_PATH = Path(__file__).resolve().parent / "data" / "en_ru_wiktionary.sqlite"
SOURCE = "wiktionary"
# Cards stay readable: the most common senses come first in Wiktionary.
MAX_SENSES = 3

# WordNet codes from the optimizer -> codes in the dictionary ("s" is a satellite adjective).
_POS = {"n": "n", "v": "v", "a": "a", "s": "a", "r": "r"}


@lru_cache(maxsize=1)
def _connection(path: Path = DICTIONARY_PATH) -> sqlite3.Connection | None:
    if not path.is_file():
        logger.warning("Offline dictionary is missing path=%s", path)
        return None
    return sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True, check_same_thread=False)


def lookup(word: str, pos: str = "") -> dict[str, str] | None:
    """Return ``{"meaning_ru", "pos", "source"}`` for a lemma, preferring the given part of speech."""
    key = " ".join(str(word or "").split()).lower()
    connection = _connection()
    if not key or connection is None:
        return None
    rows = connection.execute("SELECT pos, meanings FROM entries WHERE word = ?", (key,)).fetchall()
    if not rows:
        return None
    wanted = _POS.get(pos, "")
    chosen = next((row for row in rows if row[0] == wanted), None) or next((row for row in rows if row[0] == "p"), None) or rows[0]
    senses = [line for line in str(chosen[1]).splitlines() if line][:MAX_SENSES]
    return {"meaning_ru": "; ".join(senses), "pos": str(chosen[0]), "source": SOURCE}


def lookup_lexeme(lexeme: Mapping[str, Any]) -> dict[str, str] | None:
    """Dictionary meanings for a library lexeme or review card, trying its lemma before its surface forms."""
    analysis = (lexeme.get("processing") or {}).get("analysis") or lexeme.get("analysis") or {}
    pos = str(analysis.get("pos") or "")
    for candidate in _candidates(analysis.get("base_form"), lexeme.get("lemma"), lexeme.get("display_form")):
        found = lookup(candidate, pos)
        if found:
            return found
    return None


def _candidates(*values: Any) -> Iterable[str]:
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            yield text


def attach(lexemes: Iterable[dict[str, Any]]) -> None:
    """Add a ``dictionary`` field to each lexeme or review card in place (``None`` when not found)."""
    for lexeme in lexemes:
        lexeme["dictionary"] = lookup_lexeme(lexeme)
