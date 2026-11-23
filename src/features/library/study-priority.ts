import type { BookOption, LexemeRecord } from "@/types";
import { filterLexemes } from "./domain";

export type PriorityFilter = "all" | number;

/** Older library payloads stay visible while the bridge is being updated. */
export function studyPriority(entry: LexemeRecord): NonNullable<LexemeRecord["study_priority"]> {
  return entry.study_priority ?? {
    level: 6,
    score: 0,
    provisional: true,
    reason: "Данные для приоритета ещё не получены.",
  };
}

export function compareStudyPriority(left: LexemeRecord, right: LexemeRecord): number {
  const a = studyPriority(left);
  const b = studyPriority(right);
  const priorityOrder = a.level - b.level || Number(a.provisional) - Number(b.provisional) || b.score - a.score;
  if (priorityOrder) return priorityOrder;
  if (left.id === right.id) return 0;
  return left.id < right.id ? -1 : 1;
}

export function priorityEntries(entries: LexemeRecord[], query: string, book: BookOption | undefined, level: PriorityFilter): LexemeRecord[] {
  return filterLexemes(entries, query, book, "all", compareStudyPriority)
    .filter((entry) => level === "all" || studyPriority(entry).level === level);
}

export function decisionLabel(entry: LexemeRecord): string {
  if (!entry.decision) return "Вы ещё не выбирали";
  return { learn: "Учить", skip: "Не учить", known: "Знаю", junk: "Не слово" }[entry.decision.value];
}
