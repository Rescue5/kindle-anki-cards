from __future__ import annotations

import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from kindle_vocab_app import anki_export, vocab_cache
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


def _notes(apkg: Path) -> list[tuple[str, str]]:
    with zipfile.ZipFile(apkg) as archive, tempfile.TemporaryDirectory() as temporary:
        collection = Path(archive.extract("collection.anki2", temporary))
        with closing(sqlite3.connect(collection)) as connection:
            return connection.execute("SELECT guid, flds FROM notes ORDER BY guid").fetchall()


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
