import type { LexemeRecord } from "@/types";
import { primaryOccurrence, russianMeaning } from "./domain";

export type CardDraft = { meaning: string; exampleId: string };
export type CardChanges = { meaning_ru?: string; example_occurrence_id?: string };

export function cardDraft(entry: LexemeRecord): CardDraft {
  return {
    meaning: entry.card?.meaning_ru ?? russianMeaning(entry)?.text ?? "",
    exampleId: entry.card?.example_occurrence_id ?? primaryOccurrence(entry)?.id ?? "",
  };
}

export function cardChanges(original: CardDraft, draft: CardDraft): CardChanges {
  const changes: CardChanges = {};
  if (draft.meaning !== original.meaning) changes.meaning_ru = draft.meaning;
  if (draft.exampleId !== original.exampleId) changes.example_occurrence_id = draft.exampleId;
  return changes;
}

export function selectedExample(entry: LexemeRecord, id: string) {
  return entry.occurrences.find((occurrence) => occurrence.id === id);
}

export function worthLearning(entry: LexemeRecord): boolean {
  if (entry.ranking) return entry.ranking.shelf === "worth";
  if (entry.decision) return entry.decision.value === "learn";
  return entry.processing.state === "ready" && entry.processing.analysis?.accepted !== false;
}
