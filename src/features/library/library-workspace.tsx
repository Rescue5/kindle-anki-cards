import * as React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowDownWideNarrow, Check, ChevronDown, Download, Loader2, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PencilRule } from "@/components/sketch/sketch";
import { ImportFileButton } from "@/components/import-file-button";
import { ruCount } from "@/features/reading/reading-domain";
import { cn } from "@/lib/utils";
import { cardDraft, selectedExample } from "./card-editor-domain";
import { previewPriorityReason, studyPriority } from "./study-priority";
import { CatalogueFilterDialog, decisionOptions } from "./catalogue-filter-dialog";
import { catalogueGroup, selectCatalogueEntries, selectTranslationEntries, type CatalogueSort } from "./catalogue-selectors";
import type { useCatalogueFilters } from "./use-catalogue-filters";
import { CardEditor } from "./card-editor";
import type { useLibraryController } from "./use-library-controller";
import type { LexemeRecord, StudyPrioritySource } from "@/types";
import "./library-workspace.css";

type Controller = ReturnType<typeof useLibraryController>;

export type CatalogueTranslation = {
  availability: "loading" | "setup" | "ready";
  eligibleIds: ReadonlySet<string>;
  onStart: (ids: readonly string[]) => void;
  onOpenSettings: () => void;
  providerLabel?: string;
  providerKind?: "cloud" | "local";
  perSense?: boolean;
};

type Props = { controller: Controller; catalogueFilters: ReturnType<typeof useCatalogueFilters>; translation: CatalogueTranslation; batchLexemeId?: string; exporting?: boolean; onBackToBatch?: () => void; onDraftChange?: (dirty: boolean, pending: boolean) => void };

const sortOptions: ReadonlyArray<{ value: CatalogueSort; label: string }> = [
  { value: "priority", label: "По приоритету" },
  { value: "added", label: "По дате добавления" },
];

function SortMenu({ sort, onChange }: { sort: CatalogueSort; onChange: (sort: CatalogueSort) => void }) {
  const label = sortOptions.find(({ value }) => value === sort)!.label;
  return <DropdownMenu.Root>
    <DropdownMenu.Trigger asChild>
      <Button variant="ghost" size="sm" className="words-sort-trigger" aria-label={`Сортировка — ${label}`}>
        <ArrowDownWideNarrow size={16} aria-hidden="true" />
        <span>{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </Button>
    </DropdownMenu.Trigger>
    <DropdownMenu.Portal>
      <DropdownMenu.Content className="words-sort-menu" align="end" sideOffset={6} collisionPadding={12}>
        <DropdownMenu.RadioGroup value={sort} onValueChange={(value) => onChange(value as CatalogueSort)}>
          {sortOptions.map(({ value, label }) => <DropdownMenu.RadioItem key={value} value={value} className="words-sort-option">
            <DropdownMenu.ItemIndicator><Check size={15} aria-hidden="true" /></DropdownMenu.ItemIndicator>
            <span>{label}</span>
          </DropdownMenu.RadioItem>)}
        </DropdownMenu.RadioGroup>
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  </DropdownMenu.Root>;
}

export const LibraryWorkspace = React.memo(function LibraryWorkspace({ controller, catalogueFilters, translation, batchLexemeId, exporting, onBackToBatch, onDraftChange }: Props) {
  const { filters, setFilters } = catalogueFilters;
  const [selectedId, setSelectedId] = React.useState(batchLexemeId ?? "");
  const [inspectorOpen, setInspectorOpen] = React.useState(Boolean(batchLexemeId));
  const [dirty, setDirty] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [restoreFocus, setRestoreFocus] = React.useState(false);
  const headingRef = React.useRef<HTMLHeadingElement>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);
  const filterRef = React.useRef<HTMLButtonElement>(null);
  const focusEditor = React.useRef(Boolean(batchLexemeId));
  const operating = controller.operation.status === "running";
  const busy = operating || Boolean(exporting);
  const selectedBook = controller.books.find((book) => book.key === controller.selectedBookKey);
  const prioritySource = controller.ranking?.studyPrioritySource;
  const showFullCoverage = controller.settings.show_full_book_coverage === true;
  const browseKey = JSON.stringify([controller.query.trim(), selectedBook?.key, filters.levels, filters.decision, filters.recent, filters.sort, showFullCoverage]);
  const entries = React.useMemo(() => selectCatalogueEntries(controller.entries, controller.query, selectedBook, filters, prioritySource, showFullCoverage),
    [controller.entries, controller.query, selectedBook, filters, prioritySource, showFullCoverage]);
  const candidates = React.useMemo(() => selectTranslationEntries(entries, translation.eligibleIds), [entries, translation.eligibleIds]);
  const activeFilters = [
    filters.levels.length ? { key: "levels", label: `Приоритеты ${filters.levels.join(", ")}`, remove: () => setFilters({ ...filters, levels: [] }) } : null,
    selectedBook?.key ? { key: "book", label: selectedBook.label, remove: () => controller.setSelectedBookKey("") } : null,
    filters.recent ? { key: "recent", label: "Последнее пополнение", remove: () => setFilters({ ...filters, recent: false }) } : null,
    filters.decision !== "visible" ? { key: "decision", label: decisionOptions.find(({ value }) => value === filters.decision)!.label,
      remove: () => setFilters({ ...filters, decision: "visible" }) } : null,
  ];
  const translationSummary = [
    controller.query.trim() ? `Поиск: «${controller.query.trim()}»` : "",
    ...activeFilters.map((filter) => filter?.label),
    filters.decision === "visible" ? "«Не учить» скрыты" : "",
  ].filter(Boolean).join(" · ");
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
    if (inspectorOpen || !restoreFocus || entries.some((entry) => entry.id === selectedId)) return;
    searchRef.current?.focus();
    setRestoreFocus(false);
  }, [inspectorOpen, restoreFocus, entries, selectedId]);

  function canLeave() {
    return !dirty || window.confirm("Есть несохранённые правки. Уйти и отменить их?");
  }
  function selectWord(id: string) {
    if (pending) return;
    if (selectedId !== id && !canLeave()) return;
    if (selectedId !== id) setDirty(false);
    setRestoreFocus(false);
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
    setRestoreFocus(true);
    setInspectorOpen(false);
  }

  return <div className={cn("library-workspace words-screen card-workspace", inspectorOpen && "is-editing")}>
    <main className="words-main">
      <header className="words-head">
        <div className="words-head-top"><h1>Слова</h1>
          <TranslationControl translation={translation} entries={candidates} summary={translationSummary} blocked={busy || pending || controller.loading || controller.demo}
            onFocusFallback={() => searchRef.current?.focus()} />
        </div>
        <div className="words-catalogue-toolbar">
          <div className="screen-search"><Search size={16} aria-hidden="true" /><Input ref={searchRef} id="library-search" aria-label="Поиск слова, контекста или книги" placeholder="Найти слово" value={controller.query} onChange={(event) => controller.setQuery(event.target.value)} /></div>
          <div className="words-catalogue-actions">
            <SortMenu sort={filters.sort} onChange={(sort) => setFilters({ ...filters, sort })} />
            <CatalogueFilterDialog filters={filters} books={controller.books} bookKey={controller.selectedBookKey}
              triggerRef={filterRef} onApply={(next, bookKey) => {
                setFilters(next);
                controller.setSelectedBookKey(bookKey);
              }} />
          </div>
        </div>
        <div className="words-active-filters" aria-label="Текущий отбор" role="group">
          {activeFilters.map((filter) => filter && <button key={filter.key} type="button" className="words-active-filter"
            data-filter={filter.key} aria-label={`Снять фильтр «${filter.label}»`} title={filter.label} onClick={() => {
              filterRef.current?.focus();
              filter.remove();
            }}>
            <span>{filter.label}</span><X size={14} aria-hidden="true" />
          </button>)}
          {filters.decision === "visible" ? <div className="words-default-filter">
            <span>«Не учить» скрыты</span>
            <button type="button" onClick={() => {
              filterRef.current?.focus();
              setFilters({ ...filters, decision: "all" });
            }}>Показать все решения</button>
          </div> : null}
        </div>
      </header>
      <WordList entries={entries} browseKey={browseKey} groupByPriority={filters.sort === "priority"} prioritySource={prioritySource} selectedId={selectedId}
        revealSelection={inspectorOpen || restoreFocus} onSelect={selectWord} loading={controller.loading} disabled={pending}
        restoreFocus={restoreFocus && !inspectorOpen} onFocusRestored={() => setRestoreFocus(false)} />
      <footer className="words-library-activity">
        <PencilRule />
        {controller.operation.status === "error" ? <p role="alert" className="words-error">{controller.operation.error || controller.operation.message}</p> : null}
        {controller.queueStatus.failed > 0 ? <p className="words-error">Некоторые слова не удалось обработать. Повтор доступен в разделе «Загрузка и обработка».</p> : null}
        <details className="card-library-tools"><summary>
          <Download size={16} aria-hidden="true" />
          <span>Загрузка и обработка</span><ChevronDown size={14} aria-hidden="true" />
        </summary>
          <div className="card-edit-actions">
            <Button variant="secondary" size="sm" disabled={busy || controller.demo || controller.connectors.kindle.state !== "connected"} onClick={() => void controller.syncKindle()}>Загрузить с читалки</Button>
            <ImportFileButton disabled={busy || controller.demo} onFile={(file) => void controller.importReaderFile(file)}>Загрузить файл</ImportFileButton>
            {controller.queueStatus.failed > 0 ? <Button variant="secondary" size="sm" disabled={busy || controller.demo} onClick={() => void controller.retryFailed()}>Повторить обработку</Button> : null}
            {operating ? <Button variant="ghost" size="sm" onClick={() => void controller.cancel()}>Отменить</Button> : null}
          </div>
        </details>
      </footer>
    </main>
    <aside className="library-inspector words-inspector" aria-label="Карточка слова">
      {inspectorOpen ? <div className={cn("card-back", !batchLexemeId && "card-back-list")}><Button variant="ghost" disabled={pending} onClick={back}>{batchLexemeId ? "К подборке" : "К списку слов"}</Button></div> : null}
      {selected ? <CardEditor key={selected.id} entry={selected} prioritySource={prioritySource} headingRef={headingRef} readOnly={controller.demo} busy={busy}
        llmEnabled={translation.availability === "ready"} onEnrich={(id, mode) => void controller.enrichWords({ ids: [id], retryFailed: mode === "retry", recheck: mode === "recheck" })}
        onSave={controller.saveCardEdit} onDecision={controller.setWordDecision} onDirtyChange={setDirty} onPendingChange={setPending} />
        : <p className="words-state">{batchLexemeId ? "Слово недоступно в библиотеке." : "Выберите слово, чтобы исправить карточку."}</p>}
    </aside>
  </div>;
});

function TranslationControl({ translation, entries, summary, blocked, onFocusFallback }: {
  translation: CatalogueTranslation;
  entries: readonly LexemeRecord[];
  summary: string;
  blocked: boolean;
  onFocusFallback: () => void;
}) {
  const [preview, setPreview] = React.useState<{ entries: readonly LexemeRecord[]; summary: string; provider: string; kind: CatalogueTranslation["providerKind"]; perSense: boolean } | null>(null);
  const noEntriesId = React.useId();
  const trigger = React.useRef<HTMLButtonElement>(null);
  const provider = translation.providerLabel || (translation.providerKind === "local" ? "локальная модель" : "выбранная модель");
  const current = translation.availability === "ready" && preview?.provider === provider && preview.summary === summary
    && preview.kind === translation.providerKind && preview.perSense === Boolean(translation.perSense)
    && preview.entries.length === entries.length && preview.entries.every((entry, index) => entry.id === entries[index].id);
  const count = preview?.entries.length ?? 0;

  if (translation.availability === "setup" && !preview) {
    return <Button id="library-translate" variant="secondary" size="sm" disabled={blocked} onClick={translation.onOpenSettings}>Настроить перевод с ИИ</Button>;
  }

  return <div className="words-translation">
    <Dialog.Root open={preview !== null} onOpenChange={(open) => setPreview(open
      ? { entries, summary, provider, kind: translation.providerKind, perSense: Boolean(translation.perSense) }
      : null)}>
      <Dialog.Trigger asChild>
        <Button ref={trigger} id="library-translate" variant="default" size="sm" disabled={blocked || translation.availability !== "ready" || !entries.length}
          aria-describedby={!entries.length && translation.availability === "ready" ? noEntriesId : undefined}>
          {translation.availability === "loading" ? "Проверяю настройку ИИ…" : `Перевести с ИИ · ${entries.length.toLocaleString("ru-RU")}`}
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="words-translation-overlay" />
        <Dialog.Content className="words-translation-dialog" onCloseAutoFocus={(event) => {
          if (trigger.current && !trigger.current.disabled) return;
          event.preventDefault();
          onFocusFallback();
        }}>
          <Dialog.Title>Перевести с ИИ?</Dialog.Title>
          <Dialog.Description>
            Подходящих слов в выбранном списке: {count.toLocaleString("ru-RU")}. Модель: {preview?.provider}.
          </Dialog.Description>
          <p className="words-translation-summary">{preview?.summary}</p>
          <p>{preview?.kind === "local" ? "Запрос получит локальная модель." : "Запрос получит выбранный провайдер."} В нём будут форма слова, лемма, часть речи, номер в запросе, текущий перевод и до 400 символов выбранной цитаты.</p>
          {preview?.perSense ? <p>ИИ также предложит примеры для каждого значения.</p> : null}
          <ol className="words-translation-preview app-scrollbar" aria-label="Слова для перевода" tabIndex={0}>
            {preview?.entries.map((entry) => <li key={entry.id}>{entry.display_form || entry.lemma}</li>)}
          </ol>
          {!current ? <p role="status">Подборка или настройки изменились. Откройте подтверждение заново.</p> : null}
          <div className="words-translation-actions">
            <Dialog.Close asChild><Button variant="ghost" size="sm">Отмена</Button></Dialog.Close>
            <Button variant="default" size="sm" disabled={!current || blocked || !count} onClick={() => {
              if (!preview?.entries.length || !current || blocked) return;
              translation.onStart(preview.entries.map(({ id }) => id));
              setPreview(null);
            }}>Перевести {count.toLocaleString("ru-RU")} {ruCount(count, "слово", "слова", "слов")}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    {!entries.length && translation.availability === "ready" ? <p id={noEntriesId}>В этой выборке нет слов для перевода</p> : null}
  </div>;
}

const ROW_HEIGHT = 92;
const GROUP_HEIGHT = 38;
const OVERSCAN = 5;

type CatalogueRow = { offset: number; height: number } & ({ kind: "word"; entry: LexemeRecord } | { kind: "group"; label: string });

function catalogueRows(entries: readonly LexemeRecord[], group: boolean, source?: StudyPrioritySource) {
  const rows: CatalogueRow[] = [];
  const wordRows = new Map<string, CatalogueRow>();
  let offset = 0;
  let previous = "";
  for (const entry of entries) {
    if (group) {
      const label = catalogueGroup(entry, source);
      if (label !== previous) {
        rows.push({ kind: "group", label, offset, height: GROUP_HEIGHT });
        offset += GROUP_HEIGHT;
        previous = label;
      }
    }
    const row = { kind: "word", entry, offset, height: ROW_HEIGHT } as const;
    rows.push(row);
    wordRows.set(entry.id, row);
    offset += ROW_HEIGHT;
  }
  return { rows, wordRows, totalHeight: offset };
}

function firstRowAt(rows: readonly CatalogueRow[], offset: number) {
  let start = 0;
  let end = rows.length;
  while (start < end) {
    const middle = Math.floor((start + end) / 2);
    const row = rows[middle];
    if (row.offset + row.height <= offset) start = middle + 1;
    else end = middle;
  }
  return start;
}

function WordList({ entries, browseKey, groupByPriority, prioritySource, revealSelection, selectedId, onSelect, loading, disabled, restoreFocus, onFocusRestored }: {
  entries: LexemeRecord[]; browseKey: string; groupByPriority: boolean; prioritySource?: StudyPrioritySource; revealSelection: boolean; selectedId: string;
  onSelect: (id: string) => void; loading: boolean; disabled: boolean; restoreFocus: boolean; onFocusRestored: () => void;
}) {
  const [container, setContainer] = React.useState<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [height, setHeight] = React.useState(640);
  const previousBrowseKey = React.useRef(browseKey);
  const layout = React.useMemo(() => catalogueRows(entries, groupByPriority, prioritySource), [entries, groupByPriority, prioritySource]);
  React.useEffect(() => {
    if (!container) return;
    const observer = new ResizeObserver(([item]) => setHeight(item.contentRect.height));
    observer.observe(container);
    return () => observer.disconnect();
  }, [container]);
  React.useEffect(() => {
    if (!container) return;
    const browseChanged = previousBrowseKey.current !== browseKey;
    previousBrowseKey.current = browseKey;
    if (browseChanged) container.scrollTop = 0;
    const selected = revealSelection && (!browseChanged || restoreFocus) ? layout.wordRows.get(selectedId) : undefined;
    if (selected && (selected.offset < container.scrollTop || selected.offset + selected.height > container.scrollTop + container.clientHeight)) {
      container.scrollTop = selected.offset;
    }
    setScrollTop(container.scrollTop);
  }, [browseKey, layout, selectedId, container, revealSelection, restoreFocus]);
  React.useEffect(() => {
    if (!restoreFocus || !container || height === 0) return;
    const frame = window.requestAnimationFrame(() => {
      // The narrow layout has just unhidden the list. Wait until its rows can receive focus.
      const row = container.querySelector<HTMLButtonElement>('[data-selected-word="true"]');
      if (row && row.getClientRects().length) {
        row.focus({ preventScroll: true });
        if (document.activeElement === row) onFocusRestored();
        return;
      }
      const selected = layout.wordRows.get(selectedId);
      if (selected) {
        container.scrollTop = selected.offset;
        setScrollTop(container.scrollTop);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [restoreFocus, container, height, scrollTop, selectedId, layout, onFocusRestored]);
  if (loading) return <div className="words-state" role="status"><Loader2 className="animate-spin" />Загружаем библиотеку</div>;
  if (!entries.length) return <div className="words-state"><h2>В этой выборке нет слов</h2><p>Измените отбор, книгу или поисковый запрос.</p></div>;
  const { rows, totalHeight } = layout;
  const start = Math.max(0, firstRowAt(rows, scrollTop) - OVERSCAN);
  const end = Math.min(rows.length, firstRowAt(rows, scrollTop + height) + OVERSCAN);
  return <div className="words-table" style={{ "--catalog-row-height": `${ROW_HEIGHT}px` } as React.CSSProperties}>
    <div className="words-table-head card-list-head"><span>Слово</span><span>Предложение из книги</span><span>Приоритет</span></div>
    <div ref={setContainer} className="app-scrollbar words-table-body" onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
      <div style={{ height: rows[start]?.offset ?? totalHeight }} />
      {rows.slice(start, end).map((row) => {
        if (row.kind === "group") return <h2 className="words-priority-group" key={`group-${row.label}`} style={{ height: row.height }}>{row.label}</h2>;
        const { entry } = row;
        const occurrence = selectedExample(entry, cardDraft(entry).exampleId);
        const priority = studyPriority(entry);
        return <button type="button" disabled={disabled} key={entry.id} data-selected-word={selectedId === entry.id ? "true" : undefined} aria-current={selectedId === entry.id ? "true" : undefined}
          className={cn("words-row card-list-row", selectedId === entry.id && "is-selected")} onClick={() => onSelect(entry.id)}>
          <span className="words-row-lemma"><strong>{entry.lemma}</strong><small>{entry.card?.meaning_ru || ""}</small></span>
          <span className="card-list-example"><span className="words-row-context">{occurrence?.context || "Предложения пока нет"}</span><span className="words-row-book">{occurrence?.book_title || ""}</span></span>
          <span className="words-row-priority"><strong>Приоритет {priority.level}</strong>{priority.provisional ? <small>предварительно</small> : null}</span>
          <span className="words-row-reason">{previewPriorityReason(priority)}</span>
        </button>;
      })}
      <div style={{ height: totalHeight - (rows[end]?.offset ?? totalHeight) }} />
    </div>
  </div>;
}
