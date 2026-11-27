"""Prepare the isolated workspace used by the Windows development launcher."""

from __future__ import annotations

import json
import shutil
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Literal

from kindle_vocab_app import book_coverage, library_migrations, settings
from kindle_vocab_app.library_repository import DATABASE_FILENAME

ProfileSource = Literal["created", "copied", "existing"]
APP_DATA = ".app-data"
MODEL_NOTICE = "ranking-model-notices.txt"
_BASELINE_TABLES = {
    "schema_migrations", "metadata", "lexemes", "forms", "occurrences", "analyses",
    "processing_queue", "destinations", "sync_runs", "review_cards", "enrichments",
}
_READER_TABLES = {"word_decisions", "card_edits", "export_runs", "export_items"}


def prepare_profile(
    workspace: Path,
    installed_workspace: Path,
    *,
    seed: bool = True,
    bundled_model: Path | None = None,
) -> ProfileSource:
    """Return 'copied' for a new seeded profile, 'created' or 'existing' otherwise.

    A failed first launch never publishes a partial .app-data directory.
    A pre-existing profile always takes precedence over the installation.
    """
    workspace = workspace.resolve()
    installed_workspace = installed_workspace.resolve()
    target = workspace / APP_DATA
    source = installed_workspace / APP_DATA
    target_path, source_path = target.resolve(), source.resolve()
    if target_path.is_relative_to(source_path) or source_path.is_relative_to(target_path):
        raise RuntimeError("Рабочая папка разработки пересекается с установленным профилем.")
    if _present(target, directory=True):
        return _validate_existing(target)

    has_installed_profile = seed and _present(source, directory=True)
    source_db = source / DATABASE_FILENAME
    source_settings = source / settings.SETTINGS_FILENAME
    has_database = has_installed_profile and _present(source_db)
    has_settings = has_installed_profile and _present(source_settings)
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".app-data-init-", dir=workspace) as pending:
        staged = Path(pending)
        database = staged / DATABASE_FILENAME
        if has_database:
            _backup_database(source_db, database)
        else:
            library_migrations.migrate(database)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("PRAGMA journal_mode = DELETE")
        _check_library(database)
        if has_settings:
            payload = _read_settings(source_settings)
            payload["llm_auto_enrich"] = False
            (staged / settings.SETTINGS_FILENAME).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        if bundled_model is not None:
            _copy_model(bundled_model, staged / "models")

        # Windows rename cannot replace an existing directory. Other launches
        # of this launcher also publish a non-empty directory in a single step.
        if _present(target, directory=True):
            return _validate_existing(target)
        try:
            staged.rename(target)
        except OSError:
            if _present(target, directory=True):
                return _validate_existing(target)
            raise
    return "copied" if has_database or has_settings else "created"


def _present(path: Path, *, directory: bool = False, editable: bool = False) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    matches_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    reparse_point = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    if not matches_type or reparse_point or (editable and info.st_nlink > 1):
        raise RuntimeError(f"Ожидался обычный объект профиля без ссылок: {path}")
    return True


def _validate_existing(directory: Path) -> Literal["existing"]:
    database = directory / DATABASE_FILENAME
    if not _present(database, editable=True):
        raise RuntimeError(f"В существующем профиле отсутствует библиотека: {database}")
    _check_sidecars(database, editable=True)
    _check_library(database)
    config = directory / settings.SETTINGS_FILENAME
    if _present(config, editable=True):
        _read_settings(config)
    return "existing"


def _check_sidecars(database: Path, *, editable: bool = False) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        _present(database.with_name(database.name + suffix), editable=editable)


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)


def _backup_database(source: Path, target: Path) -> None:
    _check_sidecars(source)
    deadline = time.monotonic() + library_migrations.MIGRATION_LOCK_SECONDS

    def stop_if_locked(status: int, remaining: int, total: int) -> None:
        if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) and time.monotonic() >= deadline:
            raise TimeoutError("SQLite source is busy")

    try:
        with closing(_readonly(source)) as reader, closing(sqlite3.connect(target)) as writer:
            # Read through SQLite so committed pages still in the WAL are part of the snapshot.
            reader.backup(writer, pages=256, progress=stop_if_locked)
            writer.execute("PRAGMA journal_mode = DELETE")
    except (OSError, sqlite3.Error) as exc:
        raise RuntimeError(f"Не удалось скопировать библиотеку: {source}") from exc


def _check_library(path: Path) -> None:
    try:
        with closing(_readonly(path)) as connection:
            connection.execute("BEGIN")
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise sqlite3.DatabaseError("integrity_check failed")
            version = library_migrations.read_version(connection)
            if not 1 <= version <= library_migrations.SCHEMA_VERSION:
                raise sqlite3.DatabaseError(f"unsupported library schema: {version}")
            tables = {
                row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")
            }
            required = _BASELINE_TABLES if version >= 3 else {"lexemes", "metadata"}
            if version >= 4:
                required = required | _READER_TABLES
            if required - tables:
                raise sqlite3.DatabaseError("required library tables are missing")
            connection.execute("SELECT id, language, canonical_key FROM lexemes WHERE 0")
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise RuntimeError(f"Библиотека повреждена или имеет неподдерживаемую схему: {path}") from exc


def _read_settings(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("expected a settings object")
        settings.from_dict(payload)
        return payload
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Не удалось прочитать настройки профиля: {path}") from exc


def _copy_model(source: Path, destination: Path) -> None:
    source = source.absolute()
    if not _present(source):
        raise RuntimeError(f"Файл книжного охвата не найден: {source}")
    destination.mkdir()
    model = destination / book_coverage.EXPANDED_MODEL_FILENAME
    shutil.copyfile(source, model)
    try:
        with closing(_readonly(model)) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            provenance = connection.execute("SELECT source_sha256 FROM provenance").fetchone()
            if (
                version != book_coverage.SCHEMA_VERSION
                or provenance is None
                or provenance[0] not in book_coverage.EXPANDED_SOURCE_SHA256
                or connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
            ):
                raise sqlite3.DatabaseError("unexpected coverage model")
            connection.execute("SELECT headword, share FROM coverage WHERE 0")
            connection.execute("SELECT spelling, headword FROM aliases WHERE 0")
    except sqlite3.Error as exc:
        raise RuntimeError(f"Не удалось проверить модель книжного охвата: {source}") from exc
    for directory in (source.parent, source.parent.parent):
        notice = directory / MODEL_NOTICE
        if _present(notice):
            shutil.copyfile(notice, destination / MODEL_NOTICE)
            break
