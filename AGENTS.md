# Project Context

Kindle Vocabulary Builder is a local desktop app for extracting Kindle Vocabulary
Builder entries from `vocab.db`, previewing them, exporting Anki/Quizlet TSV
files, and running deterministic offline optimization only for words that were
not processed before.

The standard Kindle file is:

```text
Kindle/system/vocabulary/vocab.db
```

Where the product is going — who it is for, what it promises, the milestones —
is in `PRODUCT.md`; the agreed screens are in `docs/concept/`. The description
above is the app as it started.

On Windows the Kindle may appear as either a mounted drive or an MTP/WPD device
under "This PC > Kindle". The backend already has both paths covered; do not
replace this with drive-letter-only detection.

## Communication Rules

- All agent-to-user communication must be in Russian.
- This includes intermediate questions, confirmations, status updates, summaries,
  and explanations of planned or performed actions.
- If reasoning or source material is in another language, translate it to Russian
  before presenting it to the user.
- Code, commands, identifiers, file paths, and technical terms stay in their
  original form.

## Work Log

- Before inspecting or changing the project, read `WORKLOG.md` from the repository
  root so current decisions and unfinished work are not lost.
- `WORKLOG.md` is append-only. Never rewrite, reorder, or delete previous entries.
- Every agent, including delegated agents, must append its own dated entry for
  each logical batch of work. Record the goal, decisions, changed files, checks,
  failures, remaining risks, and commit hashes when available. Read-only
  reviewer subagents (see "Design and UX Reviewers") are the exception: the
  parent records their findings.
- Do not record API keys, `.env` values, private vocabulary contents, full user
  paths, or other sensitive local data in the work log.
- User instructions about whether delegation is allowed always override the
  orchestration defaults below.

## Agent Orchestration

- For multi-step or parallelizable work, spawn focused subagents rather than
  doing everything in the parent thread.
- Use `AgentSwarm` when the problem can be split into independent lanes with
  distinct, non-overlapping scopes.
- Give each subagent a clear, bounded responsibility and all the context it
  needs; do not duplicate work across agents.
- Prefer read-only exploration agents for investigation, coder agents for
  file changes, and plan agents for architecture decisions.

## Team

The owner's goal is a product people other than the author use; `PRODUCT.md`
holds the audience, the promise, the loop and the milestones. Read it before
planning any work. The work is done by a small team of role agents led by the
parent ("lead") agent. Briefs live in `.claude/agents/`; when a role is not
registered as an agent type in the session, start a general-purpose agent and
tell it to follow the brief file.

| Role | Owns | Brief |
| --- | --- | --- |
| Lead (parent agent) | Plan, contracts between roles, integration, commits, the owner's decisions | this file, `PRODUCT.md` |
| `product-skeptic` | Common sense: is each feature *needed* by real readers; cuts, simplifies, defers (read-only) | the team's veto on bloat |
| `ranking-engineer` | Ranking model, features, shelves, reasons, `ranking_eval` | ranking and its evaluation |
| `backend-engineer` | SQLite library and migrations, bridge contract, readers, export | Python outside ranking |
| `frontend-engineer` | `src/`: screens from `docs/concept/`, components, styles | UI implementation |
| `qa-engineer` | Verification: CI commands, bridge and preview walkthroughs, defect reports | does not fix product code |
| `user-advocate` | First five minutes, reasons to return, README/release notes/onboarding copy | the newcomer's voice |
| `ux-clarity-reviewer` | Meaning and load of every screen (read-only) | see below |
| `design-language-reviewer` | The Кабинет look and light (read-only) | see below |

How the team works:

- **Project chats.** The project chat `Тимлид` coordinates development. Keep a
  persistent chat per specialist in `kindle_app`. Send assignments, planning
  questions, objections and reviews to the existing specialist chat, then read
  its reply and record the decision in `Тимлид`. Use the Codex project chat
  tools to find chats, send messages and collect replies. The role titles below
  are the names shown to the owner in the sidebar.

  | Role | Project chat | Default model | Reasoning |
  | --- | --- | --- | --- |
  | Product skeptic | Продакт-менеджер | `gpt-6.2-sol` | `medium` |
  | User advocate | UX-исследователь | `gpt-6-luna` | `medium` |
  | Backend engineer | Бэкенд-разработчик | `gpt-6.2-sol` | `medium` |
  | Frontend engineer | Фронтенд-разработчик | `gpt-6.2-sol` | `medium` |
  | Ranking engineer | Инженер ранжирования | `gpt-6.2-sol` | `medium` |
  | UX clarity reviewer | UX-дизайнер | `gpt-6.1-terra` | `medium` |
  | Design language reviewer | UI-дизайнер | `gpt-6.1-terra` | `medium` |
  | QA engineer | QA-инженер | `gpt-6.2-sol` | `medium` |
  | Installed application acceptance | QA-инженер по приёмке | `gpt-6.1-terra` | `low` |
  | Release preparation and verification | Релиз-инженер | `gpt-6-luna` | `low` |
  | Anki integration and Claude Design archive provenance | Инженер интеграции с Anki | `gpt-6.2-sol` | `medium` |
  | Recovered Claude project history | Инженер по миграции данных | `gpt-6-luna` | `low` |

- **Plan, build, review, verify, log.** The lead cuts a milestone into tasks
  with one owner each, fixes the contract between roles first (bridge payloads,
  function signatures), then starts the lanes.
- **Planning is a stage in its own right.** After each milestone or lane step,
  the lead opens a team meeting with the reader's goal, evidence from the
  completed stage and unresolved questions. Invite the roles that own the
  choices at stake. They first develop independent positions on the options,
  including the cost of waiting and what evidence would change their view.
  Then circulate specific objections between the participants and let them
  respond before deciding. Record disagreements, the lead's decision and
  rationale, scope, task owners, dependencies and observable acceptance
  criteria in `docs/plan/meetings.md`. Append the outcome to `WORKLOG.md`.
  Bring decisions reserved for the owner with a recommendation. This meeting
  ends with an agreed plan before implementation begins.
- **Lanes do not share files.** Two agents never edit the same file at once.
  Anything that crosses a boundary (a new bridge field, a new ranking output)
  goes through the lead as a contract change.
- **Need before build.** Every milestone plan and every new feature goes to
  `product-skeptic` first. Items it marks "cut" are not built unless the owner
  overrules; "simplify" items are built in the simpler form.
- **Order for UI work:** `ux-clarity-reviewer` on the plan or mockup →
  `frontend-engineer` builds → `design-language-reviewer` → `qa-engineer`.
  **For ranking work:** `ranking-engineer` with before/after numbers → code
  review → `qa-engineer`. **Before a release:** `user-advocate` walkthrough.
- **Every engineer finishes with** passing checks, a `WORKLOG.md` entry and a
  report that says what was not verified. Reviewers and QA report to the lead,
  who decides disputed items.
- **Only the lead commits**, as the owner (no co-author or attribution lines),
  and only finished, checked work. Push, releases and anything public (posts,
  issues, store listings) need the owner's explicit go-ahead.
- **Subagent models.** Choose the model explicitly. Use `gpt-6.2-sol` for
  Sol assignments and research specialists. Do not assign any Astra model to
  subagents. Invite only the roles needed for the decision.
- **The owner decides** product direction, anything that changes what readers
  are promised, new dependencies that grow the installer, dataset downloads,
  and everything public. Bring such questions with a recommendation.

## Design and UX Reviewers

Two read-only reviewer subagents guard every screen, flow and mockup. Their
briefs live in `.claude/agents/`; agents in other tools should follow the same
briefs.

- `ux-clarity-reviewer` — meaning and load. Each screen answers one question
  and has one primary action; every element either leads to an action or
  explains a ranking decision; no statistics for their own sake (no KPI tiles,
  streaks, habit calendars, trend charts); details behind a click; plain
  Russian, one name per concept.
- `design-language-reviewer` — the Night Reading "Кабинет" look from
  `DESIGN.md`: drawn lamps whose light lands on what needs attention (the
  fixture suits the page: sconce in the navigation, desk, clip, pendant,
  banker's lamp, …), pencil instead of boxes and pills, one warm colour, full
  interactive states, correct light geometry.

How to work with them:

- Run `ux-clarity-reviewer` first — on the plan or the first mockup, before
  visual polish. Cutting comes before drawing.
- Run `design-language-reviewer` on the result before calling a UI change done,
  together with the build and screenshot rule in "UI Change Rules".
- Give each the files or artboards and the intent of the change. They only read
  and report "must fix" / "nice to have" items with exact snippets; the parent
  agent applies fixes, decides disputed items and records their findings in its
  own `WORKLOG.md` entry (reviewers do not write to the work log).

## Stack

- Desktop shell: Tauri v2.
- UI: React 18, TypeScript, Vite, Tailwind, Radix primitives, Framer Motion,
  lucide-react.
- Backend: Python package `kindle_vocab_app`.
- Dev runtime: conda env `kindle_app` with Python, Node.js, and Rust/Cargo from
  `environment.yml`.
- Packaging/config: `pyproject.toml`, `package.json`, `src-tauri/`.
- Runtime data: local ignored app data, not repository state.

Important scripts and entry points:

```powershell
conda activate kindle_app
npm install
kindle-vocab-doctor
kindle-vocab-app
```

If the documented conda env is absent on a machine, check `conda env list`; older
local workspaces may have used a similarly named Kindle env.

Useful checks:

```powershell
npm run build
python -m compileall kindle_vocab_app
'{"action":"load_demo","payload":{}}' | python -m kindle_vocab_app.tauri_bridge
python -m kindle_vocab_app.ranking_eval
```

For NLP resources:

```powershell
python -m nltk.downloader -q wordnet omw-1.4 averaged_perceptron_tagger_eng punkt_tab
```

## Architecture Map

- `src/main.tsx` is the main UI. It contains the current workspace screen,
  navigation, status strip, and feature composition.
- `src/features/reading/` contains the reading home, Books, Review, Insights,
  and source-backed reading metrics. Review scores are stored in SQLite.
- `src/lib/backend.ts` is the frontend backend adapter. In Tauri it calls the
  `python_bridge` command; in a plain browser preview it uses mock data.
- `src/types.ts` defines the frontend contract for vocabulary entries,
  processing status, analysis payloads, and API results.
- `src/components/ui/` contains reusable UI primitives. Reuse these before
  adding new one-off controls.
- `src/design/tokens.ts` contains design tokens. UI changes should use these
  tokens instead of ad hoc colors, radii, spacing, or motion values.
- `src-tauri/src/main.rs` owns the Tauri `python_bridge(action, payload)` command.
  It launches `python -m kindle_vocab_app.tauri_bridge` and sends JSON through
  stdin/stdout.
- `kindle_vocab_app/app.py` is now a compatibility launcher for the Tauri dev
  app. It is not the real UI. Do not extend an old PySide/Tk-style UI here.
- `kindle_vocab_app/tauri_bridge.py` is the JSON action dispatcher used by the
  frontend.
- `kindle_vocab_app/kindle_device.py` detects and copies the Kindle `vocab.db`
  from mounted drives, Windows MTP/WPD, or macOS MTP.
- `kindle_vocab_app/reader_sources.py` reads KOReader's
  `vocabulary_builder.sqlite3` (PocketBook, Kobo, Boox, Android, jailbroken
  Kindle) and Kobo's `WordList` into Kindle-shaped entries, detects a file's
  format, and finds those databases on mounted volumes. Their book keys and
  lookup IDs are prefixed `koreader:`/`kobo:`; lexemes keep `sources.kindle`,
  which means "from an e-reader".
- `kindle_vocab_app/kindle_mtp.py` runs read-only macOS USB transfers in an
  isolated worker using an installed OpenMTP Kalam runtime. Passive detection
  uses USB identity only; never bind native write operations.
- `kindle_vocab_app/book_covers.py` caches genuine Kindle/Open Library covers.
  Library loads only read this cache; cover requests never send vocabulary.
- `kindle_vocab_app/kindle_db.py` reads the SQLite Kindle database and exports
  filtered entries.
- `kindle_vocab_app/vocab_optimizer.py` performs deterministic offline word
  filtering, scoring, TSV generation, and per-word JSON analysis.
- `kindle_vocab_app/ranking_eval.py` measures word-ranking strategies on the
  local library (`python -m kindle_vocab_app.ranking_eval`): at monthly
  cutoffs it builds features only from earlier lookups and counts a word as
  needed again when it is looked up again within the next window (42 days by
  default), then reports AUC and precision@k with bootstrap intervals for the
  current importance score, simple baselines and a small learned model.
  Reports go to `.app-data/ranking_eval/` and hold aggregates only. Any change
  to ranking must be measured with it before and after.
- `kindle_vocab_app/library_repository.py` owns the authoritative local SQLite
  library, schema migration, canonical deduplication, processing queue,
  review schedule, and destination state. The database is
  `.app-data/kindle_cards.sqlite3`.
- `kindle_vocab_app/processing_state.py` stores the legacy snapshot used only by
  standalone optimizer CLI compatibility and one-time SQLite migration.
- `kindle_vocab_app/offline_dictionary.py` looks up offline Russian meanings in
  the bundled Wiktionary dictionary for library lexemes, review cards and Anki
  notes.
- `kindle_vocab_app/llm_enricher.py` optionally enriches existing TSV rows
  through the DS Lab/OpenAI-compatible API.
- `kindle_vocab_app/optimizer_cli.py` exposes optimizer and enrichment CLI modes.
- `kindle_vocab_app/settings.py` persists application settings to
  `.app-data/settings.json`.
- `kindle_vocab_app/vocab_cache.py` contains legacy catalog normalization and
  Kindle merge helpers. `.app-data/vocab_cache.json` is migration input, not an
  application source of truth after SQLite has been created.
- `kindle_vocab_app/obsidian_sync.py` reads and writes Spaced Repetition cards in
  Obsidian markdown format, handles priority-file mapping, and backs up the
  Obsidian cards folder before writes.

## Backend Contracts

The Tauri bridge currently supports these actions:

- `scan` / `sync_kindle`: find Kindle and any KOReader/Kobo databases on
  mounted volumes, copy them into `.app-data/cache` (with KOReader's WAL
  journal), merge forms and contexts into SQLite, and enqueue only unseen
  canonical lexemes for processing. `connector_status` reports such a reader
  as the `kindle` connector with its own label.
- `import_reader_file`: merge a words database the user picked (base64 in
  `data_base64`): Kindle `vocab.db`, KOReader or Kobo, detected by its tables;
  re-importing the same file adds nothing.
- `load_demo`: return demo vocabulary state without touching a Kindle or cache.
- `download_covers`: read cached Kindle book identifiers, cache local thumbnails
  and exact Open Library matches, and return the refreshed library and counts.
- `load_library` / `load_cached`: return the SQLite library and durable queue
  status without touching Kindle or Obsidian.
- `save_card_edit` accepts a lexeme ID and partial edits to `meaning_ru` and
  `example_occurrence_id`. An empty field resets that override. SQLite validates
  the selected occurrence before committing either field. The response contains
  the updated entry used by the editor and the next export.
- `set_decision` saves a reader decision or clears it with JSON `null`. It
  returns the updated entry and current `shelves`, `newBatch`, `disputed` and
  `again` summaries. A skipped word remains available under «Остальные».
- `process_queue`: sequentially analyze the persistent SQLite queue and commit
  every completed lexeme before moving to the next one. The frontend starts it
  automatically while the application is open.
- `process_lexemes` / `optimize`: compatible explicit processing actions for
  selected queued ids; application state still commits to SQLite.
- `export`: write `.app-data/kindle-anki.tsv` or `.app-data/kindle-quizlet.tsv`.
- `load_settings`: return the persisted `AppSettings` dict from
  `.app-data/settings.json` (or defaults if missing).
- `save_settings`: validate and persist a settings dict; returns `{"saved": true}`.
- `load_obsidian`: read-only reconciliation. It checks whether existing SQLite
  lexemes are present in Obsidian but never imports cards, contexts, analyses,
  priorities, or translations into the database.
- `sync_obsidian`: reconcile the live vault, append only eligible
  `ready + accepted + score 3..10` SQLite lexemes, verify the append, and then
  persist destination evidence. Obsidian is never a vocabulary source.
- `load_review` / `rate_review`: load due accepted words and store a local
  interval after `again`, `hard`, or `good` ratings.

Bridge output must be clean JSON on stdout. Do not add debug `print(...)` calls
to stdout in bridge code; use logging/stderr/file logs. The Rust bridge forces
UTF-8 via `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`.

Environment variables used by the bridge and launcher:

- `KINDLE_CARDS_PYTHON`: Python executable used by Tauri.
- `KINDLE_CARDS_WORKSPACE`: workspace root passed to Python.
- `KINDLE_VOCAB_LOG_LEVEL`: logging level, for example `DEBUG`.

## Optimizer And Data Rules

The optimizer is intentionally deterministic and explainable. Preserve that
property unless the user explicitly asks for a different model.

- Process only unseen canonical lexical keys by default.
- Persist desktop state and the resumable queue in SQLite after every lexeme.
- Treat Obsidian as a one-way destination: `Kindle -> SQLite -> Obsidian`.
- Never restore application state from JSON once SQLite migration succeeded.
- Keep `processed_snapshot.json` only for standalone CLI compatibility and
  migration of older installations.
- Preserve existing optimized TSV rows when rerunning incremental processing.
- Write per-word JSON audit files under `word_analysis/`.
- Leave translation/enrichment fields empty when local logic cannot derive them
  correctly.
- Do not fabricate LLM-derived fields.
- Offline Russian meanings come from `kindle_vocab_app/data/en_ru_wiktionary.sqlite`
  (Russian Wiktionary via Wiktextract, CC BY-SA 4.0, built by
  `packaging/build_dictionary.py`). They are looked up when the library, review
  cards or Anki notes are built, never stored in analyses, so existing lexemes
  get them without reprocessing. A ready LLM translation always wins. The
  optimizer's `wiktionary` analysis features (register labels, domains) remain
  a placeholder.

The optimized TSV schema is template-driven and was designed to match the
attached `kindle_anki_optimized.tsv` style. Be careful when changing columns:
the app and CLI both depend on stable import/export behavior.

## LLM Enrichment

Optional enrichment uses DS Lab with an OpenAI-compatible client.

Expected `.env` keys:

```text
DSLAB_API_KEY=...
DSLAB_BASE_URL=https://api.dslab.tech/v1
DSLAB_MODEL=deepseek-v4-flash
```

Also supported: `DSLAB_REASONING_EFFORT`, `DSLAB_TIMEOUT_SECONDS`.

Never commit `.env`, API keys, generated enrichment outputs, or user dictionary
state.

## Runtime Files

Treat these as local/user data and keep them out of commits:

- `.app-data/`
- `.env`
- `vocab.db`
- `kindle-anki.tsv`
- `kindle-quizlet.tsv`
- `kindle_vocab_app.egg-info/`
- `node_modules/`
- `dist/`
- `build/`
- `src-tauri/target/`

The project intentionally tracks `.npmrc` because npm 11 requires explicit
script approval for `esbuild`; without it, fresh installs can leave Vite in a
partially usable state or emit avoidable warnings.

## UI Change Rules

These rules are mandatory for UI work in this repository:

- New features must fit into the existing information architecture. Do not add a
  separate visual language or a detached panel unless the workflow truly needs
  it.
- Reuse existing components from `src/components/ui/` and design tokens from
  `src/design/tokens.ts` before creating new primitives.
- Keep the product visually modern, dense, and work-oriented. Avoid generic
  "AI dashboard" decoration, random gradients, and decorative cards without a
  functional reason.
- Every interactive component needs deliberate hover, pressed, focused,
  disabled, and loading states.
- Every async workflow needs loading, empty, and error states.
- Do not mix business logic into presentational components when a reusable
  helper or backend action is the natural boundary.
- Major UI changes require running the app or build, capturing/reviewing the
  screen, and doing a visual polish pass before considering the work complete.

## Development Notes

- The frontend can be opened in a browser with mock data, but real Kindle
  scanning and filesystem export require Tauri.
- When changing the bridge contract, update TypeScript types, Python dispatcher,
  and Rust error handling together.
- When changing optimizer behavior, add or update a focused CLI/bridge smoke
  check. The most important regression to avoid is reprocessing already-seen
  words.
- Prefer small, explicit configuration files over hidden heuristics. Book genre
  relevance should be configured manually; do not infer genre from title alone.
- Logs are written under local app data for the app and under output-specific
  log directories for CLI runs.
