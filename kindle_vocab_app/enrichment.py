"""Contextual card enrichment through a user-supplied LLM provider.

The offline optimizer stays the deterministic source of acceptance and
usefulness. This module only adds what local data cannot provide honestly:
the Russian meaning of the sense used in the book, a learner definition, a
translation of the selected quote and a fresh example when needed. Results are
stored per canonical lexeme and tied to the input used to generate them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from queue import SimpleQueue
from typing import Any, Protocol

from kindle_vocab_app import card_fields
from kindle_vocab_app.anki_export import is_exportable
from kindle_vocab_app.contracts import MEANING_MAX_LENGTH
from kindle_vocab_app.llm import LLMError
from kindle_vocab_app.llm.presets import get_api_key, preset_for
from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

PROMPT_VERSION = 2
BATCH_SIZE = 8
MAX_CONSECUTIVE_FAILED_BATCHES = 3

_FIELD_LIMITS = {
    "meaning_ru": MEANING_MAX_LENGTH, "definition_en": 200, "context_ru": 600,
    "example_en": 200, "example_ru": 240, "note_ru": 200, "context_meaning_ru": MEANING_MAX_LENGTH,
}
_MEANING_ACTIONS = ("kept", "refined", "added")
_CONTEXT_QUALITIES = ("good", "weak", "ambiguous", "missing")
_SENSE_FIELDS = ("meaning_ru", "example_en", "example_ru")

SYSTEM_PROMPT = """You write vocabulary flashcards for a Russian-speaking adult who reads English books on Kindle.
Each numbered item contains the word, its dictionary form, a part-of-speech guess, the current Russian meaning and zero or one selected book excerpt. The excerpt may be truncated.
The part of speech and existing translation are fallible hints. First identify what the excerpt actually uses.
If the lookup is a piece of a compound or idiom, explain the whole expression in the excerpt. Review the
standalone lemma separately and do not treat the meaning of the full expression as a sense of that lemma.
For example, "light" in "light-headed" is part of an expression meaning "испытывающий головокружение".
Standalone "light" still has major meanings such as "свет", "лёгкий" and "зажигать".

For every item, fill:
- meaning_ru and meaning_action: give a concise dictionary-form translation of the lemma covering its main everyday meanings. Keep the existing text verbatim (kept) only if it already covers them adequately. Refine it if it gives a wrong meaning or only a narrow sense of a common polysemous word. If none exists, supply one (added).
- context_meaning_ru: Russian meaning specifically in the selected excerpt; name the full expression when the lookup is only part of one. Leave empty when the excerpt does not establish a sense.
- context_quality: good if the excerpt teaches the sense, weak if it is fragmentary or hard to learn from, ambiguous if multiple senses fit, missing if there is no excerpt.
- definition_en: short learner-friendly English definition of that sense, at most 15 words.
- context_ru: translate only the supplied excerpt. Leave empty when none is supplied.
- example_en and example_ru: for weak, ambiguous or missing context, write a new short example that clearly demonstrates a supported sense, then translate it. Leave both empty if a good excerpt suffices. Do not reuse a book excerpt.
- senses: if examples_per_sense is true, list the substantially different common senses of the standalone lemma across parts of speech. If the lemma is commonly used as both a noun and a verb, include both. Also include its common adjectival, adverbial or other uses where applicable. Do this even if the existing translation is kept or the excerpt teaches a sense. Give each meaning_ru its own example_en using the lemma in that sense and matching example_ru. Combine near synonyms and omit obscure senses. Return a single sense when the lemma genuinely has only one common sense. If examples_per_sense is false, return an empty array.
- note_ru: optional short Russian note when it truly helps: register (книжное, устаревшее, разговорное, грубое), part of a phrasal verb or idiom, or a false friend. Otherwise an empty string.

If an item is a proper name, a typo or not an English word, leave meaning_ru empty and explain briefly in note_ru.
Return every item exactly once with its "n" number. Use plain text without markdown."""

_ITEM_PROPERTIES = {
    "n": {"type": "integer"},
    **{name: {"type": "string"} for name in _FIELD_LIMITS},
    "meaning_action": {"type": "string", "enum": list(_MEANING_ACTIONS)},
    "context_quality": {"type": "string", "enum": list(_CONTEXT_QUALITIES)},
    "senses": {"type": "array", "items": {
        "type": "object", "properties": {name: {"type": "string"} for name in _SENSE_FIELDS},
        "required": list(_SENSE_FIELDS), "additionalProperties": False,
    }},
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _ITEM_PROPERTIES,
                "required": list(_ITEM_PROPERTIES),
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class CompletionClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class EnrichmentStore(Protocol):
    def save_enrichment(
        self,
        language: str,
        canonical_key: str,
        *,
        status: str,
        provider: str,
        model: str,
        prompt_version: int,
        payload: dict[str, Any] | None,
        error: str = "",
    ) -> None: ...


@dataclass
class EnrichmentSummary:
    requested: int = 0
    enriched: int = 0
    failed: int = 0
    skipped: int = 0
    batches: int = 0
    error: str = ""
    enriched_ids: list[str] = field(default_factory=list)


def build_client(provider: str, model: str, base_url: str = "", *, parallel: bool = False) -> CompletionClient:
    preset = preset_for(provider)
    api_key = get_api_key(provider) if preset.needs_key else ""
    if preset.needs_key and not api_key:
        raise LLMError("Добавьте ключ API в настройках ИИ", fatal=True)
    if preset.kind == "anthropic":
        from kindle_vocab_app.llm.anthropic_client import AnthropicClient

        return AnthropicClient(api_key=api_key, model=model or preset.default_model)
    from kindle_vocab_app.llm.openai_compatible import OpenAICompatibleClient

    return OpenAICompatibleClient(
        base_url=base_url or preset.base_url,
        api_key=api_key,
        model=model or preset.default_model,
        # A slow local model would only be asked the same question again.
        timeout=600.0 if preset.local else 120.0,
        max_retries=0 if preset.local or parallel else 2,
    )


def batch_size_for(default: int, *, examples_per_sense: bool) -> int:
    return min(default, 2) if examples_per_sense else default


def _ineligible_reason(lexeme: Mapping[str, Any]) -> str:
    if (lexeme.get("processing") or {}).get("state") not in {"ready", "rejected"}:
        return "Слово ещё не обработано"
    spelling = str(lexeme.get("display_form") or lexeme.get("lemma") or "")
    return "" if any(character.isalpha() for character in spelling) else "В записи нет букв"


def needs_enrichment(lexeme: dict[str, Any], *, retry_failed: bool = False, decision: str = "") -> bool:
    """Conservative automatic admission, including for libraries upgraded from v1."""
    if decision in {"skip", "known", "junk"} or _ineligible_reason(lexeme) or not is_exportable(lexeme):
        return False
    status = (lexeme.get("enrichment") or {}).get("status")
    return status != "ready" and (retry_failed or status != "failed")


def enrichment_state(
    lexeme: Mapping[str, Any], edit: Mapping[str, Any] | None = None, *, examples_per_sense: bool = False,
) -> str:
    if _ineligible_reason(lexeme):
        return "ineligible"
    stored = lexeme.get("enrichment") or {}
    status = stored.get("status")
    if status == "failed":
        return "failed"
    if (status == "ready" and stored.get("prompt_version") == PROMPT_VERSION
            and stored.get("input_fingerprint") == _prepare_word(lexeme, edit, examples_per_sense).fingerprint):
        return "ready"
    return "pending"


def decorate(
    entries: list[dict[str, Any]], edits: Mapping[str, Mapping[str, Any]], *, examples_per_sense: bool,
) -> None:
    for entry in entries:
        edit = edits.get(entry["id"])
        entry["enrichment_state"] = enrichment_state(entry, edit, examples_per_sense=examples_per_sense)
        if entry["enrichment_state"] == "ineligible":
            entry["enrichment_ineligible_reason"] = _ineligible_reason(entry)
        if stored := entry.get("enrichment"):
            selected = card_fields.resolve(entry, edit, include_enrichment=False).occurrence
            context = str(selected.get("context") or "")
            applicable = card_fields.enrichment_for_context(entry, context)
            proven = "selected_context_sha256" in stored or bool(stored.get("context_source_sha256"))
            context_matches = bool(applicable and (proven or card_fields.context_translation(entry, context)))
            decorated = {**stored, "context_matches": context_matches}
            if stored.get("prompt_version") == PROMPT_VERSION:
                decorated["review_matches"] = bool(card_fields.enrichment_for_card(entry, edit))
            entry["enrichment"] = decorated


def candidates(
    lexemes: list[dict[str, Any]],
    *,
    ids: set[str] | None = None,
    retry_failed: bool = False,
    recheck: bool = False,
    edits: Mapping[str, Mapping[str, Any]] | None = None,
    decisions: Mapping[str, Mapping[str, Any]] | None = None,
    examples_per_sense: bool = False,
) -> list[dict[str, Any]]:
    """New words first: the reader cares most about what they just looked up."""
    if recheck and (ids is None or len(ids) != 1):
        return []
    if ids is None:
        decisions = decisions or {}
        selected = [lexeme for lexeme in lexemes if needs_enrichment(
            lexeme, retry_failed=retry_failed, decision=str(decisions.get(lexeme["id"], {}).get("value") or ""),
        )]
    else:
        edits = edits or {}
        states = {"ready"} if recheck else {"pending"}
        if retry_failed and not recheck:
            states.add("failed")
        selected = [lexeme for lexeme in lexemes if lexeme["id"] in ids and enrichment_state(
            lexeme, edits.get(lexeme["id"]), examples_per_sense=examples_per_sense,
        ) in states]
    selected.sort(key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)
    selected.sort(key=lambda item: item.get("freshness") != "new")
    return selected


def queue_counts(
    lexemes: list[dict[str, Any]], decisions: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    pending = len(candidates(lexemes, decisions=decisions))
    failed = sum(not _ineligible_reason(item) and (item.get("enrichment") or {}).get("status") == "failed" for item in lexemes)
    return {"pending": pending, "failed": failed}


@dataclass(frozen=True)
class _WordInput:
    word: str
    lemma: str
    pos: str
    current_meaning: str
    context: str
    review_fingerprint: str
    fingerprint: str

    @property
    def excerpt(self) -> str:
        return self.context[:card_fields.MAX_ENRICHMENT_CONTEXT_CHARS]


def _prepare_word(
    lexeme: Mapping[str, Any], edit: Mapping[str, Any] | None, examples_per_sense: bool,
    *, recheck: bool = False,
) -> _WordInput:
    analysis = (lexeme.get("processing") or {}).get("analysis") or {}
    source = card_fields.resolve(lexeme, edit, include_enrichment=False)
    current = source if recheck else card_fields.resolve(lexeme, edit)
    occurrence = source.occurrence
    word = str(occurrence.get("word") or lexeme.get("display_form") or lexeme.get("lemma") or "")
    lemma = str(analysis.get("base_form") or lexeme.get("lemma") or "")
    pos = str(analysis.get("pos") or "")
    context = str(occurrence.get("context") or "")
    review = card_fields.review_fingerprint(lexeme, source)
    fingerprint = card_fields.context_fingerprint(json.dumps([review, examples_per_sense]))
    return _WordInput(word, lemma, pos, current.meaning_ru, context, review, fingerprint)


def _user_message(words: list[_WordInput], examples_per_sense: bool) -> str:
    return json.dumps({"examples_per_sense": examples_per_sense, "items": [
        {"n": number, "word": word.word, "lemma": word.lemma, "pos": word.pos,
         "current_meaning_ru": word.current_meaning, "sentences": [word.excerpt] if word.excerpt else []}
        for number, word in enumerate(words, 1)
    ]}, ensure_ascii=False)


def parse_items(data: dict[str, Any], batch_size: int) -> dict[int, dict[str, Any]]:
    """Validate the model response; return cleaned payloads keyed by item number."""
    result: dict[int, dict[str, Any]] = {}
    seen: set[int] = set()
    rows = data.get("items")
    if not isinstance(rows, list):
        return result
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        number = raw.get("n")
        if type(number) is not int or not 1 <= number <= batch_size:
            continue
        if number in seen:
            result.pop(number, None)
            continue
        seen.add(number)
        if not all(isinstance(raw.get(name), str) for name in _FIELD_LIMITS):
            continue
        if raw.get("meaning_action") not in _MEANING_ACTIONS or raw.get("context_quality") not in _CONTEXT_QUALITIES:
            continue
        senses = _senses(raw.get("senses"))
        if senses is None:
            continue
        result[number] = {
            **{name: " ".join(raw[name].split())[:limit] for name, limit in _FIELD_LIMITS.items()},
            "meaning_action": raw["meaning_action"], "context_quality": raw["context_quality"],
            "senses": senses,
        }
    return result


def _senses(raw_senses: Any) -> list[dict[str, str]] | None:
    result = []
    seen: set[str] = set()
    if not isinstance(raw_senses, list):
        return None
    for raw in raw_senses:
        if not isinstance(raw, dict) or not all(isinstance(raw.get(name), str) for name in _SENSE_FIELDS):
            return None
        sense = {name: " ".join(raw[name].split())[:_FIELD_LIMITS[name]] for name in _SENSE_FIELDS}
        key = sense["meaning_ru"].casefold()
        if not all(sense.values()):
            return None
        if key in seen:
            continue
        result.append(sense)
        seen.add(key)
    return result


def _request_batch(
    client: CompletionClient, words: list[_WordInput], examples_per_sense: bool,
) -> dict[int, dict[str, Any]]:
    message = _user_message(words, examples_per_sense)
    items = parse_items(client.complete_json(SYSTEM_PROMPT, message, SCHEMA), len(words))
    for number, payload in list(items.items()):
        word = words[number - 1]
        if payload["meaning_action"] == "kept" and word.current_meaning:
            payload["meaning_ru"] = word.current_meaning
        payload["meaning_action"] = (
            "kept" if word.current_meaning and payload["meaning_ru"] == word.current_meaning
            else "refined" if word.current_meaning else "added"
        )
        if not word.excerpt:
            payload.update(context_ru="", context_meaning_ru="", context_quality="missing")
        elif payload["context_quality"] == "missing":
            payload["context_quality"] = "weak"
        if not (payload["example_en"] and payload["example_ru"]):
            payload.update(example_en="", example_ru="")
            if payload["meaning_ru"] and payload["context_quality"] != "good":
                items.pop(number)
                continue
        if not examples_per_sense:
            payload["senses"] = []
        payload.update(
            input_fingerprint=word.fingerprint,
            review_fingerprint=word.review_fingerprint,
            selected_context_sha256=card_fields.context_fingerprint(word.context),
            context_source_sha256=card_fields.context_fingerprint(word.excerpt),
            context_truncated=len(word.context) > len(word.excerpt),
        )
    return items


def _save_batch(
    batch: list[dict[str, Any]], items: dict[int, dict[str, Any]], batch_error: str,
    store: EnrichmentStore, provider: str, model: str, summary: EnrichmentSummary, *, recheck: bool,
) -> None:
    for number, lexeme in enumerate(batch, 1):
        payload = items.get(number)
        error = batch_error or "Модель пропустила это слово"
        stored = lexeme.get("enrichment") or {}
        translation_required = recheck and bool(stored.get("meaning_ru"))
        if payload is not None and not (payload["meaning_ru"] or (payload["note_ru"] and not translation_required)):
            payload = None
            error = "Модель не дала перевод"
        if payload is not None or stored.get("status") != "ready":
            store.save_enrichment(
                str(lexeme.get("language") or "en"), str(lexeme.get("lemma") or ""),
                status="ready" if payload is not None else "failed", provider=provider,
                model=model, prompt_version=PROMPT_VERSION, payload=payload,
                error="" if payload is not None else error,
            )
        if payload is None:
            summary.failed += 1
        else:
            summary.enriched += 1
            summary.enriched_ids.append(str(lexeme.get("id") or ""))


def enrich(
    lexemes: list[dict[str, Any]],
    client: CompletionClient,
    store: EnrichmentStore,
    *,
    provider: str,
    progress: Callable[[int, int], None] | None = None,
    batch_size: int = BATCH_SIZE,
    max_parallel_batches: int = 1,
    edits: Mapping[str, Mapping[str, Any]] | None = None,
    examples_per_sense: bool = False,
    recheck: bool = False,
) -> EnrichmentSummary:
    summary = EnrichmentSummary(requested=len(lexemes))
    if not lexemes:
        return summary
    if batch_size < 1 or max_parallel_batches < 1:
        raise ValueError("Batch size and concurrency must be positive")
    batch_size = batch_size_for(batch_size, examples_per_sense=examples_per_sense)
    consecutive_failures = 0
    next_start = 0
    pending = {}
    edits = edits or {}
    finished: SimpleQueue[Future[dict[int, dict[str, Any]]]] = SimpleQueue()
    with ThreadPoolExecutor(max_workers=max_parallel_batches) as pool:
        while True:
            # Drain available replies before admitting more work (one may be a quota error).
            while (not summary.error and next_start < len(lexemes)
                   and len(pending) < max_parallel_batches and finished.empty()):
                batch = lexemes[next_start : next_start + batch_size]
                inputs = [
                    _prepare_word(word, edits.get(word["id"]), examples_per_sense, recheck=recheck) for word in batch
                ]
                future = pool.submit(_request_batch, client, inputs, examples_per_sense)
                pending[future] = batch
                future.add_done_callback(finished.put)
                next_start += len(batch)
                summary.batches += 1
            if not pending:
                break
            future = finished.get()
            batch = pending.pop(future)
            error = None
            try:
                items = future.result()
            except LLMError as exc:
                items, error = {}, exc
            if error and error.fatal:
                summary.error = summary.error or str(error)
                continue
            if error and error.transient:
                summary.skipped += len(batch)
            else:
                _save_batch(batch, items, str(error or ""), store, provider, client.model, summary, recheck=recheck)
                if progress:
                    progress(summary.enriched + summary.failed, summary.requested)
            consecutive_failures = 0 if items else consecutive_failures + 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILED_BATCHES and not summary.error:
                summary.error = str(error or "Модель несколько раз подряд не вернула переводы")
    if summary.skipped and not summary.error:
        summary.error = "Некоторые запросы не завершились. Оставшиеся слова можно перевести повторно."
    # Results arrive out of order. Preserve the caller's ordering of successful IDs.
    saved_ids = set(summary.enriched_ids)
    summary.enriched_ids = [str(word.get("id") or "") for word in lexemes if str(word.get("id") or "") in saved_ids]
    return summary


SAMPLE_LEXEME: dict[str, Any] = {
    "id": "sample",
    "lemma": "glimpse",
    "display_form": "glimpse",
    "language": "en",
    "occurrences": [
        {"word": "glimpse", "context": "For a moment he caught a glimpse of the city below."}
    ],
    "processing": {"analysis": {"base_form": "glimpse", "pos": "n"}},
}


def test_connection(client: CompletionClient) -> dict[str, Any]:
    """Translate one built-in sample word; no library data leaves the computer."""
    items = _request_batch(client, [_prepare_word(SAMPLE_LEXEME, None, False)], False)
    if 1 not in items or not items[1]["meaning_ru"]:
        raise LLMError("Модель ответила, но не дала перевод пробного слова")
    return items[1]
