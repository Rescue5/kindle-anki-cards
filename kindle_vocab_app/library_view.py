"""The library as the reader sees it: every processed word ranked, with its card and export state.

`decorate` adds the C0 parts (`contracts.LexemePayloadV4`) to the entries of a library response in
place and returns the library-level fields (`contracts.LibraryPayloadV4`). It builds `WordFacts`
from what the catalog and the reader's own rows already hold and calls `ranking.rank`; the
scoring itself stays in `ranking.py`.

Moments:
- `now` is the time of the latest lookup in the library, so a pause in reading does not empty the
  short list;
- `history_days` is the span between the first and the last lookup;
- the repeat signal is on when the library has lookups from a reader that keeps them (book keys
  without the `koreader:` / `kobo:` prefix), which decides the ranking mode.

The reader's decisions come from `word_decisions`, the export state from `export_items`; nothing
here is stored, every response is computed again.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from kindle_vocab_app import card_fields, export_policy
from kindle_vocab_app.contracts import BATCH_SIZE_DEFAULT, DISPUTED_CAP, StudyPriority
from kindle_vocab_app.library_state import parse_moment
from kindle_vocab_app.ranking import (
    RANKING_VERSION,
    SHELVES,
    WordFacts,
    library_mode,
    rank,
    structural_study_priority,
    study_priority,
)

# Books with a lookup in this many days before `now` count as being read (see `WordFacts`).
READING_DAYS = 14
# Book keys of readers that keep one row per word: they carry no repeat lookups.
NO_REPEAT_PREFIXES = ("koreader:", "kobo:")
_SCORE_DIGITS = 4
_WEIGHT_DIGITS = 3
_PRIORITY_PENDING_REASONS = {
    "pending": "Слово ожидает обработки",
    "processing": "Слово обрабатывается",
    "failed": "Обработка слова не удалась",
}


def decorate(
    entries: list[dict[str, Any]],
    *,
    decisions: Mapping[str, Mapping[str, Any]] | None = None,
    card_edits: Mapping[str, Mapping[str, Any]] | None = None,
    exported_at: Mapping[str, str] | None = None,
    batch_size: int = BATCH_SIZE_DEFAULT,
) -> dict[str, Any]:
    """Add `ranking`, `study_priority`, `decision`, `card`, `export` and `is_new` in place.

    Returns the library-level fields: `rankingVersion`, `rankingMode`, `historyDays`,
    `repeatSignal`, `shelves`, `newBatch`, `disputed` and `again`.
    """
    decisions = decisions or {}
    card_edits = card_edits or {}
    exported_at = exported_at or {}

    lookups = {str(entry.get("id") or ""): _lookups(entry) for entry in entries}
    moments = [moment for items in lookups.values() for moment, _ in items]
    now = max(moments) if moments else datetime.now(UTC)
    history_days = (now - min(moments)).days if moments else 0
    repeat_signal = any(
        book and not book.startswith(NO_REPEAT_PREFIXES)
        for items in lookups.values()
        for _, book in items
    )
    mode = library_mode(history_days, repeat_signal)
    reading_cutoff = now - timedelta(days=READING_DAYS)
    reading_books = frozenset(
        book for items in lookups.values() for moment, book in items if book and moment >= reading_cutoff
    )

    ranked: dict[str, Any] = {}
    for entry in entries:
        lexeme_id = str(entry.get("id") or "")
        state = str((entry.get("processing") or {}).get("state") or "")
        if state not in export_policy.PROCESSED_STATES:
            entry["study_priority"] = _provisional_priority(
                _PRIORITY_PENDING_REASONS.get(state, "Анализ слова ещё недоступен")
            )
            continue
        decision = decisions.get(lexeme_id)
        word_lookups = lookups[lexeme_id]
        facts = _facts(
            entry,
            word_lookups or [(_fallback_moment(entry, now), "")],
            reading_books,
            decision,
            exported_at.get(lexeme_id),
        )
        outcome = rank(facts, now, mode=mode)
        ranked[lexeme_id] = outcome
        token = str(entry.get("lemma") or entry.get("display_form") or "")
        structural = structural_study_priority(token)
        if structural is not None:
            entry["study_priority"] = structural
        elif not _has_lexical_analysis(entry):
            entry["study_priority"] = _provisional_priority("Недостаточно данных анализа")
        elif not word_lookups:
            entry["study_priority"] = _provisional_priority("Нет даты поиска слова")
        else:
            entry["study_priority"] = study_priority(
                facts,
                now,
                mode=mode,
                token=token,
                assessed=outcome,
            )

    positions = _positions(entries, ranked)
    for entry in entries:
        lexeme_id = str(entry.get("id") or "")
        outcome = ranked.get(lexeme_id)
        entry["ranking"] = _ranking_payload(outcome, positions.get(lexeme_id, 0)) if outcome else None
        decision = decisions.get(lexeme_id)
        entry["decision"] = (
            {"value": str(decision["value"]), "decided_at": str(decision["decided_at"])}
            if decision
            else None
        )
        entry["card"] = card_fields.resolve(entry, card_edits.get(lexeme_id)).payload()
        stamp = str(exported_at.get(lexeme_id) or "")
        entry["export"] = _export_payload(stamp, lookups[lexeme_id])
        entry["is_new"] = entry.get("freshness") == "new" and not stamp

    shelves = dict.fromkeys(SHELVES, 0)
    for outcome in ranked.values():
        shelves[outcome.shelf] += 1
    return {
        "rankingVersion": RANKING_VERSION,
        "rankingMode": mode,
        "historyDays": history_days,
        "repeatSignal": repeat_signal,
        "shelves": shelves,
        "newBatch": new_batch(entries, batch_size),
        "disputed": disputed(entries),
        # Words looked up again after an export come back in a later stage (M4).
        "again": {"count": 0, "ids": [], "unavailable": not repeat_signal},
    }


def exportable_ids(entries: Iterable[Mapping[str, Any]]) -> list[str]:
    """Ids of every exportable word not yet exported, best rank first (before the batch cut)."""
    candidates = [
        entry
        for entry in entries
        if export_policy.is_exportable(entry) and entry["export"]["state"] != "exported"
    ]
    candidates.sort(key=lambda entry: (entry["ranking"]["rank"], str(entry.get("id") or "")))
    return [str(entry["id"]) for entry in candidates]


def new_batch(entries: Iterable[Mapping[str, Any]], batch_size: int) -> dict[str, Any]:
    """The short list: exportable, not yet exported words by rank, cut at the batch size."""
    ids = exportable_ids(entries)[: max(0, int(batch_size))]
    return {"count": len(ids), "ids": ids}


def disputed(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Disputed words still waiting for an answer: not exported, no decision, best score first."""
    pool = [
        entry
        for entry in entries
        if entry["ranking"]
        and entry["ranking"]["shelf"] == "disputed"
        and entry["export"]["state"] != "exported"
        and not entry["decision"]
    ]
    pool.sort(key=lambda entry: (entry["ranking"]["rank"], str(entry.get("id") or "")))
    return {"ids": [str(entry["id"]) for entry in pool[:DISPUTED_CAP]]}


# --- parts ------------------------------------------------------------------------------------


def _lookups(entry: Mapping[str, Any]) -> list[tuple[datetime, str]]:
    """(when, book key) of every occurrence with a readable lookup time, oldest first."""
    found = []
    for occurrence in entry.get("occurrences") or []:
        moment = parse_moment(str(occurrence.get("looked_up_at") or ""))
        if moment is not None:
            found.append((moment, str(occurrence.get("book_key") or "")))
    found.sort(key=lambda item: item[0])
    return found


def _fallback_moment(entry: Mapping[str, Any], now: datetime) -> datetime:
    """A word with no readable lookup time (an old import) counts from when it first appeared."""
    return parse_moment(str(entry.get("first_seen_at") or "")) or now


def _provisional_priority(reason: str) -> StudyPriority:
    return {"level": 6, "score": 0.0, "provisional": True, "reason": reason}


def _has_lexical_analysis(entry: Mapping[str, Any]) -> bool:
    analysis = (entry.get("processing") or {}).get("analysis") or {}
    def measured(value: Any) -> bool:
        return type(value) in (int, float) and math.isfinite(value)

    frequencies = [analysis.get(key) for key in ("lemma_zipf", "form_zipf")]
    synsets = analysis.get("wordnet_synset_count")
    # Positive evidence suffices. Inferring a word is unknown takes measurements from both sources.
    return any(measured(value) and value > 0 for value in [*frequencies, synsets]) or (
        measured(synsets) and any(measured(value) for value in frequencies)
    )


def _facts(
    entry: Mapping[str, Any],
    lookups: list[tuple[datetime, str]],
    reading_books: frozenset[str],
    decision: Mapping[str, Any] | None,
    exported: str | None,
) -> WordFacts:
    analysis = (entry.get("processing") or {}).get("analysis") or {}
    return WordFacts(
        lemma_zipf=_number(analysis.get("lemma_zipf")),
        form_zipf=_number(analysis.get("form_zipf")),
        synset_count=int(_number(analysis.get("wordnet_synset_count"))),
        pos_count=int(_number(analysis.get("wordnet_pos_count"))),
        warnings=frozenset(str(item) for item in analysis.get("warnings") or []),
        # Not wired: measured to change nothing (see the ranking notes).
        proper_noun=False,
        lookups=tuple(lookups),
        reading_books=reading_books,
        decision=str(decision["value"]) if decision else None,
        decided_at=parse_moment(str(decision["decided_at"])) if decision else None,
        exported_at=parse_moment(exported) if exported else None,
    )


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _positions(entries: list[dict[str, Any]], ranked: Mapping[str, Any]) -> dict[str, int]:
    """1-based place of every ranked word inside its shelf: best score first, ties by id."""
    by_shelf: dict[str, list[tuple[float, str]]] = {shelf: [] for shelf in SHELVES}
    for entry in entries:
        lexeme_id = str(entry.get("id") or "")
        outcome = ranked.get(lexeme_id)
        if outcome is not None:
            by_shelf[outcome.shelf].append((-outcome.score, lexeme_id))
    positions: dict[str, int] = {}
    for items in by_shelf.values():
        items.sort()
        for place, (_, lexeme_id) in enumerate(items, 1):
            positions[lexeme_id] = place
    return positions


def _ranking_payload(outcome: Any, position: int) -> dict[str, Any]:
    return {
        "score": round(outcome.score, _SCORE_DIGITS),
        "shelf": outcome.shelf,
        "rank": position,
        "lean": outcome.lean,
        "reasons": [
            {
                "code": reason.code,
                "text": reason.text,
                "weight": round(reason.weight, _WEIGHT_DIGITS) + 0.0,
            }
            for reason in outcome.reasons
        ],
        "version": RANKING_VERSION,
    }


def _export_payload(stamp: str, lookups: list[tuple[datetime, str]]) -> dict[str, Any]:
    moment = parse_moment(stamp) if stamp else None
    after = sum(1 for when, _ in lookups if moment is not None and when > moment)
    return {
        "state": "exported" if stamp else "not_exported",
        "last_exported_at": stamp,
        "again": False,
        "lookups_after": after,
    }
