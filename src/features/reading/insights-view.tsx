import { useMemo } from "react";
import type { BookOption, LexemeRecord } from "@/types";
import { PageHead } from "@/components/page-head";
import { Flourish, PencilRule } from "@/components/sketch/sketch";
import { activityDays, bookStats, dateKey, formatDate, repeatedLookupStats, ruCount } from "./reading-domain";

export type InsightsViewProps = {
  books: BookOption[];
  entries: LexemeRecord[];
  onOpenWord?: (entry: LexemeRecord) => void;
};

export function InsightsView({ books, entries, onOpenWord }: InsightsViewProps) {
  const bookData = useMemo(() => bookStats(books, entries), [books, entries]);
  const activity = useMemo(() => activityDays(entries), [entries]);
  const repeats = useMemo(() => repeatedLookupStats(entries), [entries]);
  const totalLookups = useMemo(() => entries.reduce((sum, entry) => sum + entry.occurrences.length, 0), [entries]);
  const datedFirstSeen = useMemo(() => entries.reduce((sum, entry) => sum + (dateKey(entry.first_seen_at) ? 1 : 0), 0), [entries]);
  const mostRepeated = useMemo(() => entries
    .filter((entry) => entry.occurrences.length > 1)
    .sort((left, right) => right.occurrences.length - left.occurrences.length || left.lemma.localeCompare(right.lemma))
    .slice(0, 6), [entries]);
  const readBooks = bookData.filter((item) => item.lookupCount > 0);
  const maxDaily = Math.max(1, ...activity.flatMap((day) => [day.firstSeen, day.lookups]));
  const activeDays = activity.filter((day) => day.firstSeen > 0 || day.lookups > 0).length;

  return (
    <main className="reading-page app-scrollbar">
      <div className="screen-page">
        <PageHead title="Аналитика" lede="Как растёт ваш словарь — по данным из вашей библиотеки." />

        {entries.length === 0 ? (
          <div className="screen-empty">
            <Flourish />
            <h2>Пока нечего считать</h2>
            <p>Когда слова с читалки появятся в библиотеке, здесь будут ваши обращения к словарю и их даты.</p>
          </div>
        ) : (
          <>
            <dl className="insights-figures">
              <Figure label="слов в библиотеке" value={entries.length} detail="уникальных лемм" />
              <Figure label="обращений к словарю" value={totalLookups} detail="из сохранённых контекстов" />
              <Figure label={ruCount(readBooks.length, "книга", "книги", "книг")} value={readBooks.length} detail="с найденными словами" />
              <Figure label="повторных обращений" value={repeats.extraLookups} detail={`${repeats.words} ${ruCount(repeats.words, "слово искали", "слова искали", "слов искали")} больше раза`} />
            </dl>

            <section className="insights-section" aria-labelledby="insights-days">
              <div className="insights-section-head">
                <div>
                  <h2 id="insights-days">Слова и обращения по дням</h2>
                  <p>14 дней до последней записи</p>
                </div>
                <div className="insights-legend">
                  <span><i className="insights-swatch is-new" />новые слова</span>
                  <span><i className="insights-swatch is-lookup" />обращения</span>
                </div>
              </div>
              {activity.length === 0 ? (
                <p className="screen-note">У записей нет дат добавления или обращения — динамику пока не показать.</p>
              ) : (
                <>
                  <div className="insights-chart" role="img" aria-label={`За показанные 14 дней: ${activeDays} ${ruCount(activeDays, "день", "дня", "дней")} с записями`}>
                    {activity.map((day, index) => (
                      <div key={day.date} className="insights-day" title={`${formatDate(day.date)}: ${day.firstSeen} новых слов, ${day.lookups} обращений`}>
                        <span className="insights-bar is-new" style={{ height: day.firstSeen ? `${Math.max(3, (day.firstSeen / maxDaily) * 100)}%` : 0 }} />
                        <span className="insights-bar is-lookup" style={{ height: day.lookups ? `${Math.max(3, (day.lookups / maxDaily) * 100)}%` : 0 }} />
                        {index % 3 === 0 || index === activity.length - 1 ? <span className="insights-date">{formatDate(day.date, { day: "numeric", month: "short" })}</span> : null}
                      </div>
                    ))}
                  </div>
                  <PencilRule variant={1} className="insights-baseline" />
                  <p className="insights-foot">
                    <span>{activeDays} {ruCount(activeDays, "день", "дня", "дней")} с записями</span>
                    <span className="home-note">последняя запись — {formatDate(activity[activity.length - 1].date, { day: "numeric", month: "long" })}</span>
                  </p>
                </>
              )}
            </section>

            <div className="insights-columns">
              <section className="insights-section" aria-labelledby="insights-books">
                <div className="insights-section-head">
                  <div>
                    <h2 id="insights-books">По книгам</h2>
                    <p>Разные слова и все обращения</p>
                  </div>
                </div>
                {readBooks.length === 0 ? (
                  <p className="screen-note">У слов ещё нет привязки к книгам.</p>
                ) : (
                  <ol className="insights-bibliography">
                    {readBooks.map((item) => (
                      <li key={item.book.key}>
                        <span className="insights-book">{item.author ? <>{item.author}. </> : null}<em>{item.book.label}</em></span>
                        <span className="insights-leader" aria-hidden="true" />
                        <span className="insights-book-count">{item.wordCount} {ruCount(item.wordCount, "слово", "слова", "слов")} · {item.lookupCount} {ruCount(item.lookupCount, "обращение", "обращения", "обращений")}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="insights-section" aria-labelledby="insights-repeats">
                <div className="insights-section-head">
                  <div>
                    <h2 id="insights-repeats">К чему возвращались</h2>
                    <p>Слова, которые вы искали больше одного раза</p>
                  </div>
                </div>
                {mostRepeated.length === 0 ? (
                  <p className="screen-note">Повторных обращений пока нет.</p>
                ) : (
                  <ul className="dict-list">
                    {mostRepeated.map((entry, index) => (
                      <li key={entry.id}>
                        {onOpenWord ? (
                          <button type="button" className="dict-entry" onClick={() => onOpenWord(entry)}>
                            <span className="dict-entry-text"><strong>{entry.display_form || entry.lemma}</strong></span>
                            <span className="dict-entry-aside">{entry.occurrences.length} {ruCount(entry.occurrences.length, "обращение", "обращения", "обращений")}</span>
                          </button>
                        ) : (
                          <div className="dict-entry">
                            <span className="dict-entry-text"><strong>{entry.display_form || entry.lemma}</strong></span>
                            <span className="dict-entry-aside">{entry.occurrences.length} {ruCount(entry.occurrences.length, "обращение", "обращения", "обращений")}</span>
                          </div>
                        )}
                        {index < mostRepeated.length - 1 ? <PencilRule variant={index} /> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
            {datedFirstSeen < entries.length ? <p className="screen-note">У части слов нет даты добавления: они учтены в общем счёте, но не на графике.</p> : null}
          </>
        )}
      </div>
    </main>
  );
}

function Figure({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="insights-figure">
      <dt>{label}</dt>
      <dd>{value.toLocaleString("ru-RU")}</dd>
      <dd className="insights-figure-detail">{detail}</dd>
    </div>
  );
}
