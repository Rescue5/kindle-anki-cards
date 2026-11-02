from __future__ import annotations

import unittest

from kindle_vocab_app import anki_export, offline_dictionary
from tests.test_anki_export import _lexeme


class OfflineDictionaryTests(unittest.TestCase):
    def test_bundled_dictionary_gives_russian_meanings_for_the_lemma(self) -> None:
        found = offline_dictionary.lookup("Dread", "n")
        self.assertIsNotNone(found)
        self.assertIn("страх", found["meaning_ru"])
        self.assertEqual(found["source"], "wiktionary")

    def test_the_requested_part_of_speech_is_preferred(self) -> None:
        self.assertEqual(offline_dictionary.lookup("admit", "v")["pos"], "v")
        self.assertEqual(offline_dictionary.lookup("give up", "v")["pos"], "p")

    def test_meanings_are_limited_to_the_first_senses(self) -> None:
        meaning = offline_dictionary.lookup("admit", "v")["meaning_ru"]
        self.assertLessEqual(meaning.count(";") + 1, offline_dictionary.MAX_SENSES * 3)

    def test_unknown_words_have_no_meaning(self) -> None:
        self.assertIsNone(offline_dictionary.lookup("zzzzqx", "n"))
        self.assertIsNone(offline_dictionary.lookup("", "n"))

    def test_a_lexeme_falls_back_from_its_analysis_to_its_lemma(self) -> None:
        lexeme = _lexeme("glimpse")
        lexeme["processing"]["analysis"]["base_form"] = "glimpsed-form-that-is-not-a-word"
        self.assertIn("проблеск", offline_dictionary.lookup_lexeme(lexeme)["meaning_ru"])

    def test_review_cards_get_meanings_too(self) -> None:
        card = {"lemma": "dread", "display_form": "dread", "analysis": {"base_form": "dread", "pos": "n"}}
        offline_dictionary.attach([card])
        self.assertIn("страх", card["dictionary"]["meaning_ru"])


class DictionaryInAnkiTests(unittest.TestCase):
    def test_card_meaning_falls_back_to_the_dictionary(self) -> None:
        lexeme = {**_lexeme("glimpse"), "dictionary": {"meaning_ru": "проблеск", "pos": "n", "source": "wiktionary"}}
        self.assertEqual(anki_export.build_note_fields(lexeme)["Meaning"], "проблеск")

    def test_a_context_translation_wins_over_the_dictionary(self) -> None:
        lexeme = {
            **_lexeme("glimpse"),
            "dictionary": {"meaning_ru": "проблеск", "pos": "n", "source": "wiktionary"},
            "enrichment": {"status": "ready", "meaning_ru": "мельком увидеть", "updated_at": "2026-07-11"},
        }
        self.assertEqual(anki_export.build_note_fields(lexeme)["Meaning"], "мельком увидеть")

    def test_cards_exported_before_the_dictionary_are_updated_once(self) -> None:
        lexeme = {**_lexeme("glimpse"), "dictionary": {"meaning_ru": "проблеск", "pos": "n", "source": "wiktionary"}}
        lexeme["destinations"]["anki"] = {"state": "exported", "last_exported_at": "2026-10-30T10:00:00+00:00"}
        self.assertTrue(anki_export.needs_anki_update(lexeme))
        lexeme["destinations"]["anki"] = {"state": "exported", "last_exported_at": "2026-11-03T10:00:00+00:00"}
        self.assertFalse(anki_export.needs_anki_update(lexeme))

    def test_cards_without_any_meaning_are_not_re_exported(self) -> None:
        lexeme = {**_lexeme("glimpse"), "dictionary": None}
        lexeme["destinations"]["anki"] = {"state": "exported", "last_exported_at": "2026-10-30T10:00:00+00:00"}
        self.assertFalse(anki_export.needs_anki_update(lexeme))


if __name__ == "__main__":
    unittest.main()
