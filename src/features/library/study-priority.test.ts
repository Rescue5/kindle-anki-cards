import { describe, expect, it } from "vitest";
import type { LexemeRecord, LibraryResult } from "@/types";
import { mockBackend, resetMockBackend } from "@/lib/mock-backend";
import { compareStudyPriority, priorityEntries, recordedSearchEvidence, studyPriority } from "./study-priority";

async function libraryEntries() {
  resetMockBackend({ scenario: "mixed", instant: true });
  return (await mockBackend<LibraryResult>("load_library", {})).entries;
}

describe("study priority catalogue", () => {
  it("shows old, rejected and low-priority records in the default catalogue", async () => {
    const entries = await libraryEntries();
    const rejected: LexemeRecord = { ...entries[0], id: "rejected-old", freshness: "known",
      processing: { ...entries[0].processing, state: "rejected" },
      study_priority: { level: 9, score: .01, provisional: false, reason: "Редко встречается" } };
    const records = [...entries, rejected];
    expect(priorityEntries(records, "", undefined, "all")).toHaveLength(records.length);
    expect(priorityEntries(records, "", undefined, "all").map((entry) => entry.id)).toContain(rejected.id);
  });

  it("sorts by level, provisional flag, descending score and id independently of personal decisions", async () => {
    const base = (await libraryEntries())[0];
    const make = (id: string, level: number, provisional: boolean, score: number): LexemeRecord => ({
      ...base, id, study_priority: { level, provisional, score, reason: "Причина" },
    });
    const records = [make("z", 2, true, .9), make("b", 2, false, .3), make("a", 2, false, .3), make("high", 1, false, .34), make("low", 2, false, .29)];
    records[3].decision = { value: "skip", decided_at: "" };
    expect([...records].sort(compareStudyPriority).map((entry) => entry.id)).toEqual(["high", "a", "b", "low", "z"]);
    expect(records[0].id).toBe("z");
  });

  it("intersects search, book and exact priority level", async () => {
    const base = (await libraryEntries())[0];
    const make = (id: string, level: number, book: string): LexemeRecord => ({ ...base, id,
      occurrences: [{ ...base.occurrences[0], book_key: book, context: "A searchable sentence." }],
      study_priority: { level, score: .2, provisional: false, reason: "Причина" },
    });
    const records = [make("match", 4, "one"), make("wrong-level", 5, "one"), make("wrong-book", 4, "two")];
    expect(priorityEntries(records, "searchable", { key: "one", label: "Book" }, 4).map((entry) => entry.id)).toEqual(["match"]);
    expect(priorityEntries(records, "missing", { key: "one", label: "Book" }, 4)).toEqual([]);
  });

  it("puts every measured level before provisional words and structural records last in coverage mode", async () => {
    const base = (await libraryEntries())[0];
    const make = (id: string, level: number, provisional: boolean, score: number): LexemeRecord => ({
      ...base, id, study_priority: { level, provisional, score, reason: "Причина" },
    });
    const records = [
      make("structural", 10, false, 0), make("unknown", 6, true, 0), make("rare", 9, false, .001),
      make("b", 6, false, .06), make("a", 6, false, .06), make("higher", 6, false, .09),
    ];
    const ids = priorityEntries(records, "", undefined, "all", "rp-v2-coverage").map(({ id }) => id);
    expect(ids).toEqual(["higher", "a", "b", "rare", "unknown", "structural"]);
    expect(priorityEntries(records, "", undefined, 6, "rp-v2-coverage").map(({ id }) => id))
      .toEqual(["higher", "a", "b", "unknown"]);
  });

  it("keeps an older payload visible as provisional level 6", async () => {
    const entry = (await libraryEntries())[0];
    delete entry.study_priority;
    expect(studyPriority(entry)).toEqual({ level: 6, score: 0, provisional: true, reason: "Данные для приоритета ещё не получены." });
  });

  it("counts recorded reader entries and known book IDs without inferring missing searches or books", async () => {
    const base = (await libraryEntries())[0].occurrences[0];
    const reader = { ...base, source: "kindle" as const, book_key: "koreader:one", id: "repeat" };
    const legacy = { ...base, id: "legacy", source: "legacy" as const, book_key: "legacy:book" };
    const missingBook = { ...reader, id: "no-book", book_key: "", looked_up_at: "", context: "" };
    expect(recordedSearchEvidence([reader, reader, { ...reader, id: "separate" }, missingBook, legacy]))
      .toBe("Записей поиска: 3 · Книг в записях: 1");
    expect(recordedSearchEvidence([missingBook])).toBe("Записей поиска: 1");
    expect(recordedSearchEvidence([legacy])).toBe("");
  });
});
