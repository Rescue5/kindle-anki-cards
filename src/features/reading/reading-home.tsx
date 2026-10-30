import * as React from "react";
import { ArrowRight, RefreshCw, Search } from "lucide-react";
import type { BookOption, ConnectorStatus, LexemeRecord, Operation } from "@/types";
import { cn } from "@/lib/utils";
import { ClipLamp, DeskLamp } from "@/components/light/light";
import { CornerCurl, PencilFrame, PencilRule } from "@/components/sketch/sketch";
import { formatDate, greeting, partOfSpeechShort, reviewMinutes, ruCount } from "./reading-domain";

type Props = {
  bookOptions: BookOption[];
  entries: LexemeRecord[];
  connectors: ConnectorStatus;
  operation: Operation;
  dueCount: number;
  ankiPending: number;
  onSync: () => void;
  onReview: () => void;
  onBooks: () => void;
  onWords: (id?: string) => void;
  onNewWords: () => void;
  onSearch: (query: string) => void;
  onSendToAnki: () => void;
};

type BookSummary = { key: string; title: string; author: string; coverDataUrl?: string; lookups: number; words: number; latest: string; latestAt: number };

function timestamp(value: string) {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function summarizeBooks(entries: LexemeRecord[], bookOptions: BookOption[]): BookSummary[] {
  const map = new Map<string, BookSummary>();
  const coverByKey = new Map(bookOptions.map((book) => [book.key, book.cover_data_url]));
  const titleByKey = new Map(bookOptions.map((book) => [book.key, book.display_title]));
  for (const entry of entries) {
    const seen = new Set<string>();
    for (const occurrence of entry.occurrences) {
      const key = occurrence.book_key || occurrence.book_title;
      if (!key) continue;
      const book = map.get(key) ?? { key, title: titleByKey.get(key) || occurrence.book_title || key, author: occurrence.authors, coverDataUrl: coverByKey.get(key), lookups: 0, words: 0, latest: "", latestAt: 0 };
      book.lookups += 1;
      if (!seen.has(key)) book.words += 1;
      const at = timestamp(occurrence.looked_up_at);
      if (at > book.latestAt) {
        book.latestAt = at;
        book.latest = occurrence.looked_up_at;
      }
      map.set(key, book);
      seen.add(key);
    }
  }
  return [...map.values()].sort((a, b) => b.latestAt - a.latestAt || b.lookups - a.lookups);
}

function meaningOf(entry: LexemeRecord): string {
  if (entry.enrichment?.status === "ready" && entry.enrichment.meaning_ru) return entry.enrichment.meaning_ru;
  return entry.processing.analysis?.russian_meanings || "";
}

/** The latest book as a jacket lying under the desk lamp: the real cover when Kindle has one. */
function BookJacket({ book, lit }: { book: BookSummary; lit: boolean }) {
  return (
    <div className={cn("home-jacket", lit && "is-lit")} aria-hidden="true">
      {book.coverDataUrl ? (
        <img className="home-jacket-image" src={book.coverDataUrl} alt="" />
      ) : (
        <>
          <svg className="home-jacket-art" viewBox="0 0 212 310" preserveAspectRatio="none">
            <rect x="16" y="14" width="180" height="282" rx="2" />
            <rect className="home-jacket-art-soft" x="21" y="19" width="170" height="272" rx="1" />
            <path className="home-jacket-art-soft" d="M156.9 217.2 L190.1 210.1 M153.5 206.8 L173.6 197.9 M148.1 197.4 L175.6 177.5 M140.8 189.4 L155.5 173 M132 183 L149 153.5 M122.1 178.5 L128.9 157.6 M111.4 176.3 L115 142.5 M100.6 176.3 L98.3 154.4 M89.9 178.5 L79.4 146.2 M80 183 L69 163.9 M71.2 189.4 L48.5 164.1 M63.9 197.4 L46.1 184.5 M58.5 206.8 L27.4 193 M55.1 217.2 L33.6 212.6" />
            <path d="M58 228 A48 48 0 0 1 154 228 M74 228 A32 32 0 0 1 138 228 M36 228 L176 228" />
          </svg>
          <span className="home-jacket-title">{book.title}</span>
          {book.author ? <span className="home-jacket-author">{book.author}</span> : null}
        </>
      )}
      <span className="home-jacket-light" />
    </div>
  );
}

function KindleStatus({ connectors }: { connectors: ConnectorStatus }) {
  const state = connectors.kindle.state;
  const label = state === "connected" ? "Kindle подключён" : state === "unknown" ? "Ищем Kindle…" : "Kindle не подключён";
  return (
    <p className={cn("home-kindle", state === "connected" && "is-connected")}>
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M10 2.6 C14.6 2.4 17.6 5.8 17.4 10.2 C17.2 14.6 13.8 17.6 9.6 17.4 C5.4 17.2 2.5 14 2.7 9.8 C2.9 6 5.6 3.1 9.4 2.9" />
        {state === "connected" ? <path d="m6.6 10.2 2.4 2.5 4.6-5" /> : <path d="M7 10h6" />}
      </svg>
      {label}
    </p>
  );
}

export function ReadingHome({ bookOptions, entries, connectors, operation, dueCount, ankiPending, onSync, onReview, onBooks, onWords, onNewWords, onSearch, onSendToAnki }: Props) {
  const books = React.useMemo(() => summarizeBooks(entries, bookOptions), [entries, bookOptions]);
  const recent = React.useMemo(() => [...entries].sort((a, b) => timestamp(b.last_seen_at) - timestamp(a.last_seen_at)).slice(0, 5), [entries]);
  const freshCount = React.useMemo(() => entries.filter((entry) => entry.freshness === "new").length, [entries]);
  const readyCount = React.useMemo(() => entries.filter((entry) => entry.processing.state === "ready" && entry.processing.analysis?.accepted).length, [entries]);
  const [query, setQuery] = React.useState("");
  const now = React.useMemo(() => new Date(), []);
  const latestBook = books[0];
  const busy = operation.status === "running";
  const syncing = busy && operation.kind === "kindle";
  const kindleConnected = connectors.kindle.state === "connected";
  // A lamp burns only where there is something to do.
  const deskLit = freshCount > 0 || kindleConnected;
  const reviewLit = dueCount > 0;
  const minutes = reviewMinutes(dueCount);

  const syncButton = (primary: boolean) => (
    <button type="button" className={primary ? "reading-primary-button" : "reading-secondary-button"} onClick={onSync} disabled={busy || !kindleConnected}>
      {primary ? null : <PencilFrame />}
      <RefreshCw size={17} strokeWidth={1.7} className={syncing ? "animate-spin" : undefined} />
      {primary ? "Синхронизировать Kindle" : "Синхронизировать"}
    </button>
  );

  return (
    <main className="reading-page app-scrollbar">
      <div className="home-page">
        <header className="home-header">
          <div className="home-greeting">
            <h1>{greeting(now)}</h1>
            <p>{new Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long" }).format(now)}</p>
          </div>
          <div className="home-header-tools">
            <form className="home-search" role="search" onSubmit={(event) => { event.preventDefault(); onSearch(query.trim()); }}>
              <label>
                <Search size={17} strokeWidth={1.7} aria-hidden="true" />
                <span className="sr-only">Найти слово или книгу</span>
                <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти слово или книгу" />
              </label>
              <PencilRule variant={1} />
            </form>
            <KindleStatus connectors={connectors} />
          </div>
        </header>

        <section className="home-hero lamp-host" aria-labelledby="home-hero-title">
          <DeskLamp lit={deskLit} />
          {latestBook ? (
            <>
              <BookJacket book={latestBook} lit={deskLit} />
              <div className="home-hero-text">
                <p className="home-eyebrow">Последняя книга в Kindle</p>
                <h2 id="home-hero-title" className="home-book-title">{latestBook.title}</h2>
                {latestBook.author ? <p className="home-book-author">{latestBook.author}</p> : null}
                <p className="home-lede">
                  {freshCount > 0
                    ? "Новые находки из ваших книг уже в библиотеке и ждут разбора."
                    : kindleConnected
                      ? "Kindle подключён — заберите слова, которые вы искали, пока читали."
                      : "Все находки разобраны. Подключите Kindle, когда дочитаете следующую главу."}
                </p>
                <div className="home-metrics-row">
                  <dl className="home-metrics">
                    <div><dt>{ruCount(latestBook.words, "слово из книги", "слова из книги", "слов из книги")}</dt><dd>{latestBook.words}</dd></div>
                    <div><dt>{ruCount(latestBook.lookups, "просмотр в Kindle", "просмотра в Kindle", "просмотров в Kindle")}</dt><dd>{latestBook.lookups}</dd></div>
                    <div><dt>{ruCount(freshCount, "новое в библиотеке", "новых в библиотеке", "новых в библиотеке")}</dt><dd>{freshCount}</dd></div>
                  </dl>
                  {latestBook.latest ? <p className="home-note home-metrics-note">← последний поиск {formatDate(latestBook.latest, { day: "numeric", month: "long" })}</p> : null}
                </div>
                <div className="home-actions">
                  {freshCount > 0 ? (
                    <>
                      <button type="button" className="reading-primary-button" onClick={onNewWords}>
                        Разобрать {freshCount} {ruCount(freshCount, "новое", "новых", "новых")}
                        <ArrowRight size={17} strokeWidth={1.8} />
                      </button>
                      {syncButton(false)}
                    </>
                  ) : (
                    <>
                      {syncButton(true)}
                      <button type="button" className="reading-text-button" onClick={onBooks}>Все книги <ArrowRight size={16} /></button>
                    </>
                  )}
                </div>
                {!kindleConnected && connectors.kindle.state !== "unknown" ? <p className="home-hint">Подключите Kindle по USB, чтобы забрать новые слова.</p> : null}
              </div>
            </>
          ) : (
            <div className="home-hero-text home-hero-empty">
              <p className="home-eyebrow">Первая синхронизация</p>
              <h2 id="home-hero-title" className="home-book-title">Ваша история чтения начинается здесь</h2>
              <p className="home-lede">Подключите Kindle по USB: книги и слова, которые вы искали в словаре, появятся здесь.</p>
              <div className="home-actions">
                <button type="button" className="reading-primary-button" onClick={onSync} disabled={busy}>
                  <RefreshCw size={17} strokeWidth={1.7} className={syncing ? "animate-spin" : undefined} />
                  Проверить Kindle
                </button>
              </div>
            </div>
          )}
          <PencilRule variant={2} className="home-desk-line" />
        </section>

        <div className="home-lower">
          <section className="home-recent" aria-labelledby="home-recent-title">
            <div className="home-section-head">
              <h2 id="home-recent-title">Недавние слова</h2>
              <button type="button" className="reading-text-button" onClick={() => onWords()}>Все слова <ArrowRight size={16} /></button>
            </div>
            {recent.length ? (
              <ul className="home-entries">
                {recent.map((entry, index) => {
                  const occurrence = entry.occurrences[0];
                  const meaning = meaningOf(entry);
                  const pos = partOfSpeechShort(entry.processing.analysis?.pos);
                  return (
                    <li key={entry.id}>
                      <button type="button" className="home-entry" onClick={() => onWords(entry.id)}>
                        <span className="home-entry-text">
                          <strong>{entry.lemma}</strong>
                          {pos ? <em> {pos}</em> : null}
                          {meaning ? <> — {meaning}</> : <span className="home-entry-context"> — {occurrence?.context || "контекст пока не найден"}</span>}
                        </span>
                        <span className="home-entry-book">{occurrence?.book_title || "Без книги"}</span>
                      </button>
                      {index < recent.length - 1 ? <PencilRule variant={index} /> : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="home-empty">После первой синхронизации здесь появятся слова из ваших книг.</p>
            )}
          </section>

          <section className={cn("home-review lamp-host", !reviewLit && "is-quiet")} aria-labelledby="home-review-title">
            <ClipLamp lit={reviewLit} />
            <PencilFrame />
            <CornerCurl className="home-curl-start" />
            <CornerCurl className="home-curl-end" />
            <h2 id="home-review-title">{reviewLit ? "Пора повторить" : "Повторение"}</h2>
            {reviewLit ? (
              <>
                <p className="home-review-count">
                  <strong>{dueCount}</strong>
                  <span>{ruCount(dueCount, "слово", "слова", "слов")}<br />{dueCount === 1 ? "ждёт" : "ждут"} сегодня</span>
                </p>
                <p className="home-note">≈ {minutes} мин на всё</p>
                <button type="button" className="reading-primary-button" onClick={onReview}>Начать повторение</button>
              </>
            ) : (
              <>
                <p className="home-review-quiet">На сегодня всё повторено. Лампа зажжётся, когда подойдут новые карточки.</p>
                <button type="button" className="reading-secondary-button" onClick={onReview}><PencilFrame />Открыть повторение</button>
              </>
            )}
          </section>

          <section className="home-library" aria-labelledby="home-library-title">
            <div className="home-section-head">
              <h2 id="home-library-title">Библиотека</h2>
              <button type="button" className="reading-text-button" onClick={onBooks}>Все книги</button>
            </div>
            {books.length ? (
              <button type="button" className="home-shelf" onClick={onBooks} aria-label="Открыть книги">
                {books.slice(0, 4).map((book, index) => (
                  <span key={book.key} className={cn("home-spine", `home-spine-${index}`)}>
                    <PencilFrame variant={index} />
                    <span>{book.title}</span>
                  </span>
                ))}
                <PencilRule variant={1} className="home-shelf-line" />
              </button>
            ) : null}
            <dl className="home-ledger">
              <div><dt>{ruCount(books.length, "Книга", "Книги", "Книг")}</dt><dd>{books.length}</dd></div>
              <div><dt>Готовых карточек</dt><dd>{readyCount}</dd></div>
              <div><dt>Ждут Anki</dt><dd>{ankiPending}</dd></div>
            </dl>
            {ankiPending > 0 ? <button type="button" className="reading-text-button" onClick={onSendToAnki} disabled={busy}>Отправить в Anki <ArrowRight size={16} /></button> : null}
          </section>
        </div>
      </div>
    </main>
  );
}
