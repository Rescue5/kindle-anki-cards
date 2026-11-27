from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest

from kindle_vocab_app import book_coverage, library_migrations
from scripts.dev_profile import APP_DATA, DATABASE_FILENAME, MODEL_NOTICE, prepare_profile


def _database(workspace: Path) -> Path:
    return workspace / APP_DATA / DATABASE_FILENAME


def _initialize(workspace: Path) -> Path:
    path = _database(workspace)
    path.parent.mkdir(parents=True)
    library_migrations.migrate(path)
    return path


def _bundled_model(tmp_path: Path) -> Path:
    bridge = tmp_path / "Installed application" / "bridge"
    model = bridge / "models" / book_coverage.EXPANDED_MODEL_FILENAME
    model.parent.mkdir(parents=True)
    (bridge / MODEL_NOTICE).write_text("Test source notices\n", encoding="utf-8")
    with closing(sqlite3.connect(model)) as connection:
        connection.executescript(f"""
            PRAGMA user_version={book_coverage.SCHEMA_VERSION};
            CREATE TABLE provenance(source_sha256 TEXT);
            CREATE TABLE coverage(headword TEXT PRIMARY KEY, share REAL);
            CREATE TABLE aliases(spelling TEXT PRIMARY KEY, headword TEXT);
            INSERT INTO coverage VALUES ('fixture', 0.4);
        """)
        connection.execute(
            "INSERT INTO provenance VALUES (?)", (next(iter(book_coverage.EXPANDED_SOURCE_SHA256)),)
        )
        connection.commit()
    return model


def test_wal_settings_and_model_are_copied_only_once(tmp_path: Path) -> None:
    installed = tmp_path / "Установленный профиль #1"
    dev = tmp_path / "Рабочий профиль #1"
    source_db = _initialize(installed)
    source_settings = source_db.parent / "settings.json"
    source_config = {
        "theme": "dark", "llm_auto_enrich": True, "extra": "неизвестное поле"
    }
    source_settings.write_text(json.dumps(source_config), encoding="utf-8")
    settings_bytes = source_settings.read_bytes()
    model = _bundled_model(tmp_path)

    with closing(sqlite3.connect(source_db)) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO metadata VALUES ('fixture', 'committed to WAL')")
        writer.commit()
        wal = source_db.with_name(source_db.name + "-wal")
        source_bytes, wal_bytes = source_db.read_bytes(), wal.read_bytes()
        assert wal_bytes
        assert prepare_profile(dev, installed, bundled_model=model) == "copied"
        assert source_db.read_bytes() == source_bytes
        assert wal.read_bytes() == wal_bytes
        assert source_settings.read_bytes() == settings_bytes

    data = dev / APP_DATA
    assert {item.name for item in data.iterdir()} == {DATABASE_FILENAME, "settings.json", "models"}
    with closing(sqlite3.connect(_database(dev))) as reader:
        assert reader.execute("SELECT value FROM metadata WHERE key='fixture'").fetchall() == [
            ("committed to WAL",)
        ]
        reader.execute("UPDATE metadata SET value='local' WHERE key='fixture'")
        reader.commit()
    assert (data / "models" / model.name).read_bytes() == model.read_bytes()
    assert (data / "models" / MODEL_NOTICE).read_text(encoding="utf-8") == "Test source notices\n"
    with book_coverage.open_model(dev) as coverage:
        assert coverage is not None
        assert coverage.priority("fixture")["score"] == 0.4

    dev_settings = data / "settings.json"
    assert json.loads(dev_settings.read_text(encoding="utf-8")) == {
        **source_config, "llm_auto_enrich": False
    }
    dev_settings.write_text('{"theme":"light"}', encoding="utf-8")
    preserved = dev_settings.read_bytes()
    assert prepare_profile(dev, installed, bundled_model=tmp_path / "missing.sqlite") == "existing"
    assert dev_settings.read_bytes() == preserved
    with closing(sqlite3.connect(_database(dev))) as reader:
        assert reader.execute("SELECT value FROM metadata WHERE key='fixture'").fetchall() == [
            ("local",)
        ]


def test_fresh_profile_does_not_read_installation_files(tmp_path: Path) -> None:
    installed = tmp_path / "installed"
    source = _initialize(installed)
    source.write_bytes(b"invalid source")
    dev = tmp_path / "dev"
    assert prepare_profile(dev, installed, seed=False) == "created"
    assert source.read_bytes() == b"invalid source"
    assert prepare_profile(dev, installed) == "existing"


@pytest.mark.parametrize("invalid_file", [DATABASE_FILENAME, "settings.json", "model"])
def test_failed_seed_never_publishes_partial_profile(tmp_path: Path, invalid_file: str) -> None:
    installed = tmp_path / "installed"
    source = _initialize(installed)
    model = None
    if invalid_file == "model":
        model = _bundled_model(tmp_path)
        invalid = model
    else:
        invalid = source.parent / invalid_file
    invalid.write_bytes(b"invalid source")
    dev = tmp_path / "dev"

    with pytest.raises(RuntimeError):
        prepare_profile(dev, installed, bundled_model=model)
    assert invalid.read_bytes() == b"invalid source"
    assert not list(dev.iterdir())


def test_corrupt_existing_profile_and_alias_are_rejected(tmp_path: Path) -> None:
    installed = tmp_path / "installed"
    _initialize(installed)
    dev = tmp_path / "dev"
    database = _initialize(dev)
    database.write_bytes(b"already existed")
    with pytest.raises(RuntimeError, match="Библиотека повреждена"):
        prepare_profile(dev, installed)
    assert database.read_bytes() == b"already existed"
    with pytest.raises(RuntimeError, match="пересекается"):
        prepare_profile(installed / APP_DATA / "child", installed)


def test_dev_workspace_can_live_in_another_folder_of_the_checkout(tmp_path: Path) -> None:
    _initialize(tmp_path)
    assert prepare_profile(tmp_path / "build" / "dev", tmp_path) == "copied"


def test_two_first_starts_publish_one_profile(tmp_path: Path) -> None:
    installed = tmp_path / "no installed profile"
    dev = tmp_path / "dev"
    ready = Barrier(2)

    def start() -> str:
        ready.wait(timeout=10)
        return prepare_profile(dev, installed)

    with ThreadPoolExecutor(2) as workers:
        jobs = [workers.submit(start) for _ in range(2)]
        assert sorted(job.result(timeout=20) for job in jobs) == ["created", "existing"]
    assert list(dev.iterdir()) == [dev / APP_DATA]
