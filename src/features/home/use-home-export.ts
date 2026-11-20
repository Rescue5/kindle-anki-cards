import * as React from "react";
import { callBackend, BridgeError } from "@/lib/backend";
import type { ExportRun } from "@/types";
import { exportReducer, idleExport } from "./home-domain";

type Options = {
  /** The short list as the reader sees it: exactly these words are sent. */
  ids: readonly string[];
  /** Refresh the short list after the export or when the bridge finds it stale. */
  reload: () => Promise<void>;
  active: boolean;
};

export type OpenResultState = "idle" | "opening-file" | "failed-file";
export type ExportFolderState = "hidden" | "ready" | "opening" | "missing" | "error";

function jobId() {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `job-${Date.now()}`;
}

/** Export of the short list, with the states Главная shows inline: running, done, empty, error. */
export function useHomeExport({ ids, reload, active }: Options) {
  const [state, dispatch] = React.useReducer(exportReducer, idleExport);
  const [openState, setOpenState] = React.useState<OpenResultState>("idle");
  const [folderState, setFolderState] = React.useState<ExportFolderState>("hidden");
  const runningRef = React.useRef(false);
  const openingFolder = React.useRef(false);
  const folderRevision = React.useRef(0);

  const refreshFolder = React.useCallback(async () => {
    if (openingFolder.current) return;
    const revision = ++folderRevision.current;
    try {
      const result = await callBackend<{ available: boolean }>("export_folder_status", {});
      if (revision !== folderRevision.current) return;
      setFolderState((previous) => result.available ? "ready" : previous === "hidden" ? "hidden" : "missing");
    } catch {
      // The folder remains available to retry when a status request fails.
    }
  }, []);

  React.useEffect(() => {
    if (!active) return;
    void refreshFolder();
    window.addEventListener("focus", refreshFolder);
    return () => window.removeEventListener("focus", refreshFolder);
  }, [active, refreshFolder]);

  const openFolder = React.useCallback(async () => {
    if (openingFolder.current) return;
    openingFolder.current = true;
    folderRevision.current += 1;
    setFolderState("opening");
    try {
      const result = await callBackend<{ opened: boolean }>("open_export_folder", {});
      if (result.opened) {
        setFolderState("ready");
      } else {
        const status = await callBackend<{ available: boolean }>("export_folder_status", {});
        setFolderState(status.available ? "error" : "missing");
      }
    } catch {
      setFolderState("error");
    } finally {
      openingFolder.current = false;
    }
  }, []);

  const start = React.useCallback(async () => {
    if (runningRef.current || ids.length === 0) return;
    runningRef.current = true;
    setOpenState("idle");
    dispatch({ type: "start" });
    try {
      const run = await callBackend<ExportRun>("export_words", { job_id: jobId(), scope: "new", ids: [...ids] });
      if (run.path && !openingFolder.current) setFolderState("ready");
      // A failed reload does not undo an export that went through.
      await reload().catch(() => undefined);
      dispatch({ type: "success", run });
    } catch (error) {
      const bridge = error instanceof BridgeError ? error : null;
      if ((bridge?.code === "anki_import_unconfirmed" || bridge?.code === "anki_import_rejected") && !openingFolder.current) setFolderState("ready");
      if (bridge?.code === "nothing_to_export") await reload().catch(() => undefined);
      dispatch({ type: "failure", message: bridge?.message ?? String(error), code: bridge?.code });
    } finally {
      runningRef.current = false;
      void refreshFolder();
    }
  }, [ids, refreshFolder, reload]);

  const openResult = React.useCallback(async (path: string) => {
    setOpenState("opening-file");
    try {
      const result = await callBackend<{ opened: boolean }>("open_path", { path, reveal: false });
      if (!result.opened) throw new Error();
      setOpenState("idle");
    } catch {
      setOpenState("failed-file");
      void refreshFolder();
    }
  }, [refreshFolder]);

  const dismiss = React.useCallback(() => {
    setOpenState("idle");
    dispatch({ type: "dismiss" });
  }, []);

  return { state, openState, folderState, start, openResult, openFolder, dismiss };
}
