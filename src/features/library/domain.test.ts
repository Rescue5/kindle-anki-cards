import { describe, expect, it } from "vitest";
import {
  counts,
  filterLexemes,
  KINDLE_AUTO_SYNC_RETRY_MS,
  obsidianSyncReason,
  ankiPendingCount,
  enrichmentCounts,
  shouldAutoEnrich,
  shouldAutoProcessQueue,
  shouldAutoSyncKindle,
} from "./domain";
import type { ConnectorInfo, LexemeRecord, QueueStatus } from "@/types";

const entry = {
  id: "one",
  lemma: "admit",
  display_form: "admitting",
  language: "en",
  forms: ["admit", "admitting"],
  occurrences: [{ id: "occ", source: "kindle", word: "admitting", context: "She admitted it.", book_key: "book", book_title: "Book", authors: "Author", looked_up_at: "2026-07-10" }],
  freshness: "new",
  processing: { state: "pending", analysis: null, updated_at: "", error: "" },
  sources: { kindle: true, legacy: false },
  destinations: {
    obsidian: { state: "not_applicable", eligible: false, reason: "waiting_processing", external_key: "admit", last_checked_at: "", last_synced_at: "" },
    anki: { state: "not_exported", last_exported_at: "" },
    quizlet: { state: "not_exported", last_exported_at: "" },
  },
  first_seen_at: "2026-07-10",
  last_seen_at: "2026-07-10",
  last_kindle_sync_id: "sync",
} satisfies LexemeRecord;

describe("library selectors", () => {
  it("does not count pending words as accepted new or missing from Obsidian", () => {
    expect(counts([entry])).toEqual({ all: 1, new: 0, pending: 1, ready: 0, unsynced: 0 });
  });

  it("filters by occurrence book and context", () => {
    expect(filterLexemes([entry], "admitted", { key: "book", label: "Book" }, "all")).toHaveLength(1);
    expect(filterLexemes([entry], "missing", { key: "book", label: "Book" }, "all")).toHaveLength(0);
  });

  it("explains why an unsynced pending lexeme is blocked", () => {
    expect(obsidianSyncReason(entry)).toBe("Сначала выполните offline-обработку");
  });

  it("excludes rejected words from New and Not in Obsidian", () => {
    const rejected: LexemeRecord = {
      ...entry,
      processing: { state: "rejected", analysis: { base_form: "admit", accepted: false, importance_score: 1 }, updated_at: "", error: "" },
      destinations: { ...entry.destinations, obsidian: { ...entry.destinations.obsidian, state: "not_applicable", reason: "rejected" } },
    };
    expect(counts([rejected])).toEqual({ all: 1, new: 0, pending: 0, ready: 0, unsynced: 0 });
    expect(filterLexemes([rejected], "", undefined, "new")).toHaveLength(0);
    expect(filterLexemes([rejected], "", undefined, "unsynced")).toHaveLength(0);
  });

  it("counts only accepted new words that are actually missing from Obsidian", () => {
    const ready: LexemeRecord = {
      ...entry,
      processing: { state: "ready", analysis: { base_form: "admit", accepted: true, importance_score: 7 }, updated_at: "", error: "" },
      destinations: { ...entry.destinations, obsidian: { ...entry.destinations.obsidian, state: "missing", eligible: true, reason: "" } },
    };
    expect(counts([ready])).toEqual({ all: 1, new: 1, pending: 0, ready: 1, unsynced: 1 });
  });
});

describe("Kindle auto-sync policy", () => {
  const disconnected: ConnectorInfo = { state: "disconnected", label: "Kindle", checked_at: "" };
  const connected: ConnectorInfo = {
    state: "connected",
    label: "Kindle Paperwhite",
    checked_at: "",
    signature: ["windows-device", "kindle"],
  };

  it("syncs when a visible Kindle has just connected", () => {
    expect(shouldAutoSyncKindle({
      previous: disconnected,
      current: connected,
      lastSyncedSignature: "windows-device|kindle",
      lastAttemptAt: 0,
      now: 1,
    })).toBe(true);
  });

  it("does not touch an unchanged connected Kindle after a successful sync", () => {
    expect(shouldAutoSyncKindle({
      previous: connected,
      current: connected,
      lastSyncedSignature: "windows-device|kindle",
      lastAttemptAt: 0,
      now: KINDLE_AUTO_SYNC_RETRY_MS * 2,
    })).toBe(false);
  });

  it("backs off before retrying a failed auto-sync", () => {
    expect(shouldAutoSyncKindle({
      previous: connected,
      current: connected,
      lastSyncedSignature: null,
      lastAttemptAt: 10_000,
      now: 10_000 + KINDLE_AUTO_SYNC_RETRY_MS - 1,
    })).toBe(false);
    expect(shouldAutoSyncKindle({
      previous: connected,
      current: connected,
      lastSyncedSignature: null,
      lastAttemptAt: 10_000,
      now: 10_000 + KINDLE_AUTO_SYNC_RETRY_MS,
    })).toBe(true);
  });
});

describe("automatic processing queue policy", () => {
  const queue = (pending: number, failed: number): QueueStatus => ({ pending, processing: 0, failed, total: pending + failed });
  const idle = { kind: "idle", status: "idle" } as const;

  it("processes pending lexemes when nothing else is running", () => {
    expect(shouldAutoProcessQueue({ loading: false, inFlight: false, queue: queue(2, 0), operation: idle })).toBe(true);
  });

  it("never re-runs failed lexemes automatically", () => {
    expect(shouldAutoProcessQueue({ loading: false, inFlight: false, queue: queue(0, 3), operation: idle })).toBe(false);
  });

  it("pauses after a failed or cancelled processing run", () => {
    for (const status of ["error", "cancelled"] as const) {
      expect(shouldAutoProcessQueue({ loading: false, inFlight: false, queue: queue(1, 1), operation: { kind: "processing", status } })).toBe(false);
    }
  });

  it("is not blocked by an unrelated operation error", () => {
    expect(shouldAutoProcessQueue({ loading: false, inFlight: false, queue: queue(1, 0), operation: { kind: "kindle", status: "error" } })).toBe(true);
  });

  it("waits while loading, running, or already in flight", () => {
    expect(shouldAutoProcessQueue({ loading: true, inFlight: false, queue: queue(1, 0), operation: idle })).toBe(false);
    expect(shouldAutoProcessQueue({ loading: false, inFlight: true, queue: queue(1, 0), operation: idle })).toBe(false);
    expect(shouldAutoProcessQueue({ loading: false, inFlight: false, queue: queue(1, 0), operation: { kind: "kindle", status: "running" } })).toBe(false);
  });
});

describe("translation and Anki selectors", () => {
  const ready: LexemeRecord = {
    ...entry,
    processing: { state: "ready", analysis: { base_form: "admit", accepted: true, importance_score: 7 }, updated_at: "", error: "" },
  };
  const translated: LexemeRecord = {
    ...ready,
    id: "two",
    enrichment: { status: "ready", meaning_ru: "признать", provider: "p", model: "m", prompt_version: 1, error: "", updated_at: "" },
    destinations: { ...ready.destinations, anki: { state: "exported", last_exported_at: "now" } },
  };
  const failed: LexemeRecord = { ...ready, id: "three", enrichment: { ...translated.enrichment!, status: "failed", error: "x" } };
  const useless: LexemeRecord = { ...ready, id: "four", processing: { ...ready.processing, analysis: { base_form: "the", accepted: true, importance_score: 1 } } };

  it("counts only card-worthy words waiting for translation", () => {
    expect(enrichmentCounts([entry, ready, translated, failed, useless])).toEqual({ pending: 1, failed: 1 });
  });

  it("counts words not yet exported to Anki", () => {
    expect(ankiPendingCount([entry, ready, translated, useless])).toBe(1);
  });

  it("queues an exported card again once its translation is newer", () => {
    const exportedEarly: LexemeRecord = {
      ...translated,
      enrichment: { ...translated.enrichment!, updated_at: "2026-10-02T00:00:00Z" },
      destinations: { ...translated.destinations, anki: { state: "exported", last_exported_at: "2026-10-01T00:00:00Z" } },
    };
    expect(ankiPendingCount([exportedEarly])).toBe(1);
  });

  it("auto-translates only when opted in and offline processing is done", () => {
    const base = { enabled: true, auto: true, loading: false, inFlight: false, pending: 3, processingPending: 0, operation: { kind: "idle", status: "idle" } as const };
    expect(shouldAutoEnrich(base)).toBe(true);
    expect(shouldAutoEnrich({ ...base, auto: false })).toBe(false);
    expect(shouldAutoEnrich({ ...base, processingPending: 2 })).toBe(false);
    expect(shouldAutoEnrich({ ...base, operation: { kind: "enrich", status: "error" } })).toBe(false);
    expect(shouldAutoEnrich({ ...base, operation: { kind: "kindle", status: "error" } })).toBe(true);
  });
});
