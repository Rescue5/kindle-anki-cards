import { useMemo, useState } from "react";
import { ImageDown, Loader2, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHead } from "@/components/page-head";
import { DeskLamp } from "@/components/light/light";
import { Flourish, PencilRule } from "@/components/sketch/sketch";
import { cn } from "@/lib/utils";
import type { BookOption, CoverSummary, LexemeRecord } from "@/types";
import { BookJacket } from "./book-jacket";
import { bookStats, formatDate, lookupsForBook, ruCount } from "./reading-domain";

export type BooksViewProps = {
  books: BookOption[];
  entries: LexemeRecord[];
  onOpenWord: (entry: LexemeRecord) => void;
  selectedBookKey?: string;
  onSelectBook?: (book: BookOption) => void;
  onDownloadCovers?: () => void;
  coversBusy?: boolean;
  coverSummary?: CoverSummary;
};

export function BooksView({ books, entries, onOpenWord, selectedBookKey, onSelectBook, onDownloadCovers, coversBusy = false, coverSummary }: BooksViewProps) {
  const stats = useMemo(() => bookStats(books, entries), [books, entries]);
  const availableCovers = stats.filter((item) => item.book.cover_data_url).length;
  const [localBookKey, setLocalBookKey] = useState("");
  const [bookQuery, setBookQuery] = useState("");
  const [wordQuery, setWordQuery] = useState("");
  const [repeatedOnly, setRepeatedOnly] = useState(false);
  const activeKey = selectedBookKey ?? localBookKey;
  const activeBook = stats.find((item) => item.book.key === activeKey) ?? stats[0];
  const shownBooks = useMemo(() => {
    const query = bookQuery.trim().toLocaleLowerCase("ru");
    return query
      ? stats.filter((item) => `${item.book.label} ${item.author}`.toLocaleLowerCase("ru").includes(query))
      : stats;
  }, [bookQuery, stats]);
  const shownWords = useMemo(() => {
    if (!activeBook) return [];
    const query = wordQuery.trim().toLocaleLowerCase("ru");
    return activeBook.words
      .filter((entry) => {
        const occurrences = lookupsForBook(entry, activeBook.book.key);
        return (!repeatedOnly || occurrences.length > 1) &&
          (!query || [entry.lemma, entry.display_form, ...entry.forms].some((form) => form.toLocaleLowerCase("ru").includes(query)));
      })
      .sort((left, right) => {
        const leftLast = lookupsForBook(left, activeBook.book.key).reduce((last, item) => item.looked_up_at > last ? item.looked_up_at : last, "");
        const rightLast = lookupsForBook(right, activeBook.book.key).reduce((last, item) => item.looked_up_at > last ? item.looked_up_at : last, "");
        return rightLast.localeCompare(leftLast) || left.lemma.localeCompare(right.lemma);
      });
  }, [activeBook, repeatedOnly, wordQuery]);

  const selectBook = (book: BookOption) => {
    setLocalBookKey(book.key);
    setWordQuery("");
    setRepeatedOnly(false);
    onSelectBook?.(book);
  };

  return (
    <main className="reading-page app-scrollbar">
      <div className="screen-page">
        <PageHead title="Книги" lede="Ваши книги и слова, которые вы искали в словаре Kindle.">
          <span className="reading-count">{stats.length} {ruCount(stats.length, "книга", "книги", "книг")} · обложки {availableCovers}/{stats.length}</span>
          {onDownloadCovers && stats.length > 0 ? (
            <Button type="button" size="sm" variant="secondary" onClick={onDownloadCovers} disabled={coversBusy} aria-busy={coversBusy}>
              {coversBusy ? <Loader2 size={15} className="animate-spin" /> : <ImageDown size={15} />}
              {coversBusy ? "Загружаем обложки" : "Загрузить обложки"}
            </Button>
          ) : null}
          {coverSummary?.errors ? <span role="status" className="screen-error-note">Часть обложек не загрузилась: {coverSummary.errors}</span> : null}
        </PageHead>

        {stats.length === 0 ? (
          <div className="screen-empty">
            <Flourish />
            <h2>Здесь появятся ваши книги</h2>
            <p>После синхронизации Kindle книги и найденные в них слова встанут на эту полку.</p>
          </div>
        ) : (
          <div className="books-layout">
            <aside className="books-shelf" aria-label="Полка">
              <div className="home-section-head">
                <h2>Полка</h2>
                <span className="reading-count">{stats.length}</span>
              </div>
              <div className="screen-search">
                <Search size={16} strokeWidth={1.7} aria-hidden="true" />
                <Input aria-label="Поиск книги" value={bookQuery} onChange={(event) => setBookQuery(event.target.value)} placeholder="Найти книгу" />
              </div>
              {shownBooks.length === 0 ? (
                <p className="screen-note">По этому запросу книг нет.</p>
              ) : (
                <ul className="books-shelf-list">
                  {shownBooks.map((item) => {
                    const active = activeBook?.book.key === item.book.key;
                    return (
                      <li key={item.book.key}>
                        <button type="button" onClick={() => selectBook(item.book)} aria-current={active ? "true" : undefined} className={cn("books-shelf-item", active && "is-active")}>
                          <BookJacket title={item.book.label} coverDataUrl={item.book.cover_data_url} size="sm" lit={active} />
                          <span className="books-shelf-text">
                            <strong>{item.book.label}</strong>
                            <span>{item.author || "Автор не указан"}</span>
                            <small>{item.wordCount} {ruCount(item.wordCount, "слово", "слова", "слов")} · {item.lookupCount} {ruCount(item.lookupCount, "обращение", "обращения", "обращений")}</small>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </aside>

            {activeBook ? (
              <section className="books-main" aria-labelledby="books-desk-title">
                <div className="books-desk lamp-host">
                  <DeskLamp lit />
                  <BookJacket title={activeBook.book.label} author={activeBook.author} coverDataUrl={activeBook.book.cover_data_url} lit />
                  <div className="books-desk-text">
                    <p className="home-eyebrow">На столе</p>
                    <h2 id="books-desk-title" className="books-desk-title">{activeBook.book.label}</h2>
                    <p className="home-book-author">{activeBook.author || "Автор не указан"}</p>
                    <dl className="home-metrics">
                      <div><dt>{ruCount(activeBook.wordCount, "слово", "разных слова", "разных слов")}</dt><dd>{activeBook.wordCount}</dd></div>
                      <div><dt>{ruCount(activeBook.lookupCount, "обращение", "обращения", "обращений")}</dt><dd>{activeBook.lookupCount}</dd></div>
                      <div><dt>искали повторно</dt><dd>{activeBook.repeatedWordCount}</dd></div>
                    </dl>
                    {activeBook.lastLookupAt ? <p className="home-note books-desk-note">последний поиск — {formatDate(activeBook.lastLookupAt, { day: "numeric", month: "long", year: "numeric" })}</p> : null}
                  </div>
                  <PencilRule variant={2} className="books-desk-line" />
                </div>

                <div className="books-words-head">
                  <div>
                    <h3>Слова из книги</h3>
                    <p>Откройте слово, чтобы увидеть контекст и обработку.</p>
                  </div>
                  <div className="books-words-tools">
                    <Button type="button" size="sm" variant="secondary" aria-pressed={repeatedOnly} onClick={() => setRepeatedOnly((value) => !value)}>Повторные · {activeBook.repeatedWordCount}</Button>
                    <div className="screen-search books-word-search">
                      <Search size={15} strokeWidth={1.7} aria-hidden="true" />
                      <Input aria-label="Поиск слова в книге" value={wordQuery} onChange={(event) => setWordQuery(event.target.value)} placeholder="Найти слово" />
                      {wordQuery ? <button type="button" aria-label="Очистить поиск" onClick={() => setWordQuery("")} className="screen-search-clear"><X size={14} /></button> : null}
                    </div>
                  </div>
                </div>

                {shownWords.length === 0 ? (
                  <p className="screen-note">{activeBook.wordCount === 0 ? "По этой книге пока нет обращений к словарю." : "Слова по выбранному фильтру не найдены."}</p>
                ) : (
                  <ul className="dict-list">
                    {shownWords.map((entry, index) => {
                      const occurrences = lookupsForBook(entry, activeBook.book.key);
                      const context = occurrences.find((item) => item.context)?.context;
                      return (
                        <li key={entry.id}>
                          <button type="button" className="dict-entry" onClick={() => onOpenWord(entry)}>
                            <span className="dict-entry-text">
                              <strong>{entry.display_form || entry.lemma}</strong>
                              <span className="dict-entry-context"> — {context || "контекст не сохранён"}</span>
                            </span>
                            <span className="dict-entry-aside">{occurrences.length} {ruCount(occurrences.length, "обращение", "обращения", "обращений")}</span>
                          </button>
                          {index < shownWords.length - 1 ? <PencilRule variant={index} /> : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            ) : null}
          </div>
        )}
      </div>
    </main>
  );
}
