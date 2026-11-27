"""The reader's own rows (B3a writes, B3b re-link) on a temporary library.

Every word here is invented; nothing comes from a real reader's library.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from library_fixture import build_v3_library, lid

from kindle_vocab_app import library_state, vocab_cache
from kindle_vocab_app.contracts import ERROR_TEXTS, MEANING_MAX_LENGTH
from kindle_vocab_app.library_repository import SCHEMA_VERSION, repository_for
from kindle_vocab_app.library_state import LibraryStateError


def _lexeme(key: str, *, forms: tuple[str, ...] = (), occurrences: int = 2) -> dict[str, Any]:
    item_id = vocab_cache.lexeme_id("en", key)
    return {
        "id": item_id,
        "lemma": key,
        "display_form": key,
        "language": "en",
        "forms": [key, *forms],
        "occurrences": [
            {
                "id": f"occ-{key}-{index}",
                "source": "kindle",
                "word": key,
                "context": f"Sentence {index} with {key}.",
                "book_key": "book-invented",
                "book_title": "An Invented Book",
                "authors": "N. Body",
                "looked_up_at": f"2026-07-1{index}T10:00:00+00:00",
            }
            for index in range(occurrences)
        ],
        "freshness": "known",
        "processing": {"state": "pending", "analysis": None, "updated_at": "", "error": ""},
        "sources": {"kindle": True, "obsidian": False, "legacy": False},
        "destinations": {},
        "first_seen_at": "2026-07-10T10:00:00+00:00",
        "last_seen_at": "2026-07-11T10:00:00+00:00",
        "last_kindle_sync_id": "sync-1",
    }


def _rows(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return [tuple(row) for row in connection.execute(sql, params)]


def _execute(path: Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(sql, params)
        connection.commit()


def _record_export(path: Path, keys: list[str], *, destination: str = "anki") -> int:
    """An export run as B6 will record it; written directly because B6 does not exist yet."""
    with closing(sqlite3.connect(path)) as connection:
        cursor = connection.execute(
            "INSERT INTO export_runs(destination, scope, created_at, word_count, path)"
            " VALUES (?, 'new', ?, ?, '')",
            (destination, vocab_cache.utc_now(), len(keys)),
        )
        run_id = int(cursor.lastrowid or 0)
        for key in keys:
            row = connection.execute(
                "SELECT id, language, canonical_key FROM lexemes WHERE canonical_key = ?", (key,)
            ).fetchone()
            connection.execute(
                "INSERT INTO export_items(run_id, lexeme_id, language, canonical_key)"
                " VALUES (?, ?, ?, ?)",
                (run_id, row[0], row[1], row[2]),
            )
        connection.commit()
    return run_id


def _process(repository: Any, lexeme_id: str, base_form: str) -> bool:
    """What `process_queue` does for one word: analyse, set the lemma, save that word."""
    catalog = repository.load_catalog()
    lexeme = next(item for item in catalog["lexemes"] if item["id"] == lexeme_id)
    lexeme["processing"] = {
        "state": "ready",
        "analysis": {"base_form": base_form, "accepted": True, "importance_score": 6},
        "updated_at": vocab_cache.utc_now(),
        "error": "",
        "origin": "sqlite_optimizer",
    }
    lexeme["lemma"] = base_form
    return repository.save_processed_lexeme(catalog, lexeme_id)


class _LibraryCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self._temporary.name)
        self.repository = repository_for(self.workspace)
        self.path = self.repository.path

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def save(self, *lexemes: dict[str, Any]) -> None:
        catalog = vocab_cache.empty_catalog()
        catalog["lexemes"] = list(lexemes)
        self.repository.save_catalog(catalog)

    def resave(self) -> None:
        self.repository.save_catalog(self.repository.load_catalog())

    def id_of(self, key: str) -> str:
        rows = _rows(self.path, "SELECT id FROM lexemes WHERE canonical_key = ?", (key,))
        self.assertEqual(len(rows), 1, "one lexeme per key")
        return str(rows[0][0])


class UserWritesTests(_LibraryCase):
    def test_set_decision_stores_the_ranking_snapshot_and_the_relink_hint(self) -> None:
        self.save(_lexeme("brindlewort"))
        lexeme_id = self.id_of("brindlewort")

        record = self.repository.set_decision(
            lexeme_id, "learn", shelf_at="disputed", score_at=0.41, ranking_version="r2"
        )

        self.assertEqual(record["value"], "learn")
        self.assertTrue(record["decided_at"])
        rows = _rows(
            self.path,
            "SELECT lexeme_id, language, canonical_key, decision, shelf_at, score_at,"
            " ranking_version FROM word_decisions",
        )
        self.assertEqual(rows, [(lexeme_id, "en", "brindlewort", "learn", "disputed", 0.41, "r2")])
        decisions = self.repository.load_decisions()
        self.assertEqual(decisions[lexeme_id]["value"], "learn")
        self.assertEqual(decisions[lexeme_id]["decided_at"], record["decided_at"])

    def test_a_new_decision_replaces_the_old_and_none_removes_it(self) -> None:
        self.save(_lexeme("brindlewort"))
        lexeme_id = self.id_of("brindlewort")
        self.repository.set_decision(lexeme_id, "learn", shelf_at="worth", score_at=0.8, ranking_version="r2")
        self.repository.set_decision(lexeme_id, "known", shelf_at="worth", score_at=0.8, ranking_version="r2")
        self.assertEqual(_rows(self.path, "SELECT decision FROM word_decisions"), [("known",)])

        self.assertIsNone(self.repository.set_decision(lexeme_id, None))

        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM word_decisions"), [(0,)])
        self.assertEqual(self.repository.load_decisions(), {})

    def test_bad_decision_and_unknown_lexeme_are_coded_errors(self) -> None:
        self.save(_lexeme("brindlewort"))
        lexeme_id = self.id_of("brindlewort")

        for value in ("maybe", "", "LEARN", 1):
            with self.assertRaises(LibraryStateError) as raised:
                self.repository.set_decision(lexeme_id, value, shelf_at="worth")  # type: ignore[arg-type]
            self.assertEqual(raised.exception.code, "bad_decision")
            self.assertEqual(str(raised.exception), ERROR_TEXTS["bad_decision"])
        with self.assertRaises(LibraryStateError) as raised:
            self.repository.set_decision("no-such-word", "learn")
        self.assertEqual(raised.exception.code, "unknown_lexeme")
        self.assertEqual(str(raised.exception), ERROR_TEXTS["unknown_lexeme"])
        with self.assertRaises(LibraryStateError) as raised:
            self.repository.save_card_edit("no-such-word", meaning_ru="слово")
        self.assertEqual(raised.exception.code, "unknown_lexeme")
        # A coded error is a ValueError, so the bridge passes its Russian text through.
        self.assertIsInstance(raised.exception, ValueError)
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM word_decisions"), [(0,)])

    def test_save_card_edit_validates_and_clears(self) -> None:
        self.save(_lexeme("brindlewort"), _lexeme("quillet"))
        lexeme_id = self.id_of("brindlewort")

        record = self.repository.save_card_edit(lexeme_id, meaning_ru="  колючий куст  ")
        self.assertEqual(record["meaning_ru"], "колючий куст")
        record = self.repository.save_card_edit(lexeme_id, example_occurrence_id="occ-brindlewort-1")
        self.assertEqual(record["meaning_ru"], "колючий куст")  # untouched when not given
        self.assertEqual(record["example_occurrence_id"], "occ-brindlewort-1")
        self.assertEqual(
            _rows(self.path, "SELECT example_context, example_form, canonical_key FROM card_edits"),
            [("Sentence 1 with brindlewort.", "brindlewort", "brindlewort")],
        )

        exact = "я" * MEANING_MAX_LENGTH
        self.assertEqual(self.repository.save_card_edit(lexeme_id, meaning_ru=exact)["meaning_ru"], exact)
        with self.assertRaises(LibraryStateError) as raised:
            self.repository.save_card_edit(lexeme_id, meaning_ru=exact + "я")
        self.assertEqual(raised.exception.code, "too_long")
        self.assertEqual(str(raised.exception), ERROR_TEXTS["too_long"])
        with self.assertRaises(LibraryStateError) as raised:
            self.repository.save_card_edit(lexeme_id, example_occurrence_id="occ-quillet-0")
        self.assertEqual(raised.exception.code, "example_not_found")
        self.assertEqual(str(raised.exception), ERROR_TEXTS["example_not_found"])
        with self.assertRaises(LibraryStateError):
            self.repository.save_card_edit(lexeme_id, example_occurrence_id="occ-missing")
        # A failed write changes nothing.
        self.assertEqual(self.repository.load_card_edits()[lexeme_id]["meaning_ru"], exact)

        record = self.repository.save_card_edit(lexeme_id, meaning_ru="")
        self.assertIsNone(record["meaning_ru"])
        self.assertEqual(record["example_occurrence_id"], "occ-brindlewort-1")
        self.assertIsNone(self.repository.save_card_edit(lexeme_id, example_occurrence_id=""))
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM card_edits"), [(0,)])
        self.assertIsNone(self.repository.save_card_edit(lexeme_id, meaning_ru="   "))
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM card_edits"), [(0,)])

    def test_meaning_whitespace_collapses_to_single_spaces_before_the_length_check(self) -> None:
        self.save(_lexeme("brindlewort"))
        lexeme_id = self.id_of("brindlewort")

        record = self.repository.save_card_edit(lexeme_id, meaning_ru=" колючий\tкуст\r\n\n  у  дороги ")

        self.assertEqual(record["meaning_ru"], "колючий куст у дороги")
        padded = "\t".join(["я" * 100, "я" * 99])  # 200 after the tab becomes a space
        self.assertEqual(
            self.repository.save_card_edit(lexeme_id, meaning_ru=padded + "\n\n\n")["meaning_ru"],
            padded.replace("\t", " "),
        )

    def test_bulk_readers_use_one_query_each_and_skip_orphans(self) -> None:
        self.save(_lexeme("brindlewort"), _lexeme("quillet"))
        for key in ("brindlewort", "quillet"):
            self.repository.set_decision(self.id_of(key), "skip", shelf_at="not_worth")
            self.repository.save_card_edit(self.id_of(key), meaning_ru="что-то")
        _execute(
            self.path,
            "INSERT INTO word_decisions(lexeme_id, language, canonical_key, decision, decided_at)"
            " VALUES ('gone', 'en', 'vanished', 'learn', '2026-01-01T00:00:00+00:00')",
        )
        with self.repository.connect() as connection:
            statements: list[str] = []
            connection.set_trace_callback(statements.append)
            decisions = library_state.read_decisions(connection)
            edits = library_state.read_card_edits(connection)
            connection.set_trace_callback(None)

        self.assertEqual(len(statements), 2)
        self.assertEqual(set(decisions), {self.id_of("brindlewort"), self.id_of("quillet")})
        self.assertEqual(set(edits), set(decisions))


class RelinkTests(_LibraryCase):
    def _user_rows_for(self, key: str) -> None:
        lexeme_id = self.id_of(key)
        self.repository.set_decision(lexeme_id, "learn", shelf_at="worth", score_at=0.7, ranking_version="r2")
        self.repository.save_card_edit(
            lexeme_id, meaning_ru="перевод", example_occurrence_id=f"occ-{key}-0"
        )
        _record_export(self.path, [key])

    def _assert_linked(self, key: str, *, decision: str = "learn") -> None:
        lexeme_id = self.id_of(key)
        self.assertEqual(self.repository.load_decisions()[lexeme_id]["value"], decision)
        self.assertIn(lexeme_id, self.repository.load_card_edits())
        self.assertIn(
            (lexeme_id, "en", key),
            _rows(self.path, "SELECT lexeme_id, language, canonical_key FROM export_items"),
        )

    def test_user_rows_survive_two_catalog_saves(self) -> None:
        self.save(_lexeme("brindlewort"), _lexeme("quillet"))
        self._user_rows_for("brindlewort")

        self.resave()
        self.resave()

        self._assert_linked("brindlewort")
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM word_decisions"), [(1,)])

    def test_process_queue_key_change_keeps_the_rows_and_a_later_save_relinks_them(self) -> None:
        # The word is stored under its inflected form, the reader decides, then
        # processing finds the base form: save_processed_lexeme keeps the old id
        # with the new key, and the next catalog save recomputes the id.
        self.save(_lexeme("glimmerings"), _lexeme("quillet"))
        old_id = self.id_of("glimmerings")
        self._user_rows_for("glimmerings")

        self.assertFalse(_process(self.repository, old_id, "glimmering"))
        self.assertEqual(self.id_of("glimmering"), old_id)
        self._assert_linked("glimmering")

        self.resave()
        new_id = self.id_of("glimmering")
        self.assertNotEqual(new_id, old_id)
        self.assertEqual(new_id, vocab_cache.lexeme_id("en", "glimmering"))
        self._assert_linked("glimmering")
        self.resave()
        self._assert_linked("glimmering")
        self.assertEqual(
            _rows(self.path, "SELECT COUNT(*) FROM word_decisions WHERE lexeme_id = ?", (old_id,)),
            [(0,)],
        )

    def test_rows_leave_an_old_id_that_now_belongs_to_another_word(self) -> None:
        # "snorled" is stored under hash("snorled"), the reader decides, processing finds the
        # base form "snorl" (same id). A later save recomputes the id to hash("snorl") while a
        # newly seen "snorled" takes hash("snorled"): the rows must follow "snorl".
        self.save(_lexeme("snorled"))
        old_id = self.id_of("snorled")
        self._user_rows_for("snorled")
        self.assertFalse(_process(self.repository, old_id, "snorl"))

        catalog = self.repository.load_catalog()
        catalog["lexemes"].append(_lexeme("snorled"))  # the same word seen again, unprocessed
        self.repository.save_catalog(catalog)

        base_id, newcomer_id = self.id_of("snorl"), self.id_of("snorled")
        self.assertEqual(newcomer_id, old_id)
        self._assert_linked("snorl")
        self.assertNotIn(newcomer_id, self.repository.load_decisions())
        self.assertNotIn(newcomer_id, self.repository.load_card_edits())
        self.assertEqual(
            _rows(self.path, "SELECT lexeme_id FROM word_decisions"), [(base_id,)]
        )
        self.assertEqual(
            _rows(self.path, "SELECT lexeme_id FROM export_items"), [(base_id,)]
        )
        self.resave()
        self._assert_linked("snorl")
        self.assertNotIn(self.id_of("snorled"), self.repository.load_decisions())

    def test_a_stale_row_on_a_word_is_never_shown_nor_overwritten(self) -> None:
        self.save(_lexeme("quillet"))
        quillet_id = self.id_of("quillet")
        _execute(
            self.path,
            "INSERT INTO word_decisions(lexeme_id, language, canonical_key, decision, decided_at)"
            " VALUES (?, 'en', 'vanished', 'junk', '2026-09-01T00:00:00+00:00')",
            (quillet_id,),
        )

        self.resave()
        self.assertEqual(self.repository.load_decisions(), {})
        self.repository.set_decision(quillet_id, "learn")

        self.assertEqual(self.repository.load_decisions()[quillet_id]["value"], "learn")
        self.assertEqual(
            sorted(_rows(self.path, "SELECT decision, canonical_key FROM word_decisions")),
            [("junk", "vanished"), ("learn", "quillet")],
        )

    def test_the_merge_check_of_save_processed_lexeme_runs_inside_its_transaction(self) -> None:
        self.save(_lexeme("glimmerings"))
        lexeme_id = self.id_of("glimmerings")
        statements: list[tuple[int, str]] = []
        original = self.repository.connect

        @contextmanager
        def traced() -> Iterator[sqlite3.Connection]:
            with original() as connection:
                key = id(connection)
                connection.set_trace_callback(lambda sql: statements.append((key, sql)))
                yield connection

        with mock.patch.object(self.repository, "connect", traced):
            _process(self.repository, lexeme_id, "glimmering")

        check = next(
            index for index, (_, sql) in enumerate(statements) if "AND id <>" in sql
        )
        same_connection = [sql for key, sql in statements[:check] if key == statements[check][0]]
        self.assertTrue(same_connection and same_connection[-1].strip() == "BEGIN IMMEDIATE")
        self.assertEqual(self.id_of("glimmering"), lexeme_id)

    def test_canonical_merge_keeps_the_newest_row_and_the_other_as_an_orphan(self) -> None:
        self.save(_lexeme("flinted"), _lexeme("flint"))
        merged_id, kept_id = self.id_of("flinted"), self.id_of("flint")
        self.repository.set_decision(merged_id, "learn", shelf_at="worth")
        self.repository.set_decision(kept_id, "skip", shelf_at="not_worth")
        self.repository.save_card_edit(merged_id, meaning_ru="старый перевод")
        self.repository.save_card_edit(kept_id, meaning_ru="новый перевод")
        # The decision on the word that disappears is the newer one; the edit is older.
        _execute(self.path, "UPDATE word_decisions SET decided_at = '2026-09-02T00:00:00+00:00' WHERE lexeme_id = ?", (merged_id,))
        _execute(self.path, "UPDATE word_decisions SET decided_at = '2026-09-01T00:00:00+00:00' WHERE lexeme_id = ?", (kept_id,))
        _execute(self.path, "UPDATE card_edits SET updated_at = '2026-09-01T00:00:00+00:00' WHERE lexeme_id = ?", (merged_id,))
        _execute(self.path, "UPDATE card_edits SET updated_at = '2026-09-02T00:00:00+00:00' WHERE lexeme_id = ?", (kept_id,))
        _record_export(self.path, ["flinted"])
        _record_export(self.path, ["flint"])
        _record_export(self.path, ["flinted", "flint"])

        self.assertTrue(_process(self.repository, merged_id, "flint"))  # the keys merged

        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM lexemes WHERE canonical_key LIKE 'flint%'"), [(1,)])
        self.assertEqual(self.id_of("flint"), kept_id)
        self.assertEqual(self.repository.load_decisions()[kept_id]["value"], "learn")
        self.assertEqual(self.repository.load_card_edits()[kept_id]["meaning_ru"], "новый перевод")
        # Nothing the reader wrote is deleted: the losers stay as orphan rows.
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM word_decisions"), [(2,)])
        self.assertEqual(
            sorted(_rows(self.path, "SELECT decision FROM word_decisions WHERE lexeme_id <> ?", (kept_id,))),
            [("skip",)],
        )
        self.assertEqual(
            _rows(self.path, "SELECT meaning_ru FROM card_edits WHERE lexeme_id <> ?", (kept_id,)),
            [("старый перевод",)],
        )
        # Every export item is kept; the three runs still mention the word.
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM export_items"), [(4,)])
        self.assertEqual(
            _rows(self.path, "SELECT COUNT(DISTINCT run_id) FROM export_items WHERE lexeme_id = ?", (kept_id,)),
            [(3,)],
        )

        # The orphan never comes back, not even after the reader clears the decision.
        self.repository.set_decision(kept_id, None)
        self.resave()
        self.resave()
        self.assertNotIn(kept_id, self.repository.load_decisions())
        self.assertEqual(_rows(self.path, "SELECT COUNT(*) FROM word_decisions"), [(1,)])

    def test_an_orphan_is_relinked_through_a_form_of_the_word(self) -> None:
        self.save(_lexeme("quillet", forms=("quillets",)))
        _execute(
            self.path,
            "INSERT INTO word_decisions(lexeme_id, language, canonical_key, decision, decided_at)"
            " VALUES ('stale-id', 'en', 'quillets', 'junk', '2026-09-01T00:00:00+00:00')",
        )
        _execute(
            self.path,
            "INSERT INTO word_decisions(lexeme_id, language, canonical_key, decision, decided_at)"
            " VALUES ('lost-id', 'en', 'nowhere', 'junk', '2026-09-01T00:00:00+00:00')",
        )

        self.resave()

        self.assertEqual(self.repository.load_decisions()[self.id_of("quillet")]["value"], "junk")
        self.assertEqual(
            _rows(self.path, "SELECT lexeme_id, canonical_key FROM word_decisions WHERE decision = 'junk' ORDER BY lexeme_id"),
            sorted([(self.id_of("quillet"), "quillet"), ("lost-id", "nowhere")]),
        )

    def test_sync_and_import_never_wipe_user_tables(self) -> None:
        self.save(_lexeme("brindlewort"), _lexeme("quillet"))
        self._user_rows_for("brindlewort")
        self.repository.set_decision(self.id_of("quillet"), "known")
        entries = [
            {
                "word": "brindlewort",
                "stem": "brindlewort",
                "language": "en",
                "context": "A fresh sentence with brindlewort.",
                "book_key": "book-second",
                "book_title": "A Second Book",
                "authors": "S. Omeone",
                "lookup_id": "lookup-1",
                "looked_up_at": "2026-10-01T10:00:00+00:00",
            },
            {
                "word": "snarvel",
                "stem": "snarvel",
                "language": "en",
                "context": "Nobody knew the snarvel.",
                "book_key": "book-second",
                "book_title": "A Second Book",
                "authors": "S. Omeone",
                "lookup_id": "lookup-2",
                "looked_up_at": "2026-10-01T11:00:00+00:00",
            },
        ]
        before = {
            table: _rows(self.path, f"SELECT * FROM {table} ORDER BY 1")
            for table in ("word_decisions", "card_edits", "export_items", "export_runs")
        }

        for sync_id in ("sync-2", "sync-3"):
            merged = vocab_cache.merge_kindle(self.repository.load_catalog(), entries, sync_id=sync_id)
            self.repository.save_catalog(merged)

        after = {
            table: _rows(self.path, f"SELECT * FROM {table} ORDER BY 1")
            for table in ("word_decisions", "card_edits", "export_items", "export_runs")
        }
        self.assertEqual(after, before)
        self.assertEqual(len(self.repository.load_catalog()["lexemes"]), 3)
        self._assert_linked("brindlewort")

    def test_relink_logs_counts_without_words(self) -> None:
        self.save(_lexeme("glimmerings"))
        old_id = self.id_of("glimmerings")
        self.repository.set_decision(old_id, "learn")
        _process(self.repository, old_id, "glimmering")

        with self.assertLogs("kindle_vocab_app.library_state", level="INFO") as logs:
            self.resave()

        text = "\n".join(logs.output)
        self.assertIn("decisions=1", text)
        self.assertNotIn("glimmer", text)


class ReviewCardsMigrationTests(unittest.TestCase):
    def test_v3_library_with_review_cards_keeps_them_through_migration_and_saves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            path = build_v3_library(workspace)
            with closing(sqlite3.connect(path)) as connection:
                connection.executemany(
                    "INSERT INTO review_cards VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (lid("meander"), 7.5, 3, "2026-10-09T00:00:00+00:00",
                         "2026-10-01T00:00:00+00:00", "good"),
                        (lid("quibble"), 0.007, 0, "2026-09-01T00:10:00+00:00",
                         "2026-09-01T00:00:00+00:00", "again"),
                    ],
                )
                connection.commit()
            before = _rows(path, "SELECT * FROM review_cards ORDER BY lexeme_id")
            self.assertEqual(len(before), 3)

            repository = repository_for(workspace)
            self.assertEqual(_rows(path, "SELECT MAX(version) FROM schema_migrations"), [(SCHEMA_VERSION,)])
            self.assertEqual(_rows(path, "SELECT * FROM review_cards ORDER BY lexeme_id"), before)

            repository.save_catalog(repository.load_catalog())
            self.assertEqual(_rows(path, "SELECT * FROM review_cards ORDER BY lexeme_id"), before)
            repository_for(workspace)  # a second start changes nothing
            self.assertEqual(_rows(path, "SELECT * FROM review_cards ORDER BY lexeme_id"), before)


if __name__ == "__main__":
    unittest.main()
