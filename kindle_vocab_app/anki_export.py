"""Anki deck export (.apkg) with a dedicated, stable note type.

Each lexeme becomes one note whose GUID derives from the lexeme id, so
re-importing an updated deck refreshes existing notes instead of duplicating
them. Fields that cannot be derived honestly stay empty; the card templates
hide empty sections.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

# Fixed ids keep the note type and deck stable across exports and versions.
MODEL_ID = 1_739_210_481
DECK_ID = 1_739_210_517
MODEL_NAME = "Kindle Cards · Word in context"
DEFAULT_DECK_NAME = "Kindle Cards"
MIN_SCORE = 3

FIELDS = [
    "Word",
    "Lemma",
    "PartOfSpeech",
    "Context",
    "Meaning",
    "Definition",
    "DefinitionSource",
    "ContextTranslation",
    "Example",
    "ExampleTranslation",
    "Book",
    "Author",
    "Usefulness",
    "LexemeId",
]

_POS_LABELS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}

FRONT = """<div class="kc-card">
  <div class="kc-word">{{Word}}</div>
  {{#Context}}<blockquote class="kc-context">{{Context}}</blockquote>{{/Context}}
</div>"""

BACK = """<div class="kc-card">
  <div class="kc-word">{{Word}}</div>
  {{#Context}}<blockquote class="kc-context">{{Context}}</blockquote>{{/Context}}
  <hr id="answer">
  <div class="kc-lemma">{{Lemma}}{{#PartOfSpeech}} <span class="kc-pos">{{PartOfSpeech}}</span>{{/PartOfSpeech}}</div>
  {{#Meaning}}<div class="kc-meaning">{{Meaning}}</div>{{/Meaning}}
  {{#Definition}}<div class="kc-definition">{{Definition}}{{#DefinitionSource}} <span class="kc-source">{{DefinitionSource}}</span>{{/DefinitionSource}}</div>{{/Definition}}
  {{#ContextTranslation}}<div class="kc-translation">{{ContextTranslation}}</div>{{/ContextTranslation}}
  {{#Example}}<div class="kc-example">{{Example}}{{#ExampleTranslation}}<div class="kc-example-ru">{{ExampleTranslation}}</div>{{/ExampleTranslation}}</div>{{/Example}}
  {{#Book}}<div class="kc-book">{{Book}}{{#Author}} · {{Author}}{{/Author}}</div>{{/Book}}
</div>"""

CSS = """.card {
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 19px;
  line-height: 1.5;
  color: #1f2a26;
  background: #faf8f3;
  text-align: left;
}
.kc-card { max-width: 640px; margin: 0 auto; padding: 8px 4px; }
.kc-word { font-size: 30px; font-weight: 600; letter-spacing: 0.01em; }
.kc-context {
  margin: 14px 0 0; padding: 10px 14px;
  border-left: 3px solid #2f5d50; background: rgba(47, 93, 80, 0.07);
  border-radius: 0 8px 8px 0; font-style: italic;
}
.kc-context .kc-hl { font-style: normal; font-weight: 700; color: #2f5d50; }
#answer { border: 0; border-top: 1px solid rgba(31, 42, 38, 0.15); margin: 18px 0 14px; }
.kc-lemma { font-size: 20px; font-weight: 600; }
.kc-pos { font-size: 14px; font-weight: 400; color: #6b766f; font-style: italic; }
.kc-meaning { margin-top: 8px; font-size: 22px; color: #1f4a3f; }
.kc-definition, .kc-translation, .kc-example { margin-top: 10px; font-size: 16px; color: #3d4844; }
.kc-source { font-size: 12px; color: #8a938d; }
.kc-example-ru { color: #6b766f; }
.kc-book { margin-top: 16px; font-size: 13px; color: #8a938d; font-family: -apple-system, "Segoe UI", sans-serif; }
.nightMode.card, .night_mode .card { color: #e6e2d8; background: #1d2321; }
.nightMode .kc-context, .night_mode .kc-context { background: rgba(140, 190, 170, 0.08); border-left-color: #7fb3a2; }
.nightMode .kc-context .kc-hl, .night_mode .kc-context .kc-hl { color: #9fd0bf; }
.nightMode .kc-meaning, .night_mode .kc-meaning { color: #a9d8c7; }
.nightMode .kc-definition, .nightMode .kc-translation, .nightMode .kc-example,
.night_mode .kc-definition, .night_mode .kc-translation, .night_mode .kc-example { color: #c4c0b6; }
"""


@dataclass(frozen=True)
class ApkgResult:
    path: Path
    exported_ids: list[str]
    skipped: int


def is_exportable(lexeme: dict[str, Any]) -> bool:
    """Same eligibility as the Obsidian destination: processed, accepted, useful."""
    processing = lexeme.get("processing") or {}
    analysis = processing.get("analysis") or {}
    score = analysis.get("importance_score")
    return (
        processing.get("state") == "ready"
        and analysis.get("accepted") is not False
        and isinstance(score, (int, float))
        and MIN_SCORE <= score <= 10
    )


def needs_anki_update(lexeme: dict[str, Any]) -> bool:
    """Never exported, or translated after the last export (the card gained fields)."""
    anki = (lexeme.get("destinations") or {}).get("anki") or {}
    if anki.get("state") != "exported":
        return True
    enrichment = lexeme.get("enrichment") or {}
    return enrichment.get("status") == "ready" and str(enrichment.get("updated_at") or "") > str(anki.get("last_exported_at") or "")


def build_note_fields(
    lexeme: dict[str, Any],
    *,
    definition_lookup: Any = None,
) -> dict[str, str]:
    """Return escaped HTML field values for one lexeme."""
    analysis = (lexeme.get("processing") or {}).get("analysis") or {}
    enrichment = lexeme.get("enrichment") or {}
    occurrence = primary_occurrence(lexeme)
    word = str(occurrence.get("word") or lexeme.get("display_form") or lexeme.get("lemma") or "")
    lemma = str(analysis.get("base_form") or lexeme.get("lemma") or word)
    pos = _POS_LABELS.get(str(analysis.get("pos") or ""), "")
    context = str(occurrence.get("context") or "")

    definition = _clean(enrichment.get("definition_en"))
    definition_source = ""
    if not definition and definition_lookup is not None:
        definition = _clean(definition_lookup(lemma, str(analysis.get("pos") or ""), context))
        definition_source = "WordNet" if definition else ""

    score = analysis.get("importance_score")
    return {
        "Word": _escape(word),
        "Lemma": _escape(lemma),
        "PartOfSpeech": _escape(pos),
        "Context": highlight(context, [word, *lexeme.get("forms", []), lemma]),
        "Meaning": _escape(_clean(enrichment.get("meaning_ru"))),
        "Definition": _escape(definition),
        "DefinitionSource": definition_source,
        "ContextTranslation": _escape(_clean(enrichment.get("context_ru"))),
        "Example": _escape(_clean(enrichment.get("example_en"))),
        "ExampleTranslation": _escape(_clean(enrichment.get("example_ru"))),
        "Book": _escape(str(occurrence.get("book_title") or "")),
        "Author": _escape(str(occurrence.get("authors") or "")),
        "Usefulness": str(int(score)) if isinstance(score, (int, float)) else "",
        "LexemeId": _escape(str(lexeme.get("id") or "")),
    }


def note_tags(lexeme: dict[str, Any]) -> list[str]:
    analysis = (lexeme.get("processing") or {}).get("analysis") or {}
    occurrence = primary_occurrence(lexeme)
    tags = ["kindle"]
    book = _tag(str(occurrence.get("book_title") or ""))
    if book:
        tags.append(f"book::{book}")
    pos = _POS_LABELS.get(str(analysis.get("pos") or ""))
    if pos:
        tags.append(pos)
    score = analysis.get("importance_score")
    if isinstance(score, (int, float)):
        tags.append(f"usefulness::{int(score)}")
    return tags


def write_apkg(
    lexemes: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    deck_name: str = DEFAULT_DECK_NAME,
    definition_lookup: Any = None,
) -> ApkgResult:
    import genanki

    model = genanki.Model(
        MODEL_ID,
        MODEL_NAME,
        fields=[{"name": name} for name in FIELDS],
        templates=[{"name": "Word in context", "qfmt": FRONT, "afmt": BACK}],
        css=CSS,
    )
    deck = genanki.Deck(DECK_ID, deck_name or DEFAULT_DECK_NAME)
    exported: list[str] = []
    skipped = 0
    for lexeme in lexemes:
        if not is_exportable(lexeme):
            skipped += 1
            continue
        fields = build_note_fields(lexeme, definition_lookup=definition_lookup)
        deck.add_note(
            genanki.Note(
                model=model,
                fields=[fields[name] for name in FIELDS],
                guid=genanki.guid_for("kindle-cards", str(lexeme.get("id") or "")),
                tags=note_tags(lexeme),
            )
        )
        exported.append(str(lexeme.get("id") or ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    genanki.Package(deck).write_to_file(str(temporary))
    temporary.replace(output_path)
    logger.info("Wrote Anki package path=%s notes=%d skipped=%d", output_path, len(exported), skipped)
    return ApkgResult(path=output_path, exported_ids=exported, skipped=skipped)


def wordnet_definition(lemma: str, pos: str, context: str) -> str:
    """Offline WordNet gloss for the sense chosen from the book context."""
    from kindle_vocab_app.vocab_optimizer import wordnet_features

    features = wordnet_features(lemma, pos, context)
    return str(features.get("selected_definition") or "") if features.get("available") else ""


def primary_occurrence(lexeme: dict[str, Any]) -> dict[str, Any]:
    """Prefer the longest real context, matching the frontend's choice."""
    occurrences = list(lexeme.get("occurrences") or [])
    return max(
        occurrences,
        key=lambda item: (bool(item.get("context")), len(str(item.get("context") or "")), str(item.get("looked_up_at") or "")),
        default={},
    )


def highlight(context: str, candidates: Iterable[str]) -> str:
    """Escape the context and wrap the first occurrence of the looked-up form."""
    escaped = _escape(context)
    for candidate in sorted({str(item) for item in candidates if str(item).strip()}, key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w'])({re.escape(_escape(candidate))})(?![\w'])", re.IGNORECASE)
        if pattern.search(escaped):
            return pattern.sub(r'<span class="kc-hl">\1</span>', escaped, count=1)
    return escaped


def _escape(value: str) -> str:
    return html.escape(" ".join(str(value or "").split()), quote=False)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _tag(value: str) -> str:
    slug = re.sub(r"[^\w]+", "_", value.casefold(), flags=re.UNICODE).strip("_")
    return slug[:60]
