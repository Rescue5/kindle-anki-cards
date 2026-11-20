import { describe, expect, it } from "vitest";
import { cardChanges, cardDraft, selectedExample, worthLearning } from "./card-editor-domain";
import { mockBackend, resetMockBackend } from "@/lib/mock-backend";
import type { LibraryResult } from "@/types";

async function exampleEntry() {
  resetMockBackend({ scenario: "mixed", instant: true });
  const library = await mockBackend<LibraryResult>("load_library", {});
  return library.entries[0];
}

describe("card editor payload", () => {
  it("sends only changed fields and supports clearing the translation override", async () => {
    const entry = await exampleEntry();
    const original = cardDraft(entry);
    expect(cardChanges(original, original)).toEqual({});
    expect(cardChanges(original, { ...original, meaning: "мой перевод" })).toEqual({ meaning_ru: "мой перевод" });
    expect(cardChanges({ ...original, meaning: "мой перевод" }, { ...original, meaning: "" })).toEqual({ meaning_ru: "" });
    expect(cardChanges(original, { ...original, exampleId: "another" })).toEqual({ example_occurrence_id: "another" });
  });

  it("uses the selected occurrence and its book, without substituting a different book for a missing id", async () => {
    const entry = await exampleEntry();
    const occurrence = entry.occurrences[entry.occurrences.length - 1];
    entry.card = { meaning_ru: "значение", meaning_source: "edited", example_occurrence_id: occurrence.id, edited: true };
    expect(cardDraft(entry)).toEqual({ meaning: "значение", exampleId: occurrence.id });
    expect(selectedExample(entry, cardDraft(entry).exampleId)).toBe(occurrence);
    expect(selectedExample(entry, "removed")).toBeUndefined();
  });

  it("keeps an explicit skip out of the worth list and restores ranking when it is removed", async () => {
    const entry = await exampleEntry();
    entry.ranking = null;
    entry.decision = { value: "skip", decided_at: "" };
    expect(worthLearning(entry)).toBe(false);
    entry.decision = null;
    entry.ranking = { score: 4, shelf: "worth", rank: 1, reasons: [], lean: null, version: "r2" };
    expect(worthLearning(entry)).toBe(true);
    entry.decision = { value: "known", decided_at: "" };
    expect(worthLearning(entry)).toBe(true);
  });
});
