// The browser preview's stand-in for the Python bridge. It speaks the short-list contract (C0, see
// `src/types.ts`) beside the old fields and keeps decisions, card edits and export runs in memory,
// so every screen can be built and checked without a Kindle. `?scenario=` picks the story:
//   mixed (default)   a short list, three disputed words, one exported word that came back
//   no-new            everything already exported or answered; nothing new to learn
//   export-error      the same as mixed, but `export_words` fails
//   learning          the same as mixed, ranking still rough (little history; repeat lookups are kept)
//   no-repeats        a reader that keeps no repeat lookups: learning mode, no repeat reasons
//   empty             a fresh install: no words, no reader; `load_demo` shows the example library
//   slow              also the first library load takes a few seconds (Главная shows its skeleton)
//   disconnected, slow, operation-error, lexeme-failure, showcase, anki-connected, obsidian-error,
//   llm-error         older scenarios the library screens still use
// Loaded only in a plain browser (`backend.ts` imports it lazily), never in the Tauri build.
import {
  DISPUTED_CAP,
  ERROR_TEXTS,
  EXPORT_BATCH_SIZE_DEFAULT,
  MEANING_MAX_LENGTH,
  type AgainSummary,
  type AppSettings,
  type BookOption,
  type CardFields,
  type ConnectorStatus,
  type DecisionValue,
  type DisputedSummary,
  type DictionaryMeaning,
  type Enrichment,
  type ErrorCode,
  type ExportDestination,
  type ExportPreview,
  type ExportRun,
  type LeanValue,
  type LexemeDecision,
  type LexemeDetails,
  type LexemeOccurrence,
  type LexemeRanking,
  type LexemeRecord,
  type LexemeRecordV4,
  type LibraryRanking,
  type LibraryResultV4,
  type LlmPreset,
  type NewBatch,
  type ProcessingState,
  type RankingReason,
  type SaveCardEditResult,
  type SetDecisionResult,
  type Shelf,
  type ShelfCounts,
  type StudyPriority,
  type WordAnalysis,
} from "@/types";
import { BridgeError, defaultSettings } from "./backend";

const SHELVES: Shelf[] = ["worth", "disputed", "not_worth", "junk", "known"];
const DECISIONS: DecisionValue[] = ["known", "learn", "skip", "junk"];
const RANKING_VERSION = "r2";

let scenarioOverride: string | undefined;
let instant = false;

const previewScenario = () =>
  scenarioOverride ?? (typeof window === "undefined" ? "mixed" : (new URLSearchParams(window.location.search).get("scenario") ?? "mixed"));

const isEmptyScenario = () => previewScenario() === "empty";
/** Reasons that need repeat lookups, several books or an earlier export: absent when the source keeps no repeats. */
const REPEAT_REASONS = new Set(["repeat_lookups", "after_export", "several_books"]);
const keepsRepeats = () => previewScenario() !== "no-repeats";
const rankingMode = (): "learning" | "full" => (["learning", "no-repeats"].includes(previewScenario()) ? "learning" : "full");

// ---- the invented library ----

type Spec = {
  word: string;
  lemma: string;
  pos: string;
  /** Offline Russian meaning; "" leaves the card without one. */
  meaning: string;
  /** Lookups, oldest first: sentence, book, authors, day of July. */
  lookups: [string, string, string, number][];
  state: Extract<ProcessingState, "ready" | "pending" | "rejected">;
  importance: number;
  fresh: boolean;
  shelf: Shelf;
  rankScore: number;
  /** Sample of the priority the Python bridge would return for this invented word. */
  studyLevel: number;
  lean?: LeanValue;
  reasons: RankingReason[];
};

const MIRROR = ["The Mirror's Truth", "Michael R. Fletcher"] as const;
const NIGHT = ["The Night Reader", "Demo Library"] as const;
const SHADOWS = ["Shadows and Signals", "Demo Library"] as const;

const specs: Spec[] = [
  {
    word: "admitting", lemma: "admit", pos: "v", meaning: "признавать; сознаваться",
    lookups: [["She knew the answer but shied from admitting it.", ...MIRROR, 10], ["He was slow to admit his own mistake.", ...MIRROR, 20]],
    state: "ready", importance: 10, fresh: false, shelf: "worth", rankScore: 0.42, studyLevel: 1,
    reasons: [{ code: "repeat_lookups", text: "Искали 2 раза", weight: 0.75 }, { code: "after_export", text: "Снова искали после экспорта", weight: 0.4 }],
  },
  {
    word: "glimpse", lemma: "glimpse", pos: "n", meaning: "проблеск; мимолётное впечатление",
    lookups: [["For a moment he caught a glimpse of the city below.", ...NIGHT, 9]],
    state: "pending", importance: 7, fresh: true, shelf: "worth", rankScore: 0.33, studyLevel: 2,
    reasons: [{ code: "reading_now", text: "Из книги с недавними поисками", weight: 0.5 }, { code: "frequency", text: "Не слишком частое слово", weight: 0.3 }],
  },
  {
    word: "dread", lemma: "dread", pos: "n", meaning: "страх; тревожное предчувствие",
    lookups: [["A quiet dread settled over the room.", ...SHADOWS, 8]],
    state: "pending", importance: 7, fresh: true, shelf: "worth", rankScore: 0.31, studyLevel: 2,
    reasons: [{ code: "recency", text: "Искали на этой неделе", weight: 0.4 }, { code: "frequency", text: "Не слишком частое слово", weight: 0.3 }],
  },
  {
    word: "submerged", lemma: "submerge", pos: "v", meaning: "погружать; затоплять",
    lookups: [["He tried to submerge the memory before it surfaced again.", ...NIGHT, 7]],
    state: "pending", importance: 6, fresh: false, shelf: "worth", rankScore: 0.27, studyLevel: 3,
    reasons: [{ code: "frequency", text: "Не слишком частое слово", weight: 0.35 }],
  },
  {
    word: "resilient", lemma: "resilient", pos: "a", meaning: "стойкий; жизнестойкий",
    lookups: [["Her resilient spirit never broke.", ...SHADOWS, 6], ["The town proved more resilient than anyone expected.", ...SHADOWS, 14]],
    state: "ready", importance: 7, fresh: false, shelf: "worth", rankScore: 0.25, studyLevel: 4,
    reasons: [{ code: "repeat_lookups", text: "Искали 2 раза", weight: 0.6 }],
  },
  {
    word: "vigilant", lemma: "vigilant", pos: "a", meaning: "бдительный, внимательный",
    lookups: [["They remained vigilant through the night.", ...SHADOWS, 5]],
    state: "rejected", importance: 1, fresh: false, shelf: "not_worth", rankScore: 0.08, studyLevel: 8,
    reasons: [{ code: "frequency_common", text: "Часто встречается в текстах", weight: -0.6 }],
  },
  {
    word: "ephemeral", lemma: "ephemeral", pos: "a", meaning: "мимолётный; недолговечный",
    lookups: [["Joy is an ephemeral guest here.", ...NIGHT, 11], ["The ephemeral light faded.", ...NIGHT, 15]],
    state: "ready", importance: 6, fresh: true, shelf: "worth", rankScore: 0.29, studyLevel: 3,
    reasons: [{ code: "repeat_lookups", text: "Искали 2 раза", weight: 0.75 }, { code: "reading_now", text: "Из книги с недавними поисками", weight: 0.4 }],
  },
  {
    word: "wistful", lemma: "wistful", pos: "a", meaning: "тоскливый; задумчиво-грустный",
    lookups: [["A wistful smile crossed her face.", ...MIRROR, 12]],
    state: "ready", importance: 5, fresh: true, shelf: "disputed", rankScore: 0.21, studyLevel: 5, lean: "learn",
    reasons: [{ code: "frequency", text: "Не слишком частое слово", weight: 0.25 }, { code: "thin_evidence", text: "Искали один раз, данных мало", weight: -0.1 }],
  },
  {
    word: "sundry", lemma: "sundry", pos: "a", meaning: "",
    lookups: [["He packed sundry odds and ends into the bag.", ...MIRROR, 13]],
    state: "ready", importance: 4, fresh: true, shelf: "disputed", rankScore: 0.2, studyLevel: 6, lean: "skip",
    reasons: [{ code: "frequency", text: "Редкое слово, но в книгах бывает", weight: 0.15 }, { code: "thin_evidence", text: "Искали один раз, данных мало", weight: -0.2 }],
  },
  {
    word: "languid", lemma: "languid", pos: "a", meaning: "томный; вялый",
    lookups: [["The languid afternoon stretched on.", ...NIGHT, 4]],
    state: "ready", importance: 5, fresh: false, shelf: "disputed", rankScore: 0.195, studyLevel: 6, lean: "learn",
    reasons: [{ code: "recency", text: "Искали недавно", weight: 0.2 }, { code: "thin_evidence", text: "Искали один раз, данных мало", weight: -0.1 }],
  },
  {
    word: "Aldric", lemma: "aldric", pos: "", meaning: "",
    lookups: [["Aldric lowered his sword and waited.", ...MIRROR, 3]],
    state: "rejected", importance: 1, fresh: false, shelf: "junk", rankScore: 0.02, studyLevel: 9,
    reasons: [{ code: "junk_proper_noun", text: "Похоже на имя персонажа", weight: -0.9 }],
  },
  {
    word: "cheerful", lemma: "cheerful", pos: "a", meaning: "весёлый; бодрый",
    lookups: [["A cheerful fire crackled in the hearth.", ...SHADOWS, 2]],
    state: "ready", importance: 3, fresh: false, shelf: "worth", rankScore: 0.14, studyLevel: 7,
    reasons: [{ code: "frequency_common", text: "Слово из частых", weight: -0.2 }],
  },
  {
    word: "00:17", lemma: "00:17", pos: "", meaning: "",
    lookups: [["The clock read 00:17 when the phone rang.", ...NIGHT, 2]],
    state: "rejected", importance: 1, fresh: false, shelf: "junk", rankScore: 0, studyLevel: 10,
    reasons: [{ code: "junk_non_word", text: "В записи нет букв", weight: -1 }],
  },
];

const FIRST_SEEN = "2026-07-10T10:00:00Z";
const EXPORTED_AT = "2026-07-18T10:00:00Z";

function analysis(lemma: string, score: number, pos = "offline"): WordAnalysis {
  return {
    base_form: lemma,
    pos,
    accepted: true,
    importance_score: score,
    importance_note: "Оценено локальными частотными и морфологическими правилами.",
    frequency_note: "Zipf 3.8",
    source_occurrence_count: 1,
    translation_status: "offline_only",
    warnings: [],
  };
}

function occurrencesOf(spec: Spec, index: number): LexemeOccurrence[] {
  return spec.lookups.map(([context, book, authors, day], at) => ({
    id: at === 0 ? `kindle-${index}` : `kindle-${index}-${at + 1}`,
    source: "kindle" as const,
    word: spec.word,
    context,
    book_key: book,
    book_title: book,
    authors,
    looked_up_at: `2026-07-${String(day).padStart(2, "0")}T09:00:00Z`,
  }));
}

function makeLexeme(spec: Spec, index: number): LexemeRecord {
  const { lemma, word, state } = spec;
  const rejected = state === "rejected";
  const ready = state === "ready";
  const inObsidian = lemma === "admit" || lemma === "resilient";
  const localAnalysis = ready
    ? analysis(lemma, spec.importance, spec.pos)
    : rejected
      ? { ...analysis(lemma, spec.importance, spec.pos), accepted: false, importance_note: "Отклонено локальными правилами." }
      : null;
  const occurrences = occurrencesOf(spec, index);
  return {
    id: `lexeme-${lemma}`,
    lemma,
    display_form: word,
    language: "en",
    forms: word === lemma ? [word] : [word, lemma],
    occurrences,
    freshness: spec.fresh ? "new" : "known",
    processing: {
      state,
      analysis: localAnalysis,
      updated_at: ready || rejected ? FIRST_SEEN : "",
      error: "",
    },
    sources: { kindle: true, legacy: false },
    destinations: {
      obsidian: {
        state: inObsidian ? "synced" : ready ? "missing" : "not_applicable",
        eligible: ready,
        reason: ready ? "" : rejected ? "rejected" : "waiting_processing",
        external_key: lemma,
        last_checked_at: FIRST_SEEN,
        last_synced_at: inObsidian ? FIRST_SEEN : "",
      },
      anki: { state: "not_exported", last_exported_at: "" },
      quizlet: { state: "not_exported", last_exported_at: "" },
    },
    first_seen_at: FIRST_SEEN,
    last_seen_at: occurrences.at(-1)?.looked_up_at ?? FIRST_SEEN,
    last_kindle_sync_id: "preview-sync",
    dictionary: spec.meaning ? { meaning_ru: spec.meaning, pos: spec.pos, source: "wiktionary" } : null,
  };
}

// ---- in-memory state ----

type CardEdit = { meaning_ru?: string; example_occurrence_id?: string };
type ExportMark = { at: string; lookupsAfter: number };

let activeSpecs: Spec[] = [];
let mockEntries: LexemeRecord[] = [];
let decisions = new Map<string, LexemeDecision>();
let cardEdits = new Map<string, CardEdit>();
let exportMarks = new Map<string, ExportMark>();
let exportRuns: { runId: string; scope: string; ids: string[]; at: string; destination: ExportDestination }[] = [];
let exportFolderAvailable = false;
let folderChecks = 0;
const cancelledJobs = new Set<string>();
let mockFailureConsumed = false;
let libraryLoads = 0;

function markExported(id: string, at: string, lookupsAfter: number, destination: ExportDestination = "anki") {
  exportMarks.set(id, { at, lookupsAfter });
  mockEntries = mockEntries.map((entry) =>
    entry.id !== id
      ? entry
      : destination === "anki" || destination === "csv"
        ? { ...entry, destinations: { ...entry.destinations, anki: { state: "exported", last_exported_at: at } } }
        : entry,
  );
}

const mockKeys: Record<string, boolean> = {};
let mockSettings: AppSettings = { ...defaultSettings };

/** Rebuild the in-memory library for a scenario. Tests call it with `instant`; the preview never does. */
export function resetMockBackend(options: { scenario?: string; instant?: boolean } = {}): void {
  scenarioOverride = options.scenario;
  instant = options.instant ?? false;
  const scenario = previewScenario();
  const savedFolder = ["saved-export", "deleted-export", "folder-open-error", "folder-deleted-on-focus"].includes(scenario);
  const quiet = scenario === "no-new" || savedFolder;
  const source = scenario.startsWith("cold-start") ? specs.filter((spec) => spec.state === "pending") : specs;
  activeSpecs = source.map((spec) => (quiet ? { ...spec, fresh: false, state: spec.state === "pending" ? ("ready" as const) : spec.state } : spec));
  if (scenario === "large") {
    const sample = specs.find((spec) => spec.lemma === "ephemeral")!;
    for (let number = 1; number <= 120; number++) {
      const lemma = `sample-${String(number).padStart(3, "0")}`;
      activeSpecs.push({ ...sample, word: lemma, lemma });
    }
  }
  mockEntries = activeSpecs.map(makeLexeme);
  decisions = new Map();
  cardEdits = new Map();
  exportMarks = new Map();
  exportRuns = [];
  exportFolderAvailable = savedFolder;
  folderChecks = 0;
  cancelledJobs.clear();
  mockFailureConsumed = false;
  libraryLoads = 0;
  for (const key of Object.keys(mockKeys)) delete mockKeys[key];
  if (scenario === "showcase") mockKeys.anthropic = true;
  mockSettings = {
    ...defaultSettings,
    obsidian_sync_enabled: true,
    obsidian_vault_path: "preview",
    export_destination: "anki",
    export_batch_size: EXPORT_BATCH_SIZE_DEFAULT,
    ...(scenario === "showcase" ? { llm_enabled: true, llm_provider: "anthropic", llm_model: "claude-opus-5-5" } : {}),
  };
  const decide = (lemma: string, value: DecisionValue) => decisions.set(`lexeme-${lemma}`, { value, decided_at: "2026-07-16T10:00:00Z" });
  decide("cheerful", "known");
  // One exported word that was looked up again afterwards: the "came back" signal.
  markExported("lexeme-admit", EXPORTED_AT, 1);
  if (quiet) {
    decide("wistful", "skip");
    decide("sundry", "skip");
    decide("languid", "learn");
    for (const spec of activeSpecs) {
      const id = `lexeme-${spec.lemma}`;
      if (spec.shelf === "worth" && !exportMarks.has(id) && !decisions.has(id)) markExported(id, EXPORTED_AT, 0);
    }
    markExported("lexeme-languid", EXPORTED_AT, 0);
  }
  if (scenario === "showcase") mockEntries = applyShowcase(mockEntries);
}

// ---- ranking, cards and the library-level summaries, derived from the state above ----

const DECISION_SHELF: Record<DecisionValue, Shelf> = { known: "known", learn: "worth", skip: "not_worth", junk: "junk" };
const DECISION_TEXT: Record<DecisionValue, string> = {
  known: "Вы отметили: знаю",
  learn: "Вы решили учить",
  skip: "Вы решили не учить",
  junk: "Вы отметили: не слово",
};

function specOf(entry: LexemeRecord): Spec | undefined {
  return activeSpecs.find((spec) => `lexeme-${spec.lemma}` === entry.id);
}

function batchSize(): number {
  const size = mockSettings.export_batch_size;
  return typeof size === "number" && size >= 5 && size <= 100 ? size : EXPORT_BATCH_SIZE_DEFAULT;
}

type Scored = { entry: LexemeRecord; shelf: Shelf; score: number; lean: LeanValue | null; reasons: RankingReason[] };

function scoreEntries(): Scored[] {
  const scored: Scored[] = [];
  for (const entry of mockEntries) {
    const spec = specOf(entry);
    // A word that was not processed yet has no ranking, as in the real library.
    if (entry.processing.state !== "ready" && entry.processing.state !== "rejected") continue;
    if (!spec && entry.processing.state !== "ready") continue;
    const decision = decisions.get(entry.id);
    if (decision) {
      scored.push({ entry, shelf: DECISION_SHELF[decision.value], score: spec?.rankScore ?? 0.5, lean: null, reasons: [{ code: `decision_${decision.value}`, text: DECISION_TEXT[decision.value], weight: 0 }] });
    } else {
      scored.push({ entry, shelf: spec?.shelf ?? "worth", score: spec?.rankScore ?? 0.5, lean: spec?.shelf === "disputed" ? (spec.lean ?? "learn") : null, reasons: (spec?.reasons ?? [{ code: "frequency", text: "Не слишком частое слово", weight: 0.3 }]).filter((reason) => keepsRepeats() || !REPEAT_REASONS.has(reason.code)) });
    }
  }
  return scored;
}

function rankingTable(): Map<string, LexemeRanking> {
  const table = new Map<string, LexemeRanking>();
  const scored = scoreEntries();
  for (const shelf of SHELVES) {
    scored
      .filter((item) => item.shelf === shelf)
      .sort((a, b) => b.score - a.score || a.entry.lemma.localeCompare(b.entry.lemma))
      .forEach((item, index) => table.set(item.entry.id, { score: item.score, shelf, rank: index + 1, lean: item.lean, reasons: item.reasons, version: RANKING_VERSION }));
  }
  return table;
}

function defaultExampleId(entry: LexemeRecord): string {
  return [...entry.occurrences].sort((a, b) => Number(Boolean(b.context)) - Number(Boolean(a.context))
    || b.context.length - a.context.length || b.looked_up_at.localeCompare(a.looked_up_at))[0]?.id ?? "";
}

function cardOf(entry: LexemeRecord): CardFields {
  const edit = cardEdits.get(entry.id);
  const llm = entry.enrichment?.status === "ready" ? (entry.enrichment.meaning_ru ?? "") : "";
  const dictionary = entry.dictionary?.meaning_ru ?? "";
  const [meaning, source] = edit?.meaning_ru ? [edit.meaning_ru, "edited" as const] : llm ? [llm, "llm" as const] : dictionary ? [dictionary, "dictionary" as const] : ["", "none" as const];
  const example = edit?.example_occurrence_id ?? defaultExampleId(entry);
  return { meaning_ru: meaning, meaning_source: source, example_occurrence_id: example, edited: Boolean(edit?.meaning_ru) || Boolean(edit?.example_occurrence_id) };
}

function withV4(entry: LexemeRecord, rankings: Map<string, LexemeRanking>): LexemeRecordV4 {
  const mark = exportMarks.get(entry.id);
  return {
    ...entry,
    study_priority: mockStudyPriority(entry),
    ranking: rankings.get(entry.id) ?? null,
    decision: decisions.get(entry.id) ?? null,
    card: cardOf(entry),
    export: { state: mark ? "exported" : "not_exported", last_exported_at: mark?.at ?? "", again: Boolean(mark && mark.lookupsAfter > 0), lookups_after: mark?.lookupsAfter ?? 0 },
    is_new: entry.freshness === "new" && !mark,
  };
}

function mockStudyPriority(entry: LexemeRecord): StudyPriority {
  const spec = specOf(entry);
  const state = entry.processing.state;
  if (spec && (state === "ready" || state === "rejected")) {
    const reason = spec.reasons.find((item) => keepsRepeats() || !REPEAT_REASONS.has(item.code));
    return {
      level: spec.studyLevel, score: spec.rankScore, provisional: false,
      reason: reason?.text ?? "Пока мало признаков, что слово понадобится снова.",
    };
  }
  const pendingReasons: Partial<Record<ProcessingState, string>> = {
    pending: "Слово ожидает обработки.", processing: "Слово обрабатывается.",
    failed: "Обработку не удалось завершить.",
  };
  return { level: 6, score: 0, provisional: true, reason: pendingReasons[state] ?? "Для оценки пока недостаточно данных." };
}

function v4Entries(): LexemeRecordV4[] {
  const rankings = rankingTable();
  return mockEntries.map((entry) => withV4(entry, rankings));
}

function summaries(entries: LexemeRecordV4[]): Omit<LibraryRanking, "rankingVersion" | "rankingMode" | "historyDays" | "repeatSignal"> {
  const shelves = Object.fromEntries(SHELVES.map((shelf) => [shelf, 0])) as ShelfCounts;
  for (const entry of entries) if (entry.ranking) shelves[entry.ranking.shelf] += 1;
  const byRank = (shelf: Shelf) =>
    entries
      .filter((entry) => entry.ranking?.shelf === shelf && entry.export.state === "not_exported")
      .sort((a, b) => (a.ranking?.rank ?? 0) - (b.ranking?.rank ?? 0));
  const availableIds = byRank("worth").map((entry) => entry.id);
  const batchIds = availableIds.slice(0, batchSize());
  const newBatch: NewBatch = { count: batchIds.length, ids: batchIds, availableIds };
  const disputed: DisputedSummary = { ids: byRank("disputed").slice(0, DISPUTED_CAP).map((entry) => entry.id) };
  const againIds = entries.filter((entry) => entry.export.again).map((entry) => entry.id);
  const again: AgainSummary = { count: againIds.length, ids: againIds, unavailable: !keepsRepeats() };
  return { shelves, newBatch, disputed, again };
}

function historyDays(entries: LexemeRecord[]): number {
  const times = entries.flatMap((entry) => entry.occurrences.map((occurrence) => Date.parse(occurrence.looked_up_at))).filter((time) => !Number.isNaN(time));
  return times.length ? Math.round((Math.max(...times) - Math.min(...times)) / 86_400_000) : 0;
}

// ---- the old fixtures (connectors, books, queue, LLM) ----

function mockConnectors(): ConnectorStatus {
  const scenario = previewScenario();
  return {
    kindle: {
      state: scenario === "disconnected" || scenario === "empty" ? "disconnected" : "connected",
      label: scenario === "disconnected" || scenario === "empty" ? "Kindle" : "Kindle Paperwhite",
      checked_at: new Date().toISOString(),
      signature: scenario === "disconnected" || scenario === "empty" ? undefined : ["preview-kindle", "12345678", "2026-07-10T10:00:00Z"],
    },
    anki: { state: scenario === "anki-connected" ? "connected" : "disconnected", label: "Anki", checked_at: new Date().toISOString() },
    obsidian: { state: scenario === "obsidian-error" ? "error" : "connected", label: "Obsidian", checked_at: new Date().toISOString() },
  };
}

function buildBooks(entries: LexemeRecord[]): BookOption[] {
  const counts = new Map<string, number>();
  const details = new Map<string, { title: string; authors: string }>();
  for (const entry of entries) {
    for (const key of new Set(entry.occurrences.map((item) => item.book_key).filter(Boolean))) {
      counts.set(key, (counts.get(key) ?? 0) + 1);
      const occurrence = entry.occurrences.find((item) => item.book_key === key);
      if (occurrence && !details.has(key)) details.set(key, { title: occurrence.book_title || key, authors: occurrence.authors });
    }
  }
  return [{ label: "Все книги", key: "" }, ...Array.from(counts, ([key, count]) => {
    const { title, authors } = details.get(key) ?? { title: key, authors: "" };
    return { label: `${title}${authors ? ` · ${authors}` : ""} · ${count}`, key, title, authors };
  })];
}

function mockQueueStatus() {
  const pending = mockEntries.filter((entry) => entry.processing.state === "pending").length;
  const failed = mockEntries.filter((entry) => entry.processing.state === "failed").length;
  return { pending, processing: 0, failed, total: pending + failed };
}

const mockLlmPresets: LlmPreset[] = [
  { id: "anthropic", label: "Anthropic (Claude)", kind: "anthropic", base_url: "", default_model: "claude-opus-5-5", needs_key: true, local: false, hint: "Ключ: console.anthropic.com" },
  { id: "deepseek", label: "DeepSeek", kind: "openai_compatible", base_url: "https://api.deepseek.com/v1", default_model: "deepseek-chat", needs_key: true, local: false, hint: "Ключ: platform.deepseek.com" },
  { id: "lmstudio", label: "LM Studio (локально)", kind: "openai_compatible", base_url: "http://localhost:1234/v1", default_model: "", needs_key: false, local: true, hint: "Бесплатно, слова не покидают компьютер. Медленнее облака" },
  { id: "custom", label: "Другой OpenAI-совместимый", kind: "openai_compatible", base_url: "", default_model: "", needs_key: true, local: false, hint: "Укажите адрес API и модель" },
];

// `?scenario=showcase`: processed words with realistic translations for screenshots.
const showcaseTranslations: Record<string, Partial<Enrichment>> = {
  admit: { meaning_ru: "признавать; сознаваться", definition_en: "to agree, often unwillingly, that something is true", context_ru: "Она знала ответ, но не решалась его признать.", example_en: "He admitted that he had made a mistake.", example_ru: "Он признал, что ошибся." },
  glimpse: { meaning_ru: "мельком увидеть; проблеск", definition_en: "a brief, incomplete look at something", context_ru: "На мгновение он мельком увидел город внизу.", example_en: "I caught a glimpse of her in the crowd.", example_ru: "Я мельком увидел её в толпе." },
  dread: { meaning_ru: "страх; тревожное предчувствие", definition_en: "a strong fear of something that may happen", context_ru: "Комнату накрыл тихий страх.", example_en: "She thought about the exam with dread.", example_ru: "Она думала об экзамене со страхом.", note_ru: "Книжное: о гнетущем ожидании беды." },
  resilient: { meaning_ru: "стойкий; жизнестойкий", definition_en: "able to recover quickly from difficulties", context_ru: "Её стойкий дух так и не сломался.", example_en: "Children are often more resilient than adults.", example_ru: "Дети часто стойче взрослых." },
};

const showcaseDictionary: Record<string, DictionaryMeaning> = {
  glimpse: { meaning_ru: "проблеск; мимолётное впечатление; намёк", pos: "n", source: "wiktionary" },
  submerge: { meaning_ru: "погружать, затоплять; погружаться", pos: "v", source: "wiktionary" },
  vigilant: { meaning_ru: "бдительный, внимательный", pos: "a", source: "wiktionary" },
};

function applyShowcase(entries: LexemeRecord[]): LexemeRecord[] {
  return entries.map((entry) => {
    const translation = showcaseTranslations[entry.lemma];
    const pos: Record<string, string> = { admit: "v", glimpse: "n", dread: "n", submerge: "v", resilient: "a", vigilant: "a" };
    const ready = entry.processing.state === "ready" || (entry.processing.state === "pending" && entry.lemma !== "submerge");
    const base = ready && entry.processing.state === "pending" ? analysis(entry.lemma, 7) : entry.processing.analysis;
    const processed: LexemeRecord = {
      ...entry,
      processing: ready && base ? { state: "ready", analysis: { ...base, pos: pos[entry.lemma] }, updated_at: FIRST_SEEN, error: "" } : entry.processing,
      destinations: ready && entry.destinations.obsidian.state !== "synced"
        ? { ...entry.destinations, obsidian: { ...entry.destinations.obsidian, state: "missing", eligible: true, reason: "" } }
        : entry.destinations,
    };
    // Words without a context translation still get offline Wiktionary meanings.
    if (!translation) return { ...processed, dictionary: showcaseDictionary[entry.lemma] ?? entry.dictionary ?? null };
    return { ...processed, enrichment: { status: "ready", provider: "anthropic", model: "claude-opus-5-5", prompt_version: 1, error: "", updated_at: FIRST_SEEN, ...translation } };
  });
}

function isEnrichable(entry: LexemeRecord) {
  const score = entry.processing.analysis?.importance_score;
  return entry.processing.state === "ready" && entry.processing.analysis?.accepted !== false && typeof score === "number" && score >= 3;
}

function mockEnrichmentQueue() {
  return {
    pending: mockEntries.filter((entry) => isEnrichable(entry) && !entry.enrichment).length,
    failed: mockEntries.filter((entry) => isEnrichable(entry) && entry.enrichment?.status === "failed").length,
  };
}

function mockEnrichment(entry: LexemeRecord): Enrichment {
  return {
    status: "ready",
    meaning_ru: `перевод «${entry.lemma}»`,
    definition_en: `a preview definition of ${entry.lemma}`,
    context_ru: "Перевод предложения из книги.",
    example_en: `A new example with ${entry.lemma}.`,
    example_ru: "Новый пример.",
    note_ru: "",
    provider: "preview",
    model: "preview-model",
    prompt_version: 1,
    error: "",
    updated_at: new Date().toISOString(),
  };
}

/** `?scenario=empty` has no words until `load_demo` is asked for the example library (`full`). */
function libraryResult(full = false): LibraryResultV4 {
  const hollow = isEmptyScenario() && !full;
  const entries = hollow ? [] : v4Entries();
  return {
    sourceName: hollow ? "" : full && isEmptyScenario() ? "Demo Kindle" : "Preview library",
    sourceStatus: hollow ? "Библиотека пуста" : full && isEmptyScenario() ? "Демонстрационные данные" : "Локальная библиотека готова",
    books: buildBooks(hollow ? [] : mockEntries),
    entries,
    last_kindle_sync_id: hollow ? "" : "preview-sync",
    connectors: mockConnectors(),
    queueStatus: hollow ? { pending: 0, processing: 0, failed: 0, total: 0 } : mockQueueStatus(),
    enrichmentQueue: hollow ? { pending: 0, failed: 0 } : mockEnrichmentQueue(),
    rankingVersion: RANKING_VERSION,
    rankingMode: rankingMode(),
    historyDays: hollow ? 0 : historyDays(mockEntries),
    repeatSignal: keepsRepeats(),
    ...summaries(entries),
  };
}

// ---- the short-list actions ----

function fail(code: ErrorCode, detail = ""): never {
  throw new BridgeError(detail ? `${ERROR_TEXTS[code]}: ${detail}` : ERROR_TEXTS[code], code);
}

function findEntry(payload: unknown): LexemeRecord {
  const id = (payload as { lexeme_id?: string } | undefined)?.lexeme_id;
  const entry = mockEntries.find((item) => item.id === id);
  if (!entry) fail("unknown_lexeme");
  return entry;
}

function entryResult(entry: LexemeRecord): LexemeRecordV4 {
  return withV4(mockEntries.find((item) => item.id === entry.id) ?? entry, rankingTable());
}

function setDecision(payload: unknown): SetDecisionResult {
  const entry = findEntry(payload);
  const value = (payload as { decision?: DecisionValue | null }).decision ?? null;
  if (value !== null && !DECISIONS.includes(value)) fail("bad_decision");
  if (value === null) decisions.delete(entry.id);
  else decisions.set(entry.id, { value, decided_at: new Date().toISOString() });
  const entries = v4Entries();
  return { entry: entries.find((item) => item.id === entry.id)!, ...summaries(entries) };
}

function saveCardEdit(payload: unknown): SaveCardEditResult {
  const entry = findEntry(payload);
  const request = payload as { meaning_ru?: string; example_occurrence_id?: string };
  const next: CardEdit = { ...cardEdits.get(entry.id) };
  if (request.meaning_ru !== undefined) {
    const meaning = request.meaning_ru.replace(/\s+/gu, " ").trim();
    if ([...meaning].length > MEANING_MAX_LENGTH) fail("too_long");
    if (meaning) next.meaning_ru = meaning;
    else delete next.meaning_ru;
  }
  if (request.example_occurrence_id !== undefined) {
    if (request.example_occurrence_id === "") delete next.example_occurrence_id;
    else {
      if (!entry.occurrences.some((occurrence) => occurrence.id === request.example_occurrence_id)) fail("example_not_found");
      next.example_occurrence_id = request.example_occurrence_id;
    }
  }
  if (next.meaning_ru === undefined && next.example_occurrence_id === undefined) cardEdits.delete(entry.id);
  else cardEdits.set(entry.id, next);
  return { entry: entryResult(entry) };
}

function exportDestination(): ExportDestination {
  return mockSettings.export_destination ?? "anki";
}

function exportPreview(): ExportPreview {
  const { newBatch, again } = summaries(v4Entries());
  return { destination: exportDestination(), new: { count: newBatch.count, ids: newBatch.ids }, again: { count: again.count, ids: again.ids }, blockedReason: null };
}

function exportWords(payload: unknown): ExportRun {
  const request = payload as { scope?: string; ids?: string[]; levels?: number[] };
  if (request.scope !== "new" && request.scope !== "again" && request.scope !== "library") fail("bad_scope");
  if (request.levels !== undefined && (request.scope !== "library" || !Array.isArray(request.levels) || !request.levels.length
    || new Set(request.levels).size !== request.levels.length || request.levels.some((level) => !Number.isInteger(level) || level < 1 || level > 10))) fail("bad_levels");
  if (request.ids !== undefined && (!Array.isArray(request.ids) || request.ids.some((id) => typeof id !== "string" || !id.trim()))) fail("unknown_lexeme");
  const preview = exportPreview();
  const available = summaries(v4Entries()).newBatch.availableIds ?? preview.new.ids;
  const requested = request.ids ? new Set(request.ids) : null;
  if (requested && [...requested].some((id) => !mockEntries.some((entry) => entry.id === id))) fail("unknown_lexeme");
  const entries = new Map(v4Entries().map((entry) => [entry.id, entry]));
  let ids: string[];
  if (request.scope === "library") {
    ids = [...(requested ?? [])].filter((id) => !request.levels || request.levels.includes(entries.get(id)!.study_priority.level));
  } else {
    const pool = request.scope === "new" ? available : preview.again.ids;
    ids = requested ? pool.filter((id) => requested.has(id)) : request.scope === "new" ? preview.new.ids : preview.again.ids;
  }
  if (!ids.length) fail("nothing_to_export");
  if (previewScenario() === "export-error") fail("export_failed", "не удалось записать файл");
  if (previewScenario() === "export-busy") fail("export_busy");
  const destination = exportDestination();
  if (destination === "anki" && ["anki-unconfirmed", "anki-rejected"].includes(previewScenario())) {
    exportFolderAvailable = true;
    fail(previewScenario() === "anki-unconfirmed" ? "anki_import_unconfirmed" : "anki_import_rejected");
  }
  const at = new Date().toISOString();
  for (const id of ids) markExported(id, at, 0, destination);
  const runId = `run-${exportRuns.length + 1}`;
  exportRuns.push({ runId, scope: request.scope, ids, at, destination });
  const pushed = destination === "anki" && mockConnectors().anki?.state === "connected" ? ids.length : 0;
  const path = pushed || destination === "obsidian" ? null : destination === "csv" ? "preview/kindle-cards.tsv" : "preview/Kindle Cards.apkg";
  if (destination === "anki" || destination === "csv") exportFolderAvailable = true;
  return { destination, runId, exported: ids.length, path, pushed, message: pushed ? `Отправлено в Anki: ${pushed}` : `Слов в экспорте: ${ids.length}` };
}

function lexemeDetails(payload: unknown): LexemeDetails {
  const entry = findEntry(payload);
  return {
    lexeme_id: entry.id,
    forms: entry.forms,
    occurrences: entry.occurrences,
    analysis: entry.processing.analysis ?? null,
    enrichment: entry.enrichment ?? null,
    dictionary: entry.dictionary ?? null,
  };
}

// ---- dispatcher ----

export function cancelMockJob(jobId: string): void {
  cancelledJobs.add(jobId);
}

resetMockBackend();

export async function mockBackend<T>(action: string, payload: unknown): Promise<T> {
  // `?scenario=slow`: the first library load and the long operations take a few seconds.
  const scenario = previewScenario();
  const slowOperation = (scenario === "slow" && (["process_queue", "process_lexemes", "load_obsidian", "sync_obsidian"].includes(action) || (action === "load_library" && libraryLoads === 0)))
    || (scenario.startsWith("cold-start") && action === "process_queue");
  if (!instant) await new Promise((resolve) => setTimeout(resolve, action === "connector_status" ? 80 : slowOperation ? 2500 : 280));
  if (action === "load_library") libraryLoads += 1;
  const requestJobId = (payload as { job_id?: string } | undefined)?.job_id;
  if (requestJobId && cancelledJobs.delete(requestJobId)) throw new Error("Операция отменена");
  if (["operation-error", "cold-start-error"].includes(scenario) && action === "process_queue" && !mockFailureConsumed) {
    mockFailureConsumed = true;
    throw new Error("Тестовая ошибка offline-обработки");
  }
  if (action === "set_decision") return setDecision(payload) as T;
  if (action === "save_card_edit") return saveCardEdit(payload) as T;
  if (action === "export_preview") return exportPreview() as T;
  if (action === "export_words") return exportWords(payload) as T;
  if (action === "load_lexeme_details") return lexemeDetails(payload) as T;
  if (action === "load_settings") return mockSettings as T;
  if (action === "llm_config") return { presets: mockLlmPresets, provider: mockSettings.llm_provider, model: mockSettings.llm_model, base_url: mockSettings.llm_base_url, has_key: { ...mockKeys } } as T;
  if (action === "save_llm_key") { mockKeys[(payload as { provider: string }).provider] = true; return { has_key: true } as T; }
  if (action === "delete_llm_key") { delete mockKeys[(payload as { provider: string }).provider]; return { has_key: false } as T; }
  if (action === "list_llm_models") return { models: ["preview-small", "preview-large"] } as T;
  if (action === "test_llm") {
    if (previewScenario() === "llm-error") throw new Error("Ключ API не подошёл. Проверьте его в настройках");
    return { ok: true, model: "preview-model", seconds: 1.4, sample: { meaning_ru: "мельком увидеть; проблеск", definition_en: "a brief look" } } as T;
  }
  if (action === "enrich_lexemes") {
    const ids = new Set(mockEntries.filter((entry) => isEnrichable(entry) && entry.enrichment?.status !== "ready").map((entry) => entry.id));
    mockEntries = mockEntries.map((entry) => (ids.has(entry.id) ? { ...entry, enrichment: mockEnrichment(entry) } : entry));
    return { requested: ids.size, enriched: ids.size, failed: 0, error: "", message: `Переведено: ${ids.size}; без перевода: 0`, entries: v4Entries(), queue_status: mockQueueStatus(), enrichmentQueue: mockEnrichmentQueue() } as T;
  }
  if (action === "export_apkg" || action === "push_anki") {
    const fresh = mockEntries.filter((entry) => isEnrichable(entry) && entry.destinations.anki.state !== "exported");
    for (const entry of fresh) markExported(entry.id, new Date().toISOString(), 0);
    const pushed = action === "push_anki";
    return { path: fresh.length ? "preview/Kindle Cards.apkg" : "", exported: fresh.length, skipped: 0, pushed, message: !fresh.length ? "Нет новых карточек для Anki" : pushed ? `Отправлено в Anki: ${fresh.length}` : `Карточек в колоде: ${fresh.length}` } as T;
  }
  if (action === "open_path") return { opened: true } as T;
  if (action === "export_folder_status") {
    if (scenario === "folder-deleted-on-focus" && ++folderChecks > 1) exportFolderAvailable = false;
    return { available: exportFolderAvailable } as T;
  }
  if (action === "open_export_folder") {
    if (scenario === "deleted-export") exportFolderAvailable = false;
    return { opened: exportFolderAvailable && scenario !== "folder-open-error" } as T;
  }
  if (action === "save_settings") {
    mockSettings = { ...mockSettings, ...(payload as { settings: Partial<AppSettings> }).settings };
    return { saved: true } as T;
  }
  if (action === "connector_status") return mockConnectors() as T;
  if (action === "load_demo") return libraryResult(true) as T;
  if (action === "load_obsidian") {
    if (previewScenario() === "obsidian-error") throw new Error("Папка карточек Obsidian недоступна");
    return libraryResult() as T;
  }
  if (["load_library", "load_cached", "sync_kindle", "scan", "download_covers"].includes(action)) return libraryResult() as T;
  if (action === "import_reader_file") return { ...libraryResult(), imported: { format: "koreader", label: "KOReader", lookups: mockEntries.length, new_words: 0 } } as T;
  if (["process_queue", "process_lexemes", "optimize"].includes(action)) {
    const request = payload as { ids?: string[]; include_failed?: boolean } | undefined;
    const states = request?.include_failed || request?.ids ? ["pending", "failed"] : ["pending"];
    const ids = new Set(request?.ids ?? mockEntries.filter((entry) => states.includes(entry.processing.state)).map((entry) => entry.id));
    // `?scenario=lexeme-failure` fails one lexeme on the first pass to preview the retry flow.
    const failingId = previewScenario() === "lexeme-failure" && !mockFailureConsumed ? mockEntries.find((entry) => ids.has(entry.id))?.id : undefined;
    if (failingId) mockFailureConsumed = true;
    mockEntries = mockEntries.map((entry) => {
      if (!ids.has(entry.id)) return entry;
      if (entry.id === failingId) {
        return { ...entry, processing: { state: "failed", analysis: null, updated_at: new Date().toISOString(), error: "Тестовая ошибка анализа леммы" } };
      }
      return {
        ...entry,
        processing: { state: "ready", analysis: analysis(entry.lemma, 6, specOf(entry)?.pos), updated_at: new Date().toISOString(), error: "" },
        destinations: {
          ...entry.destinations,
          obsidian: { ...entry.destinations.obsidian, state: "missing", eligible: true, reason: "" },
        },
      };
    });
    const failed = failingId ? 1 : 0;
    return { processed_new: ids.size - failed, accepted_new: ids.size - failed, rejected_new: 0, skipped_existing: 0, failed_new: failed, entries: v4Entries(), queue_status: mockQueueStatus() } as T;
  }
  if (action === "sync_obsidian") {
    const pendingSync = mockEntries.filter((entry) => entry.destinations.obsidian.eligible && entry.destinations.obsidian.state === "missing");
    const items = pendingSync.map((entry) => ({ id: entry.id, outcome: "added", reason: "" }));
    mockEntries = mockEntries.map((entry) =>
      entry.destinations.obsidian.eligible
        ? { ...entry, destinations: { ...entry.destinations, obsidian: { ...entry.destinations.obsidian, state: "synced", reason: "", last_synced_at: new Date().toISOString() } } }
        : entry,
    );
    return { added: items.length, skipped: 0, files: ["Priority 7.md"], backup_path: "preview", items, entries: v4Entries(), queue_status: { pending: 0, processing: 0, failed: 0, total: 0 } } as T;
  }
  if (action === "export") return { path: "preview/export.tsv", exported: (payload as { entries?: unknown[] })?.entries?.length ?? 0 } as T;
  return {} as T;
}
