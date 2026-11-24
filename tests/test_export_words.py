"""B6 core: `export_words` sends the short list to Anki or a file and remembers it only on success."""

from __future__ import annotations

import base64
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from short_list_fixture import build_library, letters, lid, word, worth_words

from kindle_vocab_app import (
    anki_connect,
    anki_export,
    book_coverage,
    contracts,
    export_cards,
    library_view,
    reader_sources,
    settings,
    vocab_cache,
)
from kindle_vocab_app.coded_error import CodedError
from kindle_vocab_app.library_repository import SQLiteVocabularyRepository
from kindle_vocab_app.tauri_bridge import dispatch, error_response
from tests.test_anki_connect import FakeAnki
from tests.test_reader_sources import _koreader_db

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
        input=json.dumps({"action": action, "payload": payload}, ensure_ascii=False),
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


def _note_mod(apkg: Path) -> int:
    with zipfile.ZipFile(apkg) as archive, tempfile.TemporaryDirectory() as temporary:
        collection = Path(archive.extract("collection.anki2", temporary))
        with closing(sqlite3.connect(collection)) as connection:
            return connection.execute("SELECT mod FROM notes").fetchone()[0]


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
        self.library([word("lumena", days=(0, 1, 2))])
        edit = _bridge(
            self.workspace, "save_card_edit", lexeme_id=lid("lumena"),
            meaning_ru="  свой\t перевод  ", example_occurrence_id="lumena-o0",
        )
        self.assertTrue(edit["ok"], edit)
        card = edit["result"]["entry"]["card"]
        self.assertEqual(card, {
            "meaning_ru": "свой перевод", "meaning_source": "edited", "example_occurrence_id": "lumena-o0", "edited": True,
        })
        reloaded = _bridge(self.workspace, "load_library")["result"]
        self.assertEqual(reloaded["entries"][0]["card"], card)
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
        self.library([word("lumena", days=(0, 1)), *worth_words(2, prefix="mist")])
        dispatch("save_card_edit", {
            "lexeme_id": lid("lumena"), "meaning_ru": "свой перевод", "example_occurrence_id": "lumena-o0",
        }, self.workspace)
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
        self.assertEqual(edited["Original context"], "The lumena showed up again.")
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

    def test_more_than_one_hundred_ids_are_rechecked_against_current_decisions_and_history(self) -> None:
        ordinary = [word(f"river{letters(index)}") for index in range(104)]
        rejected = word("manual", state="rejected", warnings=["possibly_glued_words"])
        pending = word("pending", state="pending")
        repository = self.library([*ordinary, rejected, pending])
        _use(self.workspace, "csv")
        before = dispatch("load_library", {}, self.workspace)["newBatch"]
        self.assertEqual(len(before["availableIds"]), 104)
        self.assertEqual(before["ids"], before["availableIds"][:20])

        skipped, previously_exported = before["availableIds"][:2]
        repository.set_decision(skipped, "skip")
        repository.record_export_run("csv", [previously_exported])
        repository.set_decision(pending["id"], "learn")
        learned = dispatch("set_decision", {"lexeme_id": rejected["id"], "decision": "learn"}, self.workspace)
        expected = learned["newBatch"]["availableIds"]
        self.assertEqual(set(expected), (set(before["availableIds"]) - {skipped, previously_exported}) | {rejected["id"]})

        asked = [*reversed(before["availableIds"]), skipped, rejected["id"], pending["id"]]
        run = self.export(ids=asked)
        self.assertEqual(run["exported"], 103)
        lemmas = {entry["id"]: entry["lemma"] for entry in [*ordinary, rejected]}
        with Path(run["path"]).open(encoding="utf-8", newline="") as file:
            self.assertEqual([row["Base form"] for row in csv.DictReader(file, delimiter="\t")], [lemmas[i] for i in expected])
        self.assertEqual(self.failure(ids=asked).code, "nothing_to_export")

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


class BookCoverageExportTests(_Workspace):
    def test_bridge_uses_one_coverage_order_for_library_decisions_and_new_exports(self) -> None:
        phrase = word("take")
        phrase["display_form"] = "take off"
        phrase["forms"] = ["take off"]
        inflected = word("choose")
        inflected["display_form"] = "chose"
        inflected["forms"] = ["chose"]
        inflected["occurrences"] = []
        inflected["processing"]["analysis"] = {"base_form": "choose"}
        words = [
            word("recent"), word("walked", state="rejected"), word("?!", state="rejected"),
            word("pending", state="pending"), phrase, inflected,
        ]
        repository = self.library(words)
        _use(self.workspace, "csv", batch=5)
        for item in words[1:]:
            repository.set_decision(item["id"], "learn")
        legacy = _bridge(self.workspace, "load_library")["result"]
        self.assertEqual(legacy["studyPrioritySource"], "legacy")

        path = book_coverage.model_path(self.workspace)
        path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(
                f"""
                PRAGMA user_version = {book_coverage.SCHEMA_VERSION};
                CREATE TABLE provenance (source_sha256 TEXT);
                CREATE TABLE coverage (headword TEXT PRIMARY KEY, share REAL);
                CREATE TABLE aliases (spelling TEXT PRIMARY KEY, headword TEXT);
                INSERT INTO coverage VALUES ('recent', .02), ('walk', .55), ('take', .95),
                    ('choose', .20), ('chose', .90), ('pending', .95);
                INSERT INTO aliases VALUES ('walked', 'walk');
                """
            )
            connection.execute("INSERT INTO provenance VALUES (?)", (book_coverage.SOURCE_SHA256,))

        snapshot = _bridge(self.workspace, "load_library")["result"]
        self.assertEqual(snapshot["studyPrioritySource"], "rp-v2-personal")
        self.assertEqual(snapshot["rankingVersion"], legacy["rankingVersion"])
        self.assertEqual(snapshot["shelves"], legacy["shelves"])
        priorities = {entry["lemma"]: entry["study_priority"] for entry in snapshot["entries"]}
        self.assertEqual(
            {key: (value["level"], value["provisional"]) for key, value in priorities.items()},
            {"recent": (7, False), "walked": (2, False), "?!": (10, False),
             "pending": (6, True), "take": (6, True), "choose": (4, False)},
        )
        self.assertIn("выражения", priorities["take"]["reason"])
        self.assertEqual(priorities["walked"]["coverage_score"], 0.55)
        expected = ["walked", "choose", "recent", "take", "?!"]
        self.assertEqual(snapshot["newBatch"]["availableIds"], [lid(item) for item in expected])
        self.assertNotEqual(snapshot["newBatch"]["availableIds"], legacy["newBatch"]["availableIds"])
        changed = _bridge(self.workspace, "set_decision", lexeme_id=lid("walked"), decision="skip")["result"]
        self.assertEqual(changed["studyPrioritySource"], "rp-v2-personal")
        self.assertEqual(changed["entry"]["study_priority"], priorities["walked"])
        self.assertEqual(changed["newBatch"]["availableIds"], [lid(item) for item in expected[1:]])
        missing = _bridge(self.workspace, "export_words", scope="library")
        self.assertEqual(missing["code"], "nothing_to_export")
        explicit = _bridge(
            self.workspace, "export_words", scope="new",
            ids=[lid(item) for item in ["?!", "recent", "walked"]],
        )["result"]
        with Path(explicit["path"]).open(encoding="utf-8", newline="") as file:
            self.assertEqual([row["Base form"] for row in csv.DictReader(file, delimiter="\t")], ["recent", "?!"])
        run = _bridge(self.workspace, "export_words", scope="new")["result"]
        with Path(run["path"]).open(encoding="utf-8", newline="") as file:
            self.assertEqual([row["Base form"] for row in csv.DictReader(file, delimiter="\t")], ["choose", "take"])
        full = _bridge(
            self.workspace, "export_words", scope="library", levels=[2, 4, 10],
            ids=[lid(item) for item in ["?!", "recent", "walked", "choose"]],
        )["result"]
        with Path(full["path"]).open(encoding="utf-8", newline="") as file:
            self.assertEqual(
                [row["Base form"] for row in csv.DictReader(file, delimiter="\t")],
                ["?!", "walked", "choose"],
            )

    def test_personal_lookup_filter_keeps_old_forms_and_requires_the_whole_expression(self) -> None:
        lookup = word("choose")["occurrences"][0]
        self.assertTrue(library_view.is_personal_lookup({**lookup, "word": "chose"}, "choose"))
        self.assertTrue(library_view.is_personal_lookup({**lookup, "word": " Take  Off "}, "take off"))
        for invalid in (
            {"source": "legacy"}, {"source": "obsidian"}, {"source": "kobo"},
            {"book_key": ""}, {"book_key": "kobo:other"}, {"book_key": "KOReader:other"},
            {"id": "koreader:choose:1"}, {"id": "kobo:choose:1", "book_key": "unmarked"},
            {"lookup_id": "kobo:choose:1"}, {"looked_up_at": "invalid"}, {"word": "choose from"},
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(library_view.is_personal_lookup({**lookup, **invalid}, "choose"))
        for component in ("take", "off", "take in"):
            self.assertFalse(library_view.is_personal_lookup({**lookup, "word": component}, "take off"))

    def test_personal_priority_ignores_unmarked_koreader_reimports(self) -> None:
        lexeme = word("choose", days=(0, 1, 3))
        for occurrence in lexeme["occurrences"]:
            occurrence["word"] = "chose"
        self.library([lexeme, word("unmeasured", days=(0, 2))])
        model_path = book_coverage.model_path(self.workspace)
        model_path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(model_path)) as connection, connection:
            connection.executescript(f"""
                PRAGMA user_version = {book_coverage.SCHEMA_VERSION};
                CREATE TABLE provenance (source_sha256 TEXT);
                CREATE TABLE coverage (headword TEXT PRIMARY KEY, share REAL);
                CREATE TABLE aliases (spelling TEXT PRIMARY KEY, headword TEXT);
                INSERT INTO coverage VALUES ('choose', .20);
            """)
            connection.execute("INSERT INTO provenance VALUES (?)", (book_coverage.SOURCE_SHA256,))
        before = dispatch("load_library", {}, self.workspace)
        entries = {item["lemma"]: item for item in before["entries"]}
        self.assertEqual(before["studyPrioritySource"], "rp-v2-personal")
        priority = entries["choose"]["study_priority"]
        self.assertEqual(priority["coverage_score"], 0.20)
        self.assertGreater(priority["score"], 0.20)
        provisional = entries["unmeasured"]["study_priority"]
        self.assertEqual((provisional["level"], provisional["provisional"], provisional["coverage_score"]), (6, True, None))
        self.assertGreater(provisional["score"], 0)
        self.assertEqual(contracts.validate_library(before), [])
        compact_reason = priority["personal_reason"]
        self.assertTrue(compact_reason.strip())
        try:
            priority["personal_reason"] = "Поиски в разные дни."
            self.assertEqual(contracts.validate_library(before), [])
            for invalid_reason in ("", "   ", None, 1):
                with self.subTest(invalid_reason=invalid_reason):
                    priority["personal_reason"] = invalid_reason
                    self.assertIn(
                        f"entry {entries['choose']['id']}.study_priority.personal_reason: expected a non-empty string",
                        contracts.validate_library(before),
                    )
        finally:
            priority["personal_reason"] = compact_reason

        reader_path = self.workspace / "reader.sqlite"
        with closing(_koreader_db(reader_path)) as connection, connection:
            connection.execute("UPDATE vocabulary SET word = 'choose', title_id = NULL")
        payload = {"file_name": reader_path.name, "data_base64": base64.b64encode(reader_path.read_bytes()).decode()}
        imported = dispatch("import_reader_file", payload, self.workspace)
        repeated = dispatch("import_reader_file", payload, self.workspace)
        imported_choose = next(item for item in imported["entries"] if item["lemma"] == "choose")
        repeated_choose = next(item for item in repeated["entries"] if item["lemma"] == "choose")
        self.assertEqual(len(imported_choose["occurrences"]), 4)
        self.assertEqual(repeated["imported"]["new_words"], 0)
        self.assertEqual(repeated_choose["occurrences"], imported_choose["occurrences"])
        self.assertEqual(repeated_choose["study_priority"], priority)


class LibraryScopeTests(_Workspace):
    def test_tsv_exports_the_explicit_snapshot_including_every_status_and_decision(self) -> None:
        words = [word("skip"), word("known"), word("?!", state="rejected"),
                 word("pending", state="pending"), word("failed", state="failed"), word("ready")]
        repository = self.library(words)
        _use(self.workspace, "csv")
        repository.set_decision(lid("skip"), "skip")
        repository.set_decision(lid("known"), "known")
        repository.record_export_run("csv", [lid("ready")])
        decisions = repository.load_decisions()
        catalog = repository.load_catalog()
        catalog["lexemes"].append(word("later"))
        repository.save_catalog(catalog)

        asked = {"scope": "library", "ids": [*[option["id"] for option in words], lid("known")]}
        run = self.export(**asked)
        self.assertEqual(run["exported"], len(words))
        with Path(run["path"]).open(encoding="utf-8", newline="") as file:
            self.assertEqual([row["Base form"] for row in csv.DictReader(file, delimiter="\t")], [item["lemma"] for item in words])
        self.assertNotIn(lid("later"), {item[-1] for item in _runs(self.workspace)})
        self.assertEqual(repository.load_decisions(), decisions)
        with repository.connect() as connection:
            rows = connection.execute(
                "SELECT lexeme_id, is_repeat FROM export_items WHERE run_id = ?", (run["runId"],),
            )
            self.assertEqual({row["lexeme_id"]: row["is_repeat"] for row in rows}, {
                item["id"]: int(item["id"] == lid("ready")) for item in words
            })
            self.assertEqual(connection.execute("SELECT scope FROM export_runs WHERE id = ?", (run["runId"],)).fetchone()[0], "again")

    def test_current_levels_are_rechecked_without_adding_newly_matching_words(self) -> None:
        repository = self.library([word("changed", state="pending"), word("stays", state="pending")])
        _use(self.workspace, "csv")
        selection = [entry["id"] for entry in dispatch("load_library", {}, self.workspace)["entries"]]
        catalog = repository.load_catalog()
        catalog["lexemes"] = [word("changed"), word("stays", state="pending"), word("newpending", state="pending")]
        repository.save_catalog(catalog)
        result = self.export(scope="library", ids=selection, levels=[6])
        self.assertEqual(result["exported"], 1)
        self.assertEqual([row[-1] for row in _runs(self.workspace)], [lid("stays")])
        self.assertEqual(self.failure(scope="library", ids=[lid("changed")], levels=[10]).code, "nothing_to_export")

    def test_library_repeat_attempt_reuses_anki_guid_and_current_card(self) -> None:
        repository = self.library([word("lumena", days=(0, 1))])
        anki = FakeAnki(fail_import=True)
        self.addCleanup(anki.close)
        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            original = self.export()
        lexeme_id = lid("lumena")
        repository.save_card_edit(lexeme_id, meaning_ru="новый перевод", example_occurrence_id="lumena-o0")
        before = _runs(self.workspace)
        with patch.object(anki_connect, "ANKI_CONNECT_URL", anki.url):
            self.assertEqual(self.failure(scope="library", ids=[lexeme_id]).code, "anki_import_rejected")
            self.assertEqual(_runs(self.workspace), before)
            failed_path = Path(anki.calls[-1]["params"]["path"])
            anki.fail_import = False
            sent = self.export(scope="library", ids=[lexeme_id])
        self.assertEqual((sent["pushed"], sent["path"]), (1, None))
        repeated_path = Path(anki.calls[-1]["params"]["path"])
        self.assertEqual(_guids(repeated_path), _guids(failed_path))
        self.assertEqual(_guids(repeated_path), _guids(Path(original["path"])))
        with zipfile.ZipFile(repeated_path) as archive, tempfile.TemporaryDirectory() as temporary:
            collection = Path(archive.extract("collection.anki2", temporary))
            with closing(sqlite3.connect(collection)) as connection:
                tags, fields = connection.execute("SELECT tags, flds FROM notes").fetchone()
        self.assertIn("повтор", tags.split())
        self.assertIn("новый перевод", fields)
        self.assertNotIn("at dusk", fields)
        self.assertEqual([row[1] for row in _runs(self.workspace)], ["new", "again"])

    def test_same_second_repeat_uses_a_later_note_mod_from_export_history(self) -> None:
        repository = self.library(worth_words(1))
        lexeme_id = lid("lumena")
        now = 1_780_000_000.25
        stamp = datetime.fromtimestamp(now, UTC).isoformat()
        with (
            patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI),
            patch.object(anki_export, "time", side_effect=[now, now, now + 1]),
            patch.object(anki_export, "sleep") as sleep,
            patch("kindle_vocab_app.library_state.utc_now", return_value=stamp),
        ):
            first = self.export()
            repository.save_card_edit(lexeme_id, meaning_ru="исправленный перевод")
            second = self.export(scope="library", ids=[lexeme_id])
        sleep.assert_called_once_with(0.75)
        self.assertEqual(_note_mod(Path(first["path"])), int(now))
        self.assertEqual(_note_mod(Path(second["path"])), int(now) + 1)
        self.assertEqual(_guids(Path(first["path"])), _guids(Path(second["path"])))

    def test_same_second_retry_also_waits_for_an_unconfirmed_package(self) -> None:
        self.library(worth_words(1))
        anki = FakeAnki()
        self.addCleanup(anki.close)
        anki.drop_import_response = True
        now = 1_780_000_000.25
        with (
            patch.object(anki_connect, "ANKI_CONNECT_URL", anki.url),
            patch.object(anki_export, "time", side_effect=[now, now, now + 1]),
            patch.object(anki_export, "sleep") as sleep,
        ):
            request = {"scope": "library", "ids": [lid("lumena")]}
            self.assertEqual(self.failure(**request).code, "anki_import_unconfirmed")
            self.assertEqual(_runs(self.workspace), [])
            first = Path(anki.calls[-1]["params"]["path"])
            os.utime(first, (now, now))
            anki.drop_import_response = False
            self.assertEqual(self.export(**request)["pushed"], 1)
            retry = Path(anki.calls[-1]["params"]["path"])
        sleep.assert_called_once_with(0.75)
        self.assertEqual(_note_mod(retry), _note_mod(first) + 1)

    def test_package_clock_never_waits_for_future_history_or_advances_wall_time(self) -> None:
        now = 1_780_000_000.25
        with patch.object(anki_export, "time", return_value=now), patch.object(anki_export, "sleep") as sleep:
            self.assertEqual(anki_export._package_timestamp({int(now) + 300}), now)
            sleep.assert_not_called()
        with (
            patch.object(anki_export, "time", side_effect=[now, now - 300]),
            patch.object(anki_export, "sleep") as sleep,
        ):
            self.assertEqual(anki_export._package_timestamp({int(now)}), now - 300)
            sleep.assert_called_once_with(0.75)

    def test_preliminary_note_keeps_its_guid_after_processing_and_reimport(self) -> None:
        reader_path = self.workspace / "reader.sqlite"
        with closing(_koreader_db(reader_path)) as connection:
            connection.execute("UPDATE vocabulary SET word='chose', prev_context='She ', next_context=' a book from the shelf.'")
            connection.commit()
        payload = {"file_name": reader_path.name, "data_base64": base64.b64encode(reader_path.read_bytes()).decode()}
        [old] = dispatch("import_reader_file", payload, self.workspace)["entries"]
        self.assertEqual(old["processing"]["state"], "pending")
        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            first = self.export(scope="library", ids=[old["id"]])
            dispatch("process_queue", {}, self.workspace)
            [current] = dispatch("import_reader_file", payload, self.workspace)["entries"]
            self.assertEqual(current["lemma"], "choose")
            self.assertNotEqual(current["id"], old["id"])
            dispatch("save_card_edit", {"lexeme_id": current["id"], "meaning_ru": "выбирать"}, self.workspace)
            second = self.export(scope="library", ids=[current["id"]])
        self.assertEqual(_guids(Path(second["path"])), _guids(Path(first["path"])))
        with zipfile.ZipFile(second["path"]) as archive, tempfile.TemporaryDirectory() as temporary:
            collection = Path(archive.extract("collection.anki2", temporary))
            with closing(sqlite3.connect(collection)) as connection:
                fields = connection.execute("SELECT flds FROM notes").fetchone()[0].split("\x1f")
        self.assertEqual(fields[anki_export.FIELDS.index("LexemeId")], current["id"])
        self.assertEqual(fields[anki_export.FIELDS.index("Meaning")], "выбирать")
        self.assertEqual([row[-1] for row in _runs(self.workspace)], [current["id"], current["id"]])

    def test_rekey_recovers_a_guid_from_preexisting_anki_history(self) -> None:
        old = word("chose", state="pending")
        repository = self.library([old])
        previous = anki_export.write_apkg([old], self.workspace / "legacy.apkg", require_eligible=False)
        repository.record_export_run("anki", [old["id"]], path=str(previous.path))
        catalog = repository.load_catalog()
        [current] = catalog["lexemes"]
        current.update(lemma="choose", processing=word("choose")["processing"])
        repository.save_processed_lexeme(catalog, old["id"])
        repository.save_catalog(repository.load_catalog())

        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            repeated = self.export(scope="library", ids=[lid("choose")])
        self.assertEqual(_guids(Path(repeated["path"])), _guids(previous.path))

    def test_merge_keeps_the_surviving_forms_note_and_never_reuses_the_retired_guid(self) -> None:
        old = word("chose", state="pending")
        keeper = word("choose")
        repository = self.library([old, keeper])
        # Neither package had a reserved key when an older bridge first wrote it.
        old_package = anki_export.write_apkg([old], self.workspace / "old.apkg", require_eligible=False)
        keeper_package = anki_export.write_apkg([keeper], self.workspace / "keeper.apkg")
        repository.record_export_run("anki", [old["id"]], path=str(old_package.path))
        repository.record_export_run("anki", [keeper["id"]], path=str(keeper_package.path))
        catalog = repository.load_catalog()
        source = next(entry for entry in catalog["lexemes"] if entry["id"] == old["id"])
        source.update(lemma="choose", processing=keeper["processing"])
        self.assertTrue(repository.save_processed_lexeme(catalog, old["id"]))

        with patch.object(anki_connect, "ANKI_CONNECT_URL", DEAD_ANKI):
            repeated = self.export(scope="library", ids=[keeper["id"]])
            self.assertEqual(_guids(Path(repeated["path"])), _guids(keeper_package.path))
            restored_catalog = repository.load_catalog()
            restored_catalog["lexemes"].append(old)
            repository.save_catalog(restored_catalog)
            separate = self.export(scope="library", ids=[old["id"]])
        self.assertTrue(_guids(Path(separate["path"])).isdisjoint(_guids(old_package.path) | _guids(keeper_package.path)))

    def test_invalid_or_empty_library_selections_fail_before_export(self) -> None:
        self.library(worth_words(1))
        ids = [lid("lumena")]
        for levels in ([], [True], [0], [11], [1, 1], "all", None):
            with self.subTest(levels=levels):
                self.assertEqual(self.failure(scope="library", ids=ids, levels=levels).code, "bad_levels")
        for scope in ("", "again", "other", None):
            with self.subTest(scope=scope):
                self.assertEqual(self.failure(scope=scope, ids=ids).code, "bad_scope")
        self.assertEqual(self.failure(scope="library").code, "nothing_to_export")
        self.assertEqual(self.failure(scope="library", ids=[]).code, "nothing_to_export")
        self.assertEqual(self.failure(scope="library", ids=[*ids, "stale-unknown"]).code, "unknown_lexeme")
        self.assertEqual(self.failure(scope="library", ids=[""]).code, "unknown_lexeme")
        _use(self.workspace, "obsidian")
        self.assertEqual(self.failure(scope="library", ids=ids).code, "no_destination")
        self.assertEqual(_runs(self.workspace), [])
        self.assertEqual(dispatch("export_folder_status", {}, self.workspace), {"available": False})


class ReaderActionsTests(_Workspace):
    def test_utf8_translation_survives_system_code_page_and_restart(self) -> None:
        build_library(self.workspace, [word("glimpse")])
        meaning = "мимолётное впечатление"
        with patch.dict(os.environ, {"PYTHONIOENCODING": "cp1251"}):
            saved = _bridge(self.workspace, "save_card_edit", lexeme_id=lid("glimpse"), meaning_ru=meaning)
            self.assertTrue(saved["ok"], saved)
            self.assertEqual(saved["result"]["entry"]["card"]["meaning_ru"], meaning)
            reopened = _bridge(self.workspace, "load_library")
        self.assertEqual(reopened["result"]["entries"][0]["card"]["meaning_ru"], meaning)

    def test_decision_refreshes_short_list_and_stale_ids_do_not_export_skipped_word(self) -> None:
        repository = self.library(worth_words(2))
        _use(self.workspace, "csv")
        lexeme_id = lid("lumena")
        before = dispatch("load_library", {}, self.workspace)
        [original] = [entry for entry in before["entries"] if entry["id"] == lexeme_id]
        old_ids = before["newBatch"]["ids"]
        saved = _bridge(self.workspace, "set_decision", lexeme_id=lexeme_id, decision="skip")
        self.assertTrue(saved["ok"], saved)
        result = saved["result"]
        self.assertEqual(result["entry"]["decision"]["value"], "skip")
        self.assertEqual(result["entry"]["ranking"]["shelf"], "not_worth")
        self.assertEqual(result["shelves"]["not_worth"], 1)
        self.assertEqual(result["newBatch"], {"count": 1, "ids": [lid("lumenb")], "availableIds": [lid("lumenb")]})
        self.assertEqual(result["disputed"], before["disputed"])
        self.assertEqual(result["again"], before["again"])
        decision = repository.load_decisions()[lexeme_id]
        self.assertEqual(decision["score_at"], original["ranking"]["score"])
        self.assertEqual(decision["shelf_at"], original["ranking"]["shelf"])
        self.assertEqual(decision["ranking_version"], original["ranking"]["version"])

        self.assertEqual(self.failure(ids=[lexeme_id]).code, "nothing_to_export")
        exported = self.export(ids=old_ids)
        self.assertEqual(exported["exported"], 1)
        self.assertEqual([row[-1] for row in _runs(self.workspace)], [lid("lumenb")])

        cleared = _bridge(self.workspace, "set_decision", lexeme_id=lexeme_id, decision=None)
        self.assertTrue(cleared["ok"], cleared)
        self.assertIsNone(cleared["result"]["entry"]["decision"])
        self.assertEqual(cleared["result"]["entry"]["ranking"], original["ranking"])
        self.assertEqual(cleared["result"]["newBatch"], {"count": 1, "ids": [lexeme_id], "availableIds": [lexeme_id]})

    def test_card_patch_validation_and_reset(self) -> None:
        self.library([word("lumena", days=(0, 1)), word("mist")])
        lexeme_id = lid("lumena")
        dispatch("save_card_edit", {
            "lexeme_id": lexeme_id, "meaning_ru": "правка", "example_occurrence_id": "lumena-o0",
        }, self.workspace)
        invalid = _bridge(self.workspace, "save_card_edit", lexeme_id=lexeme_id,
                          meaning_ru="другая правка", example_occurrence_id="mist-o0")
        self.assertEqual(invalid["code"], "example_not_found")
        for action, payload, code in (
            ("save_card_edit", {"lexeme_id": lexeme_id, "meaning_ru": "я" * 201}, "too_long"),
            ("set_decision", {"lexeme_id": lexeme_id, "decision": []}, "bad_decision"),
            ("set_decision", {"lexeme_id": lexeme_id}, "bad_decision"),
            ("save_card_edit", {"lexeme_id": "missing", "meaning_ru": "правка"}, "unknown_lexeme"),
        ):
            with self.subTest(action=action, code=code), self.assertRaises(ValueError) as caught:
                dispatch(action, payload, self.workspace)
            self.assertEqual(error_response(caught.exception)["code"], code)
        result = dispatch("save_card_edit", {"lexeme_id": lexeme_id, "example_occurrence_id": ""}, self.workspace)
        self.assertEqual(result["entry"]["card"]["meaning_ru"], "правка")
        self.assertEqual(result["entry"]["card"]["example_occurrence_id"], "lumena-o1")
        result = dispatch("save_card_edit", {"lexeme_id": lexeme_id, "meaning_ru": ""}, self.workspace)
        self.assertFalse(result["entry"]["card"]["edited"])
        self.assertNotEqual(result["entry"]["card"]["meaning_source"], "edited")

    def test_import_rebinds_a_selected_legacy_occurrence_and_returns_the_saved_card(self) -> None:
        reader_path = self.workspace / "device" / "vocabulary_builder.sqlite3"
        _koreader_db(reader_path).close()
        [lookup] = reader_sources.fetch_entries(reader_path)
        legacy_id = vocab_cache.occurrence_id({**lookup, "lookup_id": ""}, "kindle")
        current_id = vocab_cache.occurrence_id(lookup, "kindle")
        lexeme = word("glimpse")
        lexeme["occurrences"].append({**lookup, "id": legacy_id, "source": "kindle"})
        self.library([lexeme])
        dispatch("save_card_edit", {
            "lexeme_id": lexeme["id"], "meaning_ru": "мельком увидеть", "example_occurrence_id": legacy_id,
        }, self.workspace)
        dispatch("set_decision", {"lexeme_id": lexeme["id"], "decision": "skip"}, self.workspace)
        payload = {"file_name": reader_path.name, "data_base64": base64.b64encode(reader_path.read_bytes()).decode()}

        for _ in range(2):
            result = _bridge(self.workspace, "import_reader_file", **payload)
            self.assertTrue(result["ok"], result)
            library = result["result"]
            self.assertEqual(library["imported"]["new_words"], 0)
            [entry] = library["entries"]
            self.assertEqual(entry["decision"]["value"], "skip")
            self.assertEqual(entry["card"]["meaning_ru"], "мельком увидеть")
            self.assertEqual(entry["card"]["example_occurrence_id"], current_id)
            self.assertNotIn(legacy_id, {item["id"] for item in entry["occurrences"]})
            self.assertEqual(library["newBatch"], {"count": 0, "ids": [], "availableIds": []})
            self.assertEqual(contracts.validate_library(library), [])


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
