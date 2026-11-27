import * as React from "react";
import { Check, ChevronRight, Loader2, RefreshCw, Upload } from "lucide-react";
import type { AppSettings, ConnectorState, ExportRun, LexemeRecord, StudyPrioritySource } from "@/types";
import { isRpV2Priority, previewPriorityReason, studyPriority } from "@/features/library/study-priority";
import type { ExportFolderState, OpenResultState } from "./use-home-export";
import type { HomeProcessingProgress } from "./home-domain";
import { FoxLantern } from "@/components/light/fox-lantern";
import { PencilRule } from "@/components/sketch/sketch";
import { PencilButton, PencilLink } from "@/components/ui/pencil-controls";
import { Select } from "@/components/ui/select";
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
  PRIORITY_LEVELS,
  wordsLabel,
  type ExportSelection,
  type ExportUi,
  type HomeMode,
} from "./home-domain";

type Quantity = {
  mode: ExportSelection; limit: string; levels: number[]; count: number; available: number; levelCounts: number[];
  setMode: (mode: ExportSelection) => void; setLimit: (value: string) => void; setLevels: (levels: number[]) => void;
};

export type HomeViewProps = {
  mode: HomeMode;
  deskLamp?: React.ReactNode;
  mascotMotion?: boolean;
  /** The short list, in ranking order. */
  words: LexemeRecord[];
  prioritySource?: StudyPrioritySource;
  quantity?: Quantity;
  onOpenLibrary?: () => void;
  onFindReader?: () => void;
  findingReader?: boolean;
  quiet?: boolean;
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
  reader?: { state: ConnectorState; name: string };
  onExport: () => void;
  onOpenWord: (id: string) => void;
  onOpenResult: (run: ExportRun) => void;
  vaultPathError?: string | null;
  onOpenSettings?: () => void;
  onOpenFolder: () => void;
  onSync: () => void;
  onImportFile: (file: File) => void;
  onDemo: () => void;
  onExitDemo: () => void;
  onRetryProcessing: () => void;
};

const QUESTION = "Выгрузка слов";

export function HomeView(props: HomeViewProps) {
  const { mode, demo } = props;
  const processingPhase = props.processingProgress?.phase ?? (mode === "preparing" ? "waiting" : null);
  const phaseAnnouncement = processingPhase === "waiting" ? "Подготовка к обработке…"
    : processingPhase === "processing" ? "Обрабатываю слова…"
      : processingPhase === "finishing" ? "Собираю подборку…" : "";

  return (
    <main className="reading-page app-scrollbar" aria-busy={mode === "loading" || undefined}>
      <p className="sr-only home-processing-announcement" role="status" aria-live="polite" aria-atomic="true">{phaseAnnouncement}</p>
      <div className={`home-page${mode === "preparing" ? " home-preparing" : ""}`}>
        <section className="home-desk lamp-host" aria-labelledby="home-title">
          {props.deskLamp ?? <FoxLantern motion={props.mascotMotion} quiet={props.quiet || props.findingReader || props.exportUi.kind === "running" || props.exportUi.kind === "error"} />}
          <div className="home-desk-text">
            {mode === "loading" ? <DeskSkeleton /> : null}
            {mode === "no-reader" ? <NoReaderDesk {...props} /> : null}
            {mode !== "loading" && mode !== "no-reader" ? <ListDesk {...props} /> : null}
            {!demo && mode !== "loading" ? <FolderAccess state={props.folderState} disabled={props.openState === "opening-file"} onOpen={props.onOpenFolder} /> : null}
          </div>
          <PencilRule variant={2} className="home-desk-line" />
        </section>

        {mode === "loading" ? <ListSkeleton /> : null}
        {mode !== "loading" && mode !== "no-reader" && mode !== "preparing" && !demo ? <ReaderLine {...props} /> : null}
        {mode === "list" || mode === "processing-stopped" && props.quantity?.count ? <ShortList {...props} /> : null}
        {mode === "no-reader" ? <ReaderPlaces /> : null}
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
  const savedFileMissing = exportUi.kind === "done" && exportUi.run.destination !== "obsidian" && Boolean(exportUi.run.path) && props.folderState === "missing";
  const showEmpty = mode === "empty" && !demo && (exportUi.kind !== "done" || savedFileMissing) && exportUi.kind !== "error" && !running;
  const unconfirmed = !demo && exportUi.kind === "error" && exportUi.code === "anki_import_unconfirmed";
  const count = props.quantity?.count ?? words.length;
  const actionLabel = exportUi.kind === "error" ? "Попробовать снова" : exportButtonLabel(count, props.destination);
  const showControls = mode === "list" || mode === "processing-stopped" && Boolean(props.quantity);
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
      {showControls && props.quantity && !demo ? <ExportControls quantity={props.quantity} disabled={running || props.exportBlocked} /> : null}
      {(showControls && !unconfirmed) || demo ? (
        <div className="home-actions">
          {demo ? (
            <PencilButton look="lit" size="lg" onClick={props.onExitDemo}>Закрыть пример</PencilButton>
          ) : props.vaultPathError ? (
            <PencilButton look="lit" size="lg" onClick={props.onOpenSettings} aria-describedby="home-vault-error">Настроить Obsidian</PencilButton>
          ) : (
            <PencilButton look="lit" size="lg" loading={running} disabled={listChanging || running || props.exportBlocked || !count}
              aria-describedby={props.processingProgress && listChanging ? "home-processing-note" : undefined} onClick={props.onExport}>
              {running ? "Выгружаю…" : <><Upload size={18} strokeWidth={1.8} aria-hidden="true" />{actionLabel}</>}
            </PencilButton>
          )}
        </div>
      ) : null}
      {showControls && !demo && props.vaultPathError ? (
        <p id="home-vault-error" className="home-export-hint">{props.vaultPathError}</p>
      ) : mode === "list" && !demo && !running && exportUi.kind === "idle" ? (
        <p className="home-export-hint">
          {props.destination === "csv" ? "Подробная таблица со словами, переводами и примерами."
            : props.destination === "quizlet" ? "Текстовый файл для импорта в Quizlet."
            : props.destination === "remnote" ? "Текстовый файл для вставки в RemNote."
            : props.destination === "obsidian" ? "Карточки сохранятся в папке внутри хранилища."
            : props.quantity?.mode === "library"
              ? "При повторной выгрузке перевод и пример могут заменить ваши правки в Anki. Если Anki закрыт, сохранится колода .apkg."
              : "В Anki или в файл колоды, если Anki закрыт."}
        </p>
      ) : null}
      <DeskStatusLine {...props} exportUi={savedFileMissing ? { kind: "idle" } : exportUi} />
      {showControls && unconfirmed ? (
        <div className="home-folder">
          <PencilLink disabled={!count || listChanging || props.exportBlocked} onClick={props.onExport}>Отправить снова</PencilLink>
        </div>
      ) : null}
    </>
  );
}

function ExportControls({ quantity: q, disabled }: { quantity: Quantity; disabled: boolean }) {
  return <fieldset className="home-export-choice" disabled={disabled}>
    <legend>Что выгрузить</legend>
    <Select aria-label="Состав выгрузки" value={q.mode} onChange={(event) => q.setMode(event.target.value as ExportSelection)}>
      <option value="library">Вся библиотека</option>
      <option value="new">Все новые для изучения</option>
      <option value="portion">Порция новых слов</option>
    </Select>
    {q.mode === "library" ? <>
      <details className="home-priorities">
        <summary>{q.levels.length === 10 ? "Все приоритеты · 1–10" : `Приоритетов выбрано: ${q.levels.length} из 10`}</summary>
        <fieldset className="home-levels"><legend className="sr-only">Включить приоритеты</legend>
          {PRIORITY_LEVELS.map((level) => <label key={level} title={wordsLabel(q.levelCounts[level - 1])}>
            <input type="checkbox" checked={q.levels.includes(level)} aria-label={`Приоритет ${level}`}
              onChange={(event) => q.setLevels(event.target.checked ? [...q.levels, level].sort((a, b) => a - b) : q.levels.filter((value) => value !== level))} />
            {level}
          </label>)}
        </fieldset>
      </details>
      <p className="home-selection-note">{q.count ? "Включая отложенные и ранее выгруженные слова." : q.levels.length ? "Слов с выбранным приоритетом пока нет." : "Выберите хотя бы один приоритет."}</p>
    </> : <>
      {q.mode === "portion" ? <label className="home-portion">До <input type="number" min="1" step="1" value={q.limit}
        aria-label="Размер порции" onChange={(event) => q.setLimit(event.target.value)} /> слов</label> : null}
      <p className="home-selection-note">{q.available ? `Доступно для изучения: ${wordsLabel(q.available)}. Уже выгруженные слова пропускаются.` : "Новых слов для изучения пока нет."}</p>
    </>}
  </fieldset>;
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
    const obsidian = run.destination === "obsidian";
    const canOpen = Boolean(path) && (obsidian || folderState !== "missing");
    const openLabel = obsidian ? "Открыть папку карточек" : run.destination === "anki" ? "Открыть в Anki" : "Открыть файл";
    body = (
      <>
        <span className="home-status-line">{run.exported > 0 ? <Check aria-hidden="true" /> : null}{exportDoneText(run)}</span>
        {canOpen ? (
          <PencilLink loading={openState === "opening-file"} disabled={folderState === "opening"} onClick={() => onOpenResult(run)}>{openLabel}</PencilLink>
        ) : null}
        {openState === "failed-file" && canOpen ? <span className="home-status-hint">{obsidian ? "Не удалось открыть папку карточек." : run.destination === "anki" ? "Колода не открылась. Проверьте файл в папке выгрузок." : "Не удалось открыть файл. Проверьте папку выгрузок."}</span> : null}
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
  const connected = props.reader?.state === "connected";
  const checking = props.findingReader || props.reader?.state === "unknown" || props.reader?.state === "checking";
  return (
    <>
      <p className="home-eyebrow">Здесь пока нет слов</p>
      <Title />
      <p className="home-lede">Сюда придут слова, которые вы искали в словаре читалки. Подключите её по USB или выберите файл со словами.</p>
      <div className="home-actions">
        <PencilButton look="lit" size="lg" onClick={connected ? props.onSync : props.onFindReader} disabled={props.listChanging || props.findingReader} loading={props.listChanging || props.findingReader}>
          {props.findingReader ? SEARCHING_READER : <><RefreshCw size={17} strokeWidth={1.8} aria-hidden="true" />{connected ? LOAD_FROM_READER : "Найти Kindle"}</>}
        </PencilButton>
        <ImportFileButton look="pencil" onFile={props.onImportFile} disabled={props.listChanging}>Выбрать файл</ImportFileButton>
        <PencilLink onClick={props.onDemo} disabled={props.listChanging}>Посмотреть на примере</PencilLink>
      </div>
      {!connected && !checking ? (
        <>
          <p className="home-hand" role="status">{props.reader?.state === "error" ? "Не удалось проверить подключение читалки." : READER_NOT_FOUND}</p>
          <p className="home-export-hint">Проверьте, что кабель поддерживает передачу данных. Если читалка предлагает режим USB, выберите передачу файлов.</p>
        </>
      ) : null}
    </>
  );
}

// ---------- below the desk ----------

function ShortList({ words, prioritySource, quantity, onOpenWord, onOpenLibrary, listChanging, exportUi, processingProgress }: HomeViewProps) {
  return (
    <section className="home-list" aria-labelledby="home-list-title">
      <div className="home-preview-heading">
        <h2 id="home-list-title" tabIndex={-1}>{LIST_TITLE}</h2>
        {onOpenLibrary ? <PencilLink onClick={onOpenLibrary}>Открыть библиотеку</PencilLink> : null}
      </div>
      {quantity && quantity.count > words.length ? <p className="home-selection-note">Первые {words.length} из {quantity.count.toLocaleString("ru-RU")}</p> : null}
      {processingProgress ? <div className="home-list-progress">
        <ProcessingProgress progress={processingProgress} />
        {listChanging ? <p id="home-processing-note" className="home-export-hint">Подборка ещё меняется. Открытие карточек и выгрузка станут доступны после обработки.</p> : null}
      </div> : null}
      <ol className="home-rows">
        {words.map((entry, index) => {
          const pos = listPartOfSpeech(entry);
          const meaning = listMeaning(entry);
          const why = isRpV2Priority(prioritySource)
            ? previewPriorityReason(studyPriority(entry))
            : entry.study_priority?.reason ?? pickReason(entry.ranking?.reasons);
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

function ReaderLine({ reader, findingReader, listChanging, exportBlocked, exportUi, onFindReader, onSync, onImportFile }: HomeViewProps) {
  if (!reader) return null;
  const connected = reader.state === "connected";
  const checking = findingReader || reader.state === "unknown" || reader.state === "checking";
  const blocked = listChanging || exportBlocked || exportUi.kind === "running" || findingReader;
  return (
    <p className={`home-reader${connected ? " is-connected" : ""}`}>
      <span className="home-reader-line" role="status">
        <span className="home-reader-dot" aria-hidden="true" />
        {checking ? SEARCHING_READER : connected ? `${reader.name} подключён` : reader.state === "error" ? "Не удалось проверить подключение" : READER_NOT_FOUND}
      </span>
      {connected ? (
        <PencilLink onClick={onSync} disabled={blocked}>{LOAD_FROM_READER}</PencilLink>
      ) : null}
      {onFindReader ? <PencilLink onClick={onFindReader} disabled={blocked}>Найти Kindle</PencilLink> : null}
      {!connected ? <ImportFileButton look="link" onFile={onImportFile} disabled={blocked}>Выбрать файл со словами</ImportFileButton> : null}
    </p>
  );
}
