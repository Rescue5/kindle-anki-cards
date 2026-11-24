import * as React from "react";
import { Button } from "@/components/ui/button";
import { ClipLamp } from "@/components/light/light";
import { PencilFrame } from "@/components/sketch/sketch";
import { MEANING_MAX_LENGTH, type DecisionValue, type LexemeRecord, type StudyPrioritySource } from "@/types";
import { cardChanges, cardDraft, selectedExample, type CardChanges, type CardDraft } from "./card-editor-domain";
import { isCardEligible, obsidianSyncReason, partOfSpeechLabel, processingLabel, russianMeaning } from "./domain";
import { decisionLabel, isRpV2Priority, recordedSearchEvidence, studyPriority } from "./study-priority";

type Props = {
  entry: LexemeRecord;
  prioritySource?: StudyPrioritySource;
  readOnly: boolean;
  busy: boolean;
  llmEnabled: boolean;
  onEnrich: (id: string, retryFailed: boolean) => void;
  headingRef: React.RefObject<HTMLHeadingElement>;
  onSave: (id: string, changes: CardChanges) => Promise<void>;
  onDecision: (id: string, decision: DecisionValue | null) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
  onPendingChange: (pending: boolean) => void;
};

export function CardEditor({ entry, prioritySource, readOnly, busy, llmEnabled, onEnrich, headingRef, onSave, onDecision, onDirtyChange, onPendingChange }: Props) {
  const [original, setOriginal] = React.useState(() => cardDraft(entry));
  const [draft, setDraft] = React.useState<CardDraft>(original);
  const [pending, setPending] = React.useState(false);
  const pendingRef = React.useRef(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");
  const changes = cardChanges(original, draft);
  const dirty = Object.keys(changes).length > 0;
  const disabled = readOnly || busy || pending;
  const example = selectedExample(entry, draft.exampleId);
  const examples = entry.occurrences.filter((item) => item.context.trim());
  const fallbackMeaning = russianMeaning(entry)?.text || "";
  const tooLong = changes.meaning_ru !== undefined && [...draft.meaning].length > MEANING_MAX_LENGTH;
  const priority = studyPriority(entry);
  const searchEvidence = recordedSearchEvidence(entry.occurrences);

  // Background library refreshes may update the effective card. Keep an active draft intact.
  React.useEffect(() => {
    if (dirty || pending) return;
    const next = cardDraft(entry);
    setOriginal(next);
    setDraft(next);
  }, [entry, dirty, pending]);
  React.useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  React.useEffect(() => { onPendingChange(pending); }, [pending, onPendingChange]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (disabled || pendingRef.current || !dirty || tooLong) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    setMessage("");
    try {
      await onSave(entry.id, changes);
      setOriginal(draft);
      setMessage("Сохранено для следующей выгрузки");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Не удалось сохранить. Попробуйте ещё раз.");
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  async function decide(decision: DecisionValue | null) {
    if (disabled || dirty || pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    setMessage("");
    try {
      await onDecision(entry.id, decision);
      setMessage(decision === null ? "Решение снято" : decision === "learn" ? "Вы выбрали учить это слово" : "Вы решили не учить это слово");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Не удалось изменить отбор. Попробуйте ещё раз.");
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  return <section className="app-scrollbar words-inspector-scroll">
    <article className="word-card lamp-host">
      <ClipLamp lit={!readOnly} />
      <PencilFrame />
      <div className="word-card-head"><h2 ref={headingRef} tabIndex={-1}>{entry.lemma}</h2></div>
      {readOnly ? <p className="words-meta">Пример · только просмотр</p> : null}
      <div className="card-priority">
        <p>Приоритет {priority.level} из 10{priority.provisional ? " · предварительно" : ""}</p>
        <p className="words-meta">{priority.reason}</p>
        {searchEvidence ? <p className="words-meta">{searchEvidence}</p> : null}
      </div>
      <form onSubmit={(event) => void save(event)} className="card-edit-form" aria-busy={pending}>
        <label htmlFor="card-meaning">Перевод</label>
        <textarea id="card-meaning" value={draft.meaning} disabled={disabled} rows={3}
          aria-describedby="card-meaning-hint" aria-invalid={tooLong}
          placeholder={fallbackMeaning || "Введите перевод"}
          onChange={(event) => { setDraft({ ...draft, meaning: event.target.value }); setMessage(""); }} />
        <p id="card-meaning-hint" className="words-meta">До 200 символов · {[...draft.meaning].length}/200</p>
        {tooLong ? <p role="alert" className="words-error">Сократите перевод до 200 символов.</p> : null}
        {entry.card?.meaning_source === "edited" ? <Button type="button" variant="ghost" size="sm" disabled={disabled}
          onClick={() => { setDraft({ ...draft, meaning: "" }); setMessage(""); }}>Вернуть исходный перевод</Button> : null}
        {draft.meaning === "" ? <p className="words-meta">{fallbackMeaning || "Исходного перевода пока нет."}</p> : null}

        <h3>Предложение из книги</h3>
        {examples.length > 1 ? <label className="card-example-select">Выберите предложение
          <select value={draft.exampleId} disabled={disabled} onChange={(event) => { setDraft({ ...draft, exampleId: event.target.value }); setMessage(""); }}>
            {!example?.context ? <option value={draft.exampleId}>Сохранённый пример недоступен</option> : null}
            {examples.map((item) => <option key={item.id} value={item.id}>{item.book_title || "Без названия"} — {item.context}</option>)}
          </select>
        </label> : null}
        {example?.context ? <blockquote className="word-context"><p>{example.context}</p><footer>{example.book_title || "Источник без названия"}{example.authors ? ` · ${example.authors}` : ""}</footer></blockquote>
          : <p className="words-meta">{examples.length === 1 ? "Выберите доступное предложение." : "Предложения из книги пока нет."}</p>}
        {examples.length === 1 && examples[0].id !== draft.exampleId ? <Button type="button" variant="secondary" disabled={disabled}
          onClick={() => setDraft({ ...draft, exampleId: examples[0].id })}>Использовать предложение из книги</Button> : null}
        <p className="words-meta">Правки будут использованы при следующей выгрузке.</p>
        <div className="card-edit-actions">
          <Button type="submit" disabled={disabled || !dirty || tooLong}>{pending ? "Подождите…" : "Сохранить"}</Button>
          {dirty ? <Button type="button" variant="ghost" disabled={disabled} onClick={() => { setDraft(original); setError(""); setMessage(""); }}>Отменить правки</Button> : null}
        </div>
        {error ? <p role="alert" className="words-error">{error}</p> : null}
        <p role="status" className="words-meta">{message || (dirty ? "Есть несохранённые правки" : "")}</p>
      </form>
      <div className="card-decision" aria-busy={pending}>
        <p className="words-meta">Моё решение · {decisionLabel(entry)}</p>
        <div className="card-edit-actions" role="group" aria-label="Моё решение">
          <Button variant="secondary" aria-pressed={entry.decision?.value === "learn"} disabled={disabled || dirty || entry.decision?.value === "learn"} onClick={() => void decide("learn")}>Учить</Button>
          <Button variant="ghost" aria-pressed={entry.decision?.value === "skip"} disabled={disabled || dirty || entry.decision?.value === "skip"} onClick={() => void decide("skip")}>Не учить</Button>
          {entry.decision ? <Button variant="ghost" disabled={disabled || dirty} onClick={() => void decide(null)}>Снять моё решение</Button> : null}
        </div>
      </div>
    </article>
    <details className="card-details"><summary>Подробнее о слове</summary>
      <p className="words-meta">Формы · {entry.forms.join(" · ")}</p>
      <p className="words-meta">{processingLabel(entry.processing.state)} · {partOfSpeechLabel(entry.processing.analysis?.pos)}</p>
      {!isRpV2Priority(prioritySource) ? <>
        {entry.processing.analysis?.frequency_note ? <p className="words-meta">{entry.processing.analysis.frequency_note}</p> : null}
        {entry.ranking?.reasons.map((reason) => <p className="words-meta" key={reason.code}>{reason.text}</p>)}
        {entry.processing.analysis?.importance_note ? <p className="words-meta">{entry.processing.analysis.importance_note}</p> : null}
      </> : null}
      {entry.processing.error ? <p className="words-error">{entry.processing.error}</p> : null}
      {entry.enrichment?.error ? <p className="words-error">{entry.enrichment.error}</p> : null}
      <WordTranslationDetails entry={entry} llmEnabled={llmEnabled} disabled={disabled || dirty} onEnrich={onEnrich} />
      <p className="words-meta">Obsidian · {obsidianSyncReason(entry)}</p>
      <h3>Все контексты</h3>
      {entry.occurrences.map((item) => <blockquote className="word-context" key={item.id}><p>{item.context || "Контекст отсутствует"}</p><footer>{item.book_title || "Источник без названия"}{item.authors ? ` · ${item.authors}` : ""}</footer></blockquote>)}
    </details>
  </section>;
}

export function WordTranslationDetails({ entry, llmEnabled, disabled, onEnrich }: {
  entry: LexemeRecord;
  llmEnabled: boolean;
  disabled: boolean;
  onEnrich: (id: string, retryFailed: boolean) => void;
}) {
  const enrichment = entry.enrichment;
  if (enrichment?.status === "ready") return <div className="words-translation">
    {enrichment.definition_en ? <p>{enrichment.definition_en}</p> : null}
    {enrichment.example_en ? <div><h3>Сгенерированный пример</h3><p><em>{enrichment.example_en}</em></p>
      {enrichment.example_ru ? <p>{enrichment.example_ru}</p> : null}</div> : null}
    {enrichment.note_ru ? <p>{enrichment.note_ru}</p> : null}
  </div>;
  if (!isCardEligible(entry)) return null;
  const failed = enrichment?.status === "failed";
  return <div className="words-translation">
    <p className="words-meta">{failed ? "Перевод этого слова не удался." : llmEnabled ? "Перевода по контексту ещё нет." : "Перевод по контексту можно включить в настройках."}</p>
    {llmEnabled ? <Button type="button" variant="secondary" size="sm" disabled={disabled}
      onClick={() => onEnrich(entry.id, failed)}>{failed ? "Повторить перевод слова" : "Перевести слово"}</Button> : null}
  </div>;
}
