import { beforeEach, describe, expect, it } from "vitest";
import { callBackend } from "@/lib/backend";
import {
  expectEveryCase,
  expectEveryKey,
  expectRanksAndCounts,
  expectShortList,
} from "@/lib/contract-assertions";
import { resetMockBackend } from "@/lib/mock-backend";
import {
  ERROR_TEXTS,
  type AppSettings,
  type ExportPreview,
  type ExportRun,
  type LexemeDetails,
  type LibraryResultV4,
  type SaveCardEditResult,
  type SetDecisionResult,
} from "@/types";

const load = () => callBackend<LibraryResultV4>("load_library", {});

async function expectError(promise: Promise<unknown>, code: keyof typeof ERROR_TEXTS) {
  await expect(promise).rejects.toMatchObject({ code, message: expect.stringContaining(ERROR_TEXTS[code]) });
}

describe("browser mock speaks the C0 contract", () => {
  beforeEach(() => resetMockBackend({ scenario: "mixed", instant: true }));

  it("carries every library-level and lexeme-level key, with the old fields beside them", async () => {
    const library = await load();
    expectEveryKey(library);
    expect(library.entries[0]).toHaveProperty("processing");
    expect(library.entries[0]).toHaveProperty("destinations");
    expect(library.books.length).toBeGreaterThan(1);
  });

  it("covers every shelf, a decision, an exported word that came back and an unprocessed word; a card edit adds the edited card", async () => {
    await callBackend<SaveCardEditResult>("save_card_edit", { lexeme_id: "lexeme-dread", meaning_ru: "тревога" });
    expectEveryCase(await load());
  });

  it("numbers ranks from 1 inside each shelf, keeps the shelf counts true and the short list to worth words", async () => {
    const library = await load();
    expectRanksAndCounts(library);
    expectShortList(library);
    expect(library.newBatch.count).toBeGreaterThan(0);
    expect(library.disputed.ids.length).toBeGreaterThan(0);
  });

  it("marks a library that keeps repeat lookups: full mode, an again signal", async () => {
    const library = await load();
    expect(library.rankingMode).toBe("full");
    expect(library.repeatSignal).toBe(true);
    expect(library.again).toMatchObject({ unavailable: false, ids: ["lexeme-admit"], count: 1 });
  });

  it("ranks words that get processed and keeps the contract after processing", async () => {
    const before = await load();
    expect(before.entries.filter((entry) => entry.ranking === null).length).toBeGreaterThan(0);
    await callBackend("process_queue", {});
    const after = await load();
    expect(after.entries.every((entry) => entry.ranking !== null)).toBe(true);
    expectRanksAndCounts(after);
    expectShortList(after);
  });

  it("moves a disputed word to the shelf its decision names and back", async () => {
    const before = await load();
    const id = before.disputed.ids[0];
    const learned = await callBackend<SetDecisionResult>("set_decision", { lexeme_id: id, decision: "learn" });
    expect(learned.entry.ranking?.shelf).toBe("worth");
    expect(learned.entry.decision?.value).toBe("learn");
    expect(learned.disputed.ids).not.toContain(id);
    expect(learned.newBatch.ids).toContain(id);
    expect(learned.shelves.worth).toBe(before.shelves.worth + 1);
    const undone = await callBackend<SetDecisionResult>("set_decision", { lexeme_id: id, decision: null });
    expect(undone.entry.ranking?.shelf).toBe("disputed");
    expect(undone.disputed.ids).toContain(id);
    await expectError(callBackend("set_decision", { lexeme_id: id, decision: "maybe" }), "bad_decision");
    await expectError(callBackend("set_decision", { lexeme_id: "nope", decision: "learn" }), "unknown_lexeme");
  });

  it("saves card edits, falls back when the meaning is cleared and rejects bad ones", async () => {
    const id = "lexeme-glimpse";
    const edited = await callBackend<SaveCardEditResult>("save_card_edit", { lexeme_id: id, meaning_ru: "  проблеск  " });
    expect(edited.entry.card).toMatchObject({ meaning_ru: "проблеск", meaning_source: "edited", edited: true });
    const cleared = await callBackend<SaveCardEditResult>("save_card_edit", { lexeme_id: id, meaning_ru: "" });
    expect(cleared.entry.card).toMatchObject({ meaning_source: "dictionary", edited: false });
    const details = await callBackend<LexemeDetails>("load_lexeme_details", { lexeme_id: "lexeme-ephemeral" });
    expect(details.occurrences.length).toBe(2);
    const older = details.occurrences[0].id;
    const picked = await callBackend<SaveCardEditResult>("save_card_edit", { lexeme_id: "lexeme-ephemeral", example_occurrence_id: older });
    expect(picked.entry.card).toMatchObject({ example_occurrence_id: older, edited: true });
    await expectError(callBackend("save_card_edit", { lexeme_id: id, meaning_ru: "я".repeat(201) }), "too_long");
    await expectError(callBackend("save_card_edit", { lexeme_id: id, example_occurrence_id: "kindle-0" }), "example_not_found");
    await expectError(callBackend("save_card_edit", { lexeme_id: "nope" }), "unknown_lexeme");
  });

  it("previews and runs an export, after which the words leave the short list", async () => {
    const preview = await callBackend<ExportPreview>("export_preview", {});
    const library = await load();
    expect(preview).toMatchObject({ destination: "anki", blockedReason: null });
    expect(preview.new.ids).toEqual(library.newBatch.ids);
    expect(preview.again.ids).toEqual(library.again.ids);
    const run = await callBackend<ExportRun>("export_words", { job_id: "j1", scope: "new" });
    expect(run.exported).toBe(preview.new.count);
    expect(run.runId).toBeTruthy();
    const after = await load();
    expect(after.newBatch).toEqual({ count: 0, ids: [] });
    for (const id of preview.new.ids) expect(after.entries.find((entry) => entry.id === id)?.export).toMatchObject({ state: "exported", again: false });
    await expectError(callBackend("export_words", { job_id: "j2", scope: "new" }), "nothing_to_export");
    await expectError(callBackend("export_words", { job_id: "j3", scope: "week" }), "bad_scope");
    const again = await callBackend<ExportRun>("export_words", { job_id: "j4", scope: "again" });
    expect(again.exported).toBe(1);
    expect((await load()).again.count).toBe(0);
  });

  it("uses the saved TSV destination without replacing the other settings", async () => {
    await callBackend("save_settings", { settings: { theme: "light", export_batch_size: 10 } });
    await callBackend("save_settings", { settings: { export_destination: "csv" } });
    expect(await callBackend<AppSettings>("load_settings", {})).toMatchObject({
      theme: "light",
      export_batch_size: 10,
      export_destination: "csv",
    });
    const run = await callBackend<ExportRun>("export_words", { scope: "new" });
    expect(run).toMatchObject({ destination: "csv", pushed: 0, path: expect.stringMatching(/\.tsv$/) });
  });

  it("serves the details the lean list leaves out", async () => {
    const details = await callBackend<LexemeDetails>("load_lexeme_details", { lexeme_id: "lexeme-admit" });
    expect(details).toMatchObject({ lexeme_id: "lexeme-admit" });
    expect(details.occurrences.length).toBe(2);
    expect(details.analysis?.base_form).toBe("admit");
    await expectError(callBackend("load_lexeme_details", { lexeme_id: "nope" }), "unknown_lexeme");
  });
});

describe("scenarios", () => {
  it("no-new has nothing to learn and nothing to answer, but a word that came back", async () => {
    resetMockBackend({ scenario: "no-new", instant: true });
    const library = await load();
    expectEveryKey(library);
    expectRanksAndCounts(library);
    expectShortList(library);
    expect(library.newBatch).toEqual({ count: 0, ids: [] });
    expect(library.disputed.ids).toEqual([]);
    expect(library.entries.some((entry) => entry.is_new)).toBe(false);
    expect(library.again.count).toBe(1);
    const preview = await callBackend<ExportPreview>("export_preview", {});
    expect(preview.new.count).toBe(0);
    await expectError(callBackend("export_words", { job_id: "j", scope: "new" }), "nothing_to_export");
  });

  it("export-error fails the export with a coded Russian error and exports nothing", async () => {
    resetMockBackend({ scenario: "export-error", instant: true });
    await expectError(callBackend("export_words", { job_id: "j", scope: "new" }), "export_failed");
    const library = await load();
    expect(library.newBatch.count).toBeGreaterThan(0);
  });

  it("keeps unconfirmed Anki words pending while exposing the written deck", async () => {
    resetMockBackend({ scenario: "anki-unconfirmed", instant: true });
    const before = await load();
    expect(await callBackend("export_folder_status", {})).toEqual({ available: false });
    await expectError(callBackend("export_words", { scope: "new" }), "anki_import_unconfirmed");
    expect((await load()).newBatch.ids).toEqual(before.newBatch.ids);
    expect(await callBackend("export_folder_status", {})).toEqual({ available: true });
    expect(await callBackend("open_export_folder", {})).toEqual({ opened: true });
  });
});
