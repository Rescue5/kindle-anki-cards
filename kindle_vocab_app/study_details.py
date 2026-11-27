"""Study-card details shared by HTML and plain-text export writers."""

from collections.abc import Mapping
from typing import Any

from kindle_vocab_app import card_fields


def resolve(
    lexeme: Mapping[str, Any], edit: Mapping[str, Any] | None,
) -> tuple[card_fields.ResolvedCard, Mapping[str, Any]]:
    stored = lexeme.get("enrichment") or {}
    enrichment = card_fields.enrichment_for_card(lexeme, edit) if stored.get("prompt_version") == 2 else stored
    return card_fields.resolve(lexeme, edit), enrichment


def contextual_meaning(enrichment: Mapping[str, Any], card: card_fields.ResolvedCard) -> str:
    if enrichment.get("context_quality") != "good" or not _matched_excerpt(enrichment, card):
        return ""
    return _text(enrichment.get("context_meaning_ru"))


def example(enrichment: Mapping[str, Any]) -> str:
    source = _text(enrichment.get("example_en"))
    if not source:
        return ""
    translation = _text(enrichment.get("example_ru"))
    return f"{source} — {translation}" if translation else source


def sense_lines(enrichment: Mapping[str, Any], card: card_fields.ResolvedCard) -> list[str]:
    senses = enrichment.get("senses")
    if not isinstance(senses, list):
        return []
    primary_meanings = {card.meaning_ru.casefold(), contextual_meaning(enrichment, card).casefold()}
    main_example = example(enrichment).casefold()
    details: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for sense in senses:
        if not isinstance(sense, Mapping) or not (meaning := _text(sense.get("meaning_ru"))):
            continue
        sentence = example(sense)
        if meaning.casefold() in primary_meanings and (not sentence or sentence.casefold() == main_example):
            continue
        key = (
            meaning.casefold(),
            _text(sense.get("example_en")).casefold(),
            _text(sense.get("example_ru")).casefold(),
        )
        if key not in seen:
            seen.add(key)
            details.append(
                f"Пример по значению: {meaning} — {sentence}" if sentence else f"Дополнительное значение: {meaning}"
            )
    return details


def book_meaning_line(enrichment: Mapping[str, Any], card: card_fields.ResolvedCard) -> str:
    if meaning := contextual_meaning(enrichment, card):
        label = "Значение во фрагменте" if enrichment.get("context_truncated") else "Значение в цитате"
        return f"{label}: {meaning}"
    return ""


def quote_translation(enrichment: Mapping[str, Any], card: card_fields.ResolvedCard) -> str:
    return _text(enrichment.get("context_ru")) if _matched_excerpt(enrichment, card) else ""


def _matched_excerpt(enrichment: Mapping[str, Any], card: card_fields.ResolvedCard) -> bool:
    context = str(card.occurrence.get("context") or "")
    excerpt = context[:card_fields.MAX_ENRICHMENT_CONTEXT_CHARS]
    if not excerpt or enrichment.get("context_truncated") is not (len(excerpt) < len(context)):
        return False
    return (
        enrichment.get("selected_context_sha256") == card_fields.context_fingerprint(context)
        and enrichment.get("context_source_sha256") == card_fields.context_fingerprint(excerpt)
    )


def answer_details(enrichment: Mapping[str, Any], card: card_fields.ResolvedCard) -> list[str]:
    """Flat lines for text destinations, following the card's actual book quote."""
    if enrichment.get("prompt_version") != 2:
        return []
    details = []
    if meaning_line := book_meaning_line(enrichment, card):
        details.append(meaning_line)
    if translation := quote_translation(enrichment, card):
        label = "Перевод фрагмента" if enrichment.get("context_truncated") else "Перевод цитаты"
        details.append(f"{label}: {translation}")
    if generated := example(enrichment):
        details.append(f"Учебный пример: {generated}")
    details.extend(sense_lines(enrichment, card))
    return details


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""
