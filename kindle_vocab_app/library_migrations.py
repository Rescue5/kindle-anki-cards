"""Versioned, forward-only schema migrations for the local SQLite library.

`migrate(path)` brings `kindle_cards.sqlite3` to `SCHEMA_VERSION`:

1. Read the version without writing. Nothing to do at the current version.
2. If the file already holds tables, copy it to
   `.app-data/backups/kindle_cards.v<old>.<utc>.sqlite3` with the SQLite
   backup API, check the copy with `PRAGMA integrity_check`, and keep the
   newest three copies. This happens before any write transaction.
3. `BEGIN IMMEDIATE`, read the version again (another process may have
   migrated meanwhile), run the statements one by one, write the version row
   and commit. Any failure rolls the whole step back.

Every connection is closed explicitly: on Windows a connection used only as a
context manager keeps the file locked.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 4
BACKUP_DIRNAME = "backups"
BACKUPS_KEPT = 3
# Other starts wait this long for the one that is copying and migrating.
MIGRATION_LOCK_SECONDS = 60
SQLITE_HEADER = b"SQLite format 3\x00"
SQLITE_PAGE_MIN = 512
MIGRATION_FAILED = "Не удалось обновить библиотеку; копия сохранена"
CREATION_FAILED = "Не удалось создать библиотеку. Подробности в журнале"
BACKUP_FAILED = (
    "Не удалось сделать копию библиотеки перед обновлением; библиотека не изменена"
)

# Schema as of version 3. `IF NOT EXISTS` lets one step bring versions 0-3 to
# the v3 baseline: versions 1-3 only ever added whole tables.
BASELINE_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS schema_migrations(
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS metadata(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS lexemes(
        id TEXT PRIMARY KEY,
        language TEXT NOT NULL,
        canonical_key TEXT NOT NULL,
        display_form TEXT NOT NULL,
        freshness TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        last_kindle_sync_id TEXT NOT NULL,
        source_kindle INTEGER NOT NULL DEFAULT 0,
        source_legacy INTEGER NOT NULL DEFAULT 0,
        UNIQUE(language, canonical_key)
    )""",
    """CREATE TABLE IF NOT EXISTS forms(
        lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
        form TEXT NOT NULL,
        normalized_form TEXT NOT NULL,
        PRIMARY KEY(lexeme_id, normalized_form)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_forms_normalized ON forms(normalized_form)",
    """CREATE TABLE IF NOT EXISTS occurrences(
        id TEXT PRIMARY KEY,
        lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        word TEXT NOT NULL,
        context TEXT NOT NULL,
        book_key TEXT NOT NULL,
        book_title TEXT NOT NULL,
        authors TEXT NOT NULL,
        looked_up_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_occurrences_lexeme ON occurrences(lexeme_id)",
    """CREATE TABLE IF NOT EXISTS analyses(
        lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
        state TEXT NOT NULL,
        payload_json TEXT,
        updated_at TEXT NOT NULL,
        error TEXT NOT NULL,
        origin TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS processing_queue(
        lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        error TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS destinations(
        lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
        destination TEXT NOT NULL,
        state TEXT NOT NULL,
        eligible INTEGER NOT NULL DEFAULT 0,
        reason TEXT NOT NULL,
        external_key TEXT NOT NULL,
        last_checked_at TEXT NOT NULL,
        last_synced_at TEXT NOT NULL,
        last_exported_at TEXT NOT NULL,
        PRIMARY KEY(lexeme_id, destination)
    )""",
    """CREATE TABLE IF NOT EXISTS sync_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connector TEXT NOT NULL,
        status TEXT NOT NULL,
        added INTEGER NOT NULL DEFAULT 0,
        skipped INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL,
        completed_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS review_cards(
        lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
        interval_days REAL NOT NULL DEFAULT 0,
        repetitions INTEGER NOT NULL DEFAULT 0,
        due_at TEXT NOT NULL,
        reviewed_at TEXT NOT NULL,
        last_rating TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_review_cards_due ON review_cards(due_at)",
    # Keyed by canonical identity, not lexeme id, so enrichments survive full
    # catalog replacement and lexeme merges without a cascade.
    """CREATE TABLE IF NOT EXISTS enrichments(
        language TEXT NOT NULL,
        canonical_key TEXT NOT NULL,
        status TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        prompt_version INTEGER NOT NULL,
        payload_json TEXT,
        error TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(language, canonical_key)
    )""",
)

# Version 4: the reader's own data, keyed by lexeme_id without a foreign key so
# it survives catalog replacement; language + canonical_key are a re-link hint.
V4_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS word_decisions(
        lexeme_id TEXT PRIMARY KEY, language TEXT NOT NULL, canonical_key TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('known','learn','skip','junk')),
        decided_at TEXT NOT NULL,
        shelf_at TEXT NOT NULL DEFAULT '', score_at REAL,
        ranking_version TEXT NOT NULL DEFAULT ''
    )""",
    (
        "CREATE INDEX IF NOT EXISTS idx_word_decisions_key"
        " ON word_decisions(language, canonical_key)"
    ),
    """CREATE TABLE IF NOT EXISTS card_edits(
        lexeme_id TEXT PRIMARY KEY, language TEXT NOT NULL, canonical_key TEXT NOT NULL,
        meaning_ru TEXT, example_occurrence_id TEXT,
        example_context TEXT NOT NULL DEFAULT '', example_form TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_card_edits_key ON card_edits(language, canonical_key)",
    """CREATE TABLE IF NOT EXISTS export_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        destination TEXT NOT NULL CHECK(destination IN ('anki','csv','obsidian')),
        scope TEXT NOT NULL CHECK(scope IN ('new','again','migrated')),
        created_at TEXT NOT NULL, word_count INTEGER NOT NULL, path TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS export_items(
        run_id INTEGER NOT NULL REFERENCES export_runs(id) ON DELETE CASCADE,
        lexeme_id TEXT NOT NULL, language TEXT NOT NULL, canonical_key TEXT NOT NULL,
        is_repeat INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(run_id, lexeme_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_export_items_lexeme ON export_items(lexeme_id)",
)

# Old per-lexeme destination state -> export history destination.
_LEGACY_EXPORT_DESTINATIONS = {
    ("anki", "exported"): "anki",
    ("quizlet", "exported"): "csv",
    ("obsidian", "synced"): "obsidian",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def open_connection(
    path: Path, *, autocommit: bool = False, timeout: float = 10
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        path, timeout=timeout, isolation_level=None if autocommit else ""
    )
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def read_version(connection: sqlite3.Connection) -> int:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if exists is None:
        return 0
    row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def _has_tables(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        is not None
    )


def migrate(path: Path) -> Path | None:
    """Bring the library at `path` to `SCHEMA_VERSION`; return the backup made, if any."""
    with closing(open_connection(path)) as connection:
        version = read_version(connection)
    if version >= SCHEMA_VERSION:
        if version > SCHEMA_VERSION:
            logger.warning(
                "Library schema is newer than this app version=%d supported=%d",
                version,
                SCHEMA_VERSION,
            )
        return None

    started = datetime.now(UTC)
    backup: Path | None = None
    with closing(open_connection(path, autocommit=True, timeout=MIGRATION_LOCK_SECONDS)) as connection:
        try:
            # Journal mode cannot change inside a transaction; WAL is a no-op when set.
            connection.execute("PRAGMA journal_mode = WAL")
            # The write lock is taken before the backup: concurrent starts queue
            # here, and only the one that still finds an old schema copies and
            # migrates it. Nothing is written until the copy is verified.
            connection.execute("BEGIN IMMEDIATE")
            current = read_version(connection)
            if current >= SCHEMA_VERSION:
                connection.execute("ROLLBACK")
                logger.info("Library schema already migrated by another process")
                return None
            if _has_tables(connection):
                backup = backup_database(path, current)
        except Exception as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            if isinstance(exc, ValueError):
                raise
            logger.exception("Library could not be locked for migration")
            raise ValueError(BACKUP_FAILED) from exc
        try:
            _apply_steps(connection, current)
            connection.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )
            connection.execute("COMMIT")
        except Exception as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            logger.exception("Library schema migration failed from_version=%d", current)
            raise ValueError(MIGRATION_FAILED if backup else CREATION_FAILED) from exc
    elapsed = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "Library schema migrated from_version=%d to_version=%d seconds=%.3f backup=%s",
        current,
        SCHEMA_VERSION,
        elapsed,
        backup.name if backup else "",
    )
    return backup


def _apply_steps(connection: sqlite3.Connection, current: int) -> None:
    for target, step in _STEPS:
        if current < target:
            step(connection)


def _baseline(connection: sqlite3.Connection) -> None:
    for statement in BASELINE_STATEMENTS:
        connection.execute(statement)


def _to_v4(connection: sqlite3.Connection) -> None:
    for statement in V4_STATEMENTS:
        connection.execute(statement)
    _backfill_export_history(connection, utc_now())


def _backfill_export_history(connection: sqlite3.Connection, now: str) -> None:
    """Turn the old per-lexeme export state into `migrated` export runs.

    One old export action stamped all its words with the same time, so rows
    grouped by (destination, time) are the original runs. A lost timestamp is
    replaced by the migration time: the word was exported, but lookups before
    the migration are not treated as "looked up again after export".
    Destination rows are left as they are.
    """
    runs: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in connection.execute(
        """
        SELECT d.lexeme_id, d.destination, d.state, d.last_exported_at, d.last_synced_at,
               l.language, l.canonical_key
        FROM destinations AS d JOIN lexemes AS l ON l.id = d.lexeme_id
        WHERE (d.destination IN ('anki', 'quizlet') AND d.state = 'exported')
           OR (d.destination = 'obsidian' AND d.state = 'synced')
        ORDER BY d.lexeme_id
        """
    ):
        target = _LEGACY_EXPORT_DESTINATIONS[(str(row["destination"]), str(row["state"]))]
        stamp = row["last_synced_at"] if target == "obsidian" else row["last_exported_at"]
        runs[(target, str(stamp or "") or now)].append(row)
    for (destination, created_at), items in sorted(runs.items(), key=lambda run: run[0][::-1]):
        cursor = connection.execute(
            """
            INSERT INTO export_runs(destination, scope, created_at, word_count, path)
            VALUES (?, 'migrated', ?, ?, '')
            """,
            (destination, created_at, len(items)),
        )
        run_id = cursor.lastrowid
        for item in items:
            connection.execute(
                """
                INSERT INTO export_items(run_id, lexeme_id, language, canonical_key, is_repeat)
                VALUES (?, ?, ?, ?, 0)
                """,
                (run_id, item["lexeme_id"], item["language"], item["canonical_key"]),
            )


_STEPS: tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...] = (
    (3, _baseline),
    (4, _to_v4),
)


def backup_database(path: Path, version: int) -> Path:
    """Copy the library, verify the copy, keep the newest copies.

    Called while the migration's connection holds the write lock with nothing
    written yet. The copy is read through a second connection (a reader is
    allowed next to a reserved write lock; the locking connection itself
    cannot be a backup source), so it is exactly the library before migration.
    A failed copy is removed.
    """
    backup_dir = path.parent / BACKUP_DIRNAME
    target: Path | None = None
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = _claim_backup_path(backup_dir, path.stem, version)
        with closing(open_connection(path)) as source, closing(sqlite3.connect(target)) as copy:
            source.execute("BEGIN")  # one read snapshot for the copy and the count
            source.backup(copy)
            source_lexemes = _lexeme_count(source)
            source.rollback()
            # A single self-contained file, without -wal/-shm companions.
            copy.execute("PRAGMA journal_mode = DELETE")
        problem = _verify_backup(target, source_lexemes)
        if problem:
            raise RuntimeError(problem)
    except Exception as exc:
        logger.exception("Library backup failed before migration")
        if target is not None:
            _remove_quietly(target)
        raise ValueError(BACKUP_FAILED) from exc
    logger.info(
        "Library backed up before migration file=%s lexemes=%s", target.name, source_lexemes
    )
    _prune_backups(backup_dir, path.stem)
    return target


def _verify_backup(target: Path, expected_lexemes: int | None) -> str:
    with closing(sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)) as copy:
        integrity = [str(row[0]) for row in copy.execute("PRAGMA integrity_check")]
        copied_lexemes = _lexeme_count(copy)
    if integrity != ["ok"]:
        return f"backup integrity check failed: {integrity[:3]}"
    if copied_lexemes != expected_lexemes:
        return "backup lexeme count differs from the library"
    return ""


def _remove_quietly(path: Path) -> None:
    for item in (path, path.with_name(path.name + "-journal")):
        try:
            item.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove a failed library backup file=%s", item.name)


def _lexeme_count(connection: sqlite3.Connection) -> int | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lexemes'"
    ).fetchone()
    if exists is None:
        return None
    return int(connection.execute("SELECT COUNT(*) FROM lexemes").fetchone()[0])


def _claim_backup_path(backup_dir: Path, stem: str, version: int) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    for attempt in range(100):
        suffix = f"-{attempt}" if attempt else ""
        candidate = backup_dir / f"{stem}.v{version}.{stamp}{suffix}.sqlite3"
        try:
            # Exclusive create: two processes starting at once never share a file.
            with open(candidate, "xb"):
                pass
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError("no free backup file name")


def list_backups(backup_dir: Path, stem: str) -> list[Path]:
    """Complete-looking backups, newest first.

    Empty files and files without an SQLite header (a copy cut short) are
    ignored, so they never push a real copy out of the retention window.
    """
    found = []
    for item in backup_dir.glob(f"{stem}.v*.sqlite3"):
        try:
            stat = item.stat()
            if stat.st_size < SQLITE_PAGE_MIN:
                continue
            with open(item, "rb") as handle:
                if handle.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                    continue
        except OSError:
            continue
        found.append((stat.st_mtime_ns, item.name, item))
    return [item for _, _, item in sorted(found, reverse=True)]


def _prune_backups(backup_dir: Path, stem: str) -> None:
    for old in list_backups(backup_dir, stem)[BACKUPS_KEPT:]:
        try:
            old.unlink()
        except OSError:
            logger.warning("Could not remove an old library backup file=%s", old.name)
