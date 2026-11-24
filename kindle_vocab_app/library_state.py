"""The reader's own rows: decisions, card edits, and keeping them linked to their words.

`word_decisions`, `card_edits` and `export_items` are keyed by `lexeme_id` without a foreign
key, so a catalog save (which deletes and re-inserts `lexemes`) never cascades into them. Each
row also keeps `language` + `canonical_key` as a re-link hint.

Writes (`set_decision`, `save_card_edit`) go straight to their table in one short
`BEGIN IMMEDIATE` transaction and never through `save_catalog`, so they cannot race with the
load-mutate-save cycle of `process_queue`.

Re-link (`follow_key_change` when `save_processed_lexeme` changes a word's key under the
same id, `relink` after every catalog replacement and after `save_processed_lexeme`, always
inside the caller's write transaction) moves an orphaned row (no word has both its id and its
hint) to the lexeme that took its place. Readers apply a row only when id and hint match. When two rows land on one word
(two keys merged), the newest stays linked and the other is detached: its `lexeme_id` gets the
`DETACHED_MARK` suffix so it is never linked again, and it is kept, never deleted.

Logs carry counts only, never words.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from kindle_vocab_app.contracts import ERROR_TEXTS, MEANING_MAX_LENGTH
from kindle_vocab_app.logging_config import get_logger
from kindle_vocab_app.ranking import DECISIONS, SHELVES
from kindle_vocab_app.vocab_cache import utc_now

logger = get_logger(__name__)

# Lexeme ids are SHA-1 hex strings, so this mark never collides with a real id.
DETACHED_MARK = "#merged"
_UNSET: Any = object()

# table -> the timestamp that decides which of two rows on one word is newer
_KEYED_TABLES = {"word_decisions": "decided_at", "card_edits": "updated_at"}
_HINTED_TABLES = ("word_decisions", "card_edits", "export_items")
_ANKI_NOTE_KEYS = "anki_note_keys_v1"
AnkiIdentity = tuple[str, str, str]  # lexeme id, language, canonical key


class LibraryStateError(ValueError):
    """A reader-facing error: `str(error)` is the Russian text, `code` is from contracts.ERROR_CODES."""

    def __init__(self, code: str) -> None:
        super().__init__(ERROR_TEXTS[code])
        self.code = code


# --- writes -----------------------------------------------------------------------------------


def set_decision(
    connection: sqlite3.Connection,
    lexeme_id: str,
    decision: str | None,
    *,
    shelf_at: str = "",
    score_at: float | None = None,
    ranking_version: str = "",
) -> dict[str, Any] | None:
    """Store the reader's decision for one word, or remove it when `decision` is None.

    `shelf_at`, `score_at` and `ranking_version` describe the ranking at the moment of the
    decision (training data for a later learner). Returns the stored record, None after removal.
    """
    if decision is not None and (not isinstance(decision, str) or decision not in DECISIONS):
        raise LibraryStateError("bad_decision")
    if shelf_at and shelf_at not in SHELVES:
        raise TypeError(f"shelf_at must be one of {SHELVES} or empty")
    if score_at is not None and (isinstance(score_at, bool) or not isinstance(score_at, int | float)):
        raise TypeError("score_at must be a number or None")
    _begin_immediate(connection)
    language, canonical_key = _lexeme_identity(connection, lexeme_id)
    _detach_stale(connection, "word_decisions", lexeme_id, language, canonical_key)
    if decision is None:
        connection.execute("DELETE FROM word_decisions WHERE lexeme_id = ?", (lexeme_id,))
        return None
    decided_at = utc_now()
    connection.execute(
        """
        INSERT OR REPLACE INTO word_decisions(
            lexeme_id, language, canonical_key, decision, decided_at,
            shelf_at, score_at, ranking_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lexeme_id,
            language,
            canonical_key,
            decision,
            decided_at,
            shelf_at,
            None if score_at is None else float(score_at),
            str(ranking_version or ""),
        ),
    )
    return {
        "value": decision,
        "decided_at": decided_at,
        "shelf_at": shelf_at,
        "score_at": None if score_at is None else float(score_at),
        "ranking_version": str(ranking_version or ""),
    }


def save_card_edit(
    connection: sqlite3.Connection,
    lexeme_id: str,
    *,
    meaning_ru: str | None = _UNSET,
    example_occurrence_id: str | None = _UNSET,
) -> dict[str, Any] | None:
    """Change the reader's translation and/or chosen example of one word.

    An argument that is not given is left as it is. Every whitespace run in `meaning_ru`
    becomes one space (a tab or newline would break a TSV/CSV row); "" (or None) removes the
    edited translation. `example_occurrence_id` "" (or None) removes the choice;
    otherwise it must be an occurrence of this word. When nothing edited is left the row is
    removed. Returns the stored record, or None when there is none.
    """
    meaning: str | None = _UNSET
    if meaning_ru is not _UNSET:
        if meaning_ru is not None and not isinstance(meaning_ru, str):
            raise TypeError("meaning_ru must be a string")
        meaning = " ".join((meaning_ru or "").split()) or None
        if meaning is not None and len(meaning) > MEANING_MAX_LENGTH:
            raise LibraryStateError("too_long")
    if (
        example_occurrence_id is not _UNSET
        and example_occurrence_id is not None
        and not isinstance(example_occurrence_id, str)
    ):
        raise TypeError("example_occurrence_id must be a string")

    _begin_immediate(connection)
    language, canonical_key = _lexeme_identity(connection, lexeme_id)
    _detach_stale(connection, "card_edits", lexeme_id, language, canonical_key)
    current = connection.execute(
        """
        SELECT meaning_ru, example_occurrence_id, example_context, example_form
        FROM card_edits WHERE lexeme_id = ?
        """,
        (lexeme_id,),
    ).fetchone()
    record = {
        "meaning_ru": current["meaning_ru"] if current else None,
        "example_occurrence_id": current["example_occurrence_id"] if current else None,
        "example_context": str(current["example_context"]) if current else "",
        "example_form": str(current["example_form"]) if current else "",
    }
    if meaning is not _UNSET:
        record["meaning_ru"] = meaning
    if example_occurrence_id is not _UNSET:
        if example_occurrence_id:
            occurrence = connection.execute(
                "SELECT context, word FROM occurrences WHERE id = ? AND lexeme_id = ?",
                (example_occurrence_id, lexeme_id),
            ).fetchone()
            if occurrence is None:
                raise LibraryStateError("example_not_found")
            record.update(
                example_occurrence_id=example_occurrence_id,
                example_context=str(occurrence["context"]),
                example_form=str(occurrence["word"]),
            )
        else:
            record.update(example_occurrence_id=None, example_context="", example_form="")

    if record["meaning_ru"] is None and not record["example_occurrence_id"]:
        connection.execute("DELETE FROM card_edits WHERE lexeme_id = ?", (lexeme_id,))
        return None
    updated_at = utc_now()
    connection.execute(
        """
        INSERT OR REPLACE INTO card_edits(
            lexeme_id, language, canonical_key, meaning_ru, example_occurrence_id,
            example_context, example_form, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lexeme_id,
            language,
            canonical_key,
            record["meaning_ru"],
            record["example_occurrence_id"],
            record["example_context"],
            record["example_form"],
            updated_at,
        ),
    )
    return {**record, "updated_at": updated_at}


def _begin_immediate(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise RuntimeError("a user write must start its own transaction")
    connection.execute("BEGIN IMMEDIATE")


def _detach_stale(
    connection: sqlite3.Connection, table: str, lexeme_id: str, language: str, canonical_key: str
) -> None:
    """A row left on this id by another word (see `relink`) is kept aside, never overwritten."""
    row = connection.execute(
        f"SELECT language, canonical_key FROM {table} WHERE lexeme_id = ?", (lexeme_id,)
    ).fetchone()
    if row is not None and (str(row[0]), str(row[1])) != (language, canonical_key):
        _detach(connection, table, lexeme_id)


def _lexeme_identity(connection: sqlite3.Connection, lexeme_id: str) -> tuple[str, str]:
    row = connection.execute(
        "SELECT language, canonical_key FROM lexemes WHERE id = ?", (str(lexeme_id),)
    ).fetchone()
    if row is None:
        raise LibraryStateError("unknown_lexeme")
    return str(row["language"]), str(row["canonical_key"])


# --- bulk readers (one query each; only rows whose id and hint both match a word) ------------


def read_decisions(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(row["lexeme_id"]): {
            "value": str(row["decision"]),
            "decided_at": str(row["decided_at"]),
            "shelf_at": str(row["shelf_at"]),
            "score_at": None if row["score_at"] is None else float(row["score_at"]),
            "ranking_version": str(row["ranking_version"]),
        }
        for row in connection.execute(
            """
            SELECT d.lexeme_id, d.decision, d.decided_at, d.shelf_at, d.score_at,
                   d.ranking_version
            FROM word_decisions AS d JOIN lexemes AS l
              ON l.id = d.lexeme_id AND l.language = d.language
             AND l.canonical_key = d.canonical_key
            """
        )
    }


def read_card_edits(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(row["lexeme_id"]): {
            "meaning_ru": None if row["meaning_ru"] is None else str(row["meaning_ru"]),
            "example_occurrence_id": str(row["example_occurrence_id"] or ""),
            "example_context": str(row["example_context"]),
            "example_form": str(row["example_form"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in connection.execute(
            """
            SELECT e.lexeme_id, e.meaning_ru, e.example_occurrence_id, e.example_context,
                   e.example_form, e.updated_at
            FROM card_edits AS e JOIN lexemes AS l
              ON l.id = e.lexeme_id AND l.language = e.language
             AND l.canonical_key = e.canonical_key
            """
        )
    }


def read_last_exports(connection: sqlite3.Connection) -> dict[str, str]:
    """Latest export time per word over every run, migrated ones included (`created_at` as stored).

    Only rows whose id and hint both match a word count, like the other readers.
    """
    latest: dict[str, tuple[datetime, str]] = {}
    for row in connection.execute(
        """
        SELECT i.lexeme_id, r.created_at
        FROM export_items AS i
        JOIN export_runs AS r ON r.id = i.run_id
        JOIN lexemes AS l
          ON l.id = i.lexeme_id AND l.language = i.language AND l.canonical_key = i.canonical_key
        """
    ):
        stamp = str(row["created_at"])
        moment = parse_moment(stamp) or datetime.min.replace(tzinfo=UTC)
        known = latest.get(str(row["lexeme_id"]))
        if known is None or moment > known[0]:
            latest[str(row["lexeme_id"])] = (moment, stamp)
    return {lexeme_id: stamp for lexeme_id, (_, stamp) in latest.items()}


def record_export_run(
    connection: sqlite3.Connection,
    destination: str,
    lexeme_ids: Sequence[str],
    *,
    path: str = "",
    scope: str = "new",
) -> int:
    """Append one export run and its words in a single transaction; returns the run id.

    Call it only after the push or the file succeeded. Nothing is written when any word is
    unknown, so a run never names a word the library does not have.
    """
    ids = list(dict.fromkeys(str(item) for item in lexeme_ids))
    _begin_immediate(connection)
    previously_exported = read_last_exports(connection) if scope == "again" else {}
    identities = []
    for lexeme_id in ids:
        language, canonical_key = _lexeme_identity(connection, lexeme_id)
        identities.append((lexeme_id, language, canonical_key))
    cursor = connection.execute(
        "INSERT INTO export_runs(destination, scope, created_at, word_count, path) VALUES (?, ?, ?, ?, ?)",
        (destination, scope, utc_now(), len(identities), path),
    )
    run_id = int(cursor.lastrowid or 0)
    connection.executemany(
        "INSERT INTO export_items(run_id, lexeme_id, language, canonical_key, is_repeat) VALUES (?, ?, ?, ?, ?)",
        [(run_id, *identity, int(identity[0] in previously_exported)) for identity in identities],
    )
    return run_id


def parse_moment(text: str) -> datetime | None:
    """Read a stored time; a bare date is midnight UTC, a time without a zone is UTC."""
    try:
        moment = datetime.fromisoformat((text or "").strip())
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _read_anki_note_keys(connection: sqlite3.Connection) -> dict[str, AnkiIdentity | None]:
    row = connection.execute("SELECT value FROM metadata WHERE key = ?", (_ANKI_NOTE_KEYS,)).fetchone()
    if row is None:
        return {}
    return {seed: tuple(value) if value is not None else None for seed, value in json.loads(row["value"]).items()}


def _write_anki_note_keys(connection: sqlite3.Connection, notes: Mapping[str, AnkiIdentity | None]) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        (_ANKI_NOTE_KEYS, json.dumps(notes, ensure_ascii=False, sort_keys=True)),
    )


def remember_legacy_anki_note_keys(connection: sqlite3.Connection) -> None:
    """Preserve the former id-derived GUID while its historical identity is still available."""
    notes = _read_anki_note_keys(connection)
    targets = set(notes.values())
    added = False
    for row in connection.execute(
        """
        SELECT i.lexeme_id, i.language, i.canonical_key
        FROM export_items AS i JOIN export_runs AS r ON r.id = i.run_id
        JOIN lexemes AS l ON l.id = i.lexeme_id AND l.language = i.language AND l.canonical_key = i.canonical_key
        WHERE r.destination = 'anki'
        UNION
        SELECT l.id, l.language, l.canonical_key
        FROM destinations AS d JOIN lexemes AS l ON l.id = d.lexeme_id
        WHERE d.destination = 'anki' AND d.state = 'exported'
        """
    ):
        identity = (str(row[0]), str(row[1]), str(row[2]))
        seed = identity[0]
        if identity not in targets and seed not in notes:
            notes[seed] = identity
            targets.add(identity)
            added = True
    if added:
        _write_anki_note_keys(connection, notes)


def reserve_anki_note_keys(
    connection: sqlite3.Connection, identities: Sequence[AnkiIdentity],
) -> dict[str, str]:
    """Reserve a stable GUID seed before a package can reach Anki or the export folder."""
    _begin_immediate(connection)
    notes = _read_anki_note_keys(connection)
    by_identity = {identity: seed for seed, identity in notes.items() if identity is not None}
    added = False
    result = {}
    for identity in identities:
        lexeme_id, language, key = identity
        if _lexeme_identity(connection, lexeme_id) != (language, key):
            raise LibraryStateError("unknown_lexeme")
        seed = by_identity.get(identity)
        if seed is None:
            seed = lexeme_id
            while seed in notes:
                seed = uuid.uuid4().hex
            notes[seed] = identity
            by_identity[identity] = seed
            added = True
        result[lexeme_id] = seed
    if added:
        _write_anki_note_keys(connection, notes)
    return result


# --- re-link ----------------------------------------------------------------------------------


def follow_key_change(
    connection: sqlite3.Connection,
    lexeme_id: str,
    old: tuple[str, str],
    new: tuple[str, str],
) -> None:
    """A word kept its id but got a new (language, canonical_key): its rows follow it.

    Only rows that carried the word's old identity move; a row left on this id by another
    word keeps its own hint.
    """
    if old == new:
        return
    notes = _read_anki_note_keys(connection)
    for seed, identity in notes.items():
        if identity == (lexeme_id, *old):
            notes[seed] = (lexeme_id, *new)
            _write_anki_note_keys(connection, notes)
            break
    for table in _HINTED_TABLES:
        connection.execute(
            f"""
            UPDATE {table} SET language = ?, canonical_key = ?
            WHERE lexeme_id = ? AND language = ? AND canonical_key = ?
            """,
            (*new, lexeme_id, *old),
        )


# A row is orphaned when no word has both its id and its hint: the word is gone, or its id now
# belongs to a different word (an id computed from one key, kept after the key changed).
_ORPHANED = """NOT EXISTS (
    SELECT 1 FROM lexemes AS l
    WHERE l.id = {table}.lexeme_id AND l.language = {table}.language
      AND l.canonical_key = {table}.canonical_key
)"""
_PARKED_MARK = "#relink"


def relink(
    connection: sqlite3.Connection, id_map: Mapping[str, str] | None = None
) -> dict[str, int]:
    """Move orphaned rows to the word that replaced theirs.

    The target is found by `id_map` (old id -> new id, from catalog canonicalisation), then
    by the hint (language, canonical_key), then by a form of exactly one word of that language.
    Runs inside the caller's write transaction. Returns counts; logs them when any is non-zero.
    """
    counts = {
        "decisions": 0,
        "edits": 0,
        "export_items": 0,
        "detached": 0,
        "export_conflicts": 0,
        "unresolved": 0,
    }
    resolver = _TargetResolver(connection, id_map or {})
    if id_map is not None:
        _relink_anki_note_keys(connection, resolver)
    for table, stamp in _KEYED_TABLES.items():
        orphaned = _ORPHANED.format(table=table)
        # Rows sitting on an id that now belongs to another word are parked first, so the
        # word's own row (if one moves in) never collides with them.
        connection.execute(
            f"""
            UPDATE {table} SET lexeme_id = lexeme_id || ?
            WHERE lexeme_id IN (SELECT id FROM lexemes) AND {orphaned}
            """,
            (_PARKED_MARK,),
        )
        orphans = connection.execute(
            f"""
            SELECT lexeme_id, language, canonical_key, {stamp} AS stamp FROM {table}
            WHERE {orphaned} AND instr(lexeme_id, ?) = 0
            ORDER BY {stamp}, lexeme_id
            """,
            (DETACHED_MARK,),
        ).fetchall()
        for orphan in orphans:
            orphan_id = str(orphan["lexeme_id"])
            original_id = orphan_id.removesuffix(_PARKED_MARK)
            target = resolver.find(orphan, original_id)
            if target is None:
                counts["unresolved"] += 1
                if orphan_id != original_id:
                    _unpark(connection, table, orphan_id, original_id)
                continue
            target_id, language, canonical_key = target
            holder = connection.execute(
                f"SELECT {stamp} AS stamp FROM {table} WHERE lexeme_id = ?", (target_id,)
            ).fetchone()
            if holder is not None:
                counts["detached"] += 1
                if str(holder["stamp"]) >= str(orphan["stamp"]):
                    _detach(connection, table, orphan_id, original_id)
                    continue
                _detach(connection, table, target_id)
            connection.execute(
                f"UPDATE {table} SET lexeme_id = ?, language = ?, canonical_key = ? WHERE lexeme_id = ?",
                (target_id, language, canonical_key, orphan_id),
            )
            counts["decisions" if table == "word_decisions" else "edits"] += 1

    for orphan in connection.execute(
        f"""
        SELECT run_id, lexeme_id, language, canonical_key FROM export_items
        WHERE {_ORPHANED.format(table="export_items")}
        ORDER BY run_id, lexeme_id
        """
    ).fetchall():
        orphan_id = str(orphan["lexeme_id"])
        target = resolver.find(orphan, orphan_id)
        if target is None:
            counts["unresolved"] += 1
            continue
        target_id, language, canonical_key = target
        taken = target_id != orphan_id and connection.execute(
            "SELECT 1 FROM export_items WHERE run_id = ? AND lexeme_id = ?",
            (orphan["run_id"], target_id),
        ).fetchone() is not None
        if taken:
            # Both merged words were in the same run: the run already names the word once.
            counts["export_conflicts"] += 1
            continue
        connection.execute(
            """
            UPDATE export_items SET lexeme_id = ?, language = ?, canonical_key = ?
            WHERE run_id = ? AND lexeme_id = ?
            """,
            (target_id, language, canonical_key, orphan["run_id"], orphan_id),
        )
        counts["export_items"] += 1

    moved = counts["decisions"] + counts["edits"] + counts["export_items"] + counts["detached"]
    if any(counts.values()):
        # Rows that stay orphaned are counted on every save; only real moves are news.
        logger.log(
            logging.INFO if moved else logging.DEBUG,
            "Re-linked reader rows decisions=%d edits=%d export_items=%d detached=%d "
            "export_conflicts=%d unresolved=%d",
            *counts.values(),
        )
    return counts


def _unpark(connection: sqlite3.Connection, table: str, parked_id: str, original_id: str) -> None:
    """An orphan with nowhere to go returns to its id (readers skip it: its hint differs)."""
    free = connection.execute(
        f"SELECT 1 FROM {table} WHERE lexeme_id = ?", (original_id,)
    ).fetchone() is None
    if free:
        connection.execute(
            f"UPDATE {table} SET lexeme_id = ? WHERE lexeme_id = ?", (original_id, parked_id)
        )
    else:
        _detach(connection, table, parked_id, original_id)


class _TargetResolver:
    def __init__(self, connection: sqlite3.Connection, id_map: Mapping[str, str]) -> None:
        self._connection = connection
        self._id_map = id_map

    def find(self, orphan: sqlite3.Row | Mapping[str, str], original_id: str) -> AnkiIdentity | None:
        mapped = self._id_map.get(original_id)
        if mapped:
            row = self._connection.execute(
                "SELECT id, language, canonical_key FROM lexemes WHERE id = ?", (mapped,)
            ).fetchone()
            if row is not None:
                return str(row["id"]), str(row["language"]), str(row["canonical_key"])
        row = self._connection.execute(
            "SELECT id, language, canonical_key FROM lexemes WHERE language = ? AND canonical_key = ?",
            (orphan["language"], orphan["canonical_key"]),
        ).fetchone()
        if row is not None:
            return str(row["id"]), str(row["language"]), str(row["canonical_key"])
        rows = self._connection.execute(
            """
            SELECT DISTINCT l.id, l.language, l.canonical_key
            FROM forms AS f JOIN lexemes AS l ON l.id = f.lexeme_id
            WHERE f.normalized_form = ? AND l.language = ?
            LIMIT 2
            """,
            (orphan["canonical_key"], orphan["language"]),
        ).fetchall()
        if len(rows) == 1:
            return str(rows[0]["id"]), str(rows[0]["language"]), str(rows[0]["canonical_key"])
        return None


def _relink_anki_note_keys(connection: sqlite3.Connection, resolver: _TargetResolver) -> None:
    notes = _read_anki_note_keys(connection)
    if not notes:
        return
    live = {tuple(row) for row in connection.execute("SELECT id, language, canonical_key FROM lexemes")}
    taken = set(notes.values()) & live
    changed = False
    for seed, identity in notes.items():
        if identity is None or identity in live:
            continue
        lexeme_id, language, key = identity
        target = resolver.find({"language": language, "canonical_key": key}, lexeme_id)
        if target is not None:
            # Keep the surviving word's existing note. A retired seed is never reused.
            notes[seed] = None if target in taken else target
            taken.add(target)
            changed = True
    if changed:
        _write_anki_note_keys(connection, notes)


def _detach(
    connection: sqlite3.Connection, table: str, lexeme_id: str, base_id: str | None = None
) -> None:
    """Keep a row that lost a merge, under an id that is never linked again."""
    base = f"{base_id or lexeme_id}{DETACHED_MARK}"
    candidate, suffix = base, 1
    while connection.execute(
        f"SELECT 1 FROM {table} WHERE lexeme_id = ?", (candidate,)
    ).fetchone() is not None:
        suffix += 1
        candidate = f"{base}{suffix}"
    connection.execute(
        f"UPDATE {table} SET lexeme_id = ? WHERE lexeme_id = ?", (candidate, lexeme_id)
    )
