import { beforeEach, describe, expect, it, vi } from "vitest";
import * as backend from "@/lib/backend";
import { mockBackend, resetMockBackend } from "@/lib/mock-backend";
import type { LibraryResultV4, SaveCardEditResult, SetDecisionResult } from "@/types";
import { LibraryEdits } from "./library-edits";

const load = () => mockBackend<LibraryResultV4>("load_library", {});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("library edits and snapshot versions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    resetMockBackend({ scenario: "mixed", instant: true });
    vi.spyOn(backend, "callBackend").mockImplementation(mockBackend);
  });

  async function harness() {
    let library = await load();
    let enabled = true;
    const apply = vi.fn((next) => { library = next; });
    const applyEntry = vi.fn((result: SaveCardEditResult | SetDecisionResult) => {
      library.entries = library.entries.map((entry) => entry.id === result.entry.id ? result.entry : entry);
    });
    const writes = new LibraryEdits((id) => enabled && library.entries.some((entry) => entry.id === id), apply, applyEntry);
    return { writes, apply, applyEntry, current: () => library, disable: () => { enabled = false; } };
  }

  it("saves translation and example through the real payload, then reloads all ranks", async () => {
    const h = await harness();
    const id = "lexeme-ephemeral";
    const example = h.current().entries.find((entry) => entry.id === id)!.occurrences[0].id;
    await h.writes.saveCardEdit(id, { meaning_ru: "  мимолётный\n свет ", example_occurrence_id: example });
    expect(backend.callBackend).toHaveBeenCalledWith("save_card_edit", {
      lexeme_id: id, meaning_ru: "  мимолётный\n свет ", example_occurrence_id: example,
    });
    expect(h.current().entries.find((entry) => entry.id === id)!.card).toMatchObject({
      meaning_ru: "мимолётный свет", example_occurrence_id: example, edited: true,
    });
    expect((await load()).entries.find((entry) => entry.id === id)!.card).toEqual(
      h.current().entries.find((entry) => entry.id === id)!.card,
    );
    expect(h.apply).toHaveBeenCalledOnce();
  });

  it("replaces a skipped batch word and restores it on clearing with consistent shelf ranks", async () => {
    await mockBackend("process_queue", {});
    await mockBackend("set_decision", { lexeme_id: "lexeme-wistful", decision: "learn" });
    await mockBackend("save_settings", { settings: { export_batch_size: 5 } });
    const h = await harness();
    const before = h.current();
    const id = before.newBatch.ids[0];
    await h.writes.setWordDecision(id, "skip");
    expect(h.current().newBatch.ids).not.toContain(id);
    expect(h.current().newBatch.count).toBe(5);
    expect(h.current().shelves.not_worth).toBe(before.shelves.not_worth + 1);
    expect(h.current().entries.find((entry) => entry.id === id)!.decision?.value).toBe("skip");
    await h.writes.setWordDecision(id, null);
    expect(h.current().newBatch).toEqual(before.newBatch);
    expect(h.current().shelves).toEqual(before.shelves);
    expect(h.current().entries).toEqual((await load()).entries);
  });

  it("rejects loading/demo/unknown IDs before sending any write", async () => {
    const h = await harness();
    await expect(h.writes.saveCardEdit("demo-only", { meaning_ru: "пример" })).rejects.toThrow("Дождитесь");
    h.disable();
    await expect(h.writes.setWordDecision("lexeme-ephemeral", "skip")).rejects.toThrow("Дождитесь");
    expect(backend.callBackend).not.toHaveBeenCalled();
  });

  it("invalidates loads and Obsidian evidence from before and during a write", async () => {
    const h = await harness();
    const old = h.writes.beginRead();
    const reply = deferred<SaveCardEditResult>();
    vi.mocked(backend.callBackend).mockImplementationOnce(() => reply.promise as never);
    const saved = h.writes.saveCardEdit("lexeme-ephemeral", { meaning_ru: "свет" });
    expect(h.writes.accepts(old)).toBe(false);
    await Promise.resolve();
    const during = h.writes.beginRead();
    const evidenceVersion = h.writes.getVersion();
    expect(h.writes.accepts(during)).toBe(false);
    expect(h.writes.acceptsVersion(evidenceVersion)).toBe(false);
    reply.resolve(await mockBackend("save_card_edit", { lexeme_id: "lexeme-ephemeral", meaning_ru: "свет" }));
    await saved;
    expect(h.writes.accepts(during)).toBe(false);
    expect(h.writes.acceptsVersion(evidenceVersion)).toBe(false);
    expect(h.current().entries.find((entry) => entry.id === "lexeme-ephemeral")!.card.meaning_ru).toBe("свет");
  });

  it("does not apply an in-flight live write to another library or send queued demo writes", async () => {
    const h = await harness();
    const reply = deferred<SaveCardEditResult>();
    vi.mocked(backend.callBackend).mockImplementationOnce(() => reply.promise as never);
    const first = h.writes.saveCardEdit("lexeme-ephemeral", { meaning_ru: "свет" });
    const second = h.writes.setWordDecision("lexeme-ephemeral", "skip");
    const rejected = expect(second).rejects.toThrow("Библиотека изменилась");
    await Promise.resolve();
    h.writes.switchLibrary();
    h.disable();
    reply.resolve(await mockBackend("save_card_edit", { lexeme_id: "lexeme-ephemeral", meaning_ru: "свет" }));
    await first;
    await rejected;
    expect(h.applyEntry).not.toHaveBeenCalled();
    expect(h.apply).not.toHaveBeenCalled();
    expect(backend.callBackend).toHaveBeenCalledTimes(1);
  });

  it("serializes partial edits and continues after a validation failure", async () => {
    const h = await harness();
    const id = "lexeme-ephemeral";
    const example = h.current().entries.find((entry) => entry.id === id)!.occurrences[0].id;
    await expect(h.writes.saveCardEdit(id, { meaning_ru: "я".repeat(201) })).rejects.toThrow("Перевод длиннее");
    await Promise.all([
      h.writes.saveCardEdit(id, { meaning_ru: "исправленный перевод" }),
      h.writes.saveCardEdit(id, { example_occurrence_id: example }),
    ]);
    expect(h.current().entries.find((entry) => entry.id === id)!.card).toMatchObject({
      meaning_ru: "исправленный перевод", example_occurrence_id: example,
    });
  });

  it("keeps the saved entry if refresh fails and reports a useful Russian error", async () => {
    const h = await harness();
    vi.mocked(backend.callBackend)
      .mockImplementationOnce(mockBackend)
      .mockRejectedValueOnce(new Error("network"));
    await expect(h.writes.saveCardEdit("lexeme-ephemeral", { meaning_ru: "свет" }))
      .rejects.toThrow("Правка сохранена");
    expect(h.current().entries.find((entry) => entry.id === "lexeme-ephemeral")!.card.meaning_ru).toBe("свет");
  });

  it("only accepts the latest full response within one version", async () => {
    const h = await harness();
    const first = h.writes.beginRead();
    const second = h.writes.beginRead();
    expect(h.writes.accepts(first)).toBe(false);
    expect(h.writes.accepts(second)).toBe(true);
  });
});
