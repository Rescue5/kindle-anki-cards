"""`export_words`: send the short list to the reader's chosen destination, once, and remember it.

Which words: the library's `newBatch` (exportable, not yet exported, best rank first, cut at the
`export_batch_size` setting), or the given `ids` narrowed to the words that are exportable and not
yet exported. Where: the `export_destination` setting.

- `anki`: the deck is written as an .apkg and pushed when AnkiConnect is available. If it is
  unavailable before sending, the file is the result. Notes carry a GUID made from the lexeme id,
  so sending the same word again updates its note instead of duplicating it.
- `csv`: a tab-separated file in the optimized TSV layout, under `.app-data/exports`.
- `obsidian`: not an export destination; it keeps its own sync button.

A run is recorded (`export_runs` + `export_items`, one transaction) only after the push or file
export succeeds. An unconfirmed or rejected import keeps the saved package and leaves its words
in the short list.
"""

from __future__ import annotations

import csv
import errno
import os
import stat
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from kindle_vocab_app import (
    anki_connect,
    anki_export,
    card_fields,
    library_view,
    offline_dictionary,
    settings,
)
from kindle_vocab_app.coded_error import CodedError
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.logging_config import get_logger
from kindle_vocab_app.tsv_schema import OPTIMIZED_TSV_HEADER

logger = get_logger(__name__)

Progress = Callable[[str, str, int, int], None]

OBSIDIAN_TEXT = (
    "Obsidian пока синхронизируется своей кнопкой. "
    "Для этой выгрузки выберите Anki или файл в настройках"
)


def exports_dir(workspace: Path) -> Path:
    return workspace / ".app-data" / "exports"


def has_export_files(folder: Path) -> bool:
    """The folder is useful once it contains a finished package or table."""
    try:
        for entry in folder.iterdir():
            if entry.suffix.lower() not in {".apkg", ".tsv"}:
                continue
            try:
                info = entry.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_size > 0:
                return True
    except OSError:
        return False
    return False


@contextmanager
def _workspace_export_lock(workspace: Path) -> Iterator[None]:
    # Keep the file at a fixed path. Closing its descriptor also releases the lock after a crash.
    lock_path = exports_dir(workspace).parent / "export.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("ab")
    except OSError as exc:
        raise CodedError("export_failed", "не удалось подготовить папку выгрузок") from exc
    with lock_file:
        try:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise CodedError("export_busy") from exc
            raise CodedError("export_failed", "не удалось начать выгрузку") from exc
        yield


def export_words(
    workspace: Path, payload: Mapping[str, Any], *, progress: Progress | None = None
) -> dict[str, Any]:
    """Run one export; returns `contracts.ExportRun` or raises `CodedError`."""
    if str(payload.get("scope") or "new") != "new":
        raise CodedError("bad_scope")
    tell = progress or (lambda stage, message, current, total: None)
    with _workspace_export_lock(workspace):
        return _export_new_words(workspace, payload, tell)


def _export_new_words(
    workspace: Path, payload: Mapping[str, Any], tell: Progress
) -> dict[str, Any]:
    app_settings = settings.load(workspace)
    destination = app_settings.export_destination
    if destination == "obsidian":
        raise CodedError("no_destination", text=OBSIDIAN_TEXT)

    repository = repository_for(workspace)
    entries = repository.load_catalog()["lexemes"]
    offline_dictionary.attach(entries)
    state = repository.load_reader_state()
    library = library_view.decorate(
        entries,
        decisions=state["decisions"],
        card_edits=state["card_edits"],
        exported_at=state["exported_at"],
        batch_size=app_settings.export_batch_size,
    )
    by_id = {str(entry["id"]): entry for entry in entries}
    ids = _choose_ids(payload.get("ids"), library, entries, by_id)
    if not ids:
        raise CodedError("nothing_to_export")
    lexemes = [by_id[lexeme_id] for lexeme_id in ids]
    edits = state["card_edits"]

    tell("preparing", f"Готовим слов: {len(ids)}", 0, len(ids))
    pushed = 0
    try:
        if destination == "anki":
            path, pushed = _send_to_anki(workspace, lexemes, edits, tell)
        else:
            path = _write_tsv(workspace, lexemes, edits)
    except CodedError:
        raise
    except OSError as exc:
        logger.exception("Export file could not be written destination=%s", destination)
        raise CodedError("export_failed", "не удалось записать файл") from exc
    except Exception as exc:
        logger.exception("Export failed destination=%s", destination)
        raise CodedError("export_failed", "подробности в журнале") from exc

    try:
        run_id = repository.record_export_run(destination, ids, path=str(path))
    except Exception as exc:
        logger.exception("Export succeeded but the run was not recorded destination=%s", destination)
        if destination == "csv":
            raise CodedError(
                "export_failed",
                "TSV сохранён в папке выгрузок, но запись о выгрузке не сохранилась. "
                "При повторе будет создан ещё один файл",
            ) from exc
        raise CodedError(
            "export_failed", "колода сохранена в папке выгрузок, но запись о выгрузке не сохранилась"
        ) from exc
    logger.info("Export recorded destination=%s run=%d words=%d pushed=%d", destination, run_id, len(ids), pushed)
    tell("completed", "Выгрузка готова", len(ids), len(ids))
    return {
        "destination": destination,
        "runId": str(run_id),
        "exported": len(ids),
        "path": None if pushed else str(path),
        "pushed": pushed,
        "message": _message(len(ids), pushed),
    }


def _choose_ids(
    requested: Any,
    library: Mapping[str, Any],
    entries: list[dict[str, Any]],
    by_id: Mapping[str, Any],
) -> list[str]:
    if requested is None:
        return list(library["newBatch"]["ids"])
    if not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
        raise CodedError("unknown_lexeme")
    unknown = [item for item in requested if item not in by_id]
    if unknown:
        raise CodedError("unknown_lexeme")
    wanted = set(requested)
    # Only words that may leave and have not left yet; the order stays the ranking's.
    return [lexeme_id for lexeme_id in library_view.exportable_ids(entries) if lexeme_id in wanted]


def _send_to_anki(
    workspace: Path,
    lexemes: list[dict[str, Any]],
    edits: Mapping[str, Mapping[str, Any]],
    tell: Progress,
) -> tuple[Path, int]:
    """Write the deck; push it when AnkiConnect answers. Returns (file, cards pushed)."""
    total = len(lexemes)
    built = 0

    def definition(lemma: str, pos: str, context: str) -> str:
        nonlocal built
        built += 1
        if built % 50 == 0:
            tell("building", f"Собрано карточек: {built} из {total}", built, total)
        return anki_export.wordnet_definition(lemma, pos, context)

    with _reserve_path(exports_dir(workspace), ".apkg") as output:
        result = anki_export.write_apkg(
            lexemes,
            output,
            definition_lookup=definition,
            edits=edits,
            require_eligible=False,
        )
    if anki_connect.status()["state"] != "connected":
        return result.path, 0
    tell("importing", "Отправляем колоду в Anki", total, total)
    try:
        anki_connect.import_package(result.path)
    except anki_connect.AnkiConnectRejected as exc:
        raise CodedError("anki_import_rejected") from exc
    except anki_connect.AnkiConnectError as exc:
        raise CodedError("anki_import_unconfirmed") from exc
    return result.path, len(result.exported_ids)


def _write_tsv(
    workspace: Path, lexemes: list[dict[str, Any]], edits: Mapping[str, Mapping[str, Any]]
) -> Path:
    with _reserve_path(exports_dir(workspace), ".tsv") as output:
        temporary = output.with_suffix(output.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=OPTIMIZED_TSV_HEADER, delimiter="\t", extrasaction="ignore"
            )
            writer.writeheader()
            for lexeme in lexemes:
                writer.writerow(_tsv_row(lexeme, edits.get(str(lexeme["id"]))))
        temporary.replace(output)
    logger.info("Wrote export file words=%d", len(lexemes))
    return output


def _tsv_row(lexeme: Mapping[str, Any], edit: Mapping[str, Any] | None) -> dict[str, str]:
    """One row of the optimized TSV layout, from the card the reader saw."""
    analysis = (lexeme.get("processing") or {}).get("analysis") or {}
    enrichment = lexeme.get("enrichment") or {}
    card = card_fields.resolve(lexeme, edit)
    occurrence = card.occurrence
    word = str(occurrence.get("word") or lexeme.get("display_form") or lexeme.get("lemma") or "")
    warnings = analysis.get("warnings") or []
    forms = lexeme.get("forms") or [word]
    return {
        "Word": _cell(word),
        "Base form": _cell(analysis.get("base_form") or lexeme.get("lemma") or word),
        "Part of speech": _cell(analysis.get("pos")),
        "Russian meaning(s)": _cell(card.meaning_ru),
        "Generated context sentence EN": _cell(enrichment.get("example_en")),
        "Generated context sentence RU": _cell(enrichment.get("example_ru")),
        "Importance 0-10": _cell(analysis.get("importance_score")),
        "Importance note": _cell(analysis.get("importance_note")),
        "Lemma Zipf": _cell(analysis.get("lemma_zipf")),
        "Form Zipf": _cell(analysis.get("form_zipf")),
        "WordNet synset count": _cell(analysis.get("wordnet_synset_count")),
        "WordNet POS count": _cell(analysis.get("wordnet_pos_count")),
        "Warnings": _cell(", ".join(str(item) for item in warnings if str(item))),
        "Tags": _cell(analysis.get("tags")),
        "Source word forms": _cell(", ".join(str(item) for item in forms if str(item))),
        "Source occurrence count": _cell(len(lexeme.get("occurrences") or [])),
        "Original word": _cell(word),
        "Original stem": _cell(lexeme.get("lemma")),
        "Original context": _cell(occurrence.get("context")),
        "Original book_title": _cell(occurrence.get("book_title")),
        "Original authors": _cell(occurrence.get("authors")),
        "Original language": _cell(lexeme.get("language")),
        "Original looked_up_at": _cell(occurrence.get("looked_up_at")),
    }


def _cell(value: Any) -> str:
    """Plain text on one line: this file goes to spreadsheets and Quizlet, not to Anki's HTML import."""
    return " ".join(("" if value is None else str(value)).split())


@contextmanager
def _reserve_path(folder: Path, suffix: str) -> Iterator[Path]:
    """Claim a dated filename exclusively, including against other bridge processes."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"Kindle Cards {datetime.now().strftime('%Y-%m-%d %H-%M-%S')}"
    candidate, number = folder / f"{stem}{suffix}", 1
    while True:
        try:
            with candidate.open("xb"):
                pass
            break
        except FileExistsError:
            number += 1
            candidate = folder / f"{stem} ({number}){suffix}"
    try:
        yield candidate
    except BaseException:
        candidate.unlink(missing_ok=True)
        raise
    finally:
        candidate.with_suffix(candidate.suffix + ".tmp").unlink(missing_ok=True)


def _message(count: int, pushed: int) -> str:
    words = f"{count} {_words(count)}"
    return f"Готово: {words} в Anki" if pushed else f"Готово: {words} в файле"


def _words(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "слов"
    return {1: "слово", 2: "слова", 3: "слова", 4: "слова"}.get(tail % 10, "слов")
