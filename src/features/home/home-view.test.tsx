import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { LexemeRecord } from "@/types";
import { HomeView, type HomeViewProps } from "./home-view";

const noop = () => undefined;
const word = (id: string, lemma: string): LexemeRecord =>
  ({
    id,
    lemma,
    processing: { state: "ready", analysis: null, updated_at: "", error: "" },
    card: { meaning_ru: "страх", meaning_source: "dictionary", example_occurrence_id: "", edited: false },
    ranking: { score: 1, shelf: "worth", rank: 1, lean: null, version: "r2", reasons: [{ code: "recency", text: "Искали на этой неделе", weight: 0.4 }, { code: "thin_evidence", text: "данных мало", weight: -0.2 }] },
  }) as unknown as LexemeRecord;

const base: HomeViewProps = {
  mode: "list",
  words: [word("a", "dread"), word("b", "glimpse")],
  sinceLine: "С прошлого раза: 2 новых слова",
  roughNote: null,
  demo: false,
  exportUi: { kind: "idle" },
  destination: "anki",
  openState: "idle",
  folderState: "hidden",
  exportBlocked: false,
  listChanging: false,
  processingProgress: null,
  reader: { state: "connected", name: "Kindle" },
  onExport: noop,
  onOpenWord: noop,
  onOpenResult: noop,
  onOpenFolder: noop,
  onSync: noop,
  onImportFile: noop,
  onDemo: noop,
  onExitDemo: noop,
  onRetryProcessing: noop,
};
const html = (patch: Partial<HomeViewProps> = {}) => renderToStaticMarkup(<HomeView {...base} {...patch} />);

describe("Главная", () => {
  it("asks one question and offers one primary action with the size of the list", () => {
    const markup = html();
    expect(markup).toContain("Выгрузка слов");
    expect(markup).toContain("Выгрузить 2 слова");
    expect(markup.match(/ui-button-lit/g)).toHaveLength(1);
    expect(markup).toContain("С прошлого раза: 2 новых слова");
  });

  it("keeps the same interactive fox in every Home state", () => {
    for (const mode of ["loading", "no-reader", "empty", "preparing", "list", "processing-stopped"] as const) {
      const markup = html({ mode });
      expect(markup.match(/aria-label="Реплики лиса"/g)).toHaveLength(1);
      expect(markup).not.toContain("desk-lamp-drawing");
    }
  });

  it("labels the export with its full size while the preview shows only the supplied examples", () => {
    const quantity: NonNullable<HomeViewProps["quantity"]> = {
      mode: "library", limit: "20", levels: Array.from({ length: 10 }, (_, i) => i + 1),
      count: 123, available: 8, levelCounts: [123, 0, 0, 0, 0, 0, 0, 0, 0, 0], setMode: noop, setLimit: noop, setLevels: noop,
    };
    const words = Array.from({ length: 5 }, (_, i) => word(String(i), `example-${i}`));
    const markup = html({ words, quantity, onFindReader: noop });
    expect(markup).toContain("Выгрузить 123 слова");
    expect(markup).toContain("Первые 5 из 123");
    expect(markup.match(/class="home-row"/g)).toHaveLength(5);
    expect(markup).toContain("Найти Kindle");
    expect(html({ words: [], quantity: { ...quantity, levels: [], count: 0 } })).toContain("Выберите хотя бы один приоритет");
  });

  it("preserves the explicit desk lamp override for the historical study", () => {
    const markup = html({ deskLamp: <div data-testid="historical-lamp" /> });
    expect(markup).toContain("historical-lamp");
    expect(markup).not.toContain('aria-label="Реплики лиса"');
  });

  it("has no lede over the list and names the list plainly", () => {
    const markup = html();
    expect(markup).not.toContain("home-lede");
    expect(markup).toContain("Слова в выгрузке");
  });

  it("shows one reason per word and never one against it", () => {
    const markup = html();
    expect(markup).toContain("Искали на этой неделе");
    expect(markup).not.toContain("данных мало");
  });

  it("shows a skeleton, not the reader path, until the first answer", () => {
    const markup = html({ mode: "loading", words: [] });
    expect(markup).toContain("Открываю библиотеку");
    expect(markup).not.toContain("Где лежат слова");
    expect(markup).not.toContain("Посмотреть на примере");
    expect(markup).toContain('aria-busy="true"');
  });

  it("keeps the file places, the file picker and the example in view without a reader", () => {
    const markup = html({ mode: "no-reader", words: [], reader: { state: "disconnected", name: "Kindle" } });
    for (const text of ["system/vocabulary/vocab.db", "vocabulary_builder.sqlite3", ".kobo/KoboReader.sqlite", "Выбрать файл", "Посмотреть на примере", "Найти Kindle", "Читалка не найдена", "передачу файлов"]) expect(markup).toContain(text);
  });

  it("says the export is running on a blocked button", () => {
    const markup = html({ exportUi: { kind: "running" } });
    expect(markup).toContain("Выгружаю…");
    expect(markup).toContain('aria-busy="true"');
  });

  it("writes the empty answer and the failure with a way to retry", () => {
    expect(html({ mode: "empty", words: [] })).toContain("Новых слов для выгрузки нет.");
    const failed = html({ exportUi: { kind: "error", message: "диск полон" } });
    expect(failed).toContain("Не получилось: диск полон.");
    expect(failed).toContain("Попробовать снова");
    expect(failed).toContain("is-error");
  });

  it("offers the folder when the export wrote a file", () => {
    const run = { destination: "anki", runId: "r", exported: 2, path: "x/Kindle Cards.apkg", pushed: 0, message: "" } as const;
    const markup = html({ exportUi: { kind: "done", run }, folderState: "ready" });
    expect(markup).toContain("Готово: 2 слова в файле");
    expect(markup).toContain("Открыть в Anki");
    expect(markup).toContain("Откройте колоду и подтвердите импорт в Anki");
    expect(markup.match(/Открыть папку выгрузок/g)).toHaveLength(1);
    expect(html({ exportUi: { kind: "done", run: { ...run, destination: "csv", path: "x/words.tsv" } } })).not.toContain("Открыть в Anki");
  });

  it("keeps one keyboard action in an empty library after restart and explains a removed file", () => {
    const empty = { mode: "empty", words: [] } as const;
    expect(html({ mode: empty.mode, words: [], folderState: "ready" })).toMatch(/<button[^>]*>Открыть папку выгрузок<\/button>/);
    const missing = html({ mode: empty.mode, words: [], folderState: "missing" });
    expect(missing).toContain("В папке выгрузок больше нет файлов.");
    expect(missing).not.toContain("Открыть папку выгрузок");
  });

  it("asks to check Anki when the outcome is unknown and exposes the saved folder", () => {
    const markup = html({ folderState: "ready", exportUi: { kind: "error", message: "", code: "anki_import_unconfirmed" } });
    expect(markup).toContain("Проверьте, появились ли слова в Anki");
    expect(markup).toContain("Открыть папку выгрузок");
    expect(markup).toContain("Отправить снова");
    expect(markup.indexOf("Проверьте, появились ли слова в Anki")).toBeLessThan(markup.indexOf("Отправить снова"));
    expect(markup).not.toContain("ui-button-lit");
    expect(markup).not.toContain("Готово:");
  });

  it("distinguishes processing from the final empty list and keeps recovery available", () => {
    const preparing = html({ mode: "preparing", words: [], listChanging: true });
    expect(preparing).toContain("Готовлю подборку");
    expect(preparing).not.toContain("Новых слов для выгрузки нет.");
    const stopped = html({ mode: "processing-stopped", words: [] });
    expect(stopped).toContain("Продолжить обработку");
    const demo = html({ mode: "empty", words: [], demo: true, folderState: "ready" });
    expect(demo).toContain("Закрыть пример");
    expect(demo).not.toContain("Открыть папку выгрузок");
  });

  it("keeps the status line in the page when empty, so changes are announced", () => {
    expect(html()).toMatch(/role="status"[^>]*aria-live="polite"/);
  });

  it("shows one line under the button: error, then busy, then demo, then the rough order", () => {
    const rough = "Порядок примерный";
    const error = { kind: "error", message: "диск полон" } as const;
    const lines = (markup: string) => (markup.match(/class="home-note"/g) ?? []).length;
    expect(html({ roughNote: rough, listChanging: true })).not.toContain(rough);
    expect(html({ roughNote: rough, demo: true })).not.toContain(rough);
    expect(html({ roughNote: rough, demo: true })).toContain("Пример: слова выдуманные — ничего не сохраняется");
    expect(lines(html({ roughNote: rough, listChanging: true, demo: true }))).toBe(1);
    expect(html({ roughNote: rough, listChanging: true, exportUi: error })).not.toContain("список может измениться");
    expect(html({ roughNote: rough })).toContain(rough);
  });

  it("offers each ranked card by name and disables editing during export", () => {
    expect(html()).toContain("Открыть карточку «dread»");
    expect(html()).toContain('aria-describedby="home-why-a"');
    expect(html()).toContain("Открыть карточку «glimpse»");
    expect(html({ exportUi: { kind: "running" } })).toMatch(/<button[^>]*id="home-word-a"[^>]*disabled/);
  });

  it("blocks the button while the list is changing and says why", () => {
    const markup = html({ listChanging: true });
    expect(markup).toContain("disabled");
    expect(markup).toContain("список может измениться");
  });

  it("prepares the first batch with a real accessible counter and no repeat import action", () => {
    const markup = html({ mode: "preparing", words: [], listChanging: true, folderState: "ready",
      processingProgress: { phase: "processing", current: 7, total: 23 } });
    expect(markup).toMatch(/<h1[^>]*>Готовлю подборку<\/h1>/);
    expect(markup).toContain("Подборка появится здесь");
    expect(markup).toContain("Обработано 7 из 23");
    expect(markup).toContain('aria-label="Реплики лиса"');
    expect(markup).not.toContain('aria-label="Реплика лиса"');
    expect(markup).toMatch(/<progress[^>]*aria-label="Обработка слов"[^>]*value="7"[^>]*max="23"/);
    expect(markup).toContain('aria-live="off"');
    expect(markup).not.toContain("Выбрать файл");
    expect(markup).not.toContain("Загрузить слова с читалки");
    expect(markup).not.toContain("Выгрузка слов");
    expect(markup).not.toContain("home-skel");
    expect(markup).toContain("Открыть папку выгрузок");
  });

  it("shows waiting and finishing without inventing a numeric progress", () => {
    for (const phase of ["waiting", "finishing"] as const) {
      const markup = html({ mode: "preparing", words: [], processingProgress: { phase } });
      expect(markup).not.toContain("<progress");
      expect(markup).not.toContain("Обработано");
      expect(markup).toContain(phase === "waiting" ? "Подготовка к обработке…" : "Собираю подборку…");
    }
  });

  it("keeps the available batch and export errors beside compact processing progress", () => {
    const markup = html({ listChanging: true, processingProgress: { phase: "processing", current: 8, total: 25 },
      exportUi: { kind: "error", message: "диск полон" } });
    expect(markup).toContain("Открыть карточку «dread»");
    expect(markup).toContain("Обработано 8 из 25");
    expect(markup).toContain('aria-label="Реплики лиса"');
    expect(markup).toContain("Подборка ещё меняется");
    expect(markup).toContain('aria-describedby="home-processing-note"');
    expect(markup).toContain("Не получилось: диск полон.");
    expect(markup).not.toContain("Разбираю новые слова");
    expect(markup).toMatch(/<button[^>]*id="home-word-a"[^>]*disabled/);
  });

  it("announces only the phase while the numeric counter changes", () => {
    const announcement = (current: number) => html({ processingProgress: { phase: "processing", current, total: 1000 } })
      .match(/<p class="sr-only home-processing-announcement"[^>]*>[^<]*<\/p>/)?.[0];
    expect(announcement(1)).toBe(announcement(2));
    expect(announcement(1)).toContain("Обрабатываю слова…");
    expect(html({ processingProgress: { phase: "finishing" } })).toMatch(/home-processing-announcement[^>]*>Собираю подборку…/);
    const one = html({ processingProgress: { phase: "processing", current: 1, total: 1 } });
    expect(one).toContain('aria-valuetext="Обработано слов 1 из 1"');
    expect(one).not.toContain("из 1 слов");
  });
});
