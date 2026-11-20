"""Synthetic libraries for the short-list tests: invented words, books and sentences only.

`NOW` is the day of the latest lookup. A word looked up N days before it, in the book the reader
is reading (any book with a lookup in the last 14 days), lands on the «Стоит учить» shelf up to
about three weeks back; a word with a «possibly_glued_words» warning is «Спорное».
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kindle_vocab_app import vocab_cache
from kindle_vocab_app.library_repository import repository_for

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
KINDLE_BOOK = ("book-lighthouse", "The Lighthouse Keeper", "A. Writer")
KOREADER_BOOK = ("koreader:book-river", "Down the River", "B. Author")


def lid(lemma: str) -> str:
    return vocab_cache.lexeme_id("en", lemma)


def word(
    lemma: str,
    *,
    days: Sequence[float] = (0,),
    zipf: float = 3.6,
    warnings: Sequence[str] = (),
    state: str = "ready",
    book: tuple[str, str, str] = KINDLE_BOOK,
    freshness: str = "new",
) -> dict[str, Any]:
    """A library word looked up `days` days before NOW; `state` pending means not processed yet."""
    occurrences = [
        {
            "id": f"{lemma}-o{index}",
            "source": "kindle",
            "word": lemma,
            "context": f"The {lemma} showed up again" + " at dusk" * index + ".",
            "book_key": book[0],
            "book_title": book[1],
            "authors": book[2],
            "looked_up_at": (NOW - timedelta(days=offset)).isoformat(),
        }
        for index, offset in enumerate(days)
    ]
    analysis = (
        {
            "base_form": lemma,
            "pos": "n",
            "accepted": state == "ready",
            "importance_score": 5,
            "lemma_zipf": zipf,
            "form_zipf": zipf,
            "wordnet_synset_count": 3,
            "wordnet_pos_count": 1,
            "warnings": list(warnings),
            "translation_status": "offline_only",
        }
        if state in ("ready", "rejected")
        else None
    )
    first = occurrences[0]["looked_up_at"]
    return {
        "id": lid(lemma),
        "lemma": lemma,
        "display_form": lemma,
        "language": "en",
        "forms": [lemma],
        "occurrences": occurrences,
        "freshness": freshness,
        "processing": {"state": state, "analysis": analysis, "updated_at": first, "error": ""},
        "sources": {"kindle": True, "legacy": False},
        "destinations": {
            "obsidian": {"state": "missing", "reason": "", "last_synced_at": ""},
            "anki": {"state": "not_exported", "last_exported_at": ""},
            "quizlet": {"state": "not_exported", "last_exported_at": ""},
        },
        "first_seen_at": first,
        "last_seen_at": first,
        "last_kindle_sync_id": "sync",
    }


def build_library(workspace: Path, words: Sequence[dict[str, Any]]) -> Any:
    """Save the words into the workspace's SQLite library and return its repository."""
    catalog = vocab_cache.empty_catalog()
    catalog["lexemes"] = list(words)
    repository = repository_for(workspace)
    repository.save_catalog(catalog)
    return repository


def worth_words(count: int, *, prefix: str = "lumen") -> list[dict[str, Any]]:
    """`count` words on the «Стоит учить» shelf, the first looked up most recently."""
    return [word(f"{prefix}{letters(index)}", days=(index * 0.5,)) for index in range(count)]


def letters(number: int) -> str:
    """0 -> a, 1 -> b, ... 26 -> ba: words made of letters only, so they pass as English."""
    digits = ""
    while True:
        digits = chr(ord("a") + number % 26) + digits
        number //= 26
        if not number:
            return digits
