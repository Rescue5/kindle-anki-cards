import * as React from "react";
import ReactDOM from "react-dom/client";
import { BarChart3, BookOpen, Home, Library, RotateCcw, Settings } from "lucide-react";
import { SettingsView } from "@/components/settings-view";
import { LibraryWorkspace } from "@/features/library/library-workspace";
import { useLibraryController } from "@/features/library/use-library-controller";
import { BooksView } from "@/features/reading/books-view";
import { InsightsView } from "@/features/reading/insights-view";
import { ReadingHome } from "@/features/reading/reading-home";
import { ReviewView } from "@/features/reading/review-view";
import { callBackend } from "@/lib/backend";
import type { LexemeRecord } from "@/types";
import "@fontsource-variable/literata/opsz.css";
import "@fontsource-variable/literata/opsz-italic.css";
import "@fontsource-variable/caveat";
import "@/index.css";
import "@/design/night-reading.css";
import "@/features/reading/reading.css";
import { Sconce, useLightSwitch } from "@/components/light/light";
import { PencilDefs } from "@/components/sketch/sketch";
import { ankiPendingCount } from "@/features/library/domain";
import { ruCount } from "@/features/reading/reading-domain";

type View = "home" | "books" | "words" | "review" | "insights" | "settings";
const views: View[] = ["home", "books", "words", "review", "insights", "settings"];

const navigation = [
  { label: "Главная", icon: Home, view: "home" as const },
  { label: "Книги", icon: BookOpen, view: "books" as const },
  { label: "Слова", icon: Library, view: "words" as const },
  { label: "Повторение", icon: RotateCcw, view: "review" as const },
  { label: "Аналитика", icon: BarChart3, view: "insights" as const },
  { label: "Настройки", icon: Settings, view: "settings" as const },
];

function App() {
  const controller = useLibraryController();
  // `?view=` opens a screen directly; used for browser previews and README screenshots.
  const [view, setView] = React.useState<View>(() => {
    const requested = new URLSearchParams(window.location.search).get("view");
    return views.includes(requested as View) ? (requested as View) : "home";
  });
  const [dueCount, setDueCount] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    void callBackend<{ due_count: number }>("load_review", { limit: 1 })
      .then((result) => { if (active) setDueCount(result.due_count); })
      .catch(() => { if (active) setDueCount(0); });
    return () => { active = false; };
  }, [controller.entries]);

  function openWord(entry?: LexemeRecord | string) {
    controller.setQuery("");
    controller.setSelectedBookKey("");
    controller.setQuickFilter("all");
    if (entry) controller.setSelectedId(typeof entry === "string" ? entry : entry.id);
    setView("words");
  }

  function searchWords(query: string) {
    controller.setSelectedBookKey("");
    controller.setQuickFilter("all");
    controller.setQuery(query);
    setView("words");
  }

  function openNewWords() {
    controller.setQuery("");
    controller.setSelectedBookKey("");
    controller.setQuickFilter("new");
    setView("words");
  }

  // The room's light: night when the theme resolves to dark.
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const theme = controller.settings.theme;
  const night = theme === "dark" || (theme === "system" && prefersDark);
  React.useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", night);
    root.classList.toggle("light", !night);
  }, [night]);
  const { setSettings, settings } = controller;
  const flipLight = React.useCallback(() => {
    const next = { ...settings, theme: night ? "light" : "dark" } as typeof settings;
    setSettings(next);
    void callBackend("save_settings", { settings: next }).catch(() => undefined);
  }, [night, setSettings, settings]);
  const { toggle: pullCord, curtain } = useLightSwitch(flipLight);

  const busy = controller.operation.status === "running";
  const ankiPending = React.useMemo(() => ankiPendingCount(controller.entries), [controller.entries]);
  const activeIndex = navigation.findIndex((item) => item.view === view);
  const wordCount = controller.entries.length;
  const status = busy
    ? controller.operation.message || controller.operation.title
    : controller.operation.status === "error"
      ? controller.operation.error || controller.operation.message || controller.operation.title
      : controller.queueStatus.total > 0
        ? `Обработка: ${controller.queueStatus.total} слов`
      : controller.operation.status === "completed" && controller.operation.message
        ? controller.operation.message
        : "Библиотека готова";

  return (
    <div className="reading-app">
      <PencilDefs />
      <aside className="reading-sidebar">
        <button type="button" className="reading-brand" onClick={() => setView("home")} aria-label="Kindle Cards — главная">
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
              const active = view === item.view;
              return (
                <li key={item.view}>
                  <button type="button" onClick={() => setView(item.view)} aria-current={active ? "page" : undefined} className={active ? "is-active" : undefined}>
                    <Icon size={18} strokeWidth={1.6} />
                    <span>{item.label}</span>
                    {item.view === "review" && dueCount > 0 ? <em aria-label={`${dueCount} к повторению`}>{dueCount}</em> : null}
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
          {view === "home" ? <ReadingHome bookOptions={controller.books} entries={controller.entries} connectors={controller.connectors} operation={controller.operation} dueCount={dueCount} ankiPending={ankiPending} onSync={() => void controller.syncKindle()} onReview={() => setView("review")} onBooks={() => setView("books")} onWords={openWord} onNewWords={openNewWords} onSearch={searchWords} onSendToAnki={() => void controller.exportAnki()} onImportFile={(file) => void controller.importReaderFile(file)} /> : null}
          {view === "books" ? <BooksView books={controller.books} entries={controller.entries} onOpenWord={openWord} onDownloadCovers={controller.downloadCovers} coversBusy={controller.coversBusy || controller.operation.status === "running"} coverSummary={controller.coverSummary} /> : null}
          {view === "words" ? <LibraryWorkspace controller={controller} /> : null}
          {view === "review" ? <ReviewView onCountsChange={setDueCount} onOpenWords={() => openWord()} /> : null}
          {view === "insights" ? <InsightsView books={controller.books} entries={controller.entries} onOpenWord={openWord} /> : null}
          {view === "settings" ? <SettingsView settings={controller.settings} onChange={controller.setSettings} /> : null}
        </div>
        {curtain}
        <div className="paper-grain" aria-hidden="true" />
        <div className="reading-status" role="status"><span className={busy ? "reading-status-dot is-busy" : "reading-status-dot"} />{status}{controller.operation.status === "error" ? <button type="button" onClick={controller.retry}>Повторить</button> : null}</div>
      </div>
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
