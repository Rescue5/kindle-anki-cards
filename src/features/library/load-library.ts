import { callBackend } from "@/lib/backend";
import type { AppSettings, LexemeRecord, LibraryResult } from "@/types";

export type ObsidianCheck =
  | { status: "idle" | "checking" | "ready" }
  | { status: "error"; message: string };

export function obsidianConfig(settings: AppSettings) {
  const vault = settings.obsidian_vault_path.trim();
  const cards = settings.obsidian_cards_path.trim();
  return settings.obsidian_sync_enabled && vault && cards
    ? { vault_path: vault, cards_path: cards }
    : null;
}

export function readObsidianEvidence(config: NonNullable<ReturnType<typeof obsidianConfig>>) {
  return callBackend<LibraryResult>("load_obsidian", config);
}

/** A delayed Obsidian response must not restore a stale library or ranking. */
export function mergeObsidianEvidence(current: LexemeRecord[], checked: LexemeRecord[]) {
  const byId = new Map(checked.map((entry) => [entry.id, entry.destinations.obsidian]));
  return current.map((entry) => {
    const obsidian = byId.get(entry.id);
    if (!obsidian || obsidian.eligible !== entry.destinations.obsidian.eligible) return entry;
    return { ...entry, destinations: { ...entry.destinations, obsidian } };
  });
}
