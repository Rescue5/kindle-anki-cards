"""Project the pinned OpenResearch RP-V2 coverage and aliases into local SQLite.

Run from the workspace: python -m scripts.import_openresearch_coverage SOURCE
SOURCE can be models/ranker.json.gz or research-kit-v2.zip.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZipFile

from kindle_vocab_app import book_coverage


def import_model(source: Path, workspace: Path) -> Path:
    if source.suffix.lower() == ".zip":
        with ZipFile(source) as archive:
            compressed = archive.read("models/ranker.json.gz")
    else:
        compressed = source.read_bytes()
    digest = hashlib.sha256(compressed).hexdigest()
    if digest in book_coverage.EXPANDED_SOURCE_SHA256:
        filename = book_coverage.EXPANDED_MODEL_FILENAME
    elif digest == book_coverage.SOURCE_SHA256:
        filename = book_coverage.MODEL_FILENAME
    else:
        raise ValueError(f"Неверная SHA-256 ranker.json.gz ({digest}).")

    model = json.loads(gzip.decompress(compressed).decode("utf-8-sig"))
    coverage_index = model["columns"].index("coverage")
    destination = book_coverage.model_path(workspace, filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, prefix=".coverage-", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.executescript(
                f"""
                PRAGMA user_version = {book_coverage.SCHEMA_VERSION};
                CREATE TABLE provenance (source_sha256 TEXT NOT NULL);
                CREATE TABLE coverage (
                    headword TEXT PRIMARY KEY,
                    share REAL CHECK (share BETWEEN 0 AND 1)
                ) WITHOUT ROWID;
                CREATE TABLE aliases (
                    spelling TEXT PRIMARY KEY,
                    headword TEXT NOT NULL
                ) WITHOUT ROWID;
                """
            )
            connection.execute("INSERT INTO provenance VALUES (?)", (digest,))
            connection.executemany(
                "INSERT INTO coverage VALUES (?, ?)",
                ((headword, row[coverage_index]) for headword, row in sorted(model["rows"].items())),
            )
            connection.executemany(
                "INSERT INTO aliases VALUES (?, ?)", sorted(model["aliases"].items())
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Подготовить локальную SQLite-модель RP-V2.")
    parser.add_argument("source", type=Path, help="ranker.json.gz или research-kit-v2.zip")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        print(import_model(args.source, args.workspace))
    except (BadZipFile, KeyError, OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
