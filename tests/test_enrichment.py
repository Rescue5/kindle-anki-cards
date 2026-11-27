from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from kindle_vocab_app import anki_export, enrichment, settings, vocab_cache
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.llm import LLMError
from kindle_vocab_app.llm import presets as llm_presets
from kindle_vocab_app.llm.openai_compatible import parse_json_object
from kindle_vocab_app.tauri_bridge import dispatch


def _lexeme(lemma: str, *, freshness: str = "new", score: int = 6) -> dict:
    return {
        "id": vocab_cache.lexeme_id("en", lemma),
        "lemma": lemma,
        "display_form": lemma,
        "language": "en",
        "forms": [lemma],
        "occurrences": [
            {
                "id": f"occ-{lemma}",
                "source": "kindle",
                "word": lemma,
                "context": f"A sentence with {lemma} in it.",
                "book_key": "book",
                "book_title": "Book",
                "authors": "Author",
                "looked_up_at": "2026-07-10",
            }
        ],
        "freshness": freshness,
        "processing": {
            "state": "ready",
            "analysis": {"base_form": lemma, "pos": "n", "accepted": True, "importance_score": score},
            "updated_at": "",
            "error": "",
        },
        "sources": {"kindle": True, "legacy": False},
        "destinations": {
            "obsidian": {"state": "missing", "reason": "", "last_synced_at": ""},
            "anki": {"state": "not_exported", "last_exported_at": ""},
            "quizlet": {"state": "not_exported", "last_exported_at": ""},
        },
        "first_seen_at": "2026-07-10",
        "last_seen_at": "2026-07-10",
        "last_kindle_sync_id": "sync",
    }


class FakeClient:
    model = "fake-model"

    def __init__(self, *, skip: set[str] | None = None, error: LLMError | None = None) -> None:
        self.skip = skip or set()
        self.error = error
        self.calls: list[dict] = []

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        request = json.loads(user)
        self.calls.append(request)
        if self.error:
            raise self.error
        return {
            "items": [
                {
                    "n": item["n"],
                    "meaning_ru": f"перевод {item['lemma']}",
                    "definition_en": f"meaning of {item['lemma']}",
                    "context_ru": "Предложение.",
                    "example_en": "Example.",
                    "example_ru": "Пример.",
                    "note_ru": "",
                }
                for item in request["items"]
                if item["lemma"] not in self.skip
            ]
        }


class MemoryStore:
    def __init__(self) -> None:
        self.saved: dict[str, dict] = {}

    def save_enrichment(self, language, canonical_key, **fields) -> None:
        self.saved[canonical_key] = fields


class EnrichmentTests(unittest.TestCase):
    def test_later_batch_is_saved_while_the_first_request_is_still_running(self) -> None:
        slow_can_finish = threading.Event()
        caller = threading.get_ident()
        words = [_lexeme(f"word{i}") for i in range(17)]
        progress = []

        class DelayedClient(FakeClient):
            def complete_json(self, system, user, schema):
                if json.loads(user)["items"][0]["lemma"] == "word0" and not slow_can_finish.wait(5):
                    raise AssertionError("Fast batch was not saved")
                return super().complete_json(system, user, schema)

        class ObservedStore(MemoryStore):
            def save_enrichment(self, language, canonical_key, **fields):
                assert threading.get_ident() == caller
                super().save_enrichment(language, canonical_key, **fields)
                if canonical_key == "word15":
                    slow_can_finish.set()

        store = ObservedStore()
        summary = enrichment.enrich(
            words, DelayedClient(), store, provider="openai", max_parallel_batches=2,
            progress=lambda done, total: progress.append((done, total)),
        )
        self.assertEqual(summary.enriched_ids, [word["id"] for word in words])
        self.assertEqual((summary.enriched, summary.batches, summary.failed), (17, 3, 0))
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], (17, 17))
        for word in words:
            stored = store.saved[word["lemma"]]["payload"]
            self.assertEqual(stored["meaning_ru"], "перевод " + word["lemma"])
            source = word["occurrences"][0]["context"]
            self.assertEqual(stored["context_source_sha256"], hashlib.sha256(source.encode()).hexdigest())

    def test_quota_error_drains_active_requests_and_leaves_rest_for_retry(self) -> None:
        started = threading.Barrier(4)
        stopped = threading.Event()
        calls = []

        class QuotaError(LLMError):
            def __str__(self):
                stopped.set()  # The coordinator has observed the failure.
                return super().__str__()

        class QuotaClient(FakeClient):
            def complete_json(self, system, user, schema):
                first = json.loads(user)["items"][0]["lemma"]
                calls.append(first)
                started.wait(5)
                if first == "word0":
                    raise QuotaError("quota", fatal=True)
                if not stopped.wait(5):
                    raise AssertionError("Quota error was not observed")
                return super().complete_json(system, user, schema)

        words = [_lexeme(f"word{i}") for i in range(80)]
        store = MemoryStore()
        result = enrichment.enrich(words, QuotaClient(), store, provider="openai", max_parallel_batches=4)
        self.assertEqual(set(calls), {"word0", "word8", "word16", "word24"})
        self.assertEqual((result.error, result.enriched, result.failed), ("quota", 24, 0))
        for entry in words:
            entry["enrichment"] = store.saved.get(entry["lemma"], {})
        self.assertEqual(len(enrichment.candidates(words)), 56)

    def test_batches_use_short_numbers_and_store_each_word(self) -> None:
        words = [_lexeme(f"word{i}") for i in range(10)]
        client, store = FakeClient(skip={"word3"}), MemoryStore()
        summary = enrichment.enrich(words, client, store, provider="fake", batch_size=8)

        self.assertEqual([len(call["items"]) for call in client.calls], [8, 2])
        self.assertNotIn(words[0]["id"], json.dumps(client.calls))
        self.assertEqual((summary.enriched, summary.failed), (9, 1))
        self.assertEqual(store.saved["word0"]["status"], "ready")
        self.assertEqual(store.saved["word0"]["payload"]["meaning_ru"], "перевод word0")
        self.assertEqual(store.saved["word3"]["status"], "failed")
        self.assertEqual(store.saved["word3"]["error"], "Модель пропустила это слово")

    def test_fatal_error_stops_without_marking_words_failed(self) -> None:
        store = MemoryStore()
        summary = enrichment.enrich(
            [_lexeme("glimpse")], FakeClient(error=LLMError("bad key", fatal=True)), store, provider="fake"
        )
        self.assertEqual(summary.error, "bad key")
        self.assertEqual(store.saved, {})

    def test_timeouts_leave_words_for_the_next_run(self) -> None:
        store = MemoryStore()
        words = [_lexeme(f"word{i}") for i in range(20)]
        client = FakeClient(error=LLMError("slow", transient=True))
        summary = enrichment.enrich(words, client, store, provider="fake", batch_size=2)
        self.assertEqual(store.saved, {})
        self.assertEqual(len(client.calls), enrichment.MAX_CONSECUTIVE_FAILED_BATCHES)
        self.assertEqual(summary.skipped, 2 * enrichment.MAX_CONSECUTIVE_FAILED_BATCHES)
        self.assertIn("slow", summary.error)

    def test_repeated_batch_failures_stop_the_run(self) -> None:
        words = [_lexeme(f"word{i}") for i in range(40)]
        client = FakeClient(error=LLMError("broken json"))
        summary = enrichment.enrich(words, client, MemoryStore(), provider="fake", batch_size=8)
        self.assertEqual(len(client.calls), enrichment.MAX_CONSECUTIVE_FAILED_BATCHES)
        self.assertEqual(summary.error, "broken json")

    def test_candidates_skip_done_and_failed_words_and_put_new_first(self) -> None:
        done = {**_lexeme("done"), "enrichment": {"status": "ready", "prompt_version": enrichment.PROMPT_VERSION}}
        failed = {**_lexeme("failed"), "enrichment": {"status": "failed", "prompt_version": enrichment.PROMPT_VERSION}}
        old = _lexeme("old", freshness="known")
        new = _lexeme("new")
        useless = _lexeme("the", score=1)
        lemmas = lambda items: [item["lemma"] for item in items]
        self.assertEqual(lemmas(enrichment.candidates([old, done, failed, new, useless])), ["new", "old"])
        self.assertIn("failed", lemmas(enrichment.candidates([failed], retry_failed=True)))

    def test_lenient_json_parsing_for_local_models(self) -> None:
        text = '<think>hmm</think>Here you go:\n```json\n{"items": []}\n```'
        self.assertEqual(parse_json_object(text), {"items": []})
        with self.assertRaises(LLMError):
            parse_json_object("no json here")

    def test_enrichment_survives_catalog_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = repository_for(Path(temporary))
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"] = [_lexeme("glimpse")]
            repository.save_catalog(catalog)
            client = FakeClient()
            enrichment.enrich(repository.load_catalog()["lexemes"], client, repository, provider="fake")
            [original] = client.calls[0]["items"][0]["sentences"]

            updated = repository.load_catalog()
            lexeme = updated["lexemes"][0]
            [occurrence] = lexeme["occurrences"]
            lexeme["occurrences"].append({
                **occurrence, "id": "other-book", "book_key": "other", "book_title": "Other Book",
                "context": "A much longer quotation with a glimpse from the other book.",
            })
            repository.save_catalog(updated)

            [lexeme] = repository.load_catalog()["lexemes"]
            stored = lexeme["enrichment"]
            self.assertEqual(stored["status"], "ready")
            self.assertEqual(stored["meaning_ru"], "перевод glimpse")
            self.assertEqual(stored["model"], "fake-model")
            self.assertEqual(stored["context_source_sha256"], hashlib.sha256(original.encode()).hexdigest())
            self.assertEqual(anki_export.build_note_fields(lexeme)["ContextTranslation"], "")
            fields = anki_export.build_note_fields(lexeme, edit={"example_occurrence_id": occurrence["id"]})
            self.assertEqual(fields["ContextTranslation"], "Предложение.")

    def test_bridge_enrich_and_config_never_expose_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"] = [_lexeme("glimpse"), _lexeme("dread")]
            repository_for(workspace).save_catalog(catalog)
            settings.save(workspace, settings.AppSettings(llm_enabled=True, llm_provider="deepseek"))

            with patch.dict("os.environ", {llm_presets.ENV_API_KEY: "sk-secret-value"}):
                config = dispatch("llm_config", {}, workspace)
                self.assertNotIn("sk-secret-value", json.dumps(config))
                self.assertTrue(config["has_key"]["deepseek"])

            with patch("kindle_vocab_app.enrichment.build_client", return_value=FakeClient()):
                result = dispatch("enrich_lexemes", {}, workspace)
            self.assertEqual(result["enriched"], 2)
            self.assertEqual(result["enrichmentQueue"], {"pending": 0, "failed": 0})
            library = dispatch("load_library", {}, workspace)
            self.assertEqual({entry["enrichment"]["status"] for entry in library["entries"]}, {"ready"})

    def test_bridge_enrichment_sends_only_disclosed_fields_and_respects_off_switch(self) -> None:
        title = "Private Book Title"
        sources = ["A" * 405, "B" * 404, "Short discarded sentence."]
        word = _lexeme("glimpse")
        word["occurrences"] = [
            {
                **word["occurrences"][0], "id": f"context-{index}", "word": "glimpsed",
                "context": context, "book_title": title, "authors": "Private Author",
            }
            for index, context in enumerate(sources)
        ]
        requests: list[str] = []

        class CaptureClient(FakeClient):
            def complete_json(self, system: str, user: str, schema: dict) -> dict:
                requests.append(user)
                return super().complete_json(system, user, schema)

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"] = [word, _lexeme("dread")]
            repository_for(workspace).save_catalog(catalog)
            settings.save(workspace, settings.AppSettings(llm_auto_enrich=True, llm_provider="openai"))
            manual = {"ids": [word["id"]]}
            automatic: dict = {}
            with patch.object(enrichment, "build_client", return_value=CaptureClient()) as client:
                for payload in (manual, automatic):
                    with self.assertRaisesRegex(ValueError, "Включите перевод через ИИ"):
                        dispatch("enrich_lexemes", payload, workspace)
                client.assert_not_called()
                self.assertEqual(requests, [])

                settings.save(workspace, settings.AppSettings(
                    llm_enabled=True, llm_auto_enrich=True, llm_provider="openai",
                ))
                self.assertEqual(dispatch("enrich_lexemes", manual, workspace)["enriched"], 1)
                self.assertEqual(dispatch("enrich_lexemes", automatic, workspace)["enriched"], 1)
                self.assertEqual(dispatch("enrich_lexemes", automatic, workspace)["enriched"], 0)
                self.assertTrue(dispatch("test_llm", {}, workspace)["ok"])

        self.assertEqual([json.loads(request) for request in requests], [
            {"items": [{"n": 1, "word": "glimpsed", "lemma": "glimpse", "pos": "n",
                        "sentences": ["A" * 400, "B" * 400]}]},
            {"items": [{"n": 1, "word": "dread", "lemma": "dread", "pos": "n",
                        "sentences": ["A sentence with dread in it."]}]},
            {"items": [{"n": 1, "word": "glimpse", "lemma": "glimpse", "pos": "n",
                        "sentences": ["For a moment he caught a glimpse of the city below."]}]},
        ])

    def test_old_settings_keep_their_custom_endpoint(self) -> None:
        legacy = {"llm_enabled": True, "llm_model": "m", "llm_base_url": "https://example.test/v1"}
        migrated = settings.from_dict(legacy)
        self.assertEqual(migrated.llm_provider, "custom")
        self.assertEqual(migrated.llm_base_url, "https://example.test/v1")
        self.assertEqual(settings.from_dict({}).llm_provider, "")


if __name__ == "__main__":
    unittest.main()
