import { expect } from "vitest";
import { DISPUTED_CAP, type LexemeRecordV4, type LibraryRanking, type LibraryResultV4, type Shelf } from "@/types";

// The assertions `bridge-contract.test.ts` makes about the shared fixture, as functions, so the browser
// mock is held to the same contract the Python bridge is.

export const libraryKeys: (keyof LibraryRanking)[] = [
  "rankingVersion", "rankingMode", "historyDays", "repeatSignal", "shelves", "newBatch", "disputed", "again",
];
export const lexemeKeys: (keyof LexemeRecordV4)[] = ["ranking", "decision", "card", "export", "is_new"];
export const allShelves: Shelf[] = ["worth", "disputed", "not_worth", "junk", "known"];

export function expectEveryKey(library: LibraryResultV4): void {
  for (const key of libraryKeys) expect(library).toHaveProperty(key);
  for (const entry of library.entries) for (const key of lexemeKeys) expect(entry).toHaveProperty(key);
}

/** Every shelf, a decision, an edited card, an exported word that came back and an unprocessed word. */
export function expectEveryCase(library: LibraryResultV4): void {
  const ranked = library.entries.flatMap((entry) => (entry.ranking ? [entry.ranking] : []));
  expect(new Set(ranked.map((ranking) => ranking.shelf))).toEqual(new Set(allShelves));
  expect(library.entries.some((entry) => entry.decision !== null)).toBe(true);
  expect(library.entries.some((entry) => entry.card.edited && entry.card.meaning_source === "edited")).toBe(true);
  expect(library.entries.some((entry) => entry.export.state === "exported" && entry.export.again)).toBe(true);
  expect(library.entries.some((entry) => entry.ranking === null)).toBe(true);
}

export function expectRanksAndCounts(library: LibraryResultV4): void {
  for (const shelf of allShelves) {
    const ranks = library.entries.flatMap((entry) => (entry.ranking?.shelf === shelf ? [entry.ranking.rank] : []));
    expect([...ranks].sort((a, b) => a - b)).toEqual(ranks.map((_, index) => index + 1));
    expect(library.shelves[shelf]).toBe(ranks.length);
  }
}

export function expectShortList(library: LibraryResultV4): void {
  expect(library.disputed.ids.length).toBeLessThanOrEqual(DISPUTED_CAP);
  for (const id of library.disputed.ids) expect(library.newBatch.ids).not.toContain(id);
  expect(library.newBatch.count).toBe(library.newBatch.ids.length);
  const shelfOf = (id: string) => library.entries.find((entry) => entry.id === id)?.ranking?.shelf;
  for (const id of library.newBatch.ids) expect(shelfOf(id)).toBe("worth");
  for (const id of library.disputed.ids) expect(shelfOf(id)).toBe("disputed");
  const ranks = library.newBatch.ids.map((id) => library.entries.find((entry) => entry.id === id)?.ranking?.rank ?? 0);
  expect(ranks).toEqual([...ranks].sort((a, b) => a - b));
  for (const id of library.newBatch.ids) expect(library.entries.find((entry) => entry.id === id)?.export.state).toBe("not_exported");
}
