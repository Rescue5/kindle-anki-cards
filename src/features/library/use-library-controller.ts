import * as React from "react";
import { callBackend, cancelBackend, defaultSettings, listenProgress } from "@/lib/backend";
import { mergeObsidianEvidence, obsidianConfig, readObsidianEvidence, type ObsidianCheck } from "./load-library";
import {
  enrichmentCounts,
  filterLexemes,
  idleOperation,
  kindleSignature,
  KINDLE_PROBE_INTERVAL_MS,
  shouldAutoEnrich,
  shouldAutoProcessQueue,
  shouldAutoSyncKindle,
  type QuickFilter,
} from "./domain";
import type {
  AppSettings,
  BookOption,
  ConnectorStatus,
  CoverSummary,
  LexemeRecord,
  LibraryRanking,
  LibraryResult,
  Operation,
  ProgressEvent,
  QueueStatus,
} from "@/types";
import { LibraryEdits } from "./library-edits";
import { rankingOf, wordsLabel } from "@/features/home/home-domain";

const unknownConnectors: ConnectorStatus = {
  kindle: { state: "unknown", label: "Kindle", checked_at: "" },
  obsidian: { state: "disabled", label: "Obsidian", checked_at: "" },
};

type ProcessingResult = {
  processed_new: number;
  accepted_new: number;
  rejected_new: number;
  skipped_existing: number;
  failed_new?: number;
  entries: LexemeRecord[];
  queue_status: QueueStatus;
  message?: string;
};

type EnrichResult = {
  requested: number;
  enriched: number;
  failed: number;
  error: string;
  message: string;
  entries: LexemeRecord[];
  queue_status: QueueStatus;
};

type ObsidianResult = {
  added: number;
  skipped: number;
  entries: LexemeRecord[];
  queue_status: QueueStatus;
};

const emptyQueue: QueueStatus = { pending: 0, processing: 0, failed: 0, total: 0 };

function jobId() {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `job-${Date.now()}`;
}

export function useLibraryController() {
  const [entries, setEntries] = React.useState<LexemeRecord[]>([]);
  const [books, setBooks] = React.useState<BookOption[]>([{ label: "Все книги", key: "" }]);
  const [coverSummary, setCoverSummary] = React.useState<CoverSummary>();
  const [coversBusy, setCoversBusy] = React.useState(false);
  const [connectors, setConnectors] = React.useState<ConnectorStatus>(unknownConnectors);
  const [settings, setSettings] = React.useState<AppSettings>(defaultSettings);
  const settingsRef = React.useRef(settings);
  const savedSettingsRef = React.useRef(settings);
  const settingsWritesRef = React.useRef<Promise<void>>(Promise.resolve());
  const pendingSettingsWrites = React.useRef(0);
  const [settingsSaving, setSettingsSaving] = React.useState(false);
  const [obsidianCheck, setObsidianCheck] = React.useState<ObsidianCheck>({ status: "idle" });
  const obsidianRevision = React.useRef(0);
  const obsidianReadsRef = React.useRef<Promise<void>>(Promise.resolve());
  const obsidianSyncInFlight = React.useRef(false);
  const [query, setQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  const debounceRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    debounceRef.current = window.setTimeout(() => setDebouncedQuery(query), 180);
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [query]);
  const [selectedBookKey, setSelectedBookKey] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [selectedId, setSelectedId] = React.useState("");
  const [operation, setOperation] = React.useState<Operation>(idleOperation);
  const [queueStatus, setQueueStatus] = React.useState<QueueStatus>(emptyQueue);
  const [loading, setLoading] = React.useState(true);
  // The short-list parts of the last library answer (null until the bridge sends them).
  const [ranking, setRanking] = React.useState<LibraryRanking | null>(null);
  // `load_demo` words are shown on Главная only; nothing of them is stored or exported.
  const [demo, setDemo] = React.useState(false);
  const demoRef = React.useRef(false);
  const entriesRef = React.useRef(entries);
  entriesRef.current = entries;
  const loadingRef = React.useRef(loading);
  loadingRef.current = loading;
  const operationRef = React.useRef(operation);
  operationRef.current = operation;
  const prevConnectorsRef = React.useRef<ConnectorStatus>(unknownConnectors);
  const lastAutoSyncSignatureRef = React.useRef<string | null>(null);
  const lastAutoSyncAttemptAtRef = React.useRef(0);
  const probeInFlightRef = React.useRef<Promise<void> | null>(null);
  const manualProbe = React.useRef(false);
  const [findingReader, setFindingReader] = React.useState(false);
  const autoSyncInFlightRef = React.useRef(false);
  const processingInFlightRef = React.useRef(false);
  const syncKindleRef = React.useRef(syncKindlePlaceholder);
  function syncKindlePlaceholder() { return Promise.resolve(); }

  const selectedBook = React.useMemo(
    () => books.find((book) => book.key === selectedBookKey) ?? books[0],
    [books, selectedBookKey],
  );
  const visibleEntries = React.useMemo(
    () => filterLexemes(entries, debouncedQuery, selectedBook, quickFilter),
    [entries, debouncedQuery, selectedBook, quickFilter],
  );
  const selectedEntry = React.useMemo(
    () => visibleEntries.find((entry) => entry.id === selectedId) ?? visibleEntries[0] ?? null,
    [visibleEntries, selectedId],
  );

  React.useEffect(() => {
    if (!selectedEntry) {
      setSelectedId("");
    } else if (selectedEntry.id !== selectedId) {
      setSelectedId(selectedEntry.id);
    }
  }, [selectedEntry, selectedId]);

  const applyLibrary = React.useCallback((result: LibraryResult) => {
    entriesRef.current = result.entries;
    setEntries(result.entries);
    setRanking(rankingOf(result));
    setBooks(result.books.length ? result.books : [{ label: "Все книги", key: "" }]);
    setCoverSummary(result.coverSummary);
    setConnectors((current) => ({
      kindle: result.connectors?.kindle?.state === "unknown" ? current.kindle : (result.connectors?.kindle ?? current.kindle),
      obsidian: result.connectors?.obsidian ?? current.obsidian,
      anki: result.connectors?.anki?.state === "unknown" || !result.connectors?.anki ? current.anki : result.connectors.anki,
    }));
    setQueueStatus(result.queueStatus ?? emptyQueue);
  }, []);

  const edits = React.useMemo(() => new LibraryEdits(
    (id) => !demoRef.current && !loadingRef.current && operationRef.current.status !== "running"
      && entriesRef.current.some((entry) => entry.id === id),
    applyLibrary,
    (result) => {
      setEntries((previous) => previous.map((entry) => entry.id === result.entry.id ? result.entry : entry));
      if ("newBatch" in result) {
        setRanking((previous) => previous ? { ...previous, shelves: result.shelves, newBatch: result.newBatch, disputed: result.disputed, again: result.again } : previous);
      }
    },
  ), [applyLibrary]);

  const loadLibrary = React.useCallback(async () => {
    const ticket = edits.beginRead();
    const result = await callBackend<LibraryResult>("load_library", {});
    if (edits.accepts(ticket) && !demoRef.current) applyLibrary(result);
  }, [applyLibrary, edits]);

  const checkObsidian = React.useCallback((current = savedSettingsRef.current) => {
    const revision = ++obsidianRevision.current;
    const version = edits.getVersion();
    const config = obsidianConfig(current);
    if (!config) {
      setObsidianCheck({ status: "idle" });
      return;
    }
    setObsidianCheck({ status: "checking" });
    obsidianReadsRef.current = obsidianReadsRef.current.then(async () => {
      if (revision !== obsidianRevision.current || !edits.acceptsVersion(version) || demoRef.current) return;
      try {
        const result = await readObsidianEvidence(config);
        if (revision !== obsidianRevision.current || !edits.acceptsVersion(version) || demoRef.current) return;
        setEntries((previous) => mergeObsidianEvidence(previous, result.entries));
        setObsidianCheck({ status: "ready" });
      } catch (error) {
        if (revision !== obsidianRevision.current || !edits.acceptsVersion(version) || demoRef.current) return;
        setObsidianCheck({ status: "error", message: String(error) });
      }
    });
  }, [edits]);

  const saveCardEdit = React.useCallback(async (id: string, changes: Parameters<LibraryEdits["saveCardEdit"]>[1]) => {
    await edits.saveCardEdit(id, changes);
    if (!demoRef.current) checkObsidian();
  }, [edits, checkObsidian]);

  const setWordDecision = React.useCallback(async (id: string, decision: Parameters<LibraryEdits["setWordDecision"]>[1]) => {
    await edits.setWordDecision(id, decision);
    if (!demoRef.current) checkObsidian();
  }, [edits, checkObsidian]);

  const saveSettings = React.useCallback((patch: Partial<AppSettings>) => {
    settingsRef.current = { ...settingsRef.current, ...patch };
    setSettings(settingsRef.current);
    pendingSettingsWrites.current += 1;
    setSettingsSaving(true);

    const saved = settingsWritesRef.current.then(async () => {
      const previous = savedSettingsRef.current;
      await callBackend<{ saved: boolean }>("save_settings", { settings: patch });
      const next = { ...previous, ...patch };
      savedSettingsRef.current = next;
      if (demoRef.current) return;
      if (next.obsidian_sync_enabled !== previous.obsidian_sync_enabled
        || next.obsidian_vault_path !== previous.obsidian_vault_path
        || next.obsidian_cards_path !== previous.obsidian_cards_path) {
        checkObsidian(next);
      }
      if (next.export_batch_size !== previous.export_batch_size) await loadLibrary();
    }).finally(() => {
      pendingSettingsWrites.current -= 1;
      if (pendingSettingsWrites.current === 0) {
        // Keep optimistic edits while writes are queued. After a failure, show what was saved.
        settingsRef.current = savedSettingsRef.current;
        setSettings(settingsRef.current);
        setSettingsSaving(false);
      }
    });
    settingsWritesRef.current = saved.catch(() => undefined);
    return saved;
  }, [applyLibrary, checkObsidian, edits]);

  React.useEffect(() => {
    let cancelled = false;
    const ticket = edits.beginRead();
    void Promise.all([callBackend<AppSettings>("load_settings", {}), callBackend<LibraryResult>("load_library", {})])
      .then(([loadedSettings, library]) => {
        if (cancelled) return;
        if (pendingSettingsWrites.current === 0) {
          settingsRef.current = loadedSettings;
          savedSettingsRef.current = loadedSettings;
          setSettings(loadedSettings);
        }
        if (edits.accepts(ticket) && !demoRef.current) applyLibrary(library);
        if (!demoRef.current) checkObsidian();
      })
      .catch((error) => {
        if (cancelled || !edits.accepts(ticket)) return;
        setOperation({ ...idleOperation, status: "error", title: "Не удалось открыть библиотеку", message: String(error), error: String(error) });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyLibrary, checkObsidian, edits]);

  React.useEffect(() => {
    let unlisten: () => void = () => {};
    void listenProgress((progress: ProgressEvent) => {
      setOperation((current) => {
        if (current.id !== progress.job_id || current.status !== "running") return current;
        return {
          ...current,
          // Processing is complete for the screen after the new ranking has loaded.
          status: progress.stage === "completed" && current.kind !== "processing" ? "completed" : "running",
          stage: progress.stage,
          message: progress.message,
          current: progress.current,
          total: progress.total,
        };
      });
    }).then((dispose) => {
      unlisten = dispose;
    });
    return () => unlisten();
  }, []);

  const lastProbedAt = React.useRef(0);
  const probeConnectors = React.useCallback(async (force = false) => {
    if (document.visibilityState !== "visible") return;
    if (probeInFlightRef.current) return probeInFlightRef.current;
    const now = Date.now();
    if (!force && now - lastProbedAt.current < KINDLE_PROBE_INTERVAL_MS) return;
    lastProbedAt.current = now;
    const previous = prevConnectorsRef.current;
    const probe = callBackend<ConnectorStatus>("connector_status", {}).then((status) => {
      prevConnectorsRef.current = status;
      setConnectors(status);
      const kindle = status.kindle;
      const shouldSync = shouldAutoSyncKindle({
        previous: previous.kindle,
        current: kindle,
        lastSyncedSignature: lastAutoSyncSignatureRef.current,
        lastAttemptAt: lastAutoSyncAttemptAtRef.current,
        now,
      });
      if (shouldSync && !manualProbe.current && !demoRef.current && operationRef.current.status !== "running" && !autoSyncInFlightRef.current) {
        lastAutoSyncAttemptAtRef.current = now;
        autoSyncInFlightRef.current = true;
        void syncKindleRef.current().finally(() => {
          autoSyncInFlightRef.current = false;
        });
      }
    }).catch(() => {
      setConnectors((current) => ({ ...current, kindle: { ...current.kindle, state: "error", checked_at: new Date().toISOString() } }));
    }).finally(() => { probeInFlightRef.current = null; });
    probeInFlightRef.current = probe;
    return probe;
  }, []);

  const findReader = React.useCallback(async () => {
    if (manualProbe.current || demoRef.current) return;
    manualProbe.current = true;
    setFindingReader(true);
    try {
      await probeConnectors(true);
    } finally {
      manualProbe.current = false;
      setFindingReader(false);
    }
  }, [probeConnectors]);

  React.useEffect(() => {
    void probeConnectors();
    const interval = window.setInterval(() => void probeConnectors(), KINDLE_PROBE_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void probeConnectors();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onVisibility);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onVisibility);
    };
  }, [probeConnectors]);

  const begin = React.useCallback((kind: Operation["kind"], title: string, message: string) => {
    const id = jobId();
    operationRef.current = { id, kind, status: "running", title, message, current: 0, total: 0, stage: "starting", error: "" };
    setOperation(operationRef.current);
    return id;
  }, []);

  const fail = React.useCallback((id: string, title: string, error: unknown) => {
    const message = String(error);
    const cancelled = message.toLocaleLowerCase("ru").includes("отменена");
    setOperation({
      id,
      kind: operationRef.current.kind,
      status: cancelled ? "cancelled" : "error",
      title: cancelled ? "Операция отменена" : title,
      message: cancelled ? "Дочерний процесс остановлен" : message,
      current: 0,
      total: 0,
      stage: cancelled ? "cancelled" : "failed",
      error: cancelled ? "" : message,
    });
  }, []);

  const backgroundCoversInFlightRef = React.useRef(false);
  // Online cover lookup can take a minute; it runs outside the operation slot so
  // it never delays queue processing. Only books and covers are applied, because
  // the entries in this response may predate concurrent processing results.
  const fetchCoversInBackground = React.useCallback(async () => {
    if (backgroundCoversInFlightRef.current) return;
    backgroundCoversInFlightRef.current = true;
    try {
      const version = edits.getVersion();
      const result = await callBackend<LibraryResult>("download_covers", { retry_errors: false });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      setBooks(result.books.length ? result.books : [{ label: "Все книги", key: "" }]);
      setCoverSummary(result.coverSummary);
    } catch {
      // Covers are decorative; the manual "Загрузить обложки" action reports errors.
    } finally {
      backgroundCoversInFlightRef.current = false;
    }
  }, [edits]);

  const syncKindle = React.useCallback(async () => {
    if (operationRef.current.status === "running" || edits.isWriting()) return;
    lastAutoSyncAttemptAtRef.current = Date.now();
    edits.switchLibrary();
    demoRef.current = false;
    setDemo(false);
    const id = begin("kindle", "Синхронизация", "Ищем подключённую читалку");
    try {
      const version = edits.getVersion();
      const result = await callBackend<LibraryResult>("sync_kindle", { job_id: id });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      applyLibrary(result);
      const connected = result.connectors.kindle.state === "connected";
      const signature = kindleSignature(result.connectors.kindle);
      if (connected && signature) {
        lastAutoSyncSignatureRef.current = signature;
      }
      if (connected) checkObsidian();
      const covers = result.coverSummary;
      if (connected && covers && covers.available < covers.total) void fetchCoversInBackground();
      setOperation((current) => ({
        ...current,
        status: connected ? "completed" : "error",
        stage: connected ? "completed" : "failed",
        title: connected ? `Синхронизировано: ${result.connectors.kindle.label}` : "Читалка не найдена",
        message: connected ? `В библиотеке ${wordsLabel(result.entries.length)}` : "Библиотека сохранена; подключите читалку по USB или выберите файл со словами",
        error: connected ? "" : "Читалка не найдена",
      }));
    } catch (error) {
      fail(id, "Синхронизация остановлена", error);
    } finally {
      void probeConnectors(true);
    }
  }, [applyLibrary, begin, checkObsidian, edits, fail, fetchCoversInBackground, probeConnectors]);
  syncKindleRef.current = syncKindle;

  // A words database picked by hand: Kindle vocab.db, KOReader or Kobo. The bridge detects which.
  const importReaderFile = React.useCallback(async (file: File) => {
    if (operationRef.current.status === "running" || edits.isWriting()) return;
    edits.switchLibrary();
    demoRef.current = false;
    setDemo(false);
    const id = begin("kindle", "Импорт слов", `Читаем ${file.name}`);
    try {
      if (file.size > MAX_IMPORT_BYTES) throw new Error(`${file.name} слишком большой для базы слов`);
      const version = edits.getVersion();
      const result = await callBackend<LibraryResult>("import_reader_file", { job_id: id, file_name: file.name, data_base64: await fileToBase64(file) });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      applyLibrary(result);
      checkObsidian();
      const imported = result.imported;
      setOperation((current) => ({
        ...current,
        status: "completed",
        stage: "completed",
        title: imported ? `Импорт из ${imported.label}` : "Импорт завершён",
        message: imported ? `Новых слов: ${imported.new_words}; записей в файле: ${imported.lookups}` : `В библиотеке ${wordsLabel(result.entries.length)}`,
        error: "",
      }));
    } catch (error) {
      fail(id, "Не удалось импортировать файл", error);
    }
  }, [applyLibrary, begin, checkObsidian, edits, fail]);

  const downloadCovers = React.useCallback(async () => {
    if (operationRef.current.status === "running" || edits.isWriting()) return;
    const id = begin("covers", "Обложки книг", "Ищем и сохраняем обложки");
    setCoversBusy(true);
    try {
      const version = edits.getVersion();
      const result = await callBackend<LibraryResult>("download_covers", { job_id: id });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      applyLibrary(result);
      const available = result.coverSummary?.available ?? 0;
      const total = result.coverSummary?.total ?? 0;
      setOperation((current) => ({ ...current, status: "completed", stage: "completed",
        title: "Обложки сохранены", message: `Найдено ${available} из ${total}. Доступны без интернета.`, error: "" }));
    } catch (error) {
      fail(id, "Не удалось загрузить обложки", error);
    } finally {
      setCoversBusy(false);
    }
  }, [applyLibrary, begin, edits, fail]);

  const processQueue = React.useCallback(async (includeFailed = false) => {
    if (processingInFlightRef.current || edits.isWriting()) return;
    processingInFlightRef.current = true;
    const queueSize = queueStatus.pending + (includeFailed ? queueStatus.failed : 0);
    const id = begin("processing", "Обработка слов", `В очереди ${wordsLabel(queueSize)}`);
    try {
      const version = edits.getVersion();
      const result = await callBackend<ProcessingResult>("process_queue", { job_id: id, include_failed: includeFailed });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      setEntries(result.entries);
      setQueueStatus(result.queue_status ?? emptyQueue);
      // Newly analysed words get a place in the ranking; the short list must follow.
      if (result.processed_new > 0) {
        await loadLibrary().catch(() => undefined);
        checkObsidian();
      }
      const skipped = result.skipped_existing ?? 0;
      const failed = result.failed_new ?? 0;
      const defaultMessage = [
        `Обработано: ${result.processed_new}`,
        `принято: ${result.accepted_new}`,
        `отклонено: ${result.rejected_new}`,
        ...(skipped > 0 ? [`пропущено ранее: ${skipped}`] : []),
        ...(failed > 0 ? [`ошибок: ${failed}`] : []),
      ].join("; ");
      const message = result.message || defaultMessage;
      setOperation((current) => ({
        ...current,
        status: failed > 0 ? "error" : "completed",
        stage: "completed",
        title: failed > 0 ? "Обработка завершена с ошибками" : "Обработка завершена",
        message,
        error: failed > 0 ? message : "",
        current: queueSize,
        total: queueSize,
      }));
    } catch (error) {
      void loadLibrary().catch(() => undefined);
      fail(id, "Offline-обработка остановлена", error);
    } finally {
      processingInFlightRef.current = false;
    }
  }, [begin, checkObsidian, edits, fail, loadLibrary, queueStatus.failed, queueStatus.pending]);

  const retryFailed = React.useCallback(() => processQueue(true), [processQueue]);

  // The example library on Главная for a reader who has no words yet. While it is shown the queue stays idle.
  const loadDemo = React.useCallback(async () => {
    if (demoRef.current || operationRef.current.status === "running") return;
    edits.switchLibrary();
    demoRef.current = true;
    loadingRef.current = true;
    setDemo(true);
    setLoading(true);
    setOperation(idleOperation);
    // A late live-vault response must not affect the example library.
    obsidianRevision.current += 1;
    setObsidianCheck({ status: "idle" });
    try {
      const ticket = edits.beginRead();
      const result = await callBackend<LibraryResult>("load_demo", {});
      if (edits.accepts(ticket) && demoRef.current) applyLibrary(result);
    } catch (error) {
      demoRef.current = false;
      setDemo(false);
      setOperation({ ...idleOperation, status: "error", title: "Не удалось показать пример", message: String(error), error: String(error) });
    } finally {
      setLoading(false);
    }
  }, [applyLibrary, edits]);

  const exitDemo = React.useCallback(async () => {
    edits.switchLibrary();
    loadingRef.current = true;
    setLoading(true);
    try {
      const ticket = edits.beginRead();
      const result = await callBackend<LibraryResult>("load_library", {});
      if (!edits.accepts(ticket)) return;
      applyLibrary(result);
      demoRef.current = false;
      setDemo(false);
      setOperation(idleOperation);
      checkObsidian();
    } catch (error) {
      setOperation({ ...idleOperation, status: "error", title: "Не удалось открыть библиотеку", message: String(error), error: String(error) });
    } finally {
      setLoading(false);
    }
  }, [applyLibrary, checkObsidian, edits]);

  React.useEffect(() => {
    if (!shouldAutoProcessQueue({ loading: loading || demo, inFlight: processingInFlightRef.current, queue: queueStatus, operation })) return;
    void processQueue();
  }, [demo, loading, operation, processQueue, queueStatus]);

  const syncObsidian = React.useCallback(async () => {
    if (demo || edits.isWriting() || obsidianSyncInFlight.current || operationRef.current.status === "running"
      || pendingSettingsWrites.current > 0 || obsidianCheck.status !== "ready") return;
    obsidianSyncInFlight.current = true;
    const id = begin("obsidian", "Синхронизация Obsidian", "Сверяем глобальную очередь карточек");
    try {
      const version = edits.getVersion();
      const result = await callBackend<ObsidianResult>("sync_obsidian", { job_id: id });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      setEntries((previous) => mergeObsidianEvidence(previous, result.entries));
      setOperation((current) => ({ ...current, status: "completed", stage: "completed", title: "Obsidian синхронизирован", message: `Добавлено: ${result.added}; без изменений или заблокировано: ${result.skipped}` }));
    } catch (error) {
      fail(id, "Синхронизация Obsidian остановлена", error);
    } finally {
      obsidianSyncInFlight.current = false;
    }
  }, [begin, demo, edits, fail, obsidianCheck.status]);

  const enrichmentQueue = React.useMemo(() => enrichmentCounts(entries), [entries]);
  const enrichInFlightRef = React.useRef(false);

  const enrichWords = React.useCallback(async (options: { ids?: string[]; retryFailed?: boolean } = {}) => {
    if (enrichInFlightRef.current || operationRef.current.status === "running" || edits.isWriting()) return;
    enrichInFlightRef.current = true;
    const id = begin("enrich", "Перевод по контексту", "Отправляем слова провайдеру ИИ");
    try {
      const version = edits.getVersion();
      const result = await callBackend<EnrichResult>("enrich_lexemes", { job_id: id, ids: options.ids, retry_failed: options.retryFailed ?? false });
      if (!edits.acceptsVersion(version) || demoRef.current) return;
      setEntries(result.entries);
      setQueueStatus(result.queue_status ?? emptyQueue);
      setOperation((current) => ({
        ...current,
        status: result.error ? "error" : "completed",
        stage: "completed",
        title: result.error ? "Перевод остановлен" : "Перевод готов",
        message: result.message,
        error: result.error,
      }));
    } catch (error) {
      fail(id, "Перевод остановлен", error);
    } finally {
      enrichInFlightRef.current = false;
    }
  }, [begin, edits, fail]);

  React.useEffect(() => {
    if (!shouldAutoEnrich({
      enabled: settings.llm_enabled,
      auto: settings.llm_auto_enrich,
      loading: loading || demo,
      inFlight: enrichInFlightRef.current,
      pending: enrichmentQueue.pending,
      processingPending: queueStatus.pending,
      operation,
    })) return;
    void enrichWords();
  }, [demo, enrichWords, enrichmentQueue.pending, loading, operation, queueStatus.pending, settings.llm_auto_enrich, settings.llm_enabled]);

  const cancel = React.useCallback(async () => {
    const current = operationRef.current;
    if (!current.id || current.status !== "running") return;
    await cancelBackend(current.id);
    setOperation((value) => ({ ...value, status: "cancelled", title: "Операция отменена", message: "Дочерний процесс остановлен", stage: "cancelled" }));
  }, []);

  const retry = React.useCallback(() => {
    const kind = operationRef.current.kind;
    if (kind === "kindle") return void syncKindle();
    if (kind === "covers") return void downloadCovers();
    if (kind === "processing") return void retryFailed();
    if (kind === "enrich") return void enrichWords({ retryFailed: true });
  }, [downloadCovers, enrichWords, retryFailed, syncKindle]);

  const dismissOperation = React.useCallback(() => setOperation(idleOperation), []);

  return React.useMemo(
    () => ({
      entries,
      books,
      coverSummary,
      coversBusy,
      downloadCovers,
      connectors,
      settings,
      saveSettings,
      settingsSaving,
      obsidianCheck,
      checkObsidian,
      query,
      setQuery,
      selectedBookKey,
      setSelectedBookKey,
      quickFilter,
      setQuickFilter,
      selectedId,
      setSelectedId,
      visibleEntries,
      selectedEntry,
      operation,
      queueStatus,
      loading,
      ranking,
      demo,
      loadDemo,
      exitDemo,
      syncKindle,
      findReader,
      findingReader,
      importReaderFile,
      syncObsidian,
      cancel,
      retry,
      retryFailed,
      enrichmentQueue,
      enrichWords,
      dismissOperation,
      loadLibrary,
      saveCardEdit,
      setWordDecision,
    }),
    [
      saveCardEdit,
      setWordDecision,
      entries,
      books,
      coverSummary,
      coversBusy,
      downloadCovers,
      connectors,
      settings,
      saveSettings,
      settingsSaving,
      obsidianCheck,
      checkObsidian,
      query,
      setQuery,
      selectedBookKey,
      setSelectedBookKey,
      quickFilter,
      setQuickFilter,
      selectedId,
      setSelectedId,
      visibleEntries,
      selectedEntry,
      operation,
      queueStatus,
      loading,
      ranking,
      demo,
      loadDemo,
      exitDemo,
      syncKindle,
      findReader,
      findingReader,
      importReaderFile,
      syncObsidian,
      cancel,
      retry,
      retryFailed,
      enrichmentQueue,
      enrichWords,
      dismissOperation,
      loadLibrary,
    ],
  );
}

const MAX_IMPORT_BYTES = 300 * 1024 * 1024;

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).replace(/^data:[^,]*,/, ""));
    reader.onerror = () => reject(reader.error ?? new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}
