from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from library_fixture import EXPECTED_EXPORT_ITEMS, build_v3_library, lid

from kindle_vocab_app import contracts, library_migrations, vocab_cache
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.tauri_bridge import dispatch

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).with_name("fixtures") / "library_v3_golden.json"
V3_TABLES = (
    "metadata", "lexemes", "forms", "occurrences", "analyses", "processing_queue",
    "destinations", "sync_runs", "review_cards", "enrichments",
)
V4_TABLES = ("word_decisions", "card_edits", "export_runs", "export_items")


def _read(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return [tuple(row) for row in connection.execute(sql, params)]


def _tables(path: Path) -> set[str]:
    return {row[0] for row in _read(path, "SELECT name FROM sqlite_master WHERE type = 'table'")}


def _snapshot(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every v3 table, in a stable order."""
    return {
        table: sorted(_read(path, f"SELECT * FROM {table}"), key=repr) for table in V3_TABLES
    }


def _snapshot_v1(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    return {
        table: sorted(_read(path, f"SELECT * FROM {table}"), key=repr)
        for table in V3_TABLES
        if table not in {"review_cards", "enrichments"}
    }


def _tiny_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE lexemes(id TEXT)")
        connection.commit()


def _version(path: Path) -> int:
    return int(_read(path, "SELECT MAX(version) FROM schema_migrations")[0][0])


def _backups(workspace: Path) -> list[Path]:
    return library_migrations.list_backups(
        workspace / ".app-data" / library_migrations.BACKUP_DIRNAME, "kindle_cards"
    )


def _export_history(path: Path) -> dict[tuple[str, str], set[str]]:
    runs: dict[tuple[str, str], set[str]] = {}
    for destination, created_at, scope, word_count, run_id in _read(
        path, "SELECT destination, created_at, scope, word_count, id FROM export_runs"
    ):
        assert scope == "migrated"
        keys = {
            row[0]
            for row in _read(
                path, "SELECT canonical_key FROM export_items WHERE run_id = ?", (run_id,)
            )
        }
        assert len(keys) == word_count
        runs[(destination, created_at)] = keys
    return runs


def _build_v4_with_export_history(workspace: Path) -> Path:
    path = build_v3_library(workspace)
    with closing(library_migrations.open_connection(path)) as connection, connection:
        library_migrations._to_v4(connection)
        connection.execute("INSERT INTO schema_migrations VALUES (4, 'v4')")
        connection.execute(
            "INSERT INTO export_runs VALUES (40, 'csv', 'again', '2026-11-20', 1, 'words.tsv')"
        )
        connection.execute(
            "INSERT INTO export_items VALUES (40, 'old-lexeme-id', 'en', 'old-form', 1)"
        )
        connection.execute("INSERT INTO export_runs VALUES (50, 'anki', 'new', '2026-11-21', 0, '')")
        connection.execute("DELETE FROM export_runs WHERE id = 50")
    return path


def _raw_export_history(path: Path) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    return (
        _read(path, "SELECT * FROM export_runs ORDER BY id"),
        _read(path, "SELECT * FROM export_items ORDER BY run_id, lexeme_id"),
    )


class LibraryMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_v3_data_survives_and_export_history_is_backfilled(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)
        started = vocab_cache.utc_now()

        repository_for(self.workspace)

        self.assertEqual(_version(path), 5)
        self.assertEqual(_snapshot(path), before)  # review_cards and analyses untouched
        self.assertTrue(set(V4_TABLES) <= _tables(path))
        self.assertNotIn("legacy_review_cards", _tables(path))
        self.assertEqual(_read(path, "SELECT COUNT(*) FROM word_decisions"), [(0,)])
        self.assertEqual(_read(path, "SELECT COUNT(*) FROM card_edits"), [(0,)])
        history = _export_history(path)
        lost = [key for key in history if key[0] == "anki" and key[1] >= started]
        self.assertEqual(len(lost), 1)
        history[("anki", None)] = history.pop(lost[0])  # type: ignore[index]
        self.assertEqual(history, EXPECTED_EXPORT_ITEMS)
        item = _read(
            path,
            "SELECT language, canonical_key, is_repeat FROM export_items WHERE lexeme_id = ?",
            (lid("tarn"),),
        )
        self.assertEqual(item, [("en", "tarn", 0)])
        # Runs are numbered in time order.
        ordered = [row[0] for row in _read(path, "SELECT created_at FROM export_runs ORDER BY id")]
        self.assertEqual(ordered, sorted(ordered))

    def test_backup_is_made_and_verified_before_any_write(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)
        original = library_migrations._apply_steps
        seen: dict[str, Any] = {}

        def inspect_then_apply(connection: sqlite3.Connection, current: int) -> None:
            backups = _backups(self.workspace)
            seen["backups"] = [item.name for item in backups]
            seen["integrity"] = _read(backups[0], "PRAGMA integrity_check")
            seen["backup_version"] = _version(backups[0])
            seen["backup_rows"] = _snapshot(backups[0])
            seen["companions"] = sorted(
                item.name for item in backups[0].parent.iterdir() if item.suffix != ".sqlite3"
            )
            original(connection, current)

        with mock.patch.object(library_migrations, "_apply_steps", inspect_then_apply):
            repository_for(self.workspace)

        self.assertEqual(len(seen["backups"]), 1)
        self.assertRegex(seen["backups"][0], r"^kindle_cards\.v3\.\d{8}T\d{12}Z\.sqlite3$")
        self.assertEqual(seen["integrity"], [("ok",)])
        self.assertEqual(seen["backup_version"], 3)
        self.assertEqual(seen["backup_rows"], before)
        self.assertEqual(seen["companions"], [])  # self-contained, no -wal/-shm

    def test_second_run_is_idempotent(self) -> None:
        path = build_v3_library(self.workspace)
        repository_for(self.workspace)
        after_first = (_snapshot(path), _export_history(path))

        repository_for(self.workspace)

        self.assertEqual((_snapshot(path), _export_history(path)), after_first)
        self.assertEqual(
            _read(path, "SELECT version FROM schema_migrations ORDER BY version"),
            [(1,), (2,), (3,), (5,)],
        )
        self.assertEqual(len(_backups(self.workspace)), 1)

    def test_v4_export_history_survives_first_and_repeated_start_in_new_processes(self) -> None:
        path = _build_v4_with_export_history(self.workspace)
        before = _raw_export_history(path)
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from kindle_vocab_app.library_repository import repository_for\n"
            "repository_for(Path(sys.argv[1]))\n"
        )
        for _ in range(2):
            process = subprocess.run(
                [sys.executable, "-B", "-c", script, str(self.workspace)],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", "replace")[-2000:])
            self.assertEqual(_version(path), 5)
            self.assertEqual(_raw_export_history(path), before)
        [backup] = _backups(self.workspace)
        self.assertEqual(_version(backup), 4)
        self.assertEqual(_raw_export_history(backup), before)
        self.assertEqual(_read(path, "PRAGMA foreign_key_check"), [])
        self.assertIn("idx_export_items_lexeme", {row[1] for row in _read(path, "PRAGMA index_list(export_items)")})

        repository = repository_for(self.workspace)
        quizlet = repository.record_export_run("quizlet", [lid("tarn")])
        remnote = repository.record_export_run("remnote", [lid("tarn")])
        self.assertEqual((quizlet, remnote), (51, 52))
        runs, items = _raw_export_history(path)
        self.assertEqual(runs[:-2], before[0])
        self.assertEqual(items[:-2], before[1])
        self.assertEqual([row[1] for row in runs[-2:]], ["quizlet", "remnote"])
        with closing(library_migrations.open_connection(path)) as connection, connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO export_items VALUES (99, 'missing-run', 'en', 'word', 0)")
            connection.execute("DELETE FROM export_runs WHERE id = ?", (quizlet,))
        self.assertEqual(_raw_export_history(path)[1][:-1], before[1])
        self.assertEqual(_read(path, "PRAGMA foreign_key_check"), [])

    def test_v5_failure_rolls_back_the_rebuild_and_leaves_v4_history_intact(self) -> None:
        path = _build_v4_with_export_history(self.workspace)
        before = _raw_export_history(path)
        original = library_migrations._apply_steps

        def fail_after_rebuild(connection: sqlite3.Connection, current: int) -> None:
            original(connection, current)
            connection.execute("INSERT INTO export_runs VALUES (NULL, 'quizlet', 'new', 't', 0, '')")
            raise RuntimeError("failure after export history rebuild")

        with mock.patch.object(library_migrations, "_apply_steps", fail_after_rebuild), self.assertRaisesRegex(
            ValueError, "копия сохранена"
        ):
            repository_for(self.workspace)

        self.assertEqual(_version(path), 4)
        self.assertEqual(_raw_export_history(path), before)
        self.assertEqual(_read(path, "PRAGMA foreign_key_check"), [])
        self.assertEqual(_read(path, "SELECT seq FROM sqlite_sequence WHERE name = 'export_runs'"), [(50,)])
        self.assertFalse({"export_runs_v5", "export_items_v5"} & _tables(path))
        with closing(library_migrations.open_connection(path)) as connection, self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO export_runs VALUES (NULL, 'quizlet', 'new', 't', 0, '')")

        repository_for(self.workspace)
        self.assertEqual(_version(path), 5)
        self.assertEqual(_raw_export_history(path), before)

    def test_keeps_the_newest_three_backups(self) -> None:
        build_v3_library(self.workspace)
        backup_dir = self.workspace / ".app-data" / "backups"
        backup_dir.mkdir(parents=True)
        for index in range(4):
            old = backup_dir / f"kindle_cards.v3.2026010{index}T000000000000Z.sqlite3"
            _tiny_database(old)
            os.utime(old, (1_700_000_000 + index, 1_700_000_000 + index))
        unrelated = backup_dir / "notes.txt"
        unrelated.write_text("keep", encoding="utf-8")
        # Leftovers of copies cut short: never counted, so they cannot push a
        # real copy out of the window.
        empty = backup_dir / "kindle_cards.v3.20991231T000000000000Z.sqlite3"
        empty.write_bytes(b"")
        partial = backup_dir / "kindle_cards.v3.20991230T000000000000Z.sqlite3"
        partial.write_bytes(b"not a database" * 100)

        repository_for(self.workspace)

        names = [item.name for item in _backups(self.workspace)]
        self.assertEqual(len(names), 3)
        self.assertTrue(names[0].startswith("kindle_cards.v3.2026") and "2026010" not in names[0])
        self.assertEqual(names[1:], [
            "kindle_cards.v3.20260103T000000000000Z.sqlite3",
            "kindle_cards.v3.20260102T000000000000Z.sqlite3",
        ])
        self.assertTrue(unrelated.exists())

    def test_concurrent_initialisation_from_threads_migrates_once(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)
        racers = 6  # more than BACKUPS_KEPT
        barrier = threading.Barrier(racers)

        def open_repository() -> None:
            barrier.wait()
            repository_for(self.workspace)

        with ThreadPoolExecutor(max_workers=racers) as pool:
            futures = [pool.submit(open_repository) for _ in range(racers)]
            for future in futures:
                future.result(timeout=120)  # re-raises any thread's error here

        self.assertEqual(_version(path), 5)
        self.assertEqual(_snapshot(path), before)
        self.assertEqual(_read(path, "SELECT COUNT(*) FROM export_runs"), [(4,)])
        self.assertEqual(_read(path, "SELECT COUNT(*) FROM export_items"), [(6,)])
        self._assert_one_real_v3_backup(before)

    def _assert_one_real_v3_backup(self, before: dict[str, Any]) -> None:
        backups = _backups(self.workspace)
        self.assertEqual(len(backups), 1, [item.name for item in backups])
        self.assertIn(".v3.", backups[0].name)
        self.assertEqual(_version(backups[0]), 3)
        self.assertFalse(set(V4_TABLES) & _tables(backups[0]))
        self.assertEqual(_snapshot(backups[0]), before)
        self.assertEqual(
            sorted(item.name for item in backups[0].parent.iterdir()), [backups[0].name]
        )

    def test_concurrent_initialisation_from_processes_migrates_once(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from kindle_vocab_app.library_repository import repository_for\n"
            "repository_for(Path(sys.argv[1]))\n"
        )
        environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(self.workspace)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(4)
        ]
        results = [process.communicate(timeout=180) for process in processes]

        for process, (_, stderr) in zip(processes, results):
            self.assertEqual(process.returncode, 0, stderr.decode("utf-8", "replace")[-2000:])
        self.assertEqual(_version(path), 5)
        self.assertEqual(_snapshot(path), before)
        self.assertEqual(_read(path, "SELECT COUNT(*) FROM export_runs"), [(4,)])
        self.assertEqual(_read(path, "SELECT COUNT(*) FROM export_items"), [(6,)])
        self._assert_one_real_v3_backup(before)

    def test_failure_mid_migration_rolls_back_and_leaves_v3_intact(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)

        with mock.patch.object(
            library_migrations,
            "_backfill_export_history",
            side_effect=RuntimeError("disk trouble"),
        ), self.assertRaises(ValueError) as raised:
            repository_for(self.workspace)

        self.assertEqual(str(raised.exception), "Не удалось обновить библиотеку; копия сохранена")
        self.assertEqual(_version(path), 3)
        self.assertEqual(_snapshot(path), before)
        self.assertFalse(set(V4_TABLES) & _tables(path))  # created tables rolled back
        self.assertEqual(len(_backups(self.workspace)), 1)

        repository_for(self.workspace)  # the next start completes the migration
        self.assertEqual(_version(path), 5)
        self.assertEqual(_snapshot(path), before)

    def test_backup_failure_stops_before_any_write(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)

        with mock.patch.object(
            library_migrations, "_claim_backup_path", side_effect=OSError("read-only")
        ), self.assertRaises(ValueError) as raised:
            repository_for(self.workspace)

        self.assertIn("библиотека не изменена", str(raised.exception))
        self.assertEqual(_version(path), 3)
        self.assertEqual(_snapshot(path), before)

    def test_a_copy_that_fails_verification_is_removed_and_nothing_written(self) -> None:
        path = build_v3_library(self.workspace)
        before = _snapshot(path)

        with mock.patch.object(
            library_migrations, "_verify_backup", return_value="integrity check failed"
        ), self.assertRaises(ValueError) as raised:
            repository_for(self.workspace)

        self.assertIn("библиотека не изменена", str(raised.exception))
        self.assertEqual(_version(path), 3)
        self.assertEqual(_snapshot(path), before)
        self.assertEqual(list((self.workspace / ".app-data" / "backups").iterdir()), [])

        repository_for(self.workspace)
        self._assert_one_real_v3_backup(before)

    def test_version_one_library_upgrades_through_the_baseline(self) -> None:
        # Versions 1-3 only ever added whole tables (review_cards in 2,
        # enrichments in 3); there were no column changes to replay.
        path = build_v3_library(self.workspace)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("DROP TABLE review_cards")
            connection.execute("DROP TABLE enrichments")
            connection.execute("DELETE FROM schema_migrations WHERE version > 1")
            connection.commit()
        kept = _snapshot_v1(path)

        repository_for(self.workspace)

        self.assertEqual(_version(path), 5)
        self.assertTrue({"review_cards", "enrichments", *V4_TABLES} <= _tables(path))
        self.assertEqual(_snapshot_v1(path), kept)
        self.assertIn(".v1.", _backups(self.workspace)[0].name)

    def test_fresh_database_goes_straight_to_v5_without_backup(self) -> None:
        repository = repository_for(self.workspace)
        path = self.workspace / ".app-data" / "kindle_cards.sqlite3"

        self.assertEqual(_read(path, "SELECT version FROM schema_migrations"), [(5,)])
        self.assertTrue(set(V4_TABLES) | {"lexemes", "review_cards"} <= _tables(path))
        self.assertFalse((self.workspace / ".app-data" / "backups").exists())
        self.assertEqual(_read(path, "PRAGMA journal_mode")[0][0].casefold(), "wal")
        self.assertEqual(repository.record_export_run("quizlet", []), 1)
        self.assertEqual(repository.record_export_run("remnote", []), 2)
        self.assertEqual(_read(path, "SELECT destination FROM export_runs ORDER BY id"), [("quizlet",), ("remnote",)])

    def test_legacy_json_never_replaces_an_existing_sqlite_library(self) -> None:
        path = build_v3_library(self.workspace)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("DELETE FROM metadata WHERE key = 'legacy_migration_completed'")
            connection.commit()
        before = _snapshot(path)["lexemes"]
        legacy = self.workspace / ".app-data" / vocab_cache.CACHE_FILENAME
        legacy.write_text(json.dumps(vocab_cache.empty_catalog()), encoding="utf-8")

        repository_for(self.workspace)

        self.assertEqual(_snapshot(path)["lexemes"], before)

    def test_legacy_json_rechecks_the_library_inside_the_replacing_transaction(self) -> None:
        # The marker is missing and the library looks empty when the app
        # starts; a sync from another process commits words before the legacy
        # catalog is written. Those words must survive.
        legacy = self.workspace / ".app-data" / vocab_cache.CACHE_FILENAME
        legacy.parent.mkdir(parents=True)
        legacy.write_text(json.dumps(vocab_cache.empty_catalog()), encoding="utf-8")
        path = self.workspace / ".app-data" / "kindle_cards.sqlite3"
        library_migrations.migrate(path)
        original_load = vocab_cache.load

        def load_after_a_concurrent_sync(workspace: Path) -> Any:
            with closing(sqlite3.connect(path)) as other:
                other.execute(
                    "INSERT INTO lexemes VALUES"
                    " ('x', 'en', 'tarn', 'tarn', 'new', 't', 't', 's', 1, 0)"
                )
                other.commit()
            return original_load(workspace)

        with mock.patch.object(vocab_cache, "load", load_after_a_concurrent_sync):
            repository_for(self.workspace)

        self.assertEqual(_read(path, "SELECT canonical_key FROM lexemes"), [("tarn",)])
        marker = "SELECT 1 FROM metadata WHERE key = 'legacy_migration_completed'"
        self.assertEqual(len(_read(path, marker)), 1)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<volatile>" if key == "checked_at" else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


_V4_LIBRARY_KEYS = (
    "rankingVersion", "rankingMode", "historyDays", "repeatSignal", "shelves", "newBatch",
    "disputed", "again", "studyPrioritySource",
)
_V4_ENTRY_KEYS = ("ranking", "study_priority", "decision", "card", "export", "is_new")


def _without_v4(library: dict[str, Any]) -> dict[str, Any]:
    """The golden file predates the short-list parts; every old field must still be there unchanged."""
    return {
        **{key: value for key, value in library.items() if key not in _V4_LIBRARY_KEYS},
        "entries": [
            {key: value for key, value in entry.items() if key not in _V4_ENTRY_KEYS}
            for entry in library["entries"]
        ],
    }


class BulkCatalogGoldenTests(unittest.TestCase):
    """`load_catalog` output was captured with the per-lexeme queries before the
    bulk rewrite; the rewrite (and the v4 migration) must not change a byte."""

    def test_load_catalog_and_load_library_match_the_golden_payload(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_v3_library(workspace)
            repository = repository_for(workspace)

            catalog = repository.load_catalog()
            library = dispatch("load_library", {}, workspace)

        self.assertEqual(json.loads(json.dumps(catalog)), golden["load_catalog"])
        self.assertEqual(
            json.loads(json.dumps(_scrub(_without_v4(library)))), golden["load_library"]
        )
        # The same migrated library also carries a valid short-list payload.
        self.assertEqual(library["studyPrioritySource"], "legacy")
        self.assertEqual(contracts.validate_library(library), [])

    def test_load_catalog_uses_a_fixed_number_of_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            build_v3_library(workspace)
            repository = repository_for(workspace)
            statements: list[str] = []
            original = repository.connect

            @contextmanager
            def traced() -> Iterator[sqlite3.Connection]:
                with original() as connection:
                    connection.set_trace_callback(statements.append)
                    yield connection

            with mock.patch.object(repository, "connect", traced):
                catalog = repository.load_catalog()

        selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
        self.assertEqual(len(catalog["lexemes"]), 7)
        self.assertEqual(len(selects), 7)

    def test_load_catalog_reads_one_snapshot_while_another_process_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            path = build_v3_library(workspace)
            repository = repository_for(workspace)
            expected = repository.load_catalog()
            original = repository.connect
            fired: list[bool] = []

            def commit_elsewhere(statement: str) -> None:
                # Between the forms and occurrences queries another process
                # replaces part of the catalog: one word gone, one word added.
                if fired or "FROM occurrences" not in statement:
                    return
                fired.append(True)
                with closing(sqlite3.connect(path, timeout=10)) as other:
                    other.execute("PRAGMA foreign_keys = ON")
                    other.execute("DELETE FROM lexemes WHERE canonical_key = 'lantern'")
                    other.execute(
                        "INSERT INTO lexemes VALUES ('late', 'en', 'late', 'late', 'new',"
                        " '2026-01-01', '2026-01-01', 's', 1, 0)"
                    )
                    other.commit()

            @contextmanager
            def traced() -> Iterator[sqlite3.Connection]:
                with original() as connection:
                    connection.set_trace_callback(commit_elsewhere)
                    yield connection

            with mock.patch.object(repository, "connect", traced):
                during = repository.load_catalog()
            after = repository.load_catalog()

        self.assertEqual(fired, [True])
        self.assertEqual(during, expected)
        changed = {item["lemma"] for item in after["lexemes"]} ^ {
            item["lemma"] for item in expected["lexemes"]
        }
        self.assertEqual(changed, {"lantern", "late"})


if __name__ == "__main__":
    unittest.main()
