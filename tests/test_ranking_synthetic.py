"""The synthetic newcomer library: it imports as a KOReader and a Kobo file, and ranking v2 holds on it.

The library is invented (pseudo-words with a planted "needed again" process), so these tests say that the
evaluation path and the shelves work for a newcomer-shaped history and do not collapse; the evidence that the
ranking generalises to a real reader is the replay on a real library, reported in the WORKLOG.
"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from kindle_vocab_app import ranking_eval, ranking_synthetic
from kindle_vocab_app.reader_sources import KOBO, KOREADER, detect_format, fetch_entries

HORIZON = timedelta(days=21)


def _close_app_logging() -> None:
    logger = logging.getLogger("kindle_vocab_app")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


class GeneratorTests(unittest.TestCase):
    def test_the_same_seed_gives_the_same_library(self) -> None:
        first = ranking_synthetic.generate()
        again = ranking_synthetic.generate()
        self.assertEqual(first.lookups, again.lookups)
        self.assertNotEqual(first.lookups, ranking_synthetic.generate(seed=1).lookups)

    def test_it_looks_like_a_newcomer(self) -> None:
        library = ranking_synthetic.generate()
        self.assertTrue(300 <= len(library.lookups) <= 800)
        self.assertEqual({item.book for item in library.lookups}, {0, 1})
        days = (max(item.at for item in library.lookups) - min(item.at for item in library.lookups)).days
        self.assertTrue(60 <= days <= 95)
        counts: dict[str, int] = {}
        for item in library.lookups:
            counts[item.word] = counts.get(item.word, 0) + 1
        repeated = sum(1 for count in counts.values() if count > 1)
        # Most words are looked up once, a real share comes back, some across both books.
        self.assertTrue(0.1 < repeated / len(counts) < 0.45)
        both = {word for word in counts if len({item.book for item in library.lookups if item.word == word}) == 2}
        self.assertGreater(len(both), 5)

    def test_the_words_are_invented_or_common_never_a_reader_vocabulary(self) -> None:
        library = ranking_synthetic.generate()
        common = {word for word, _ in ranking_synthetic.COMMON_WORDS}
        names = set(ranking_synthetic.NAMES) | set(ranking_synthetic.GLUED)
        for lexeme_id, lexical in library.lexical.items():
            self.assertEqual(lexeme_id, lexical.display_form.casefold())
            if lexical.display_form not in common | names:
                self.assertTrue(lexical.display_form.isalpha() and lexical.display_form.islower())
        # Names and glued words are the rejected junk of the library.
        self.assertEqual(sum(1 for lexical in library.lexical.values() if not lexical.accepted), len(names))


class ReaderFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)
        self.library = ranking_synthetic.generate()

    def test_the_koreader_file_imports(self) -> None:
        path = self.folder / "vocabulary_builder.sqlite3"
        ranking_synthetic.write_koreader(self.library, path)
        self.assertEqual(detect_format(path), KOREADER)
        entries = fetch_entries(path)
        self.assertEqual(len(entries), len(self.library.lookups))
        self.assertTrue(all(entry["book_key"].startswith("koreader:Synthetic Book") for entry in entries))
        self.assertTrue(all(entry["looked_up_at"] and entry["context"] for entry in entries))
        self.assertEqual({str(entry["word"]).casefold() for entry in entries}, set(self.library.lexical))

    def test_the_kobo_file_imports(self) -> None:
        path = self.folder / "KoboReader.sqlite"
        ranking_synthetic.write_kobo(self.library, path)
        self.assertEqual(detect_format(path), KOBO)
        entries = fetch_entries(path)
        self.assertEqual(len(entries), len(self.library.lookups))
        self.assertTrue(all(entry["book_key"].startswith("kobo:synthetic-volume-") for entry in entries))
        self.assertTrue(all(entry["looked_up_at"] for entry in entries))
        self.assertEqual({entry["book_title"] for entry in entries}, set(ranking_synthetic.BOOKS))
        self.assertEqual({entry["language"] for entry in entries}, {"en"})

    def test_both_files_carry_the_same_lookups(self) -> None:
        koreader, kobo = self.folder / "k.sqlite3", self.folder / "o.sqlite"
        ranking_synthetic.write_koreader(self.library, koreader)
        ranking_synthetic.write_kobo(self.library, kobo)
        first = sorted((str(e["word"]), str(e["looked_up_at"])[:16]) for e in fetch_entries(koreader))
        second = sorted((str(e["word"]), str(e["looked_up_at"])[:16]) for e in fetch_entries(kobo))
        self.assertEqual(first, second)

    def test_files_that_keep_one_row_per_word_have_no_repeats_to_learn_from(self) -> None:
        path = self.folder / "once.sqlite3"
        ranking_synthetic.write_koreader(self.library, path, repeats=False)
        entries = fetch_entries(path)
        self.assertEqual(len(entries), len(self.library.lexical))
        # Nothing comes back, so there is nothing to evaluate against: the command says so instead of guessing.
        library = ranking_eval.load_reader_library(path, self.library.lexical)
        report = ranking_eval.newcomer_report(library, HORIZON, (20,), start_days=21)
        self.assertEqual(report["cutoffs"], 0)

    def test_the_evaluation_command_reads_a_reader_file(self) -> None:
        path = self.folder / "vocabulary_builder.sqlite3"
        ranking_synthetic.write_koreader(self.library, path)
        out = self.folder / "report"
        # main() attaches a file log under `out`; close it before the folder is removed (Windows file locks).
        self.addCleanup(_close_app_logging)
        # Real WordNet and frequency facts (the words are invented): the command must still run end to end.
        code = ranking_eval.main(
            ["--reader-file", str(path), "--newcomer", "--horizon", "21", "--top", "20", "--out", str(out)]
        )
        self.assertEqual(code, 0)
        saved = json.loads(next(out.glob("extras-*.json")).read_text(encoding="utf-8"))
        self.assertIn("ranking_v2", saved["newcomer"]["levels"])
        self.assertNotIn("Synthetic", json.dumps(saved))


class NewcomerRankingTests(unittest.TestCase):
    """Ranking v2 on the synthetic KOReader library: it does not collapse and the shelves are usable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._folder = tempfile.TemporaryDirectory()
        library = ranking_synthetic.generate()
        path = Path(cls._folder.name) / "vocabulary_builder.sqlite3"
        ranking_synthetic.write_koreader(library, path)
        cls.library = ranking_eval.load_reader_library(path, library.lexical)
        cls.report = ranking_eval.newcomer_report(cls.library, HORIZON, (20, 50), step_days=7, start_days=21)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._folder.cleanup()

    def test_there_are_cutoffs_with_enough_words_needed_again(self) -> None:
        self.assertGreaterEqual(self.report["cutoffs"], 5)
        self.assertEqual(self.report["books"], 2)

    def test_ranking_v2_puts_needed_words_on_top_well_above_chance(self) -> None:
        v2 = self.report["levels"]["ranking_v2"]
        self.assertGreater(v2["lift"]["50"]["value"], 1.5)
        # The whole interval, not only the mean, stays above chance at the top and overall.
        self.assertGreater(v2["lift"]["50"]["low"], 1.0)
        self.assertGreater(v2["auc"]["low"], 0.55)

    def test_it_beats_the_current_importance_score(self) -> None:
        delta = self.report["v2_minus_current"]
        self.assertGreater(delta["auc"]["low"], 0.0)
        self.assertGreater(delta["lift"]["50"]["low"], 0.0)

    def test_the_shelves_are_not_degenerate_at_the_first_sync(self) -> None:
        shelves = self.report["shelves"]
        words = shelves["words"]
        self.assertEqual(sum(shelves["shelves"].values()), words)
        for name in ("worth", "disputed", "not_worth"):
            self.assertGreaterEqual(shelves["shelves"][name], 0.05 * words, name)
        self.assertLessEqual(shelves["shelves"]["worth"], 0.6 * words)
        self.assertLessEqual(shelves["disputed_share"], 0.25)

    def test_features_use_only_lookups_before_each_cutoff(self) -> None:
        cutoff = self.library.first_lookup + timedelta(days=30)
        for example in ranking_eval.build_examples(self.library, cutoff, HORIZON):
            self.assertTrue(all(when < cutoff for when, _ in example.history))


class LearningModeTests(unittest.TestCase):
    """Learning mode on a source without repeat lookups: not worse than frequency or a plain lookup count.

    The "came back" label does not exist in such a source. The proxy: the rankers see only the first lookup of
    each word (the file written with `repeats=False`), the label comes from the same library with its repeats.
    Weak evidence: the planted process makes recent words the ones that come back, which learning mode leans on.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._folder = tempfile.TemporaryDirectory()
        folder = Path(cls._folder.name)
        library = ranking_synthetic.generate()
        ranking_synthetic.write_koreader(library, folder / "full.sqlite3")
        ranking_synthetic.write_koreader(library, folder / "once.sqlite3", repeats=False)
        cls.full = ranking_eval.load_reader_library(folder / "full.sqlite3", library.lexical)
        cls.once = ranking_eval.load_reader_library(folder / "once.sqlite3", library.lexical)
        cls.report = ranking_eval.blind_report(cls.once, cls.full, HORIZON, (20, 50), start_days=14)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._folder.cleanup()

    def test_the_collapsed_library_is_the_repeats_false_file(self) -> None:
        collapsed = ranking_eval.collapse_repeats(self.full)
        self.assertEqual(
            sorted((item.lexeme_id, item.at) for item in collapsed.lookups),
            sorted((item.lexeme_id, item.at) for item in self.once.lookups),
        )

    def test_learning_is_not_worse_than_frequency_or_the_lookup_count_at_the_top(self) -> None:
        self.assertGreaterEqual(self.report["cutoffs"], 5)
        for other in ("frequency", "lookups", "current_score"):
            delta = self.report["learning_minus"][other]
            with self.subTest(other=other):
                self.assertGreater(delta["auc"]["low"], 0.0)
                self.assertGreater(delta["lift"]["50"]["low"], 0.0)
                self.assertGreater(delta["lift"]["20"]["value"], 0.0)

    def test_without_repeats_full_mode_adds_nothing(self) -> None:
        # Nothing was looked up twice, so the two modes order the words alike (that is why learning is safe).
        delta = self.report["learning_minus"]["ranking_v2"]
        self.assertEqual(delta["auc"]["value"], 0.0)

    def test_labels_come_from_the_outcome_and_features_from_before_the_cutoff(self) -> None:
        cutoff = self.once.first_lookup + timedelta(days=50)
        with_outcome = ranking_eval.build_examples(self.once, cutoff, HORIZON, outcome=self.full)
        alone = ranking_eval.build_examples(self.once, cutoff, HORIZON)
        self.assertEqual(sum(example.needed_again for example in alone), 0)
        self.assertGreater(sum(example.needed_again for example in with_outcome), 0)
        for example in with_outcome:
            self.assertEqual(example.lookups_before, 1)
            self.assertTrue(all(when < cutoff for when, _ in example.history))

    def test_the_command_runs_the_no_repeats_proxy(self) -> None:
        folder = Path(self._folder.name)
        out = folder / "report"
        self.addCleanup(_close_app_logging)
        code = ranking_eval.main(
            ["--reader-file", str(folder / "full.sqlite3"), "--no-repeats", "--horizon", "21", "--top", "20", "--out", str(out)]
        )
        self.assertEqual(code, 0)
        saved = json.loads(next(out.glob("extras-*.json")).read_text(encoding="utf-8"))
        self.assertIn("ranking_learning", saved["no_repeats"]["levels"])
        self.assertGreaterEqual(saved["no_repeats"]["cutoffs"], 5)

    def test_the_shelves_in_learning_mode_still_sort_the_first_sync(self) -> None:
        shelves = ranking_eval.shelf_counts(self.once, mode="learning")
        self.assertEqual(sum(shelves["shelves"].values()), shelves["words"])
        self.assertGreaterEqual(shelves["shelves"]["worth"], 0.05 * shelves["words"])
        self.assertGreaterEqual(shelves["shelves"]["not_worth"], 0.05 * shelves["words"])
        self.assertLessEqual(shelves["disputed_share"], 0.25)


if __name__ == "__main__":
    unittest.main()
