"""B4: `load_library` returns a ranked short list (library_view), card fields and export policy."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from short_list_fixture import (
    KOREADER_BOOK,
    build_library,
    letters,
    lid,
    word,
    worth_words,
)

from kindle_vocab_app import card_fields, contracts, export_policy, library_view, settings
from kindle_vocab_app.ranking import RANKING_VERSION
from kindle_vocab_app.tauri_bridge import dispatch


def _problems(library: dict[str, Any]) -> list[str]:
    return contracts.validate_library(library)


def _load(workspace: Path) -> dict[str, Any]:
    result = dispatch("load_library", {}, workspace)
    assert _problems(result) == [], _problems(result)
    return result


def _entry(library: dict[str, Any], lemma: str) -> dict[str, Any]:
    return next(entry for entry in library["entries"] if entry["id"] == lid(lemma))


class PayloadTests(unittest.TestCase):
    def test_a_mixed_library_validates_and_every_part_is_present(self) -> None:
        words = [
            *worth_words(4),
            word("ravelin", days=(50,), zipf=3.6),
            word("gloamy", warnings=["possibly_glued_words"]),
            word("zzxqv", warnings=["non_word"]),
            word("pending", state="pending"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_library(workspace, words)
            library = _load(workspace)

        self.assertEqual(library["rankingVersion"], RANKING_VERSION)
        self.assertEqual(library["rankingMode"], "learning")
        self.assertTrue(library["repeatSignal"])
        self.assertEqual(library["historyDays"], 50)
        self.assertEqual(library["again"], {"count": 0, "ids": [], "unavailable": False})
        self.assertEqual(library["shelves"]["worth"], 4)
        self.assertIsNone(_entry(library, "pending")["ranking"])
        self.assertEqual(_entry(library, "gloamy")["ranking"]["shelf"], "disputed")
        self.assertEqual(_entry(library, "zzxqv")["ranking"]["shelf"], "junk")
        # Old fields stay for the old screens.
        first = library["entries"][0]
        for key in ("lemma", "processing", "destinations", "occurrences", "dictionary", "freshness"):
            self.assertIn(key, first)
        self.assertIn("books", library)
        self.assertIn("connectors", library)

    def test_an_empty_library_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            library = _load(Path(temporary))
        self.assertEqual(library["entries"], [])
        self.assertEqual(library["newBatch"], {"count": 0, "ids": []})
        self.assertEqual(library["historyDays"], 0)
        self.assertEqual(library["rankingMode"], "learning")

    def test_the_demo_library_is_ranked_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            # A reader's own decision must not leak into the demo.
            build_library(workspace, [word("afraid")]).set_decision(lid("afraid"), "skip")
            result = dispatch("load_demo", {}, workspace)
        self.assertEqual(_problems(result), [])
        self.assertTrue(all(entry["ranking"] for entry in result["entries"]))
        self.assertGreaterEqual(result["newBatch"]["count"], 3)
        self.assertGreaterEqual(result["shelves"]["worth"], 3)
        self.assertGreaterEqual(len(result["disputed"]["ids"]), 1)
        self.assertTrue(all(entry["decision"] is None for entry in result["entries"]))
        self.assertTrue(any(entry["card"]["meaning_source"] == "dictionary" for entry in result["entries"]))

    def test_responses_that_return_entries_carry_the_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_library(workspace, [word("pending", state="pending")])
            result = dispatch("process_queue", {}, workspace)
        self.assertEqual(_problems(result), [])


class NewBatchTests(unittest.TestCase):
    def test_batch_is_the_best_ranked_words_cut_at_the_size_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_library(workspace, worth_words(8))
            everything = _load(workspace)
            settings.save(workspace, settings.AppSettings(export_batch_size=5))
            cut = _load(workspace)

        self.assertEqual(everything["newBatch"]["count"], 8)
        self.assertEqual(cut["newBatch"]["count"], 5)
        ranks = [_by_id(cut, lexeme_id)["ranking"]["rank"] for lexeme_id in cut["newBatch"]["ids"]]
        self.assertEqual(ranks, [1, 2, 3, 4, 5])
        # The most recent lookup ranks first.
        self.assertEqual(cut["newBatch"]["ids"][0], lid("lumena"))
        self.assertEqual(cut["newBatch"]["ids"], everything["newBatch"]["ids"][:5])

    def test_only_worth_words_are_in_it_and_unprocessed_words_never(self) -> None:
        words = [*worth_words(2), word("pending", state="pending"), word("faded", days=(60,))]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_library(workspace, words)
            library = _load(workspace)
        self.assertEqual(sorted(library["newBatch"]["ids"]), sorted([lid("lumena"), lid("lumenb")]))

    def test_decisions_move_words_in_and_out(self) -> None:
        words = [*worth_words(2), word("faded", days=(60,))]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = build_library(workspace, words)
            repository.set_decision(lid("faded"), "learn")
            repository.set_decision(lid("lumena"), "skip")
            library = _load(workspace)

        self.assertEqual(set(library["newBatch"]["ids"]), {lid("faded"), lid("lumenb")})
        self.assertEqual(_entry(library, "faded")["decision"]["value"], "learn")
        self.assertEqual(_entry(library, "faded")["ranking"]["shelf"], "worth")
        self.assertEqual(_entry(library, "lumena")["ranking"]["shelf"], "not_worth")

    def test_exported_words_leave_the_batch_and_stop_being_new(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = build_library(workspace, worth_words(3))
            before = _load(workspace)
            repository.record_export_run("anki", [lid("lumena")])
            after = _load(workspace)

        self.assertTrue(_entry(before, "lumena")["is_new"])
        self.assertNotIn(lid("lumena"), after["newBatch"]["ids"])
        self.assertEqual(after["newBatch"]["count"], 2)
        exported = _entry(after, "lumena")
        self.assertEqual(exported["export"]["state"], "exported")
        self.assertTrue(exported["export"]["last_exported_at"])
        self.assertFalse(exported["is_new"])
        # Still on the shelf, still ranked: only the batch changes.
        self.assertEqual(exported["ranking"]["shelf"], "worth")
        self.assertEqual(after["shelves"]["worth"], 3)


class DisputedTests(unittest.TestCase):
    def test_at_most_five_best_scoring_words_not_exported_and_not_decided(self) -> None:
        words = [
            word(f"glom{letters(index)}", days=(index,), warnings=["possibly_glued_words"])
            for index in range(8)
        ]
        words.append(word("lumena"))
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = build_library(workspace, words)
            library = _load(workspace)
            self.assertEqual(library["shelves"]["disputed"], 8)
            self.assertEqual(len(library["disputed"]["ids"]), contracts.DISPUTED_CAP)
            best = sorted(
                (e for e in library["entries"] if e["ranking"]["shelf"] == "disputed"),
                key=lambda e: e["ranking"]["rank"],
            )[:5]
            self.assertEqual(library["disputed"]["ids"], [e["id"] for e in best])
            self.assertTrue(set(library["disputed"]["ids"]).isdisjoint(library["newBatch"]["ids"]))

            # An answered or exported word drops out and the next one takes its place.
            first, second = library["disputed"]["ids"][:2]
            repository.set_decision(first, "skip")
            repository.record_export_run("csv", [second])
            again = _load(workspace)
        self.assertNotIn(first, again["disputed"]["ids"])
        self.assertNotIn(second, again["disputed"]["ids"])
        self.assertEqual(len(again["disputed"]["ids"]), contracts.DISPUTED_CAP)


class ModeTests(unittest.TestCase):
    def test_a_koreader_only_library_is_in_learning_mode_without_a_repeat_signal(self) -> None:
        words = [
            word(f"lumen{suffix}", days=(index,), book=KOREADER_BOOK)
            for index, suffix in enumerate("abcd")
        ]
        words.append(word("ravelin", days=(100,), book=KOREADER_BOOK))
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_library(workspace, words)
            library = _load(workspace)

        self.assertEqual(library["rankingMode"], "learning")
        self.assertFalse(library["repeatSignal"])
        self.assertEqual(library["historyDays"], 100)
        self.assertEqual(library["again"], {"count": 0, "ids": [], "unavailable": True})
        # No reason cites a signal this reader does not keep.
        codes = {
            reason["code"]
            for entry in library["entries"]
            for reason in (entry["ranking"] or {"reasons": []})["reasons"]
        }
        self.assertTrue(codes.isdisjoint({"repeat_lookups", "several_books", "after_export"}))

    def test_a_long_kindle_history_is_ranked_in_full_mode(self) -> None:
        words = [*worth_words(3), word("ravelin", days=(70,))]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_library(workspace, words)
            library = _load(workspace)
        self.assertEqual(library["rankingMode"], "full")
        self.assertEqual(library["historyDays"], 70)


class CardTests(unittest.TestCase):
    def test_card_in_the_payload_follows_edits_llm_and_dictionary(self) -> None:
        words = [word("lumena", days=(0, 1, 2)), word("lumenb"), word("lumenc")]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = build_library(workspace, words)
            repository.save_enrichment(
                "en", "lumenb", status="ready", provider="test", model="m", prompt_version=1,
                payload={"meaning_ru": "свет"},
            )
            repository.save_card_edit(lid("lumena"), meaning_ru="  мой  перевод ")
            repository.save_card_edit(lid("lumena"), example_occurrence_id="lumena-o0")
            library = _load(workspace)

        edited = _entry(library, "lumena")["card"]
        self.assertEqual(edited["meaning_ru"], "мой перевод")
        self.assertEqual(edited["meaning_source"], "edited")
        self.assertEqual(edited["example_occurrence_id"], "lumena-o0")
        self.assertTrue(edited["edited"])
        generated = _entry(library, "lumenb")["card"]
        self.assertEqual((generated["meaning_ru"], generated["meaning_source"]), ("свет", "llm"))
        self.assertFalse(generated["edited"])
        # The longest sentence is the default example.
        default = _entry(library, "lumenc")["card"]
        self.assertEqual(default["example_occurrence_id"], "lumenc-o0")


class CardFieldsTests(unittest.TestCase):
    def _lexeme(self, **extra: Any) -> dict[str, Any]:
        return {**word("lumena", days=(0, 1, 2)), **extra}

    def test_translation_priority_is_edit_then_llm_then_dictionary(self) -> None:
        lexeme = self._lexeme(
            enrichment={"status": "ready", "meaning_ru": "от ИИ"},
            dictionary={"meaning_ru": "из словаря"},
        )
        self.assertEqual(card_fields.resolve(lexeme, {"meaning_ru": "своё"}).meaning_source, "edited")
        self.assertEqual(card_fields.resolve(lexeme).meaning_source, "llm")
        lexeme["enrichment"] = {"status": "failed", "meaning_ru": "от ИИ"}
        self.assertEqual(card_fields.resolve(lexeme).meaning_ru, "из словаря")
        lexeme["dictionary"] = None
        card = card_fields.resolve(lexeme)
        self.assertEqual((card.meaning_ru, card.meaning_source), ("", "none"))

    def test_example_is_the_chosen_occurrence_else_the_longest_context(self) -> None:
        lexeme = self._lexeme()
        self.assertEqual(card_fields.resolve(lexeme).example_occurrence_id, "lumena-o2")
        chosen = card_fields.resolve(lexeme, {"example_occurrence_id": "lumena-o0"})
        self.assertEqual(chosen.example_occurrence_id, "lumena-o0")
        self.assertTrue(chosen.edited)
        self.assertEqual(card_fields.resolve(self._lexeme(occurrences=[])).example_occurrence_id, "")

    def test_a_long_dictionary_meaning_loses_whole_trailing_senses(self) -> None:
        senses = ["; ".join(f"значение номер {n}" for n in range(30))]
        card = card_fields.resolve(self._lexeme(dictionary={"meaning_ru": senses[0]}))
        self.assertLessEqual(len(card.meaning_ru), contracts.MEANING_MAX_LENGTH)
        self.assertTrue(card.meaning_ru.startswith("значение номер 0; значение номер 1"))
        self.assertFalse(card.meaning_ru.endswith(";"))
        single = card_fields.resolve(self._lexeme(dictionary={"meaning_ru": "я" * 500}))
        self.assertEqual(len(single.meaning_ru), contracts.MEANING_MAX_LENGTH)

    def test_a_picked_sentence_that_left_the_library_is_kept_for_the_writers(self) -> None:
        edit = {"example_occurrence_id": "gone", "example_context": "A kept sentence.", "example_form": "lumena"}
        card = card_fields.resolve(self._lexeme(), edit)
        self.assertEqual(card.occurrence["context"], "A kept sentence.")
        self.assertEqual(card.example_occurrence_id, "")
        self.assertTrue(card.edited)


class ExportPolicyTests(unittest.TestCase):
    def _entry(self, shelf: str | None, decision: str | None = None, state: str = "ready") -> dict[str, Any]:
        return {
            "processing": {"state": state},
            "ranking": {"shelf": shelf} if shelf else None,
            "decision": {"value": decision} if decision else None,
        }

    def test_the_rule(self) -> None:
        rule = export_policy.is_exportable
        self.assertTrue(rule(self._entry("worth")))
        self.assertTrue(rule(self._entry("worth", "learn")))
        self.assertTrue(rule(self._entry("disputed", "learn")))
        for shelf in ("disputed", "not_worth", "junk", "known"):
            self.assertFalse(rule(self._entry(shelf)))
        for decision, shelf in (("known", "known"), ("skip", "not_worth"), ("junk", "junk")):
            self.assertFalse(rule(self._entry(shelf, decision)))
        # A skip is final even if the shelf were stale.
        self.assertFalse(rule(self._entry("worth", "skip")))
        # A «знаю» that lapsed (the word came back) is judged by its shelf again.
        self.assertTrue(rule(self._entry("worth", "known")))
        self.assertFalse(rule(self._entry(None, None, state="pending")))
        self.assertFalse(rule(self._entry("worth", None, state="pending")))


class PerformanceTests(unittest.TestCase):
    def test_decorating_three_thousand_lexemes_is_fast(self) -> None:
        entries = []
        for index in range(3000):
            entry = word(
                f"lumen{index}", days=(index % 30, (index % 7) + 1), zipf=3.0 + (index % 20) / 10,
                warnings=["possibly_glued_words"] if index % 11 == 0 else [],
            )
            entry["dictionary"] = {"meaning_ru": "слово"} if index % 2 else None
            entries.append(entry)
        timings = []
        for _ in range(3):
            started = time.perf_counter()
            library = library_view.decorate(entries, batch_size=20)
            timings.append(time.perf_counter() - started)
        best = min(timings)
        print(f"decorate 3000 lexemes: best of 3 = {best * 1000:.0f} ms")
        self.assertEqual(library["newBatch"]["count"], 20)
        # The local budget is 150 ms; CI machines get three times that.
        self.assertLess(best, 0.45)


def _by_id(library: dict[str, Any], lexeme_id: str) -> dict[str, Any]:
    return next(entry for entry in library["entries"] if entry["id"] == lexeme_id)


if __name__ == "__main__":
    unittest.main()
