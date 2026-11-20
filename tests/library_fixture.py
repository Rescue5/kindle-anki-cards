"""A synthetic schema-v3 library used by migration and catalog tests.

The DDL below is frozen as it was in schema version 3, so the fixture keeps
describing an *old* library even after the application schema moves on. All
words, books and contexts are invented or common English words; nothing comes
from a real reader's library.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from kindle_vocab_app import vocab_cache

DATABASE_FILENAME = "kindle_cards.sqlite3"

V3_DDL = [
    """CREATE TABLE schema_migrations(
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )""",
    """CREATE TABLE metadata(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE lexemes(
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
    """CREATE TABLE forms(
        lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
        form TEXT NOT NULL,
        normalized_form TEXT NOT NULL,
        PRIMARY KEY(lexeme_id, normalized_form)
    )""",
    "CREATE INDEX idx_forms_normalized ON forms(normalized_form)",
    """CREATE TABLE occurrences(
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
    "CREATE INDEX idx_occurrences_lexeme ON occurrences(lexeme_id)",
    """CREATE TABLE analyses(
        lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
        state TEXT NOT NULL,
        payload_json TEXT,
        updated_at TEXT NOT NULL,
        error TEXT NOT NULL,
        origin TEXT NOT NULL
    )""",
    """CREATE TABLE processing_queue(
        lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        error TEXT NOT NULL
    )""",
    """CREATE TABLE destinations(
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
    """CREATE TABLE sync_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connector TEXT NOT NULL,
        status TEXT NOT NULL,
        added INTEGER NOT NULL DEFAULT 0,
        skipped INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL,
        completed_at TEXT NOT NULL
    )""",
    """CREATE TABLE review_cards(
        lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
        interval_days REAL NOT NULL DEFAULT 0,
        repetitions INTEGER NOT NULL DEFAULT 0,
        due_at TEXT NOT NULL,
        reviewed_at TEXT NOT NULL,
        last_rating TEXT NOT NULL
    )""",
    "CREATE INDEX idx_review_cards_due ON review_cards(due_at)",
    """CREATE TABLE enrichments(
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
]

ANKI_RUN_AT = "2026-08-01T09:00:00+00:00"
QUIZLET_RUN_AT = "2026-08-15T18:30:00+00:00"
OBSIDIAN_RUN_AT = "2026-09-02T07:45:00+00:00"
BOOK_A = ("book-lighthouse", "The Lighthouse Keeper", "A. Writer")
BOOK_B = ("koreader:book-river", "Down the River", "B. Author")


def lid(key: str, language: str = "en") -> str:
    return vocab_cache.lexeme_id(language, key)


def _analysis(base: str, *, accepted: bool, score: int) -> str:
    return json.dumps(
        {
            "accepted": accepted,
            "base_form": base,
            "importance_score": score,
            "warnings": [] if accepted else ["non_word"],
            "translation_status": "offline_only",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


# (key, language, display, freshness, first_seen, last_seen, kindle, legacy)
LEXEMES = [
    ("lantern", "en", "lanterns", "known", "2026-06-01T10:00:00+00:00",
     "2026-09-01T10:00:00+00:00", 1, 0),
    ("meander", "en", "meandering", "known", "2026-06-01T10:00:00+00:00",
     "2026-08-20T10:00:00+00:00", 1, 1),
    ("quibble", "en", "quibbles", "known", "2026-06-05T10:00:00+00:00",
     "2026-06-05T10:00:00+00:00", 1, 0),
    ("zephyr", "en", "zephyr", "new", "2026-09-30T10:00:00+00:00",
     "2026-09-30T10:00:00+00:00", 1, 0),
    ("tarn", "en", "tarns", "new", "2026-09-30T10:00:00+00:00",
     "2026-09-30T10:00:00+00:00", 1, 0),
    ("brogue", "en", "brogue", "known", "2026-07-01T10:00:00+00:00",
     "2026-07-01T10:00:00+00:00", 0, 1),
    ("fernweh", "de", "Fernweh", "new", "2026-09-30T10:00:00+00:00",
     "2026-09-30T10:00:00+00:00", 1, 0),
]


def build_v3_library(workspace: Path) -> Path:
    """Create `.app-data/kindle_cards.sqlite3` in schema v3 with synthetic rows."""
    path = workspace / ".app-data" / DATABASE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        for statement in V3_DDL:
            connection.execute(statement)
        connection.executemany(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            [(1, "2026-05-01T00:00:00+00:00"), (2, "2026-06-01T00:00:00+00:00"),
             (3, "2026-07-01T00:00:00+00:00")],
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("updated_at", "2026-10-01T10:00:00+00:00"),
                ("last_kindle_sync_id", "sync-2"),
                ("legacy_migration_completed", "2026-05-01T00:00:00+00:00"),
            ],
        )
        for key, language, display, freshness, first, last, kindle, legacy in LEXEMES:
            connection.execute(
                "INSERT INTO lexemes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lid(key, language), language, key, display, freshness, first, last,
                 "sync-2" if freshness == "new" else "sync-1", kindle, legacy),
            )
        # Forms in a deliberately non-alphabetical insertion order: rowid order matters.
        forms = [
            ("lantern", "lanterns"), ("lantern", "lantern"), ("lantern", "Lantern's"),
            ("meander", "meandering"), ("meander", "meander"), ("meander", "meandered"),
            ("quibble", "quibbles"), ("zephyr", "zephyr"), ("tarn", "tarns"),
            ("tarn", "tarn"),
        ]
        for key, form in forms:
            connection.execute(
                "INSERT INTO forms VALUES (?, ?, ?)",
                (lid(key), form, vocab_cache.normalize_lemma(form)),
            )
        connection.execute(
            "INSERT INTO forms VALUES (?, ?, ?)", (lid("fernweh", "de"), "Fernweh", "fernweh")
        )
        occurrences = [
            ("occ-l3", "lantern", "kindle", "lanterns", "Two lanterns swung over the dock.",
             BOOK_A, "2026-09-01T10:00:00+00:00"),
            ("occ-l1", "lantern", "kindle", "lantern", "She lit the lantern at dusk.",
             BOOK_A, "2026-06-01T10:00:00+00:00"),
            ("occ-l2", "lantern", "koreader", "lanterns", "Paper lanterns drifted downstream.",
             BOOK_B, "2026-06-01T10:00:00+00:00"),
            ("occ-m1", "meander", "kindle", "meandering", "A meandering path led home.",
             BOOK_A, "2026-06-01T10:00:00+00:00"),
            ("occ-m2", "meander", "kindle", "meandered", "The river meandered for miles.",
             BOOK_B, "2026-08-20T10:00:00+00:00"),
            ("occ-q1", "quibble", "kindle", "quibbles", "No time for quibbles.",
             BOOK_A, "2026-06-05T10:00:00+00:00"),
            ("occ-z1", "zephyr", "kindle", "zephyr", "A zephyr stirred the sails.",
             BOOK_B, "2026-09-30T10:00:00+00:00"),
            ("occ-t1", "tarn", "kindle", "tarns", "Cold tarns lay between the peaks.",
             BOOK_B, "2026-09-30T10:00:00+00:00"),
            ("occ-b1", "brogue", "legacy", "brogue", "", ("", "", ""), ""),
        ]
        for occ_id, key, source, word, context, book, looked_up_at in occurrences:
            connection.execute(
                "INSERT INTO occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (occ_id, lid(key), source, word, context, *book, looked_up_at),
            )
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("occ-f1", lid("fernweh", "de"), "kindle", "Fernweh", "Er hatte Fernweh.",
             *BOOK_A, "2026-09-30T10:00:00+00:00"),
        )
        analyses = [
            ("lantern", "ready", _analysis("lantern", accepted=True, score=7),
             "2026-06-02T00:00:00+00:00", "", "sqlite_optimizer"),
            ("meander", "ready", _analysis("meander", accepted=True, score=5),
             "2026-06-02T00:00:00+00:00", "", "legacy_catalog"),
            ("quibble", "rejected", _analysis("quibble", accepted=False, score=1),
             "2026-06-06T00:00:00+00:00", "", "sqlite_optimizer"),
            ("zephyr", "pending", None, "", "", "catalog"),
            ("tarn", "failed", None, "2026-09-30T11:00:00+00:00", "timeout", "catalog"),
        ]
        for key, state, payload, updated, error, origin in analyses:
            connection.execute(
                "INSERT INTO analyses VALUES (?, ?, ?, ?, ?, ?)",
                (lid(key), state, payload, updated, error, origin),
            )
        connection.executemany(
            "INSERT INTO processing_queue VALUES (?, ?, ?, ?, ?)",
            [
                (lid("zephyr"), "pending", "2026-09-30T10:00:00+00:00",
                 "2026-09-30T10:00:00+00:00", ""),
                (lid("tarn"), "failed", "2026-09-30T10:00:00+00:00",
                 "2026-09-30T11:00:00+00:00", "timeout"),
                (lid("fernweh", "de"), "pending", "2026-09-30T10:00:00+00:00",
                 "2026-09-30T10:00:00+00:00", ""),
            ],
        )
        destinations = [
            ("lantern", "obsidian", "synced", 1, "", "lantern", OBSIDIAN_RUN_AT,
             OBSIDIAN_RUN_AT, ""),
            ("lantern", "anki", "exported", 0, "", "", "", "", ANKI_RUN_AT),
            ("lantern", "quizlet", "exported", 0, "", "", "", "", QUIZLET_RUN_AT),
            ("meander", "obsidian", "synced", 1, "", "meander", OBSIDIAN_RUN_AT,
             OBSIDIAN_RUN_AT, ""),
            ("meander", "anki", "exported", 0, "", "", "", "", ANKI_RUN_AT),
            ("meander", "quizlet", "not_exported", 0, "", "", "", "", ""),
            ("quibble", "obsidian", "not_applicable", 0, "rejected", "quibble", "", "", ""),
            ("quibble", "anki", "not_exported", 0, "", "", "", "", ""),
            ("zephyr", "obsidian", "not_applicable", 0, "waiting_processing", "zephyr",
             "", "", ""),
            ("tarn", "obsidian", "not_applicable", 0, "processing_failed", "tarn", "", "", ""),
            # An export with a lost timestamp still counts as a past export.
            ("tarn", "anki", "exported", 0, "", "", "", "", ""),
        ]
        for key, *rest in destinations:
            connection.execute(
                "INSERT INTO destinations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lid(key), *rest),
            )
        connection.execute(
            "INSERT INTO sync_runs(connector, status, added, skipped, error, completed_at)"
            " VALUES ('kindle', 'completed', 3, 0, '', '2026-09-30T10:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO review_cards VALUES (?, 3.0, 1, ?, ?, 'good')",
            (lid("lantern"), "2026-08-05T00:00:00+00:00", "2026-08-02T00:00:00+00:00"),
        )
        connection.executemany(
            "INSERT INTO enrichments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("en", "lantern", "ready", "openai_compatible", "test-model", 2,
                 '{"meaning_ru": "фонарь", "note": "synthetic"}', "",
                 "2026-07-01T00:00:00+00:00"),
                ("en", "orphan", "failed", "openai_compatible", "test-model", 2, None,
                 "timeout", "2026-07-01T00:00:00+00:00"),
            ],
        )
        connection.commit()
    return path


EXPECTED_EXPORT_ITEMS = {
    # (destination, created_at) -> lexeme keys; None = timestamp was lost, so the
    # migration time stands in for it.
    ("anki", ANKI_RUN_AT): {"lantern", "meander"},
    ("csv", QUIZLET_RUN_AT): {"lantern"},
    ("obsidian", OBSIDIAN_RUN_AT): {"lantern", "meander"},
    ("anki", None): {"tarn"},
}
