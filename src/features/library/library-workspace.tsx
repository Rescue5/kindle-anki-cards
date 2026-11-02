import * as React from "react";
import {
  AlertCircle,
  BookOpen,
  Check,
  Circle,
  CloudOff,
  Database,
  Download,
  HardDrive,
  Languages,
  Layers3,
  Loader2,
  RefreshCw,
  Search,
  Square,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ClipLamp } from "@/components/light/light";
import { Flourish, PencilFrame, PencilRule } from "@/components/sketch/sketch";
import { cn } from "@/lib/utils";
import { counts, isAcceptedNew, isCardEligible, obsidianSyncReason, partOfSpeechLabel, primaryOccurrence, processingLabel, processingTone, russianMeaning, type QuickFilter } from "./domain";
import type { useLibraryController } from "./use-library-controller";
import type { ConnectorInfo, LexemeRecord, WordAnalysis } from "@/types";

type Controller = ReturnType<typeof useLibraryController>;

export const LibraryWorkspace = React.memo(function LibraryWorkspace({ controller }: { controller: Controller }) {
  const [exportFormat, setExportFormat] = React.useState<"anki" | "quizlet">(controller.settings.default_export_format);
  React.useEffect(() => setExportFormat(controller.settings.default_export_format), [controller.settings.default_export_format]);
  const totals = React.useMemo(() => counts(controller.entries), [controller.entries]);
  const busy = controller.operation.status === "running";
  const obsidianEnabled = controller.settings.obsidian_sync_enabled;
  const inspectorRef = React.useRef<HTMLElement>(null);
  const selectWord = React.useCallback((id: string) => {
    controller.setSelectedId(id);
    if (window.matchMedia("(max-width: 600px)").matches) {
      window.requestAnimationFrame(() => inspectorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }, [controller.setSelectedId]);

  return (
    <div className="library-workspace words-screen">
      <main className="words-main">
        <header className="words-head">
          <div className="words-head-top">
            <div>
              <h1>Слова</h1>
              <p className="page-head-lede">Слова и контексты из ваших книг</p>
            </div>
            <div className="words-head-tools">
              {busy ? (
                <Button variant="secondary" size="sm" onClick={() => void controller.cancel()}>
                  <Square size={13} /> Отменить
                </Button>
              ) : null}
              <ConnectorButton kind="kindle" info={controller.connectors.kindle} onClick={() => void controller.syncKindle()} disabled={busy || controller.connectors.kindle.state !== "connected"} />
              {obsidianEnabled ? (
                <ConnectorButton kind="obsidian" info={controller.connectors.obsidian} onClick={() => void controller.syncObsidian()} disabled={busy || controller.connectors.obsidian.state !== "connected"} />
              ) : null}
              {controller.settings.llm_enabled && !busy && (controller.enrichmentQueue.pending > 0 || controller.enrichmentQueue.failed > 0) ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void controller.enrichWords({ retryFailed: controller.enrichmentQueue.pending === 0 })}
                  title={controller.enrichmentQueue.pending > 0 ? "Перевести слова без перевода через выбранного провайдера ИИ" : "Повторить перевод слов, для которых он не удался"}
                >
                  <Languages size={15} />
                  {controller.enrichmentQueue.pending > 0 ? "Перевести" : "Повторить перевод"}
                  <span className="words-count">{controller.enrichmentQueue.pending || controller.enrichmentQueue.failed}</span>
                </Button>
              ) : controller.operation.kind === "enrich" && busy ? (
                <span className="words-activity">
                  <Loader2 size={14} className="animate-spin" />
                  {controller.operation.total ? `Перевод ${controller.operation.current}/${controller.operation.total}` : "Перевод"}
                </span>
              ) : null}
              {controller.queueStatus.failed > 0 && !busy ? (
                <Button variant="destructive" size="sm" onClick={() => void controller.retryFailed()} title="Повторить offline-обработку лемм, завершившихся ошибкой">
                  <AlertCircle size={14} />
                  Ошибки: {controller.queueStatus.failed}
                  <RefreshCw size={13} />
                </Button>
              ) : controller.queueStatus.total > 0 ? (
                <span className="words-activity" title="Автоматическая очередь offline-обработки">
                  {controller.operation.kind === "processing" && busy ? <Loader2 size={14} className="animate-spin" /> : <Layers3 size={14} />}
                  В очереди: {controller.queueStatus.total}
                </span>
              ) : null}
            </div>
          </div>

          <div className="library-workspace-toolbar words-toolbar">
            <div className="screen-search">
              <Search size={16} strokeWidth={1.7} aria-hidden="true" />
              <Input aria-label="Поиск слова, контекста или книги" value={controller.query} onChange={(event) => controller.setQuery(event.target.value)} placeholder="Слово, контекст, книга" />
            </div>
            <Select value={controller.selectedBookKey} onChange={(event) => controller.setSelectedBookKey(event.target.value)} aria-label="Книга">
              {controller.books.map((book) => <option key={book.key || "all"} value={book.key}>{book.label}</option>)}
            </Select>
            <Select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "anki" | "quizlet")} disabled={busy} aria-label="Формат экспорта">
              <option value="anki">Anki</option>
              <option value="quizlet">Quizlet</option>
            </Select>
            {exportFormat === "anki" ? (
              <Button
                variant={controller.ankiPending > 0 ? "default" : "secondary"}
                size="sm"
                onClick={() => void controller.exportAnki()}
                disabled={busy || controller.ankiPending === 0}
                title={!controller.ankiPending ? "Все подходящие слова уже в Anki" : controller.connectors.anki?.state === "connected" ? "Отправить новые и обновлённые карточки в открытый Anki" : "Собрать колоду из новых и обновлённых карточек. Чтобы отправлять сразу в Anki, установите дополнение AnkiConnect (код 2055492159)"}
              >
                <Download size={15} /> В Anki <span className="words-count">{controller.ankiPending}</span>
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => void controller.exportVisible(exportFormat)} disabled={busy || totals.ready === 0} title="Сохранить видимые слова в TSV для Quizlet">
                <Download size={15} /> Экспорт
              </Button>
            )}
          </div>

          <div className="library-workspace-filters words-filters">
            <div className="words-filter-tabs" role="group" aria-label="Быстрые фильтры">
              <QuickFilterButton label="Все" value={totals.all} filter="all" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              <QuickFilterButton label="Новые" value={totals.new} filter="new" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              <QuickFilterButton label="На обработку" value={totals.pending} filter="pending" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              <QuickFilterButton label="Готовые" value={totals.ready} filter="ready" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              {obsidianEnabled ? <QuickFilterButton label="Не в Obsidian" value={totals.unsynced} filter="unsynced" current={controller.quickFilter} onChange={controller.setQuickFilter} /> : null}
            </div>
            <span className="words-count">{controller.visibleEntries.length} из {controller.entries.length}</span>
          </div>
        </header>

        <ConnectorNotice connector={controller.connectors.kindle} />
        {controller.lastExportPath && controller.operation.kind === "export" && controller.operation.status === "completed" ? (
          <div className="words-notice">
            <Check size={15} />
            <span className="words-notice-text">{controller.operation.message}. Откройте файл — Anki сам предложит импорт, повторный импорт обновит карточки без дублей.</span>
            <Button size="sm" onClick={() => void controller.openExport(false)}>Открыть в Anki</Button>
            <Button variant="ghost" size="sm" onClick={() => void controller.openExport(true)}>Показать в папке</Button>
          </div>
        ) : null}
        <LexemeTable entries={controller.visibleEntries} selectedId={controller.selectedEntry?.id ?? ""} onSelect={selectWord} obsidianEnabled={obsidianEnabled} loading={controller.loading} />
      </main>

      <aside ref={inspectorRef} className="library-inspector words-inspector" aria-label="Слово">
        <LexemeInspector
          entry={controller.selectedEntry}
          obsidianEnabled={obsidianEnabled}
          llmEnabled={controller.settings.llm_enabled}
          busy={busy}
          onEnrich={(id, retry) => void controller.enrichWords({ ids: [id], retryFailed: retry })}
        />
      </aside>
    </div>
  );
});

function ConnectorButton({ kind, info, onClick, disabled }: { kind: "kindle" | "obsidian"; info: ConnectorInfo; onClick: () => void; disabled: boolean }) {
  const Icon = kind === "obsidian" ? Database : HardDrive;
  return (
    <Button variant="secondary" size="sm" onClick={onClick} disabled={disabled} title={`${info.label}: ${connectorLabel(info.state)}`}>
      <Icon size={15} />
      {kind === "obsidian" ? "Obsidian" : "Kindle"}
      <span className={cn("words-connector-mark", `is-${info.state}`)} aria-label={connectorLabel(info.state)} />
    </Button>
  );
}

function ConnectorNotice({ connector }: { connector: ConnectorInfo }) {
  if (connector.state !== "disconnected") return null;
  return (
    <div className="words-notice is-quiet">
      <CloudOff size={15} />
      <span className="words-notice-text">Kindle не подключён. Библиотека доступна, синхронизация продолжится, когда вы подключите Kindle по USB.</span>
    </div>
  );
}

function QuickFilterButton({ label, value, filter, current, onChange }: { label: string; value: number; filter: QuickFilter; current: QuickFilter; onChange: (filter: QuickFilter) => void }) {
  return (
    <button type="button" onClick={() => onChange(filter)} aria-pressed={current === filter} className="words-filter">
      {label} <span>{value}</span>
    </button>
  );
}

const ITEM_HEIGHT = 52;
const OVERSCAN = 5;
const COLUMNS = "grid-cols-[minmax(110px,.8fr)_minmax(190px,1.5fr)_minmax(115px,.9fr)_118px]";
const COLUMNS_WITH_OBSIDIAN = "grid-cols-[minmax(105px,.75fr)_minmax(170px,1.45fr)_minmax(105px,.85fr)_112px_104px]";

const LexemeTable = React.memo(function LexemeTable({ entries, selectedId, onSelect, obsidianEnabled, loading }: { entries: LexemeRecord[]; selectedId: string; onSelect: (id: string) => void; obsidianEnabled: boolean; loading: boolean }) {
  const [container, setContainer] = React.useState<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportHeight, setViewportHeight] = React.useState(0);

  const setContainerRef = React.useCallback((el: HTMLDivElement | null) => {
    setContainer(el);
    if (el) {
      setViewportHeight(el.clientHeight);
      setScrollTop(el.scrollTop);
    }
  }, []);

  React.useEffect(() => {
    if (!container) return;
    const handleScroll = () => setScrollTop(container.scrollTop);
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setViewportHeight(entry.contentRect.height);
      }
    });
    container.addEventListener("scroll", handleScroll, { passive: true });
    observer.observe(container);
    return () => {
      container.removeEventListener("scroll", handleScroll);
      observer.disconnect();
    };
  }, [container]);

  React.useEffect(() => {
    if (!container || !selectedId) return;
    const index = entries.findIndex((entry) => entry.id === selectedId);
    if (index === -1) return;
    const rowTop = index * ITEM_HEIGHT;
    const rowBottom = rowTop + ITEM_HEIGHT;
    const viewTop = container.scrollTop;
    const viewBottom = viewTop + container.clientHeight;
    if (rowTop < viewTop || rowBottom > viewBottom) {
      container.scrollTo({ top: rowTop, behavior: "auto" });
    }
  }, [selectedId, entries, container]);

  if (loading) return <div className="words-state"><Loader2 size={20} className="animate-spin" />Загружаем библиотеку</div>;
  if (!entries.length) return <EmptyLibrary />;

  const totalHeight = entries.length * ITEM_HEIGHT;
  const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - OVERSCAN);
  const endIndex = Math.min(entries.length - 1, Math.ceil((scrollTop + viewportHeight) / ITEM_HEIGHT) + OVERSCAN);
  const topHeight = startIndex * ITEM_HEIGHT;
  const bottomHeight = Math.max(0, totalHeight - (endIndex + 1) * ITEM_HEIGHT);
  const visibleEntries = entries.slice(startIndex, endIndex + 1);

  return (
    <div className="words-table">
      <div className={cn("library-table-header words-table-head grid", obsidianEnabled ? COLUMNS_WITH_OBSIDIAN : COLUMNS)}>
        <span>Слово</span><span>Последний контекст</span><span>Книга</span><span>Обработка</span>{obsidianEnabled ? <span>Obsidian</span> : null}
      </div>
      <div ref={setContainerRef} className="app-scrollbar words-table-body">
        {topHeight > 0 ? <div style={{ height: topHeight }} /> : null}
        {visibleEntries.map((entry) => (
          <LexemeRow key={entry.id} entry={entry} selected={entry.id === selectedId} onSelect={onSelect} obsidianEnabled={obsidianEnabled} />
        ))}
        {bottomHeight > 0 ? <div style={{ height: bottomHeight }} /> : null}
      </div>
    </div>
  );
});

const LexemeRow = React.memo(function LexemeRow({ entry, selected, onSelect, obsidianEnabled }: { entry: LexemeRecord; selected: boolean; onSelect: (id: string) => void; obsidianEnabled: boolean }) {
  const occurrence = primaryOccurrence(entry);
  return (
    <button type="button" onClick={() => onSelect(entry.id)} aria-current={selected ? "true" : undefined} className={cn("library-word-row words-row grid", obsidianEnabled ? COLUMNS_WITH_OBSIDIAN : COLUMNS, selected && "is-selected")}>
      <div className="words-row-lemma">
        <div>
          <strong>{entry.lemma}</strong>
          {isAcceptedNew(entry) ? <Badge>новое</Badge> : null}
        </div>
        <small>
          {entry.sources.kindle ? <BookOpen size={11} aria-label="Kindle" /> : null}
          {entry.destinations.obsidian.state === "synced" ? <Database size={11} aria-label="Obsidian" /> : null}
          {entry.forms.length > 1 ? <span>{entry.forms.length} формы</span> : null}
          {entry.occurrences.length > 1 ? <span>· {entry.occurrences.length} контекста</span> : null}
        </small>
      </div>
      <span className="words-row-context">{occurrence?.context || "Контекст отсутствует"}</span>
      <span className="words-row-book">{occurrence?.book_title || "Без книги"}</span>
      <ProcessingMark entry={entry} />
      {obsidianEnabled ? <ObsidianMark entry={entry} /> : null}
    </button>
  );
});

function ProcessingMark({ entry }: { entry: LexemeRecord }) {
  const state = entry.processing.state;
  return <span className={cn("words-mark", processingTone(state))}><span className={cn("words-mark-dot", state === "processing" && "animate-pulse")} />{processingLabel(state)}</span>;
}

function ObsidianMark({ entry }: { entry: LexemeRecord }) {
  const synced = entry.destinations.obsidian.state === "synced";
  const missing = entry.destinations.obsidian.eligible && entry.destinations.obsidian.state === "missing";
  const label = synced ? "В Obsidian" : missing ? "Не в Obsidian" : "Не подходит";
  return <span className={cn("words-mark", synced ? "text-foreground" : "text-muted-foreground")} title={obsidianSyncReason(entry)}>{synced ? <Check size={13} /> : <Circle size={11} />}{label}</span>;
}

type LexemeInspectorProps = {
  entry: LexemeRecord | null;
  obsidianEnabled: boolean;
  llmEnabled: boolean;
  busy: boolean;
  onEnrich: (id: string, retry: boolean) => void;
};

function LexemeInspector({ entry, obsidianEnabled, llmEnabled, busy, onEnrich }: LexemeInspectorProps) {
  if (!entry) return <div className="words-state words-state-inspector"><Flourish width={120} />Выберите слово в списке — оно ляжет сюда, под лампу.</div>;
  const analysis = entry.processing.analysis;
  const enrichment = entry.enrichment?.status === "ready" ? entry.enrichment : null;
  const primary = primaryOccurrence(entry);
  const meaning = russianMeaning(entry);
  return (
    <section className="app-scrollbar words-inspector-scroll">
      <article className="word-card lamp-host">
        <ClipLamp lit />
        <PencilFrame />
        <div className="word-card-head">
          <h2>{entry.lemma}</h2>
          {isAcceptedNew(entry) ? <Badge>новое</Badge> : null}
          <span className="word-card-sources">
            {entry.sources.kindle ? <span title="Есть в Kindle"><BookOpen size={15} /></span> : null}
            {entry.destinations.obsidian.state === "synced" ? <span title="Есть в Obsidian"><Database size={15} /></span> : null}
          </span>
        </div>
        <p className="word-card-forms">{entry.forms.join(" · ")}</p>
        {meaning ? <p className="word-card-meaning">{meaning.text}</p> : null}
        {meaning?.source === "dictionary" ? <p className="word-card-source">значения по Викисловарю{enrichment ? "" : " · перевод по контексту — в настройках ИИ"}</p> : null}
        {primary?.context ? (
          <blockquote className="word-context">
            <p>{primary.context}</p>
            {enrichment?.context_ru ? <p className="word-context-translation">{enrichment.context_ru}</p> : null}
            <footer>{primary.book_title || "Источник без названия"}{primary.authors ? ` · ${primary.authors}` : ""}</footer>
          </blockquote>
        ) : null}
      </article>
      <TranslationDetails entry={entry} llmEnabled={llmEnabled} busy={busy} onEnrich={onEnrich} />
      <p className="words-meta">{entry.occurrences.length} {entry.occurrences.length === 1 ? "встреча в книгах" : "встреч в книгах"}</p>

      <InspectorSection title="О слове">
        <div className="words-state-row"><span>Состояние</span><ProcessingMark entry={entry} /></div>
        {entry.processing.error ? <p className="words-error">{entry.processing.error}</p> : null}
        {analysis ? <AnalysisDetails analysis={analysis} /> : <p className="words-meta">Слово ещё не проходило offline-обработку. Оценки и перевод заранее не заполняются.</p>}
      </InspectorSection>

      {entry.occurrences.length > 1 ? (
        <InspectorSection title={`Все контексты · ${entry.occurrences.length}`}>
          <div className="words-contexts">
            {entry.occurrences.map((occurrence) => (
              <blockquote key={occurrence.id} className="word-context">
                <p>{occurrence.context || "Контекст отсутствует"}</p>
                <footer>{occurrence.book_title || "Источник без названия"}{occurrence.looked_up_at ? ` · ${occurrence.looked_up_at}` : ""}</footer>
              </blockquote>
            ))}
          </div>
        </InspectorSection>
      ) : null}

      {obsidianEnabled ? (
        <InspectorSection title="Obsidian">
          <ObsidianMark entry={entry} />
          <p className="words-meta">{obsidianSyncReason(entry)}</p>
        </InspectorSection>
      ) : null}
    </section>
  );
}

function TranslationDetails({ entry, llmEnabled, busy, onEnrich }: { entry: LexemeRecord; llmEnabled: boolean; busy: boolean; onEnrich: (id: string, retry: boolean) => void }) {
  const enrichment = entry.enrichment;
  if (enrichment?.status === "ready") {
    if (!enrichment.definition_en && !enrichment.example_en && !enrichment.note_ru) return null;
    return (
      <div className="words-translation">
        {enrichment.definition_en ? <p>{enrichment.definition_en}</p> : null}
        {enrichment.example_en ? <p className="words-translation-example"><em>{enrichment.example_en}</em>{enrichment.example_ru ? ` — ${enrichment.example_ru}` : ""}</p> : null}
        {enrichment.note_ru ? <p className="home-note words-translation-note">{enrichment.note_ru}</p> : null}
        <p className="words-meta">Перевод: {enrichment.model}</p>
      </div>
    );
  }
  if (!isCardEligible(entry)) return null;
  const failed = enrichment?.status === "failed";
  return (
    <div className="words-translation-missing">
      <PencilFrame variant={1} />
      <span className={failed ? "text-destructive" : undefined}>
        {failed ? `Перевод не удался: ${enrichment?.error}` : llmEnabled ? "Перевода по контексту ещё нет." : "Перевод по контексту можно включить в настройках."}
      </span>
      {llmEnabled ? (
        <Button variant="secondary" size="sm" onClick={() => onEnrich(entry.id, failed)} disabled={busy}>
          <Languages size={14} /> {failed ? "Повторить" : "Перевести"}
        </Button>
      ) : null}
    </div>
  );
}

function AnalysisDetails({ analysis }: { analysis: WordAnalysis }) {
  return (
    <>
      <dl className="home-ledger words-ledger">
        <div><dt>Часть речи</dt><dd>{partOfSpeechLabel(analysis.pos)}</dd></div>
        <div><dt>Полезность</dt><dd>{analysis.importance_score != null ? `${analysis.importance_score}/10` : "не рассчитана"}</dd></div>
        <div><dt>Частотность</dt><dd>{analysis.frequency_note || "нет данных"}</dd></div>
      </dl>
      {analysis.importance_note ? <p className="words-meta">{analysis.importance_note}</p> : null}
    </>
  );
}

function InspectorSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="words-section">
      <PencilRule variant={1} />
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function EmptyLibrary() {
  return (
    <div className="words-state">
      <Flourish width={140} />
      <h2>В этой выборке нет слов</h2>
      <p>Измените фильтр, книгу или поисковый запрос.</p>
    </div>
  );
}

function connectorLabel(state: ConnectorInfo["state"]) {
  return { unknown: "не проверено", checking: "проверяется", connected: "подключён", disconnected: "не подключён", disabled: "выключен", error: "ошибка" }[state];
}
