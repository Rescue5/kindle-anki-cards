from __future__ import annotations

import math
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kindle_vocab_app.ranking import (
    DEFAULT_WEIGHTS,
    FULL_MODE_MIN_DAYS,
    RANKING_VERSION,
    REASON_CODES,
    Ranking,
    WordFacts,
    library_mode,
    rank,
    study_priority,
)

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def _facts(
    zipf: float = 3.6,
    lookups: tuple[tuple[datetime, str], ...] | None = None,
    **changes,
) -> WordFacts:
    facts = WordFacts(
        lemma_zipf=zipf,
        form_zipf=zipf,
        synset_count=2,
        pos_count=1,
        warnings=frozenset(),
        proper_noun=False,
        lookups=lookups or ((_ago(20), "book-a"),),
    )
    return replace(facts, **changes)


def _codes(ranking: Ranking) -> list[str]:
    return [reason.code for reason in ranking.reasons]


def _texts(ranking: Ranking) -> list[str]:
    return [reason.text for reason in ranking.reasons]


class StudyPriorityTests(unittest.TestCase):
    def test_inclusive_boundaries_use_the_unrounded_score(self) -> None:
        thresholds = (0.34, 0.30, 0.26, 0.22, 0.205, 0.19, 0.12, 0.06)
        for level, threshold in enumerate(thresholds, 1):
            for score, expected in ((threshold, level), (math.nextafter(threshold, 0), level + 1)):
                with self.subTest(score=score):
                    assessed = Ranking(score, "worth", (), mode="learning")
                    result = study_priority(_facts(), NOW, mode="learning", token="river", assessed=assessed)
                    self.assertEqual((result["level"], result["score"], result["provisional"]), (expected, score, False))

    def test_reader_decisions_including_lapsed_known_do_not_change_priority(self) -> None:
        facts = _facts(lookups=((NOW, "book-a"),))
        for mode in ("learning", "full"):
            expected = study_priority(facts, NOW, mode=mode, token="river")
            for decision in ("learn", "skip", "junk", "known"):
                with self.subTest(mode=mode, decision=decision):
                    changed = replace(facts, decision=decision, decided_at=_ago(1))
                    assessed = rank(changed, NOW, mode=mode)
                    self.assertEqual(study_priority(changed, NOW, mode=mode, token="river", assessed=assessed), expected)

    def test_only_nonempty_tokens_without_letters_have_level_ten(self) -> None:
        for token in ("42", "3.14", "—?!", "🐋"):
            with self.subTest(token=token):
                result = study_priority(_facts(), NOW, mode="full", token=token)
                self.assertEqual((result["level"], result["reason"]), (10, "В записи нет букв"))
        suspect = _facts(zipf=0, synset_count=0, proper_noun=True, warnings=frozenset({"non_word", "non_english"}))
        for token in ("Ё", "ё-моё", "co-operate", "3-D", "B2B", "I", "", "旧文"):
            with self.subTest(token=token):
                self.assertIn(study_priority(suspect, NOW, mode="full", token=token)["level"], range(1, 10))

    def test_unknown_name_and_missing_dictionary_keep_uncertain_reasons(self) -> None:
        unknown = _facts(zipf=0, synset_count=0, proper_noun=True)
        incomplete = replace(unknown, warnings=frozenset({"wordnet_unavailable"}))
        self.assertEqual(
            study_priority(unknown, NOW, mode="learning", token="Irwen")["reason"],
            "Слово не найдено в доступных словарях",
        )
        self.assertEqual(
            study_priority(incomplete, NOW, mode="learning", token="Irwen")["reason"], "Словарная проверка неполная"
        )


class DecisionTests(unittest.TestCase):
    def test_the_readers_decision_always_wins(self) -> None:
        strong = _facts(lookups=((_ago(3), "a"), (_ago(2), "b"), (_ago(1), "b")), reading_books=frozenset({"b"}))
        weak = _facts(zipf=1.5, lookups=((_ago(300), "a"),))
        junk = _facts(warnings=frozenset({"non_word"}))
        expected = {"learn": "worth", "skip": "not_worth", "junk": "junk", "known": "known"}
        for facts in (strong, weak, junk):
            for decision, shelf in expected.items():
                with self.subTest(decision=decision, facts=facts.lemma_zipf):
                    ranking = rank(replace(facts, decision=decision), NOW)
                    self.assertEqual(ranking.shelf, shelf)
                    self.assertEqual(ranking.reasons[0].code, f"decision_{decision}")

    def test_learn_explains_itself_and_goes_to_the_top(self) -> None:
        ranking = rank(_facts(zipf=1.5, lookups=((_ago(300), "a"),), decision="learn"), NOW)
        self.assertEqual(ranking.reasons[0].text, "вы отметили «учить»")
        # The score stays the model's own: the decision only fixes the shelf.
        self.assertEqual(ranking.score, rank(replace(_facts(zipf=1.5, lookups=((_ago(300), "a"),)), decision=None), NOW).score)

    def test_a_decision_is_a_zero_weight_reason_and_the_score_still_decomposes(self) -> None:
        facts = _facts(lookups=((_ago(30), "a"), (_ago(4), "b")), reading_books=frozenset({"b"}), decision="skip")
        ranking = rank(facts, NOW)
        self.assertEqual(ranking.reasons[0].weight, 0.0)
        logit = DEFAULT_WEIGHTS.bias + sum(reason.weight for reason in ranking.reasons)
        self.assertAlmostEqual(ranking.score, 1.0 / (1.0 + math.exp(-logit)))

    def test_known_stops_overriding_when_the_word_is_looked_up_after_it(self) -> None:
        facts = _facts(lookups=((_ago(40), "a"), (_ago(4), "a")), decision="known", decided_at=_ago(10))
        ranking = rank(facts, NOW)
        self.assertNotEqual(ranking.shelf, "known")
        self.assertIn("снова искали после «знаю»", _texts(ranking))
        self.assertNotIn("decision_known", _codes(ranking))
        # Lookups before the decision change nothing.
        before = rank(replace(facts, decided_at=_ago(2)), NOW)
        self.assertEqual(before.shelf, "known")
        self.assertEqual(before.reasons[0].code, "decision_known")
        # Other decisions are never lifted by later lookups.
        for decision, shelf in (("learn", "worth"), ("skip", "not_worth"), ("junk", "junk")):
            kept = rank(replace(facts, decision=decision), NOW)
            self.assertEqual(kept.shelf, shelf)

    def test_repeat_cap_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            replace(DEFAULT_WEIGHTS, repeat_cap=0)

    def test_an_unknown_decision_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _facts(decision="maybe")


class SignalTests(unittest.TestCase):
    def _score(self, facts: WordFacts) -> float:
        return rank(facts, NOW).score

    def test_more_lookups_rank_higher(self) -> None:
        once = _facts(lookups=((_ago(5), "a"),))
        twice = _facts(lookups=((_ago(9), "a"), (_ago(5), "a")))
        four = _facts(lookups=((_ago(12), "a"), (_ago(10), "a"), (_ago(9), "a"), (_ago(5), "a")))
        self.assertLess(self._score(once), self._score(twice))
        self.assertLess(self._score(twice), self._score(four))

    def test_several_books_rank_higher(self) -> None:
        one = _facts(lookups=((_ago(9), "a"), (_ago(5), "a")))
        two = _facts(lookups=((_ago(9), "a"), (_ago(5), "b")))
        self.assertLess(self._score(one), self._score(two))

    def test_recent_lookups_rank_higher(self) -> None:
        scores = [self._score(_facts(lookups=((_ago(days), "a"),))) for days in (0, 7, 30, 90, 400)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_the_book_being_read_ranks_higher(self) -> None:
        facts = _facts(lookups=((_ago(5), "now-reading"),))
        reading = replace(facts, reading_books=frozenset({"now-reading"}))
        other = replace(facts, reading_books=frozenset({"other"}))
        self.assertGreater(self._score(reading), self._score(facts))
        self.assertEqual(self._score(other), self._score(facts))

    def test_a_lookup_after_export_is_a_strong_signal(self) -> None:
        facts = _facts(lookups=((_ago(60), "a"), (_ago(10), "a")))
        after = replace(facts, exported_at=_ago(30))
        before = replace(facts, exported_at=_ago(5))
        self.assertEqual(self._score(before), self._score(facts))
        self.assertGreater(self._score(after) - self._score(facts), 0.2)
        self.assertEqual(rank(after, NOW).shelf, "worth")
        self.assertEqual(rank(after, NOW).reasons[0].text, "снова искали после экспорта")

    def test_frequency_is_a_band(self) -> None:
        by_zipf = {zipf: self._score(_facts(zipf=zipf)) for zipf in (1.5, 2.5, 3.0, 4.0, 5.0, 5.5, 6.5)}
        self.assertLess(by_zipf[1.5], by_zipf[2.5])
        self.assertLess(by_zipf[2.5], by_zipf[3.0])
        self.assertEqual(by_zipf[3.0], by_zipf[4.0])
        self.assertEqual(by_zipf[4.0], by_zipf[5.0])
        self.assertGreater(by_zipf[5.0], by_zipf[5.5])
        self.assertGreater(by_zipf[5.5], by_zipf[6.5])

    def test_personal_signals_outweigh_frequency(self) -> None:
        rare_but_mine = _facts(zipf=2.0, lookups=((_ago(9), "a"), (_ago(4), "b"), (_ago(1), "b")))
        usual_once_long_ago = _facts(zipf=3.8, lookups=((_ago(120), "a"),))
        self.assertGreater(self._score(rare_but_mine), self._score(usual_once_long_ago))

    def test_every_score_decomposes_into_its_reasons(self) -> None:
        facts = _facts(
            zipf=2.4,
            lookups=((_ago(40), "a"), (_ago(4), "b")),
            reading_books=frozenset({"b"}),
            exported_at=_ago(20),
        )
        ranking = rank(facts, NOW)
        logit = DEFAULT_WEIGHTS.bias + sum(reason.weight for reason in ranking.reasons)
        self.assertAlmostEqual(ranking.score, 1 / (1 + math.exp(-logit)))


class ShelfTests(unittest.TestCase):
    def test_scores_map_to_worth_disputed_and_not_worth(self) -> None:
        weights = DEFAULT_WEIGHTS
        worth = rank(_facts(lookups=((_ago(3), "a"), (_ago(1), "a"))), NOW)
        not_worth = rank(_facts(zipf=2.0, lookups=((_ago(200), "a"),)), NOW)
        self.assertEqual(worth.shelf, "worth")
        self.assertGreaterEqual(worth.score, weights.worth_from)
        self.assertEqual(not_worth.shelf, "not_worth")
        self.assertLess(not_worth.score, weights.disputed_from)

    def test_the_disputed_band_sits_between_the_thresholds(self) -> None:
        facts = _facts()
        shelves = {}
        for disputed_from, worth_from in ((0.0, 0.99), (0.99, 0.995), (0.0, 0.01)):
            weights = replace(DEFAULT_WEIGHTS, disputed_from=disputed_from, worth_from=worth_from)
            shelves[(disputed_from, worth_from)] = rank(facts, NOW, weights).shelf
        self.assertEqual(shelves[(0.0, 0.99)], "disputed")
        self.assertEqual(shelves[(0.99, 0.995)], "not_worth")
        self.assertEqual(shelves[(0.0, 0.01)], "worth")

    def test_only_disputed_words_lean(self) -> None:
        facts = _facts()
        low = replace(DEFAULT_WEIGHTS, disputed_from=0.0, worth_from=0.99)
        high = replace(DEFAULT_WEIGHTS, disputed_from=0.0, worth_from=rank(facts, NOW).score * 1.5)
        self.assertEqual(rank(facts, NOW, low).lean, "skip")
        self.assertEqual(rank(facts, NOW, high).lean, "learn")
        self.assertEqual(rank(_facts(proper_noun=True), NOW).lean, "junk")
        for ranking in (
            rank(_facts(lookups=((_ago(3), "a"), (_ago(1), "a"))), NOW),
            rank(_facts(zipf=2.0, lookups=((_ago(200), "a"),)), NOW),
            rank(_facts(warnings=frozenset({"non_word"})), NOW),
            rank(_facts(decision="learn"), NOW),
        ):
            self.assertNotEqual(ranking.shelf, "disputed")
            self.assertIsNone(ranking.lean)

    def test_the_default_disputed_band_is_narrow(self) -> None:
        self.assertLess(DEFAULT_WEIGHTS.disputed_from, DEFAULT_WEIGHTS.worth_from)
        self.assertLessEqual(DEFAULT_WEIGHTS.worth_from - DEFAULT_WEIGHTS.disputed_from, 0.05)
        # Sweep a smooth range of words: only a thin slice lands in the band.
        shelves = [
            rank(_facts(zipf=2.0 + i / 10, lookups=((_ago(day), "a"),)), NOW).shelf
            for i in range(30)
            for day in range(0, 120, 3)
        ]
        self.assertLess(shelves.count("disputed") / len(shelves), 0.15)
        self.assertIn("worth", shelves)
        self.assertIn("not_worth", shelves)


class JunkTests(unittest.TestCase):
    def test_strong_junk_goes_to_not_words(self) -> None:
        for warning in ("non_word", "non_english", "unsupported_language"):
            with self.subTest(warning=warning):
                facts = _facts(lookups=((_ago(1), "a"), (_ago(0), "a")), warnings=frozenset({warning}))
                self.assertEqual(rank(facts, NOW).shelf, "junk")

    def test_weak_junk_goes_to_disputed_even_with_a_high_score(self) -> None:
        strong_signals = ((_ago(9), "a"), (_ago(4), "b"), (_ago(1), "b"))
        for change in (
            {"proper_noun": True},
            {"warnings": frozenset({"possibly_glued_words"})},
            {"warnings": frozenset({"unknown_to_local_lexicons"})},
        ):
            with self.subTest(change=change):
                self.assertEqual(rank(_facts(lookups=strong_signals, **change), NOW).shelf, "disputed")

    def test_unknown_and_name_together_are_junk(self) -> None:
        facts = _facts(zipf=0.0, synset_count=0, proper_noun=True)
        ranking = rank(facts, NOW)
        self.assertEqual(ranking.shelf, "junk")
        self.assertIn("нет в словарях", _texts(ranking))
        self.assertIn("похоже на имя", _texts(ranking))

    def test_harmless_warnings_do_not_count_as_junk(self) -> None:
        facts = _facts(warnings=frozenset({"context_has_unusual_symbols"}))
        self.assertEqual(rank(facts, NOW), rank(_facts(), NOW))


class ReasonTests(unittest.TestCase):
    def test_reasons_come_strongest_first(self) -> None:
        facts = _facts(
            zipf=2.4,
            lookups=((_ago(40), "a"), (_ago(30), "b"), (_ago(4), "b")),
            reading_books=frozenset({"b"}),
        )
        weights = [abs(reason.weight) for reason in rank(facts, NOW).reasons]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_reasons_read_as_the_concept_does(self) -> None:
        facts = _facts(
            zipf=3.0,
            lookups=((_ago(40), "a"), (_ago(30), "b"), (_ago(4), "b")),
            reading_books=frozenset({"b"}),
            exported_at=_ago(35),
        )
        texts = _texts(rank(facts, NOW))
        for text in (
            "искали 3 раза",
            "в двух ваших книгах",
            "Из книги с недавними поисками",
            "снова искали после экспорта",
            "встречается раз в ~11 книг",
        ):
            self.assertIn(text, texts)

    def test_lookup_counts_agree_in_russian(self) -> None:
        expected = {2: "искали дважды", 3: "искали 3 раза", 4: "искали 4 раза", 5: "искали 5 раз", 7: "искали 7 раз"}
        for count, text in expected.items():
            facts = _facts(lookups=tuple((_ago(day), "a") for day in range(count)))
            with self.subTest(count=count):
                self.assertIn(text, _texts(rank(facts, NOW)))

    def test_book_counts_agree_in_russian(self) -> None:
        expected = {
            2: "в двух ваших книгах", 3: "в трёх ваших книгах", 4: "в четырёх ваших книгах", 6: "в 6 ваших книгах",
            11: "в 11 ваших книгах", 21: "в 21 вашей книге", 22: "в 22 ваших книгах", 25: "в 25 ваших книгах",
        }
        for count, text in expected.items():
            facts = _facts(lookups=tuple((_ago(day), f"book-{day}") for day in range(count)))
            with self.subTest(count=count):
                self.assertIn(text, _texts(rank(facts, NOW)))

    def test_days_agree_in_russian(self) -> None:
        expected = {0: "искали сегодня", 1: "искали вчера", 2: "искали 2 дня назад", 5: "искали 5 дней назад",
                    21: "искали 21 день назад", 22: "искали 22 дня назад"}
        for days, text in expected.items():
            facts = _facts(lookups=((_ago(days + 0.1), "a"),))
            with self.subTest(days=days):
                self.assertIn(text, _texts(rank(facts, NOW)))
        self.assertIn("давно не искали", _texts(rank(_facts(lookups=((_ago(200), "a"),)), NOW)))

    def test_frequency_reads_in_books_pages_or_as_common(self) -> None:
        expected = {
            2.0: "встречается раз в ~111 книг",
            3.0: "встречается раз в ~11 книг",
            3.6: "встречается раз в ~3 книги",
            3.75: "встречается раз в ~2 книги",
            3.9: "встречается раз в ~1,4 книги",
            4.2: "встречается раз в ~210 страниц",
            4.4: "встречается раз в ~130 страниц",
            4.7: "частое",
        }
        for zipf, text in expected.items():
            with self.subTest(zipf=zipf):
                self.assertIn(text, _texts(rank(_facts(zipf=zipf), NOW)))

    def test_a_very_common_word_is_plainly_common_when_the_penalty_is_negligible(self) -> None:
        for zipf in (5.0, 5.05):
            ranking = rank(_facts(zipf=zipf), NOW)
            reason = next(item for item in ranking.reasons if item.code.startswith("frequency"))
            self.assertEqual((reason.code, reason.text, reason.weight), ("frequency", "частое", 0.0))

    def test_the_common_word_penalty_only_explains_frequency(self) -> None:
        facts = _facts(zipf=5.6, lookups=((NOW, "book-a"),), reading_books=frozenset({"book-a"}))
        for mode in ("learning", "full"):
            with self.subTest(mode=mode):
                ranking = rank(facts, NOW, mode=mode)
                reason = next(item for item in ranking.reasons if item.code == "frequency_common")
                self.assertEqual(reason.text, "очень частое слово")
                self.assertAlmostEqual(reason.weight, -0.6)
                self.assertAlmostEqual(ranking.score, 0.2314752165)
                self.assertEqual(ranking.shelf, "worth")

    def test_book_counts_in_frequency_agree_in_russian(self) -> None:
        # 10**(9 - z) / 90000 books: about 21 and about 24.
        self.assertIn("встречается раз в ~21 книгу", _texts(rank(_facts(zipf=2.72), NOW)))
        self.assertIn("встречается раз в ~24 книги", _texts(rank(_facts(zipf=2.67), NOW)))

    def test_reasons_carry_no_internals(self) -> None:
        facts = _facts(
            zipf=2.4,
            lookups=((_ago(40), "a"), (_ago(4), "b")),
            reading_books=frozenset({"b"}),
            exported_at=_ago(20),
            proper_noun=True,
        )
        for text in _texts(rank(facts, NOW)):
            self.assertNotRegex(text, r"[A-Za-z_]|\d\.\d|zipf|score")


class ContractTests(unittest.TestCase):
    def test_every_emitted_code_is_listed(self) -> None:
        facts = _facts(
            zipf=2.4,
            lookups=((_ago(60), "a"), (_ago(4), "b")),
            reading_books=frozenset({"b"}),
            exported_at=_ago(20),
            proper_noun=True,
            warnings=frozenset({"non_word", "non_english", "possibly_glued_words", "unknown_to_local_lexicons"}),
        )
        seen = set()
        for variant in (facts, replace(facts, lemma_zipf=5.8, form_zipf=5.8, lookups=((_ago(200), "a"),))):
            for decision in (None, "learn", "skip", "junk", "known"):
                seen.update(_codes(rank(replace(variant, decision=decision), NOW)))
        known = replace(facts, decision="known", decided_at=_ago(30))
        seen.update(_codes(rank(known, NOW)))
        seen.update(_codes(rank(_facts(lookups=((_ago(40), "a"),)), NOW)))
        self.assertEqual(seen, set(REASON_CODES))
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))

    def test_every_word_on_not_worth_carries_a_negative_reason(self) -> None:
        thin = 0
        for zipf in (0.0, 1.5, 2.5, 3.0, 3.6, 4.4, 4.8, 5.4, 6.5):
            for days in (0, 3, 10, 25, 34, 40, 50, 60, 120, 400):
                for lookups in (1, 2, 3, 9):
                    for books in (1, 2):
                        for warnings in (frozenset(), frozenset({"possibly_glued_words"}), frozenset({"non_word"})):
                            when = tuple((_ago(days + 2 * i), f"book-{i % books}") for i in range(lookups))
                            for reading in (frozenset(), frozenset({"book-0"})):
                                facts = _facts(zipf=zipf, lookups=when, warnings=warnings, reading_books=reading)
                                ranking = rank(facts, NOW)
                                if ranking.shelf != "not_worth":
                                    continue
                                against = [reason for reason in ranking.reasons if reason.weight < 0]
                                if against:
                                    self.assertNotIn("thin_evidence", _codes(ranking))
                                    continue
                                # Only the bias is against it: the last reason says so, in words, with weight 0.
                                thin += 1
                                self.assertEqual(ranking.reasons[-1].code, "thin_evidence")
                                self.assertEqual(ranking.reasons[-1].weight, 0.0)
        self.assertGreater(thin, 0)  # the grid does reach the case the fallback exists for

    def test_a_word_with_one_lookup_and_nothing_else_says_so(self) -> None:
        ranking = rank(_facts(lookups=((_ago(40), "a"),)), NOW)
        self.assertEqual(ranking.shelf, "not_worth")
        self.assertEqual(ranking.reasons[-1].text, "искали один раз, других признаков нет")
        # With the default weights two lookups are already enough for the worth shelf; weaker weights are not.
        weak = replace(DEFAULT_WEIGHTS, repeat=0.2)
        many = rank(_facts(lookups=((_ago(40), "a"), (_ago(41), "a"))), NOW, weak)
        self.assertEqual(many.shelf, "not_worth")
        self.assertEqual(many.reasons[-1].text, "мало признаков, что слово вам нужно")

    def test_the_fallback_reason_keeps_the_score_decomposable(self) -> None:
        ranking = rank(_facts(lookups=((_ago(40), "a"),)), NOW)
        total = DEFAULT_WEIGHTS.bias + sum(reason.weight for reason in ranking.reasons)
        self.assertAlmostEqual(ranking.score, 1 / (1 + math.exp(-total)))

    def test_the_version_is_named(self) -> None:
        self.assertEqual(RANKING_VERSION, "r2")


class EdgeTests(unittest.TestCase):
    def test_same_input_same_output(self) -> None:
        facts = _facts(lookups=((_ago(9), "a"), (_ago(4), "b")), reading_books=frozenset({"b"}))
        self.assertEqual(rank(facts, NOW), rank(facts, NOW))

    def test_lookup_order_does_not_matter(self) -> None:
        forward = _facts(lookups=((_ago(9), "a"), (_ago(4), "b")))
        backward = _facts(lookups=((_ago(4), "b"), (_ago(9), "a")))
        self.assertEqual(rank(forward, NOW).score, rank(backward, NOW).score)

    def test_a_word_needs_a_lookup(self) -> None:
        with self.assertRaises(ValueError):
            WordFacts(3.0, 3.0, 1, 1, frozenset(), False, ())
        with self.assertRaises(ValueError):
            replace(_facts(), lookups=())

    def test_times_without_a_zone_are_taken_as_utc(self) -> None:
        aware = _facts(lookups=((_ago(5), "a"),))
        naive = _facts(lookups=((_ago(5).replace(tzinfo=None), "a"),))
        self.assertEqual(rank(aware, NOW).score, rank(naive, NOW.replace(tzinfo=None)).score)

    def test_a_lookup_in_the_future_counts_as_now(self) -> None:
        future = rank(_facts(lookups=((NOW + timedelta(days=3), "a"),)), NOW)
        today = rank(_facts(lookups=((NOW, "a"),)), NOW)
        self.assertEqual(future.score, today.score)
        self.assertIn("искали сегодня", _texts(future))

    def test_missing_frequencies_do_not_break_the_ranking(self) -> None:
        for zipf in (0.0, float("nan"), -1.0):
            with self.subTest(zipf=zipf):
                ranking = rank(_facts(zipf=zipf), NOW)
                self.assertTrue(0.0 <= ranking.score <= 1.0)
                self.assertNotIn("frequency", _codes(ranking))

    def test_scores_stay_between_zero_and_one(self) -> None:
        many = tuple((_ago(day / 10), f"book-{day}") for day in range(200))
        top = rank(_facts(lookups=many, reading_books=frozenset({"book-0"}), exported_at=_ago(100)), NOW)
        bottom = rank(_facts(zipf=0.5, lookups=((_ago(5000), "a"),), warnings=frozenset({"non_word"})), NOW)
        for ranking in (top, bottom):
            self.assertTrue(0.0 <= ranking.score <= 1.0)
        self.assertEqual(top.shelf, "worth")
        self.assertEqual(bottom.shelf, "junk")


REPEAT_CODES = {"repeat_lookups", "after_export", "several_books"}


class RankingModeTests(unittest.TestCase):
    def test_library_mode_needs_repeats_and_enough_history(self) -> None:
        self.assertEqual(library_mode(FULL_MODE_MIN_DAYS, True), "full")
        self.assertEqual(library_mode(400, True), "full")
        self.assertEqual(library_mode(FULL_MODE_MIN_DAYS - 1, True), "learning")
        self.assertEqual(library_mode(0, True), "learning")
        # A source without repeat lookups stays in learning however long the history is.
        self.assertEqual(library_mode(1000, False), "learning")
        self.assertEqual(library_mode(10, True, min_days=7), "full")

    def test_full_is_the_default_and_unchanged(self) -> None:
        facts = _facts(lookups=((_ago(30), "a"), (_ago(4), "b")), reading_books=frozenset({"b"}), exported_at=_ago(10))
        self.assertEqual(rank(facts, NOW), rank(facts, NOW, mode="full"))
        self.assertEqual(rank(facts, NOW).mode, "full")

    def test_unknown_mode_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            rank(_facts(), NOW, mode="fast")

    def test_learning_ignores_repeats_books_and_exports_and_never_cites_them(self) -> None:
        many = _facts(
            lookups=((_ago(30), "a"), (_ago(9), "b"), (_ago(4), "c"), (_ago(2), "c")),
            reading_books=frozenset({"c"}),
            exported_at=_ago(20),
        )
        once = _facts(lookups=((_ago(2), "c"),), reading_books=frozenset({"c"}))
        learning = rank(many, NOW, mode="learning")
        self.assertEqual(learning.mode, "learning")
        self.assertTrue(REPEAT_CODES.isdisjoint(_codes(learning)))
        self.assertEqual(learning.score, rank(once, NOW, mode="learning").score)
        self.assertNotIn("раз", " ".join(_texts(learning)).replace("встречается раз в", ""))
        self.assertGreater(rank(many, NOW).score, learning.score)

    def test_learning_leans_on_the_book_being_read_recency_and_the_frequency_band(self) -> None:
        base = _facts(lookups=((_ago(3), "a"),), reading_books=frozenset({"a"}))
        reading = rank(base, NOW, mode="learning")
        self.assertIn("reading_now", _codes(reading))
        self.assertGreater(reading.score, rank(replace(base, reading_books=frozenset()), NOW, mode="learning").score)
        self.assertGreater(reading.score, rank(replace(base, lookups=((_ago(60), "a"),)), NOW, mode="learning").score)
        self.assertGreater(reading.score, rank(replace(base, lemma_zipf=2.0, form_zipf=2.0), NOW, mode="learning").score)
        self.assertGreater(reading.score, rank(replace(base, lemma_zipf=6.0, form_zipf=6.0), NOW, mode="learning").score)

    def test_learning_scores_still_decompose_and_decisions_still_win(self) -> None:
        facts = _facts(lookups=((_ago(40), "a"), (_ago(4), "a")), reading_books=frozenset({"a"}))
        ranking = rank(facts, NOW, mode="learning")
        logit = DEFAULT_WEIGHTS.bias + sum(reason.weight for reason in ranking.reasons)
        self.assertAlmostEqual(ranking.score, 1.0 / (1.0 + math.exp(-logit)))
        for decision, shelf in (("learn", "worth"), ("skip", "not_worth"), ("junk", "junk"), ("known", "known")):
            with self.subTest(decision=decision):
                self.assertEqual(rank(replace(facts, decision=decision), NOW, mode="learning").shelf, shelf)

    def test_learning_keeps_junk_evidence_and_the_negative_reason(self) -> None:
        junk = rank(_facts(warnings=frozenset({"non_word"})), NOW, mode="learning")
        self.assertEqual(junk.shelf, "junk")
        old = rank(_facts(lookups=((_ago(300), "a"),)), NOW, mode="learning")
        self.assertEqual(old.shelf, "not_worth")
        self.assertTrue(any(reason.weight < 0 for reason in old.reasons))

    def test_known_again_is_only_a_note_in_learning(self) -> None:
        facts = _facts(lookups=((_ago(40), "a"), (_ago(4), "a")), decision="known", decided_at=_ago(10))
        learning = rank(facts, NOW, mode="learning")
        again = next(reason for reason in learning.reasons if reason.code == "known_again")
        self.assertEqual(again.weight, 0.0)
        self.assertNotEqual(learning.shelf, "known")


if __name__ == "__main__":
    unittest.main()
