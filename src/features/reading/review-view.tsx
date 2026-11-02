import * as React from "react";
import { ArrowRight, BookOpen } from "lucide-react";
import { callBackend } from "@/lib/backend";
import type { DictionaryMeaning, LexemeOccurrence, WordAnalysis } from "@/types";
import { Button } from "@/components/ui/button";
import { PageHead } from "@/components/page-head";
import { DeskLamp } from "@/components/light/light";
import { Flourish, PencilFrame, PencilRule } from "@/components/sketch/sketch";
import { cn } from "@/lib/utils";
import { ruCount } from "./reading-domain";

type ReviewCard = {
  lexeme_id: string;
  lemma: string;
  display_form: string;
  analysis?: WordAnalysis | null;
  dictionary?: DictionaryMeaning | null;
  occurrences: LexemeOccurrence[];
  review: { due_at: string; interval_days: number; repetitions: number; last_rating: string; reviewed_at: string };
};

type ReviewResult = { cards: ReviewCard[]; due_count: number; total_count: number };
type Rating = "again" | "hard" | "good";

const ratings: Array<{ rating: Rating; label: string; hint: string; key: string }> = [
  { rating: "again", label: "Не знаю", hint: "скоро снова", key: "1" },
  { rating: "hard", label: "Трудно", hint: "повторить раньше", key: "2" },
  { rating: "good", label: "Знаю", hint: "отложить", key: "3" },
];

function cloze(card: ReviewCard) {
  const context = card.occurrences.find((item) => item.context)?.context ?? "";
  if (!context) return "";
  const word = card.occurrences.find((item) => item.context)?.word || card.display_form || card.lemma;
  const position = context.toLocaleLowerCase().indexOf(word.toLocaleLowerCase());
  if (position < 0) return context;
  return `${context.slice(0, position)}______${context.slice(position + word.length)}`;
}

export function ReviewView({ onCountsChange, onOpenWords }: { onCountsChange: (due: number) => void; onOpenWords: () => void }) {
  const [result, setResult] = React.useState<ReviewResult | null>(null);
  const [revealed, setRevealed] = React.useState(false);
  const [working, setWorking] = React.useState(false);
  const [error, setError] = React.useState("");
  const [completed, setCompleted] = React.useState(0);

  const refresh = React.useCallback(async () => {
    const next = await callBackend<ReviewResult>("load_review", { limit: 20 });
    setResult(next);
    onCountsChange(next.due_count);
    setRevealed(false);
  }, [onCountsChange]);

  React.useEffect(() => {
    let mounted = true;
    void callBackend<ReviewResult>("load_review", { limit: 20 })
      .then((next) => { if (mounted) { setResult(next); onCountsChange(next.due_count); } })
      .catch((cause) => { if (mounted) setError(String(cause)); });
    return () => { mounted = false; };
  }, [onCountsChange]);

  const card = result?.cards[0];
  const rate = React.useCallback(async (rating: Rating) => {
    if (!card || working) return;
    setWorking(true);
    setError("");
    try {
      await callBackend("rate_review", { lexeme_id: card.lexeme_id, rating });
      setCompleted((count) => count + 1);
      await refresh();
    } catch (cause) {
      setError(String(cause));
    } finally {
      setWorking(false);
    }
  }, [card, refresh, working]);

  // Space shows the answer; 1, 2 and 3 rate it, so a session needs no mouse.
  React.useEffect(() => {
    if (!card) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable]")) return;
      if (!revealed && (event.key === " " || event.key === "Enter")) {
        event.preventDefault();
        setRevealed(true);
        return;
      }
      const choice = revealed ? ratings.find((item) => item.key === event.key) : undefined;
      if (choice) void rate(choice.rating);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, rate, revealed]);

  const context = card ? cloze(card) : "";
  const answer = card ? card.analysis?.russian_meanings || card.dictionary?.meaning_ru || "" : "";
  const done = Boolean(result) && !card;

  return (
    <main className="reading-page app-scrollbar">
      <div className="screen-page review-page">
        <PageHead title="Повторение" lede="Слова, которые встретились вам во время чтения.">
          {result ? <span className="reading-count">{result.due_count} сейчас · {result.total_count} в колоде</span> : null}
        </PageHead>

        {error ? <div className="reading-error" role="alert">{error}<button type="button" onClick={() => void refresh()}>Повторить запрос</button></div> : null}

        <div className="review-desk lamp-host">
          <DeskLamp lit={Boolean(card)} />
          <article className={cn("review-card", card && "is-lit")} aria-live="polite">
            <PencilFrame />
            <span className="review-card-light" aria-hidden="true" />
            {!result && !error ? <p className="review-card-loading">Загружаем карточки…</p> : null}
            {done ? (
              <div className="review-done">
                <Flourish />
                <h2>На сегодня всё</h2>
                <p className="home-note">лампа погашена до завтра</p>
                <p>{completed ? `Вы повторили ${completed} ${ruCount(completed, "слово", "слова", "слов")}. Хорошая работа.` : "Сейчас нет слов для повторения. Обработанные слова придут сюда в своё время."}</p>
                <Button variant="secondary" onClick={onOpenWords}>Открыть слова <ArrowRight size={16} /></Button>
              </div>
            ) : null}
            {card ? (
              <>
                <header className="review-card-top">
                  <span>Карточка {completed + 1}</span>
                  <span>{result?.due_count ?? 0} {ruCount(result?.due_count ?? 0, "осталась", "осталось", "осталось")}</span>
                </header>
                <PencilRule variant={1} className="review-card-rule" />
                <h2 className="review-lemma">{card.lemma}</h2>
                {context ? <blockquote className="word-context review-context"><p>{context}</p></blockquote> : <p className="review-muted">Контекст из Kindle не найден.</p>}
                {card.occurrences[0]?.book_title ? <p className="review-source"><BookOpen size={14} />{card.occurrences[0].book_title}</p> : null}
                {revealed ? (
                  <div className="review-answer">
                    <span className="home-note">ответ</span>
                    <strong>{answer || card.display_form}</strong>
                    {card.dictionary?.meaning_ru && !card.analysis?.russian_meanings ? <p className="word-card-source">значения по Викисловарю</p> : null}
                    {!answer ? <p className="review-muted">Перевода пока нет — сравните слово с контекстом выше.</p> : null}
                    {card.occurrences[0]?.context ? <p className="review-muted">{card.occurrences[0].context}</p> : null}
                  </div>
                ) : (
                  <button type="button" className="reading-primary-button review-reveal" onClick={() => setRevealed(true)}>Показать ответ <ArrowRight size={16} /></button>
                )}
              </>
            ) : null}
          </article>
          <PencilRule variant={2} className="review-desk-line" />
        </div>

        {card ? (
          revealed ? (
            <div className="review-ratings" role="group" aria-label="Как хорошо вы помните слово">
              {ratings.map((item) => (
                <Button key={item.rating} variant="secondary" size="lg" disabled={working} onClick={() => void rate(item.rating)} aria-keyshortcuts={item.key}>
                  <span className="review-rating-key" aria-hidden="true">{item.key}</span>
                  <span className="review-rating-text">{item.label}<small>{item.hint}</small></span>
                </Button>
              ))}
            </div>
          ) : (
            <p className="review-tip">Вспомните значение, потом откройте ответ · <kbd>Пробел</kbd> — ответ, <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> — оценка</p>
          )
        ) : null}
      </div>
    </main>
  );
}
