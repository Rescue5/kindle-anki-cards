from __future__ import annotations

import itertools
import json
import math
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

    def test_personal_bonus_uses_only_eligible_history_before_the_cutoff(self) -> None:
        library = Library(
            lookups=[
                Lookup("a", "first", _at(-4)),
                Lookup("a", "other-source", _at(-2), personal_evidence=False),
                Lookup("a", "future", CUTOFF),
            ],
            lexical={"a": _lexical("a")},
        )
        [example] = ranking_eval.build_examples(library, CUTOFF, WINDOW)
        self.assertTrue(example.needed_again)
        self.assertEqual(example.personal_history, ((_at(-4), "first"),))

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


class NewcomerToolsTests(unittest.TestCase):
    def _library(self) -> Library:
        start = CUTOFF - timedelta(days=100)
        lookups, lexical = [], {}
        for i in range(60):
            word = f"w{i}"
            lexical[word] = _lexical(word)
            lookups.append(Lookup(word, "book-a" if i < 40 else "book-b", start + timedelta(days=i)))
            if i % 4 == 0:
                lookups.append(Lookup(word, "book-a", start + timedelta(days=i + 10)))
        return Library(lookups=lookups, lexical=lexical)

    def test_restricting_keeps_the_first_books_and_the_first_days(self) -> None:
        library = self._library()
        first = ranking_eval.restrict_library(library, first_books=1)
        self.assertEqual({item.book_key for item in first.lookups}, {"book-a"})
        named = ranking_eval.restrict_library(library, only_books={"book-b"})
        self.assertEqual({item.book_key for item in named.lookups}, {"book-b"})
        early = ranking_eval.restrict_library(library, first_days=20)
        self.assertTrue(all(item.at < library.first_lookup + timedelta(days=20) for item in early.lookups))
        self.assertEqual(ranking_eval.restrict_library(Library([], {}), first_days=5).lookups, [])

    def test_step_cutoffs_leave_a_full_window_after_each(self) -> None:
        library = self._library()
        window = timedelta(days=14)
        cutoffs = ranking_eval.step_cutoffs(library, window, step_days=7, start_days=21)
        self.assertEqual(cutoffs[0], library.first_lookup + timedelta(days=21))
        self.assertTrue(all(b - a == timedelta(days=7) for a, b in itertools.pairwise(cutoffs)))
        self.assertTrue(all(cutoff + window <= library.last_lookup for cutoff in cutoffs))
        self.assertEqual(ranking_eval.step_cutoffs(Library([], {}), window, 7, 0), [])

    def test_a_newcomer_report_never_looks_at_what_was_cut_away(self) -> None:
        report = ranking_eval.newcomer_report(self._library(), timedelta(days=14), (10,), first_books=1, start_days=21)
        self.assertEqual(report["books"], 1)
        self.assertGreater(report["cutoffs"], 0)
        self.assertEqual(ranking_eval.newcomer_report(Library([], {}), timedelta(days=14), (10,))["cutoffs"], 0)

    def test_paired_differences_use_the_same_words(self) -> None:
        labels = [True, True, False, False, False, False]
        groups = [ranking_eval.Group({"good": [6, 5, 4, 3, 2, 1], "same": [6, 5, 4, 3, 2, 1]}, labels)] * 2
        delta = ranking_eval.compare_to(groups, "good", "same", (2,))
        self.assertEqual(delta["auc"], {"value": 0.0, "low": 0.0, "high": 0.0})
        self.assertEqual(delta["lift"]["2"]["low"], 0.0)
        levels = ranking_eval.compare_rankers(groups, ["good"], (2,))
        self.assertEqual(levels["good"]["auc"]["value"], 1.0)
        self.assertAlmostEqual(levels["good"]["lift"]["2"]["value"], 3.0)  # precision 1.0 over a third

    def test_lift_is_undefined_when_nobody_comes_back(self) -> None:
        self.assertTrue(math.isnan(ranking_eval.lift_at([1, 2], [False, False], 1)))

    def test_too_basic_words_are_counted_against_the_base_rate(self) -> None:
        start = CUTOFF - timedelta(days=10)
        lookups, lexical = [], {}
        for i in range(30):
            word = f"basic{i}"
            lexical[word] = replace(_lexical(word, 6.3), warnings=frozenset({"too_basic"}), accepted=False)
            lookups.append(Lookup(word, "b", start + timedelta(days=i % 8)))
            if i < 3:
                lookups.append(Lookup(word, "b", CUTOFF + timedelta(days=3)))
        for i in range(30):
            word = f"plain{i}"
            lexical[word] = _lexical(word)
            lookups.append(Lookup(word, "b", start + timedelta(days=i % 8)))
            if i < 15:
                lookups.append(Lookup(word, "b", CUTOFF + timedelta(days=3)))
        result = ranking_eval.too_basic_recall(Library(lookups, lexical), [CUTOFF], WINDOW)
        self.assertEqual((result["flagged"], result["flagged_back"]), (30, 3))
        self.assertEqual(result["not_worth"], 30)  # very common words are not worth learning
        self.assertEqual(result["not_worth_back"], 3)
        self.assertEqual((result["other_words"], result["other_back"]), (30, 15))
        self.assertAlmostEqual(result["not_worth_rate"]["value"], 0.1)
        self.assertLess(result["not_worth_rate"]["high"], result["other_rate"]["value"])
        self.assertEqual(sum(result["flagged_shelves"].values()), 30)

    def test_wilson_interval_surrounds_the_share_and_survives_an_empty_sample(self) -> None:
        rate = ranking_eval._rate(5, 50)
        self.assertTrue(rate["low"] < rate["value"] < rate["high"])
        self.assertTrue(math.isnan(ranking_eval._rate(0, 0)["value"]))


class ExportsAndNamesTests(unittest.TestCase):
    """The library's destination rows give export times; capitalised unknown words are proper nouns."""

    def _database(self, folder: Path) -> Path:
        path = folder / "library.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE lexemes (id TEXT PRIMARY KEY, display_form TEXT);
                CREATE TABLE occurrences (lexeme_id TEXT, book_key TEXT, looked_up_at TEXT, word TEXT, context TEXT);
                CREATE TABLE analyses (lexeme_id TEXT, state TEXT, payload_json TEXT);
                CREATE TABLE destinations (
                    lexeme_id TEXT, destination TEXT, state TEXT, last_exported_at TEXT, last_synced_at TEXT);
                """
            )
            for word, raw, context in (("tolmar", "Tolmar", "He met Tolmar there."), ("plain", "plain", "A plain day.")):
                connection.execute("INSERT INTO lexemes VALUES (?, ?)", (word, raw))
                payload = {
                    "base_form": word,
                    "lemma_zipf": 0.0 if word == "tolmar" else 3.5,
                    "wordnet_synset_count": 0 if word == "tolmar" else 2,
                }
                connection.execute("INSERT INTO analyses VALUES (?, 'ready', ?)", (word, json.dumps(payload)))
                connection.execute("INSERT INTO occurrences VALUES (?, 'b', '2026-06-01', ?, ?)", (word, raw, context))
                connection.execute("INSERT INTO occurrences VALUES (?, 'b', '2026-06-20', ?, ?)", (word, raw, context))
            connection.execute(
                "INSERT INTO destinations VALUES ('plain', 'obsidian', 'synced', '', '2026-06-10T08:00:00+00:00')"
            )
            connection.execute("INSERT INTO destinations VALUES ('tolmar', 'anki', 'not_exported', '', '')")
        return path

    def _examples(self, cutoff: datetime, include_rejected: bool = False) -> dict[str, Example]:
        with tempfile.TemporaryDirectory() as folder:
            library = ranking_eval.load_library(self._database(Path(folder)))
        self.assertIsNone(library.lexical["tolmar"].exported_at)
        built = ranking_eval.build_examples(library, cutoff, WINDOW, include_rejected)
        return {example.lexeme_id: example for example in built}

    def test_export_times_come_from_destination_rows_and_stay_before_the_cutoff(self) -> None:
        after = self._examples(datetime(2026, 7, 1, tzinfo=UTC))
        self.assertEqual(after["plain"].exported_at, datetime(2026, 6, 10, 8, tzinfo=UTC))
        self.assertIsNone(after["tolmar"].exported_at)
        # At a cutoff before the export the word had not been exported yet.
        before = self._examples(datetime(2026, 6, 5, tzinfo=UTC))
        self.assertTrue(all(example.exported_at is None for example in before.values()))

    def test_exports_only_reach_the_ranking_when_asked_for(self) -> None:
        example = self._examples(datetime(2026, 7, 1, tzinfo=UTC))["plain"]
        self.assertIsNone(ranking_eval.word_facts(example).exported_at)
        self.assertEqual(ranking_eval.word_facts(example, exports=True).exported_at, example.exported_at)
        plain, exported = ranking_eval.v2_variant(), ranking_eval.v2_variant(exports=True)
        self.assertGreater(exported(example), plain(example))  # looked up again after the export on June 10

    def test_proper_nouns_need_every_lookup_to_look_like_a_name(self) -> None:
        examples = self._examples(datetime(2026, 7, 1, tzinfo=UTC), include_rejected=True)
        self.assertTrue(examples["tolmar"].proper_noun)
        self.assertFalse(examples["plain"].proper_noun)
        self.assertTrue(ranking_eval.word_facts(examples["tolmar"], proper_nouns=True).proper_noun)
        self.assertFalse(ranking_eval.word_facts(examples["tolmar"]).proper_noun)

    def test_a_library_without_destination_rows_or_contexts_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old.sqlite3"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.executescript(
                    """
                    CREATE TABLE lexemes (id TEXT PRIMARY KEY, display_form TEXT);
                    CREATE TABLE occurrences (lexeme_id TEXT, book_key TEXT, looked_up_at TEXT);
                    CREATE TABLE analyses (lexeme_id TEXT, state TEXT, payload_json TEXT);
                    INSERT INTO lexemes VALUES ('a', 'a');
                    INSERT INTO occurrences VALUES ('a', 'b', '2026-06-01');
                    """
                )
            library = ranking_eval.load_library(path)
        self.assertEqual(len(library.lookups), 1)
        self.assertIsNone(library.lexical["a"].exported_at)
        self.assertFalse(library.lookups[0].proper)

    def test_the_ablation_compares_each_variant_with_the_ranking_without_it(self) -> None:
        start = CUTOFF - timedelta(days=100)
        lookups, lexical = [], {}
        for i in range(120):
            word = f"a{i}"
            lexical[word] = replace(_lexical(word), exported_at=start + timedelta(days=30) if i % 2 else None)
            lookups.append(Lookup(word, "b", start + timedelta(days=i % 70)))
            if i % 3 == 0:
                lookups.append(Lookup(word, "b", start + timedelta(days=i % 70 + 40)))
        library = Library(lookups, lexical)
        cutoffs = [CUTOFF - timedelta(days=45), CUTOFF - timedelta(days=30)]
        report = ranking_eval.ablation_report(library, cutoffs, timedelta(days=21), (10,))
        self.assertGreater(report["cutoffs"], 0)
        self.assertGreater(report["inputs_present"]["exported"], 0)
        self.assertEqual(report["inputs_present"]["proper_noun"], 0)
        self.assertNotIn("off", report["versus_off"])
        # No proper nouns present: switching them on cannot change anything.
        self.assertEqual(report["versus_off"]["proper"]["auc"]["value"], 0.0)
        self.assertIn("exports_w2", report["versus_off"])


if __name__ == "__main__":
    unittest.main()
