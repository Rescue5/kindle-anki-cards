import { beforeEach, describe, expect, it } from "vitest";
import { callBackend } from "@/lib/backend";
import { resetMockBackend } from "@/lib/mock-backend";
import { previewPriorityReason, studyPriority } from "@/features/library/study-priority";
import type { ExportRun, LexemeRecord, LibraryResult, LibraryResultV4, RankingReason } from "@/types";
import {
  BUSY_NOTE,
  DEMO_NOTE,
  deskStatus,
  exportButtonLabel,
  exportQuantity,
  exportDoneHint,
  exportDoneText,
  exportErrorText,
  exportReducer,
  homeMode,
  homeProcessingProgress,
  homeQueueState,
  idleExport,
  libraryExportOrder,
  listMeaning,
  pickReason,
  rankingNote,
  rankingOf,
  shortList,
  sinceLastTimeLine,
  wordsLabel,
  type ExportUi,
} from "./home-domain";

const reason = (code: RankingReason["code"], text: string, weight: number): RankingReason => ({ code, text, weight });

it("keeps full export order global in coverage mode and batches only eligible new words", async () => {
  resetMockBackend({ scenario: "coverage", instant: true });
  const initial = await callBackend<LibraryResultV4>("load_library", {});
  expect(rankingOf(initial)?.studyPrioritySource).toBe("rp-v2-coverage");
  const initialOrder = libraryExportOrder(initial.entries, initial.studyPrioritySource).map(({ id }) => id);
  expect(initialOrder.indexOf("lexeme-vigilant")).toBeLessThan(initialOrder.indexOf("lexeme-ephemeral"));
  expect(initialOrder.at(-1)).toBe("lexeme-00:17");
  const legacyOrder = libraryExportOrder(initial.entries, "legacy").map(({ id }) => id);
  expect(legacyOrder.indexOf("lexeme-ephemeral")).toBeLessThan(legacyOrder.indexOf("lexeme-vigilant"));
  expect(rankingNote({ rankingMode: "learning", repeatSignal: false, studyPrioritySource: initial.studyPrioritySource })).toBeNull();

  await callBackend("process_queue", {});
  const ready = await callBackend<LibraryResultV4>("load_library", {});
  expect(ready.newBatch.availableIds).toEqual(["lexeme-dread", "lexeme-glimpse", "lexeme-submerge", "lexeme-resilient", "lexeme-ephemeral"]);
});

it("uses the personal bridge scores for export order and keeps the adjustment in the preview", async () => {
  resetMockBackend({ scenario: "personal", instant: true });
  const result = await callBackend<LibraryResultV4>("load_library", {});
  expect(rankingOf(result)?.studyPrioritySource).toBe("rp-v2-personal");
  const order = libraryExportOrder(result.entries, result.studyPrioritySource).map(({ id }) => id);
  expect(order.indexOf("lexeme-vigilant")).toBeLessThan(order.indexOf("lexeme-ephemeral"));
  expect(order.indexOf("lexeme-ephemeral")).toBeLessThan(order.indexOf("lexeme-glimpse"));
  expect(order.at(-1)).toBe("lexeme-00:17");
  const admit = result.entries.find(({ lemma }) => lemma === "admit")!;
  expect(admit.study_priority).toMatchObject({ score: .4545, coverage_score: .4 });
  expect(previewPriorityReason(studyPriority(admit)))
    .toBe("Вы искали это слово в разные дни в одной книге.");
  expect(rankingNote({ rankingMode: "learning", repeatSignal: false, studyPrioritySource: result.studyPrioritySource })).toBeNull();

  await callBackend("process_queue", {});
  const ready = await callBackend<LibraryResultV4>("load_library", {});
  const dread = ready.entries.find(({ lemma }) => lemma === "dread")!;
  expect(new Set(dread.occurrences.map(({ book_key }) => book_key)).size).toBe(3);
  expect(dread.study_priority).toMatchObject({ level: 1, score: .75, coverage_score: .60, provisional: false });
  expect(previewPriorityReason(studyPriority(dread))).toBe("Вы искали это слово в разных книгах.");
  expect(ready.newBatch.availableIds?.[0]).toBe(dread.id);

  resetMockBackend({ scenario: "coverage", instant: true });
  await callBackend("process_queue", {});
  const coverage = await callBackend<LibraryResultV4>("load_library", {});
  const coveragePriority = studyPriority(coverage.entries.find(({ id }) => id === dread.id)!);
  expect(coveragePriority)
    .toMatchObject({ level: 2, score: dread.study_priority?.coverage_score, provisional: false });
  expect(previewPriorityReason(coveragePriority)).toBe(coveragePriority.reason);
});

it("allows a custom portion above 100 and clamps it to the available words", () => {
  expect(exportQuantity("101", 123)).toBe(101);
  expect(exportQuantity("800", 123)).toBe(123);
  for (const invalid of ["", "0", "-1", "1.5"]) expect(exportQuantity(invalid, 123)).toBe(0);
});
const run = (patch: Partial<ExportRun> = {}): ExportRun => ({ destination: "anki", runId: "run-1", exported: 5, path: null, pushed: 5, message: "", ...patch });

describe("progress of the active word queue", () => {
  const active = { kind: "processing", status: "running", stage: "processing", current: 649, total: 1820 } as const;

  it("uses this run's counts and starts a retry at its own zero", () => {
    expect(homeProcessingProgress(active)).toEqual({ phase: "processing", current: 649, total: 1820 });
    expect(homeProcessingProgress({ ...active, stage: "preparing", current: 0, total: 3 })).toEqual({ phase: "processing", current: 0, total: 3 });
  });

  it("does not turn import steps, old jobs or unknown totals into word counts", () => {
    for (const operation of [{ ...active, kind: "kindle" as const }, { ...active, status: "completed" as const },
      { ...active, stage: "starting" }, { ...active, current: 0, total: 0 }, { ...active, current: 4, total: 3 }]) {
      expect(homeProcessingProgress(operation)).toEqual({ phase: "waiting" });
    }
  });

  it("distinguishes ranking refresh from a new zero-length run", () => {
    expect(homeProcessingProgress({ ...active, stage: "completed" })).toEqual({ phase: "finishing" });
  });
});

describe("words and counts", () => {
  it("declines «слово» by the number", () => {
    expect(wordsLabel(1)).toBe("1 слово");
    expect(wordsLabel(2)).toBe("2 слова");
    expect(wordsLabel(5)).toBe("5 слов");
    expect(wordsLabel(11)).toBe("11 слов");
    expect(wordsLabel(21)).toBe("21 слово");
    expect(wordsLabel(24)).toBe("24 слова");
  });

  it("writes the primary action with the size of the short list", () => {
    expect(exportButtonLabel(15)).toBe("Выгрузить 15 слов");
  });

  it("counts the new words and stays silent at zero", () => {
    const word = (id: string, is_new: boolean) => ({ id, is_new }) as LexemeRecord;
    expect(sinceLastTimeLine([word("a", true), word("b", false), word("c", true)])).toBe("С прошлого раза: 2 новых слова");
    expect(sinceLastTimeLine([word("a", true)])).toBe("С прошлого раза: 1 новое слово");
    expect(sinceLastTimeLine(Array.from({ length: 5 }, (_, i) => word(String(i), true)))).toBe("С прошлого раза: 5 новых слов");
    expect(sinceLastTimeLine([word("a", false)])).toBeNull();
    expect(sinceLastTimeLine([])).toBeNull();
  });

  it("stays silent when it would only repeat the size of the list", () => {
    const word = (id: string) => ({ id, is_new: true }) as LexemeRecord;
    expect(sinceLastTimeLine([word("a"), word("b")], 2)).toBeNull();
    expect(sinceLastTimeLine([word("a"), word("b")], 5)).toBe("С прошлого раза: 2 новых слова");
  });
});

describe("the short list", () => {
  it("keeps the ranking order and skips ids the library does not hold", () => {
    const entries = ["a", "b", "c"].map((id) => ({ id }) as LexemeRecord);
    expect(shortList(entries, ["c", "gone", "a"]).map((entry) => entry.id)).toEqual(["c", "a"]);
    expect(shortList(entries, [])).toEqual([]);
  });

  it("shows the strongest reason for learning the word", () => {
    expect(pickReason([reason("frequency", "Не слишком частое слово", 0.3), reason("repeat_lookups", "Искали 2 раза", 0.75), reason("recency", "Искали недавно", 0.4)])).toBe("Искали 2 раза");
  });

  it("never shows a reason against the word", () => {
    expect(pickReason([reason("thin_evidence", "Искали один раз, данных мало", -0.2)])).toBe("");
    expect(pickReason([reason("thin_evidence", "Искали один раз", -0.2), reason("frequency", "Не слишком частое слово", 0.1)])).toBe("Не слишком частое слово");
    expect(pickReason(undefined)).toBe("");
  });

  it("lets the reader's own decision stand when nothing stronger exists", () => {
    expect(pickReason([reason("decision_learn", "Вы решили учить", 0)])).toBe("Вы решили учить");
  });

  it("prefers the card's meaning, then what the library knows", () => {
    const base = { processing: { state: "ready", analysis: null, updated_at: "", error: "" } } as unknown as LexemeRecord;
    expect(listMeaning({ ...base, card: { meaning_ru: " страх ", meaning_source: "edited", example_occurrence_id: "", edited: true } })).toBe("страх");
    expect(listMeaning({ ...base, dictionary: { meaning_ru: "проблеск", pos: "n", source: "wiktionary" } })).toBe("проблеск");
    expect(listMeaning(base)).toBe("");
  });
});

describe("the grey line about the order", () => {
  it("says nothing when the ranking has what it needs", () => {
    expect(rankingNote({ rankingMode: "full", repeatSignal: true })).toBeNull();
    expect(rankingNote(null)).toBeNull();
  });

  it("says the order is rough while history is short", () => {
    expect(rankingNote({ rankingMode: "learning", repeatSignal: true })).toBe("Порядок пока примерный: в библиотеке ещё мало истории чтения.");
  });

  it("says why when the reader keeps no repeat lookups, whatever the mode", () => {
    const line = "Порядок примерный: читалка не сохраняет повторные поиски, поэтому слова идут в основном по частоте";
    expect(rankingNote({ rankingMode: "learning", repeatSignal: false })).toBe(line);
    expect(rankingNote({ rankingMode: "full", repeatSignal: false })).toBe(line);
  });
});

describe("which body the screen shows", () => {
  const base = { loading: false, entryCount: 0, batchCount: 0, demo: false, queue: "idle" } as const;
  it("waits for the first answer before it decides anything", () => {
    expect(homeMode({ ...base, loading: true })).toBe("loading");
    expect(homeMode({ ...base, loading: true, entryCount: 40, batchCount: 15 })).toBe("loading");
  });

  it("shows the reader path only without words, and not during the demo", () => {
    expect(homeMode(base)).toBe("no-reader");
    expect(homeMode({ ...base, entryCount: 12, batchCount: 5, demo: true })).toBe("list");
  });

  it("shows the list while there is a batch and the empty answer when there is none", () => {
    expect(homeMode({ ...base, entryCount: 40, batchCount: 15 })).toBe("list");
    expect(homeMode({ ...base, entryCount: 40 })).toBe("empty");
  });

  it("waits with queued words, leaves waiting on a failure, and ignores the queue in demo", () => {
    const queue = { pending: 2, processing: 0, failed: 0, total: 2 };
    const imported = { ...base, entryCount: 2 };
    const working = homeQueueState(queue, { kind: "kindle", status: "completed" });
    expect(homeMode({ ...imported, queue: working })).toBe("preparing");
    expect(homeMode({ ...imported, queue: working, demo: true })).toBe("empty");
    const stopped = homeQueueState(queue, { kind: "processing", status: "error" });
    expect(homeMode({ ...imported, queue: stopped })).toBe("processing-stopped");
  });
});

describe("export states", () => {
  const start = exportReducer(idleExport, { type: "start" });

  it("goes idle -> running -> done", () => {
    expect(start).toEqual({ kind: "running" });
    expect(exportReducer(start, { type: "success", run: run() })).toEqual({ kind: "done", run: run() });
  });

  it("ignores a second start while running", () => {
    expect(exportReducer(start, { type: "start" })).toBe(start);
  });

  it("treats a run of zero words as the empty state", () => {
    expect(exportReducer(start, { type: "success", run: run({ exported: 0 }) })).toEqual({ kind: "empty" });
  });

  it("treats nothing_to_export as empty and any other failure as an error that keeps the reason", () => {
    expect(exportReducer(start, { type: "failure", code: "nothing_to_export", message: "Нет слов для экспорта" })).toEqual({ kind: "empty" });
    expect(exportReducer(start, { type: "failure", code: "export_failed", message: "диск полон" })).toEqual({ kind: "error", code: "export_failed", message: "диск полон" });
    expect(exportReducer(start, { type: "failure", message: "нет связи" })).toEqual({ kind: "error", message: "нет связи" });
  });

  it("retries from an error and clears a stale «Готово», but never interrupts a running export", () => {
    const failed: ExportUi = { kind: "error", message: "x" };
    expect(exportReducer(failed, { type: "start" })).toEqual({ kind: "running" });
    expect(exportReducer({ kind: "done", run: run() }, { type: "dismiss" })).toEqual(idleExport);
    expect(exportReducer(start, { type: "dismiss" })).toBe(start);
    expect(exportReducer(idleExport, { type: "success", run: run() })).toBe(idleExport);
  });

  it("shows one status line by priority: error, done, busy, demo, rough order", () => {
    const base = { exportUi: idleExport, listChanging: false, demo: false, roughNote: "rough" };
    const done = { kind: "done", run: run() } as const;
    expect(deskStatus(base)).toEqual({ kind: "note", text: "rough" });
    expect(deskStatus({ ...base, demo: true })).toEqual({ kind: "note", text: DEMO_NOTE });
    expect(deskStatus({ ...base, demo: true, listChanging: true })).toEqual({ kind: "note", text: BUSY_NOTE });
    expect(deskStatus({ ...base, listChanging: true, exportUi: done })).toEqual({ kind: "done", run: run() });
    expect(deskStatus({ ...base, listChanging: true, exportUi: { kind: "error", message: "x" } })).toEqual({ kind: "error", message: "x" });
    expect(deskStatus({ ...base, roughNote: null })).toBeNull();
  });

  it("writes where the words went", () => {
    expect(exportDoneText(run({ exported: 5 }))).toBe("Готово: 5 слов в Anki");
    expect(exportDoneText(run({ exported: 1, pushed: 0, path: "preview/Kindle Cards.apkg" }))).toBe("Готово: 1 слово в файле");
    expect(exportDoneText(run({ destination: "csv", exported: 3, pushed: 0, path: "x.csv" }))).toBe("Готово: 3 слова в файле");
    expect(exportDoneText(run({ destination: "obsidian", exported: 2, pushed: 0 }))).toBe("Готово: 2 слова в Obsidian");
  });

  it("adds a hint only when an Anki file waits to be opened", () => {
    expect(exportDoneHint(run())).toBe("");
    expect(exportDoneHint(run({ path: "a.apkg", pushed: 0 }))).not.toBe("");
    expect(exportDoneHint(run({ destination: "csv", path: "a.csv", pushed: 0 }))).toBe("");
  });

  it("states the reason as one sentence without the bridge's generic prefix", () => {
    expect(exportErrorText("Не удалось выполнить экспорт: не удалось записать файл")).toBe("Не получилось: не удалось записать файл.");
    expect(exportErrorText("Нет связи с AnkiConnect.")).toBe("Не получилось: нет связи с AnkiConnect.");
    expect(exportErrorText("AnkiConnect не отвечает")).toBe("Не получилось: AnkiConnect не отвечает.");
    expect(exportErrorText("Не удалось выполнить экспорт")).toBe("Не получилось: экспорт не завершился.");
  });
});

describe("the short-list parts of a library answer", () => {
  beforeEach(() => resetMockBackend({ scenario: "mixed", instant: true }));

  it("is read from the mock and drives the list", async () => {
    const library = await callBackend<LibraryResultV4>("load_library", {});
    const ranking = rankingOf(library);
    expect(ranking?.newBatch.ids).toEqual(library.newBatch.ids);
    const words = shortList(library.entries, ranking!.newBatch.ids);
    expect(words.map((word) => word.id)).toEqual(library.newBatch.ids);
    for (const word of words) expect(pickReason(word.ranking?.reasons)).not.toBe("");
  });

  it("is null for an older bridge that sends none", () => {
    expect(rankingOf({ entries: [] } as unknown as LibraryResult)).toBeNull();
  });

  it("covers learning mode, a reader without repeat lookups and an empty library", async () => {
    resetMockBackend({ scenario: "learning", instant: true });
    expect(rankingNote(rankingOf(await callBackend<LibraryResultV4>("load_library", {})))).toMatch(/^Порядок пока примерный/);
    resetMockBackend({ scenario: "no-repeats", instant: true });
    const noRepeats = await callBackend<LibraryResultV4>("load_library", {});
    expect(rankingNote(rankingOf(noRepeats))).toMatch(/не сохраняет повторные поиски/);
    for (const word of noRepeats.entries) for (const r of word.ranking?.reasons ?? []) expect(["repeat_lookups", "after_export", "several_books"]).not.toContain(r.code);
    resetMockBackend({ scenario: "empty", instant: true });
    expect((await callBackend<LibraryResultV4>("load_library", {})).entries).toEqual([]);
    expect((await callBackend<LibraryResultV4>("load_demo", {})).entries.length).toBeGreaterThan(0);
  });

  it("exports the new batch and lets the list move on", async () => {
    const before = await callBackend<LibraryResultV4>("load_library", {});
    const result = await callBackend<ExportRun>("export_words", { job_id: "j", scope: "new", ids: before.newBatch.ids });
    expect(result.exported).toBe(before.newBatch.count);
    expect((await callBackend<LibraryResultV4>("load_library", {})).newBatch.count).toBe(0);
  });
});
