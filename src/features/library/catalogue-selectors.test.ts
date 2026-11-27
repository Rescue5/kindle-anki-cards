import { describe, expect, it } from "vitest";
import { mockBackend, resetMockBackend } from "@/lib/mock-backend";
import type { LexemeRecord, LibraryResult } from "@/types";
import { catalogueGroup, defaultCatalogueFilters, selectCatalogueEntries, selectTranslationEntries } from "./catalogue-selectors";

async function fixture() {
  resetMockBackend({ scenario: "mixed", instant: true });
  const [base] = (await mockBackend<LibraryResult>("load_library", {})).entries;
  return function word(id: string, level: number, patch: Partial<LexemeRecord> = {}): LexemeRecord {
    return {
      ...base, id, lemma: id, display_form: id, forms: [id], decision: null,
      occurrences: [{ ...base.occurrences[0], book_key: "target", context: "A searchable sentence." }],
      study_priority: { level, score: .1, provisional: false, reason: "Причина." },
      ...patch,
    };
  };
}

describe("catalogue selectors", () => {
  it("intersects levels 8, 9 and 10 with book, text and server translation eligibility", async () => {
    const word = await fixture();
    const wrongBook = word("other-book", 10);
    wrongBook.occurrences[0].book_key = "other";
    const wrongText = word("other-text", 9);
    wrongText.occurrences[0].context = "Different sentence.";
    const filters = { ...defaultCatalogueFilters, levels: [8, 9, 10] };
    const visible = selectCatalogueEntries([
      word("eight", 8), word("nine", 9), word("ten", 10), word("seven", 7), wrongBook, wrongText,
    ], "searchable", { key: "target", label: "Book" }, filters, "rp-v2-personal");
    expect(visible.map(({ id }) => id)).toEqual(["eight", "nine", "ten"]);
    expect(selectTranslationEntries(visible, new Set(["ten", "eight", "seven"])).map(({ id }) => id)).toEqual(["eight", "ten"]);
    expect(selectTranslationEntries([], new Set(["ten"]))).toEqual([]);
  });

  it("hides skips initially and shows them only under the skip or all filters", async () => {
    const word = await fixture();
    const entries = [word("skipped", 1, { decision: { value: "skip", decided_at: "" } }), word("visible", 2)];
    expect(selectCatalogueEntries(entries, "", undefined, defaultCatalogueFilters).map(({ id }) => id)).toEqual(["visible"]);
    expect(selectCatalogueEntries(entries, "", undefined, { ...defaultCatalogueFilters, decision: "skip" }).map(({ id }) => id)).toEqual(["skipped"]);
    expect(selectCatalogueEntries(entries, "", undefined, { ...defaultCatalogueFilters, decision: "all" })).toHaveLength(2);
  });

  it("uses the first import date and stable freshness even after export", async () => {
    const word = await fixture();
    const entries = [
      word("retouched", 2, { freshness: "known", first_seen_at: "2026-08-01", last_seen_at: "2026-11-26" }),
      word("no-date", 1, { freshness: "known", first_seen_at: "" }),
      word("imported", 9, { freshness: "new", is_new: false, first_seen_at: "2026-10-01", last_seen_at: "2026-10-01" }),
    ];
    expect(selectCatalogueEntries(entries, "", undefined, { ...defaultCatalogueFilters, sort: "added" }).map(({ id }) => id))
      .toEqual(["imported", "retouched", "no-date"]);
    expect(selectCatalogueEntries(entries, "", undefined, { ...defaultCatalogueFilters, recent: true }).map(({ id }) => id))
      .toEqual(["imported"]);
  });

  it("keeps provisional RP-V2 words outside measured priority groups", async () => {
    const word = await fixture();
    const provisional = word("pending", 6, { study_priority: { level: 6, score: 0, provisional: true, reason: "Причина." } });
    expect(catalogueGroup(provisional, "rp-v2-personal")).toBe("Предварительные оценки");
    expect(catalogueGroup(word("measured", 6), "rp-v2-personal")).toBe("4–6 · Средний приоритет");
    expect(catalogueGroup(word("structural", 10), "rp-v2-personal")).toBe("10 · Проверить запись");
  });
});
