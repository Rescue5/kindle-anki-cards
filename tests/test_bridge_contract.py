"""The C0 bridge contract: `contracts.py`, `src/types.ts` and the shared fixtures must agree."""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import get_args

from kindle_vocab_app import contracts
from kindle_vocab_app.ranking import (
    DECISIONS,
    RANKING_MODES,
    RANKING_VERSION,
    REASON_CODES,
    SHELVES,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FixtureContractTests(unittest.TestCase):
    def test_both_fixtures_are_valid(self):
        for name in ("bridge_library_v4.json", "bridge_library_v4_learning.json"):
            with self.subTest(name):
                self.assertEqual(contracts.validate_library(_load(name)), [])

    def test_full_fixture_covers_the_cases_the_ui_needs(self):
        library = _load("bridge_library_v4.json")
        entries = library["entries"]
        self.assertEqual({e["ranking"]["shelf"] for e in entries if e["ranking"]}, set(SHELVES))
        self.assertTrue(any(e["decision"] for e in entries))
        self.assertTrue(any(e["card"]["edited"] and e["card"]["meaning_source"] == "edited" for e in entries))
        self.assertTrue(any(e["export"]["state"] == "exported" and e["export"]["again"] for e in entries))
        self.assertTrue(any(e["ranking"] is None for e in entries))
        self.assertTrue(any(e["ranking"] and e["ranking"]["lean"] for e in entries))
        self.assertEqual(library["rankingMode"], "full")
        self.assertLessEqual(len(library["disputed"]["ids"]), contracts.DISPUTED_CAP)

    def test_learning_fixture_has_no_repeat_signal(self):
        library = _load("bridge_library_v4_learning.json")
        self.assertEqual(library["rankingMode"], "learning")
        self.assertFalse(library["repeatSignal"])
        self.assertTrue(library["again"]["unavailable"])

    def test_fixtures_hold_no_private_data(self):
        text = "".join((FIXTURES / n).read_text(encoding="utf-8") for n in ("bridge_library_v4.json", "bridge_library_v4_learning.json"))
        self.assertNotIn("C:\\", text)
        self.assertNotIn("@", text)


class ValidatorCatchesTests(unittest.TestCase):
    def setUp(self):
        self.library = _load("bridge_library_v4.json")

    def _entry(self, lexeme_id: str) -> dict:
        return next(e for e in self.library["entries"] if e["id"] == lexeme_id)

    def assertProblem(self, fragment: str):
        problems = contracts.validate_library(self.library)
        self.assertTrue(any(fragment in p for p in problems), f"{fragment!r} not in {problems}")

    def test_missing_library_key(self):
        del self.library["rankingMode"]
        self.assertProblem("missing rankingMode")

    def test_rank_must_be_one_based_and_contiguous(self):
        self._entry("w1")["ranking"]["rank"] = 0
        self.assertProblem("ranks in shelf worth")

    def test_study_priority_is_required_and_well_formed(self):
        del self._entry("w1")["study_priority"]
        self._entry("w2")["study_priority"].update(level=11, score=float("nan"), reason=" ")
        self._entry("w3")["study_priority"].update(level=5, score=0.15, provisional=True)
        for fragment in ("missing study_priority", "integer in 1..10", "score: not in 0..1", "reason: empty",
                         "provisional priority must have level 6 and score 0"):
            self.assertProblem(fragment)

    def test_more_than_five_disputed(self):
        self.library["disputed"]["ids"] = ["w5", "w6", "w1", "w2", "w3", "w4"]
        self.assertProblem("more than 5")

    def test_disputed_words_are_not_in_the_short_list(self):
        self.library["newBatch"] = {"count": 4, "ids": ["w1", "w2", "w3", "w5"]}
        self.assertProblem("is not on the worth shelf")
        self.assertProblem("must not be in newBatch.ids")

    def test_short_list_is_in_rank_order_and_not_exported(self):
        self.library["newBatch"] = {"count": 2, "ids": ["w2", "w1"]}
        self.assertProblem("not in rank order")
        self.library["newBatch"] = {"count": 1, "ids": ["w4"]}
        self.assertProblem("already exported")

    def test_disputed_must_be_on_the_disputed_shelf_and_unexported(self):
        self.library["disputed"]["ids"] = ["w1"]
        self.assertProblem("w1 is not on the disputed shelf")

    def test_lean_only_on_disputed(self):
        self._entry("w1")["ranking"]["lean"] = "learn"
        self.assertProblem("exactly on the disputed shelf")

    def test_unknown_reason_code_and_literals(self):
        self._entry("w1")["ranking"]["reasons"][0]["code"] = "invented"
        self._entry("w2")["card"]["meaning_source"] = "guess"
        self._entry("w3")["decision"]["value"] = "maybe"
        for fragment in ("invented", "guess", "maybe"):
            self.assertProblem(fragment)

    def test_not_worth_needs_a_reason_against_it(self):
        self._entry("w7")["ranking"]["reasons"][0]["weight"] = 0.2
        self.assertProblem("reason against it")

    def test_again_needs_a_repeat_signal(self):
        learning = _load("bridge_library_v4_learning.json")
        learning["entries"][1]["export"].update(again=True, lookups_after=1)
        problems = contracts.validate_library(learning)
        self.assertTrue(any("again without a repeat signal" in p for p in problems), problems)

    def test_exported_flag_and_timestamp_agree(self):
        self._entry("w4")["export"]["last_exported_at"] = ""
        self.assertProblem("last_exported_at set exactly when exported")

    def test_processed_word_needs_a_ranking(self):
        self._entry("w1")["ranking"] = None
        self.assertProblem("processed word without a ranking")

    def test_meaning_length_and_example_belong_to_the_word(self):
        self._entry("w2")["card"]["meaning_ru"] = "я" * (contracts.MEANING_MAX_LENGTH + 1)
        self._entry("w1")["card"]["example_occurrence_id"] = "w2-o1"
        self.assertProblem("longer than 200")
        self.assertProblem("not an occurrence of the word")

    def test_validator_does_not_mutate(self):
        before = copy.deepcopy(self.library)
        contracts.validate_library(self.library)
        self.assertEqual(before, self.library)


class ConstantsTests(unittest.TestCase):
    def test_literals_match_ranking(self):
        self.assertEqual(get_args(contracts.Shelf), SHELVES)
        self.assertEqual(get_args(contracts.RankingMode), RANKING_MODES)
        self.assertEqual(set(get_args(contracts.DecisionValue)), set(DECISIONS))
        self.assertEqual(contracts.RANKING_VERSION, RANKING_VERSION)
        self.assertTrue(set(contracts.ShelfCounts.__annotations__) == set(SHELVES))

    def test_error_codes_have_russian_texts(self):
        self.assertEqual(set(contracts.ERROR_TEXTS), set(contracts.ERROR_CODES))
        self.assertEqual(set(get_args(contracts.ErrorCode)), set(contracts.ERROR_CODES))
        for text in contracts.ERROR_TEXTS.values():
            self.assertRegex(text, "[А-Яа-я]")

    def test_error_response_shape(self):
        self.assertEqual(
            contracts.error_response("too_long"),
            {"ok": False, "error": contracts.ERROR_TEXTS["too_long"], "code": "too_long"},
        )
        self.assertTrue(contracts.error_response("export_failed", "диск полон")["error"].endswith(": диск полон"))
        with self.assertRaises(ValueError):
            contracts.error_response("nope")  # type: ignore[arg-type]

    def test_batch_size_bounds(self):
        self.assertEqual((contracts.BATCH_SIZE_MIN, contracts.BATCH_SIZE_DEFAULT, contracts.BATCH_SIZE_MAX), (5, 20, 100))
        self.assertEqual(contracts.EXPORT_DESTINATIONS, ("anki", "csv", "obsidian"))
        self.assertIn(contracts.EXPORT_DESTINATION_DEFAULT, contracts.EXPORT_DESTINATIONS)


class TypesTsInSyncTests(unittest.TestCase):
    """`src/types.ts` repeats the literals and constants; a drift fails here, not in the UI."""

    @classmethod
    def setUpClass(cls):
        cls.ts = (ROOT / "src" / "types.ts").read_text(encoding="utf-8")

    def _union(self, name: str) -> set[str]:
        match = re.search(rf"export type {name} =([^;]+);", self.ts)
        self.assertIsNotNone(match, name)
        return set(re.findall(r'"([a-z_]+)"', match.group(1)))

    def test_unions(self):
        self.assertEqual(self._union("ReasonCode"), set(REASON_CODES))
        self.assertEqual(self._union("Shelf"), set(SHELVES))
        self.assertEqual(self._union("DecisionValue"), set(DECISIONS))
        self.assertEqual(self._union("RankingMode"), set(RANKING_MODES))
        self.assertEqual(self._union("ErrorCode"), set(contracts.ERROR_CODES))
        self.assertEqual(self._union("ExportDestination"), set(contracts.EXPORT_DESTINATIONS))

    def test_constants_and_texts(self):
        self.assertIn(f"DISPUTED_CAP = {contracts.DISPUTED_CAP};", self.ts)
        self.assertIn(f"MEANING_MAX_LENGTH = {contracts.MEANING_MAX_LENGTH};", self.ts)
        self.assertIn(f"EXPORT_BATCH_SIZE_MAX = {contracts.BATCH_SIZE_MAX};", self.ts)
        for code, text in contracts.ERROR_TEXTS.items():
            if "{" in text:
                continue
            self.assertIn(f'{code}: "{text}"', self.ts)


if __name__ == "__main__":
    unittest.main()
