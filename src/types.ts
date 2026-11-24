export type BookOption = {
  label: string;
  key: string;
  title?: string;
  display_title?: string;
  authors?: string;
  cover_data_url?: string;
  cover_status?: "available" | "missing" | "error" | "pending" | "unavailable";
};

export type CoverSummary = {
  available: number;
  total: number;
  downloaded: number;
  missing: number;
  errors: number;
};

export type OccurrenceSource = "kindle" | "legacy";

export type LexemeOccurrence = {
  id: string;
  source: OccurrenceSource;
  word: string;
  context: string;
  book_key: string;
  book_title: string;
  authors: string;
  looked_up_at: string;
};

export type Freshness = "new" | "known";
export type ProcessingState = "pending" | "processing" | "ready" | "rejected" | "failed";
export type SyncState = "missing" | "synced" | "not_applicable" | "failed";
export type ExportState = "not_exported" | "exporting" | "exported" | "failed";

export type WordAnalysis = {
  base_form: string;
  pos?: string;
  accepted: boolean;
  importance_score?: number;
  importance_note?: string;
  frequency_note?: string;
  lemma_zipf?: number;
  form_zipf?: number;
  wordnet_synset_count?: number;
  wordnet_pos_count?: number;
  warnings?: string[];
  tags?: string;
  source_word_forms?: string[];
  source_occurrence_count?: number;
  processed_at?: string;
  tsv_path?: string;
  translation_status?: "not_started" | "offline_only" | "llm_enriched";
  russian_meanings?: string;
  generated_context_en?: string;
  generated_context_ru?: string;
};

export type DictionaryMeaning = {
  meaning_ru: string;
  pos: string;
  source: "wiktionary";
};

export type Enrichment = {
  status: "ready" | "failed";
  meaning_ru?: string;
  definition_en?: string;
  context_ru?: string;
  example_en?: string;
  example_ru?: string;
  note_ru?: string;
  provider: string;
  model: string;
  prompt_version: number;
  error: string;
  updated_at: string;
};

export type EnrichmentQueue = {
  pending: number;
  failed: number;
};

export type LexemeRecord = {
  id: string;
  lemma: string;
  display_form: string;
  language: string;
  forms: string[];
  occurrences: LexemeOccurrence[];
  freshness: Freshness;
  processing: {
    state: ProcessingState;
    analysis?: WordAnalysis | null;
    updated_at: string;
    error: string;
  };
  sources: {
    kindle: boolean;
    legacy: boolean;
  };
  destinations: {
    obsidian: {
      state: SyncState;
      eligible: boolean;
      reason: string;
      external_key: string;
      last_checked_at: string;
      last_synced_at: string;
    };
    anki: {
      state: ExportState;
      last_exported_at: string;
    };
    quizlet: {
      state: ExportState;
      last_exported_at: string;
    };
  };
  first_seen_at: string;
  last_seen_at: string;
  last_kindle_sync_id: string;
  enrichment?: Enrichment | null;
  /** Offline meanings from the bundled Wiktionary dictionary, attached when the library loads. */
  dictionary?: DictionaryMeaning | null;
  /** Short-list contract (C0). Optional until the bridge sends it; see `LexemeRecordV4`. */
  ranking?: LexemeRanking | null;
  study_priority?: StudyPriority;
  decision?: LexemeDecision | null;
  card?: CardFields;
  export?: ExportInfo;
  is_new?: boolean;
};

// ---- Short-list bridge contract (C0). Mirrors `kindle_vocab_app/contracts.py`. ----
// Key case: lexeme-level and request keys are snake_case, library-level and result
// aggregates are camelCase. The list payload is lean; analysis comes from `load_lexeme_details`.

export type Shelf = "worth" | "disputed" | "not_worth" | "junk" | "known";
export type DecisionValue = "known" | "learn" | "skip" | "junk";
export type LeanValue = "learn" | "skip" | "junk";
export type RankingMode = "learning" | "full";
/** Personal study order. Level 1 comes first. A provisional 6 awaits sufficient analysis. */
export type StudyPriority = {
  level: number;
  score: number;
  provisional: boolean;
  reason: string;
  coverage_score?: number | null;
  personal_reason?: string;
};
export type MeaningSource = "edited" | "llm" | "dictionary" | "none";
export type ExportDestination = "anki" | "csv" | "obsidian";
export type ExportScope = "new" | "again" | "library";

export type ReasonCode =
  | "decision_learn" | "decision_skip" | "decision_junk" | "decision_known" | "known_again"
  | "repeat_lookups" | "after_export" | "several_books" | "reading_now" | "recency"
  | "frequency" | "frequency_common"
  | "junk_non_word" | "junk_non_english" | "junk_unknown_word" | "junk_glued_words" | "junk_proper_noun"
  | "thin_evidence";

export type RankingReason = {
  code: ReasonCode;
  /** Russian, one short line. Weight > 0 speaks for learning the word, < 0 against, 0 is a decision. */
  text: string;
  weight: number;
};

export type LexemeRanking = {
  score: number;
  shelf: Shelf;
  /** 1-based inside the shelf, best first. */
  rank: number;
  /** The suggested answer; set only on the `disputed` shelf. */
  lean: LeanValue | null;
  reasons: RankingReason[];
  version: string;
};

export type LexemeDecision = { value: DecisionValue; decided_at: string };

export type CardFields = {
  meaning_ru: string;
  meaning_source: MeaningSource;
  example_occurrence_id: string;
  edited: boolean;
};

export type ExportInfo = {
  state: "exported" | "not_exported";
  last_exported_at: string;
  /** Looked up again after the last export; never true when the source keeps no repeat lookups. */
  again: boolean;
  lookups_after: number;
};

/** A library entry as the short-list bridge sends it: the old fields plus all new ones. */
export type LexemeRecordV4 = LexemeRecord &
  Required<Pick<LexemeRecord, "study_priority" | "ranking" | "decision" | "card" | "export" | "is_new">>;

export type ShelfCounts = Record<Shelf, number>;

export type NewBatch = {
  count: number;
  /** All eligible unexported IDs in rank order. Older bridges supply only the configured portion. */
  availableIds?: string[];
  /** The short list: `worth` words not yet exported, by rank, cut at `export_batch_size`. No disputed words. */
  ids: string[];
};

/** Disputed words still to answer: at most `DISPUTED_CAP`, never in `newBatch.ids`; the length is the Слова badge. */
export type DisputedSummary = { ids: string[] };

export type AgainSummary = {
  count: number;
  ids: string[];
  /** True when the source keeps no repeat lookups; the UI stays silent instead of saying "none". */
  unavailable: boolean;
};

export type StudyPrioritySource = "rp-v2-coverage" | "rp-v2-personal" | "legacy";

export type LibraryRanking = {
  studyPrioritySource?: StudyPrioritySource;
  rankingVersion: string;
  rankingMode: RankingMode;
  historyDays: number;
  repeatSignal: boolean;
  shelves: ShelfCounts;
  newBatch: NewBatch;
  disputed: DisputedSummary;
  again: AgainSummary;
};

/** What `load_library` returns once the bridge sends the short-list parts. */
export type LibraryResultV4 = Omit<LibraryResult, "entries"> & LibraryRanking & { entries: LexemeRecordV4[] };

export const DISPUTED_CAP = 5;
export const MEANING_MAX_LENGTH = 200;
export const EXPORT_BATCH_SIZE_DEFAULT = 20;
export const EXPORT_BATCH_SIZE_MIN = 5;
export const EXPORT_BATCH_SIZE_MAX = 100;

export type ErrorCode =
  | "no_destination" | "too_long" | "example_not_found" | "nothing_to_export" | "export_failed"
  | "anki_import_unconfirmed" | "anki_import_rejected" | "export_busy"
  | "unknown_lexeme" | "bad_decision" | "bad_scope" | "bad_levels";

/** Failure envelope: `error` is Russian text for the UI, `code` is absent on older errors. */
export type ActionError = { ok: false; error: string; code?: ErrorCode };

export const ERROR_TEXTS: Record<ErrorCode, string> = {
  no_destination: "Не выбрано, куда экспортировать. Выберите место в настройках.",
  too_long: "Перевод длиннее 200 символов",
  example_not_found: "Пример не относится к этому слову",
  nothing_to_export: "Нет слов для экспорта",
  export_failed: "Не удалось выполнить экспорт",
  anki_import_unconfirmed: "Anki не подтвердил импорт. Колода сохранена в папке выгрузок. Проверьте Anki перед повторной отправкой.",
  anki_import_rejected: "Anki отклонил импорт. Колода сохранена в папке выгрузок. Её можно открыть вручную.",
  export_busy: "Выгрузка уже идёт. Дождитесь её завершения и попробуйте снова.",
  unknown_lexeme: "Слово не найдено в библиотеке",
  bad_decision: "Неизвестное решение. Допустимо: знаю, учить, не учить, не слово",
  bad_scope: "Неизвестный набор слов для экспорта",
  bad_levels: "Выберите хотя бы один уровень от 1 до 10",
};

// set_decision {lexeme_id, decision: DecisionValue | null}
export type SetDecisionResult = {
  studyPrioritySource?: StudyPrioritySource;
  entry: LexemeRecordV4;
  shelves: ShelfCounts;
  newBatch: NewBatch;
  disputed: DisputedSummary;
  again: AgainSummary;
};

// save_card_edit {lexeme_id, meaning_ru?, example_occurrence_id?}; meaning_ru "" removes the edit.
export type SaveCardEditResult = { entry: LexemeRecordV4 };

// export_preview {}
export type ExportBucket = { count: number; ids: string[] };
export type ExportPreview = {
  destination: ExportDestination;
  new: ExportBucket;
  again: ExportBucket;
  blockedReason: { code: ErrorCode; text: string } | null;
};

// export_words {job_id, scope, ids?}; the destination comes from settings.
export type ExportRun = {
  destination: ExportDestination;
  runId: string;
  exported: number;
  /** The written file; null for a push or a vault write. */
  path: string | null;
  /** Cards pushed to Anki, 0 otherwise. */
  pushed: number;
  message: string;
};

// load_lexeme_details {lexeme_id}: what the inspector needs and the list does not carry.
export type LexemeDetails = {
  lexeme_id: string;
  forms: string[];
  occurrences: LexemeOccurrence[];
  analysis: WordAnalysis | null;
  enrichment: Enrichment | null;
  dictionary: DictionaryMeaning | null;
};

export type ConnectorState = "unknown" | "checking" | "connected" | "disconnected" | "disabled" | "error";

export type ConnectorInfo = {
  state: ConnectorState;
  label: string;
  checked_at: string;
  signature?: string[];
};

export type ConnectorStatus = {
  kindle: ConnectorInfo;
  obsidian: ConnectorInfo;
  /** AnkiConnect add-on reachable on localhost; absent in older bridge responses. */
  anki?: ConnectorInfo;
};

export type LibraryResult = {
  studyPrioritySource?: StudyPrioritySource;
  sourceName: string;
  sourceStatus: string;
  books: BookOption[];
  coverSummary?: CoverSummary;
  entries: LexemeRecord[];
  last_kindle_sync_id: string;
  connectors: ConnectorStatus;
  queueStatus: QueueStatus;
  enrichmentQueue?: EnrichmentQueue;
  /** Present after `import_reader_file`: what the picked file was and what it added. */
  imported?: { format: "kindle" | "koreader" | "kobo"; label: string; lookups: number; new_words: number };
};

export type QueueStatus = {
  pending: number;
  processing: number;
  failed: number;
  total: number;
};

export type ProgressEvent = {
  job_id: string;
  stage: string;
  message: string;
  current: number;
  total: number;
  lexeme_id: string;
  timestamp: string;
};

export type ActivityEvent = {
  phase: "ready" | "thinking" | "answered" | "failed" | string;
  title: string;
  message: string;
  meta?: string;
};

export type AppSettings = {
  theme: "system" | "light" | "dark";
  language: "ru" | "en";
  default_export_format: "anki" | "quizlet";
  app_data_path: string;
  llm_enabled: boolean;
  llm_provider: string;
  llm_model: string;
  llm_base_url: string;
  llm_auto_enrich: boolean;
  obsidian_sync_enabled: boolean;
  obsidian_vault_path: string;
  obsidian_cards_path: string;
  obsidian_backup_enabled: boolean;
  /** Short-list release: where `export_words` writes. Absent in older bridge responses (anki). */
  export_destination?: ExportDestination;
  /** Size of the short list, 5..100; absent in older bridge responses (20). */
  export_batch_size?: number;
};

export type OperationKind = "idle" | "kindle" | "covers" | "processing" | "enrich" | "obsidian" | "export";
export type OperationStatus = "idle" | "running" | "completed" | "cancelled" | "error";

export type Operation = {
  id: string;
  kind: OperationKind;
  status: OperationStatus;
  title: string;
  message: string;
  current: number;
  total: number;
  stage: string;
  error: string;
};

export type LlmPreset = {
  id: string;
  label: string;
  kind: "openai_compatible" | "anthropic";
  base_url: string;
  default_model: string;
  needs_key: boolean;
  local: boolean;
  hint: string;
};

export type LlmConfig = {
  presets: LlmPreset[];
  provider: string;
  model: string;
  base_url: string;
  has_key: Record<string, boolean>;
};

export type LlmTestResult = {
  ok: boolean;
  model: string;
  seconds: number;
  sample: Partial<Enrichment>;
};
