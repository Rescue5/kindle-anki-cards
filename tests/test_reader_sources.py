from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from kindle_vocab_app import reader_sources


def _koreader_db(path: Path, *, journal_wal: bool = False) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    if journal_wal:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.executescript(
        """
        CREATE TABLE title (id INTEGER NOT NULL UNIQUE, name TEXT UNIQUE, filter INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(id));
        CREATE TABLE vocabulary (word TEXT NOT NULL UNIQUE, title_id INTEGER, create_time INTEGER NOT NULL,
            review_time INTEGER, due_time INTEGER NOT NULL, review_count INTEGER NOT NULL DEFAULT 0,
            prev_context TEXT, next_context TEXT, streak_count INTEGER NOT NULL DEFAULT 0, highlight TEXT, PRIMARY KEY(word));
        INSERT INTO title VALUES (1, 'The Night Reader', 1);
        INSERT INTO vocabulary VALUES ('glimpse', 1, 1783000000, NULL, 1783000300, 0,
            'It was late. For a moment he caught a ', ' of the city below. Then the clouds closed in.', 0, NULL);
        """
    )
    connection.commit()
    return connection


class KOReaderTests(unittest.TestCase):
    def test_entries_have_the_sentence_book_and_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vocabulary_builder.sqlite3"
            _koreader_db(path).close()
            self.assertEqual(reader_sources.detect_format(path), reader_sources.KOREADER)
            [entry] = reader_sources.fetch_entries(path)
        self.assertEqual(entry["word"], "glimpse")
        self.assertEqual(entry["context"], "For a moment he caught a glimpse of the city below.")
        self.assertEqual(entry["book_title"], "The Night Reader")
        self.assertEqual(entry["book_key"], "koreader:The Night Reader")
        self.assertEqual(entry["lookup_id"], "koreader:glimpse:1783000000")
        self.assertTrue(str(entry["looked_up_at"]).startswith("2026-07-02"))

    def test_the_old_schema_with_a_book_title_column_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vocabulary_builder.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE vocabulary (word TEXT NOT NULL UNIQUE, book_title TEXT DEFAULT '', create_time INTEGER NOT NULL,
                        review_time INTEGER, due_time INTEGER NOT NULL, review_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(word));
                    INSERT INTO vocabulary VALUES ('dread', 'Frankenstein', 1700000000, NULL, 1700000300, 0);
                    """
                )
            [entry] = reader_sources.fetch_entries(path)
        self.assertEqual((entry["word"], entry["book_title"], entry["context"]), ("dread", "Frankenstein", "dread"))

    def test_lookups_still_in_the_wal_journal_are_not_lost(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            device = Path(temporary) / "device" / "vocabulary_builder.sqlite3"
            connection = _koreader_db(device, journal_wal=True)
            try:
                connection.execute("INSERT INTO vocabulary VALUES ('languid', 1, 1783000100, NULL, 1783000400, 0, '', '', 0, NULL)")
                connection.commit()
                self.assertTrue(device.with_name(device.name + "-wal").is_file())
                cached = reader_sources.copy_to_cache(device, Path(temporary) / "cache", reader_sources.KOREADER)
            finally:
                connection.close()
            words = {entry["word"] for entry in reader_sources.fetch_entries(cached)}
        self.assertEqual(words, {"glimpse", "languid"})


class KoboTests(unittest.TestCase):
    def test_word_list_entries_carry_the_book_and_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "KoboReader.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE content (ContentID TEXT PRIMARY KEY, ContentType TEXT, Title TEXT, Attribution TEXT);
                    CREATE TABLE WordList (Text TEXT, VolumeId TEXT, DictSuffix TEXT, DateCreated TEXT);
                    INSERT INTO content VALUES ('file:///mnt/onboard/night.epub', '6', 'The Night Reader', 'Demo Author');
                    INSERT INTO WordList VALUES ('resilient', 'file:///mnt/onboard/night.epub', '-en', '2026-07-10T21:15:00.000');
                    """
                )
            self.assertEqual(reader_sources.detect_format(path), reader_sources.KOBO)
            [entry] = reader_sources.fetch_entries(path)
        self.assertEqual(entry["word"], "resilient")
        self.assertEqual((entry["book_title"], entry["authors"], entry["language"]), ("The Night Reader", "Demo Author", "en"))
        self.assertEqual(entry["book_key"], "kobo:file:///mnt/onboard/night.epub")
        self.assertEqual(entry["context"], "")
        self.assertTrue(str(entry["looked_up_at"]).startswith("2026-07-10T21:15:00"))


class DetectionTests(unittest.TestCase):
    def test_reader_databases_are_found_on_mounted_volumes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pocketbook = Path(temporary) / "PB"
            kobo = Path(temporary) / "KOBOeReader"
            _koreader_db(pocketbook / "applications" / "koreader" / "settings" / "vocabulary_builder.sqlite3").close()
            (kobo / ".kobo").mkdir(parents=True)
            (kobo / ".kobo" / "KoboReader.sqlite").write_bytes(b"")
            found = reader_sources.find_reader_files([pocketbook, kobo, Path(temporary) / "empty"])
        self.assertEqual([(item.kind, item.label) for item in found], [("koreader", "PocketBook · KOReader"), ("kobo", "Kobo")])

    def test_other_files_are_not_mistaken_for_word_databases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            text = Path(temporary) / "notes.sqlite"
            text.write_text("not a database", encoding="utf-8")
            other = Path(temporary) / "other.sqlite"
            with closing(sqlite3.connect(other)) as connection:
                connection.execute("CREATE TABLE notes (body TEXT)")
            self.assertIsNone(reader_sources.detect_format(text))
            self.assertIsNone(reader_sources.detect_format(other))
            with self.assertRaises(ValueError):
                reader_sources.fetch_entries(other)

    def test_the_sentence_is_cut_at_sentence_ends(self) -> None:
        self.assertEqual(reader_sources.sentence_around("No. She said: “", "yes", "”, quietly. And left."), "She said: “yes”, quietly.")
        self.assertEqual(reader_sources.sentence_around("", "alone", ""), "alone")


if __name__ == "__main__":
    unittest.main()
