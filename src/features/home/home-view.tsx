import * as React from "react";
import { Check, ChevronRight, Loader2, RefreshCw, Upload } from "lucide-react";
import type { AppSettings, ConnectorState, LexemeRecord } from "@/types";
import type { ExportFolderState, OpenResultState } from "./use-home-export";
import type { HomeProcessingProgress } from "./home-domain";
import { DeskLamp } from "@/components/light/light";
import { PencilRule } from "@/components/sketch/sketch";
import { PencilButton, PencilLink } from "@/components/ui/pencil-controls";
import { ImportFileButton } from "@/components/import-file-button";
import {
  EMPTY_NOTE,
  EMPTY_TITLE,
  LIST_TITLE,
  LOAD_FROM_READER,
  READER_LOCATIONS,
  READER_NOT_FOUND,
  SEARCHING_READER,
  deskStatus,
  exportButtonLabel,
  exportDoneHint,
  exportDoneText,
  exportErrorText,
  listMeaning,
  listPartOfSpeech,
  pickReason,
  type ExportUi,
  type HomeMode,
} from "./home-domain";

export type HomeViewProps = {
  mode: HomeMode;
  /** The short list, in ranking order. */
  words: LexemeRecord[];
  /** «С прошлого раза: N новых слов», or null. */
  sinceLine: string | null;
  /** The grey «order is rough» line, or null. */
  roughNote: string | null;
  demo: boolean;
  exportUi: ExportUi;
  destination: AppSettings["export_destination"];
  openState: OpenResultState;
  folderState: ExportFolderState;
  exportBlocked: boolean;
  /** The reader is being read or new words are being analysed: the list is about to change. */
  listChanging: boolean;
  processingProgress: HomeProcessingProgress | null;
  reader: { state: ConnectorState; name: string };
  onExport: () => void;
  onOpenWord: (id: string) => void;
  onOpenResult: (path: string) => void;
  onOpenFolder: () => void;
  onSync: () => void;
  onImportFile: (file: File) => void;
  onDemo: () => void;
  onExitDemo: () => void;
  onRetryProcessing: () => void;
};

const QUESTION = "Что выгрузить сейчас?";

export function HomeView(props: HomeViewProps) {
  const { mode, demo } = props;
  const processingPhase = props.processingProgress?.phase ?? (mode === "preparing" ? "waiting" : null);
  const phaseAnnouncement = processingPhase === "waiting" ? "Подготовка к обработке…"
    : processingPhase === "processing" ? "Обрабатываю слова…"
      : processingPhase === "finishing" ? "Собираю подборку…" : "";
  const readerConnected = props.reader.state === "connected";
  // A lamp burns only where there is something to do.
  const lit = mode === "list" || mode === "preparing" || mode === "processing-stopped" || (mode === "no-reader" && readerConnected);

  return (
    <main className="reading-page app-scrollbar" aria-busy={mode === "loading" || undefined}>
      <p className="sr-only home-processing-announcement" role="status" aria-live="polite" aria-atomic="true">{phaseAnnouncement}</p>
      <div className={`home-page${mode === "preparing" ? " home-preparing" : ""}`}>
        <section className="home-desk lamp-host" aria-labelledby="home-title">
          <DeskLamp lit={lit} />
          <div className="home-desk-text">
            {mode === "loading" ? <DeskSkeleton /> : null}
            {mode === "no-reader" ? <NoReaderDesk {...props} /> : null}
            {mode !== "loading" && mode !== "no-reader" ? <ListDesk {...props} /> : null}
            {!demo && mode !== "loading" ? <FolderAccess state={props.folderState} disabled={props.openState === "opening-file"} onOpen={props.onOpenFolder} /> : null}
          </div>
          <PencilRule variant={2} className="home-desk-line" />
        </section>

        {mode === "loading" ? <ListSkeleton /> : null}
        {mode === "list" ? <ShortList {...props} /> : null}
        {mode === "no-reader" ? <ReaderPlaces /> : null}
        {mode !== "loading" && mode !== "no-reader" && mode !== "preparing" && !demo ? <ReaderLine {...props} /> : null}
      </div>
    </main>
  );
}

// ---------- the desk ----------

function Title({ preparing = false }: { preparing?: boolean }) {
  return <h1 id="home-title" className="home-title" tabIndex={-1}>{preparing ? "Готовлю подборку" : QUESTION}</h1>;
}

function DeskSkeleton() {
  return (
    <div role="status">
      <span className="sr-only">Открываю библиотеку…</span>
      <p className="home-eyebrow" aria-hidden="true"><span className="home-skel" style={{ width: 210 }} /></p>
      <Title />
      <div className="home-actions" aria-hidden="true"><span className="home-skel home-skel-button" /></div>
    </div>
  );
}

function ListDesk(props: HomeViewProps) {
  const { mode, exportUi, demo, sinceLine, listChanging, words } = props;
  const running = exportUi.kind === "running";
  const savedFileMissing = exportUi.kind === "done" && Boolean(exportUi.run.path) && props.folderState === "missing";
  const showEmpty = mode === "empty" && !demo && (exportUi.kind !== "done" || savedFileMissing) && exportUi.kind !== "error" && !running;
  const unconfirmed = !demo && exportUi.kind === "error" && exportUi.code === "anki_import_unconfirmed";
  const actionLabel = exportUi.kind === "error" ? "Попробовать снова" : exportButtonLabel(words.length);
  return (
    <>
      {mode !== "preparing" ? <p className="home-eyebrow">{demo ? null : sinceLine}</p> : null}
      <Title preparing={mode === "preparing"} />
      {showEmpty ? (
        <>
          <p className="home-answer">{EMPTY_TITLE}</p>
          <p className="home-hand">{EMPTY_NOTE}</p>
        </>
      ) : null}
      {mode === "preparing" ? (
        <div className="home-preparation">
          <p className="home-lede">Слова загружены. Подборка появится здесь, когда закончится обработка.</p>
          <ProcessingProgress progress={props.processingProgress ?? { phase: "waiting" }} />
        </div>
      ) : null}
      {mode === "processing-stopped" ? (
        <>
          <p className="home-answer">Обработка слов остановилась</p>
          <div className="home-actions">
            <PencilButton look="lit" size="lg" disabled={props.exportBlocked} onClick={props.onRetryProcessing}>Продолжить обработку</PencilButton>
          </div>
        </>
      ) : null}
      {(mode === "list" && !unconfirmed) || demo ? (
        <div className="home-actions">
          {demo ? (
            <PencilButton look="lit" size="lg" onClick={props.onExitDemo}>Закрыть пример</PencilButton>
          ) : (
            <PencilButton look="lit" size="lg" loading={running} disabled={listChanging || props.exportBlocked} aria-describedby={props.processingProgress && listChanging ? "home-processing-note" : undefined} onClick={props.onExport}>
              {running ? "Выгружаю…" : <><Upload size={18} strokeWidth={1.8} aria-hidden="true" />{actionLabel}</>}
            </PencilButton>
          )}
        </div>
      ) : null}
      {mode === "list" && !demo && !running && exportUi.kind === "idle" ? (
        <p className="home-export-hint">
          {props.destination === "csv" ? "Слова сохранятся в файл TSV для Quizlet или таблицы."
            : "Если AnkiConnect недоступен, сохранится колода .apkg. Её можно открыть в Anki."}
        </p>
      ) : null}
      <DeskStatusLine {...props} exportUi={savedFileMissing ? { kind: "idle" } : exportUi} />
      {mode === "list" && unconfirmed ? (
        <div className="home-folder">
          <PencilLink disabled={listChanging || props.exportBlocked} onClick={props.onExport}>Отправить снова</PencilLink>
        </div>
      ) : null}
    </>
  );
}

/**
 * The one line under the button, by priority (see `deskStatus`). It stays in the page even when empty,
 * so screen readers announce a change; an empty line is only visually hidden.
 */
function DeskStatusLine({ exportUi, openState, folderState, demo, listChanging, processingProgress, roughNote, mode, onOpenResult }: HomeViewProps) {
  const status = deskStatus({ exportUi: demo ? { kind: "idle" } : exportUi, listChanging: mode === "list" && listChanging && !processingProgress, demo, roughNote: mode === "list" && !processingProgress ? roughNote : null });
  const region = React.useRef<HTMLDivElement>(null);
  const outcome = status?.kind === "done" || status?.kind === "error" ? status.kind : null;
  // When the export button disappears with the list, keep keyboard focus on the result instead of <body>.
  React.useEffect(() => {
    if (outcome && (document.activeElement === document.body || document.activeElement === null)) {
      region.current?.focus({ preventScroll: true });
    }
  }, [outcome]);
  let body: React.ReactNode = null;
  if (status?.kind === "done") {
    const { run } = status;
    const { path } = run;
    const hint = exportDoneHint(run);
    body = (
      <>
        <span className="home-status-line"><Check aria-hidden="true" />{exportDoneText(run)}</span>
        {path && run.destination === "anki" && folderState !== "missing" ? (
          <PencilLink loading={openState === "opening-file"} disabled={folderState === "opening"} onClick={() => onOpenResult(path)}>Открыть в Anki</PencilLink>
        ) : null}
        {openState === "failed-file" && folderState !== "missing" ? <span className="home-status-hint">Колода не открылась. Проверьте файл в папке выгрузок.</span> : null}
        {hint && folderState !== "missing" && openState !== "failed-file" ? <span className="home-status-hint">{hint}</span> : null}
      </>
    );
  } else if (status?.kind === "error") {
    body = (
      <>
        <span className="home-status-line">
          <svg className="home-cross" viewBox="0 0 18 18" aria-hidden="true"><path d="M3.5 3.8 14.2 14.4 M14.4 3.6 3.6 14.5" /></svg>
          {exportErrorText(status.message, status.code)}
        </span>
      </>
    );
  } else if (status?.kind === "note") {
    body = <span className="home-note">{status.text}</span>;
  }
  return (
    <div ref={region} tabIndex={-1} className={`home-status${status?.kind === "error" ? " is-error" : ""}`} role="status" aria-live="polite">
      {body}
    </div>
  );
}

function FolderAccess({ state, disabled, onOpen }: { state: ExportFolderState; disabled: boolean; onOpen: () => void }) {
  const announcement = React.useRef<HTMLParagraphElement>(null);
  const action = React.useRef<HTMLElement | null>(null);
  const restoreFocus = React.useRef(false);
  const bindAction = React.useCallback((node: HTMLElement | null) => {
    // Capture focus before React removes the button. A reader who tabbed away keeps their focus.
    if (!node && action.current === document.activeElement) restoreFocus.current = true;
    action.current = node;
  }, []);
  React.useEffect(() => {
    if (state === "missing" && restoreFocus.current && document.activeElement === document.body) {
      announcement.current?.focus({ preventScroll: true });
    }
    restoreFocus.current = false;
  }, [state]);
  const showAction = state === "ready" || state === "opening" || state === "error";
  const opening = state === "opening";
  const blocked = disabled || opening;
  return (
    <div className="home-folder">
      {showAction ? (
        <PencilLink ref={bindAction} aria-busy={opening || undefined} aria-disabled={blocked || undefined} onClick={() => {
          if (!blocked) onOpen();
        }}>
          {opening ? <Loader2 size={14} aria-hidden="true" className="animate-spin motion-reduce:animate-none" /> : null}
          Открыть папку выгрузок
        </PencilLink>
      ) : null}
      <p ref={announcement} tabIndex={-1} className="home-folder-note" role="status">
        {state === "missing" ? "В папке выгрузок больше нет файлов." : state === "error" ? "Не удалось открыть папку выгрузок." : null}
      </p>
    </div>
  );
}

function NoReaderDesk(props: HomeViewProps) {
  const connected = props.reader.state === "connected";
  const checking = props.reader.state === "unknown" || props.reader.state === "checking";
  return (
    <>
      <p className="home-eyebrow">Здесь пока нет слов</p>
      <Title />
      <p className="home-lede">Сюда придут слова, которые вы искали в словаре читалки. Подключите её по USB или выберите файл со словами.</p>
      <div className="home-actions">
        <PencilButton look="lit" size="lg" onClick={props.onSync} disabled={props.listChanging} loading={props.listChanging}>
          {props.listChanging ? SEARCHING_READER : <><RefreshCw size={17} strokeWidth={1.8} aria-hidden="true" />{LOAD_FROM_READER}</>}
        </PencilButton>
        <ImportFileButton look="pencil" onFile={props.onImportFile} disabled={props.listChanging}>Выбрать файл</ImportFileButton>
        <PencilLink onClick={props.onDemo} disabled={props.listChanging}>Посмотреть на примере</PencilLink>
      </div>
      {!connected && !checking ? (
        <>
          <p className="home-hand">{READER_NOT_FOUND}</p>
          <p className="home-export-hint">Проверьте, что кабель поддерживает передачу данных. Если читалка предлагает режим USB, выберите передачу файлов.</p>
        </>
      ) : null}
    </>
  );
}

// ---------- below the desk ----------

function ShortList({ words, onOpenWord, listChanging, exportUi, processingProgress }: HomeViewProps) {
  return (
    <section className="home-list" aria-labelledby="home-list-title">
      <h2 id="home-list-title" tabIndex={-1}>{LIST_TITLE}</h2>
      {processingProgress ? <div className="home-list-progress">
        <ProcessingProgress progress={processingProgress} />
        {listChanging ? <p id="home-processing-note" className="home-export-hint">Подборка ещё меняется. Открытие карточек и выгрузка станут доступны после обработки.</p> : null}
      </div> : null}
      <ol className="home-rows">
        {words.map((entry, index) => {
          const pos = listPartOfSpeech(entry);
          const meaning = listMeaning(entry);
          const why = pickReason(entry.ranking?.reasons);
          return (
            <li key={entry.id}>
              <PencilRule variant={index} />
              <button
                type="button"
                className="home-row"
                id={`home-word-${entry.id}`}
                aria-label={`Открыть карточку «${entry.lemma}»`}
                aria-describedby={why ? `home-why-${entry.id}` : undefined}
                disabled={listChanging || exportUi.kind === "running"}
                onClick={() => onOpenWord(entry.id)}
              >
                <span className="home-row-text">
                  <strong className="home-lemma">{entry.lemma}</strong>
                  {pos ? <em> {pos}</em> : null}
                  {meaning ? <> — {meaning}</> : null}
                </span>
                {why ? <span className="home-why" id={`home-why-${entry.id}`}>{why}</span> : null}
                <ChevronRight className="home-word-arrow" size={16} aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function ProcessingProgress({ progress }: { progress: HomeProcessingProgress }) {
  if (progress.phase === "processing") {
    const current = progress.current.toLocaleString("ru-RU");
    const total = progress.total.toLocaleString("ru-RU");
    return <div className="home-processing" aria-live="off">
      <p className="home-processing-count">Обработано {current} из {total}</p>
      <progress className="home-processing-bar" aria-label="Обработка слов" aria-valuetext={`Обработано слов ${current} из ${total}`} value={progress.current} max={progress.total} />
    </div>;
  }
  return <div className="home-processing home-processing-waiting" aria-live="off">
    <span className="home-processing-dot" aria-hidden="true" />
    <p>{progress.phase === "finishing" ? "Собираю подборку…" : "Подготовка к обработке…"}</p>
  </div>;
}

function ListSkeleton() {
  const widths = [["34%", "22%"], ["28%", "18%"], ["40%", "24%"], ["30%", "20%"], ["36%", "16%"]];
  return (
    <section className="home-list" aria-hidden="true">
      {widths.map(([a, b], index) => (
        <div key={index}>
          <PencilRule variant={index} />
          <div className="home-skel-row">
            <span className="home-skel" style={{ width: a }} />
            <span className="home-skel" style={{ width: b }} />
          </div>
        </div>
      ))}
    </section>
  );
}

function ReaderPlaces() {
  return (
    <section className="home-places" aria-labelledby="home-places-title">
      <h2 id="home-places-title">Где лежат слова</h2>
      <p className="home-places-lede">Если провода нет, скопируйте нужный файл с читалки и выберите его.</p>
      <ul>
        {READER_LOCATIONS.map((place, index) => (
          <li key={place.reader}>
            {index > 0 ? <PencilRule variant={index} /> : null}
            <strong>{place.reader}</strong> — <code>{place.where}</code>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ReaderLine({ reader, listChanging, onSync, onImportFile }: HomeViewProps) {
  const connected = reader.state === "connected";
  const checking = reader.state === "unknown" || reader.state === "checking";
  return (
    <p className={`home-reader${connected ? " is-connected" : ""}`}>
      <span className="home-reader-line">
        <span className="home-reader-dot" aria-hidden="true" />
        {connected ? `${reader.name} подключён` : checking ? SEARCHING_READER : READER_NOT_FOUND}
      </span>
      {connected ? (
        <PencilLink onClick={onSync} disabled={listChanging}>{LOAD_FROM_READER}</PencilLink>
      ) : (
        <ImportFileButton look="link" onFile={onImportFile} disabled={listChanging}>Выбрать файл со словами</ImportFileButton>
      )}
    </p>
  );
}
