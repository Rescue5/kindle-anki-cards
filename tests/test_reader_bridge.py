from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kindle_vocab_app.tauri_bridge import dispatch
from tests.test_reader_sources import _koreader_db


class ReaderBridgeTests(unittest.TestCase):
    def test_a_pocketbook_with_koreader_syncs_without_a_kindle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            volume = Path(temporary) / "PB632"
            _koreader_db(volume / "applications" / "koreader" / "settings" / "vocabulary_builder.sqlite3").close()
            with (
                patch("kindle_vocab_app.tauri_bridge.find_kindle_source", return_value=None),
                patch("kindle_vocab_app.tauri_bridge.find_kindle_presence", return_value=None),
                patch("kindle_vocab_app.tauri_bridge.mounted_volume_roots", return_value=[volume]),
                patch("kindle_vocab_app.anki_connect.status", return_value={"state": "disconnected", "label": "Anki"}),
            ):
                status = dispatch("connector_status", {}, workspace)
                result = dispatch("sync_kindle", {}, workspace)

            self.assertEqual(status["kindle"]["state"], "connected")
            self.assertEqual(status["kindle"]["label"], "PocketBook · KOReader")
            self.assertEqual([entry["lemma"] for entry in result["entries"]], ["glimpse"])
            [occurrence] = result["entries"][0]["occurrences"]
            self.assertEqual(occurrence["book_title"], "The Night Reader")
            self.assertEqual(occurrence["context"], "For a moment he caught a glimpse of the city below.")
            self.assertEqual(result["entries"][0]["freshness"], "new")
            self.assertEqual(result["queueStatus"]["pending"], 1)

    def test_a_picked_file_is_imported_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            database = Path(temporary) / "vocabulary_builder.sqlite3"
            _koreader_db(database).close()
            payload = {"file_name": database.name, "data_base64": base64.b64encode(database.read_bytes()).decode("ascii")}
            first = dispatch("import_reader_file", payload, workspace)
            second = dispatch("import_reader_file", payload, workspace)

        self.assertEqual(first["imported"], {"format": "koreader", "label": "KOReader", "lookups": 1, "new_words": 1})
        self.assertEqual(second["imported"]["new_words"], 0)
        self.assertEqual(len(second["entries"]), 1)
        self.assertEqual(len(second["entries"][0]["occurrences"]), 1)

    def test_a_file_that_is_not_a_words_database_is_refused_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            payload = {"file_name": "photo.jpg", "data_base64": base64.b64encode(b"\xff\xd8 not sqlite").decode("ascii")}
            with self.assertRaisesRegex(ValueError, "photo.jpg: это не база слов"):
                dispatch("import_reader_file", payload, workspace)
            with self.assertRaisesRegex(ValueError, "пустой"):
                dispatch("import_reader_file", {"file_name": "empty.db", "data_base64": ""}, workspace)


if __name__ == "__main__":
    unittest.main()
