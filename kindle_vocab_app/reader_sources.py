"""Word lookups from e-readers other than Kindle: KOReader and Kobo.

KOReader (on PocketBook, Kobo, Boox, Android and jailbroken Kindles) keeps its
Vocabulary builder in ``vocabulary_builder.sqlite3``; Kobo keeps looked-up
words in the ``WordList`` table of ``.kobo/KoboReader.sqlite``. Both are read
read-only from a cached copy and turned into the same entry dictionaries as
Kindle's ``vocab.db``, so they merge into the library through the same path.
Book keys and lookup IDs carry a ``koreader:``/``kobo:`` prefix so they never
collide with Kindle data.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kindle_vocab_app.kindle_db import fetch_entries as fetch_kindle_entries
from kindle_vocab_app.kindle_db import normalize_timestamp
from kindle_vocab_app.kindle_device import _volume_label
from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

KINDLE = "kindle"
KOREADER = "koreader"
KOBO = "kobo"

# Where each reader keeps its words, relative to the root of the USB volume.
KOREADER_PATHS = (
    (Path("applications") / "koreader" / "settings" / "vocabulary_builder.sqlite3", "PocketBook"),
    (Path(".adds") / "koreader" / "settings" / "vocabulary_builder.sqlite3", "Kobo"),
    (Path("koreader") / "settings" / "vocabulary_builder.sqlite3", ""),
)
KOBO_PATH = Path(".kobo") / "KoboReader.sqlite"
FORMAT_LABELS = {KINDLE: "Kindle", KOREADER: "KOReader", KOBO: "Kobo"}

_SENTENCE_END = re.compile(r"[.!?…](?:[\"'”»)\]]*)\s")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class ReaderFile:
    """A words database found on a mounted reader."""

    kind: str
    path: Path
    label: str

    @property
    def signature(self) -> tuple[str, ...]:
        stat = self.path.stat()
        wal = self.path.with_name(self.path.name + "-wal")
        wal_mtime = str(wal.stat().st_mtime_ns) if wal.is_file() else ""
        return (str(self.path), str(stat.st_size), str(stat.st_mtime_ns), wal_mtime)


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def detect_format(path: Path) -> str | None:
    """Which reader wrote this SQLite file, by its tables; ``None`` if it is none of them."""
    try:
        with _connect(path) as connection:
            tables = {str(row[0]).casefold() for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError:
        return None
    if {"words", "lookups", "book_info"} <= tables:
        return KINDLE
    if "vocabulary" in tables:
        return KOREADER
    if "wordlist" in tables:
        return KOBO
    return None


def find_reader_files(roots: Iterable[Path]) -> list[ReaderFile]:
    """KOReader and Kobo word databases on mounted volumes (Kindle is found by ``kindle_device``)."""
    found: list[ReaderFile] = []
    for root in roots:
        for relative, device in KOREADER_PATHS:
            path = root / relative
            if _is_file(path):
                found.append(ReaderFile(KOREADER, path, f"{device or _volume_name(root) or 'Читалка'} · KOReader"))
                break
        kobo = root / KOBO_PATH
        if _is_file(kobo):
            found.append(ReaderFile(KOBO, kobo, "Kobo"))
    return found


def copy_to_cache(source: Path, cache_dir: Path, kind: str) -> Path:
    """Copy a reader database (with its WAL journal, where recent lookups may live) and fold it in."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{kind}.sqlite"
    for suffix in ("", "-wal", "-shm"):
        cached = target.with_name(target.name + suffix)
        cached.unlink(missing_ok=True)
    shutil.copy2(source, target)
    wal = source.with_name(source.name + "-wal")
    if wal.is_file():
        shutil.copy2(wal, target.with_name(target.name + "-wal"))
        # The copy is ours: checkpoint the journal so a read-only open sees every lookup.
        connection = sqlite3.connect(target)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA journal_mode=DELETE")
        finally:
            connection.close()
    logger.info("Cached reader database kind=%s source=%s target=%s", kind, source, target)
    return target


def fetch_entries(path: Path, kind: str | None = None) -> list[dict[str, object]]:
    """Lookup entries in Kindle's shape from any supported reader database."""
    kind = kind or detect_format(path)
    if kind == KINDLE:
        return fetch_kindle_entries(path)
    if kind == KOREADER:
        return fetch_koreader_entries(path)
    if kind == KOBO:
        return fetch_kobo_entries(path)
    raise ValueError("Это не база слов Kindle, KOReader или Kobo")


def fetch_koreader_entries(path: Path) -> list[dict[str, object]]:
    with _connect(path) as connection:
        columns = {str(row["name"]).casefold() for row in connection.execute("PRAGMA table_info(vocabulary)")}
        tables = {str(row[0]).casefold() for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        prev_context = "v.prev_context" if "prev_context" in columns else "''"
        next_context = "v.next_context" if "next_context" in columns else "''"
        if "title_id" in columns and "title" in tables:
            title, join = "t.name", "LEFT JOIN title t ON t.id = v.title_id"
        elif "book_title" in columns:
            title, join = "v.book_title", ""
        else:
            title, join = "''", ""
        rows = connection.execute(
            f"""
            SELECT v.word AS word, v.create_time AS create_time,
                   {prev_context} AS prev_context, {next_context} AS next_context,
                   COALESCE({title}, '') AS book_title
            FROM vocabulary v {join}
            ORDER BY v.create_time DESC
            """
        ).fetchall()
    entries = []
    for row in rows:
        word = _SPACES.sub(" ", str(row["word"] or "")).strip()
        if not word:
            continue
        book_title = str(row["book_title"] or "").strip()
        created = row["create_time"] or 0
        entries.append({
            "lookup_id": f"koreader:{word}:{created}",
            "book_key": f"koreader:{book_title}" if book_title else "",
            "word": word,
            "stem": "",
            "context": sentence_around(str(row["prev_context"] or ""), word, str(row["next_context"] or "")),
            "book_title": book_title,
            "authors": "",
            "language": "en",
            "looked_up_at": normalize_timestamp(int(created)) if created else "",
        })
    logger.info("Fetched KOReader entries path=%s count=%d", path, len(entries))
    return entries


def fetch_kobo_entries(path: Path) -> list[dict[str, object]]:
    with _connect(path) as connection:
        tables = {str(row[0]).casefold() for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        join = "LEFT JOIN content c ON c.ContentID = w.VolumeId" if "content" in tables else ""
        book = "COALESCE(c.Title, '')" if join else "''"
        author = "COALESCE(c.Attribution, '')" if join else "''"
        rows = connection.execute(
            f"""
            SELECT w.Text AS word, w.VolumeId AS volume, COALESCE(w.DictSuffix, '') AS suffix,
                   COALESCE(w.DateCreated, '') AS created, {book} AS book_title, {author} AS authors
            FROM WordList w {join}
            ORDER BY w.DateCreated DESC
            """
        ).fetchall()
    entries = []
    for row in rows:
        word = _SPACES.sub(" ", str(row["word"] or "")).strip()
        if not word:
            continue
        created = str(row["created"] or "")
        volume = str(row["volume"] or "")
        entries.append({
            "lookup_id": f"kobo:{word}:{created}",
            "book_key": f"kobo:{volume}" if volume else "",
            "word": word,
            "stem": "",
            # Kobo keeps only the word, not the sentence it was found in.
            "context": "",
            "book_title": str(row["book_title"] or "").strip(),
            "authors": str(row["authors"] or "").strip(),
            "language": _kobo_language(str(row["suffix"])),
            "looked_up_at": _kobo_time(created),
        })
    logger.info("Fetched Kobo entries path=%s count=%d", path, len(entries))
    return entries


def sentence_around(prev_context: str, word: str, next_context: str) -> str:
    """The sentence containing the looked-up word, cut from KOReader's text before and after it."""
    before = _SPACES.sub(" ", prev_context)
    after = _SPACES.sub(" ", next_context)
    ends = list(_SENTENCE_END.finditer(before))
    if ends:
        before = before[ends[-1].end():]
    first_end = _SENTENCE_END.search(after + " ")
    if first_end:
        after = after[: first_end.end()]
    joiner_before = "" if not before or before.endswith((" ", "(", "“", "«", '"', "'")) else " "
    joiner_after = "" if not after or after[0] in " .,;:!?…)”»\"'" else " "
    return f"{before.lstrip()}{joiner_before}{word}{joiner_after}{after}".strip()


def _kobo_language(suffix: str) -> str:
    code = suffix.strip().lstrip("-").lower()
    return code[:2] if len(code) >= 2 and code[:2].isalpha() else "en"


def _kobo_time(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).isoformat()


def _volume_name(root: Path) -> str:
    """The volume's label, or "" when only a drive letter or mount point is known."""
    name = _volume_label(root)
    return "" if not name or name == root.anchor or name.endswith((":", ":\\")) else name


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False
