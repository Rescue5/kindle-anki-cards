"""Contextual card enrichment through a user-supplied LLM provider.

The offline optimizer stays the deterministic source of acceptance and
usefulness. This module only adds what local data cannot provide honestly:
the Russian meaning of the sense used in the book, a learner definition, a
translation of the book sentence and a fresh example. Results are stored per
canonical lexeme, so every word is sent to the provider at most once.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from queue import SimpleQueue
from typing import Any, Protocol

from kindle_vocab_app import card_fields
from kindle_vocab_app.anki_export import is_exportable, primary_occurrence
from kindle_vocab_app.llm import LLMError
from kindle_vocab_app.llm.presets import get_api_key, preset_for
from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

PROMPT_VERSION = 1
BATCH_SIZE = 8
MAX_CONSECUTIVE_FAILED_BATCHES = 3
CONTEXTS_PER_WORD = 2

FIELDS = ("meaning_ru", "definition_en", "context_ru", "example_en", "example_ru", "note_ru")
_FIELD_LIMITS = {"meaning_ru": 120, "definition_en": 200, "context_ru": 600, "example_en": 200, "example_ru": 240, "note_ru": 200}

SYSTEM_PROMPT = """You write vocabulary flashcards for a Russian-speaking adult who reads English books on Kindle.
Each numbered item contains a word the reader looked up, its dictionary form, a part-of-speech guess and up to two excerpts from the book. An excerpt may be truncated.

For every item, first decide which sense the word has in the book sentence, then fill:
- meaning_ru: concise Russian translation of exactly that sense, 1-4 words, in dictionary form (infinitive for verbs, singular nominative for nouns) even if the book uses another form; separate close alternatives with "; ".
- definition_en: short learner-friendly English definition of that sense, at most 15 words.
- context_ru: natural Russian translation of the first book sentence; empty string if there is no sentence.
- example_en: one new short everyday sentence using the word in the same sense. Do not reuse the book sentence.
- example_ru: Russian translation of example_en.
- note_ru: optional short Russian note when it truly helps: register (книжное, устаревшее, разговорное, грубое), part of a phrasal verb or idiom, or a false friend. Otherwise an empty string.

If an item is a proper name, a typo or not an English word, leave meaning_ru empty and explain briefly in note_ru.
Return every item exactly once with its "n" number. Use plain text without markdown."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, **{name: {"type": "string"} for name in FIELDS}},
                "required": ["n", *FIELDS],
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


def needs_enrichment(lexeme: dict[str, Any], *, retry_failed: bool = False) -> bool:
    if not is_exportable(lexeme):
        return False
    enrichment = lexeme.get("enrichment") or {}
    status = enrichment.get("status")
    if status == "ready" and enrichment.get("prompt_version") == PROMPT_VERSION:
        return False
    return retry_failed or status != "failed"


def candidates(
    lexemes: list[dict[str, Any]],
    *,
    ids: set[str] | None = None,
    retry_failed: bool = False,
) -> list[dict[str, Any]]:
    """New words first: the reader cares most about what they just looked up."""
    selected = [
        lexeme
        for lexeme in lexemes
        if (not ids or str(lexeme.get("id") or "") in ids) and needs_enrichment(lexeme, retry_failed=retry_failed)
    ]
    selected.sort(key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)
    selected.sort(key=lambda item: item.get("freshness") != "new")
    return selected


def queue_counts(lexemes: list[dict[str, Any]]) -> dict[str, int]:
    pending = sum(needs_enrichment(item) for item in lexemes)
    failed = sum(
        is_exportable(item) and (item.get("enrichment") or {}).get("status") == "failed" for item in lexemes
    )
    return {"pending": pending, "failed": failed}


def _prompt_items(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for number, lexeme in enumerate(batch, 1):
        analysis = (lexeme.get("processing") or {}).get("analysis") or {}
        primary = primary_occurrence(lexeme)
        items.append(
            {
                "n": number,
                "word": str(primary.get("word") or lexeme.get("display_form") or lexeme.get("lemma") or ""),
                "lemma": str(analysis.get("base_form") or lexeme.get("lemma") or ""),
                "pos": str(analysis.get("pos") or ""),
                "sentences": card_fields.enrichment_sentences(lexeme, CONTEXTS_PER_WORD),
            }
        )
    return items


def build_user_message(batch: list[dict[str, Any]]) -> str:
    return json.dumps({"items": _prompt_items(batch)}, ensure_ascii=False)


def parse_items(data: dict[str, Any], batch_size: int) -> dict[int, dict[str, str]]:
    """Validate the model response; return cleaned payloads keyed by item number."""
    result: dict[int, dict[str, str]] = {}
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        try:
            number = int(raw.get("n"))
        except (TypeError, ValueError):
            continue
        if not 1 <= number <= batch_size or number in result:
            continue
        result[number] = {
            name: " ".join(str(raw.get(name) or "").split())[: _FIELD_LIMITS[name]] for name in FIELDS
        }
    return result


def _request_batch(client: CompletionClient, batch: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    prompt_items = _prompt_items(batch)
    message = json.dumps({"items": prompt_items}, ensure_ascii=False)
    items = parse_items(client.complete_json(SYSTEM_PROMPT, message, SCHEMA), len(batch))
    for number, payload in items.items():
        if payload["context_ru"]:
            sentences = prompt_items[number - 1]["sentences"]
            payload["context_source_sha256"] = card_fields.context_fingerprint(sentences[0]) if sentences else ""
    return items


def _save_batch(
    batch: list[dict[str, Any]], items: dict[int, dict[str, str]], batch_error: str,
    store: EnrichmentStore, provider: str, model: str, summary: EnrichmentSummary,
) -> None:
    for number, lexeme in enumerate(batch, 1):
        payload = items.get(number)
        error = batch_error or "Модель пропустила это слово"
        if payload is not None and not (payload["meaning_ru"] or payload["note_ru"]):
            payload = None
            error = "Модель не дала перевод"
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
) -> EnrichmentSummary:
    summary = EnrichmentSummary(requested=len(lexemes))
    if not lexemes:
        return summary
    if batch_size < 1 or max_parallel_batches < 1:
        raise ValueError("Batch size and concurrency must be positive")
    consecutive_failures = 0
    next_start = 0
    pending = {}
    finished: SimpleQueue[Future[dict[int, dict[str, str]]]] = SimpleQueue()
    with ThreadPoolExecutor(max_workers=max_parallel_batches) as pool:
        while True:
            # Drain available replies before admitting more work (one may be a quota error).
            while (not summary.error and next_start < len(lexemes)
                   and len(pending) < max_parallel_batches and finished.empty()):
                batch = lexemes[next_start : next_start + batch_size]
                future = pool.submit(_request_batch, client, batch)
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
                _save_batch(batch, items, str(error or ""), store, provider, client.model, summary)
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


def test_connection(client: CompletionClient) -> dict[str, str]:
    """Translate one built-in sample word; no library data leaves the computer."""
    items = parse_items(client.complete_json(SYSTEM_PROMPT, build_user_message([SAMPLE_LEXEME]), SCHEMA), 1)
    if 1 not in items or not items[1]["meaning_ru"]:
        raise LLMError("Модель ответила, но не дала перевод пробного слова")
    return items[1]
