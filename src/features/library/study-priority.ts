import type { BookOption, LexemeRecord, StudyPriority, StudyPrioritySource } from "@/types";
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
  return priorityOrder || compareIds(left, right);
}

function compareIds(left: LexemeRecord, right: LexemeRecord): number {
  if (left.id === right.id) return 0;
  return left.id < right.id ? -1 : 1;
}

function coverageClass(priority: StudyPriority): number {
  if (priority.level === 10) return 2;
  return priority.provisional ? 1 : 0;
}

export function compareCoveragePriority(left: LexemeRecord, right: LexemeRecord): number {
  const a = studyPriority(left);
  const b = studyPriority(right);
  const aClass = coverageClass(a);
  const bClass = coverageClass(b);
  return aClass - bClass || a.level - b.level || b.score - a.score || compareIds(left, right);
}

export function studyPriorityComparator(source?: StudyPrioritySource) {
  return isRpV2Priority(source) ? compareCoveragePriority : compareStudyPriority;
}

export function isRpV2Priority(source?: StudyPrioritySource): boolean {
  return source === "rp-v2-coverage" || source === "rp-v2-personal";
}

export function hasFullBookCoverage(entry: LexemeRecord, source?: StudyPrioritySource): boolean {
  const priority = entry.study_priority;
  if (!isRpV2Priority(source) || !priority || priority.provisional || priority.level === 10) return false;
  if (source === "rp-v2-coverage" && priority.coverage_score === undefined) return priority.score === 1;
  return priority.coverage_score === 1;
}

export function previewPriorityReason(priority: StudyPriority): string {
  return priority.personal_reason || priority.reason;
}

export function priorityEntries(entries: LexemeRecord[], query: string, book: BookOption | undefined, level: PriorityFilter, source?: StudyPrioritySource): LexemeRecord[] {
  return filterLexemes(entries, query, book, "all", studyPriorityComparator(source))
    .filter((entry) => level === "all" || studyPriority(entry).level === level);
}

export function recordedSearchEvidence(occurrences: LexemeRecord["occurrences"]): string {
  const records = new Set<string>();
  const books = new Set<string>();
  for (const occurrence of occurrences) {
    const id = occurrence.id.trim();
    if (occurrence.source !== "kindle" || !id) continue;
    records.add(id);
    const book = occurrence.book_key.trim();
    if (book) books.add(book);
  }
  if (!records.size) return "";
  return `Записей поиска: ${records.size}${books.size ? ` · Книг в записях: ${books.size}` : ""}`;
}

export function decisionLabel(entry: LexemeRecord): string {
  if (!entry.decision) return "Вы ещё не выбирали";
  return { learn: "Учить", skip: "Не учить", known: "Знаю", junk: "Не слово" }[entry.decision.value];
}
