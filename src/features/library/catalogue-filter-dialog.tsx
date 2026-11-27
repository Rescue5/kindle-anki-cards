import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, SlidersHorizontal } from "lucide-react";
import { ClipLamp } from "@/components/light/light";
import { PencilRule } from "@/components/sketch/sketch";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { BookOption } from "@/types";
import { defaultCatalogueFilters, type CatalogueDecision, type CatalogueFilters } from "./catalogue-selectors";
import "./catalogue-filter-dialog.css";

export const decisionOptions: ReadonlyArray<{ value: CatalogueDecision; label: string }> = [
  { value: "visible", label: "Без «Не учить»" },
  { value: "all", label: "Все решения" },
  { value: "undecided", label: "Без решения" },
  { value: "learn", label: "Учить" },
  { value: "skip", label: "Не учить" },
  { value: "known", label: "Знаю" },
  { value: "junk", label: "Не слово" },
];

const priorityLevels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

type Props = {
  filters: CatalogueFilters;
  books: readonly BookOption[];
  bookKey: string;
  onApply: (filters: CatalogueFilters, bookKey: string) => void;
  triggerRef: React.Ref<HTMLButtonElement>;
};

export function CatalogueFilterDialog({ filters, books, bookKey, onApply, triggerRef }: Props) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState(filters);
  const [draftBookKey, setDraftBookKey] = React.useState(bookKey);
  const titleRef = React.useRef<HTMLHeadingElement>(null);
  const scaleId = React.useId();
  const activeCount = Number(filters.levels.length > 0) + Number(filters.decision !== "visible")
    + Number(filters.recent) + Number(bookKey !== "");

  function changeOpen(nextOpen: boolean) {
    if (nextOpen) {
      setDraft(filters);
      setDraftBookKey(bookKey);
    }
    setOpen(nextOpen);
  }

  function toggleLevel(level: number, checked: boolean) {
    setDraft((current) => ({
      ...current,
      levels: checked
        ? [...current.levels, level].sort((left, right) => left - right)
        : current.levels.filter((value) => value !== level),
    }));
  }

  function reset() {
    setDraft({ ...defaultCatalogueFilters, sort: draft.sort });
    setDraftBookKey("");
  }

  return (
    <Dialog.Root open={open} onOpenChange={changeOpen}>
      <Dialog.Trigger asChild>
        <Button ref={triggerRef} type="button" id="library-filters" variant="secondary">
          <SlidersHorizontal size={17} aria-hidden="true" />
          Фильтры{activeCount ? ` · ${activeCount}` : ""}
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="catalogue-filter-overlay" />
        <Dialog.Content
          className="catalogue-filter-dialog lamp-host"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            titleRef.current?.focus();
          }}
        >
          <ClipLamp lit className="catalogue-filter-lamp" />
          <header className="catalogue-filter-header">
            <Dialog.Title ref={titleRef} tabIndex={-1}>Фильтры слов</Dialog.Title>
          </header>
          <div className="app-scrollbar catalogue-filter-body">
            <section className="catalogue-filter-priorities" aria-labelledby={scaleId}>
              <h3 id={scaleId}>Приоритеты</h3>
              <Dialog.Description>1 — в первую очередь, 10 — проверить запись</Dialog.Description>
              <div className="catalogue-filter-levels">
                {priorityLevels.map((level) => (
                  <label className="catalogue-filter-level" key={level}>
                    <input
                      type="checkbox"
                      aria-label={`Приоритет ${level}`}
                      checked={draft.levels.includes(level)}
                      onChange={(event) => toggleLevel(level, event.target.checked)}
                    />
                    <span className="catalogue-filter-level-mark" aria-hidden="true">
                      {level}
                      <Check size={12} />
                      <PencilRule />
                    </span>
                  </label>
                ))}
              </div>
              <div className="catalogue-filter-level-tools">
                <p>Без отметок видны все уровни.</p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-disabled={!draft.levels.length}
                  onClick={() => {
                    if (draft.levels.length) setDraft({ ...draft, levels: [] });
                  }}
                >
                  Очистить уровни
                </Button>
              </div>
            </section>
            <PencilRule variant={1} />
            <div className="catalogue-filter-fields">
              <label>
                <span>Книга</span>
                <Select value={draftBookKey} onChange={(event) => setDraftBookKey(event.target.value)}>
                  <option value="">Все книги</option>
                  {books.filter(({ key }) => key).map(({ key, label }) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </Select>
              </label>
              <label>
                <span>Моё решение</span>
                <Select
                  value={draft.decision}
                  onChange={(event) => setDraft({ ...draft, decision: event.target.value as CatalogueDecision })}
                >
                  {decisionOptions.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </Select>
              </label>
            </div>
            <label className="catalogue-filter-recent">
              <input
                type="checkbox"
                checked={draft.recent}
                onChange={(event) => setDraft({ ...draft, recent: event.target.checked })}
              />
              <span className="catalogue-filter-recent-mark" aria-hidden="true"><Check size={16} /></span>
              Только последнее пополнение
            </label>
          </div>
          <footer className="catalogue-filter-footer">
            <PencilRule variant={2} />
            <Button type="button" variant="ghost" size="sm" onClick={reset}>Сбросить</Button>
            <Dialog.Close asChild><Button type="button" variant="ghost" size="sm">Отмена</Button></Dialog.Close>
            <Button
              type="button"
              onClick={() => {
                onApply(draft, draftBookKey);
                setOpen(false);
              }}
            >
              Применить
            </Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
