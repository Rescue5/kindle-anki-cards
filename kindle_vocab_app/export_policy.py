"""Which words may leave the library: one rule for the short list, the export and every writer.

A word is exportable when it has been processed and the reader wants it: either the reader answered
«учить», or there is no answer and the ranking puts it on the «Стоит учить» shelf. «Знаю»,
«не учить» and «не слово» never export, and neither does a word that is not processed yet.
A «знаю» that lapsed because the word was looked up again goes back to the model (the ranking says so
by moving it off the `known` shelf), so it is judged by its shelf again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROCESSED_STATES = ("ready", "rejected")


def is_exportable(entry: Mapping[str, Any]) -> bool:
    """True for a decorated library entry (`ranking`, `decision` and `processing` present)."""
    if str((entry.get("processing") or {}).get("state") or "") not in PROCESSED_STATES:
        return False
    ranking = entry.get("ranking")
    if not ranking:
        return False
    decision = (entry.get("decision") or {}).get("value")
    shelf = ranking.get("shelf")
    if decision == "learn":
        return True
    if decision in ("skip", "junk"):
        return False
    if decision == "known" and shelf == "known":
        return False
    return shelf == "worth"
