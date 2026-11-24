import * as React from "react";
import type { useLibraryController } from "@/features/library/use-library-controller";
import { readerName } from "@/features/library/domain";
import { HomeView } from "./home-view";
import { homeMode, homeProcessingProgress, homeQueueState, rankingNote, shortList, sinceLastTimeLine } from "./home-domain";
import type { useHomeExport } from "./use-home-export";

type Controller = ReturnType<typeof useLibraryController>;

/** Главная: connects the library controller to the screen. What is said and when lives in home-domain.ts. */
export function HomeScreen({ controller, exporter, onOpenWord, onOpenLibrary }: {
  controller: Controller;
  exporter: ReturnType<typeof useHomeExport>;
  onOpenWord: (id: string) => void;
  onOpenLibrary: () => void;
}) {
  const { entries, ranking, loading, demo, operation, queueStatus, connectors, settings, settingsSaving } = controller;
  const words = React.useMemo(() => shortList(entries, exporter.selectedIds.slice(0, 5)), [entries, exporter.selectedIds]);
  const sinceLine = React.useMemo(() => sinceLastTimeLine(entries), [entries]);
  const queue = homeQueueState(queueStatus, operation);
  const readyForDesk = queue === "idle" || queue === "stopped" && Boolean(ranking?.newBatch.count);
  const mode = homeMode({ loading, entryCount: entries.length, batchCount: readyForDesk ? entries.length : ranking?.newBatch.count ?? 0, demo, queue });

  // The list is about to change while the reader is read or new words are analysed.
  const listChanging = !demo && (queue === "working" || (operation.status === "running" && operation.kind === "kindle"));
  const exportBlocked = settingsSaving || operation.status === "running";

  return (
    <HomeView
      mode={mode}
      words={words}
      quantity={exporter.quantity}
      onOpenLibrary={onOpenLibrary}
      onFindReader={() => void controller.findReader()}
      findingReader={controller.findingReader}
      quiet={operation.status === "error" || queue === "stopped"}
      sinceLine={sinceLine}
      processingProgress={!demo && queue === "working" ? homeProcessingProgress(operation) : null}
      roughNote={rankingNote(ranking)}
      demo={demo}
      exportUi={exporter.state}
      destination={settings.export_destination}
      openState={exporter.openState}
      folderState={exporter.folderState}
      exportBlocked={exportBlocked}
      listChanging={listChanging}
      reader={{ state: connectors.kindle.state, name: readerName(connectors.kindle) }}
      onExport={() => void exporter.start()}
      onOpenWord={onOpenWord}
      onOpenResult={(path) => void exporter.openResult(path)}
      onOpenFolder={() => void exporter.openFolder()}
      onSync={() => void controller.syncKindle()}
      onImportFile={(file) => void controller.importReaderFile(file)}
      onDemo={() => void controller.loadDemo()}
      onExitDemo={() => void controller.exitDemo()}
      onRetryProcessing={() => void controller.retryFailed()}
    />
  );
}
