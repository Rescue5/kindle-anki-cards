// What the home screen says and when. Pure helpers, tested without a browser: the short list, its
// one-line reasons, the "order is rough" line and the export state machine. The screen only draws them.
import { ERROR_TEXTS, type ErrorCode, type ExportRun, type LexemeRecord, type LibraryRanking, type LibraryResult, type Operation, type QueueStatus, type RankingReason, type StudyPrioritySource } from "@/types";
import { partOfSpeechShort, ruCount } from "@/features/reading/reading-domain";
import { russianMeaning } from "@/features/library/domain";
import { isRpV2Priority, studyPriorityComparator, studyPriority } from "@/features/library/study-priority";

/** The short-list parts of a library answer, or null when the bridge does not send them (an older one). */
export function rankingOf(result: LibraryResult): LibraryRanking | null {
  const { rankingVersion, rankingMode, historyDays, repeatSignal, shelves, newBatch, disputed, again } = result as Partial<LibraryRanking>;
  if (!newBatch || !Array.isArray(newBatch.ids)) return null;
  return {
    studyPrioritySource: result.studyPrioritySource,
    rankingVersion: rankingVersion ?? "",
    rankingMode: rankingMode ?? "full",
    historyDays: historyDays ?? 0,
    repeatSignal: repeatSignal ?? true,
    shelves: shelves ?? { worth: 0, disputed: 0, not_worth: 0, junk: 0, known: 0 },
    newBatch,
    disputed: disputed ?? { ids: [] },
    again: again ?? { count: 0, ids: [], unavailable: true },
  };
}

/** «1 слово», «2 слова», «5 слов». */
export function wordsLabel(count: number): string {
  return `${count} ${ruCount(count, "слово", "слова", "слов")}`;
}

/** Number of selected words, including those beyond the preview. */
export function exportButtonLabel(count: number): string {
  return `Выгрузить ${wordsLabel(count)}`;
}

export const PRIORITY_LEVELS = Array.from({ length: 10 }, (_, index) => index + 1);
export type ExportSelection = "library" | "new" | "portion";

export function exportQuantity(limit: string, available: number): number {
  const value = Number(limit);
  return /^\d+$/.test(limit) && Number.isSafeInteger(value) && value > 0 ? Math.min(value, available) : 0;
}

export function libraryExportOrder(entries: readonly LexemeRecord[], source?: StudyPrioritySource) {
  return [...entries].sort(studyPriorityComparator(source)).map((entry) => ({ id: entry.id, level: studyPriority(entry).level }));
}


/** «С прошлого раза: 3 новых слова»; null when nothing is new or the list already says that many. */
export function sinceLastTimeLine(entries: readonly LexemeRecord[], listCount = -1): string | null {
  const fresh = entries.filter((entry) => entry.is_new).length;
  if (fresh <= 0 || fresh === listCount) return null;
  return `С прошлого раза: ${fresh} ${ruCount(fresh, "новое слово", "новых слова", "новых слов")}`;
}

/** The short list in the order the ranking gave it; ids the library no longer holds are skipped. */
export function shortList(entries: readonly LexemeRecord[], ids: readonly string[]): LexemeRecord[] {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  return ids.flatMap((id) => {
    const entry = byId.get(id);
    return entry ? [entry] : [];
  });
}

/**
 * The single reason shown beside a word: the strongest one speaking for learning it. A decision of the
 * reader (weight 0) counts when nothing stronger exists; reasons against the word are never shown here.
 */
export function pickReason(reasons: readonly RankingReason[] | undefined): string {
  let best: RankingReason | undefined;
  for (const reason of reasons ?? []) {
    if (reason.weight < 0 || !reason.text.trim()) continue;
    if (!best || reason.weight > best.weight) best = reason;
  }
  return best?.text.trim() ?? "";
}

/** The Russian meaning for the list: the card's own (edited, LLM or dictionary), else what the library knows. */
export function listMeaning(entry: LexemeRecord): string {
  return entry.card?.meaning_ru?.trim() || russianMeaning(entry)?.text.trim() || "";
}

export function listPartOfSpeech(entry: LexemeRecord): string {
  return partOfSpeechShort(entry.processing.analysis?.pos ?? entry.dictionary?.pos);
}

export const DEMO_NOTE = "Пример: слова выдуманные — ничего не сохраняется";
const LEARNING_NOTE = "Порядок пока примерный: в библиотеке ещё мало истории чтения.";
const NO_REPEATS_NOTE = "Порядок примерный: читалка не сохраняет повторные поиски, поэтому слова идут в основном по частоте";

/** One grey line when the order is still rough; null when the ranking has what it needs. */
export function rankingNote(ranking: Pick<LibraryRanking, "rankingMode" | "repeatSignal" | "studyPrioritySource"> | null): string | null {
  if (!ranking || isRpV2Priority(ranking.studyPrioritySource)) return null;
  if (!ranking.repeatSignal) return NO_REPEATS_NOTE;
  return ranking.rankingMode === "learning" ? LEARNING_NOTE : null;
}

// ---- the first screen of a reader without words ----

/** Where each reader keeps its words (README wording); shown while there is no library. */
export const READER_LOCATIONS: readonly { reader: string; where: string }[] = [
  { reader: "Kindle", where: "system/vocabulary/vocab.db" },
  { reader: "KOReader (PocketBook, Kobo, Boox)", where: "vocabulary_builder.sqlite3 в папке настроек KOReader" },
  { reader: "Kobo со своим словарём", where: ".kobo/KoboReader.sqlite" },
];

/** Which body the screen shows. `loading` lasts until the first library answer, so no onboarding flashes by. */
export type HomeMode = "loading" | "no-reader" | "list" | "preparing" | "processing-stopped" | "empty";
export type HomeQueueState = "idle" | "working" | "stopped";
export type HomeProcessingProgress =
  | { phase: "waiting" }
  | { phase: "processing"; current: number; total: number }
  | { phase: "finishing" };

/** The bridge counts this processing run, which can be smaller than the library after a retry. */
export function homeProcessingProgress(operation: Pick<Operation, "kind" | "status" | "stage" | "current" | "total">): HomeProcessingProgress {
  const { kind, status, stage, current, total } = operation;
  if (kind === "processing" && status === "running") {
    // The bridge has finished, but the refreshed ranking is still being read.
    if (stage === "completed") return { phase: "finishing" };
    if ((stage === "preparing" || stage === "processing") && total > 0 && current >= 0 && current <= total) {
      return { phase: "processing", current, total };
    }
  }
  return { phase: "waiting" };
}

export function homeQueueState(queue: QueueStatus, operation: Pick<Operation, "status" | "kind">): HomeQueueState {
  if (operation.kind === "processing") {
    if (operation.status === "running") return "working";
    if (operation.status === "error" || operation.status === "cancelled") return "stopped";
  }
  if (queue.pending > 0 || queue.processing > 0) return "working";
  return queue.failed > 0 ? "stopped" : "idle";
}

export function homeMode(input: { loading: boolean; entryCount: number; batchCount: number; demo: boolean; queue: HomeQueueState }): HomeMode {
  if (input.loading) return "loading";
  if (input.entryCount === 0 && !input.demo) return "no-reader";
  if (input.batchCount > 0) return "list";
  if (!input.demo && input.queue === "working") return "preparing";
  if (!input.demo && input.queue === "stopped") return "processing-stopped";
  return "empty";
}

// ---- export states ----

export type ExportUi =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; run: ExportRun }
  | { kind: "empty" }
  | { kind: "error"; message: string; code?: ErrorCode };

export type ExportEvent =
  | { type: "start" }
  | { type: "success"; run: ExportRun }
  | { type: "failure"; message: string; code?: ErrorCode }
  | { type: "dismiss" };

export const idleExport: ExportUi = { kind: "idle" };

export function exportReducer(state: ExportUi, event: ExportEvent): ExportUi {
  switch (event.type) {
    case "start":
      return state.kind === "running" ? state : { kind: "running" };
    case "success":
      if (state.kind !== "running") return state;
      return event.run.exported > 0 ? { kind: "done", run: event.run } : { kind: "empty" };
    case "failure":
      if (state.kind !== "running") return state;
      return event.code === "nothing_to_export" ? { kind: "empty" } : { kind: "error", message: event.message, ...(event.code ? { code: event.code } : {}) };
    case "dismiss":
      return state.kind === "running" ? state : idleExport;
  }
}

/** «Готово: 5 слов в Anki» for a push, «… в файле» when a file was written. */
export function exportDoneText(run: ExportRun): string {
  const words = wordsLabel(run.exported);
  if (run.path) return `Готово: ${words} в файле`;
  if (run.destination === "obsidian") return `Готово: ${words} в Obsidian`;
  return `Готово: ${words} в Anki`;
}

/** A line under «Готово» only when the reader still has a step to take: an Anki file waits to be opened. */
export function exportDoneHint(run: ExportRun): string {
  return run.path && run.destination === "anki" ? "Откройте колоду и подтвердите импорт в Anki" : "";
}

/** «Не получилось: <причина>.» — the reason without the bridge's generic prefix, as one sentence. */
export function exportErrorText(message: string, code?: ErrorCode): string {
  if (code === "anki_import_unconfirmed") {
    return "Anki не подтвердил импорт. Колода сохранена в папке выгрузок. Проверьте, появились ли слова в Anki, прежде чем отправлять их снова.";
  }
  if (code === "anki_import_rejected" || code === "export_busy") return ERROR_TEXTS[code];
  let reason = message.trim();
  const generic = `${ERROR_TEXTS.export_failed}:`;
  if (reason.startsWith(generic)) reason = reason.slice(generic.length).trim();
  reason = reason.replace(/[.\s]+$/, "");
  if (!reason || reason === ERROR_TEXTS.export_failed) reason = "экспорт не завершился";
  // Lower-case the first letter of a sentence, but keep acronyms and names («Anki», «AnkiConnect») as they are.
  if (/^[А-ЯЁ][а-яё]/.test(reason)) reason = reason[0].toLowerCase() + reason.slice(1);
  return `Не получилось: ${reason}.`;
}

export const EMPTY_TITLE = "Новых слов для выгрузки нет.";
export const EMPTY_NOTE = "Подключите читалку, когда прочтёте ещё что-нибудь";
export const LOAD_FROM_READER = "Загрузить слова с читалки";
export const SEARCHING_READER = "Ищу читалку…";
export const READER_NOT_FOUND = "Читалка не найдена";
export const LIST_TITLE = "Слова в выгрузке";
export const BUSY_NOTE = "Разбираю новые слова — список может измениться";

// ---- the one line under the button ----

export type DeskStatus =
  | Extract<ExportUi, { kind: "error" }>
  | { kind: "done"; run: ExportRun }
  | { kind: "note"; text: string };

/** One status line, by priority: error, then what the last export did, then busy, then demo, then «order is rough». */
export function deskStatus(input: { exportUi: ExportUi; listChanging: boolean; demo: boolean; roughNote: string | null }): DeskStatus | null {
  const { exportUi, listChanging, demo, roughNote } = input;
  if (exportUi.kind === "error") return exportUi;
  if (exportUi.kind === "done") return { kind: "done", run: exportUi.run };
  if (listChanging) return { kind: "note", text: BUSY_NOTE };
  if (demo) return { kind: "note", text: DEMO_NOTE };
  return roughNote ? { kind: "note", text: roughNote } : null;
}
