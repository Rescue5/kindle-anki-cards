"""B6 core: `export_words` sends the short list to Anki or a file and remembers it only on success."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from short_list_fixture import build_library, lid, word, worth_words

from kindle_vocab_app import anki_connect, contracts, export_cards, settings
from kindle_vocab_app.coded_error import CodedError
from kindle_vocab_app.library_repository import SQLiteVocabularyRepository
from kindle_vocab_app.tauri_bridge import dispatch, error_response
from tests.test_anki_connect import FakeAnki

DEAD_ANKI = "http://127.0.0.1:9"
ROOT = Path(__file__).resolve().parent.parent


def _bridge_env(workspace: Path) -> dict[str, str]:
    return {
        **os.environ,
        "KINDLE_CARDS_WORKSPACE": str(workspace),
        "PYTHONPATH": str(ROOT),
        "PYTHONUTF8": "1",
    }


def _bridge(workspace: Path, action: str, **payload: Any) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "kindle_vocab_app.tauri_bridge"],
        input=json.dumps({"action": action, "payload": payload}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        env=_bridge_env(workspace),
        timeout=30,
        check=False,
    )
    return json.loads(completed.stdout)


def _runs(workspace: Path) -> list[tuple[Any, ...]]:
    path = workspace / ".app-data" / "kindle_cards.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT r.destination, r.scope, r.word_count, i.lexeme_id "
            "FROM export_runs AS r JOIN export_items AS i ON i.run_id = r.id ORDER BY r.id, i.lexeme_id"
        ).fetchall()


def _guids(apkg: Path) -> set[str]:
    with zipfile.ZipFile(apkg) as archive, tempfile.TemporaryDirectory() as temporary:
        collection = Path(archive.extract("collection.anki2", temporary))
        with closing(sqlite3.connect(collection)) as connection:
            return {row[0] for row in connection.execute("SELECT guid FROM notes")}


def _use(workspace: Path, destination: str = "anki", batch: int = 20) -> None:
    settings.save(
        workspace, settings.AppSettings(export_destination=destination, export_batch_size=batch)
    )


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def library(self, words: list[dict[str, Any]]) -> Any:
        return build_library(self.workspace, words)

    def batch(self) -> list[str]:
        return dispatch("load_library", {}, self.workspace)["newBatch"]["ids"]

    def export(self, **payload: Any) -> dict[str, Any]:
        return dispatch("export_words", {"scope": "new", **payload}, self.workspace)

    def failure(self, **payload: Any) -> CodedError:
        with self.assertRaises(CodedError) as caught:
            self.export(**payload)
        return caught.exception


class AnkiExportTests(_Workspace):
    def test_without_anki_the_deck_is_written_and_recorded(self) -> None:
        self.library(worth_words(3))
        _use(self.workspace)
        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            result = self.export()

        self.assertEqual(result["destination"], "anki")
        self.assertEqual(result["exported"], 3)
        self.assertEqual(result["pushed"], 0)
        self.assertTrue(result["path"].endswith(".apkg"))
        self.assertTrue(Path(result["path"]).is_file())
        self.assertEqual(result["message"], "Готово: 3 слова в файле")
        self.assertEqual(len(_guids(Path(result["path"]))), 3)
        rows = _runs(self.workspace)
        self.assertEqual({(r[0], r[1], r[2]) for r in rows}, {("anki", "new", 3)})
        self.assertEqual(result["runId"], "1")
        # The words left the short list.
        self.assertEqual(self.batch(), [])

    def test_with_anki_the_deck_is_pushed(self) -> None:
        anki = FakeAnki()
        self.addCleanup(anki.close)
        self.library(worth_words(2))
        with patch.object(anki_connect, "ANKI_CONNECT_URL", anki.url):
            result = self.export()
        self.assertEqual((result["pushed"], result["path"]), (2, None))
        self.assertEqual(result["message"], "Готово: 2 слова в Anki")
        imports = [call for call in anki.calls if call["action"] == "importPackage"]
        self.assertEqual(len(imports), 1)
        self.assertEqual(len(_runs(self.workspace)), 2)

    def test_a_failed_push_records_nothing_and_a_retry_does_not_duplicate(self) -> None:
        anki = FakeAnki(fail_import=True)
        self.addCleanup(anki.close)
        self.library(worth_words(3))
        before = self.batch()
        with patch.object(anki_connect, "ANKI_CONNECT_URL", anki.url):
            error = self.failure()
            self.assertEqual(error.code, "anki_import_rejected")
            self.assertEqual(str(error), contracts.ERROR_TEXTS["anki_import_rejected"])
            self.assertEqual(_runs(self.workspace), [])
            self.assertEqual(self.batch(), before)
            self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": True})
            failed_files = sorted((self.workspace / ".app-data" / "exports").glob("*.apkg"))
            self.assertEqual(len(failed_files), 1)

            anki.fail_import = False
            result = self.export()

        self.assertEqual(result["pushed"], 3)
        self.assertEqual(len(_runs(self.workspace)), 3)
        self.assertEqual(self.batch(), [])
        # Same words, same note GUIDs: Anki updates its notes instead of adding second ones.
        retry_guids = {
            guid
            for path in (self.workspace / ".app-data" / "exports").glob("*.apkg")
            for guid in _guids(path)
        }
        self.assertEqual(retry_guids, _guids(failed_files[0]))
        self.assertEqual(len(retry_guids), 3)

    def test_lost_import_response_keeps_the_saved_package_and_the_batch(self) -> None:
        anki = FakeAnki()
        self.addCleanup(anki.close)
        anki.drop_import_response = True
        self.library(worth_words(3))
        before = self.batch()
        with patch.object(anki_connect, "ANKI_CONNECT_URL", anki.url):
            error = self.failure()
        self.assertEqual(error_response(error), {
            "ok": False,
            "code": "anki_import_unconfirmed",
            "error": contracts.ERROR_TEXTS["anki_import_unconfirmed"],
        })
        self.assertEqual([call["action"] for call in anki.calls], ["version", "importPackage"])
        self.assertEqual(_runs(self.workspace), [])
        self.assertEqual(self.batch(), before)
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": True})
        package = Path(anki.calls[-1]["params"]["path"])
        self.assertEqual(len(_guids(package)), 3)

    def test_an_unwritable_folder_records_nothing(self) -> None:
        self.library(worth_words(2))
        # A file where the exports folder should be.
        (self.workspace / ".app-data" / "exports").write_text("not a folder", encoding="utf-8")
        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            error = self.failure()
        self.assertEqual(error.code, "export_failed")
        self.assertEqual(_runs(self.workspace), [])
        self.assertEqual(len(self.batch()), 2)
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": False})

    def test_the_card_the_reader_saw_is_the_card_that_is_exported(self) -> None:
        repository = self.library([word("lumena", days=(0, 1, 2))])
        repository.save_card_edit(lid("lumena"), meaning_ru="свой перевод")
        repository.save_card_edit(lid("lumena"), example_occurrence_id="lumena-o0")
        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            result = self.export()
        with zipfile.ZipFile(result["path"]) as archive, tempfile.TemporaryDirectory() as temporary:
            collection = Path(archive.extract("collection.anki2", temporary))
            with closing(sqlite3.connect(collection)) as connection:
                fields = connection.execute("SELECT flds FROM notes").fetchone()[0].split("\x1f")
        self.assertIn("свой перевод", fields)
        self.assertTrue(any(field.endswith("showed up again.") for field in fields))
        self.assertFalse(any("at dusk" in field for field in fields))


class FileExportTests(_Workspace):
    def test_csv_writes_a_tab_separated_file(self) -> None:
        repository = self.library([word("lumena", days=(0, 1)), *worth_words(2, prefix="mist")])
        repository.save_card_edit(lid("lumena"), meaning_ru="свой перевод")
        _use(self.workspace, "csv")
        result = self.export()

        self.assertEqual((result["destination"], result["pushed"], result["exported"]), ("csv", 0, 3))
        self.assertTrue(result["path"].endswith(".tsv"))
        self.assertEqual(result["message"], "Готово: 3 слова в файле")
        with Path(result["path"]).open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file, delimiter="\t"))
        self.assertEqual(len(rows), 3)
        edited = next(row for row in rows if row["Base form"] == "lumena")
        self.assertEqual(edited["Russian meaning(s)"], "свой перевод")
        self.assertEqual(edited["Original context"], "The lumena showed up again at dusk.")
        self.assertEqual({(r[0], r[1]) for r in _runs(self.workspace)}, {("csv", "new")})
        self.assertEqual(self.batch(), [])

    def test_two_exports_in_one_second_keep_their_own_files(self) -> None:
        self.library(worth_words(4))
        _use(self.workspace, "csv", batch=5)
        with patch("kindle_vocab_app.export_cards.datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 19, 12, 0, 0)
            first = self.export(ids=[lid("lumena"), lid("lumenb")])
            second = self.export(ids=[lid("lumenc"), lid("lumend")])
        self.assertNotEqual(first["path"], second["path"])
        for result in (first, second):
            with Path(result["path"]).open(encoding="utf-8", newline="") as file:
                self.assertEqual(len(list(csv.DictReader(file, delimiter="\t"))), 2)
        path = self.workspace / ".app-data" / "kindle_cards.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            recorded = {row[0] for row in connection.execute("SELECT path FROM export_runs")}
        self.assertEqual(recorded, {first["path"], second["path"]})

    def test_tsv_history_failure_keeps_the_file_and_warns_that_retry_creates_another(self) -> None:
        self.library(worth_words(2))
        _use(self.workspace, "csv")
        with patch.object(SQLiteVocabularyRepository, "record_export_run", side_effect=OSError("test write failure")):
            error = self.failure()
        self.assertEqual(error.code, "export_failed")
        self.assertIn("TSV сохранён в папке выгрузок", str(error))
        self.assertIn("При повторе будет создан ещё один файл", str(error))
        self.assertEqual(_runs(self.workspace), [])
        self.assertEqual(len(self.batch()), 2)
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": True})
        self.export()
        self.assertEqual(len(list(export_cards.exports_dir(self.workspace).glob("*.tsv"))), 2)
        self.assertEqual(len(_runs(self.workspace)), 2)

    def test_the_file_is_plain_text_and_a_failed_write_leaves_no_temporary(self) -> None:
        repository = self.library([word("lumena")])
        repository.save_card_edit(lid("lumena"), meaning_ru="свет & тень <b>")
        _use(self.workspace, "csv")
        result = self.export()
        with Path(result["path"]).open(encoding="utf-8", newline="") as file:
            row = next(csv.DictReader(file, delimiter="\t"))
        self.assertEqual(row["Russian meaning(s)"], "свет & тень <b>")

        self.library(worth_words(2, prefix="mist"))
        with patch("kindle_vocab_app.export_cards._tsv_row", side_effect=RuntimeError("boom")):
            self.assertEqual(self.failure().code, "export_failed")
        self.assertEqual(list((self.workspace / ".app-data" / "exports").glob("*.tmp")), [])
        self.assertEqual(len(_runs(self.workspace)), 1)

    def test_csv_failure_records_nothing(self) -> None:
        self.library(worth_words(2))
        _use(self.workspace, "csv")
        (self.workspace / ".app-data" / "exports").write_text("not a folder", encoding="utf-8")
        self.assertEqual(self.failure().code, "export_failed")
        self.assertEqual(_runs(self.workspace), [])

    def test_obsidian_is_not_an_export_destination(self) -> None:
        self.library(worth_words(2))
        _use(self.workspace, "obsidian")
        error = self.failure()
        self.assertEqual(error.code, "no_destination")
        self.assertIn("Obsidian", str(error))
        self.assertEqual(_runs(self.workspace), [])
        self.assertEqual(len(self.batch()), 2)


class ExportFolderTests(_Workspace):
    def test_status_requires_a_nonempty_finished_file(self) -> None:
        folder = export_cards.exports_dir(self.workspace)
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": False})
        self.assertFalse(folder.exists())
        folder.mkdir(parents=True)
        (folder / "empty.apkg").touch()
        (folder / "unfinished.tsv.tmp").write_bytes(b"incomplete")
        (folder / "directory.tsv").mkdir()
        (folder / "unrelated.txt").write_bytes(b"text")
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": False})

        self.library(worth_words(1))
        _use(self.workspace, "csv")
        self.export()
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": True})

    def test_open_uses_only_the_workspace_folder_and_rechecks_missing_files(self) -> None:
        self.library(worth_words(1))
        _use(self.workspace, "csv")
        exported = Path(self.export()["path"])
        with patch("kindle_vocab_app.tauri_bridge._open_local_path") as opener:
            self.assertEqual(dispatch("open_export_folder", {"path": str(self.workspace)}, self.workspace), {"opened": True})
            opener.assert_called_once_with(export_cards.exports_dir(self.workspace))
            opener.reset_mock()

            exported.unlink()
            self.assertEqual(dispatch("open_export_folder", {}, self.workspace), {"opened": False})
            opener.assert_not_called()

    def test_missing_folder_at_launch_returns_false(self) -> None:
        self.library(worth_words(1))
        _use(self.workspace, "csv")
        self.export()
        with patch("kindle_vocab_app.tauri_bridge._open_local_path", side_effect=FileNotFoundError):
            self.assertEqual(dispatch("open_export_folder", {}, self.workspace), {"opened": False})

    def test_saved_files_are_visible_to_new_bridge_processes(self) -> None:
        self.library(worth_words(1))
        _use(self.workspace, "csv")
        self.assertEqual(_bridge(self.workspace, "export_folder_status"), {"ok": True, "result": {"available": False}})
        exported = _bridge(self.workspace, "export_words", scope="new")["result"]
        self.assertEqual(_bridge(self.workspace, "export_folder_status"), {"ok": True, "result": {"available": True}})
        Path(exported["path"]).unlink()
        self.assertEqual(_bridge(self.workspace, "open_export_folder"), {"ok": True, "result": {"opened": False}})


class ConcurrentExportsTests(_Workspace):
    @contextmanager
    def paused_export(self, ids: list[str], *, phase: str) -> Iterator[subprocess.Popen[str]]:
        script = """
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from kindle_vocab_app import export_cards
from kindle_vocab_app.library_repository import SQLiteVocabularyRepository
from kindle_vocab_app.tauri_bridge import dispatch

workspace = Path(os.environ["KINDLE_CARDS_WORKSPACE"])
ready, phase, ids = sys.argv[1:]
target, method = (
    (export_cards, "_write_tsv")
    if phase == "file"
    else (SQLiteVocabularyRepository, "record_export_run")
)
original = getattr(target, method)

def pause(*args, **kwargs):
    Path(ready).touch()
    sys.stdin.readline()
    return original(*args, **kwargs)

with patch.object(target, method, pause):
    print(json.dumps(dispatch("export_words", {"scope": "new", "ids": json.loads(ids)}, workspace)))
"""
        ready = self.workspace / f"export-{phase}-ready"
        with subprocess.Popen(
            [sys.executable, "-u", "-c", script, str(ready), phase, json.dumps(ids)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
            env=_bridge_env(self.workspace),
        ) as child:
            try:
                deadline = time.monotonic() + 20
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.025)
                if child.poll() is not None:
                    _, stderr = child.communicate()
                    self.fail(f"Export subprocess exited before {phase}: {stderr}")
                self.assertTrue(ready.exists(), f"Export subprocess did not reach {phase}")
                yield child
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)

    def test_identical_and_overlapping_requests_recheck_history_under_the_lock(self) -> None:
        self.library(worth_words(3))
        _use(self.workspace, "csv")
        first_ids = [lid("lumena"), lid("lumenb")]
        overlapping_ids = [lid("lumenb"), lid("lumenc")]
        with self.paused_export(first_ids, phase="history") as first:
            self.assertEqual(_runs(self.workspace), [])
            for ids in (first_ids, overlapping_ids):
                with self.subTest(ids=ids):
                    second = _bridge(self.workspace, "export_words", scope="new", ids=ids)
                    self.assertEqual(second, {
                        "ok": False,
                        "code": "export_busy",
                        "error": contracts.ERROR_TEXTS["export_busy"],
                    })
            stdout, stderr = first.communicate(input="commit\n", timeout=20)
            self.assertEqual(first.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)["exported"], 2)

        identical = _bridge(self.workspace, "export_words", scope="new", ids=first_ids)
        self.assertEqual(identical["code"], "nothing_to_export")
        overlapping = _bridge(self.workspace, "export_words", scope="new", ids=overlapping_ids)
        self.assertEqual(overlapping["result"]["exported"], 1)
        folder = export_cards.exports_dir(self.workspace)
        exports = sorted(folder.glob("*.tsv"))
        self.assertEqual(len(exports), 2)
        words = []
        for exported in exports:
            with exported.open(encoding="utf-8", newline="") as stream:
                words.extend(row["Base form"] for row in csv.DictReader(stream, delimiter="\t"))
        self.assertCountEqual(words, ["lumena", "lumenb", "lumenc"])
        self.assertCountEqual([row[3] for row in _runs(self.workspace)], [*first_ids, lid("lumenc")])

    def test_terminating_the_holder_releases_the_lock(self) -> None:
        self.library(worth_words(1))
        _use(self.workspace, "csv")
        ids = [lid("lumena")]
        with self.paused_export(ids, phase="file") as first:
            first.kill()
            first.wait(timeout=10)
        result = _bridge(self.workspace, "export_words", scope="new", ids=ids)
        self.assertEqual(result["result"]["exported"], 1)
        self.assertEqual(len(_runs(self.workspace)), 1)


class SelectionTests(_Workspace):
    def test_the_default_is_the_short_list_cut_at_the_batch_size(self) -> None:
        self.library(worth_words(8))
        _use(self.workspace, "csv", batch=5)
        first = self.batch()
        result = self.export()
        self.assertEqual(result["exported"], 5)
        self.assertEqual({row[3] for row in _runs(self.workspace)}, set(first))
        self.assertEqual(len(self.batch()), 3)

    def test_given_ids_are_narrowed_to_exportable_words_in_rank_order(self) -> None:
        repository = self.library([*worth_words(4), word("faded", days=(60,))])
        repository.set_decision(lid("lumenb"), "skip")
        _use(self.workspace, "csv")
        asked = [lid("lumenc"), lid("faded"), lid("lumenb"), lid("lumena")]
        result = self.export(ids=asked)
        # `faded` is not worth learning and lumenb was answered «не учить»: neither leaves.
        self.assertEqual(result["exported"], 2)
        self.assertEqual([row[3] for row in _runs(self.workspace)], sorted([lid("lumena"), lid("lumenc")]))

    def test_a_decided_word_is_exported_even_when_the_ranking_says_no(self) -> None:
        repository = self.library([word("faded", days=(60,)), *worth_words(1)])
        repository.set_decision(lid("faded"), "learn")
        _use(self.workspace, "csv")
        self.assertEqual(self.export()["exported"], 2)

    def test_exported_words_are_not_sent_twice(self) -> None:
        self.library(worth_words(2))
        _use(self.workspace, "csv")
        self.export()
        _use(self.workspace, "anki")
        self.assertEqual(self.failure().code, "nothing_to_export")
        self.assertEqual(self.failure(ids=[lid("lumena")]).code, "nothing_to_export")
        self.assertEqual(len(_runs(self.workspace)), 2)

    def test_nothing_to_export(self) -> None:
        _use(self.workspace, "csv")
        self.assertEqual(self.failure().code, "nothing_to_export")
        self.library([word("pending", state="pending"), word("faded", days=(60,))])
        self.assertEqual(self.failure().code, "nothing_to_export")
        self.assertEqual(self.failure(ids=[]).code, "nothing_to_export")
        self.assertEqual(_runs(self.workspace), [])

    def test_bad_requests(self) -> None:
        self.library(worth_words(1))
        _use(self.workspace, "csv")
        self.assertEqual(self.failure(scope="again").code, "bad_scope")
        self.assertEqual(self.failure(ids=["no-such-word"]).code, "unknown_lexeme")
        self.assertEqual(_runs(self.workspace), [])


class ErrorEnvelopeTests(unittest.TestCase):
    def test_coded_errors_carry_their_code(self) -> None:
        response = error_response(CodedError("nothing_to_export"))
        self.assertEqual(
            response, {"ok": False, "error": contracts.ERROR_TEXTS["nothing_to_export"], "code": "nothing_to_export"}
        )
        self.assertNotIn("code", error_response(ValueError("plain")))
        self.assertEqual(error_response(ValueError("plain"))["error"], "plain")

    def test_the_bridge_prints_clean_json_with_the_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            response = _bridge(Path(temporary), "export_words", scope="new")
        self.assertEqual(response["ok"], False)
        self.assertEqual(response["code"], "nothing_to_export")
        self.assertEqual(response["error"], contracts.ERROR_TEXTS["nothing_to_export"])


class SettingsTests(unittest.TestCase):
    def test_defaults_and_round_trip(self) -> None:
        defaults = settings.to_dict(settings.AppSettings())
        self.assertEqual((defaults["export_destination"], defaults["export_batch_size"]), ("anki", 20))
        restored = settings.from_dict({**defaults, "export_destination": "csv", "export_batch_size": 50})
        self.assertEqual((restored.export_destination, restored.export_batch_size), ("csv", 50))
        # An old settings file without the keys still loads.
        self.assertEqual(settings.from_dict({"theme": "dark"}).export_batch_size, 20)

    def test_invalid_values_are_refused_in_russian(self) -> None:
        for key, value in (
            ("export_destination", "quizlet"),
            ("export_batch_size", 4),
            ("export_batch_size", 101),
            ("export_batch_size", True),
            ("export_batch_size", "20"),
        ):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "[А-Яа-я]"):
                settings.from_dict({key: value})

    def test_save_settings_through_the_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            saved = dispatch(
                "save_settings",
                {"settings": {"export_destination": "csv", "export_batch_size": 7}},
                workspace,
            )
            self.assertEqual(saved, {"saved": True})
            loaded = dispatch("load_settings", {}, workspace)
            self.assertEqual((loaded["export_destination"], loaded["export_batch_size"]), ("csv", 7))
            with self.assertRaises(ValueError):
                dispatch("save_settings", {"settings": {"export_batch_size": 1000}}, workspace)
            # An older frontend saves without the export keys: they keep their values.
            dispatch("save_settings", {"settings": {"theme": "dark"}}, workspace)
            kept = dispatch("load_settings", {}, workspace)
            self.assertEqual(
                (kept["theme"], kept["export_destination"], kept["export_batch_size"]), ("dark", "csv", 7)
            )


if __name__ == "__main__":
    unittest.main()
