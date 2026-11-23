import { describe, expect, it } from "vitest";
import fullFixture from "../../tests/fixtures/bridge_library_v4.json";
import learningFixture from "../../tests/fixtures/bridge_library_v4_learning.json";
import {
  DISPUTED_CAP,
  ERROR_TEXTS,
  type ErrorCode,
  type LexemeRecordV4,
  type LibraryRanking,
  type LibraryResultV4,
  type Shelf,
} from "@/types";

// The same files `tests/test_bridge_contract.py` validates against `kindle_vocab_app/contracts.py`.
// Assigning them to the types is the compile-time check (`npm run build` runs tsc over this file);
// the key lists below are typed with `keyof`, so a renamed field breaks the build, and the asserts
// catch a fixture that lost a field.
const full = fullFixture as LibraryResultV4;
const learning = learningFixture as LibraryResultV4;

const libraryKeys: (keyof LibraryRanking)[] = [
  "rankingVersion", "rankingMode", "historyDays", "repeatSignal", "shelves", "newBatch", "disputed", "again",
];
const lexemeKeys: (keyof LexemeRecordV4)[] = ["study_priority", "ranking", "decision", "card", "export", "is_new"];
const shelves: Shelf[] = ["worth", "disputed", "not_worth", "junk", "known"];
const errorCodes: ErrorCode[] = [
  "no_destination", "too_long", "example_not_found", "nothing_to_export", "export_failed",
  "anki_import_unconfirmed", "anki_import_rejected", "export_busy",
  "unknown_lexeme", "bad_decision", "bad_scope",
];

describe("bridge contract fixture", () => {
  it("carries every library-level and lexeme-level key", () => {
    for (const library of [full, learning]) {
      for (const key of libraryKeys) expect(library).toHaveProperty(key);
      for (const entry of library.entries) for (const key of lexemeKeys) expect(entry).toHaveProperty(key);
    }
  });

  it("covers every shelf, a decision, an edited card, an exported word that came back and an unprocessed word", () => {
    const ranked = full.entries.flatMap((entry) => (entry.ranking ? [entry.ranking] : []));
    expect(new Set(ranked.map((ranking) => ranking.shelf))).toEqual(new Set(shelves));
    expect(full.entries.some((entry) => entry.decision !== null)).toBe(true);
    expect(full.entries.some((entry) => entry.card.edited && entry.card.meaning_source === "edited")).toBe(true);
    expect(full.entries.some((entry) => entry.export.state === "exported" && entry.export.again)).toBe(true);
    expect(full.entries.some((entry) => entry.ranking === null)).toBe(true);
  });

  it("numbers ranks from 1 inside each shelf and keeps the shelf counts true", () => {
    for (const shelf of shelves) {
      const ranks = full.entries.flatMap((entry) => (entry.ranking?.shelf === shelf ? [entry.ranking.rank] : []));
      expect([...ranks].sort((a, b) => a - b)).toEqual(ranks.map((_, index) => index + 1));
      expect(full.shelves[shelf]).toBe(ranks.length);
    }
  });

  it("keeps the short list to worth words and the disputed words out of it, under the cap", () => {
    expect(full.disputed.ids.length).toBeLessThanOrEqual(DISPUTED_CAP);
    for (const id of full.disputed.ids) expect(full.newBatch.ids).not.toContain(id);
    expect(full.newBatch.count).toBe(full.newBatch.ids.length);
    const shelfOf = (id: string) => full.entries.find((entry) => entry.id === id)?.ranking?.shelf;
    for (const id of full.newBatch.ids) expect(shelfOf(id)).toBe("worth");
    for (const id of full.disputed.ids) expect(shelfOf(id)).toBe("disputed");
  });

  it("marks the repeat-less library: learning mode, no again signal", () => {
    expect(full.rankingMode).toBe("full");
    expect(full.repeatSignal).toBe(true);
    expect(full.again.unavailable).toBe(false);
    expect(learning.rankingMode).toBe("learning");
    expect(learning.repeatSignal).toBe(false);
    expect(learning.again).toEqual({ count: 0, ids: [], unavailable: true });
    expect(learning.entries.every((entry) => !entry.export.again)).toBe(true);
  });

  it("has a Russian text for every error code", () => {
    for (const code of errorCodes) expect(ERROR_TEXTS[code]).toMatch(/[А-Яа-я]/);
    expect(Object.keys(ERROR_TEXTS).sort()).toEqual([...errorCodes].sort());
  });
});
