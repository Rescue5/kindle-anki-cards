from __future__ import annotations

import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from kindle_vocab_app import anki_export, card_fields, vocab_cache
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.tauri_bridge import dispatch


def _lexeme(lemma: str, *, score: int = 6, state: str = "ready", accepted: bool = True) -> dict:
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
                "context": f"She <b>saw</b> a {lemma} & ran.",
                "book_key": "book",
                "book_title": "The Night Reader",
                "authors": "Demo Author",
                "looked_up_at": "2026-07-10",
            }
        ],
        "freshness": "new",
        "processing": {
            "state": state,
            "analysis": {"base_form": lemma, "pos": "n", "accepted": accepted, "importance_score": score},
            "updated_at": "2026-07-10",
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


def _notes(apkg: Path) -> list[tuple[str, str, str]]:
    with zipfile.ZipFile(apkg) as archive, tempfile.TemporaryDirectory() as temporary:
        collection = Path(archive.extract("collection.anki2", temporary))
        with closing(sqlite3.connect(collection)) as connection:
            return connection.execute("SELECT guid, flds, tags FROM notes ORDER BY guid").fetchall()


class AnkiExportTests(unittest.TestCase):
    def test_context_is_escaped_and_the_word_highlighted(self) -> None:
        fields = anki_export.build_note_fields(_lexeme("glimpse"))
        self.assertEqual(
            fields["Context"],
            'She &lt;b&gt;saw&lt;/b&gt; a <span class="kc-hl">glimpse</span> &amp; ran.',
        )
        self.assertEqual(fields["Meaning"], "")
        self.assertEqual(fields["PartOfSpeech"], "noun")

    def test_offline_definition_is_labelled_with_its_source(self) -> None:
        fields = anki_export.build_note_fields(
            _lexeme("glimpse"), definition_lookup=lambda lemma, pos, context: "a brief look"
        )
        self.assertEqual(fields["Definition"], "a brief look")
        self.assertEqual(fields["DefinitionSource"], "WordNet")

    def test_enrichment_definition_wins_over_offline_lookup(self) -> None:
        lexeme = {**_lexeme("glimpse"), "enrichment": {"meaning_ru": "мельком увидеть", "definition_en": "a quick look"}}
        fields = anki_export.build_note_fields(lexeme, definition_lookup=lambda *_: "unused")
        self.assertEqual(fields["Meaning"], "мельком увидеть")
        self.assertEqual(fields["Definition"], "a quick look")
        self.assertEqual(fields["DefinitionSource"], "")

    def test_selected_book_and_context_translation_in_exported_notes(self) -> None:
        lexeme = _lexeme("glimpse")
        original = lexeme["occurrences"][0]
        original["context"] = "She caught a glimpse of the lighthouse between the waves."
        other = {
            **original, "id": "other", "book_title": "River Watch", "book_key": "river",
            "context": "He caught a glimpse of the river.",
        }
        lexeme["occurrences"].append(other)
        lexeme["enrichment"] = {
            "status": "ready", "prompt_version": 1, "updated_at": "2026-07-11",
            "context_ru": "Она мельком увидела маяк между волнами.",
        }

        with tempfile.TemporaryDirectory() as temporary:
            for occurrence, translation, book_tag in (
                (other, "", "book::river_watch"),
                (original, "Она мельком увидела маяк между волнами.", "book::the_night_reader"),
            ):
                with self.subTest(occurrence=occurrence["id"]):
                    result = anki_export.write_apkg(
                        [lexeme], Path(temporary) / "note.apkg",
                        edits={lexeme["id"]: {"example_occurrence_id": occurrence["id"]}},
                    )
                    [(_, raw_fields, tags)] = _notes(result.path)
                    fields = dict(zip(anki_export.FIELDS, raw_fields.split("\x1f"), strict=True))
                    self.assertEqual(fields["Book"], occurrence["book_title"])
                    self.assertEqual(fields["Context"], anki_export.highlight(occurrence["context"], ["glimpse"]))
                    self.assertEqual(fields["ContextTranslation"], translation)
                    self.assertEqual([tag for tag in tags.split() if tag.startswith("book::")], [book_tag])

    def test_legacy_translation_uses_prompt_order_and_requires_a_matching_quote(self) -> None:
        lexeme = _lexeme("glimpse")
        original = lexeme["occurrences"][0]
        original["context"] = "A glimpse at dawn."
        lexeme["occurrences"].append({
            **original, "id": "later", "context": "A glimpse at dusk.", "looked_up_at": "2026-07-11",
        })
        lexeme["enrichment"] = {
            "status": "ready", "prompt_version": 1, "updated_at": "2026-07-12", "context_ru": "Взгляд на рассвете.",
        }
        self.assertEqual(anki_export.build_note_fields(lexeme)["ContextTranslation"], "")
        edit = {"example_occurrence_id": original["id"]}
        self.assertEqual(anki_export.build_note_fields(lexeme, edit=edit)["ContextTranslation"], "Взгляд на рассвете.")
        lexeme["last_seen_at"] = "2026-07-13"
        self.assertEqual(anki_export.build_note_fields(lexeme, edit=edit)["ContextTranslation"], "")

    def test_structured_details_keep_examples_paired_inside_the_existing_note_type(self) -> None:
        lexeme = _lexeme("bank")
        source = lexeme["occurrences"][0]
        other = {**source, "id": "other", "context": "A bank advertised a mortgage."}
        lexeme["occurrences"].append(other)
        fingerprint = card_fields.context_fingerprint(source["context"])
        lexeme["enrichment"] = {
            "status": "ready", "prompt_version": 2,
            "selected_context_sha256": fingerprint, "context_source_sha256": fingerprint,
            "context_quality": "good", "context_truncated": False,
            "meaning_ru": "берег", "context_meaning_ru": "берег реки",
            "context_ru": "Она увидела берег и побежала.",
            "example_en": "They walked along the bank.", "example_ru": "Они шли вдоль берега.",
            "senses": [
                {"meaning_ru": "банк", "example_en": "A <b>bank</b> lent it.", "example_ru": "Банк выдал & заём."},
                {"meaning_ru": "вираж", "example_en": "The plane began to bank.", "example_ru": "Самолёт накренился."},
                {"meaning_ru": "резерв", "example_en": "They operate a blood bank.",
                 "example_ru": "Они заведуют банком крови."},
                {"meaning_ru": "ряд", "example_en": "A bank of switches lit up.",
                 "example_ru": "Засветился ряд переключателей."},
                {"meaning_ru": "берег", "example_en": "They walked along the bank.",
                 "example_ru": "Они шли вдоль берега."},
            ],
        }
        picked = {"example_occurrence_id": source["id"]}
        baseline = card_fields.resolve(lexeme, picked, include_enrichment=False)
        lexeme["enrichment"]["review_fingerprint"] = card_fields.review_fingerprint(lexeme, baseline)
        fields = anki_export.build_note_fields(lexeme, edit=picked)
        self.assertEqual(list(fields), anki_export.FIELDS)
        self.assertEqual(fields["Meaning"], "берег")
        self.assertEqual(fields["ContextTranslation"], "Она увидела берег и побежала.")
        self.assertIn("Значение в цитате: берег реки", fields["Example"])
        self.assertIn("банк — A &lt;b&gt;bank&lt;/b&gt; lent it. — Банк выдал &amp; заём.", fields["Example"])
        self.assertIn("вираж — The plane began to bank. — Самолёт накренился.", fields["Example"])
        self.assertIn("резерв — They operate a blood bank. — Они заведуют банком крови.", fields["Example"])
        self.assertIn("ряд — A bank of switches lit up. — Засветился ряд переключателей.", fields["Example"])
        self.assertEqual(fields["Example"].count("Пример по значению"), 4)
        self.assertTrue(fields["Example"].endswith("They walked along the bank."))
        self.assertEqual(fields["Example"].count("They walked along the bank."), 1)
        self.assertEqual(fields["ExampleTranslation"], "Они шли вдоль берега.")

        moved = anki_export.build_note_fields(lexeme, edit={"example_occurrence_id": other["id"]})
        self.assertIn("mortgage", moved["Context"])
        self.assertEqual(moved["ContextTranslation"], "")
        self.assertNotIn("Значение в цитате", moved["Example"])

        manual = {**picked, "meaning_ru": "свой перевод"}
        stale = anki_export.build_note_fields(lexeme, edit=manual)
        self.assertEqual(stale["Meaning"], "свой перевод")
        self.assertEqual(stale["Example"], "")
        self.assertEqual(stale["ContextTranslation"], "")
        baseline = card_fields.resolve(lexeme, manual, include_enrichment=False)
        lexeme["enrichment"]["review_fingerprint"] = card_fields.review_fingerprint(lexeme, baseline)
        fresh = anki_export.build_note_fields(lexeme, edit=manual)
        self.assertEqual(fresh["Meaning"], "свой перевод")
        self.assertIn("Банк выдал &amp; заём.", fresh["Example"])
        self.assertIn("Самолёт накренился.", fresh["Example"])

    def test_truncated_translation_is_labeled_and_bound_to_the_full_quote(self) -> None:
        lexeme = _lexeme("glimpse")
        excerpt = "A glimpse " + "x" * (card_fields.MAX_ENRICHMENT_CONTEXT_CHARS - 10)
        source = lexeme["occurrences"][0]
        source["context"] = excerpt + " at dusk"
        lexeme["occurrences"].append({**source, "context": excerpt + " at dawn", "id": "other"})
        lexeme["enrichment"] = {
            "status": "ready", "prompt_version": 2,
            "selected_context_sha256": card_fields.context_fingerprint(source["context"]),
            "context_source_sha256": card_fields.context_fingerprint(excerpt),
            "context_truncated": True, "context_quality": "ambiguous",
            "context_meaning_ru": "предположение", "context_ru": "переведённая часть",
        }
        picked = {"example_occurrence_id": source["id"]}
        baseline = card_fields.resolve(lexeme, picked, include_enrichment=False)
        lexeme["enrichment"]["review_fingerprint"] = card_fields.review_fingerprint(lexeme, baseline)
        first = anki_export.build_note_fields(lexeme, edit=picked)
        self.assertEqual(first["ContextTranslation"], "Перевод фрагмента: переведённая часть")
        self.assertNotIn("предположение", first["Example"])
        second = anki_export.build_note_fields(lexeme, edit={"example_occurrence_id": "other"})
        self.assertEqual(second["ContextTranslation"], "")

    def test_only_useful_accepted_words_are_written_with_stable_guids(self) -> None:
        lexemes = [
            _lexeme("glimpse"),
            _lexeme("the", score=1),
            _lexeme("xyzzy", state="rejected", accepted=False),
            _lexeme("dread", state="pending"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            first = anki_export.write_apkg(lexemes, Path(temporary) / "one.apkg")
            second = anki_export.write_apkg(lexemes, Path(temporary) / "two.apkg")
            self.assertEqual(first.exported_ids, [lexemes[0]["id"]])
            self.assertEqual(first.skipped, 3)
            self.assertEqual(_notes(first.path), _notes(second.path))
            self.assertEqual(len(_notes(first.path)), 1)

    def test_bridge_exports_only_new_words_and_records_the_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"] = [_lexeme("glimpse"), _lexeme("dread")]
            repository_for(workspace).save_catalog(catalog)

            first = dispatch("export_apkg", {}, workspace)
            self.assertEqual(first["exported"], 2)
            self.assertTrue(Path(first["path"]).is_file())
            states = {item["destinations"]["anki"]["state"] for item in repository_for(workspace).load_catalog()["lexemes"]}
            self.assertEqual(states, {"exported"})

            again = dispatch("export_apkg", {}, workspace)
            self.assertEqual(again["exported"], 0)
            everything = dispatch("export_apkg", {"only_new": False}, workspace)
            self.assertEqual(everything["exported"], 2)

    def test_open_path_refuses_files_outside_the_export_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            outside = workspace / "secret.txt"
            outside.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                dispatch("open_path", {"path": str(outside)}, workspace)


if __name__ == "__main__":
    unittest.main()
