"""The bridge contract of the short-list release (C0): payload shapes, literals, error codes.

This module describes data; it does not compute any. The bridge builds these payloads, the
frontend reads them (`src/types.ts` mirrors every name here) and `tests/fixtures/bridge_library_v4.json`
is one example both sides check against. Change this file, `src/types.ts` and the fixture together.

Key case, as the existing payload already does it:

- request payloads and anything that describes one lexeme (`ranking`, `decision`, `card`,
  `export`, `is_new`, `lexeme_id`, `job_id`) use snake_case;
- library-level and action-result aggregates (`rankingMode`, `newBatch`, `blockedReason`,
  `runId`) use camelCase;
- the shelf names and other enum values are lowercase snake_case words.

The list payload carries what a list row shows. Analysis details come from `load_lexeme_details`.
Until the old screens are removed (B7) the library entries also keep their old fields; every
field added here is therefore optional in `src/types.ts` for now and required in `LexemeRecordV4`.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from kindle_vocab_app.ranking import (
    DECISIONS,
    RANKING_MODES,
    RANKING_VERSION,
    REASON_CODES,
    SHELVES,
)

__all__ = [
    "BATCH_SIZE_DEFAULT",
    "BATCH_SIZE_MAX",
    "BATCH_SIZE_MIN",
    "DISPUTED_CAP",
    "ERROR_CODES",
    "ERROR_TEXTS",
    "EXPORT_DESTINATIONS",
    "EXPORT_DESTINATION_DEFAULT",
    "MEANING_MAX_LENGTH",
    "RANKING_VERSION",
    "ActionError",
    "AgainSummary",
    "BlockedReason",
    "CardFields",
    "DecisionRecord",
    "DecisionResult",
    "DecisionValue",
    "DisputedSummary",
    "ErrorCode",
    "ExportBucket",
    "ExportDestination",
    "ExportInfo",
    "ExportPreview",
    "ExportRun",
    "ExportScope",
    "LeanValue",
    "LexemeDetails",
    "LexemePayloadV4",
    "LibraryPayloadV4",
    "MeaningSource",
    "NewBatch",
    "RankingInfo",
    "RankingMode",
    "ReasonInfo",
    "SaveCardEditResult",
    "Shelf",
    "ShelfCounts",
    "StudyPriority",
    "error_response",
    "validate_library",
]

# --- constants --------------------------------------------------------------------------------

# Settings keys `export_destination` and `export_batch_size` (validated in settings.py by B6).
EXPORT_DESTINATIONS = ("anki", "csv", "obsidian")
EXPORT_DESTINATION_DEFAULT = "anki"
BATCH_SIZE_DEFAULT = 20
BATCH_SIZE_MIN = 5
BATCH_SIZE_MAX = 100

# Meeting 2026-11-19 (second): at most this many disputed words, from the pool of the next batch.
DISPUTED_CAP = 5
# `card.meaning_ru` written by the reader may not be longer than this.
MEANING_MAX_LENGTH = 200

ERROR_CODES = (
    "no_destination",
    "too_long",
    "example_not_found",
    "nothing_to_export",
    "export_failed",
    "export_busy",
    "anki_import_unconfirmed",
    "anki_import_rejected",
    "unknown_lexeme",
    "bad_decision",
    "bad_scope",
    "bad_levels",
)

# `{"ok": false, "error": <text>, "code": <code>}`: `error` is always shown to the reader as is.
# For `export_failed` the bridge may append the cause after the text.
ERROR_TEXTS: dict[str, str] = {
    "no_destination": "Не выбрано, куда экспортировать. Выберите место в настройках.",
    "too_long": f"Перевод длиннее {MEANING_MAX_LENGTH} символов",
    "example_not_found": "Пример не относится к этому слову",
    "nothing_to_export": "Нет слов для экспорта",
    "export_failed": "Не удалось выполнить экспорт",
    "export_busy": "Выгрузка уже идёт. Дождитесь её завершения и попробуйте снова.",
    "anki_import_unconfirmed": (
        "Anki не подтвердил импорт. Колода сохранена в папке выгрузок. Проверьте Anki перед повторной отправкой."
    ),
    "anki_import_rejected": (
        "Anki отклонил импорт. Колода сохранена в папке выгрузок. Её можно открыть вручную."
    ),
    "unknown_lexeme": "Слово не найдено в библиотеке",
    "bad_decision": "Неизвестное решение. Допустимо: знаю, учить, не учить, не слово",
    "bad_scope": "Неизвестный набор слов для экспорта",
    "bad_levels": "Выберите хотя бы один уровень от 1 до 10",
}

# --- literals ---------------------------------------------------------------------------------

Shelf = Literal["worth", "disputed", "not_worth", "junk", "known"]
DecisionValue = Literal["known", "learn", "skip", "junk"]
LeanValue = Literal["learn", "skip", "junk"]
RankingMode = Literal["learning", "full"]
MeaningSource = Literal["edited", "llm", "dictionary", "none"]
ExportDestination = Literal["anki", "csv", "obsidian"]
ExportScope = Literal["new", "again", "library"]
ExportStateValue = Literal["exported", "not_exported"]
ErrorCode = Literal[
    "no_destination",
    "too_long",
    "example_not_found",
    "nothing_to_export",
    "export_failed",
    "export_busy",
    "anki_import_unconfirmed",
    "anki_import_rejected",
    "unknown_lexeme",
    "bad_decision",
    "bad_scope",
    "bad_levels",
]

# --- per-lexeme parts -------------------------------------------------------------------------


class ReasonInfo(TypedDict):
    code: str  # one of ranking.REASON_CODES
    text: str  # Russian, one short line; never cites a signal the source does not have
    weight: float  # > 0 for the word being worth learning, < 0 against, 0.0 for a reader's decision


class RankingInfo(TypedDict):
    score: float  # 0..1
    shelf: Shelf
    rank: int  # 1-based inside the shelf, best first
    lean: LeanValue | None  # the suggested answer; set only on the `disputed` shelf
    reasons: list[ReasonInfo]  # strongest first; every `not_worth` word has one against it
    version: str  # RANKING_VERSION


class StudyPriority(TypedDict):
    level: int  # 1 best, 10 possible recording error
    score: float  # 0..1; hybrid or within-provisional-group ordering score
    provisional: bool
    reason: str
    coverage_score: NotRequired[float | None]  # original RP-V2 share, null when unavailable
    personal_reason: NotRequired[str]  # compact explanation of the personal adjustment


class DecisionRecord(TypedDict):
    value: DecisionValue
    decided_at: str  # ISO 8601


class CardFields(TypedDict):
    meaning_ru: str  # the text a card would carry now; "" when meaning_source is "none"
    meaning_source: MeaningSource  # a ready LLM text or a reader's edit always beats the dictionary
    example_occurrence_id: str  # an id from the lexeme's occurrences, "" when there is none
    edited: bool  # the reader changed the meaning or picked the example


class ExportInfo(TypedDict):
    state: ExportStateValue
    last_exported_at: str  # ISO 8601, "" when not exported
    again: bool  # looked up again after last_exported_at (never true without a repeat signal)
    lookups_after: int  # lookups after last_exported_at, 0 when not exported


class LexemePayloadV4(TypedDict):
    """The parts added to every library entry; the entry keeps its old fields beside them."""

    ranking: RankingInfo | None  # None until the word is processed
    study_priority: StudyPriority  # for the library list; independent of manual decisions
    decision: DecisionRecord | None
    card: CardFields
    export: ExportInfo
    is_new: bool  # arrived with the latest reader sync and not exported yet


# --- library-level parts ----------------------------------------------------------------------

ShelfCounts = TypedDict(
    "ShelfCounts",
    {"worth": int, "disputed": int, "not_worth": int, "junk": int, "known": int},
)


class NewBatch(TypedDict):
    """The short list: `worth` words not yet exported, by rank, cut at `export_batch_size`.

    Disputed words are not in it; they are in `disputed`. A disputed word the reader answers
    «Учить» moves to `worth` and joins the short list in the next response. `count` is `len(ids)`.
    """

    count: int
    ids: list[str]
    availableIds: list[str]  # all currently exportable new words, in rank order before the batch cut


class DisputedSummary(TypedDict):
    """Disputed, not-yet-exported words that still need an answer: at most DISPUTED_CAP.

    Taken from the candidates of the next batch (best first), never listed in `newBatch.ids`;
    its length is what the Слова badge shows.
    """

    ids: list[str]


class AgainSummary(TypedDict):
    """Exported words looked up again afterwards.

    `unavailable` is true when the source keeps no repeat lookups (`repeatSignal` is false);
    then `count` is 0 and `ids` is empty, and the UI says nothing about it instead of "none".
    """

    count: int
    ids: list[str]
    unavailable: bool


class LibraryPayloadV4(TypedDict):
    """What `load_library` adds to the existing response (`LibraryResult` in `src/types.ts`)."""

    rankingVersion: str
    rankingMode: RankingMode
    historyDays: int  # days between the first and the last lookup, 0 for an empty library
    repeatSignal: bool  # the source keeps repeat lookups (Kindle does; KOReader and Kobo do not)
    studyPrioritySource: NotRequired[Literal["rp-v2-personal", "rp-v2-coverage", "legacy"]]
    shelves: ShelfCounts  # every ranked word of the library
    newBatch: NewBatch
    disputed: DisputedSummary
    again: AgainSummary


# --- actions ----------------------------------------------------------------------------------
# set_decision        {lexeme_id, decision: DecisionValue | null}  -> DecisionResult
# save_card_edit      {lexeme_id, meaning_ru?, example_occurrence_id?} -> SaveCardEditResult
#                     meaning_ru "" removes the edit (the card falls back to llm/dictionary);
#                     errors: too_long, example_not_found, unknown_lexeme
# export_preview      {}                                           -> ExportPreview
# export_words        {job_id, scope: "new", ids?}              -> ExportRun
# export_words        {job_id, scope: "library", ids, levels?}  -> ExportRun
#                     library uses only supplied ids; omitted levels mean all (1..10).
#                     ids defaults to the library's new batch. Reload the library after success.
#                     Import errors preserve the saved package and leave its words in the batch.
# export_folder_status {}                                          -> {available: bool}
# open_export_folder   {}                                          -> {opened: bool}
# load_lexeme_details {lexeme_id}                                  -> LexemeDetails
# Settings: export_destination (EXPORT_DESTINATIONS, default "anki"), export_batch_size (5..100,
# default 20). The destination is never sent by the UI with an export; it is read from settings.


class DecisionResult(TypedDict):
    entry: dict[str, Any]  # the updated library entry (ranking, decision, card, export, is_new)
    studyPrioritySource: NotRequired[Literal["rp-v2-personal", "rp-v2-coverage", "legacy"]]
    shelves: ShelfCounts
    newBatch: NewBatch
    disputed: DisputedSummary
    again: AgainSummary


class SaveCardEditResult(TypedDict):
    entry: dict[str, Any]


class BlockedReason(TypedDict):
    code: ErrorCode  # `no_destination` today
    text: str  # Russian, ready to show; tells where to fix it


class ExportBucket(TypedDict):
    count: int
    ids: list[str]


# `new` and `again` stay as the plan names them; they are not Python keywords.
class ExportPreview(TypedDict):
    destination: ExportDestination
    new: ExportBucket
    again: ExportBucket
    blockedReason: BlockedReason | None


class ExportRun(TypedDict):
    destination: ExportDestination
    runId: str
    exported: int
    path: str | None  # the written file, None for a push or a vault write
    pushed: int  # cards pushed to Anki, 0 otherwise
    message: str  # Russian summary the UI shows


class LexemeDetails(TypedDict):
    lexeme_id: str
    forms: list[str]
    occurrences: list[dict[str, Any]]  # LexemeOccurrence: id, context, book_title, looked_up_at, ...
    analysis: dict[str, Any] | None  # WordAnalysis
    enrichment: dict[str, Any] | None  # Enrichment
    dictionary: dict[str, Any] | None  # DictionaryMeaning


class ActionError(TypedDict):
    ok: Literal[False]
    error: str  # Russian text for the UI
    code: NotRequired[ErrorCode]  # absent for errors that have no code (the old ones)


def error_response(code: ErrorCode, detail: str = "") -> ActionError:
    """The failure envelope for a coded error; `detail` is appended after the fixed text."""
    if code not in ERROR_TEXTS:
        raise ValueError(f"Unknown error code: {code!r}")
    text = ERROR_TEXTS[code]
    return {"ok": False, "error": f"{text}: {detail}" if detail else text, "code": code}


# --- validation (used by the shared-fixture test and by bridge tests) -------------------------

_RANKING_KEYS = {"score", "shelf", "rank", "lean", "reasons", "version"}
_STUDY_PRIORITY_KEYS = {"level", "score", "provisional", "reason"}
_REASON_KEYS = {"code", "text", "weight"}
_DECISION_KEYS = {"value", "decided_at"}
_CARD_KEYS = {"meaning_ru", "meaning_source", "example_occurrence_id", "edited"}
_EXPORT_KEYS = {"state", "last_exported_at", "again", "lookups_after"}
_LIBRARY_KEYS = {
    "rankingVersion",
    "rankingMode",
    "historyDays",
    "repeatSignal",
    "shelves",
    "newBatch",
    "disputed",
    "again",
}
_SHELF_KEYS = set(SHELVES)
_MEANING_SOURCES = {"edited", "llm", "dictionary", "none"}


def _keys(problems: list[str], where: str, value: Any, expected: set[str]) -> bool:
    if not isinstance(value, dict):
        problems.append(f"{where}: expected an object")
        return False
    if set(value) != expected:
        problems.append(f"{where}: keys {sorted(value)} != {sorted(expected)}")
        return False
    return True


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def study_priority_order(priority: StudyPriority, lexeme_id: str) -> tuple[int, int, float, str]:
    level = priority["level"]
    group = 2 if level == 10 else int(priority["provisional"])
    return group, level, -priority["score"], lexeme_id


def _validate_study_priority(problems: list[str], where: str, priority: Any) -> None:
    expected_keys = _STUDY_PRIORITY_KEYS
    if isinstance(priority, dict):
        expected_keys = expected_keys | ({"coverage_score", "personal_reason"} & priority.keys())
    if not _keys(problems, where, priority, expected_keys):
        return
    level, score = priority["level"], priority["score"]
    if not _is_int(level) or not 1 <= level <= 10:
        problems.append(f"{where}.level: must be an integer in 1..10")
    if isinstance(score, bool) or not isinstance(score, int | float) or not 0.0 <= score <= 1.0:
        problems.append(f"{where}.score: not in 0..1")
    if "coverage_score" in priority:
        coverage_score = priority["coverage_score"]
        if coverage_score is not None and (
            isinstance(coverage_score, bool) or not isinstance(coverage_score, int | float)
            or not 0.0 <= coverage_score <= 1.0
        ):
            problems.append(f"{where}.coverage_score: not in 0..1")
    if not isinstance(priority["provisional"], bool):
        problems.append(f"{where}.provisional: must be a boolean")
    elif priority["provisional"]:
        personal_order = "coverage_score" in priority and priority["coverage_score"] is None
        if level != 6 or (score != 0 and not personal_order):
            problems.append(f"{where}: provisional priority must have level 6 and score 0 unless ordered by personal evidence")
    if not isinstance(priority["reason"], str) or not priority["reason"].strip():
        problems.append(f"{where}.reason: empty")
    if "personal_reason" in priority:
        personal_reason = priority["personal_reason"]
        if not isinstance(personal_reason, str) or not personal_reason.strip():
            problems.append(f"{where}.personal_reason: expected a non-empty string")


def _validate_ranking(problems: list[str], where: str, ranking: Any) -> None:
    if not _keys(problems, where, ranking, _RANKING_KEYS):
        return
    if not isinstance(ranking["score"], int | float) or not 0.0 <= ranking["score"] <= 1.0:
        problems.append(f"{where}.score: not in 0..1")
    if ranking["shelf"] not in SHELVES:
        problems.append(f"{where}.shelf: {ranking['shelf']!r}")
    if not _is_int(ranking["rank"]) or ranking["rank"] < 1:
        problems.append(f"{where}.rank: must be a 1-based integer")
    lean = ranking["lean"]
    if lean is not None and lean not in ("learn", "skip", "junk"):
        problems.append(f"{where}.lean: {lean!r}")
    if (lean is not None) != (ranking["shelf"] == "disputed"):
        problems.append(f"{where}.lean: set exactly on the disputed shelf")
    if ranking["version"] != RANKING_VERSION:
        problems.append(f"{where}.version: {ranking['version']!r} != {RANKING_VERSION!r}")
    reasons = ranking["reasons"]
    if not isinstance(reasons, list) or not reasons:
        problems.append(f"{where}.reasons: a ranked word has at least one reason")
        return
    for index, reason in enumerate(reasons):
        if not _keys(problems, f"{where}.reasons[{index}]", reason, _REASON_KEYS):
            continue
        if reason["code"] not in REASON_CODES:
            problems.append(f"{where}.reasons[{index}].code: {reason['code']!r}")
        if not reason["text"] or not isinstance(reason["text"], str):
            problems.append(f"{where}.reasons[{index}].text: empty")
        if not isinstance(reason["weight"], int | float):
            problems.append(f"{where}.reasons[{index}].weight: not a number")
    # A not_worth word must say why: a negative reason, or a zero-weight explanation such as
    # `thin_evidence` or the reader's own `decision_skip`.
    if ranking["shelf"] == "not_worth" and not any(
        isinstance(r, dict)
        and isinstance(r.get("weight"), int | float)
        and (r["weight"] < 0 or r.get("code") in {"thin_evidence", "decision_skip"})
        for r in reasons
    ):
        problems.append(f"{where}.reasons: a not_worth word needs a reason against it")


def _validate_shelf_counts(problems: list[str], where: str, counts: Any) -> bool:
    if not _keys(problems, where, counts, _SHELF_KEYS):
        return False
    ok = True
    for shelf, value in counts.items():
        if not _is_int(value) or value < 0:
            problems.append(f"{where}.{shelf}: not a non-negative integer")
            ok = False
    return ok


def validate_library(payload: dict[str, Any]) -> list[str]:
    """Check the C0 parts of a `load_library` response; returns the problems (empty when valid).

    Does not look at the old fields. Ranks must be 1..n without gaps inside each shelf, which
    holds for a whole library (the only thing `load_library` returns).
    """
    problems: list[str] = []
    for key in _LIBRARY_KEYS:
        if key not in payload:
            problems.append(f"library: missing {key}")
    if problems:
        return problems

    if payload["rankingVersion"] != RANKING_VERSION:
        problems.append(f"rankingVersion: {payload['rankingVersion']!r}")
    if payload["rankingMode"] not in RANKING_MODES:
        problems.append(f"rankingMode: {payload['rankingMode']!r}")
    if not _is_int(payload["historyDays"]) or payload["historyDays"] < 0:
        problems.append("historyDays: not a non-negative integer")
    if not isinstance(payload["repeatSignal"], bool):
        problems.append("repeatSignal: not a boolean")
    if payload["rankingMode"] == "full" and payload["repeatSignal"] is False:
        problems.append("rankingMode: full needs a repeat signal")

    entries = payload.get("entries") or []
    by_id: dict[str, dict[str, Any]] = {}
    by_study_priority = payload.get("studyPrioritySource") in ("rp-v2-personal", "rp-v2-coverage")
    study_order: dict[str, tuple[int, int, float, str]] = {}
    ranks: dict[str, list[int]] = {shelf: [] for shelf in SHELVES}
    shelf_totals = dict.fromkeys(SHELVES, 0)
    for entry in entries:
        lexeme_id = str(entry.get("id", ""))
        where = f"entry {lexeme_id or '?'}"
        by_id[lexeme_id] = entry
        for key in ("ranking", "study_priority", "decision", "card", "export", "is_new"):
            if key not in entry:
                problems.append(f"{where}: missing {key}")
        if "study_priority" in entry:
            previous_problem_count = len(problems)
            _validate_study_priority(problems, f"{where}.study_priority", entry["study_priority"])
            if by_study_priority and len(problems) == previous_problem_count:
                study_order[lexeme_id] = study_priority_order(entry["study_priority"], lexeme_id)
        if "ranking" not in entry or "export" not in entry or "card" not in entry:
            continue
        ranking = entry["ranking"]
        processed = (entry.get("processing") or {}).get("state") in ("ready", "rejected")
        if ranking is None:
            if processed:
                problems.append(f"{where}: processed word without a ranking")
        else:
            _validate_ranking(problems, f"{where}.ranking", ranking)
            if isinstance(ranking, dict) and ranking.get("shelf") in shelf_totals and _is_int(ranking.get("rank")):
                ranks[ranking["shelf"]].append(ranking["rank"])
                shelf_totals[ranking["shelf"]] += 1
        decision = entry.get("decision")
        if decision is not None and _keys(problems, f"{where}.decision", decision, _DECISION_KEYS):
            if decision["value"] not in DECISIONS:
                problems.append(f"{where}.decision.value: {decision['value']!r}")
            if not decision["decided_at"]:
                problems.append(f"{where}.decision.decided_at: empty")
        if _keys(problems, f"{where}.card", entry["card"], _CARD_KEYS):
            card = entry["card"]
            if card["meaning_source"] not in _MEANING_SOURCES:
                problems.append(f"{where}.card.meaning_source: {card['meaning_source']!r}")
            if (card["meaning_source"] == "none") != (card["meaning_ru"] == ""):
                problems.append(f"{where}.card: meaning_source none exactly when meaning_ru is empty")
            if len(card["meaning_ru"]) > MEANING_MAX_LENGTH:
                problems.append(f"{where}.card.meaning_ru: longer than {MEANING_MAX_LENGTH}")
            if card["example_occurrence_id"] and card["example_occurrence_id"] not in {
                occurrence.get("id") for occurrence in entry.get("occurrences", [])
            }:
                problems.append(f"{where}.card.example_occurrence_id: not an occurrence of the word")
        if _keys(problems, f"{where}.export", entry["export"], _EXPORT_KEYS):
            export = entry["export"]
            if export["state"] not in ("exported", "not_exported"):
                problems.append(f"{where}.export.state: {export['state']!r}")
            if (export["state"] == "exported") != bool(export["last_exported_at"]):
                problems.append(f"{where}.export: last_exported_at set exactly when exported")
            if not _is_int(export["lookups_after"]) or export["lookups_after"] < 0:
                problems.append(f"{where}.export.lookups_after: not a non-negative integer")
            if export["again"] and (export["state"] != "exported" or export["lookups_after"] < 1):
                problems.append(f"{where}.export: again needs an exported word with lookups_after >= 1")
            if export["again"] and not payload["repeatSignal"]:
                problems.append(f"{where}.export: again without a repeat signal")
        if not isinstance(entry.get("is_new"), bool):
            problems.append(f"{where}.is_new: not a boolean")

    for shelf, values in ranks.items():
        if sorted(values) != list(range(1, len(values) + 1)):
            problems.append(f"ranks in shelf {shelf} are not 1..{len(values)}: {sorted(values)}")

    if _validate_shelf_counts(problems, "shelves", payload["shelves"]) and payload["shelves"] != shelf_totals:
        problems.append(f"shelves: {payload['shelves']} != counted {shelf_totals}")

    batch = payload["newBatch"]
    if _keys(problems, "newBatch", batch, {"count", "ids", "availableIds"}):
        ids = batch["ids"]
        available_ids = batch["availableIds"]
        if batch["count"] != len(ids) or len(set(ids)) != len(ids):
            problems.append("newBatch: count must equal the number of distinct ids")
        if batch["count"] > BATCH_SIZE_MAX:
            problems.append(f"newBatch: more than {BATCH_SIZE_MAX} words")
        if ids != available_ids[:len(ids)]:
            problems.append("newBatch.ids: must be a prefix of availableIds")
        if len(available_ids) != len(set(available_ids)):
            problems.append("newBatch.availableIds: duplicate ids")
        for key, candidates in (("ids", ids), ("availableIds", available_ids)):
            previous = 0
            previous_study = None
            for lexeme_id in candidates:
                item = by_id.get(lexeme_id)
                if item is None:
                    problems.append(f"newBatch.{key}: an id that is not in entries")
                    continue
                ranking = item["ranking"]
                if ranking is None or ranking["shelf"] != "worth":
                    problems.append(f"newBatch.{key}: {item['id']} is not on the worth shelf")
                    continue
                if by_study_priority:
                    order = study_order.get(lexeme_id)
                    if order is not None:
                        if previous_study is not None and order < previous_study:
                            problems.append(f"newBatch.{key}: not in study priority order")
                        previous_study = order
                else:
                    if ranking["rank"] < previous:
                        problems.append(f"newBatch.{key}: not in rank order")
                    previous = ranking["rank"]
                if item["export"]["state"] == "exported":
                    problems.append(f"newBatch.{key}: {item['id']} is already exported")

    disputed = payload["disputed"]
    if _keys(problems, "disputed", disputed, {"ids"}):
        ids = disputed["ids"]
        if len(ids) > DISPUTED_CAP:
            problems.append(f"disputed: more than {DISPUTED_CAP} ids")
        batch_ids = set(batch.get("ids", [])) if isinstance(batch, dict) else set()
        for lexeme_id in ids:
            item = by_id.get(lexeme_id)
            if item is None or item["ranking"] is None or item["ranking"]["shelf"] != "disputed":
                problems.append(f"disputed: {lexeme_id} is not on the disputed shelf")
            elif item["export"]["state"] == "exported":
                problems.append(f"disputed: {lexeme_id} is already exported")
            if lexeme_id in batch_ids:
                problems.append(f"disputed: {lexeme_id} must not be in newBatch.ids")

    again = payload["again"]
    if _keys(problems, "again", again, {"count", "ids", "unavailable"}):
        if again["unavailable"] != (not payload["repeatSignal"]):
            problems.append("again.unavailable: must be true exactly when repeatSignal is false")
        if again["count"] != len(again["ids"]):
            problems.append("again: count must equal the number of ids")
        if again["unavailable"] and again["count"]:
            problems.append("again: unavailable but not empty")
        expected = sorted(i for i, e in by_id.items() if e["export"]["again"])
        if sorted(again["ids"]) != expected:
            problems.append("again.ids: must be the words whose export.again is true")
    return problems
