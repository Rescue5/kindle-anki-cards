"""What one word's card says, resolved once for the library payload and for every export writer.

Translation: the reader's own edit beats a ready LLM translation, which beats the bundled offline
dictionary. Example sentence: the occurrence the reader picked, else the longest real context.
The payload (`card` in `contracts.CardFields`) and the files and pushes written by `export_cards`
read the same result, so the card the reader saw is the card that is exported.

Pure functions over a library entry, the reader's edit row and the dictionary meaning the caller
attached to the entry (`offline_dictionary.attach`); no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kindle_vocab_app.contracts import MEANING_MAX_LENGTH


@dataclass(frozen=True)
class ResolvedCard:
    meaning_ru: str  # "" when meaning_source is "none"
    meaning_source: str  # edited | llm | dictionary | none
    occurrence: Mapping[str, Any]  # the example: an occurrence of the word, {} when there is none
    example_occurrence_id: str  # id of `occurrence`; "" when there is none or it is a kept copy
    edited: bool  # the reader changed the meaning or picked the example

    def payload(self) -> dict[str, Any]:
        """The `card` part of a library entry."""
        return {
            "meaning_ru": self.meaning_ru,
            "meaning_source": self.meaning_source,
            "example_occurrence_id": self.example_occurrence_id,
            "edited": self.edited,
        }


def longest_occurrence(occurrences: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    """The occurrence with the longest real context; ties go to the latest lookup."""
    return max(
        occurrences,
        key=lambda item: (
            bool(item.get("context")),
            len(str(item.get("context") or "")),
            str(item.get("looked_up_at") or ""),
        ),
        default={},
    )


def resolve(lexeme: Mapping[str, Any], edit: Mapping[str, Any] | None = None) -> ResolvedCard:
    """Resolve the card of a library entry.

    `edit` is the reader's row from `card_edits` (`meaning_ru`, `example_occurrence_id`,
    `example_context`, `example_form`), or None. The dictionary meaning is `lexeme["dictionary"]`,
    attached once per response by the caller; an entry without it has no dictionary meaning.
    """
    occurrences = list(lexeme.get("occurrences") or [])
    edit = edit or {}

    meaning, source = _meaning(lexeme, edit)

    chosen_id = str(edit.get("example_occurrence_id") or "")
    occurrence: Mapping[str, Any] = {}
    if chosen_id:
        occurrence = next((item for item in occurrences if str(item.get("id") or "") == chosen_id), {})
        if not occurrence and edit.get("example_context"):
            # The picked sentence is gone from the library (a re-sync replaced it): keep what the
            # reader picked, on the book of the best remaining occurrence.
            base = longest_occurrence(occurrences)
            occurrence = {
                **base,
                "id": "",
                "context": str(edit.get("example_context") or ""),
                "word": str(edit.get("example_form") or base.get("word") or ""),
            }
    if not occurrence:
        occurrence = longest_occurrence(occurrences)

    return ResolvedCard(
        meaning_ru=meaning,
        meaning_source=source,
        occurrence=occurrence,
        example_occurrence_id=str(occurrence.get("id") or ""),
        edited=bool(edit.get("meaning_ru")) or bool(chosen_id),
    )


def _meaning(lexeme: Mapping[str, Any], edit: Mapping[str, Any]) -> tuple[str, str]:
    edited = _clean(edit.get("meaning_ru"))
    if edited:
        return edited, "edited"
    enrichment = lexeme.get("enrichment") or {}
    if enrichment.get("status", "ready") == "ready":
        generated = _clean(enrichment.get("meaning_ru"))
        if generated:
            return generated, "llm"
    offline = _clean((lexeme.get("dictionary") or {}).get("meaning_ru"))
    if offline:
        return _fit(offline), "dictionary"
    return "", "none"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _fit(meaning: str) -> str:
    """A dictionary meaning is senses joined by "; ": drop whole trailing senses until it fits the card limit."""
    if len(meaning) <= MEANING_MAX_LENGTH:
        return meaning
    kept = meaning[: MEANING_MAX_LENGTH + 1].rpartition("; ")[0]
    return kept or meaning[: MEANING_MAX_LENGTH - 1].rstrip() + "…"
