import { beforeEach, describe, expect, it, vi } from "vitest";
import { callBackend, defaultSettings } from "@/lib/backend";
import { mergeObsidianEvidence, obsidianConfig, readObsidianEvidence } from "./load-library";
import type { LexemeRecord } from "@/types";

vi.mock("@/lib/backend", () => ({
  callBackend: vi.fn(),
  defaultSettings: { obsidian_sync_enabled: false, obsidian_vault_path: "", obsidian_cards_path: "" },
}));

function entry(id: string, state: LexemeRecord["destinations"]["obsidian"]["state"] = "missing", eligible = true) {
  return {
    id,
    destinations: { obsidian: { state, eligible }, anki: { state: "not_exported" } },
  } as LexemeRecord;
}

describe("library Obsidian reconciliation", () => {
  beforeEach(() => { vi.mocked(callBackend).mockReset(); });

  it("checks the saved folder without exporting and preserves bridge errors", async () => {
    const config = obsidianConfig({
      ...defaultSettings, obsidian_sync_enabled: true, obsidian_vault_path: " vault ", obsidian_cards_path: "cards",
    });
    vi.mocked(callBackend).mockRejectedValueOnce(new Error("Cards directory does not exist"));
    await expect(readObsidianEvidence(config!)).rejects.toThrow("Cards directory does not exist");
    expect(vi.mocked(callBackend).mock.calls).toEqual([["load_obsidian", { vault_path: "vault", cards_path: "cards" }]]);
  });

  it("waits for both paths and the integration switch", () => {
    expect(obsidianConfig({ ...defaultSettings, obsidian_sync_enabled: true, obsidian_vault_path: "vault" })).toBeNull();
    expect(obsidianConfig({ ...defaultSettings, obsidian_vault_path: "vault", obsidian_cards_path: "cards" })).toBeNull();
  });

  it("updates Obsidian evidence without replacing a newer catalog, eligibility, or export state", () => {
    const completed = entry("same");
    completed.destinations.anki.state = "exported";
    const newEntry = entry("new");
    const newlyEligible = entry("changed");
    const checked = [entry("same", "synced"), entry("gone", "synced"), entry("changed", "not_applicable", false)];
    const result = mergeObsidianEvidence([completed, newEntry, newlyEligible], checked);
    expect(result[0].destinations.obsidian.state).toBe("synced");
    expect(result[0].destinations.anki).toBe(completed.destinations.anki);
    expect(result[1]).toBe(newEntry);
    expect(result[2]).toBe(newlyEligible);
    expect(result).toHaveLength(3);
  });
});
