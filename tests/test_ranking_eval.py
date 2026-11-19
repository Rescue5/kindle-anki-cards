from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kindle_vocab_app import ranking_eval
from kindle_vocab_app.ranking_eval import Example, Lexical, Library, Lookup

CUTOFF = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW = timedelta(days=42)


def _lexical(word: str, zipf: float = 3.5) -> Lexical:
    return Lexical(
        display_form=word,
        base_form=word,
        lemma_zipf=zipf,
        form_zipf=zipf,
        synset_count=2,
        pos_count=1,
        warnings=frozenset(),
    )


def _example(word: str, needed: bool, lookups: int = 1, zipf: float = 3.5) -> Example:
    return Example(
        lexeme_id=word,
        lexical=_lexical(word, zipf),
        lookups_before=lookups,
        books_before=1,
        days_since_last=10.0,
        days_since_first=20.0,
        needed_again=needed,
    )


def _at(days: float) -> datetime:
    return CUTOFF + timedelta(days=days)


class MetricTests(unittest.TestCase):
    def test_auc_is_one_for_a_perfect_order_and_zero_for_the_reverse(self) -> None:
        labels = [True, True, False, False]
        self.assertEqual(ranking_eval.auc([4, 3, 2, 1], labels), 1.0)
        self.assertEqual(ranking_eval.auc([1, 2, 3, 4], labels), 0.0)

    def test_auc_counts_ties_as_half(self) -> None:
        self.assertEqual(ranking_eval.auc([1, 1, 1, 1], [True, False, True, False]), 0.5)

    def test_auc_is_undefined_with_one_class(self) -> None:
        self.assertTrue(ranking_eval.auc([1, 2], [True, True]) != ranking_eval.auc([1, 2], [True, True]))

    def test_precision_shares_a_tie_at_the_boundary_evenly(self) -> None:
        # The top slot is a tie between a needed and a not-needed word.
        self.assertEqual(ranking_eval.precision_at([1, 1, 0, 0], [True, False, True, False], 1), 0.5)
        self.assertEqual(ranking_eval.precision_at([3, 2, 1], [True, False, True], 2), 0.5)

    def test_precision_never_asks_for_more_than_there_is(self) -> None:
        self.assertEqual(ranking_eval.precision_at([2, 1], [True, True], 100), 1.0)

    def test_bootstrap_interval_contains_the_point_estimate(self) -> None:
        scores = [float(i) for i in range(40)]
        labels = [i % 3 == 0 for i in range(40)]
        low, high = ranking_eval.bootstrap_interval(scores, labels, ranking_eval.auc)
        self.assertLessEqual(low, ranking_eval.auc(scores, labels))
        self.assertGreaterEqual(high, ranking_eval.auc(scores, labels))


class ExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.library = Library(
            lookups=[
                Lookup("a", "book-1", _at(-30)),
                Lookup("a", "book-2", _at(-3)),
                Lookup("a", "book-2", _at(5)),
                Lookup("b", "book-1", _at(-10)),
                Lookup("b", "book-1", _at(60)),
                Lookup("c", "book-1", _at(1)),
            ],
            lexical={"a": _lexical("a"), "b": _lexical("b"), "c": _lexical("c")},
        )

    def test_features_use_only_lookups_before_the_cutoff(self) -> None:
        examples = {item.lexeme_id: item for item in ranking_eval.build_examples(self.library, CUTOFF, WINDOW)}
        self.assertEqual(examples["a"].lookups_before, 2)
        self.assertEqual(examples["a"].books_before, 2)
        self.assertAlmostEqual(examples["a"].days_since_last, 3.0)
        self.assertEqual(examples["b"].lookups_before, 1)

    def test_examples_carry_only_earlier_lookups_and_the_books_being_read(self) -> None:
        examples = {item.lexeme_id: item for item in ranking_eval.build_examples(self.library, CUTOFF, WINDOW)}
        self.assertEqual(examples["a"].history, ((_at(-30), "book-1"), (_at(-3), "book-2")))
        self.assertEqual(examples["b"].history, ((_at(-10), "book-1"),))
        # Both books had a lookup in the 14 days before the cutoff, by any word.
        self.assertEqual(examples["a"].reading_books, frozenset({"book-1", "book-2"}))
        self.assertEqual(examples["a"].cutoff, CUTOFF)

    def test_reading_books_use_only_the_two_weeks_before_the_cutoff(self) -> None:
        library = Library(
            lookups=[
                Lookup("a", "recent", _at(-3)),
                Lookup("a", "edge", CUTOFF - timedelta(days=14)),
                Lookup("a", "stale", CUTOFF - timedelta(days=14, seconds=1)),
                Lookup("a", "future-only", _at(2)),
                Lookup("future-word", "future-only", _at(2)),
            ],
            lexical={"a": _lexical("a"), "future-word": _lexical("future-word")},
        )
        examples = {item.lexeme_id: item for item in ranking_eval.build_examples(library, CUTOFF, WINDOW)}
        self.assertEqual(examples["a"].reading_books, frozenset({"recent", "edge"}))

    def test_ranking_v2_scores_with_the_facts_known_at_the_cutoff(self) -> None:
        examples = {item.lexeme_id: item for item in ranking_eval.build_examples(self.library, CUTOFF, WINDOW)}
        facts = ranking_eval.word_facts(examples["a"])
        self.assertEqual(len(facts.lookups), 2)
        self.assertEqual(facts.reading_books, frozenset({"book-1", "book-2"}))
        self.assertIsNone(facts.decision)
        self.assertGreater(ranking_eval.ranking_v2(examples["a"]), ranking_eval.ranking_v2(examples["b"]))

    def test_ranking_v2_accepts_an_example_built_by_hand(self) -> None:
        once = _example("linger", needed=False, lookups=1)
        often = _example("linger", needed=False, lookups=4)
        self.assertGreater(ranking_eval.ranking_v2(often), ranking_eval.ranking_v2(once))

    def test_a_word_is_needed_again_only_inside_the_window(self) -> None:
        examples = {item.lexeme_id: item for item in ranking_eval.build_examples(self.library, CUTOFF, WINDOW)}
        self.assertTrue(examples["a"].needed_again)
        self.assertFalse(examples["b"].needed_again)

    def test_words_first_seen_after_the_cutoff_are_left_out(self) -> None:
        examples = ranking_eval.build_examples(self.library, CUTOFF, WINDOW)
        self.assertNotIn("c", {item.lexeme_id for item in examples})

    def test_the_current_score_counts_only_earlier_lookups(self) -> None:
        once = _example("linger", needed=False, lookups=1, zipf=3.3)
        often = _example("linger", needed=False, lookups=4, zipf=3.3)
        self.assertGreater(ranking_eval.current_score(often), ranking_eval.current_score(once))

    def test_the_current_score_keeps_the_penalty_for_specialised_words(self) -> None:
        plain = _example("ledger", needed=False, zipf=3.5)
        specialised = Example(**{**plain.__dict__, "lexical": replace(plain.lexical, specialized=True)})
        self.assertLess(ranking_eval.current_score(specialised), ranking_eval.current_score(plain))

    def test_rejected_words_are_left_out_unless_asked_for(self) -> None:
        library = Library(
            lookups=[Lookup("kept", "b", _at(-5)), Lookup("junk", "b", _at(-5))],
            lexical={"kept": _lexical("kept"), "junk": replace(_lexical("junk"), accepted=False)},
        )
        ranked = {item.lexeme_id for item in ranking_eval.build_examples(library, CUTOFF, WINDOW)}
        everything = {
            item.lexeme_id
            for item in ranking_eval.build_examples(library, CUTOFF, WINDOW, include_rejected=True)
        }
        self.assertEqual(ranked, {"kept"})
        self.assertEqual(everything, {"kept", "junk"})

    def test_stored_timestamps_with_and_without_time_are_read(self) -> None:
        self.assertEqual(ranking_eval.parse_timestamp("2026-05-20"), datetime(2026, 5, 20, tzinfo=UTC))
        self.assertEqual(
            ranking_eval.parse_timestamp("2026-10-30T04:57:38+00:00"),
            datetime(2026, 10, 30, 4, 57, 38, tzinfo=UTC),
        )
        self.assertIsNone(ranking_eval.parse_timestamp("not a date"))


class LearnedRankerTests(unittest.TestCase):
    def _examples(self) -> list[Example]:
        # Words looked up repeatedly come back; single lookups do not.
        return [_example(f"w{i}", needed=i % 2 == 0, lookups=3 if i % 2 == 0 else 1) for i in range(60)]

    def test_the_model_learns_a_clear_signal(self) -> None:
        examples = self._examples()
        model = ranking_eval.LogisticModel.fit(examples)
        scores = [model.score(example) for example in examples]
        self.assertGreater(ranking_eval.auc(scores, [example.needed_again for example in examples]), 0.9)

    def test_training_is_deterministic(self) -> None:
        first = ranking_eval.LogisticModel.fit(self._examples())
        second = ranking_eval.LogisticModel.fit(self._examples())
        self.assertEqual(first.weights, second.weights)
        self.assertEqual(first.bias, second.bias)

    def _history(self) -> Library:
        """Three months of lookups: every third word comes back three weeks later."""
        lookups, lexical = [], {}
        start = CUTOFF - timedelta(days=100)
        for i in range(300):
            word = f"w{i}"
            lexical[word] = _lexical(word, 3.0 + (i % 7) / 5)
            first = start + timedelta(days=i % 95)
            lookups.append(Lookup(word, "book", first))
            if i % 3 == 0:
                lookups.append(Lookup(word, "book", first + timedelta(days=21)))
        return Library(lookups=lookups, lexical=lexical)

    def test_the_learned_ranker_never_sees_the_cutoff_or_later(self) -> None:
        library = self._history()
        later = Library(
            lookups=library.lookups + [Lookup(f"w{i}", "book", _at(i % 60)) for i in range(0, 300, 2)],
            lexical=library.lexical,
        )
        before = ranking_eval.evaluate(library, [CUTOFF], WINDOW, (10,))["rounds"][0]
        after = ranking_eval.evaluate(later, [CUTOFF], WINDOW, (10,))["rounds"][0]
        self.assertIsNotNone(before["learned_weights"])
        self.assertEqual(before["learned_weights"], after["learned_weights"])


class SyntheticReaderTests(unittest.TestCase):
    """A synthetic reader unlike the author. The default weights were derived from the author's
    own cutoffs, so this is only a sanity check that the signal also separates a made-up history
    built to contain it; it is not evidence that the ranking generalises to other readers."""

    def _library(self) -> Library:
        lookups, lexical = [], {}
        start = CUTOFF - timedelta(days=120)
        for i in range(400):
            word = f"s{i}"
            # Frequencies cycle over the whole band, unrelated to what comes back.
            lexical[word] = _lexical(word, 2.0 + (i * 7 % 40) / 10)
            day = i % 115
            book = f"book-{day // 10}"
            lookups.append(Lookup(word, book, start + timedelta(days=day)))
            # Every fifth word did not stick: looked up again in the next book, and again later.
            if i % 5 == 0:
                lookups.append(Lookup(word, f"book-{day // 10 + 1}", start + timedelta(days=day + 9)))
                lookups.append(Lookup(word, "book-late", start + timedelta(days=day + 30)))
        return Library(lookups=lookups, lexical=lexical)

    def test_ranking_v2_separates_a_synthetic_history_with_a_planted_signal(self) -> None:
        report = ranking_eval.evaluate(self._library(), [CUTOFF - timedelta(days=30)], WINDOW, (20,))
        results = report["rounds"][0]["results"]
        self.assertGreater(results["ranking_v2"]["auc"], results["current_score"]["auc"] + 0.1)
        self.assertGreater(results["ranking_v2"]["precision"]["20"], results["current_score"]["precision"]["20"])


class SummaryTests(unittest.TestCase):
    def _round(self, base_rate: float, names: dict[str, float]) -> dict:
        return {
            "base_rate": base_rate,
            "results": {name: {"auc": value, "precision": {"10": value / 2}} for name, value in names.items()},
        }

    def test_rankers_are_compared_only_on_rounds_where_all_of_them_ran(self) -> None:
        rounds = [
            self._round(0.1, {"frequency": 0.9}),
            self._round(0.2, {"frequency": 0.5, "learned": 0.7}),
        ]
        summary = ranking_eval._summary(rounds, (10,))
        self.assertEqual(summary["frequency"]["rounds"], 1)
        self.assertEqual(summary["frequency"]["auc"], 0.5)
        self.assertEqual(summary["learned"]["auc"], 0.7)

    def test_lift_is_precision_over_the_base_rate(self) -> None:
        summary = ranking_eval._summary([self._round(0.2, {"frequency": 0.6})], (10,))
        self.assertAlmostEqual(summary["frequency"]["lift"]["10"], 1.5)

    def test_undefined_metrics_are_written_as_null(self) -> None:
        self.assertEqual(ranking_eval._json_safe({"auc": float("nan"), "ci": [float("nan"), 0.5]}), {
            "auc": None,
            "ci": [None, 0.5],
        })


class DatabaseTests(unittest.TestCase):
    def _database(self, folder: Path) -> Path:
        path = folder / "library.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE lexemes (id TEXT PRIMARY KEY, display_form TEXT);
                CREATE TABLE occurrences (lexeme_id TEXT, book_key TEXT, looked_up_at TEXT);
                CREATE TABLE analyses (lexeme_id TEXT, state TEXT, payload_json TEXT);
                """
            )
            start = datetime(2026, 5, 3, tzinfo=UTC)
            for i in range(120):
                word = f"word{i}"
                connection.execute("INSERT INTO lexemes VALUES (?, ?)", (word, word))
                payload = {"base_form": word, "lemma_zipf": 3.0 + (i % 10) / 10, "form_zipf": 3.0}
                connection.execute("INSERT INTO analyses VALUES (?, 'ready', ?)", (word, json.dumps(payload)))
                first = start + timedelta(days=i % 90)
                connection.execute("INSERT INTO occurrences VALUES (?, 'book', ?)", (word, first.date().isoformat()))
                if i % 3 == 0:
                    again = first + timedelta(days=20)
                    connection.execute("INSERT INTO occurrences VALUES (?, 'book', ?)", (word, again.isoformat()))
        return path

    def test_a_small_library_is_evaluated_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            library = ranking_eval.load_library(self._database(Path(folder)))
            horizon = timedelta(days=21)
            cutoffs = ranking_eval.default_cutoffs(library, horizon)
            self.assertTrue(cutoffs)
            for cutoff in cutoffs:
                self.assertLessEqual(cutoff + horizon, library.last_lookup)
            report = ranking_eval.evaluate(library, cutoffs, horizon, (10,))
        self.assertTrue(report["rounds"])
        self.assertIn("current_score", report["summary"])
        self.assertIn("frequency", report["summary"])
        text = ranking_eval.format_report(report)
        self.assertIn("AUC", text)
        self.assertNotIn("word1", text)

    def test_the_command_reports_a_missing_library(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(ranking_eval.main(["--db", str(Path(folder) / "missing.sqlite3")]), 2)


if __name__ == "__main__":
    unittest.main()
