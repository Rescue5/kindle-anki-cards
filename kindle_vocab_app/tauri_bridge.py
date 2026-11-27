from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import html
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

from kindle_vocab_app import (
    anki_connect,
    anki_export,
    book_coverage,
    book_covers,
    enrichment,
    export_cards,
    library_view,
    obsidian_sync,
    offline_dictionary,
    reader_sources,
    settings,
    vocab_cache,
)
from kindle_vocab_app.coded_error import CodedError
from kindle_vocab_app.contracts import ERROR_CODES, DecisionResult, SaveCardEditResult
from kindle_vocab_app.kindle_db import fetch_entries, list_books, validate_vocab_db
from kindle_vocab_app.kindle_device import (
    find_kindle_presence,
    find_kindle_source,
    mounted_volume_roots,
)
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.llm import presets as llm_presets
from kindle_vocab_app.logging_config import configure_logging, get_logger
from kindle_vocab_app.tsv_schema import OPTIMIZED_TSV_HEADER
from kindle_vocab_app.vocab_optimizer import _candidate_from_entry, analyze_entries_once
from kindle_vocab_app.workspace_lock import enrichment_run_lock

logger = get_logger(__name__)
PROGRESS_PREFIX = "KINDLE_PROGRESS "


def main() -> int:
    _configure_stdio()
    workspace = _workspace_root()
    configure_logging(workspace / ".app-data" / "tauri-logs", console=True)
    try:
        request_body = (sys.stdin.read() or "{}").lstrip("\ufeff")
        request = json.loads(request_body)
        action = str(request.get("action") or "")
        payload = dict(request.get("payload") or {})
        logger.info("Tauri bridge request action=%s payload_keys=%s", action, sorted(payload))
        result = dispatch(action, payload, workspace)
        _write_response({"ok": True, "result": result})
        return 0
    except Exception as exc:
        logger.exception("Tauri bridge request failed")
        _write_response(error_response(exc))
        return 1


def error_response(exc: BaseException) -> dict[str, Any]:
    """The failure envelope: the text the UI shows and, for coded errors, `code` (contracts.ERROR_CODES)."""
    response: dict[str, Any] = {"ok": False, "error": str(exc)}
    code = getattr(exc, "code", None)
    if code in ERROR_CODES:
        response["code"] = code
    return response


def dispatch(action: str, payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")

    if action in {"load_library", "load_cached"}:
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        return _catalog_response(
            catalog,
            workspace=workspace,
            connector_status=_connector_status(workspace, probe_kindle=False),
            queue_status=repository_for(workspace).queue_status(),
        )

    if action == "save_card_edit":
        return _save_card_edit(payload, workspace)

    if action == "set_decision":
        return _set_decision(payload, workspace)

    if action == "export_words":
        return export_cards.export_words(
            workspace,
            payload,
            progress=lambda stage, message, current, total: _emit_progress(job_id, stage, message, current, total),
        )

    if action == "export_folder_status":
        return {"available": export_cards.has_export_files(export_cards.exports_dir(workspace))}

    if action == "open_export_folder":
        return _open_export_folder(workspace)

    if action == "open_obsidian_folder":
        return _open_obsidian_folder(workspace)

    if action == "load_review":
        review = repository_for(workspace).load_review(limit=payload.get("limit", 20))
        offline_dictionary.attach(review["cards"])
        return review

    if action == "rate_review":
        return repository_for(workspace).rate_review(
            str(payload.get("lexeme_id") or ""), str(payload.get("rating") or "")
        )

    if action == "connector_status":
        return _connector_status(workspace, probe_kindle=True)

    if action == "download_covers":
        catalog = repository_for(workspace).load_catalog()
        _emit_progress(job_id, "covers", "Загружаем обложки книг", 0, 1)
        summary = _download_book_covers(
            catalog, workspace, retry_errors=bool(payload.get("retry_errors", True))
        )
        _emit_progress(job_id, "completed", "Обложки сохранены", 1, 1)
        result = _catalog_response(catalog, workspace=workspace,
                                   connector_status=_connector_status(workspace, probe_kindle=False),
                                   queue_status=repository_for(workspace).queue_status())
        result["coverSummary"].update(summary)
        result["coverSummary"]["downloaded"] = summary["downloaded"] + summary["local_copied"]
        return result

    if action in {"sync_kindle", "scan"}:
        _emit_progress(job_id, "detecting", "Ищем подключённую читалку", 0, 5)
        source = find_kindle_source()
        readers = reader_sources.find_reader_files(mounted_volume_roots())
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        if source is None and not readers:
            logger.info("Reader synchronization skipped job_id=%s reason=disconnected", job_id)
            disconnected = _connector_status(workspace, probe_kindle=False)
            disconnected["kindle"] = {"state": "disconnected", "label": "Kindle", "checked_at": vocab_cache.utc_now()}
            return _catalog_response(
                catalog,
                workspace=workspace,
                connector_status=disconnected,
                queue_status=repository_for(workspace).queue_status(),
            )
        _emit_progress(job_id, "copying", "Копируем слова и обложки в локальный кэш", 1, 5)
        entries: list[dict[str, str]] = []
        labels: list[str] = []
        if source is not None:
            db_path = source.copy_to_cache(workspace / ".app-data" / "cache")
            validate_vocab_db(db_path)
            entries.extend(_entry_for_frontend(entry) for entry in fetch_entries(db_path))
            labels.append(source.label)
        for reader in readers:
            cached = reader_sources.copy_to_cache(reader.path, workspace / ".app-data" / "cache" / "readers", reader.kind)
            entries.extend(_entry_for_frontend(entry) for entry in reader_sources.fetch_entries(cached, reader.kind))
            labels.append(reader.label)
        _emit_progress(job_id, "parsing", "Читаем слова и контексты", 2, 5)
        sync_id = uuid.uuid4().hex
        _emit_progress(job_id, "merging", "Объединяем формы и известные леммы", 3, 5)
        catalog = vocab_cache.merge_kindle(catalog, entries, sync_id=sync_id, mark_new=True)
        _refresh_obsidian_destination_states(catalog)
        repository = repository_for(workspace)
        repository.save_catalog(catalog)
        catalog = repository.load_catalog()
        # Online cover lookup is slow (sequential requests), so sync only copies
        # Kindle thumbnails; the frontend fetches the rest in the background.
        _emit_progress(job_id, "covers", "Сохраняем обложки с читалки", 4, 5)
        if source is not None:
            _download_book_covers(catalog, workspace, network=False)
        label = " + ".join(labels)
        _emit_progress(job_id, "completed", "Синхронизация завершена", 5, 5)
        logger.info(
            "Reader synchronization completed job_id=%s sync_id=%s sources=%s entries=%d lexemes=%d",
            job_id,
            sync_id,
            label,
            len(entries),
            len(catalog["lexemes"]),
        )
        connector_status = _connector_status(workspace, probe_kindle=True)
        if connector_status["kindle"]["state"] != "connected":
            connector_status["kindle"] = {
                "state": "connected",
                "label": label,
                "checked_at": vocab_cache.utc_now(),
            }
        return _catalog_response(
            catalog,
            workspace=workspace,
            source_name=label,
            source_status="Слова с читалки синхронизированы",
            connector_status=connector_status,
            queue_status=repository.queue_status(),
        )

    if action == "import_reader_file":
        return _import_reader_file(payload, workspace, job_id=job_id)

    if action == "load_demo":
        catalog = _demo_catalog()
        return _catalog_response(
            catalog,
            workspace=workspace,
            source_name="Demo Kindle",
            source_status="Демонстрационные данные",
            queue_status={"pending": 0, "processing": 0, "failed": 0, "total": 0},
            reader_state=False,
        )

    if action == "export":
        entries = [_lexeme_as_entry(item) for item in payload.get("entries") or []]
        export_format = str(payload.get("format") or "anki")
        output = workspace / ".app-data" / f"kindle-{export_format}.tsv"
        exported = export_frontend_entries(entries, output, export_format, workspace)
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        exported_ids = {str(item.get("id") or "") for item in payload.get("entries") or []}
        now = vocab_cache.utc_now()
        for lexeme in catalog["lexemes"]:
            if lexeme.get("id") in exported_ids:
                lexeme["destinations"][export_format] = {"state": "exported", "last_exported_at": now}
        repository_for(workspace).save_catalog(catalog)
        return {"path": str(output), "exported": exported}

    if action == "enrich_lexemes":
        with enrichment_run_lock(workspace):
            return _with_ranking(_llm_action(action, payload, workspace, job_id=job_id), workspace)
    if action in _LLM_ACTIONS:
        return _with_ranking(_llm_action(action, payload, workspace, job_id=job_id), workspace)

    if action == "export_apkg":
        return _export_apkg(payload, workspace, job_id=job_id)

    if action == "push_anki":
        return _export_apkg(payload, workspace, job_id=job_id, push=True)

    if action == "open_path":
        return _open_export_path(Path(str(payload.get("path") or "")), workspace, reveal=bool(payload.get("reveal")))

    if action in {"process_queue", "process_lexemes", "optimize"}:
        repository = repository_for(workspace)
        catalog = repository.load_catalog()
        requested_ids: set[str] | None = None
        # The automatic queue retries failed lexemes only on an explicit request;
        # otherwise a deterministic failure would be re-run on every pass.
        include_failed = bool(payload.get("include_failed"))
        if action != "process_queue":
            include_failed = True
            requested_ids = {str(value) for value in payload.get("ids") or []}
            if not requested_ids and payload.get("entries"):
                requested_ids = {
                    str(item.get("id") or "") for item in payload.get("entries") or []
                }
        queued_ids = repository.queued_ids(requested_ids, include_failed=include_failed)
        return _with_ranking(
            _process_queued_lexemes(
                catalog,
                queued_ids,
                repository,
                workspace,
                job_id=job_id,
            ),
            workspace,
        )

    if action == "load_settings":
        app_settings = settings.load(workspace)
        return settings.to_dict(app_settings)

    if action == "save_settings":
        # Keys the payload leaves out keep their current values (an older frontend does not know them all).
        merged = {**settings.to_dict(settings.load(workspace)), **(payload.get("settings") or {})}
        app_settings = settings.from_dict(merged)
        settings.save(workspace, app_settings)
        return {"saved": True}

    if action == "load_obsidian":
        app_settings = settings.load(workspace)
        vault_path = str(payload.get("vault_path") or app_settings.obsidian_vault_path)
        cards_path = str(payload.get("cards_path") or app_settings.obsidian_cards_path)
        if not vault_path or not cards_path:
            raise ValueError("vault_path and cards_path are required")
        cards_dir = obsidian_sync.legacy_cards_dir(Path(vault_path), cards_path)
        if not cards_dir.is_dir():
            raise ValueError("Папка карточек Obsidian не найдена или путь не является папкой")
        repository = repository_for(workspace)
        catalog = repository.load_catalog()
        card_count = _reconcile_obsidian(catalog, cards_dir)
        repository.save_obsidian_evidence(catalog["lexemes"])
        return _catalog_response(
            repository.load_catalog(),
            workspace=workspace,
            source_name="Obsidian",
            source_status=f"Сверено карточек: {card_count}",
            connector_status=_connector_status(workspace, probe_kindle=False),
            queue_status=repository.queue_status(),
        )

    if action == "sync_obsidian":
        app_settings = settings.load(workspace)
        vault_path = str(payload.get("vault_path") or app_settings.obsidian_vault_path)
        cards_path = str(payload.get("cards_path") or app_settings.obsidian_cards_path)
        backup_enabled = bool(payload.get("backup_enabled", app_settings.obsidian_backup_enabled))
        if not vault_path or not cards_path:
            raise ValueError("vault_path and cards_path are required")
        vault = Path(vault_path)
        with obsidian_sync.vault_operation_lock(vault):
            if app_settings.export_destination == "obsidian" or (vault / "Kindle Cards" / ".kindle-cards-owner").exists():
                raise ValueError("Для этого хранилища используйте выгрузку с Главной")
            cards_dir = obsidian_sync.legacy_cards_dir(vault, cards_path)
            return _sync_legacy_obsidian(workspace, cards_dir, backup_enabled, job_id)

    raise ValueError(f"Unsupported bridge action: {action}")


def _sync_legacy_obsidian(workspace: Path, cards_dir: Path, backup_enabled: bool, job_id: str) -> dict[str, Any]:
    repository = repository_for(workspace)
    catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
    backups_dir = workspace / ".app-data" / "obsidian-backups"
    before_count = _reconcile_obsidian(catalog, cards_dir)
    entries = [
        _lexeme_as_entry(item)
        for item in catalog["lexemes"]
        if (item.get("destinations") or {}).get("obsidian", {}).get("eligible")
        and (item.get("destinations") or {}).get("obsidian", {}).get("state") == "missing"
    ]
    _emit_progress(job_id, "reconciling", f"Проверяем очередь: {len(entries)}", 0, max(len(entries), 1))
    result = obsidian_sync.append_cards(
        cards_dir, entries, backups_dir, backup_enabled=backup_enabled
    )
    after_count = _reconcile_obsidian(catalog, cards_dir)
    if after_count - before_count != int(result.get("added") or 0):
        raise RuntimeError("Проверка Obsidian не подтвердила количество добавленных карточек")
    failed_by_id = {
        str(item.get("id") or ""): item
        for item in result.get("items") or []
        if item.get("outcome") == "failed"
    }
    for index, lexeme in enumerate(catalog["lexemes"], 1):
        failed = failed_by_id.get(str(lexeme.get("id") or ""))
        if failed:
            lexeme["destinations"]["obsidian"].update(
                {"state": "failed", "reason": failed.get("reason") or "sync_failed"}
            )
        _emit_progress(job_id, "syncing", f"Проверено {index} из {len(catalog['lexemes'])}", index, len(catalog["lexemes"]), lexeme_id=str(lexeme.get("id") or ""))
    repository.save_obsidian_evidence(catalog["lexemes"])
    repository.record_sync_run(
        "obsidian",
        "completed",
        added=int(result.get("added") or 0),
        skipped=int(result.get("skipped") or 0),
    )
    result["entries"] = repository.load_catalog()["lexemes"]
    result["queue_status"] = repository.queue_status()
    _emit_progress(job_id, "completed", "Синхронизация Obsidian завершена", len(entries), max(len(entries), 1))
    return _with_ranking(result, workspace)


def _process_queued_lexemes(
    catalog: dict[str, Any],
    queued_ids: list[str],
    repository: Any,
    workspace: Path,
    *,
    job_id: str,
) -> dict[str, Any]:
    total = len(queued_ids)
    output_dir = workspace / ".app-data" / "optimized"
    accepted_new = 0
    rejected_new = 0
    processed_new = 0
    skipped_existing = 0
    failed_new = 0
    _emit_progress(job_id, "preparing", f"В очереди лемм: {total}", 0, max(total, 1))

    for index, queued_id in enumerate(queued_ids, 1):
        lexeme = next(
            (item for item in catalog["lexemes"] if str(item.get("id") or "") == queued_id),
            None,
        )
        if lexeme is None or (lexeme.get("processing") or {}).get("state") not in {
            "pending",
            "failed",
        }:
            skipped_existing += 1
            continue
        entry = _lexeme_as_entry(lexeme)
        candidate = _candidate_from_entry(entry)
        try:
            if candidate is None:
                analysis = _analysis_for_unsupported_entry(lexeme)
            else:
                audit_rows = analyze_entries_once([entry], output_dir)
                if not audit_rows:
                    raise RuntimeError("Offline-анализ не вернул результат")
                analysis = _analysis_from_audit(audit_rows[0])

            accepted = analysis.get("accepted") is not False
            lexeme["processing"] = {
                "state": "ready" if accepted else "rejected",
                "analysis": analysis,
                "updated_at": str(analysis.get("processed_at") or vocab_cache.utc_now()),
                "error": "",
                "origin": "sqlite_optimizer",
            }
            lexeme["lemma"] = vocab_cache.normalize_lexical_key(
                str(analysis.get("base_form") or lexeme.get("lemma") or "")
            )
            processed_new += 1
            if accepted:
                accepted_new += 1
            else:
                rejected_new += 1
            _refresh_obsidian_destination_states(catalog)
            if repository.save_processed_lexeme(catalog, queued_id):
                catalog = repository.load_catalog()
        except Exception as exc:
            # One broken lexeme must not stop the rest of the queue: record the
            # failure durably and continue. Storage errors still propagate from
            # the save below.
            logger.exception("Offline processing failed lexeme_id=%s", queued_id)
            lexeme["processing"] = {
                "state": "failed",
                "analysis": None,
                "updated_at": vocab_cache.utc_now(),
                "error": str(exc),
                "origin": "sqlite_optimizer",
            }
            _refresh_obsidian_destination_states(catalog)
            if repository.save_processed_lexeme(catalog, queued_id):
                catalog = repository.load_catalog()
            failed_new += 1

        _emit_progress(
            job_id,
            "processing",
            f"Обработано {index} из {total}",
            index,
            max(total, 1),
            lexeme_id=queued_id,
        )

    _emit_progress(job_id, "completed", "Offline-обработка завершена", total, max(total, 1))
    message = (
        f"Обработано: {processed_new}; принято: {accepted_new}; "
        f"отклонено: {rejected_new}; пропущено ранее: {skipped_existing}"
    )
    if failed_new:
        message += f"; ошибок: {failed_new}"
    message += "."
    return {
        "processed_new": processed_new,
        "accepted_new": accepted_new,
        "skipped_existing": skipped_existing,
        "rejected_new": rejected_new,
        "failed_new": failed_new,
        "tsv_path": str(output_dir / "optimized.tsv"),
        "entries": catalog["lexemes"],
        "queue_status": repository.queue_status(),
        "message": message,
        "events": [
            {
                "phase": "answered",
                "title": "Offline optimizer",
                "message": message,
                "meta": "SQLite",
            }
        ],
    }


_LLM_ACTIONS = {"llm_config", "save_llm_key", "delete_llm_key", "list_llm_models", "test_llm", "enrich_lexemes"}


def _llm_action(action: str, payload: dict[str, Any], workspace: Path, *, job_id: str) -> dict[str, Any]:
    """Provider configuration, key storage, connection test and enrichment runs.

    API keys are written to the OS keychain and never returned to the frontend.
    """
    app_settings = settings.load(workspace)
    provider = str(payload.get("provider") or app_settings.llm_provider)
    model = str(payload.get("model") if "model" in payload else app_settings.llm_model)
    base_url = str(payload.get("base_url") if "base_url" in payload else app_settings.llm_base_url)

    if action == "llm_config":
        return {
            "presets": llm_presets.presets_payload(),
            "provider": app_settings.llm_provider,
            "model": app_settings.llm_model,
            "base_url": app_settings.llm_base_url,
            "has_key": {preset_id: llm_presets.has_api_key(preset_id) for preset_id in llm_presets.PRESETS},
        }
    if action == "save_llm_key":
        llm_presets.set_api_key(provider, str(payload.get("api_key") or ""))
        return {"has_key": True}
    if action == "delete_llm_key":
        llm_presets.delete_api_key(provider)
        return {"has_key": llm_presets.has_api_key(provider)}
    if action == "list_llm_models":
        client = enrichment.build_client(provider, model or "placeholder", base_url)
        return {"models": client.list_models()}
    if action == "test_llm":
        client = enrichment.build_client(provider, model, base_url)
        started = time.monotonic()
        sample = enrichment.test_connection(client)
        return {"ok": True, "model": client.model, "seconds": round(time.monotonic() - started, 1), "sample": sample}

    # enrich_lexemes
    requested = None
    if "ids" in payload:
        ids = payload["ids"]
        if not isinstance(ids, list) or not all(isinstance(item, str) and item.strip() for item in ids):
            raise ValueError("Список слов для перевода должен содержать только непустые идентификаторы")
        requested = set(ids)
    if not app_settings.llm_enabled and (requested is None or requested):
        raise ValueError("Включите перевод через ИИ в настройках")
    expected = payload.get("expected_count")
    if "expected_count" in payload and (type(expected) is not int or expected < 0):
        raise ValueError("Ожидаемое число слов для перевода должно быть целым неотрицательным числом")
    repository = repository_for(workspace)
    catalog = repository.load_catalog()
    state = repository.load_reader_state()
    edits = state["card_edits"]
    offline_dictionary.attach(catalog["lexemes"])
    selected = enrichment.candidates(
        catalog["lexemes"], ids=requested, retry_failed=payload.get("retry_failed") is True,
        edits=edits, decisions=state["decisions"], examples_per_sense=app_settings.llm_examples_per_sense,
    )
    limit = int(payload.get("limit") or 0)
    if limit > 0:
        selected = selected[:limit]
    if expected is not None and expected != len(selected):
        raise ValueError(f"Список слов для перевода изменился. Доступно: {len(selected)}. Обновите выбор")
    _emit_progress(job_id, "preparing", f"Слов для перевода: {len(selected)}", 0, max(len(selected), 1))
    summary = enrichment.EnrichmentSummary()
    if selected:
        preset = llm_presets.preset_for(provider)
        batch_size = enrichment.batch_size_for(preset.batch_size, examples_per_sense=app_settings.llm_examples_per_sense)
        parallel = preset.max_parallel_batches > 1 and len(selected) > batch_size
        client = enrichment.build_client(provider, model, base_url, parallel=parallel)
        summary = enrichment.enrich(
            selected, client, repository, provider=provider,
            batch_size=preset.batch_size, max_parallel_batches=preset.max_parallel_batches,
            edits=edits, examples_per_sense=app_settings.llm_examples_per_sense,
            progress=lambda done, total: _emit_progress(job_id, "enriching", f"Обработано {done} из {total}", done, total),
        )
        catalog = repository.load_catalog()
    processed = summary.enriched + summary.failed
    _emit_progress(
        job_id, "stopped" if summary.error else "completed",
        "Перевод остановлен" if summary.error else "Перевод завершён", processed, max(len(selected), 1),
    )
    message = f"Переведено: {summary.enriched}; без перевода: {summary.failed}"
    if summary.requested > processed:
        message += f"; отложено: {summary.requested - processed}"
    return {
        "requested": summary.requested,
        "enriched": summary.enriched,
        "failed": summary.failed,
        "error": summary.error,
        "message": f"{message}. {summary.error}" if summary.error else message,
        "entries": catalog["lexemes"],
        "queue_status": repository.queue_status(),
    }


def _export_apkg(payload: dict[str, Any], workspace: Path, *, job_id: str, push: bool = False) -> dict[str, Any]:
    """Write an Anki package of new or newly translated words; optionally import it via AnkiConnect.

    Words are marked as exported only after the file exists and, when pushing,
    after Anki confirmed the import.
    """
    repository = repository_for(workspace)
    catalog = repository.load_catalog()
    requested = {str(value) for value in payload.get("ids") or []}
    only_new = bool(payload.get("only_new", True))
    # Copies carry offline dictionary meanings for the cards without touching the stored catalog.
    lexemes = [{**lexeme, "dictionary": offline_dictionary.lookup_lexeme(lexeme)} for lexeme in catalog["lexemes"]]
    candidates = [
        lexeme
        for lexeme in lexemes
        if (not requested or str(lexeme.get("id") or "") in requested)
        and anki_export.is_exportable(lexeme)
        and (not only_new or anki_export.needs_anki_update(lexeme))
    ]
    if not candidates:
        return {"path": "", "exported": 0, "skipped": 0, "message": "Нет новых карточек для Anki"}

    total = len(candidates)
    _emit_progress(job_id, "preparing", f"Готовим карточек: {total}", 0, total)
    lookups = 0

    def definition_lookup(lemma: str, pos: str, context: str) -> str:
        nonlocal lookups
        lookups += 1
        if lookups % 50 == 0:
            _emit_progress(job_id, "building", f"Собрано карточек: {lookups} из {total}", lookups, total)
        return anki_export.wordnet_definition(lemma, pos, context)

    stamp = datetime.now().strftime("%Y-%m-%d %H-%M")
    output = export_cards.exports_dir(workspace) / f"Kindle Cards {stamp}.apkg"
    result = anki_export.write_apkg(
        candidates,
        output,
        deck_name=str(payload.get("deck_name") or anki_export.DEFAULT_DECK_NAME),
        definition_lookup=definition_lookup,
        edits=repository.load_card_edits(),
        note_keys=repository.reserve_anki_note_keys(candidates),
    )
    if push:
        _emit_progress(job_id, "importing", "Импортируем колоду в Anki", total, total)
        try:
            anki_connect.import_package(result.path)
        except anki_connect.AnkiConnectError as exc:
            raise ValueError(f"{exc}. Колода сохранена в файл: {result.path.name}") from exc
    exported_ids = set(result.exported_ids)
    now = vocab_cache.utc_now()
    for lexeme in catalog["lexemes"]:
        if lexeme.get("id") in exported_ids:
            lexeme["destinations"]["anki"] = {"state": "exported", "last_exported_at": now}
    repository.save_catalog(catalog)
    _emit_progress(job_id, "completed", "Колода Anki готова", total, total)
    count = len(result.exported_ids)
    return {
        "path": str(result.path),
        "exported": count,
        "skipped": result.skipped,
        "pushed": push,
        "message": f"Отправлено в Anki: {count}" if push else f"Карточек в колоде: {count}",
    }


def _open_export_path(path: Path, workspace: Path, *, reveal: bool) -> dict[str, Any]:
    """Open an exported file (Anki imports .apkg on open) or reveal it."""
    exports = export_cards.exports_dir(workspace).resolve()
    target = path.resolve()
    if exports not in target.parents or not target.is_file():
        raise ValueError("Можно открыть только файл из папки экспорта приложения")
    _open_local_path(target, reveal=reveal)
    return {"opened": True}


def _open_obsidian_folder(workspace: Path) -> dict[str, Any]:
    from kindle_vocab_app.obsidian_export import managed_folder

    current = settings.load(workspace)
    vault = Path(current.obsidian_vault_path.strip())
    if current.export_destination != "obsidian" or not vault.is_absolute():
        return {"opened": False}
    try:
        _open_local_path(managed_folder(vault))
    except (ValueError, OSError):
        return {"opened": False}
    return {"opened": True}


def _open_export_folder(workspace: Path) -> dict[str, Any]:
    folder = export_cards.exports_dir(workspace).absolute()
    if not export_cards.has_export_files(folder):
        return {"opened": False}
    try:
        _open_local_path(folder)
    except OSError:
        return {"opened": False}
    return {"opened": True}


def _open_local_path(target: Path, *, reveal: bool = False) -> None:
    if sys.platform == "win32":
        if reveal:
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)] if reveal else ["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target.parent if reveal else target)])


def _analysis_from_audit(raw: dict[str, Any]) -> dict[str, Any]:
    importance = raw.get("importance") or {}
    frequencies = raw.get("frequencies") or {}
    wordnet = raw.get("wordnet") or {}
    warnings = raw.get("warnings") or {}
    return {
        "base_form": str(raw.get("base_form") or raw.get("lexical_key") or ""),
        "pos": str(raw.get("pos") or ""),
        "accepted": bool(raw.get("accepted", True)),
        "importance_score": importance.get("score"),
        "importance_note": str(importance.get("explanation") or importance.get("note") or ""),
        "frequency_note": _frequency_note(frequencies),
        "lemma_zipf": frequencies.get("lemma_zipf"),
        "form_zipf": frequencies.get("form_zipf"),
        "wordnet_synset_count": wordnet.get("synset_count"),
        "wordnet_pos_count": wordnet.get("pos_count"),
        "warnings": sorted(warnings) if isinstance(warnings, dict) else list(warnings),
        "tags": str(raw.get("tags") or ""),
        "source_word_forms": list(raw.get("source_word_forms") or []),
        "source_occurrence_count": raw.get("source_occurrence_count"),
        "processed_at": str(raw.get("processed_at") or vocab_cache.utc_now()),
        "translation_status": "offline_only",
    }


def _emit_progress(
    job_id: str,
    stage: str,
    message: str,
    current: int,
    total: int,
    *,
    lexeme_id: str = "",
) -> None:
    if not job_id:
        return
    payload = {
        "job_id": job_id,
        "stage": stage,
        "message": message,
        "current": current,
        "total": total,
        "lexeme_id": lexeme_id,
        "timestamp": vocab_cache.utc_now(),
    }
    sys.stderr.write(PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stderr.flush()


def _load_catalog_with_sources(workspace: Path, *, reconcile_kindle: bool = True, reconcile_obsidian: bool = True) -> dict[str, Any]:
    repository = repository_for(workspace)
    catalog = repository.load_catalog()
    if reconcile_kindle:
        cached_db = workspace / ".app-data" / "cache" / "vocab.db"
        if cached_db.exists():
            try:
                validate_vocab_db(cached_db)
                entries = [_entry_for_frontend(entry) for entry in fetch_entries(cached_db)]
                catalog = vocab_cache.merge_kindle(
                    catalog,
                    entries,
                    sync_id=str(catalog.get("last_kindle_sync_id") or "cached"),
                    mark_new=False,
                )
            except Exception:
                logger.exception("Failed to reconcile cached Kindle database")
    _refresh_obsidian_destination_states(catalog)
    if reconcile_kindle:
        repository.save_catalog(catalog)
    if reconcile_obsidian:
        app_settings = settings.load(workspace)
        if (
            app_settings.export_destination != "obsidian"
            and app_settings.obsidian_sync_enabled
            and app_settings.obsidian_vault_path
            and app_settings.obsidian_cards_path
        ):
            try:
                cards_dir = obsidian_sync.legacy_cards_dir(Path(app_settings.obsidian_vault_path), app_settings.obsidian_cards_path)
                _reconcile_obsidian(catalog, cards_dir)
                repository.save_obsidian_evidence(catalog["lexemes"])
            except Exception:
                logger.exception("Failed to reconcile Obsidian cards")
    return catalog


def _connector_status(workspace: Path, *, probe_kindle: bool) -> dict[str, Any]:
    app_settings = settings.load(workspace)
    presence = find_kindle_presence() if probe_kindle else None
    label, signature = (presence.label, list(presence.signature)) if presence is not None else ("Kindle", None)
    if probe_kindle and presence is None:
        # KOReader and Kobo readers mount as ordinary USB drives: their word files are the identity.
        readers = reader_sources.find_reader_files(mounted_volume_roots())
        if readers:
            label = " + ".join(reader.label for reader in readers)
            signature = [part for reader in readers for part in reader.signature]
    kindle: dict[str, Any] = {
        "state": "connected" if signature is not None else ("disconnected" if probe_kindle else "unknown"),
        "label": label,
        "checked_at": vocab_cache.utc_now(),
    }
    if signature is not None:
        kindle["signature"] = signature
    obsidian_state = "disabled"
    if app_settings.obsidian_vault_path:
        vault = Path(app_settings.obsidian_vault_path)
        if app_settings.export_destination == "obsidian":
            obsidian_state = "connected" if vault.is_absolute() and vault.is_dir() else "error"
        elif app_settings.obsidian_sync_enabled:
            try:
                cards_dir = obsidian_sync.legacy_cards_dir(vault, app_settings.obsidian_cards_path)
                obsidian_state = "connected" if cards_dir.is_dir() else "error"
            except (ValueError, OSError):
                obsidian_state = "error"
    anki = anki_connect.status() if probe_kindle else {"state": "unknown", "label": "Anki"}
    anki["checked_at"] = vocab_cache.utc_now()
    return {
        "kindle": kindle,
        "obsidian": {
            "state": obsidian_state,
            "label": "Obsidian",
            "checked_at": vocab_cache.utc_now(),
        },
        "anki": anki,
    }


def _catalog_response(
    catalog: dict[str, Any],
    *,
    workspace: Path | None = None,
    source_name: str = "Локальная библиотека",
    source_status: str = "Сохранённые слова доступны без устройства",
    connector_status: dict[str, Any] | None = None,
    queue_status: dict[str, int] | None = None,
    reader_state: bool = True,
) -> dict[str, Any]:
    result = vocab_cache.frontend_state(catalog, source_name=source_name, source_status=source_status)
    workspace = workspace or _workspace_root()
    result["books"] = book_covers.attach_covers(result["books"], workspace / ".app-data" / "covers")
    for book in result["books"]:
        if book.get("title"):
            book["display_title"] = book_covers.clean_book_title(str(book["title"]), str(book.get("authors") or ""))
    real_books = [book for book in result["books"] if book.get("key")]
    result["coverSummary"] = {"available": sum(bool(book.get("cover_data_url")) for book in real_books),
                              "total": len(real_books),
                              "missing": sum(book.get("cover_status") == "missing" for book in real_books),
                              "errors": sum(book.get("cover_status") == "error" for book in real_books)}
    result["connectors"] = connector_status or _connector_status(workspace, probe_kindle=False)
    result["queueStatus"] = queue_status or {"pending": 0, "processing": 0, "failed": 0, "total": 0}
    offline_dictionary.attach(result["entries"])
    result.update(_ranked_library(result["entries"], workspace, reader_state=reader_state))
    return result


def _ranked_library(
    entries: list[dict[str, Any]], workspace: Path, *, reader_state: bool = True, decision_audit: bool = False
) -> dict[str, Any]:
    """Rank the entries in place (see `library_view`) and return the library-level fields.

    The reader's decisions, card edits and exports come from the workspace's SQLite library; the demo
    library is not stored there, so it is ranked without them.
    """
    state = repository_for(workspace).load_reader_state() if reader_state else {}
    app_settings = settings.load(workspace)
    # The audit only records the legacy shelf and score. Open the coverage snapshot once,
    # for the response after the decision has been stored.
    with (nullcontext() if decision_audit else book_coverage.open_model(workspace)) as model:
        result = library_view.decorate(
            entries,
            decisions=state.get("decisions"),
            card_edits=state.get("card_edits"),
            exported_at=state.get("exported_at"),
            batch_size=app_settings.export_batch_size,
            coverage_model=model,
        )
    if not decision_audit:
        enrichment.decorate(entries, state.get("card_edits") or {}, examples_per_sense=app_settings.llm_examples_per_sense)
        result["enrichmentQueue"] = enrichment.queue_counts(entries, state.get("decisions"))
    return result


def _with_ranking(result: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Responses that hand back the whole library (`entries`) carry the ranking too, so a screen that
    swaps its entries for them never loses it."""
    entries = result.get("entries")
    if isinstance(entries, list):
        offline_dictionary.attach(entries)
        result.update(_ranked_library(entries, workspace))
    return result


def _reader_action_id(payload: dict[str, Any]) -> str:
    lexeme_id = payload.get("lexeme_id")
    if not isinstance(lexeme_id, str) or not lexeme_id:
        raise CodedError("unknown_lexeme")
    return lexeme_id


def _reader_action_entry(entries: list[dict[str, Any]], lexeme_id: str) -> dict[str, Any]:
    for entry in entries:
        if entry["id"] == lexeme_id:
            return entry
    raise CodedError("unknown_lexeme")


def _save_card_edit(payload: dict[str, Any], workspace: Path) -> SaveCardEditResult:
    lexeme_id = _reader_action_id(payload)
    changes = {key: payload[key] for key in ("meaning_ru", "example_occurrence_id") if key in payload}
    if "meaning_ru" in changes and not isinstance(changes["meaning_ru"], str):
        raise ValueError("Перевод должен быть строкой")
    if "example_occurrence_id" in changes and not isinstance(changes["example_occurrence_id"], str):
        raise CodedError("example_not_found")
    repository = repository_for(workspace)
    repository.save_card_edit(lexeme_id, **changes)
    result = _with_ranking({"entries": repository.load_catalog()["lexemes"]}, workspace)
    return {"entry": _reader_action_entry(result["entries"], lexeme_id)}


def _set_decision(payload: dict[str, Any], workspace: Path) -> DecisionResult:
    lexeme_id = _reader_action_id(payload)
    if "decision" not in payload:
        raise CodedError("bad_decision")
    decision = payload["decision"]
    repository = repository_for(workspace)
    ranking = {}
    if decision is not None:
        entries = repository.load_catalog()["lexemes"]
        _ranked_library(entries, workspace, decision_audit=True)
        ranking = _reader_action_entry(entries, lexeme_id)["ranking"] or {}
    repository.set_decision(
        lexeme_id,
        decision,
        shelf_at=ranking.get("shelf", ""),
        score_at=ranking.get("score"),
        ranking_version=ranking.get("version", ""),
    )
    after = _with_ranking({"entries": repository.load_catalog()["lexemes"]}, workspace)
    return {
        "entry": _reader_action_entry(after["entries"], lexeme_id),
        "studyPrioritySource": after["studyPrioritySource"],
        "shelves": after["shelves"],
        "newBatch": after["newBatch"],
        "disputed": after["disputed"],
        "again": after["again"],
    }


def _download_book_covers(
    catalog: dict[str, Any],
    workspace: Path,
    *,
    retry_errors: bool = False,
    network: bool = True,
) -> dict[str, int]:
    books = vocab_cache.books_from_lexemes(catalog.get("lexemes") or [])
    db_path = workspace / ".app-data" / "cache" / "vocab.db"
    if db_path.is_file():
        try:
            identifiers = {book.key: book.asin for book in list_books(db_path)}
            books = [{**book, "asin": identifiers.get(str(book.get("key")), "")} for book in books]
        except Exception:
            logger.warning("Could not read book cover identifiers from cached Kindle database")
    cache_dir = workspace / ".app-data" / "covers"
    thumbnail_dir = workspace / ".app-data" / "cache" / "kindle-thumbnails"
    if not network:
        return book_covers.prefer_local_covers(books, cache_dir, thumbnail_dir)
    return book_covers.download_covers(
        books,
        cache_dir,
        local_thumbnail_dir=thumbnail_dir,
        retry_errors=retry_errors,
    )


def _lexeme_as_entry(lexeme: dict[str, Any]) -> dict[str, Any]:
    occurrences = list(lexeme.get("occurrences") or [])
    occurrence = max(
        occurrences,
        key=lambda item: (bool(item.get("context")), len(str(item.get("context") or "")), str(item.get("looked_up_at") or "")),
        default={},
    )
    processing = lexeme.get("processing") or {}
    return {
        "id": str(lexeme.get("id") or ""),
        "word": str(lexeme.get("display_form") or lexeme.get("lemma") or ""),
        "stem": str(lexeme.get("lemma") or ""),
        "context": str(occurrence.get("context") or ""),
        "book_key": str(occurrence.get("book_key") or ""),
        "book_title": str(occurrence.get("book_title") or ""),
        "authors": str(occurrence.get("authors") or ""),
        "language": str(lexeme.get("language") or "en"),
        "looked_up_at": str(occurrence.get("looked_up_at") or ""),
        "processing_status": "processed" if processing.get("state") == "ready" else processing.get("state"),
        "analysis": processing.get("analysis"),
    }


def _refresh_obsidian_destination_states(catalog: dict[str, Any]) -> None:
    """Derive Obsidian eligibility without treating it as a vocabulary source."""
    for lexeme in catalog.get("lexemes") or []:
        destination = (lexeme.get("destinations") or {}).get("obsidian")
        if not isinstance(destination, dict):
            continue
        processing_state = str((lexeme.get("processing") or {}).get("state") or "pending")
        analysis = (lexeme.get("processing") or {}).get("analysis") or {}
        score = analysis.get("importance_score")
        eligible = (
            processing_state == "ready"
            and analysis.get("accepted") is not False
            and isinstance(score, (int, float))
            and 3 <= score <= 10
        )
        destination["eligible"] = eligible
        destination["external_key"] = vocab_cache.normalize_lemma(
            str(analysis.get("base_form") or lexeme.get("lemma") or "")
        )
        destination.setdefault("last_checked_at", "")
        destination.setdefault("last_synced_at", "")
        if eligible:
            if destination.get("state") not in {"synced", "failed"}:
                destination["state"] = "missing"
            if destination.get("state") != "failed":
                destination["reason"] = ""
        elif processing_state == "rejected":
            reason = str(destination.get("reason") or "")
            unsupported = "unsupported_language" in (analysis.get("warnings") or [])
            destination.update(
                {
                    "state": "not_applicable",
                    "reason": "unsupported_language" if unsupported or reason == "unsupported_language" else "rejected",
                }
            )
        elif processing_state == "failed":
            destination.update({"state": "not_applicable", "reason": "processing_failed"})
        elif processing_state == "ready":
            destination.update({"state": "not_applicable", "reason": "unsupported_priority"})
        else:
            destination.update({"state": "not_applicable", "reason": "waiting_processing"})


def _reconcile_obsidian(catalog: dict[str, Any], cards_dir: Path) -> int:
    """Refresh destination evidence without importing Obsidian vocabulary."""
    now = vocab_cache.utc_now()
    cards = obsidian_sync.read_cards(cards_dir)
    existing_keys = set().union(*(obsidian_sync.lexical_aliases(item) for item in cards))
    _refresh_obsidian_destination_states(catalog)
    for lexeme in catalog.get("lexemes") or []:
        destination = lexeme["destinations"]["obsidian"]
        destination["last_checked_at"] = now
        if not destination.get("eligible"):
            destination["state"] = "not_applicable"
            continue
        analysis = (lexeme.get("processing") or {}).get("analysis") or {}
        aliases = {
            vocab_cache.normalize_lemma(str(value or ""))
            for value in [
                lexeme.get("lemma"),
                lexeme.get("display_form"),
                analysis.get("base_form"),
                *(lexeme.get("forms") or []),
            ]
        }
        aliases.discard("")
        if aliases & existing_keys:
            destination.update(
                {
                    "state": "synced",
                    "reason": "",
                    "last_synced_at": destination.get("last_synced_at") or now,
                }
            )
        else:
            destination.update({"state": "missing", "reason": ""})
    return len(cards)


def _analysis_for_unsupported_entry(lexeme: dict[str, Any]) -> dict[str, Any]:
    """Build an honest terminal result when the offline English optimizer cannot parse an entry."""
    occurrences = list(lexeme.get("occurrences") or [])
    return {
        "base_form": str(lexeme.get("lemma") or lexeme.get("display_form") or ""),
        "accepted": False,
        "importance_score": 0,
        "importance_note": "Offline-обработчик поддерживает только английские слова.",
        "frequency_note": "",
        "warnings": ["unsupported_language"],
        "source_occurrence_count": len(occurrences),
        "translation_status": "offline_only",
    }


def _analysis_by_lemma(analysis_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (analysis by normalized lexical_key, analysis by representative entry id)."""
    by_lemma: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    if not analysis_dir.exists():
        return by_lemma, by_id
    for path in analysis_dir.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read analysis audit file path=%s", path)
            continue
        importance = raw.get("importance") or {}
        frequencies = raw.get("frequencies") or {}
        wordnet = raw.get("wordnet") or {}
        analysis = {
            "base_form": str(raw.get("base_form") or raw.get("lexical_key") or ""),
            "pos": str(raw.get("pos") or ""),
            "accepted": bool(raw.get("accepted", True)),
            "importance_score": importance.get("score"),
            "importance_note": str(importance.get("explanation") or importance.get("note") or ""),
            "frequency_note": _frequency_note(frequencies),
            "lemma_zipf": frequencies.get("lemma_zipf"),
            "form_zipf": frequencies.get("form_zipf"),
            "wordnet_synset_count": wordnet.get("synset_count"),
            "wordnet_pos_count": wordnet.get("pos_count"),
            "warnings": sorted((raw.get("warnings") or {}).keys()) if isinstance(raw.get("warnings"), dict) else list(raw.get("warnings") or []),
            "tags": str(raw.get("tags") or ""),
            "source_word_forms": list(raw.get("source_word_forms") or []),
            "source_occurrence_count": raw.get("source_occurrence_count"),
            "processed_at": str(raw.get("processed_at") or ""),
            "translation_status": "offline_only",
        }
        key = vocab_cache.normalize_lemma(str(raw.get("lexical_key") or analysis["base_form"]))
        if key:
            by_lemma[key] = analysis
        entry = dict(raw.get("representative_entry") or {})
        entry_id = str(entry.get("id") or "")
        if entry_id:
            by_id[entry_id] = analysis
    return by_lemma, by_id


def _configure_stdio() -> None:
    # Rust writes UTF-8 bytes; a frozen Windows interpreter may start with the system code page.
    configure_input = getattr(sys.stdin, "reconfigure", None)
    if configure_input is not None:
        configure_input(encoding="utf-8", errors="strict")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _write_response(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    sys.stdout.write(text)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _workspace_root() -> Path:
    env_root = os.environ.get("KINDLE_CARDS_WORKSPACE")
    if env_root:
        return Path(env_root).resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "package.json").exists():
            return candidate
    return current


def missing_kindle_state() -> dict[str, Any]:
    return demo_state(
        source_name="Kindle не найден",
        source_status="Подключите Kindle по USB. Пока показаны демонстрационные слова.",
    )


def load_database_state(db_path: Path, source_label: str) -> dict[str, Any]:
    books = [{"label": "Все книги", "key": ""}]
    for book in list_books(db_path):
        label = book.title
        if book.authors:
            label += f" · {book.authors}"
        label += f" · {book.lookup_count}"
        books.append({"label": label, "key": book.key})
    entries = [_entry_for_frontend(entry) for entry in fetch_entries(db_path)]
    return {
        "sourceName": source_label,
        "sourceStatus": "Vocabulary Builder загружен",
        "books": books,
        "entries": entries,
    }


# A Kobo database with many books can be large; anything past this is not a words file.
MAX_IMPORT_BYTES = 300 * 1024 * 1024


def _import_reader_file(payload: dict[str, Any], workspace: Path, *, job_id: str) -> dict[str, Any]:
    """Merge words from a database file the user picked: Kindle vocab.db, KOReader or Kobo."""
    name = Path(str(payload.get("file_name") or "words.sqlite")).name
    try:
        data = base64.b64decode(str(payload.get("data_base64") or ""), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Не удалось прочитать файл") from exc
    if not data:
        raise ValueError("Файл пустой")
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("Файл слишком большой для базы слов")
    _emit_progress(job_id, "reading", f"Читаем {name}", 0, 3)
    import_dir = workspace / ".app-data" / "cache" / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    upload = import_dir / "upload.sqlite"
    upload.write_bytes(data)
    kind = reader_sources.detect_format(upload)
    if kind is None:
        raise ValueError(f"{name}: это не база слов Kindle (vocab.db), KOReader (vocabulary_builder.sqlite3) или Kobo (KoboReader.sqlite)")
    entries = [_entry_for_frontend(entry) for entry in reader_sources.fetch_entries(upload, kind)]
    _emit_progress(job_id, "merging", "Объединяем формы и известные леммы", 1, 3)
    catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
    before = len(catalog["lexemes"])
    catalog = vocab_cache.merge_kindle(catalog, entries, sync_id=uuid.uuid4().hex, mark_new=True)
    _refresh_obsidian_destination_states(catalog)
    repository = repository_for(workspace)
    repository.save_catalog(catalog)
    added = len(catalog["lexemes"]) - before
    label = reader_sources.FORMAT_LABELS[kind]
    _emit_progress(job_id, "completed", f"Импортировано из {label}: {added} новых слов", 3, 3)
    logger.info("Imported reader file job_id=%s kind=%s entries=%d new_lexemes=%d", job_id, kind, len(entries), added)
    result = _catalog_response(
        repository.load_catalog(),
        workspace=workspace,
        source_name=f"{label} · {name}",
        source_status="Слова из файла добавлены",
        queue_status=repository.queue_status(),
    )
    result["imported"] = {"format": kind, "label": label, "lookups": len(entries), "new_words": added}
    return result


def _entry_for_frontend(entry: dict[str, object]) -> dict[str, str]:
    payload = {
        "word": str(entry.get("word") or ""),
        "stem": str(entry.get("stem") or ""),
        "context": str(entry.get("context") or ""),
        "book_key": str(entry.get("book_key") or ""),
        "book_title": str(entry.get("book_title") or ""),
        "authors": str(entry.get("authors") or ""),
        "language": str(entry.get("language") or ""),
        "lookup_id": str(entry.get("lookup_id") or ""),
        "looked_up_at": str(entry.get("looked_up_at") or ""),
        "processing_status": "raw",
        "export_status": "none",
    }
    payload["id"] = _entry_id(payload)
    return payload


def _entry_id(entry: dict[str, object]) -> str:
    raw = "|".join(
        str(entry.get(key) or "")
        for key in ["word", "stem", "context", "book_key", "book_title", "looked_up_at"]
    )
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def export_frontend_entries(
    entries: list[object],
    output_path: Path,
    export_format: str,
    workspace: Path,
) -> int:
    saved_rows = _load_saved_optimized_rows(workspace / ".app-data" / "optimized" / "optimized.tsv")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in entries:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        row = _optimized_row_from_frontend(entry)
        if row is None:
            row = _saved_optimized_row_for_entry(entry, saved_rows)
        if row is None or not _is_exportable_optimized_row(row):
            continue
        key = _optimized_export_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "anki":
        _write_anki_export(rows, output_path)
    elif export_format == "quizlet":
        _write_quizlet_export(rows, output_path)
    else:
        raise ValueError(f"Unsupported export format: {export_format}")

    logger.info("Exported optimized rows path=%s format=%s rows=%d", output_path, export_format, len(rows))
    return len(rows)


def _optimized_row_from_frontend(entry: dict[str, Any]) -> dict[str, str] | None:
    analysis = entry.get("analysis")
    if not isinstance(analysis, dict):
        return None
    if analysis.get("accepted") is False:
        return None
    if _export_score(analysis.get("importance_score")) is None:
        return None

    warnings = analysis.get("warnings") or []
    source_forms = analysis.get("source_word_forms") or [entry.get("word") or ""]
    return {
        "Word": _clean_export(entry.get("word")),
        "Base form": _clean_export(analysis.get("base_form") or entry.get("stem") or entry.get("word")),
        "Part of speech": _clean_export(analysis.get("pos")),
        "Russian meaning(s)": _clean_export(analysis.get("russian_meanings")),
        "Generated context sentence EN": _clean_export(analysis.get("generated_context_en")),
        "Generated context sentence RU": _clean_export(analysis.get("generated_context_ru")),
        "Importance 0-10": _clean_export(analysis.get("importance_score")),
        "Importance note": _clean_export(analysis.get("importance_note")),
        "Lemma Zipf": _clean_export(analysis.get("lemma_zipf")),
        "Form Zipf": _clean_export(analysis.get("form_zipf")),
        "WordNet synset count": _clean_export(analysis.get("wordnet_synset_count")),
        "WordNet POS count": _clean_export(analysis.get("wordnet_pos_count")),
        "Warnings": _clean_export(_join_export_values(warnings)),
        "Tags": _clean_export(analysis.get("tags")),
        "Source word forms": _clean_export(_join_export_values(source_forms)),
        "Source occurrence count": _clean_export(analysis.get("source_occurrence_count")),
        "Original word": _clean_export(entry.get("word")),
        "Original stem": _clean_export(entry.get("stem")),
        "Original context": _clean_export(entry.get("context")),
        "Original book_title": _clean_export(entry.get("book_title")),
        "Original authors": _clean_export(entry.get("authors")),
        "Original language": _clean_export(entry.get("language")),
        "Original looked_up_at": _clean_export(entry.get("looked_up_at")),
    }


def _load_saved_optimized_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        for raw_row in reader:
            row = {header: str((raw_row or {}).get(header) or "") for header in OPTIMIZED_TSV_HEADER}
            rows[_optimized_export_key(row)] = row
    return rows


def _saved_optimized_row_for_entry(
    entry: dict[str, Any],
    saved_rows: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    if not saved_rows:
        return None
    analysis = entry.get("analysis") if isinstance(entry.get("analysis"), dict) else {}
    base_candidates = [
        str(analysis.get("base_form") or ""),
        str(entry.get("stem") or ""),
        str(entry.get("word") or ""),
    ]
    book_title = str(entry.get("book_title") or "")
    authors = str(entry.get("authors") or "")
    for base_form in base_candidates:
        key = _optimized_export_key_from_values(base_form, book_title, authors)
        if key in saved_rows:
            return saved_rows[key]
    return None


def _is_exportable_optimized_row(row: dict[str, str]) -> bool:
    return _export_score(row.get("Importance 0-10")) is not None


def _write_anki_export(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OPTIMIZED_TSV_HEADER, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in OPTIMIZED_TSV_HEADER})


def _write_quizlet_export(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(["term", "definition"])
        for row in rows:
            source = " - ".join(part for part in [row.get("Original book_title", ""), row.get("Original authors", "")] if part)
            details = [
                f"base: {row.get('Base form', '')}",
                f"score: {row.get('Importance 0-10', '')}/10",
            ]
            if row.get("Part of speech"):
                details.append(f"pos: {row['Part of speech']}")
            if row.get("Lemma Zipf"):
                details.append(f"lemma Zipf: {row['Lemma Zipf']}")
            if row.get("Form Zipf"):
                details.append(f"form Zipf: {row['Form Zipf']}")
            if row.get("Importance note"):
                details.append(f"note: {row['Importance note']}")
            if row.get("Original context"):
                details.append(f"context: {row['Original context']}")
            if source:
                details.append(f"source: {source}")
            writer.writerow([row.get("Word", ""), "; ".join(details)])


def _optimized_export_key(row: dict[str, str]) -> str:
    return _optimized_export_key_from_values(
        row.get("Base form", ""),
        row.get("Original book_title", ""),
        row.get("Original authors", ""),
    )


def _optimized_export_key_from_values(base_form: object, book_title: object, authors: object) -> str:
    return "\t".join(str(value or "").casefold().strip() for value in [base_form, book_title, authors])


def _export_score(value: object) -> int | None:
    try:
        score = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    if score < 0 or score > 10:
        return None
    return score


def _join_export_values(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item))
    return str(value or "")


def _clean_export(value: object) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return html.escape(text, quote=False)


def _entry_updates_from_analysis(
    analysis_dir: Path,
    submitted_entries: list[object],
    tsv_path: str,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    submitted_ids = {
        str(entry.get("id") or _entry_id(entry))
        for entry in submitted_entries
        if isinstance(entry, dict)
    }
    for path in sorted(analysis_dir.glob("*.json")):
        try:
            analysis = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read analysis JSON path=%s", path)
            continue

        entry = dict(analysis.get("representative_entry") or {})
        entry_id = str(entry.get("id") or _entry_id(entry))
        if entry_id not in submitted_ids:
            continue
        importance = dict(analysis.get("importance") or {})
        frequencies = dict(analysis.get("frequencies") or {})
        wordnet = dict(analysis.get("wordnet") or {})
        warnings = dict(analysis.get("warnings") or {})
        tsv_row = dict(analysis.get("tsv_row") or {})
        accepted = bool(analysis.get("accepted"))
        updates.append(
            {
                "id": entry_id,
                "processing_status": "processed" if accepted else "rejected",
                "analysis": {
                    "base_form": str(analysis.get("base_form") or entry.get("stem") or entry.get("word") or ""),
                    "pos": str(analysis.get("pos") or ""),
                    "accepted": accepted,
                    "importance_score": importance.get("score"),
                    "importance_note": str(importance.get("note") or ""),
                    "frequency_note": _frequency_note(frequencies),
                    "lemma_zipf": frequencies.get("lemma_zipf"),
                    "form_zipf": frequencies.get("form_zipf"),
                    "wordnet_synset_count": wordnet.get("synset_count"),
                    "wordnet_pos_count": wordnet.get("pos_count"),
                    "warnings": sorted(warnings),
                    "tags": str(tsv_row.get("Tags") or ""),
                    "source_word_forms": analysis.get("source_word_forms") or [],
                    "source_occurrence_count": analysis.get("source_occurrence_count"),
                    "processed_at": str(analysis.get("processed_at") or ""),
                    "translation_status": "offline_only",
                    "tsv_path": tsv_path,
                },
            }
        )

    if updates:
        return updates

    return [
        {
            "id": str(entry.get("id") or _entry_id(entry)),
            "processing_status": "skipped",
            "analysis": {
                "base_form": str(entry.get("stem") or entry.get("word") or ""),
                "accepted": True,
                "importance_note": "уже есть в processed snapshot",
                "translation_status": "offline_only",
                "tsv_path": tsv_path,
            },
        }
        for entry in submitted_entries
        if isinstance(entry, dict)
    ]


def _frequency_note(frequencies: dict[str, Any]) -> str:
    lemma = frequencies.get("lemma_zipf")
    form = frequencies.get("form_zipf")
    parts = []
    if lemma is not None:
        parts.append(f"lemma Zipf {lemma}")
    if form is not None:
        parts.append(f"form Zipf {form}")
    return ", ".join(parts)


# (word, zipf, lookup days of June 2026, book, sentence, warnings); invented sentences, common words.
_DEMO_EXTRA = [
    ("lantern", 3.9, ["2026-06-19", "2026-06-14"], "The Night Reader", "He raised the lantern above the stairs."),
    ("meander", 3.2, ["2026-06-18"], "Shadows and Signals", "The path began to meander through the fields."),
    ("quibble", 2.8, ["2026-06-16"], "Shadows and Signals", "They did not quibble over the price."),
    ("ephemeral", 3.1, ["2026-06-15"], "The Night Reader", "Their happiness was brief and ephemeral."),
    ("tarn", 2.4, ["2026-06-12"], "Shadows and Signals", "A cold tarn lay between the hills."),
    ("nightwatch", 0.0, ["2026-06-19"], "The Night Reader", "The nightwatch passed beneath the window."),
]
_DEMO_ZIPF = {"afraid": 4.6, "glimpse": 3.9, "dread": 3.7}


def _demo_catalog() -> dict[str, Any]:
    """The demo library: invented lookups, already processed, so every shelf of the ranking has words.

    It never touches the reader's SQLite library; the analyses are fixed, not computed.
    """
    raw = list(demo_state()["entries"])
    for word, _zipf, days, book, context in _DEMO_EXTRA:
        for day in days:
            raw.append(
                _entry_for_frontend(
                    {
                        "word": word,
                        "stem": word,
                        "context": context,
                        "book_key": book,
                        "book_title": book,
                        "authors": "Demo Library",
                        "language": "en",
                        "looked_up_at": day,
                    }
                )
            )
    catalog = vocab_cache.merge_kindle(vocab_cache.empty_catalog(), raw, sync_id="demo", mark_new=True)
    zipf = {**_DEMO_ZIPF, **{word: value for word, value, *_ in _DEMO_EXTRA}}
    for lexeme in catalog["lexemes"]:
        key = str(lexeme["lemma"])
        glued = key == "nightwatch"
        lexeme["processing"] = {
            "state": "ready",
            "analysis": {
                "base_form": key,
                "pos": "n",
                "accepted": True,
                "importance_score": 5,
                "lemma_zipf": zipf.get(key, 3.5),
                "form_zipf": zipf.get(key, 3.5),
                "wordnet_synset_count": 0 if glued else 2,
                "wordnet_pos_count": 1,
                "warnings": ["possibly_glued_words"] if glued else [],
                "translation_status": "offline_only",
            },
            "updated_at": "2026-06-19T00:00:00+00:00",
            "error": "",
            "origin": "demo",
        }
    return catalog


def demo_state(source_name: str = "Demo Kindle", source_status: str = "Загружены демонстрационные данные") -> dict[str, Any]:
    entries = [
        {
            "word": "afraid",
            "stem": "afraid",
            "context": "She was afraid to open the old door.",
            "book_key": "The Night Reader",
            "book_title": "The Night Reader",
            "authors": "Demo Library",
            "language": "en",
            "looked_up_at": "2026-06-19",
        },
        {
            "word": "glimpse",
            "stem": "glimpse",
            "context": "For a moment he caught a glimpse of the city below.",
            "book_key": "The Night Reader",
            "book_title": "The Night Reader",
            "authors": "Demo Library",
            "language": "en",
            "looked_up_at": "2026-06-18",
        },
        {
            "word": "dread",
            "stem": "dread",
            "context": "A quiet dread settled over the room.",
            "book_key": "Shadows and Signals",
            "book_title": "Shadows and Signals",
            "authors": "Demo Library",
            "language": "en",
            "looked_up_at": "2026-06-17",
        },
    ]
    return {
        "sourceName": source_name,
        "sourceStatus": source_status,
        "books": [
            {"label": "Все книги", "key": ""},
            {"label": "The Night Reader · Demo Library · 2", "key": "The Night Reader"},
            {"label": "Shadows and Signals · Demo Library · 1", "key": "Shadows and Signals"},
        ],
        "entries": [_entry_for_frontend(entry) for entry in entries],
    }


if __name__ == "__main__":
    raise SystemExit(main())
