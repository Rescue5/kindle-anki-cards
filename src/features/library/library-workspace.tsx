import * as React from "react";
import { Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ImportFileButton } from "@/components/import-file-button";
import { cn } from "@/lib/utils";
import { filterLexemes } from "./domain";
import { cardDraft, selectedExample, worthLearning } from "./card-editor-domain";
import { CardEditor } from "./card-editor";
import type { useLibraryController } from "./use-library-controller";
import type { LexemeRecord } from "@/types";
import "./library-workspace.css";

type Controller = ReturnType<typeof useLibraryController>;

type Props = { controller: Controller; batchLexemeId?: string; onBackToBatch?: () => void; onDraftChange?: (dirty: boolean, pending: boolean) => void };

export const LibraryWorkspace = React.memo(function LibraryWorkspace({ controller, batchLexemeId, onBackToBatch, onDraftChange }: Props) {
  const [shelf, setShelf] = React.useState("worth");
  const [selectedId, setSelectedId] = React.useState(batchLexemeId ?? "");
  const [inspectorOpen, setInspectorOpen] = React.useState(Boolean(batchLexemeId));
  const [dirty, setDirty] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const headingRef = React.useRef<HTMLHeadingElement>(null);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const focusEditor = React.useRef(Boolean(batchLexemeId));
  const focusRow = React.useRef(false);
  const busy = controller.operation.status === "running";
  const selectedBook = controller.books.find((book) => book.key === controller.selectedBookKey);
  const entries = React.useMemo(() => filterLexemes(controller.entries, controller.query, selectedBook, "all")
    .filter((entry) => worthLearning(entry) === (shelf === "worth"))
    .sort((a, b) => (a.ranking?.rank ?? Infinity) - (b.ranking?.rank ?? Infinity)),
    [controller.entries, controller.query, selectedBook, shelf]);
  // The direct entry is independent of all saved filters. Keep a removed word open to undo its decision.
  const selected = controller.entries.find((entry) => entry.id === selectedId) ?? null;
  React.useEffect(() => { onDraftChange?.(dirty, pending); }, [dirty, pending, onDraftChange]);
  React.useEffect(() => () => { onDraftChange?.(false, false); }, [onDraftChange]);

  React.useEffect(() => {
    if (!batchLexemeId) return;
    setSelectedId(batchLexemeId);
    setInspectorOpen(true);
    focusEditor.current = true;
  }, [batchLexemeId]);
  React.useEffect(() => {
    if (selected && inspectorOpen && focusEditor.current) {
      headingRef.current?.focus();
      focusEditor.current = false;
    }
  }, [selected, inspectorOpen]);
  React.useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  React.useEffect(() => {
    if (inspectorOpen || !focusRow.current) return;
    rootRef.current?.querySelector<HTMLButtonElement>('[data-selected-word="true"]')?.focus();
    focusRow.current = false;
  }, [inspectorOpen]);

  function canLeave() {
    return !dirty || window.confirm("Есть несохранённые правки. Уйти и отменить их?");
  }
  function selectWord(id: string) {
    if (pending) return;
    if (selectedId !== id && !canLeave()) return;
    if (selectedId !== id) setDirty(false);
    setSelectedId(id);
    setInspectorOpen(true);
    focusEditor.current = true;
    window.requestAnimationFrame(() => headingRef.current?.focus());
  }
  function back() {
    if (pending) return;
    if (!canLeave()) return;
    setDirty(false);
    if (batchLexemeId && onBackToBatch) { onBackToBatch(); return; }
    focusRow.current = true;
    setInspectorOpen(false);
  }

  return <div ref={rootRef} className={cn("library-workspace words-screen card-workspace", inspectorOpen && "is-editing")}>
    <main className="words-main">
      <header className="words-head">
        <div className="words-head-top"><h1>Слова</h1></div>
        <div className="words-toolbar">
          <div className="screen-search"><Search size={16} aria-hidden="true" /><Input aria-label="Поиск слова, контекста или книги" placeholder="Слово, контекст, книга" value={controller.query} onChange={(event) => controller.setQuery(event.target.value)} /></div>
          <Select aria-label="Книга" value={controller.selectedBookKey} onChange={(event) => controller.setSelectedBookKey(event.target.value)}>
            {controller.books.map((book) => <option key={book.key || "all"} value={book.key}>{book.label}</option>)}
          </Select>
        </div>
        <div className="words-filters" role="group" aria-label="Отбор слов">
          <div className="words-filter-tabs">{[["worth", "Стоит учить"], ["other", "Остальные"]].map(([value, label]) => <button key={value} type="button" className="words-filter" aria-pressed={shelf === value} onClick={() => setShelf(value)}>{label}</button>)}</div>
        </div>
        <details className="card-library-tools"><summary>Загрузка и обработка</summary>
          <div className="card-edit-actions">
            <Button variant="secondary" size="sm" disabled={busy || controller.demo || controller.connectors.kindle.state !== "connected"} onClick={() => void controller.syncKindle()}>Загрузить с читалки</Button>
            <ImportFileButton disabled={busy || controller.demo} onFile={(file) => void controller.importReaderFile(file)}>Загрузить файл</ImportFileButton>
            {controller.queueStatus.failed > 0 ? <Button variant="secondary" size="sm" disabled={busy || controller.demo} onClick={() => void controller.retryFailed()}>Повторить обработку</Button> : null}
            {controller.settings.llm_enabled && (controller.enrichmentQueue.pending > 0 || controller.enrichmentQueue.failed > 0) ? <Button variant="secondary" size="sm" disabled={busy || controller.demo} onClick={() => void controller.enrichWords({ retryFailed: controller.enrichmentQueue.pending === 0 })}>{controller.enrichmentQueue.pending > 0 ? "Перевести слова" : "Повторить перевод"}</Button> : null}
            {busy ? <Button variant="ghost" size="sm" onClick={() => void controller.cancel()}>Отменить</Button> : null}
          </div>
        </details>
        {controller.operation.status === "error" ? <p role="alert" className="words-error">{controller.operation.error || controller.operation.message}</p> : null}
        {busy ? <p className="words-meta" role="status">{controller.operation.message || "Обработка…"}</p> : null}
        {controller.queueStatus.failed > 0 ? <p className="words-error">Некоторые слова не удалось обработать. Повтор доступен в разделе «Загрузка и обработка».</p> : null}
      </header>
      <WordList entries={entries} selectedId={selectedId} onSelect={selectWord} loading={controller.loading} disabled={pending} />
    </main>
    <aside className="library-inspector words-inspector" aria-label="Карточка слова">
      {inspectorOpen ? <div className={cn("card-back", !batchLexemeId && "card-back-list")}><Button variant="ghost" disabled={pending} onClick={back}>{batchLexemeId ? "К подборке" : "К списку слов"}</Button></div> : null}
      {selected ? <CardEditor key={selected.id} entry={selected} headingRef={headingRef} readOnly={controller.demo} busy={busy}
        llmEnabled={controller.settings.llm_enabled} onEnrich={(id, retryFailed) => void controller.enrichWords({ ids: [id], retryFailed })}
        onSave={controller.saveCardEdit} onDecision={controller.setWordDecision} onDirtyChange={setDirty} onPendingChange={setPending} />
        : <p className="words-state">{batchLexemeId ? "Слово недоступно в библиотеке." : "Выберите слово, чтобы исправить карточку."}</p>}
    </aside>
  </div>;
});

const ROW_HEIGHT = 64;
const OVERSCAN = 5;

function WordList({ entries, selectedId, onSelect, loading, disabled }: { entries: LexemeRecord[]; selectedId: string; onSelect: (id: string) => void; loading: boolean; disabled: boolean }) {
  const [container, setContainer] = React.useState<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [height, setHeight] = React.useState(640);
  React.useEffect(() => {
    if (!container) return;
    const observer = new ResizeObserver(([item]) => setHeight(item.contentRect.height));
    observer.observe(container);
    return () => observer.disconnect();
  }, [container]);
  React.useEffect(() => {
    if (!container) return;
    const index = entries.findIndex((entry) => entry.id === selectedId);
    const top = Math.max(0, index) * ROW_HEIGHT;
    if (top < container.scrollTop || top + ROW_HEIGHT > container.scrollTop + container.clientHeight) container.scrollTop = top;
    setScrollTop(container.scrollTop);
  }, [entries, selectedId, container]);
  if (loading) return <div className="words-state" role="status"><Loader2 className="animate-spin" />Загружаем библиотеку</div>;
  if (!entries.length) return <div className="words-state"><h2>В этой выборке нет слов</h2><p>Измените отбор, книгу или поисковый запрос.</p></div>;
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const end = Math.min(entries.length, Math.ceil((scrollTop + height) / ROW_HEIGHT) + OVERSCAN);
  return <div className="words-table">
    <div className="words-table-head card-list-head"><span>Слово</span><span>Предложение из книги</span></div>
    <div ref={setContainer} className="app-scrollbar words-table-body" onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
      <div style={{ height: start * ROW_HEIGHT }} />
      {entries.slice(start, end).map((entry) => {
        const occurrence = selectedExample(entry, cardDraft(entry).exampleId);
        return <button type="button" disabled={disabled} key={entry.id} data-selected-word={selectedId === entry.id ? "true" : undefined} aria-current={selectedId === entry.id ? "true" : undefined}
          className={cn("words-row card-list-row", selectedId === entry.id && "is-selected")} onClick={() => onSelect(entry.id)}>
          <span className="words-row-lemma"><strong>{entry.lemma}</strong><small>{entry.card?.meaning_ru || ""}</small></span>
          <span className="card-list-example"><span className="words-row-context">{occurrence?.context || "Предложения пока нет"}</span><span className="words-row-book">{occurrence?.book_title || ""}</span></span>
        </button>;
      })}
      <div style={{ height: Math.max(0, entries.length - end) * ROW_HEIGHT }} />
    </div>
  </div>;
}
