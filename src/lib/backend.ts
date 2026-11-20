import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { AppSettings, ErrorCode, ProgressEvent } from "@/types";

const isTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export const defaultSettings: AppSettings = {
  theme: "system",
  language: "ru",
  default_export_format: "anki",
  app_data_path: ".app-data",
  llm_enabled: false,
  llm_provider: "",
  llm_model: "",
  llm_base_url: "",
  llm_auto_enrich: false,
  obsidian_sync_enabled: false,
  obsidian_vault_path: "",
  obsidian_cards_path: "cards/Book Vocab",
  obsidian_backup_enabled: true,
};

/** A failed action with the contract's error code, when the bridge (or the browser mock) sends one. */
export class BridgeError extends Error {
  readonly code?: ErrorCode;

  constructor(message: string, code?: ErrorCode) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
  }

  /** Callers that print `String(error)` get the Russian text, not "BridgeError: ...". */
  override toString(): string {
    return this.message;
  }
}

/**
 * The Rust bridge rejects an `ok:false` answer with the JSON text `{"error": "...", "code": "..."}`.
 * That becomes a `BridgeError`; anything else (a plain string, an Error from Tauri) passes through as it came.
 */
export function parseBridgeError(raw: unknown): unknown {
  if (raw instanceof BridgeError || typeof raw !== "string") return raw;
  const text = raw.trim();
  if (!text.startsWith("{")) return raw;
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && typeof (parsed as { error?: unknown }).error === "string") {
      const { error, code } = parsed as { error: string; code?: unknown };
      return new BridgeError(error, typeof code === "string" ? (code as ErrorCode) : undefined);
    }
  } catch {
    // Not JSON after all: keep the plain string.
  }
  return raw;
}

// The browser stand-in is imported lazily: the desktop build never loads it.
const loadMock = () => import("./mock-backend");

export async function callBackend<T>(action: string, payload: unknown): Promise<T> {
  if (!isTauri()) return (await loadMock()).mockBackend<T>(action, payload);
  try {
    return await invoke<T>("python_bridge", { action, payload });
  } catch (error) {
    throw parseBridgeError(error);
  }
}

export async function cancelBackend(jobId: string): Promise<boolean> {
  if (!isTauri()) {
    (await loadMock()).cancelMockJob(jobId);
    return true;
  }
  return invoke<boolean>("cancel_python_bridge", { jobId });
}

export async function listenProgress(handler: (event: ProgressEvent) => void): Promise<UnlistenFn> {
  if (!isTauri()) return () => undefined;
  return listen<ProgressEvent>("backend-progress", (event) => handler(event.payload));
}
