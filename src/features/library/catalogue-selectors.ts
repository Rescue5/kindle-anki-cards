import type { BookOption, DecisionValue, LexemeRecord, StudyPrioritySource } from "@/types";
import { filterLexemes } from "./domain";
import { hasFullBookCoverage, isRpV2Priority, studyPriority, studyPriorityComparator } from "./study-priority";

export const CATALOGUE_PRIORITY_GROUPS = [
  { label: "1–3 · В первую очередь", levels: [1, 2, 3] },
  { label: "4–6 · Средний приоритет", levels: [4, 5, 6] },
  { label: "7–9 · Можно отложить", levels: [7, 8, 9] },
  { label: "10 · Проверить запись", levels: [10] },
] as const;

export type CatalogueDecision = "visible" | "all" | "undecided" | DecisionValue;
export type CatalogueSort = "priority" | "added";

export type CatalogueFilters = {
  levels: readonly number[];
  decision: CatalogueDecision;
  recent: boolean;
  sort: CatalogueSort;
};

export const defaultCatalogueFilters: CatalogueFilters = {
  levels: [],
  decision: "visible",
  recent: false,
  sort: "priority",
};

function matchesDecision(entry: LexemeRecord, filter: CatalogueDecision): boolean {
  const decision = entry.decision?.value;
  if (filter === "all") return true;
  if (filter === "visible") return decision !== "skip";
  if (filter === "undecided") return !decision;
  return decision === filter;
}

export function selectCatalogueEntries(
  entries: LexemeRecord[],
  query: string,
  book: BookOption | undefined,
  filters: CatalogueFilters,
  source?: StudyPrioritySource,
  showFullCoverage = false,
): LexemeRecord[] {
  const { levels, decision, recent, sort } = filters;
  const narrowed = entries.filter((entry) => (!recent || entry.freshness === "new")
    && (showFullCoverage || !hasFullBookCoverage(entry, source))
    && matchesDecision(entry, decision) && (!levels.length || levels.includes(studyPriority(entry).level)));
  const priorityOrder = studyPriorityComparator(source);
  if (sort === "priority") return filterLexemes(narrowed, query, book, "all", priorityOrder);
  const addedAt = new Map(narrowed.map((entry) => {
    const timestamp = Date.parse(entry.first_seen_at);
    return [entry.id, Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY];
  }));
  return filterLexemes(narrowed, query, book, "all", (left, right) =>
    (addedAt.get(right.id)! - addedAt.get(left.id)!) || priorityOrder(left, right));
}

export function selectTranslationEntries(entries: readonly LexemeRecord[], eligibleIds: ReadonlySet<string>): LexemeRecord[] {
  return entries.filter(({ id }) => eligibleIds.has(id));
}

export function catalogueGroup(entry: LexemeRecord, source?: StudyPrioritySource): string {
  const priority = studyPriority(entry);
  if (isRpV2Priority(source) && priority.provisional && priority.level !== 10) return "Предварительные оценки";
  return CATALOGUE_PRIORITY_GROUPS.find(({ levels }) => (levels as readonly number[]).includes(priority.level))?.label
    ?? "Другие оценки";
}
