import * as React from "react";
import ReactDOM from "react-dom/client";
import { Home, Library, Settings } from "lucide-react";
import { SettingsView } from "@/components/settings-view";
import { obsidianVaultPathError } from "@/lib/export-destinations";
import { LibraryWorkspace } from "@/features/library/library-workspace";
import { useLibraryController } from "@/features/library/use-library-controller";
import { useCatalogueFilters } from "@/features/library/use-catalogue-filters";
import { translationState } from "@/features/library/domain";
import { useLibraryProvider } from "@/features/llm/use-llm-config";
import { HomeScreen } from "@/features/home/home-screen";
import { FoxTour } from "@/features/onboarding/fox-tour";
import { useFoxTour } from "@/features/onboarding/use-fox-tour";
import { homeQueueState, libraryExportOrder, shortList } from "@/features/home/home-domain";
import { useHomeExport } from "@/features/home/use-home-export";
import { navViewOf, parseView, type NavView, type View } from "@/features/shell/views";
import "@fontsource-variable/literata/opsz.css";
import "@fontsource-variable/literata/opsz-italic.css";
import "@fontsource-variable/caveat";
import "@/index.css";
import "@/design/night-reading.css";
import "@/design/cabinet.css";
import "@/features/reading/reading.css";
import "@/features/home/home.css";
import { Sconce, useLightSwitch } from "@/components/light/light";
import { PencilDefs } from "@/components/sketch/sketch";
import { ruCount } from "@/features/reading/reading-domain";

const navigation: { label: string; icon: typeof Home; view: NavView }[] = [
  { label: "Главная", icon: Home, view: "home" },
  { label: "Слова", icon: Library, view: "words" },
  { label: "Настройки", icon: Settings, view: "settings" },
];
const noExportIds: string[] = [];

function App() {
  const controller = useLibraryController();
  // `?view=` opens a screen directly; used for browser previews and README screenshots.
  const [view, setView] = React.useState<View>(() => parseView(window.location.search));
  const catalogueFilters = useCatalogueFilters();
  const [focusLlmSettings, setFocusLlmSettings] = React.useState(false);
  const focusTranslation = React.useRef(false);
  const provider = useLibraryProvider(controller.settings, navViewOf(view) === "words" && !controller.loading);
  const eligibleIds = React.useMemo(() => new Set(controller.entries.filter((entry) => {
    const state = translationState(entry);
    return state === "pending" || state === "failed";
  }).map((entry) => entry.id)), [controller.entries]);
  React.useEffect(() => {
    if (view !== "words" || !focusTranslation.current || provider.availability === "loading") return;
    const launch = document.getElementById("library-translate");
    const target = launch && !launch.matches(":disabled") ? launch : document.getElementById("library-search");
    target?.focus();
    focusTranslation.current = false;
  }, [view, provider.availability]);
  const tour = useFoxTour(controller.initialLibraryEmpty, view === "home" && !controller.demo);
  const [batchLexemeId, setBatchLexemeId] = React.useState<string>();
  const returnFocus = React.useRef<string>();
  const draftDirty = React.useRef(false);
  const [cardSaving, setCardSaving] = React.useState(false);
  const reportDraft = React.useCallback((dirty: boolean, pending = false) => {
    draftDirty.current = dirty;
    setCardSaving(pending);
  }, []);
  function navigate(next: View, focusLlm = false) {
    if (view === next || cardSaving) return;
    if (draftDirty.current && !window.confirm("Есть несохранённые правки. Уйти и отменить их?")) return;
    draftDirty.current = false;
    setBatchLexemeId(undefined);
    setFocusLlmSettings(focusLlm);
    setView(next);
  }
  function openBatchWord(id: string) {
    setBatchLexemeId(id);
    setView("words");
  }
  function backToBatch() {
    returnFocus.current = batchLexemeId;
    draftDirty.current = false;
    setBatchLexemeId(undefined);
    setView("home");
  }
  React.useLayoutEffect(() => {
    if (view !== "home" || controller.loading || !returnFocus.current) return;
    const target = document.getElementById(`home-word-${returnFocus.current}`)
      ?? document.getElementById("home-list-title")
      ?? document.getElementById("home-title");
    target?.focus();
    returnFocus.current = undefined;
  }, [view, controller.loading]);

  // The room's light: night when the theme resolves to dark.
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const theme = controller.settings.theme;
  const night = theme === "dark" || (theme === "system" && prefersDark);
  React.useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", night);
    root.classList.toggle("light", !night);
  }, [night]);
  const { saveSettings, loading } = controller;
  const flipLight = React.useCallback(() => {
    if (!loading) void saveSettings({ theme: night ? "light" : "dark" }).catch(() => undefined);
  }, [loading, night, saveSettings]);
  const { toggle: pullCord, curtain } = useLightSwitch(flipLight);

  const busy = controller.operation.status === "running";
  const batch = controller.ranking?.newBatch;
  const rankedIds = batch?.availableIds ?? batch?.ids;
  const exportIds = React.useMemo(() => shortList(controller.entries, rankedIds ?? noExportIds).map((entry) => entry.id),
    [controller.entries, rankedIds]);
  const homeQueue = homeQueueState(controller.queueStatus, controller.operation);
  const prioritySource = controller.ranking?.studyPrioritySource;
  const libraryWords = React.useMemo(() => libraryExportOrder(controller.entries, prioritySource), [controller.entries, prioritySource]);
  const destination = controller.settings.export_destination;
  const vaultPath = destination === "obsidian" ? controller.settings.obsidian_vault_path : "";
  const vaultPathError = destination === "obsidian" ? obsidianVaultPathError(vaultPath) : null;
  const exporter = useHomeExport({
    ids: exportIds,
    libraryWords,
    defaultCount: controller.settings.export_batch_size ?? 20,
    blocked: controller.settingsSaving || busy || homeQueue === "working" || Boolean(vaultPathError),
    reload: controller.loadLibrary,
    active: view === "home" && !controller.demo,
  });
  const homeHandlesProcessing = view === "home" && !controller.demo && controller.entries.length > 0
    && exportIds.length === 0 && homeQueue === "stopped" && controller.operation.kind === "processing";
  const homeShowsProgress = view === "home" && !loading && !controller.demo && controller.entries.length > 0
    && homeQueue === "working" && (busy ? controller.operation.kind === "processing" : controller.operation.status !== "error");
  const { dismiss } = exporter;
  const exporting = exporter.state.kind === "running";
  React.useEffect(() => dismiss(), [dismiss, destination, vaultPath]);
  React.useEffect(() => {
    if (controller.operation.status === "running" && controller.operation.kind === "kindle") dismiss();
  }, [dismiss, controller.operation.kind, controller.operation.status]);
  // The sconce rides to the entry that holds the current view (Спорные and Экспорт belong to Слова).
  const activeIndex = navigation.findIndex((item) => item.view === navViewOf(view));
  const wordCount = controller.entries.length;
  const status = exporting ? "Выгружаю слова…" : busy
    ? controller.operation.message || controller.operation.title
    : controller.operation.status === "error"
      ? controller.operation.error || controller.operation.message || controller.operation.title
      : controller.queueStatus.total > 0
        ? `Обработка: ${controller.queueStatus.total} слов`
      : controller.operation.status === "completed" && controller.operation.kind !== "processing" && controller.operation.message
        ? controller.operation.message
        : "Библиотека готова";

  return (
    <div className="reading-app">
      <PencilDefs />
      <aside className="reading-sidebar">
        <button type="button" className="reading-brand" disabled={cardSaving} onClick={() => navigate("home")} aria-label="Kindle Cards — главная">
          <svg className="reading-brand-mark" viewBox="0 0 28 28" aria-hidden="true">
            <path d="M5 24.5h12 M9 24.5 13 13l-4-4" />
            <path className="reading-brand-shade" d="M6.5 11.5 12.5 5.5l4.5 4.5-6 6z" />
            <circle className="reading-brand-bulb" cx="17.5" cy="17" r="3" />
          </svg>
          <strong>Kindle Cards</strong>
        </button>
        <nav className="reading-nav lamp-host" aria-label="Основная навигация" style={{ "--sconce-index": Math.max(0, activeIndex) } as React.CSSProperties}>
          {/* The wall sconce rides to the section you are in. */}
          <Sconce lit />
          <ul>
            {navigation.map((item) => {
              const Icon = item.icon;
              const active = navViewOf(view) === item.view;
              return (
                <li key={item.view}>
                  <button type="button" disabled={cardSaving} onClick={() => navigate(item.view)} aria-current={active ? "page" : undefined} className={active ? "is-active" : undefined}>
                    <Icon size={18} strokeWidth={1.6} />
                    <span>{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="reading-sidebar-bottom">
          <p>В библиотеке</p>
          <p className="reading-sidebar-count">{wordCount.toLocaleString("ru-RU")} <span>{ruCount(wordCount, "слово", "слова", "слов")}</span></p>
          <button type="button" className="reading-light-switch" onClick={pullCord} aria-label={night ? "Включить дневной свет" : "Зажечь лампы — ночной режим"}>
            <svg viewBox="0 0 36 52" aria-hidden="true">
              <path className="reading-light-switch-plate" d="M5.5 3.2 C14 2.6 23 3.4 31.2 2.9 C33 3 33.4 4.6 33.3 6.4 C33.6 20 32.9 34 33.4 46.2 C33.2 48.6 31.9 49.2 30.1 49.3 C21 49.6 13 48.9 5.4 49.4 C3.4 49.2 2.7 47.9 2.8 46 C2.5 32 3.3 18 2.7 5.8 C2.9 3.8 3.9 3.3 5.5 3.2 Z" />
              <rect x="12.5" y="13" width="11" height="26" rx="3.5" />
              <circle cx="18" cy="7.5" r="1" />
              <circle cx="18" cy="44.5" r="1" />
              <rect className="reading-light-switch-lever" x="14" y="14.5" width="8" height="13" rx="2.5" />
            </svg>
            <span>
              <strong>{night ? "Ночной свет" : "Дневной свет"}</strong>
              <small>{night ? "щёлкните, чтобы включить день" : "щёлкните, чтобы зажечь лампы"}</small>
            </span>
          </button>
        </div>
      </aside>

      <div className="reading-app-main">
        <div className="reading-view-frame">
          {view === "home" ? <HomeScreen controller={controller} exporter={exporter} onOpenWord={openBatchWord} onOpenLibrary={() => navigate("words")}
            onOpenSettings={() => navigate("settings")} vaultPathError={vaultPathError} tourOpen={tour.open} /> : null}
          {/* Until Спорные and Экспорт ship, their views open the library workspace. */}
          {view === "words" || view === "triage" || view === "export" ? (
            <LibraryWorkspace controller={controller} batchLexemeId={batchLexemeId} exporting={exporting}
              catalogueFilters={catalogueFilters}
              translation={{ ...provider, availability: controller.settingsSaving ? "loading" : provider.availability,
                eligibleIds, perSense: Boolean(controller.settings.llm_examples_per_sense),
                onOpenSettings: () => navigate("settings", true),
                onStart: (ids) => void controller.enrichWords({ ids, retryFailed: true, exact: true }) }}
              onBackToBatch={batchLexemeId ? backToBatch : undefined} onDraftChange={reportDraft} />
          ) : null}
          {view === "settings" && loading ? <main className="reading-page app-scrollbar"><p className="screen-page" role="status">Загружаю настройки…</p></main> : null}
          {view === "settings" && !loading ? (
            <SettingsView
              settings={controller.settings}
              onSave={controller.saveSettings}
              onOpenTour={tour.start}
              focusLlm={focusLlmSettings} onOpenWords={() => { focusTranslation.current = true; navigate("words"); }}
              saving={controller.settingsSaving}
              busy={busy || exporting}
            />
          ) : null}
        </div>
        {curtain}
        <div className="paper-grain" aria-hidden="true" />
        {!homeShowsProgress ? (
          <div className="reading-status" role="status">
            <span className={busy || exporting ? "reading-status-dot is-busy" : "reading-status-dot"} />{status}
            {!exporting && controller.operation.status === "error" && controller.operation.kind !== "obsidian" && !homeHandlesProcessing
              ? <button type="button" onClick={controller.retry}>Повторить</button> : null}
          </div>
        ) : null}
      </div>
      <FoxTour open={tour.open} onDismiss={tour.dismiss} />
    </div>
  );
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = React.useState(() => window.matchMedia(query).matches);
  React.useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

const rootElement = document.getElementById("root")!;
const rootState = rootElement as typeof rootElement & { __kindleCardsRoot?: ReturnType<typeof ReactDOM.createRoot> };
rootState.__kindleCardsRoot ??= ReactDOM.createRoot(rootElement);
rootState.__kindleCardsRoot.render(<React.StrictMode><App /></React.StrictMode>);
