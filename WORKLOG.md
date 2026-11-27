# Agent Work Log

This file is an append-only engineering journal for agents working on the
project. Read it before starting work and append a dated entry after every
logical batch. Do not store secrets or private vocabulary data here.

## 2026-07-11 - Codex - Lifecycle and synchronization redesign started

### Goal

Replace the overloaded entry status model with independent lexeme freshness,
processing, source membership, and destination synchronization states. Preserve
Kindle contexts, integrate Obsidian without replacing the library, and make
connector/process UI states factual.

### Audit

- Reviewed commits `2311f25` and `4e25a5f` and the current ignored runtime cache.
- Confirmed that `processing_status` currently mixes novelty and processing.
- Confirmed that `export_status` is reused for file export and Obsidian sync.
- Confirmed that enabling Obsidian replaces frontend library state before a
  client-side lemma merge, losing reliable provenance.
- Confirmed that the cache merge drops fresh Kindle occurrences when a base form
  already exists.
- Confirmed that a missing Kindle returns cached data without a separate physical
  connection state.
- Confirmed that pipeline progress is timer-driven and cancel only ignores the
  eventual response.

### Decisions

- One library row represents one lemma; forms and contexts are occurrences.
- A lemma is new only until the next successful Kindle synchronization.
- Obsidian-imported cards are known, processed, and synchronized.
- Obsidian content wins on conflicts; Kindle contributes forms and occurrences.
- Offline processing remains a manual action.
- The main Obsidian action synchronizes all eligible pending lexemes, regardless
  of the current table filter.
- This implementation is performed by Codex without subagents, per user request.

### Verification Before Changes

- `npm.cmd run build`: passed.
- `conda run -n kindle_app python tests/test_obsidian_sync_smoke.py`: passed.
- `pytest` is not installed in the `kindle_app` conda environment; backend tests
  will use the standard-library `unittest` runner.

### Next

- Introduce catalog schema v2 and migration.
- Replace bridge and frontend contracts.
- Add real progress/cancellation, UI integration, tests, and visual QA.

## 2026-07-11 - Codex - Lifecycle and synchronization redesign implemented

### Backend And Runtime

- Replaced cache v1 entries with catalog v2 lexemes, occurrences, freshness,
  processing, source membership, and independent destination states.
- Added atomic v1 migration with a one-time `.v1.bak` backup and source
  reconciliation from cached Kindle data and configured Obsidian cards.
- Changed Kindle synchronization to preserve known processing while adding new
  forms and contexts. A successful sync advances the novelty batch.
- Changed Obsidian import to merge into the catalog with Obsidian analysis as the
  authority instead of replacing frontend state.
- Added per-lexeme Obsidian outcomes: `added`, `already_present`, `blocked`, and
  `failed`. Existing cards are never overwritten.
- Added optimizer progress callbacks and structured progress events on stderr;
  stdout remains clean bridge JSON.
- Changed the Tauri bridge to stream progress events and terminate the child
  Python process when `cancel_python_bridge(job_id)` is called.
- Improved Obsidian card rendering so the English base form survives round-trip
  parsing for enriched and `NN_PENDING` cards.

### Frontend

- Replaced the old entry contract with `LexemeRecord` and independent connector,
  processing, freshness, source, and destination types.
- Split the former monolithic `src/main.tsx` into a controller hook, pure domain
  selectors, and focused workspace components.
- Removed the bottom-left source card and timer-driven pipeline.
- Added factual Kindle/Obsidian connector controls, five-second focused-window
  probing, combined row states, grouped contexts, global Obsidian sync, and a
  compact operation rail with cancel, retry, and dismiss states.
- Added a real Obsidian enable switch to Settings.
- Added deterministic browser preview scenarios for mixed, disconnected, slow,
  and one-time operation-error states.

### Local Data Migration

- Migrated the ignored local catalog successfully: 1,022 legacy rows became 997
  lexemes without deleting occurrences.
- Reconciliation produced 809 `ready + synced` lexemes and 188
  `pending + not_synced` lexemes.
- Runtime data and its backup remain ignored and are not part of commits.

### Tests And Visual QA

- `python -m compileall kindle_vocab_app`: passed.
- `python -m unittest discover -s tests -v`: 8 tests passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `cargo check`: passed.
- `git diff --check`: passed; only expected Windows line-ending warnings.
- Browser QA at 1280x720 passed with no console errors and no body overflow.
- Verified filtering, manual processing, global Obsidian sync, disconnected
  Kindle, operation error plus successful retry, cancellation restoring pending
  state, settings navigation, and the Obsidian enable switch.
- Visual polish removed a horizontal table scrollbar, prevented metadata wrapping,
  and improved the narrow inspector's Obsidian status layout.

### Failures Encountered

- `pytest` was unavailable, so backend tests use standard `unittest`.
- Two simultaneous `conda run` commands conflicted over a conda temporary file;
  all conda checks are now run sequentially.
- Vitest dependency installation and execution initially lacked sandbox access;
  both succeeded with the approved external npm cache access.
- PowerShell `Start-Process` inherited duplicate `Path`/`PATH` keys; the local
  Vite server was started through an approved detached Windows process instead.

### Remaining Risk

- Browser preview validates frontend workflows; the Tauri-specific child-process
  cancellation path is covered by Rust compilation and code review, not an
  automated end-to-end WebView test.

## 2026-07-11 - Codex - Redesign finalized

### Commits

- `37d64dd` - work-log protocol and mandatory agent rules.
- `4031d24` - catalog v2, backend lifecycle, progress/cancel bridge, and tests.
- `fc4603b` - React domain/controller/component refactor and Vitest coverage.

### Final Verification

- Re-ran the production frontend build after the final controller and retry
  changes: passed.
- Final Browser screenshots cover a mixed Kindle/Obsidian library with an
  inspected processed lemma and a disconnected Kindle with cached data retained.
- Final console error/warning collection was empty.
- `.kimi-code/`, `.vscode/`, generated screenshots, runtime cache, migration
  backup, logs, and user dictionary data were intentionally left untracked.

## 2026-07-11 - Kimi - Fix Kindle connector flicker and bridge `sync_id` crash

### Goal

Fix two regressions reported after the Codex redesign:

1. The Kindle connector button lost its glow and the disconnected notice flashed
   during every background probe, even when the Kindle was still connected.
2. Offline processing failed with `UnboundLocalError: cannot access local variable 'sync_id'`.

### Changes

- `kindle_vocab_app/tauri_bridge.py`: removed duplicated `process_lexemes`,
  `export`, and `load_demo` branches left over from the redesign merge. The
  remaining `process_lexemes`/`optimize` handler is the correct one and no
  longer references the undefined `sync_id` or `source.label` variables.
- `src/features/library/use-library-controller.ts`: stopped setting the Kindle
  connector state to `checking` during `probeConnectors`; the previous connected
  state is now preserved until the probe returns a new factual state.
- `src/features/library/library-workspace.tsx`:
  - `ConnectorNotice` now renders only when the Kindle state is `disconnected`,
    so it no longer appears during checks or errors.
  - `ConnectorButton` no longer uses the `checking` state for a spinner, since
    probing no longer transitions to that state.

### Verification

- `python -m compileall kindle_vocab_app`: passed.
- `python -m unittest discover -s tests -v`: 8 tests passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `cargo check`: passed.
- `git diff --check`: passed.

### Remaining Risk

- Visual QA was limited to a successful production build and TypeScript checks;
  a live browser/Tauri screenshot was not captured because no browser automation
  tooling was installed in the current environment.

## 2026-07-11 - Kimi - Fix `process_lexemes` tuple handling and add bridge smoke test

### Goal

Fix the follow-up regression `'tuple' object has no attribute 'get'` during offline
processing and add a focused smoke test for the bridge `process_lexemes` path.

### Changes

- `kindle_vocab_app/tauri_bridge.py`: in the `process_lexemes`/`optimize`
  handler, unpacked the tuple returned by `_analysis_by_lemma` into
  `(analyses, analyses_by_id)` and restored the lookup by representative entry id.
- `tests/test_tauri_bridge_smoke.py`: added a new test module covering:
  - `_analysis_by_lemma` returning a `(by_lemma, by_id)` tuple;
  - `dispatch("process_lexemes", ...)` running end-to-end without crashing on
    the tuple return value.
- `.kimi-code/AGENTS.md`: added a "Mandatory verification after every code change"
  section requiring runtime checks, not just static checks, before reporting
  completion.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 10 tests
  passed (including 2 new bridge smoke tests).
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed.
- `cargo check`: passed.
- `git diff --check`: passed.

### Remaining Risk

- The new smoke test exercises the happy path; it does not cover all failure
  modes of the optimizer or cancellation edge cases.

## 2026-07-11 - Codex - Recover skipped offline analyses and verify Obsidian state

### Goal

Resolve the remaining bridge error `Не найден audit-файл offline-обработки` and
verify that catalog synchronization marks agree with the configured Obsidian
cards without writing to the vault.

### Changes

- Corrected `process_lexemes` to look up optimizer results by the optimizer's
  normalized candidate key, not only by the display form stored in the catalog.
  This recovers previously processed forms such as an inflected word whose
  audit/snapshot belongs to its base form.
- Treated entries for which the English offline optimizer cannot form a
  candidate as an explicit `rejected` result with the
  `unsupported_language` reason. They no longer report a missing audit file.
- Normalized Obsidian queue reasons from the independent processing state:
  `ready` entries are ready to sync, while rejected and failed entries retain a
  factual blocking reason.
- Added bridge regression coverage for both normalized snapshot recovery and
  unsupported-language rejection.

### Verification

- Re-ran the actual pending-failure batch after the fix: no lexemes remain in
  the `failed` processing state; the unsupported entry is correctly rejected.
- Read-only reconciliation check found 809 catalog entries marked as synced and
  809 matching normalized lemmas in the configured Obsidian cards; there were
  zero catalog entries falsely marked as synced.
- The remaining Obsidian queue consists of ready entries awaiting sync and
  rejected entries with explicit blocking reasons. No vault files were written
  during this verification.

## 2026-07-12 - Kimi - Step 1: async python_bridge with spawn_blocking

### Goal

Make the Tauri `python_bridge` command asynchronous and offload the blocking
Python child-process wait to `tauri::async_runtime::spawn_blocking`, preventing
the Tauri main/UI thread from blocking during backend calls.

### Changes

- `src-tauri/src/main.rs`:
  - Converted `python_bridge` to `async fn` while preserving its
    `Result<Value, String>` frontend contract.
  - Wrapped the managed `OperationState` in `Arc<OperationState>` so it can be
    cloned into the async task and its Drop guard.
  - Added `CancellationTokenGuard` to guarantee removal of the cancellation
    token from `OperationState` even if `spawn_blocking` panics or returns an
    error.
  - Changed `run_python_bridge` to accept `Arc<AtomicBool>` instead of
    `&AtomicBool` for `'static` use inside `spawn_blocking`.
  - Kept `cancel_python_bridge` synchronous and kept the JSON contract and
    progress event emission logic unchanged.

### Verification

- `cargo check` inside `src-tauri`: passed.
- `npm run build`: passed (1,996 modules transformed).

### Remaining Risk

- The change compiles and builds, but the actual WebView→Rust→Python latency
  improvement was not measured with a running Tauri app in this step.
- Concurrent cancellation during a blocking backend call is logically preserved,
  but not exercised by an automated end-to-end test yet.

## 2026-07-12 - Kimi - Step 2: avoid heavy reconciliation on read-only library loads

### Goal

Stop re-reconciling Kindle and Obsidian data on every `load_library`/`load_cached`
call. Heavy reconciliation should only happen during explicit actions that mutate
the catalog.

### Changes

- `kindle_vocab_app/tauri_bridge.py`:
  - Added `reconcile_obsidian: bool = True` to `_load_catalog_with_sources` while
    keeping the existing `reconcile_kindle: bool = True` default.
  - Changed `load_library`/`load_cached` to call with both reconciliation flags
    set to `False`.
  - Changed `sync_kindle`/`scan`, `process_lexemes`/`optimize`, `export`,
    `load_obsidian`, and `sync_obsidian` to call with both flags set to `False`;
    these handlers apply their own targeted Kindle/Obsidian updates afterwards.
  - No response shapes or other logic were changed.

### Verification

- `python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 11 tests
  passed.
- The base-env run failed only because the `wordfreq` dependency is not installed
  outside the `kindle_app` conda environment; this is environmental, not a code
  regression.

### Remaining Risk

- `load_obsidian` now goes through `_load_catalog_with_sources` (which saves the
  catalog and refreshes destination states) before applying its own Obsidian
  merge. This matches the new contract but adds a small amount of redundant I/O
  compared to the previous direct `vocab_cache.load` call.

## 2026-07-12 - Kimi - Frontend performance fix Steps 3–6

### Goal

Reduce React re-renders, debounce search input, remove forced layout in the
operation rail, reduce connector probing frequency, and virtualize the lexeme
table.

### Changes

- `src/features/library/use-library-controller.ts`:
  - Replaced `React.useDeferredValue(query)` with an explicit `debouncedQuery`
    state updated via `setTimeout(..., 180)` and cleared on unmount/query
    change. The controlled `<Input>` still uses `query`; filtering uses
    `debouncedQuery`.
  - Increased the `connector_status` probe interval from 5 s to 30 s.
  - Added a `lastProbedAt` ref that skips interval/focus probes occurring
    sooner than 30 s after the previous probe. Explicit probes (e.g. after a
    Kindle sync) still run immediately via a new `force` argument.
  - Wrapped the returned controller object in `React.useMemo` with all
    primitives, derived values, and callbacks as dependencies, giving
    `LibraryWorkspace`'s `React.memo` a stable reference.

- `src/features/library/library-workspace.tsx`:
  - Removed the `layout` prop from `motion.section` in `OperationRail`; the
    `AnimatePresence` height animation remains.
  - Virtualized `LexemeTable`: tracks `scrollTop`/`clientHeight` of the scroll
    container, renders an overscan slice (±5 rows) with spacer rows before and
    after, and scrolls the selected row into view when it leaves the visible
    window. `LexemeRow` and its `React.memo` are unchanged.

### Verification

- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `git diff --check`: passed (only expected Windows line-ending warnings).

### Remaining Risk

- The virtualized list assumes a fixed 48 px row height. Rows with unusually
    long lemmata or contexts could grow slightly, causing minor scroll drift;
    visual QA on a large real library is recommended.
- Connector probes are now spaced 30 s apart; users connecting/disconnecting a
    Kindle between probes will see the state update only on the next scheduled
    probe or an explicit sync action.

## 2026-07-12 - Kimi - Integrated performance fixes

### Goal

Integrate the async Tauri bridge, Python reconciliation flags, and frontend
performance improvements, then verify the combined change.

### Integration

- Reviewed the three parallel coder outputs (Rust async bridge, Python reconcile
  flags, frontend memoization/virtualization).
- Confirmed no overlapping file edits and no JSON contract changes.
- Verified that `CancellationTokenGuard` removes the token even if the blocking
  task panics.
- Confirmed `_load_catalog_with_sources` defaults remain backward-compatible.
- Checked that the virtualized table preserves grid columns and scrolls selected
  rows into view.

### Verification

- `cargo check` inside `src-tauri`: passed.
- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 11 tests
  passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `git diff --check`: passed (only expected Windows line-ending warnings).

### Remaining Risk

- Real-world Tauri UI smoothness (window move/resize during heavy operations)
  was not measured in this environment because no live WebView profiling tool
  is available here.
- Visual QA of the virtualized table with a very large library is recommended.

## 2026-07-13 - Kimi - Backend: restore skipped snapshot state and report skip count

### Goal

Fix the backend part of three reported issues:
1. Provide a stable Kindle connection signature for frontend auto-sync detection.
2. Restore `ready` processing state for lexemes already present in the processed snapshot when the catalog loads.
3. Include the `skipped_existing` count in the offline-processing completion message so the UI can explain the numbers.

### Changes

- `kindle_vocab_app/tauri_bridge.py`:
  - `_connector_status` now returns `signature` for a connected Kindle source using `source.signature` from `find_kindle_source()`.
  - `_load_catalog_with_sources` now calls `_restore_ready_from_snapshot` after reconciliation and before saving. Pending lexemes whose normalized `lemma`, `display_form`, or any `form` matches a key in `.app-data/optimized/processed_snapshot.json` are marked `ready` with an analysis built by `_analysis_from_snapshot`.
  - Added helpers `_restore_ready_from_snapshot` and `_lexeme_snapshot_keys`.
  - The `process_lexemes`/`optimize` completion event message is now in Russian and includes the `skipped_existing` count: "Обработано: N; принято: N; отклонено: N; пропущено ранее: M".

- `tests/test_tauri_bridge_smoke.py`:
  - Replaced the old `test_process_lexemes_recovers_snapshot_using_normalized_candidate_key` with `test_load_catalog_restores_ready_state_from_snapshot`, which verifies the new catalog-load restore path.
  - Added `test_process_lexemes_message_includes_skipped_existing_in_russian` to assert the Russian message and skip count.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 12 tests passed.

### Remaining Risk

- The snapshot restore only matches by normalized lemma/forms; lexemes whose processed snapshot key differs from all stored forms will remain pending until reprocessed.
- The new `signature` field in `_connector_status` is only present when a Kindle source is actually connected; the frontend must handle its absence on disconnected/unknown states.
- Full cross-layer verification (npm test, npm run build, cargo check) is left to the integration pass.

## 2026-07-13 - Kimi - Frontend auto-sync, table virtualization, and integration

### Goal

Complete the frontend and integration parts of the three reported issues:
1. Auto-sync Kindle when the connector probe detects a new connection or device signature.
2. Fix the virtualized lexeme table so it renders all visible rows on first mount.
3. Wire the backend's Russian skip-count message through to the UI and verify the full stack.

### Changes

- `src/types.ts`:
  - Added optional `signature?: string[]` to `ConnectorInfo`.

- `src/lib/backend.ts`:
  - `mockConnectors` now returns a stable `signature` for the connected Kindle preview source.

- `src/features/library/use-library-controller.ts`:
  - Added `prevConnectorsRef`, `lastAutoSyncSignatureRef`, and `syncKindleRef`.
  - `probeConnectors` now compares the current Kindle state/signature with the previous probe and triggers `syncKindle` only on a genuine transition to `connected` or when a new signature appears, skipping duplicates and avoiding loops.
  - `syncKindle` records the synced signature so the next probe does not re-trigger.
  - `processVisible` now uses the backend's `message` if present and falls back to a Russian message that includes `skipped_existing`.

- `src/features/library/library-workspace.tsx`:
  - Replaced the post-mount viewport measurement with a callback ref that reads `clientHeight` synchronously when the scroll container is attached.
  - Added a `ResizeObserver` to keep `viewportHeight` accurate on resize.
  - Removed the mutable `containerRef` in favor of a `container` state variable, avoiding TypeScript readonly-ref issues.

- `kindle_vocab_app/tauri_bridge.py`:
  - Added a top-level `message` field to the `process_lexemes`/`optimize` response containing the same Russian skip-count text already used in the event array.

### Verification

- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 12 tests passed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed (only expected Windows line-ending warning for `WORKLOG.md`).

### Remaining Risk

- Auto-sync is gated by the 30-second probe interval; a Kindle connected and disconnected within that window may be missed.
- The virtualized table still assumes a fixed 48 px row height; unusually long content could cause minor scroll drift on very large libraries.
- Live browser/Tauri screenshot QA was not performed in this environment.

## 2026-07-13 - Kimi - Integration: auto-sync, table virtualization, and snapshot restore

### Goal

Integrate and verify the three reported fixes across frontend, backend, and contracts:
1. Automatic Kindle sync when the device is connected or its signature changes.
2. Virtualized lexeme table renders all visible rows on first paint.
3. Processed-snapshot lexemes are restored to ready state and the skip count is reported in the UI.

### Changes

- `src/types.ts`: added optional `signature?: string[]` to `ConnectorInfo`.
- `src/lib/backend.ts`: mock backend connector status now returns a stable `signature` for the Kindle preview source.
- `src/features/library/use-library-controller.ts`:
  - Tracks the previous connector status and the last auto-synced Kindle signature in refs.
  - `probeConnectors` triggers `syncKindle` only on a genuine transition to `connected` or when the signature changes, avoiding duplicate syncs and loops.
  - `processVisible` now includes `skipped_existing` in the completion message shown in the operation rail.
- `src/features/library/library-workspace.tsx`: fixed the virtualized table initial render by measuring the scroll container through a callback ref and `ResizeObserver`, so `viewportHeight` is never stuck at 0.
- `kindle_vocab_app/tauri_bridge.py`: already updated by the backend pass; verified that `_connector_status` returns `signature`, `_load_catalog_with_sources` restores snapshot state, and the completion event reports `skipped_existing` in Russian.
- `tests/test_tauri_bridge_smoke.py`: already updated by the backend pass; tests pass.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 12 tests passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed (only expected Windows line-ending warning for `WORKLOG.md`).

### Remaining Risk

- The snapshot restore currently marks every matched lexeme as `ready`, even if the snapshot entry was originally rejected (`accepted: false`). The analysis object preserves the correct `accepted` value, but the UI state does not reflect rejection. This matches the current instruction to set state to `ready`, but may need refinement if rejected snapshot entries exist in the wild.
- First-render auto-sync may trigger an immediate `sync_kindle` when a Kindle is already connected at app startup; this is intentional but could surprise users who expected the app to stay on the cached library.
- Real-world Tauri end-to-end verification (actual USB Kindle connection, auto-sync timing, and large-library table scrolling) was not performed in this environment.

## 2026-07-13 - Kimi - Refine snapshot restore for rejected entries

### Goal

Ensure that lexemes restored from the processed snapshot reflect their original
acceptance status instead of always appearing as `ready`.

### Changes

- `kindle_vocab_app/tauri_bridge.py`: `_restore_ready_from_snapshot` now sets
  `processing.state` to `rejected` when the snapshot entry has `accepted: false`.
- `tests/test_tauri_bridge_smoke.py`: added
  `test_load_catalog_restores_rejected_state_from_snapshot` to cover the
  rejected-restore path.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 13 tests
  passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`:
  passed.
- `git diff --check`: passed (only expected Windows line-ending warnings).

### Remaining Risk

- Live USB Kindle auto-sync timing and large-library table virtualization were
  not verified in this environment.

## 2026-07-13 - Codex - Passive Kindle presence probing

### Goal

Keep automatic Kindle synchronization while preventing periodic connector
checks from browsing device storage or opening `vocab.db`.

### Changes

- Added a lightweight `KindlePresence` detector that checks only top-level
  devices shown by Windows under "This PC". Mounted-volume fallback checks the
  volume identity but does not search folders.
- `connector_status` now uses the passive detector. Full MTP/path traversal and
  copying remain confined to `sync_kindle`.
- Connector polling is limited to once per minute, overlapping probes are
  suppressed, and failed automatic synchronization retries use a five-minute
  backoff.
- Added Python and Vitest coverage for the passive boundary and retry policy.

### Verification

- `conda run -n kindle_app python -m unittest discover -s tests -v`: 16 passed.
- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `npm test`: 6 passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed with expected Windows line-ending warnings.

### Device Safety

- Background probes do not enumerate Kindle folders or copy files.
- Synchronization copies `vocab.db` from Kindle to a local staging/cache path;
  the application never writes, renames, or deletes files on the device.
- A live passive probe reported the device as disconnected at verification
  time, so the connected-device path remains covered by mocks rather than a
  physical Kindle test.

## 2026-07-14 - Codex - SQLite library and one-way Obsidian sync

### Goal

Replace competing JSON state files with one durable SQLite library, process new
Kindle lexemes through a resumable queue, and make Obsidian a verified one-way
destination rather than a source of vocabulary state.

### Decisions

- `.app-data/kindle_cards.sqlite3` is the authoritative application store.
  Legacy catalog and snapshot JSON files are imported once and backed up, but
  are no longer written by the application bridge.
- Lexemes are unique by language and canonical key; forms and Kindle contexts
  remain separate records, and context fingerprints prevent duplicate imports.
- Queue items are committed one lexeme at a time. Accepted and rejected terminal
  states are both durable and are not reanalysed when another form or context is
  discovered.
- Obsidian is read only for reconciliation. A sync rereads the vault, backs it
  up, appends eligible cards, verifies the result, and only then records a
  destination as synced.
- Rejected lexemes remain visible under `Все`, but are excluded from `Новые`
  and `Не в Obsidian`.

### Changes

- Added the versioned SQLite repository, migration, repository-level queue,
  analysis, destination, and sync-run persistence.
- Moved bridge loading, Kindle sync, processing, export state, and Obsidian
  reconciliation to the repository. Added `process_queue` while preserving the
  explicit `process_lexemes` compatibility action.
- Hardened Obsidian append-only writes with exact prefix verification and
  duplicate-lemma blocking inside a single sync batch.
- Replaced the normal manual processing control with compact automatic queue
  status and retry-on-error behavior. Fixed automatic queue resumption after a
  Kindle operation completed.
- Updated frontend contracts, filters, preview fixtures, project documentation,
  and focused Python/Vitest coverage.

### Local Migration Audit

- Imported 1,039 canonical lexemes and 1,332 non-Obsidian occurrences.
- Preserved 1,023 ready and 16 rejected states; the persistent queue is empty.
- Reconciliation reports 1,022 synced, 16 not applicable, and 1 missing
  Obsidian destination, repairing the previously stale synced state.
- SQLite integrity check passed, foreign-key violations are zero, and both
  legacy JSON backup files exist.
- No Obsidian write was performed during the audit.

### Verification

- `conda run -n kindle_app python -m unittest discover -s tests`: 21 passed.
- `conda run -n kindle_app python -m compileall -q kindle_vocab_app`: passed.
- `npm test -- --run`: 8 passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check -q --manifest-path src-tauri/Cargo.toml`:
  passed.
- Bridge `load_library` smoke: 1,039 entries, zero pending/failed queue items.
- Chromium QA at 1,440 x 900 confirmed automatic queue completion, accepted-only
  `Новые`, eligible-only `Не в Obsidian`, bounded table scrolling, and zero
  console errors or warnings.
- `git diff --check`: passed with expected Windows line-ending warnings.

### Remaining Risk

- A physical Kindle was not connected during the final end-to-end run, so the
  new SQLite path is covered by repository/bridge tests and the existing mocked
  device boundary rather than a live USB sync.
- The standalone optimizer CLI intentionally retains snapshot compatibility;
  application runtime state is SQLite-only.

## 2026-09-29 - Codex - Initialize macOS development workspace

### Goal

Initialize this local workspace from `git@github.com:Rescue5/kindle_app.git` and
install the documented development environment.

### Changes

- Configured `origin` and checked out `main` at `1a0d815`, tracking
  `origin/main`.
- Ran `scripts/setup-dev.sh`, creating the `kindle_app` conda environment and
  installing the Python package, npm dependencies, and NLTK resources.
- No application source files were changed.

### Verification

- `kindle-vocab-doctor`: all checks passed.
- `conda run -n kindle_app npm run build`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests`: 21 passed.
- `conda run -n kindle_app npm test`: 8 passed.

### Remaining Risk

- npm reported 6 dependency advisories (3 moderate, 3 high) during installation;
  dependencies were not changed beyond the committed lockfile.

## 2026-09-29 - Codex Review backend subagent - Durable review queue

### Goal

Add a small offline review loop for accepted vocabulary without changing Kindle processing or inventing translations.

### Changes

- Added SQLite schema v2 with per-lexeme review schedule and ratings.
- Added `load_review` and `rate_review` bridge actions. Due cards contain stored analysis and Kindle occurrences; rejected words are excluded.
- Preserved review progress across full catalog replacements used by Kindle and Obsidian synchronization.
- Added focused tests for eligibility, rating intervals, persistence, migration from schema v1, bridge actions, and invalid requests.

### Verification

- `conda run -n kindle_app python -m unittest discover -s tests -v`: 25 passed.
- `git diff --check`: passed.

### Remaining Risk

- The scheduling rules are intentionally basic: again after 10 minutes, hard after at least 1 day, and good after at least 3 days. No long-term retention model or daily new-card limit is implemented.

## 2026-09-29 - Codex subagent - Books and Insights views

### Goal

Add book and reading-insight screens using only the existing `BookOption`,
`LexemeRecord`, and occurrence data.

### Decisions And Changes

- Added `src/features/reading/reading-domain.ts` for book grouping, validated
  date keys, daily activity, and repeat counts.
- Added `src/features/reading/books-view.tsx` with a searchable book shelf,
  selected-book summary, word search, repeat filter, and word-open callback.
- Added `src/features/reading/insights-view.tsx` with factual vocabulary,
  occurrence, book, repeat, and dated activity summaries.
- No reading progress, chapter position, or reading speed is inferred.

### Verification

- `conda run -n kindle_app ./node_modules/.bin/tsc --noEmit`: passed.
- `git diff --check`: passed before this log append.

### Remaining Risk

- These new views are not yet connected to the application navigation in this
  independent work lane. Visual QA belongs to the integration pass after the
  parent wires the screens into the running app.

## 2026-09-29 - Codex - Reading companion interface integrated

### Goal

Turn the utility-focused desktop workspace into a reading vocabulary companion
with a useful home, books, words, review, and insights flow.

### Decisions And Changes

- Created a literary light visual direction and implemented the new navigation,
  home, review card UI, compact background status, and responsive layouts.
- Connected Books and Insights to real saved Kindle occurrences. The home uses
  the latest recorded book, and never invents reading progress or book covers.
- Kept export inside Words and moved processing out of navigation. Added a
  shortcut to review newly found words with the existing New filter.
- Improved the word inspector with its saved context and available translation
  first, plus a calmer treatment of technical analysis and Obsidian state.
- Added browser-preview review actions and focused tests for book grouping,
  activity dates, repeat counts, and Russian count forms.
- Replaced the mismatched app icon with a matching SVG source and PNG/ICO/ICNS
  variants. Added the missing PNG required by Tauri's macOS build context.
- Updated README and architecture notes for the new UI and Review actions.

### Verification

- `conda run -n kindle_app npm run build`: passed.
- `conda run -n kindle_app npm test`: 10 passed.
- `conda run -n kindle_app python -m unittest discover -s tests`: 25 passed.
- `conda run -n kindle_app cargo check -q --manifest-path src-tauri/Cargo.toml`:
  passed after adding the missing icon.
- In-app browser QA covered Home, book selection, book-to-word navigation,
  review reveal and rating, Insights, and Settings. Reviewed desktop, the
  normal browser window, and a 390 px mobile viewport; no horizontal document
  overflow or console warnings/errors were observed.
- `git diff --check`: passed.

### Remaining Risk

- Browser QA used sample data. A live Kindle and the full Tauri WebView workflow
  were not exercised here.
- Review scheduling is intentionally simple; AI explanations and reading
  progress are omitted because the current data cannot support them reliably.

## 2026-09-30 - Codex MTP test subagent - Sync audit and macOS MTP coverage

### Goal

Review existing Kindle synchronization for idempotency and add focused tests for the new macOS MTP adapter without accessing personal vocabulary contents.

### Findings

- SQLite library changes occur only after device copy, database validation, and entry extraction. A transfer failure leaves the library intact.
- Existing mounted-path and Windows MTP copy helpers replace the cached `vocab.db` before SQLite validation; the macOS adapter instead validates its staging copy before replacement.
- Occurrence identity currently uses word, context, book, and date; duplicate lookups with the same values on one day may be counted once. This affects repeated-lookup metrics but does not duplicate processing of known lexemes.

### Changes

- Added `tests/test_kindle_mtp.py` with synthetic USB trees, fake MTP sessions, and temporary SQLite fixtures. Tests cover passive detection, Kindle-only device selection, worker timeout and malformed JSON, incomplete transfer preserving the previous cache, validated cache replacement, and thumbnail path restrictions.

### Verification

- `conda run -n kindle_app python -m unittest tests.test_kindle_mtp -v`: 6 passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 36 passed.
- `git diff --check`: passed.

### Remaining Risk

- The native Kalam ABI and a live USB transfer require separate integration verification; these tests do not open a physical Kindle.

## 2026-09-30 - Codex subagent - Book cover cache and reading UI

### Goal

Show genuine Kindle or Open Library book covers in Home and Books, with a local
cache and a manual Books action to fetch missing covers.

### Decisions And Changes

- Added `kindle_vocab_app/book_covers.py` with `attach_covers`,
  `prefer_local_covers`, and `download_covers`. Kindle portrait thumbnails are
  matched by an ASIN present in the book key and take priority. Open Library
  search uses exact normalized title and author matches, then downloads a
  medium JPEG by Cover ID. Ambiguous works are skipped.
- Limited Open Library requests to HTTPS trusted hosts, bounded response sizes
  and timeouts, and at most 40 new searches per run. Missing results are cached
  for 30 days and transient errors for six hours. Per-book errors are contained.
- Added optional book title, author, cover data URL, and cover status to the
  frontend contract. Home and Books render cached real images and retain the
  typographic fallback. Books has a manual cover-download button with a busy
  state and available-count display.
- Added seven isolated tests using synthetic book data and mocked network
  responses; no user vocabulary database or runtime cover files were read.
- API contract checked against the official Open Library Search and Covers API
  documentation.

### Verification

- `conda run -n kindle_app python -m unittest tests.test_book_covers -v`: 7 passed.
- `conda run -n kindle_app npm run build`: passed.
- `git diff --check`: passed before this log append.

### Remaining Risk

- Bridge/controller wiring and the real Kindle-thumbnail copy are handled by
  the integration lane. A live cover download and final Tauri visual pass were
  not performed in this isolated lane.

## 2026-09-30 - Codex occurrence identity subagent - Preserve distinct Kindle lookups

### Goal

Keep each Kindle lookup distinct while avoiding duplicate occurrences when an existing content-hash catalog is synchronized again with stable Kindle lookup IDs.

### Changes

- `kindle_vocab_app/vocab_cache.py`: Kindle entries with a `lookup_id` now use SHA1 of `kindle|lookup-id|<id>` as the occurrence ID. Entries without a lookup ID retain the previous content-hash behavior.
- Before adding an ID-backed lookup, the merge removes only matching legacy Kindle content-hash occurrences calculated with the full timestamp or the earlier date-only timestamp. Existing ID-backed occurrences are left intact.
- `tests/test_vocab_catalog.py`: added identical-content distinct-ID and repeated-sync checks, plus transition checks for both legacy hash variants.
- `tests/test_kindle_mtp.py`: updated the synthetic MTP session to allow optional root listing for device metadata.

### Verification

- `conda run -n kindle_app python -m unittest tests.test_vocab_catalog -v`: 6 passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 40 passed.
- `git diff --check`: passed.

### Remaining Risk

- A live repeat sync after the current queue finishes is still needed to confirm aggregate lookup counts against the connected Kindle. No personal vocabulary contents were inspected for this change.

## 2026-09-30 - Codex subagent - Recover real book-cover matches

### Goal

Improve cover matching after the first live Kindle synchronization returned no
covers for books whose metadata included file provenance or series decorations.

### Changes

- `kindle_vocab_app/book_covers.py` now strips only recognized trailing source,
  author, copy-number, and series markers for search/display. It preserves the
  original Kindle title in application occurrences. Author matching handles
  reversed names and missing spaces, and title matching treats apostrophes
  consistently.
- Added a bounded second title candidate only when a numbered series prefix
  overlaps the true title. A broad Open Library query can recover punctuation
  variants, but the returned title and author still need exact normalized
  matching and a unique work.
- Local Kindle thumbnail matching accepts an explicit `asin` field when book
  keys are UUIDs. Negative cache entries carry `search_version`; old misses are
  retried without deleting cache files. Manual calls can use
  `retry_errors=True` to retry transient failures.
- Accepted HTTPS redirects from the Open Library Covers API to `archive.org`
  and strict `*.us.archive.org` hosts. Initial requests remain limited to
  Open Library; response host, JPEG type, size, and timeouts are checked.
- Expanded synthetic tests for cleanup, strict matching, local ASIN matching,
  negative-cache refresh, manual retry, and trusted/untrusted redirects.

### Verification

- `conda run -n kindle_app python -m unittest tests.test_book_covers -v`: 17 passed.
- `conda run -n kindle_app python -m unittest discover -s tests`: 50 passed.
- A read-only search for several public titles found exact Cover IDs; one
  full HTTPS search and JPEG download into a temporary test directory returned
  `downloaded=1` and `cover_status=available`.

### Remaining Risk

- Some books may have no exact Open Library work with a cover. They keep the
  typographic fallback rather than receiving a guessed image. The integration
  lane must pass `retry_errors=True` for the manual Books action.

## 2026-09-30 - Codex - Live macOS Kindle synchronization and covers

### Goal

Read the user's connected USB Kindle, add macOS MTP support and genuine cached
book covers, and verify synchronization against the physical device.

### Decisions And Changes

- Identified an Amazon Kindle over USB MTP rather than a mounted volume.
  Downloaded OpenMTP 3.3.0 for Apple Silicon from its official GitHub release,
  verified its Developer ID and notarization with macOS, and installed it in
  Applications. No additional global package manager was installed.
- Added a read-only Kalam adapter in `kindle_mtp.py`. Native transfers run in a
  bounded subprocess with a local exclusive lock, Kindle identity verification,
  fixed source paths, staged SQLite validation, and atomic cache replacement.
  Passive device polling reads USB identity without opening Kindle storage.
- Connected the adapter through `kindle_device.py`. Preserved the existing
  mounted-volume and Windows MTP paths. No files were written to the Kindle.
- Integrated cached ASIN metadata and local Kindle thumbnails with the cover
  service. Connected automatic cover fetching after Kindle sync, manual Books
  downloads, transient-error retry, offline cache reads, counts, and UI states.
  Added cleaned shelf titles while preserving original occurrence metadata.
- Retained full Kindle timestamps and stable lookup IDs. Compatibility migration
  now preserves distinct identical lookups and avoids duplicating older hashes.
- Updated README and architecture/action notes. All personal databases, images,
  local backups, and optimizer outputs remain under ignored app data.

### Verification

- Live transfer copied a validated Vocabulary Builder database and 61 nonempty
  portrait thumbnails. The library contains 1,760 canonical lexemes, 2,522
  distinct lookups, and 7 books after deterministic processing and consolidation.
- Initial queue processing completed. Repeated live synchronization left the
  queue empty; a subsequent processing call processed zero new lexemes.
- Six of seven books have real cached covers: one matched Kindle thumbnail and
  five Open Library downloads. The unmatched book retains a typographic jacket.
- Fixed two concrete integration failures: `ioreg` needs `-l` to include USB
  identity properties in its plist, and Covers API image redirects use the
  Internet Archive HTTPS hosts. Both now have focused coverage.
- `python -m unittest discover -s tests`: 50 passed.
- `npm test`: 10 passed. TypeScript/Vite build and a macOS debug app bundle built
  successfully using `npm run tauri build -- --debug --bundles app`.
- Launched the actual bundled Tauri app with the workspace Python runtime.
  Reviewed the Books screen screenshot with real cached covers and aggregate
  counts; invoked the cover-download button and verified the bridge action.
- `git diff --check`: passed. Personal app data is ignored by Git.

### Remaining Limits

- One book has no exact cover match; no substitute image was guessed.
- macOS became locked after the successful Books visual pass, so an additional
  Home screenshot was unavailable. The final UI build is verified by compilation.
- The debug app still uses the project's Python runtime; distributing a fully
  self-contained desktop package is separate work. Close OpenMTP while Kindle
  Cards owns the MTP connection.

## 2026-10-16 - Codex subagent setup_audit - Windows prerequisites and Kindle workflow

### Цель

Проверить готовность Windows к запуску Tauri и доступный сценарий подключения Kindle без установки ПО, запуска серверов и чтения личной библиотеки.

### Проверки и решения

- Прочитаны AGENTS.md, WORKLOG.md, README.md, setup-dev.ps1 и код точек входа, UI, bridge и Windows Kindle connector.
- Windows preflight подтвердил Windows x64, PowerShell 5.1 и активное окружение base. В ambient PATH отсутствуют Cargo/Rust; настройку проектного conda-окружения выполняет основной агент.
- Через vswhere найдены Visual Studio 18 Community и VC.Tools.x86.x64. Проверено наличие MSVC link.exe/cl.exe версий 14.44 и 14.50, Windows SDK 10.0.26100.0 и VsDevCmd.bat.
- Обнаружен установленный WebView2 Runtime. Ambient link.exe указывает на Scoop shim; при проблемах линковки рекомендовано использовать VsDevCmd, а не менять глобальный PATH.
- Подтверждены оба Windows пути: mounted volume и Shell.Application MTP/WPD. Пассивное обнаружение не обходит содержимое устройства; полная синхронизация копирует vocab.db в локальный cache.
- В UI доступны «Проверить Kindle», «Синхронизировать Kindle», «Книги», «Слова», фильтры, Anki/Quizlet export и «Повторение». Очередь новых лексем обрабатывается автоматически.
- В текущем UI не найден ручной file picker для vocab.db, хотя README перечисляет такую возможность; для первичного сценария использовать USB Kindle и Tauri. Browser preview использует mock data.

### Изменённые файлы и ограничения

- Изменён только WORKLOG.md: добавлена эта запись. Установки, серверы и чтение личных баз не выполнялись.
- Окончательную проверку сборки и запуск Tauri выполняет основной агент. Физический Kindle в этом аудите не проверялся.
- Коммит не создавался.

## 2026-10-16 - Codex subagent setup_audit - Close SQLite handles on Windows

### Цель и причина

Устранить выявленные основным агентом ошибки первого Windows запуска unittest: открытые sqlite3.Connection удерживали временные файлы, а POSIX macOS worker test импортировал отсутствующий в Windows fcntl.

### Изменения

- В kindle_vocab_app/kindle_db.py четыре read-only подключения validate_vocab_db/list_books/fetch_entries закрываются через contextlib.closing до замены cache или выхода из функции. SQLite connection context самостоятельно не закрывает файл.
- В tests/test_kindle_mtp.py fixture явно закрывает SQLite connection; transaction context сохранён. Только worker timeout/JSON test, которому требуется fcntl, пропускается на Windows. Остальные platform-independent MTP проверки выполняются.
- В tests/test_review.py прямые SQLite подключения явно закрываются; запись версии схемы сохраняет прежнюю транзакционную семантику.
- Изменений MTP протокола, схемы базы и правил обработки слов нет. Личные данные не использовались.

### Проверки и ограничения

- conda run -n kindle_app python -m unittest discover -s tests -p test_review.py -v: 4 passed.
- conda run -n kindle_app python -m unittest discover -s tests -p test_kindle_mtp.py -v: 5 passed, 1 skipped (Windows/fcntl).
- Первый повтор MTP suite после исправления завершился WinError 145 при удалении временного cache; последующая проверка нашла cache пустым. Изолированный valid-download test и повтор всего MTP suite затем прошли без дополнительной правки; причина единичной задержки удаления каталога не подтверждена.
- git diff --check проходит с предупреждением о преобразовании LF/CRLF для WORKLOG.md.
- Общий suite и запуск desktop проверяет основной агент. Коммит не создавался.

## 2026-10-16 - Codex - Initialize Windows checkout and launch Kindle Cards

### Цель и выполненная настройка

- Развернут origin/main из запрошенного SSH remote в исходно пустой Git workspace; локальная main отслеживает origin/main.
- Использовано существующее conda-окружение kindle_app: Python 3.11, Node 26.4.0, Rust/Cargo 1.96.1, pywin32 и ресурсы NLTK уже установлены. Editable Python package перепривязан к текущему клону без переустановки зависимостей.
- npm ci установил 227 пакетов по lockfile; production frontend и native debug executable собраны. API key для локального режима не требуется.
- Приложение запущено штатным kindle-vocab-app; подтверждены отвечающее окно Kindle Cards, HTTP 200 dev server и успешные локальные bridge requests/load_review. Создана пустая SQLite библиотека в ignored app data.
- Исправление закрытия SQLite handles и платформенного теста выполнено отдельным агентом и описано выше. Других изменений функциональности нет.

### Проверки и ограничения

- npm run build: passed. npm test: 10 passed. cargo build --locked: passed. kindle-vocab-doctor: все проверки OK.
- Первый frontend build в sandbox не смог прочитать родительские каталоги через esbuild; тот же build вне sandbox прошёл.
- Общий Python suite запускает 50 tests; один POSIX/fcntl test корректно skipped. После исправления SQLite остались непостоянные WinError 145 только при cleanup TemporaryDirectory, в разных тестах, как внутри, так и вне sandbox. Полный suite поэтому не объявляется прошедшим. Целевые MTP и review suites прошли у отдельного агента.
- Временная папка внутри workspace дала дополнительный ложный Kindle presence в тесте, поскольку полный путь содержит kindle_app; это не исправлялось в рамках инициализации. Повтор с внешней папкой без kindle в пути устранил этот assertion, сохранив непостоянную cleanup ошибку.
- Реальный USB перенос не проверен: подключённое устройство не подтверждено. Browser preview использует mock data; работать с устройством следует в открытом Tauri окне.
- Штатный повторный запуск: conda run --no-capture-output -n kindle_app kindle-vocab-app. Коммит не создавался; личные данные и runtime artifacts игнорируются Git.

## 2026-10-16 - Codex subagent obsidian_match_audit - Аудит проверки присутствия в Obsidian

### Цель и выводы

- Прочитаны AGENTS.md и WORKLOG.md, проверены read_cards/parser, bridge reconciliation, UI counters и сохранение настроек. Личные базы и содержимое vault не читались.
- Найден источник устаревшего статуса: UI не вызывает load_obsidian; load_library, sync_kindle и обработка очереди загружают каталог с reconcile_obsidian=False. Настройки сохраняются без read-only сверки, connector_status проверяет существование каталога. Поэтому eligible лексемы получают missing без свежей проверки файлов.
- Выявлены отдельные ограничения matching: индекс Obsidian содержит только base_form, не исходное word; extractor трактует внутренний ASCII дефис как разделитель; нормализация dedup в append_cards слабее bridge normalization. Parser читает только файлы фиксированного Priority шаблона непосредственно в cards_dir.
- Счётчик UI считает eligible + state=missing, а не все слова, фактически отсутствующие в vault. Для достоверной диагностики нужна read-only сверка с правильным каталогом.

### Изменения, проверки и ограничения

- Изменён только WORKLOG.md: добавлена эта запись. Производственный код и тесты не менялись; runtime checks и доступ к пользовательскому vault оставлены основному агенту.
- Проверены исходники и текущие smoke tests. Рекомендованы regression cases: начальная/после настроек сверка без append, сохранение полного hyphenated lemma, совпадение по форме карточки, единая нормализация punctuation/apostrophes.
- Число действительных несовпадений по коду определить нельзя; его независимо проверяет основной агент. Коммит не создавался.

## 2026-10-16 - Codex subagent obsidian_match_audit - Исправление точного matching и защиты сверки

### Цель и изменения

- По поручению основного агента устранены подтверждённые ограничения backend matching без доступа к личным данным, без frontend изменений и без изменения load_library semantics.
- В obsidian_sync.py добавлен общий набор точных aliases карточки (word, stem, analysis.base_form), использованный и reconciliation, и append dedup. Нормализация делегирована vocab_cache.normalize_lemma, UTF-8 reader принимает BOM. Парсер сохраняет внутренний ASCII дефис в лемме.
- В tauri_bridge.py load_obsidian отклоняет отсутствующий каталог и путь к файлу до открытия repository; прежние destination evidence не изменяются при такой ошибке. Reconciliation использует тот же индекс aliases, что append dedup.
- Добавлены синтетические tests в test_obsidian_sync_smoke.py и test_tauri_bridge_smoke.py: hyphenated heading, punctuation/apostrophes, BOM, alias match, отсутствие дубликатов/изменения существующих файлов, invalid-directory сохранение SQLite evidence.

### Проверки и ограничения

- Windows skill preflight подтвердил PowerShell 5.1, Windows x64 и Python 3.11 из проектного conda environment; suites запускались напрямую этим interpreter.
- Obsidian smoke suite: 7 passed. Bridge smoke suite: 11 passed. git diff --check: passed; только ранее известные LF/CRLF warnings.
- Личная SQLite библиотека, vault и настройки не читались и не менялись. Live подсчёт, UI refresh и интеграцию выполняет основной агент. Коммит не создавался.

## 2026-10-16 - Codex - Verify live Obsidian presence and refresh stale counts

### Цель и доказательства

- Проверена указанная пользователем папка карточек только на чтение. Сохранённые настройки указывают на правильный каталог; интеграция включена. Все восемь Priority markdown файлов читаются, 1049 разделителей карточек соответствуют 1049 разобранным карточкам; пустых заголовков нет.
- Начальное состояние SQLite: 1768 лексем, 1750 ready/eligible, 18 rejected. Все eligible имели missing, last_checked_at отсутствовал у всех. Независимая read-only сверка дала 941 совпадение старым алгоритмом, ещё три подтверждены по исходной форме карточки и корректному разбору дефисов.
- Итог после исправления и штатной сверки открытым приложением: 944 synced, 806 missing, 18 not_applicable. Повторное чтение SQLite и независимая сверка в памяти дали те же числа. Новые карточки в пользовательский Obsidian не записывались; sync_obsidian для личного vault не вызывался.

### Изменения и решения

- Backend matching, нормализация, hyphen/BOM и invalid-directory guard исправлены отдельным агентом; детали выше.
- Новый load-library.ts загружает настройки и SQLite параллельно, затем вызывает существующий read-only load_obsidian только для настроенного включённого vault. Backend load_library остаётся быстрым чтением без внешней сверки.
- Контроллер использует эту последовательность при старте, после Kindle sync, после обработки очереди и повторе проверки. После успешного сохранения Obsidian настроек SettingsView обновляет библиотеку через тот же callback; посторонние настройки не вызывают дополнительную сверку.
- При недоступной папке сохраняются cached entries, connector и операция показывают ошибку; Retry повторяет чтение, а не sync_obsidian/append. В browser mock добавлен load_obsidian response.
- Добавлены три frontend regression tests на проверку перед показом библиотеки, disabled integration и сохранение evidence/error без экспорта.

### Проверки

- npm run build: passed; npm test: 13 passed. Backend focused suites: 7 Obsidian + 11 bridge passed. git diff --check: passed с ранее известными LF/CRLF warnings.
- Browser plugin not available. Использован bundled Playwright с уже установленным Edge; bundled Chromium отсутствует, новые browser dependencies не устанавливались. URL localhost:1420, viewport 1320x840, только встроенные demo данные.
- Browser identity/meaningful render/no framework overlay/console health: passed. Проверены фильтр Не в Obsidian, повторная сверка после process_queue и сохранения папки, ошибка недоступности и Retry без sync_obsidian. Скриншоты и временный QA script сохранены вне repository.
- Начальные QA attempts исправляли только инструмент проверки: HMR query в URL требовал wildcard route, ожидание должно учитывать окончание загрузки, locator фильтра требовал exact match. Production failure при этих попытках не найден.
- Полный Python suite не повторялся: проверены затронутые contracts; прежние нестабильные Windows TemporaryDirectory cleanup ошибки остаются отдельным известным ограничением. Mobile и native UI automation не выполнялись; native bridge подтверждён live SQLite состоянием и load_obsidian logs.
- Данные слов и полные пользовательские пути не записаны в work log. Коммит не создавался.

## 2026-11-20 — Codex — Проверка экспорта Claude для Kindle Cards

- Цель: найти переписку и материалы разработки Kindle Cards в пользовательском экспорте и сопоставить их с текущим кодом.
- Проверены структуры четырёх ZIP. В архиве чатов три записи по два сообщения с пустыми text/content. В памяти есть краткая сводка проекта. В архиве дизайна найдены два проекта с 20 и 6 версиями и исходными HTML-макетами.
- По исходникам подтверждены шесть разделов приложения, локальное расписание повторений в SQLite и экспорт; отдельно в макетах описаны ручной разбор спорных слов, правка карточек и аналитика повторных поисков после экспорта.
- Изменён только WORKLOG.md. Архивы прочитаны без распаковки, прототипы не запускались. Работоспособность приложения в этом обзоре не перепроверялась. Историю обсуждений восстановить по данным этого экспорта не удалось. Коммит не создавался.

## 2026-11-20 — Codex subagent archives — Восстановление материалов Claude Design

- Цель: перенести материалы проекта Kindle Cards из приложенных экспортов Claude и сохранить происхождение файлов.
- В recovery/claude-export сохранены все 138 файлов project/ двух артефактов, карточка памяти о Kindle Cards и одно целевое упоминание из другой заметки. Индекс включает 26 версий, даты, активные версии, размеры и SHA-256; README описывает экраны и ограничения.
- Сверены SHA-256 и размеры с оригинальными манифестами и с записанными файлами. Проверены 14 локальных ссылок из README. В 20 версиях «Библиотеки чтения» 13 разных снимков project/, в 6 версиях Night Reading их 5 с учётом версии без файлов project/. git diff --check для журнала проходит с предупреждением LF/CRLF.
- Из чатов нечего перенести: три записи по два пустых сообщения, связь единственного указателя на файл с Kindle не установлена. Данные аккаунта, общие файлы среды дизайна и шаблонные инструкции не переносились.
- HTML сохранён без изменения байтов и не запускался. Для части макетов экспорт не содержит support.js; автономный просмотр не подтверждён. Код приложения не менялся, коммит не создавался.

## 2026-11-20 — Codex subagent claude_local — Восстановление локальных материалов Claude

- Цель: восстановить историю именно Kindle Cards из локальных проектных папок Claude Code и Claude Desktop. Найдена актуальная копия Anki Cards и три перекрывающихся журнала разработки. Результаты сохранены в recovery/claude-local.
- Извлечены 298 уникальных реплик, 3 сводки, 28 последних текстовых отчётов субагентов, 39 уведомлений о задачах, 8 файлов памяти и 284 исторических текстовых снимка по 133 путям. Индексы связывают записи с исходными строками. Резервные версии хранятся с расширением .snapshot.
- Восстановлены решение от 3 ноября о переносе обучения во внешние приложения, контекст рейтинга v2, дизайн «Кабинет» и состояние подготовки 0.4.0 по журналу. Описания ролей найдены в исходной копии. Исторические команды и указания не запускались.
- Проверены индексы и существование всех снимков. Поиск типовых токенов, закрытых ссылок и полноформатных пользовательских путей в результате без совпадений. Личная база, вложения и сырые логи не переносились. Служебная область MSIX недоступна в песочнице. Функциональные тесты не нужны, код приложения не менялся. Коммит не создавался.


## 2026-11-20 — Codex — История из найденной рабочей копии

Ниже добавлены ранее отсутствовавшие записи из WORKLOG.md исходного проекта. Порядок внутри источника сохранён.

## 2026-10-30 - Claude - Read-only project audit

### Goal

Study the current architecture and state after the SQLite redesign. No source
files were changed.

### Findings

- Library state: 1,158 lexemes (1,142 ready, 16 rejected), empty queue;
  Obsidian destinations: 1,022 synced, 120 missing, 16 not applicable.
- `save_catalog` rewrites every table (`DELETE FROM lexemes` + reinsert) and
  `load_catalog` issues several queries per lexeme; acceptable at ~1k lexemes.
- `vocab_cache._merge_entry` scans the whole catalog per Kindle entry (quadratic
  sync merge).
- `_process_queued_lexemes` re-raises on the first failure; a deterministically
  failing lexeme stays first in the `failed` queue and blocks the rest on retry.
  The frontend also pauses auto-processing while the last operation is `error`.
- Unused bridge helpers remain: `_entry_updates_from_analysis`,
  `missing_kindle_state`, `load_database_state`; `_analysis_by_lemma` is only
  referenced by a test.
- Obsidian lemma normalization (`_normalize_base`) differs slightly from
  `vocab_cache.normalize_lemma`.
- The Rust bridge spawns Python without a no-console-window flag and the binary
  has no `windows_subsystem` attribute; release builds may show console windows.

### Verification

- `python -m unittest discover -s tests`: 21 passed.
- `python -m compileall -q kindle_vocab_app`: passed.
- `npm test`: 8 passed. `npm run build`: passed. `cargo check`: passed.
- Bridge `load_library` ~0.4 s, `connector_status` ~0.5 s (Kindle disconnected).
- Note: `conda run` does not forward stdin; bridge smoke checks must call the
  env's `python.exe` directly.

## 2026-10-30 - Claude - Processing queue no longer stalls on a failed lexeme

### Goal

Fix the audit finding that one deterministically failing lexeme blocked the
whole offline-processing queue.

### Decisions

- A per-lexeme analysis failure is recorded durably as `failed` and the run
  continues; storage errors still propagate.
- The automatic `process_queue` handles only `pending` items. Failed items are
  retried only with `include_failed: true` (Retry in the operation rail or the
  new header button). Explicit `process_lexemes` still includes failed ids.
- Queue order is pending first, then failed, each by `created_at`.
- Auto-processing pauses only after a failed/cancelled processing run, not after
  unrelated operation errors (for example a disconnected Kindle).

### Changes

- `kindle_vocab_app/library_repository.py`: `queued_ids(..., include_failed=)`
  with pending-first ordering.
- `kindle_vocab_app/tauri_bridge.py`: continue after per-lexeme failures, new
  `failed_new` response field, `ошибок: N` in the completion message,
  `include_failed` payload flag.
- `src/features/library/domain.ts`: pure `shouldAutoProcessQueue` policy.
- `src/features/library/use-library-controller.ts`: auto-run via the policy,
  `retryFailed`, partial failures surface as an error operation with Retry.
- `src/features/library/library-workspace.tsx`: header "Ошибки: N" retry button
  when failed lexemes exist and nothing is running.
- `src/lib/backend.ts`: mock respects `include_failed`, reports failed queue
  items, and adds `?scenario=lexeme-failure` for preview QA.
- Tests: replaced the old "stop on first failure" bridge test with continue,
  retry-on-request, and pending-first ordering tests; added Vitest policy tests.

### Verification

- `python -m unittest discover -s tests`: 23 passed.
- `npm test`: 13 passed. `npm run build`: passed.
- Browser QA at 1440x900 with `?scenario=lexeme-failure`: the queue processed
  the remaining lexemes, showed the partial-failure rail and header button,
  did not loop automatically; dismiss + header retry processed the failed
  lexeme; no console errors.

### Remaining Risk

- No Rust changes, so `cargo check` was not re-run. The real Tauri path was not
  exercised end to end; behaviour is covered by bridge tests and the mock.

## 2026-10-30 - Claude - Product direction agreed with the user

### Decisions

- Goal: turn the personal tool into a product another person can install and
  use; possible modest demand.
- First audience: Russian-speaking readers of English books on Kindle.
- Contextual meaning/translation via the user's own API key (OpenAI-compatible
  providers and Anthropic). Offline mode stays honest: no fabricated fields.
- Outputs: Anki (direct deck via AnkiConnect and `.apkg`) and Obsidian with a
  configurable, non-personal format. Built-in spaced repetition (FSRS) is
  deferred to a later phase as a complement to Anki, not a replacement.

### Proposed Phases

1. Card value: contextual LLM enrichment, direct Anki export, generalized
   Obsidian format.
2. Shippable: single installer (Python sidecar), data in the OS app-data
   directory, first-run onboarding, manual `vocab.db` selection.
3. Product: English UI, auto-update, code signing, landing page, optional
   in-app review.

No code changes in this entry.

## 2026-10-30 - Claude - Tooling setup and macOS work integration

### Goal

Prepare for sustained product development and open-source promotion, and
bring the local Windows branch up to date with work pushed from macOS.

### Tooling

- Installed into the `kindle_app` env: `pytest`, `ruff`, `genanki`.
- Installed GitHub CLI; it still needs `gh auth login` by the owner.
- Installed a reviewed subset of MIT-licensed marketing skills
  (coreyhaines31/marketingskills) at user level, not in this repository.
- Offered official Claude Code plugins (feature-dev, pr-review-toolkit,
  code-simplifier, security-guidance, github) via the plugin catalog.

### Integration

- `origin/main` contained `59ac6de` (reading companion UI, review queue,
  covers, macOS MTP) that diverged from the local queue fix. Merged with
  `--no-ff`; resolved `WORKLOG.md` (both sides kept, chronological) and the
  controller (covers + failed-lexeme retry both kept).
- On Windows, `59ac6de` already failed 6 tests: `with sqlite3.connect()` does
  not close the handle, so the Kindle `vocab.db` stayed locked.
  `kindle_db._connect` now closes its connection; tests use `closing()`.
- The macOS-only MTP worker test is skipped on Windows (`fcntl`).
- `tests/conftest.py` ignores temp-dir cleanup errors on Windows, where
  scanners briefly hold new files after assertions pass.

### Verification

- `pytest`: 51 passed, 1 skipped, stable across 4 runs.
- `npm test`: 15 passed. `npm run build`: passed.
- Browser preview (`?scenario=lexeme-failure`): status bar shows the failure
  count with Retry; retry clears it; no console errors.

### Commits

- `7d4a67f` merge, `bf97e78` Windows fixes. Not pushed.

## 2026-10-30 - Claude - Phase 1: Anki decks and contextual AI translation

### Goal

Make the cards worth installing the app for: a real Anki deck and the
Russian meaning of each word in the sense used in the book.

### Live Device Checks (Windows, Kindle over MTP)

- Passive probe detected the Kindle in ~0.7 s. Live sync copied and merged
  the library; 831 new lexemes were queued and processed in 83 s with no
  failures. A repeated sync re-queued nothing.
- Sync took 83 s because online cover lookup ran inside it (77 s). Sync now
  copies only Kindle thumbnails; online lookup runs in the background
  without occupying the operation slot. Sync now takes ~3 s.

### Changes

- `anki_export.py`: `.apkg` export via genanki with a fixed note type
  ("Word in context"), GUIDs derived from lexeme ids (re-import updates
  notes), escaped context with the looked-up form highlighted, offline
  WordNet definition labelled with its source, light/dark card CSS.
  Bridge actions `export_apkg` (new words only by default) and `open_path`
  (restricted to the app export folder).
- `llm/`: provider presets (Anthropic, OpenAI, DeepSeek, OpenRouter,
  LM Studio, Ollama, custom), API keys in the OS keychain via `keyring`
  (env override `KINDLE_CARDS_LLM_API_KEY` for development), an
  OpenAI-compatible client with JSON-schema → json_object → plain fallback,
  and a separate Anthropic SDK client (`claude-opus-5-5` default, low effort,
  structured output, server-side refusal fallback).
- `enrichment.py`: batches with short item numbers, per-batch persistence,
  fatal errors stop the run, timeouts leave words queued, three failed
  batches in a row stop the run. Local presets use batches of 2, a 600 s
  timeout and no SDK retries.
- SQLite schema v3: `enrichments` keyed by `(language, canonical_key)` so
  results survive full catalog replacement; exposed as `lexeme.enrichment`.
- Settings: `llm_provider`, `llm_auto_enrich`; old settings with a custom
  endpoint migrate to the `custom` preset.
- UI: "Перевод через ИИ" settings (provider, key, model list, connection test
  with a built-in sample word), "Перевести N" and "В Anki N" actions, an
  "Открыть в Anki" notice, translation details in the word inspector, and
  completion messages in the status bar.

### Verification

- `pytest`: 67 passed, 1 skipped. `npm test`: 18 passed. `npm run build`: passed.
- Real-library copy: 1,940 cards exported in 3.8 s; WordNet definitions for
  1,921; the looked-up form highlighted in 1,939 contexts.
- Local LM Studio model (9B): 8-word batches timed out; 2-word batches
  translated 6 real words in 71 s with good quality. The prompt now asks
  for dictionary forms (the model returned "казались" for "seem").
- Browser preview: provider selection, key save/replace, connection test
  success and error, translate, export and the open-in-Anki notice work;
  no console errors or horizontal overflow. Screenshots were unavailable
  because the app window was not drawn; checks used the DOM.

### Remaining Risk

- No cloud provider was exercised live (no key on this machine).
- The full Tauri WebView flow and opening `.apkg` in a real Anki were not run.
- The `kindle_app` conda env has an editable install pointing at another
  checkout; scripts run outside the repo import that older package.
- Offline lemmatization still produces some wrong lemmas (e.g. "felt").

## 2026-10-30 - Claude - AnkiConnect delivery and Windows installer

### Goal

Send cards straight into a running Anki and make the app installable without
Python, conda or the repository.

### Decisions

- AnkiConnect delivers the same `.apkg` through `importPackage` instead of
  `addNotes`, so a note keeps one GUID whether it arrived by file or directly,
  and re-sending updates notes instead of duplicating them.
- A card is re-sent when its enrichment is newer than its last Anki export.
- Words are marked exported only after the file exists and, when pushing,
  after Anki confirmed the import.
- Installer: PyInstaller one-folder bridge (fast start for per-action
  processes) shipped as Tauri resources via a separate
  `tauri.bundle.conf.json`, so development builds do not need it. Installed
  builds store data in the per-user app data directory; development keeps the
  repository `.app-data`. Release builds are GUI-subsystem apps and spawn the
  bridge with `CREATE_NO_WINDOW`.

### Changes

- `anki_connect.py`, bridge `push_anki`, AnkiConnect state in
  `connector_status`, `needs_anki_update`; UI sends directly when Anki is
  reachable and otherwise builds the file with an "open in Anki" notice.
- `packaging/bridge_entry.py`, `packaging/build_bridge.py`,
  `scripts/build-installer.ps1`, Rust bridge resolution, README section.
- `.github/workflows/ci.yml` (tests, build, cargo check) and `release.yml`
  (installer on tags or manual runs, attached to a draft release).

### Findings

- PyInstaller's NLTK runtime hook imports nltk before the entry script, so
  `NLTK_DATA` set there was ignored. The build machine masked it with the
  user's own `%APPDATA%\nltk_data`; a clean machine would have run without
  WordNet. The entry now prepends the bundled path, and the smoke test runs
  with an empty `APPDATA`.
- The first bridge build was 225 MB: duplicated NLTK data from the build
  machine, wordfreq data for ~40 languages and Tcl/Tk. Now 66 MB; only English
  frequencies, WordNet and the POS tagger are shipped (`omw-1.4` and
  `punkt_tab` are unused by the code).

### Verification

- `pytest`: 71 passed, 1 skipped. `npm test`: 19 passed. `npm run build` and
  `cargo check`: passed.
- AnkiConnect covered by a local fake add-on server (status, import, failed
  import keeps words pending). Not exercised against the real Anki: the
  add-on is not installed and importing would change the user's collection.
- Frozen bridge smoke test: analyses of the demo words are identical to the
  development Python with an empty `APPDATA`; it detected the real Kindle over
  MTP; ~0.85 s per call.
- The local NSIS build is blocked: Kaspersky (`avp.exe`) denies executing the
  freshly compiled release build scripts (`os error 5/32`, also with another
  target directory). Security settings were not changed. The GitHub release
  workflow builds on a clean runner instead; it has not run yet (not pushed).

## 2026-10-30 - Claude - First CI-built installer verified

### Results

- Pushed `main` (16 commits) with the owner's permission. CI passed on the
  first run on `windows-latest` (lint, 71 Python tests, Vitest, build,
  cargo check).
- `release.yml` (manual dispatch) built `Kindle Cards_0.1.0_x64-setup.exe`
  (41 MB) in 8 minutes, sidestepping the local Kaspersky block.
- Silent per-user install (`/S`) succeeded into `%LOCALAPPDATA%\Kindle Cards`
  with the bundled bridge. The installed app ran the full real flow on the
  bundled bridge (`kindle-bridge.exe`, no system Python): connector probe,
  automatic Kindle sync in 6 s, background covers, automatic offline
  processing of 1,781 lexemes with zero failures.

### Notes

- Processes started from the Claude desktop app (an MSIX package) have their
  `%APPDATA%` writes virtualized into the package's `LocalCache`. The test
  run's library therefore lives there; launching the app normally uses the
  real `%APPDATA%\com.kindlevocab.cards`.
- GitHub annotates the Node 20 based actions as deprecated; they already run
  on Node 24. Bump action majors when convenient.
- The installer is unsigned; Windows SmartScreen will warn on first run.

## 2026-10-30 - Claude - README and first public release v0.1.0

### Decisions (owner)

- License: MIT (copyright holder "Gwyndolin", matching the git identity).
- Repository renamed `kindle_app` → `kindle-anki-cards` (GitHub keeps a
  redirect; the local remote was updated; the Mac checkout can keep working
  through the redirect or run `git remote set-url`).
- Personal traces already in the public history (a real book title in tests
  and demo data, commit e-mail, a Mac host name in one commit, library counts
  in this log) were reviewed with the owner and intentionally left as is.

### Changes

- New user-facing `README.md` (Russian with an English summary, badges,
  screenshots, install, usage, AI providers, privacy, limitations); the former
  README moved to `docs/DEVELOPMENT.md`.
- Screenshots in `docs/screenshots/` captured with headless Chrome from the
  browser preview (`?scenario=showcase&view=...`, demo data only) plus an
  Anki card rendered by `packaging/render_card_preview.py`.
- UI fixes found on the screenshots: part of speech shown as a raw WordNet
  code ("n", "v"); settings labels rendered inline with selects; the Obsidian
  column label wrapped. Removed the "language" and "app data folder" settings,
  which had no effect anywhere.
- Repository description and topics set for discovery.
- Tag `v0.1.0` → `release.yml` built the installer and attached it to a draft
  release, which was then published with release notes as the latest release.

### Verification

- `npm test`: 19 passed; `npm run build`: passed.
- The release asset downloads anonymously (42.6 MB); the release badge,
  README screenshots and MIT license detection work on GitHub.
- The published installer comes from a newer commit than the one installed
  and exercised locally earlier; the bridge smoke test (identical analyses to
  development Python on an empty APPDATA) ran in its CI build.

## 2026-10-30 - Claude - Night Reading design: foundation and canvas concepts

### Goal

Give the app one visual world ("Night reading") before new features land,
and reach a higher design level than the generic dashboard look.

### Decisions (owner)

- World: a room at night, the UI drawn in soft pencil, one warm lamp colour,
  light and dark themes; transitions through switching the light.
- Light must be functional: it lands on what matters now, unused areas stay in
  shadow. The interface is a modern minimal layout stylised as pencil, not a
  crooked drawing.
- After two code iterations the owner asked for a higher bar; the next step
  is concept exploration on a private Claude Design canvas, then the chosen
  direction is implemented in code.

### Changes

- `e615a54`, `c654f0f` (local, not pushed): `DESIGN.md`, Night Reading tokens
  and pencil kit (`src/design/night-reading.css`), roughjs sketch primitives,
  light scene with exact beam geometry (`src/components/light/`), sidebar
  sconce, home screen lamps, light-switch transition, Literata and Caveat
  (OFL) fonts.
- Private Design canvas with three home-screen directions, each with a
  working day/night switch and tweaks that turn lamps on and off:
  1. "Кабинет": one architect lamp lights the latest book and its actions,
     a clip lamp lights the review card only when cards are due.
  2. "Читальный зал": four pendant lamps over Kindle, new words, review and
     Anki; a lamp is lit only when its desk has something to do.
  3. "Разворот": the home screen is an open book under a clip-on book light;
     the running head is the navigation, the light falls on the top halves.
- Local previews of the concepts are in the ignored `build/concept/`.

### Findings

- In the concepts, a lamp-off rule lost to the warm-up animation rule on
  specificity, and inline fills beat class rules; both fixed. The same trap
  applies when porting the chosen concept to `night-reading.css`.

### Remaining

- Owner picks a direction (or a mix); then port it to all screens, decide
  whether WebGL light is still needed, run the CI commands and push the design
  commits.

## 2026-10-30 - Claude - "Кабинет" direction in the app shell and home

### Decision (owner)

- Of the three canvas concepts the owner chose "Кабинет" as the base, plus
  the reading-room rule (a lamp burns only where there is something to do)
  and the open-book typography (dictionary entries, dot-leader ledgers).

### Changes

- `src/components/light/lamps.tsx`: `DeskLamp`, `ClipLamp`, `Sconce` replace
  the measured `LightScene`/`Lit` system (`scene.tsx`, `geometry.ts`,
  `lamps.ts` removed). Each lamp is anchored to a corner of its host and its
  beam is a CSS clip-path cone from the same corner, so no measuring or
  ResizeObserver is needed; `--lamp-s` scales the desk lamp and its beam
  together by container width.
- `src/components/sketch/sketch.tsx`: inline `PencilRule`, `PencilFrame`,
  `CornerCurl`, `#pencil-graphite` filter; `roughjs` dependency removed.
- Shell (`src/main.tsx`): brand lamp, the sconce rides the nav wall to the
  active item, library count, a wall light switch for day/night.
- Home (`reading-home.tsx`): greeting by time of day, search that opens the
  word list, Kindle state; the latest book under the desk lamp (lit when
  there are new words or Kindle is connected); recent words as dictionary
  entries; review card with a clip lamp lit only when cards are due; library
  shelf with a dot-leader ledger and "send to Anki".
- `reading-domain.ts`: `greeting`, `reviewMinutes`, `partOfSpeechShort` with
  tests. `DESIGN.md` updated with the lamp rule and the new primitives.

### Verification

- ruff (CI paths), `pytest` 71 passed / 1 skipped, `npm test` 22 passed,
  `npm run build` passed.
- Screenshots of the showcase data at 1120, 1320 and 1600 px in both themes;
  the wall switch flips the theme through the curtain in the browser preview.

### Remaining

- Books, Words, Review, Insights and Settings still use the previous styles
  (bright placeholder covers, coloured connector chips); port them next.
- Not tried in the packaged Tauri window yet; design commits are not pushed.

## 2026-11-02 - Claude - "Кабинет" on every screen

### Goal

Port Books, Words, Review, Insights and Settings to the "Кабинет" world so the
whole app reads as one room.

### Changes

- UI primitives restyled once for all screens: `Button` (lit `default`,
  pencil-framed `secondary`/`destructive`, `ghost`), `Input` and `Select` on a
  pencil line that warms on focus, `Switch` with a bulb knob, `Badge` as a
  handwritten note. Unused `card.tsx` and `progress.tsx` removed, along with
  `@radix-ui/react-progress`.
- Shared pieces: `PageHead` (`src/components/page-head.tsx`), `BookJacket`
  (`src/features/reading/book-jacket.tsx`, drawn jacket or real cover; replaces
  the bright placeholder covers), dictionary-entry list classes.
- Books: shelf with small jackets and a lit selection; the chosen book on the
  desk under a desk lamp; its words as dictionary entries.
- Words: no purple/blue connector colours; pencil filters, lit selected row,
  the chosen word as an index card under a clip lamp, dot-leader analysis.
- Review: the index card on the desk under a desk lamp that goes out when the
  session is done; Space reveals, 1/2/3 rate.
- Insights: figures with pencil separators, chart with amber new-word bars
  and hatched lookup bars, bibliography with dot leaders.
- Settings: sections with a description column, no icon-in-a-square cards,
  switch rows.
- `DESIGN.md` components section updated (one lamp per screen, primitives).

### Verification

- ruff (CI paths), `pytest` 71 passed / 1 skipped, `npm test` 22 passed,
  `npm run build` passed.
- Screenshots of every screen with showcase data at 1320 px (night and day)
  and the 1120 px minimum window; keyboard review (Space, 3) exercised in the
  browser preview.

### Notes

- The Vite dev server once missed a CSS change written by a shell append and
  served stale styles; touching the file fixed it. Not an app issue.
- Not tried in the packaged Tauri window yet; design commits are not pushed.

## 2026-11-02 - Claude - Audience research and offline Russian meanings

### Research (for the audience plan)

- Kindle -> Anki tools today are mostly scripts (wzyboy/kindle_vocab_anki,
  NdYAG/Kindle2Anki, r0usta/kindle-to-anki), a Chrome extension and
  Fluentcards; none is a polished desktop app with Russian translations.
- In Russia PocketBook holds most of the e-reader market and Kindle is not sold
  officially; PocketBook has no exportable lookup history, but KOReader (runs
  on PocketBook, Kobo, Boox, jailbroken Kindle) keeps a vocabulary-builder
  SQLite and Kobo keeps a WordList table. Only scripts exist for them.
- First-run barrier found: without an AI key cards had no Russian meaning at
  all (only an English WordNet definition).

### Changes

- `packaging/build_dictionary.py` builds `kindle_vocab_app/data/en_ru_wiktionary.sqlite`
  (5.0 MB, 57,380 English words and phrases with short Russian meanings) from
  the Russian Wiktionary extract on kaikki.org; data is CC BY-SA 4.0 with
  attribution in `kindle_vocab_app/data/README.md`, README and the UI.
- `kindle_vocab_app/offline_dictionary.py`: lookup by lemma and part of speech;
  meanings are attached when the library, review cards and Anki notes are
  built, never stored, so already processed words get them without
  reprocessing. A ready LLM translation always wins.
- Anki: Meaning falls back to the dictionary; cards exported before
  2026-11-02 without a translation are re-exported once (same GUIDs, notes are
  updated). Frontend mirrors the rule (`needsAnkiUpdate`, `russianMeaning`).
- UI: meaning in home, word card (marked "значения по Викисловарю") and the
  review answer; settings copy explains the dictionary vs AI.
- `AGENTS.md`, README, `pyproject.toml` package data and the CI ruff list
  updated.

### Verification

- Coverage on the two local libraries: about 84% of analysed words; through
  the real bridge 85% of library lexemes and 16 of 20 review cards got
  meanings.
- ruff (CI paths + new module), `pytest` 81 passed / 1 skipped, `npm test`
  24 passed, `npm run build` passed; word card checked in the browser preview.

### Remaining

- Obsidian cards still use only LLM translations.
- The other ~16%: rare words and lemmatisation misses; English Wiktionary
  translation tables could fill part of it.

## 2026-11-02 - Claude - Release 0.2.0

- Owner approved releasing the design and the offline dictionary.
- Version 0.2.0 in `package.json`, `package-lock.json`, `src-tauri/tauri.conf.json`,
  `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock`, `pyproject.toml`.
- README screenshots (`docs/screenshots/home|words|books|settings.png`)
  recaptured from the browser preview with showcase demo data only.
- Tag `v0.2.0` -> `release.yml` builds the installer into a draft release,
  which is published with release notes once the build passes.
- Published: CI and `release.yml` passed for `v0.2.0`; the release
  "Kindle Cards 0.2.0" is the latest release and
  `Kindle.Cards_0.2.0_x64-setup.exe` (44.8 MB) downloads anonymously.

## 2026-11-02 - Claude - KOReader, Kobo and file import

### Goal

Reach readers beyond Kindle (PocketBook dominates the Russian market) and give
a path that does not depend on USB detection.

### Changes

- `kindle_vocab_app/reader_sources.py`: KOReader `vocabulary_builder.sqlite3`
  (current schema with `title`, old schema with `book_title`; the sentence is
  cut from `prev_context`/`next_context`), Kobo `WordList` joined to `content`
  (no context sentence exists there), format detection by tables, discovery on
  mounted volumes (`applications/koreader` on PocketBook, `.adds/koreader` on
  Kobo, `koreader/` at the root, `.kobo/KoboReader.sqlite`), and caching that
  copies and checkpoints KOReader's WAL journal so fresh lookups are not lost.
- Bridge: `sync_kindle` merges Kindle and every reader found in one sync;
  `connector_status` reports a KOReader/Kobo reader as connected with its own
  label and a file-based signature, so auto-sync works for it; new
  `import_reader_file` action merges a picked file (base64), refuses non-word
  databases with a clear message, and re-imports without duplicates.
- UI: "Импорт файла" in Words, an inline file link on Home when no reader is
  connected and in the first-run state with the file paths for each reader;
  copy speaks of "читалка" and shows the reader's name instead of "Kindle".
- README, `AGENTS.md`, CI ruff list updated; lamp text reserve widened so a
  long title never touches the shade at 1320 px.

### Verification

- New tests: synthetic KOReader (both schemas, WAL), Kobo, detection,
  discovery, sentence cutting; bridge sync of a PocketBook volume without a
  Kindle, file import and refusal. `pytest` 91 passed / 1 skipped, `npm test`
  25 passed, build passed; the import path exercised in the browser preview.

### Remaining risks

- Not tried on a real PocketBook, Kobo or Boox; schemas follow KOReader's
  `db.lua` and community notes on Kobo's `WordList`.
- Android/Boox over MTP is not scanned automatically; the file import covers it.

## 2026-11-02 - Claude - Release 0.3.0

- Owner approved releasing KOReader/Kobo support and the file import, marked
  beta for PocketBook/Kobo/Boox because no real device was tried.
- Version 0.3.0 in `package.json`, `package-lock.json`, `src-tauri/tauri.conf.json`,
  `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock`, `pyproject.toml`.
- Tag `v0.3.0` -> `release.yml` builds the installer into a draft release,
  published with release notes once the build passes.
- Published: CI and `release.yml` passed for `v0.3.0`; "Kindle Cards 0.3.0" is
  the latest release and `Kindle.Cards_0.3.0_x64-setup.exe` (44.8 MB)
  downloads anonymously.

## 2026-11-03 - Claude - Concept: reading library with word ranking

- Owner's direction: the core is ranking words by how worth learning they
  are; reading-progress "snapshots" give a reason to come back.
- Finding: Kindle `LOOKUPS.pos` ends in a numeric offset (`<id>:<offset>`)
  that advances with time inside a book in local data, so every lookup is a
  dated point in the book. Reading history and a per-book curve of unknown
  words can be built retroactively from `vocab.db` alone; book length (for a
  percentage) is not in `vocab.db`.
- Proposed (not approved, nothing implemented):
  - Ranking v2: frequency shown as "about once in N pages" (Zipf z ->
    10^(9-z) words), personal signals dominate (repeat lookups, several
    books, gap below the reader's usual level), explicit triage
    know/learn/skip, shelves "learn now / queue / context is enough / hidden",
    one-line reason per word. Stays deterministic.
  - Reading diary: every sync is a snapshot; "since last time" page, per-book
    timeline and unknown-word curve, level trend from the frequency of words
    looked up. KOReader/Kobo progress fields and Kindle `.sdr` sidecars still
    need checking on real devices.
- No code changed.

## 2026-11-03 - Claude (design reviewer subagent) - Review of library concept canvas

- Reviewed the concept canvas artboards (Main, Words, Triage, Book, plus the
  Level file that was dropped from `canvas.json` mid-review) against
  `DESIGN.md`, `src/components/light/lamps.tsx` and the light section of
  `src/design/night-reading.css`, by source only (no rendering).
- Light geometry: desk, clip and sconce ports match production coordinates;
  the pendant over the triage card is aligned. Main's text reserve is narrower
  than production (330 vs 366 x `--lamp-s`) and the jacket sits above the
  cone; Book's banker's lamp lights the empty end of the progress row, not the
  book; the Level floor lamp's cone misses the chart.
- Other findings: inline `--lamp-s` custom property is a rendering risk, the
  27 "new" words also appear on regular shelves (double count), a triage word
  comes from a book not in the sync, nav badge shows 0 when done, masculine
  status labels, flat 1px rules and glowing tab bars instead of pencil marks,
  uppercase eyebrows, missing pressed/disabled states.
- No canvas or project files changed; only this entry was appended.

## 2026-11-03 - Claude - Library concept canvas, critical pass, reviewer agents

- Goal: draw the "reading library + word ranking" concept as screens in the
  Кабинет language, then cut everything that is not functional (owner: no
  "нейрослоп", no statistics dashboards).
- Private Design canvas with four linked screens (scratch files, not in the
  repo): Главная (since last time → «Разобрать», current book, «Учить сейчас»),
  Слова (shelves Новые / Учить сейчас / Очередь / Хватит контекста / Знаю /
  Не слова, one reason per word, word card with pros/cons and decisions),
  Разбор (one word at a time with the ranking's advice), Книга (status,
  progress line, this book's words). Fixtures per page: sconce in the nav,
  desk lamp, clip lamp, pendant over the triage card, banker's lamp.
- Cut in the critical pass: the «Уровень» statistics screen, reading-days
  calendar, unknown-words chart, counters, tally table, signal-strength bars,
  the separate «Разбор» nav item. Navigation is now Главная, Слова,
  Повторение, Книги, Настройки.
- Proposed rule shown on the canvas, awaiting the owner: a user's «Учить»
  puts the word into «Учить сейчас» at once (their decision beats the
  ranking); «Не учить» replaces «Пропустить» and sends the word to «Хватит
  контекста».
- Reviews: a design-language review (light geometry, pencil lines, italic
  eyebrows, states, data double-counting) and a UX clarity review (one name
  per concept, one reason vocabulary, empty/done states, book screen no
  longer duplicates Слова) were applied to all four screens.
- Owner asked for two standing reviewer subagents: added
  `.claude/agents/ux-clarity-reviewer.md` and
  `.claude/agents/design-language-reviewer.md` (read-only briefs) and an
  AGENTS.md section "Design and UX Reviewers"; the Work Log rule now says the
  parent records read-only reviewers' findings.
- Open: no books-list screen yet («Книги» opens one book); where learning
  happens (in-app Повторение vs export) is undecided; reading percentage for
  Kindle still needs the `.sdr` check on a device. Nothing committed.

## 2026-11-03 - Claude - Scope change: ranking + edit + export + progress; ranking baseline

- Owner decision: no learning or review inside the app. Cards are learned in
  another app; Kindle Cards ranks looked-up words (a statistics/ML problem:
  smart ranking, junk filtering), lets the user browse and edit them
  (translation, example on the card), exports, and tracks progress — mainly
  whether an exported word stuck (looked up again in a book after export =
  it did not) and lookups per 10 pages across books.
- Ranking baseline on local Kindle lookups (aggregates only, scratch script,
  not in the repo): temporal split at 2026-09-01, label = the stem was looked
  up again after the cutoff (13% of 1,422 earlier stems). Corpus frequency
  alone: AUC 0.57, precision@100 0.10 (below the base rate at the top);
  personal lookup count P@100 0.30; recency AUC 0.62; a pure-Python logistic
  regression on cheap features: AUC 0.66, P@100 0.31. Only ~2% of Kindle
  stems look like proper nouns (capitalised mid-sentence); KOReader/Kobo will
  bring more junk. Caveat: words learned via the owner's Obsidian cards
  suppress the "looked up again" label.
- Canvas reworked (private Design artifact): Главная (27 new already shelved
  → «Экспортировать 15 новых», check 5 disputed, current book, «Держатся ли
  слова»), Слова (Спорные / Стоит учить / Не стоит учить / Знаю / Не слова;
  editable translation, choice of example, export state), Спорные (one by
  one; answers teach the ranking), Экспорт (Anki/Quizlet/CSV/Obsidian;
  not-yet-exported or again; loading, done, empty and error states),
  Прогресс (looked up again after export + re-export; lookups per 10 pages
  per book; empty state), Книга (status, progress, its words). Navigation:
  Главная, Слова, Прогресс, Настройки.
- Both reviewer subagents ran on the result; applied: one verb «экспорт»,
  shelf «Не стоит учить», consistent demo numbers, floor lamp moved over the
  list it lights, pencil bars instead of filtered thick strokes, lamp kept
  but put out after export, base button sizes unified. Rejected: "style holes
  do not apply" (the canvas format supports them).
- Open: the ML plan itself (features, model, active learning, evaluation) is
  proposed to the owner, nothing implemented; no books-list screen (books are
  listed in Прогресс). Nothing committed.

## 2026-11-09 - Claude - Ranking evaluation harness

- Goal: before changing the ranking, measure it. New
  `kindle_vocab_app/ranking_eval.py` (`python -m kindle_vocab_app.ranking_eval`):
  at monthly cutoffs it builds features only from earlier lookups, labels a
  word "needed again" when it is looked up again within the next 42 days,
  and reports AUC and precision@50/100 with bootstrap intervals for the
  current importance score (recomputed with the earlier lookup count only),
  frequency, lookups, recency, and a small pure-Python logistic regression
  trained one window earlier (labels fully before the cutoff). Rejected words
  are excluded as the app never ranks them. Reports (aggregates only) and run
  logs go to `.app-data/ranking_eval/`.
- First result on the local library (2 comparable cutoffs, Aug and Sep 2026):
  current score AUC 0.56, top-50 lift 1.0 (no better than random at the top);
  frequency alone 0.55, lift 0.5; lookups 0.58, lift 2.3; recency 0.63,
  lift 2.3; learned 0.64, lift 2.5 (Sep: 0.68, interval 0.64-0.72, vs current
  0.56, 0.52-0.61).
- Code review subagent (pr-review-toolkit:code-reviewer) confirmed no leakage
  and correct metrics; fixed what it found: the recomputed score lacked the
  specialised-domain penalty (now matches the stored score for all ready
  words), rejected analyses lost their features, missing tests for leakage of
  the learned ranker, the summary and lift, CLI logging, `--top 0`, NaN in
  JSON.
- Changed: `kindle_vocab_app/ranking_eval.py`, `tests/test_ranking_eval.py`
  (21 tests), `.github/workflows/ci.yml` (ruff list), `AGENTS.md` (architecture
  map, useful checks; ranking changes must be measured before and after).
- Checks: CI ruff list clean, full pytest 112 passed / 1 skipped.
- Risks: only two comparable cutoffs so far; labels are noisy because words
  learned through the owner's Obsidian cards stop being looked up. Nothing
  committed yet.
- Committed as b9a404d (not pushed); `.claude/launch.json` stays local.

## 2026-11-13 - Claude (lead) - Team, product document, first lanes

- Owner's mandate: build a team and make a product people actually use; the
  team is responsible for design, interface, functionality and engagement.
- Added `PRODUCT.md` (goal, audience, promise, what the product does and does
  not do, the loop, milestones M1-M4 with done criteria, open questions for
  the owner).
- Concept screens saved from the private Design canvas into `docs/concept/`
  (six `.dc.html` artboards + `canvas.json`) so they are a durable
  specification; the scratch copies were gone.
- Team briefs in `.claude/agents/`: `ranking-engineer`, `backend-engineer`,
  `frontend-engineer`, `qa-engineer`, `user-advocate` (plus the two existing
  reviewers). `AGENTS.md` got a "Team" section: roles and ownership, lanes do
  not share files, contracts go through the lead, only the lead commits (as
  the owner), push/releases/anything public need the owner.
- Started three lanes: an architecture blueprint for M1-M2 (read-only), ranking
  v2 as a standalone module measured with `ranking_eval` (ranking-engineer),
  and a first-five-minutes walkthrough (user-advocate, report only).

## 2026-11-19 - Claude (lead) - Token budget, product skeptic, trimmed plan, README

- Owner: rerun the agents cheaply; Opus 5.5 high is the ceiling and only for
  the hardest lane. Token-budget rule added to AGENTS.md "Team"; agents now
  get an explicit model/effort (ranking: Opus high; architect, user-advocate:
  Sonnet medium; skeptic: Opus medium).
- Owner asked for a role whose only job is common sense — is it *needed* by
  real people. Added `.claude/agents/product-skeptic.md` and the rule "need
  before build" in AGENTS.md.
- Newcomer walkthrough (user-advocate): biggest losses are SmartScreen on the
  unsigned installer, a README written for programmers that still promised
  review/analytics, the no-cable path hidden in a tooltip; comparable free
  tools exist but none choose what is worth learning or track what stuck.
- Skeptic verdicts applied to PRODUCT.md: two screens (Главная, Слова) +
  Настройки; Progress/Book screens, manual book status, lookups per 10 pages,
  month cohorts, five equal shelves, Quizlet branch, per-export questions cut
  or deferred; short list of 15–30 words; one-button export to a remembered
  destination; re-export updates the same Anki note with «повтор»; «снова
  искали после экспорта» on Главная; M3a (newcomer fixes) moved before M2.
- Architect blueprint trimmed into `docs/plan/m1-m2.md` (live ranking, user
  tables keyed by lexeme_id without FK, append-only export history, single
  eligibility and card resolver, freshness fix, schema v4, bridge contract,
  lanes). Ranking lane told about `lean`, `REASON_CODES`, `RANKING_VERSION`.
- README rewritten for readers by user-advocate; technical lists moved to
  `docs/TECHNICAL.md`. Lead fixed the KOReader paths per device (checked
  against `reader_sources.KOREADER_PATHS`) and a claim untrue for 0.3.0
  (it still has built-in review). Step 3 wording must be updated when M2
  changes the export button.
- Open for the owner: lookups-per-10-pages progress (deferred by the skeptic,
  was the owner's wish); installer signing (SignPath, unverified).

## 2026-11-19 - Claude (ranking-engineer) - Ranking v2 as a standalone, measured module (M1)

- Goal: replace the importance score with a personal, explainable ranking
  that beats it at the top on `ranking_eval`, as a module other lanes can
  call (`rank(facts, now, weights) -> Ranking`).
- Built `kindle_vocab_app/ranking.py`: `WordFacts`, `Reason`, `Ranking`
  (+ `lean` for disputed words), `Weights`, `DEFAULT_WEIGHTS`, `rank`,
  `RANKING_VERSION = "r2"`, `REASON_CODES`. Logistic score over named
  contributions: repeat lookups (log2, capped at 8), several books (log2),
  recency (2^(-days/21) centred at 0.25, so old lookups count against),
  book being read, looked up again after export, frequency band (penalty
  below Zipf 3.0 and above 5.0, flat between), junk evidence (non_word,
  non_english/unsupported_language, unknown to lexicons, glued words, proper
  noun). Decision always wins (learn -> worth with score 1.0, skip ->
  not_worth, junk -> junk, known -> known) and comes first in reasons.
  Junk evidence >= 3 -> junk shelf; weaker -> disputed with lean "junk";
  score in [0.19, 0.22) -> disputed with lean learn/skip; >= 0.22 worth.
  Reasons are plain Russian with correct plurals (искали 3 раза / дважды,
  в двух ваших книгах, читаете сейчас, снова искали после экспорта,
  встречается раз в ~N книг / страниц, частое, частое — видимо, в редком
  значении, нет в словарях, похоже на имя, давно не искали), strongest
  first; every score is sigmoid(bias + sum of reason weights). Where
  `proper_noun` comes from is documented next to `WordFacts`.
- `ranking_eval.py`: examples carry `history` (pre-cutoff (time, book)),
  `reading_books` (books with any lookup in the 14 days before the cutoff)
  and `cutoff`; new `ranking_v2` ranker with DEFAULT_WEIGHTS (nothing fitted
  per cutoff; no exports or decisions in the history); per-cutoff table with
  intervals in the printed report. Existing rankers and tests kept.
- Weights: chosen as rounded log-odds differences of each signal across all
  four cutoffs, not fitted. One change after measuring: books 0.5 -> 0.25
  (univariate AUC of "several books" is 0.50-0.54 and it repeats what repeat
  lookups say; lowering it helped top-50 in 3 of 3 informative rounds).
  Sensitivity: each weight x0.5 / x1.5 moves mean AUC by <= 0.01 except the
  frequency band edges; top-50 lift moves 1.8-2.5 (it is noisy: 50 words).
- Numbers (mean of the 2 rounds where `learned` runs, Aug+Sep 2026):
  current_score AUC 0.559, lift@50 1.0; learned 0.637, 2.5; ranking_v2
  0.654, 2.8 (P@50 0.32, P@100 0.29). Per cutoff v2 vs current, AUC
  [interval]: Jun 0.532 [0.40-0.66] vs 0.472 (138 words, lift 0.9 vs 0.9);
  Jul 0.661 [0.61-0.71] vs 0.590 (lift 1.9 vs 1.1); Aug 0.635 [0.60-0.68]
  vs 0.555 [0.50-0.60] (lift 2.0 vs 0.9); Sep 0.672 [0.63-0.72] vs 0.564
  [0.53-0.60] (lift 3.5 vs 1.0). Mean over all 4: AUC 0.625 vs 0.545,
  lift@50 2.08 vs 0.98. With books 0.5 the 2-round lift was 2.3.
- Shelves on the real library (counts only, 1961 lexemes, rejected
  included): now = today: worth 272, disputed 71 (3.6%), not_worth 1615,
  junk 3; now = last lookup: 421 / 98 (5.0%) / 1439 / 3. ~15 us per word.
- Tests: `tests/test_ranking.py` (new, 36 tests: decisions, signal
  directions, shelves and lean, junk, reason order, Russian plurals,
  codes/version, determinism, edge inputs); `tests/test_ranking_eval.py`
  (history, reading books, v2 ranker, a synthetic second reader on which
  v2 beats the current score). CI ruff list + `ranking.py`: clean. Full
  pytest: 152 passed, 1 skipped.
- Changed: `kindle_vocab_app/ranking.py` (new), `kindle_vocab_app/ranking_eval.py`,
  `tests/test_ranking.py` (new), `tests/test_ranking_eval.py`,
  `.github/workflows/ci.yml`.
- Risks: recency makes the worth shelf shrink when the reader pauses
  (worth 31.6% at the Sep cutoff, 13.9% today); the bridge could pass
  `now` = the last lookup to measure time in reading. Only 2-4 cutoffs from
  one reader; the "after export" weight is unmeasured (no export history),
  as is `proper_noun` (not stored). `too_basic` words are not treated
  specially. Labels are suppressed by words learned through Obsidian.
  Nothing committed.

## 2026-11-19 - ranking v2: code-review fixes (ranking-engineer)

- Goal: close six review findings on `ranking.py` / `ranking_eval.py`.
- Decisions: a reader's decision is a reason with weight 0.0 and fixes only
  the shelf; `score` is always sigmoid(bias + sum of reason weights) (the old
  +-10 weights and score 1.0 for "learn" are gone, callers sort by shelf
  first). `WordFacts.decided_at` added: a "known" word looked up after it
  returns to the model with reason `known_again` ("снова искали после
  «знаю»", weight = after_export, or 0 if after_export already counted);
  other decisions are never lifted. `Weights` refuses `repeat_cap < 1`.
  `frequency_common` is emitted only when its weight <= -0.1, otherwise a
  plain "частое" (`frequency`, weight 0). "в 21 вашей книге" plural fixed.
  `format_report` now says ranking_v2 is in-sample; `SecondReaderTests`
  renamed `SyntheticReaderTests` with a comment that it is no
  generalisation claim.
- Numbers: unchanged (weights and eval inputs untouched): ranking_v2 mean AUC
  0.653 (2 rounds), P@50 0.32, lift 2.8; current_score 0.559 / 1.0.
- Tests: reading_books leakage (post-cutoff-only book, 14d+1s book excluded,
  exactly cutoff-14d included), decision decomposition, known lapse,
  plurals 11/21/22/25, common-frequency emission, repeat_cap guard. CI ruff
  list clean, full pytest 157 passed, 1 skipped.
- Files: `kindle_vocab_app/ranking.py`, `kindle_vocab_app/ranking_eval.py`,
  `tests/test_ranking.py`, `tests/test_ranking_eval.py`.
- Risks: new reason code `known_again` and `decided_at` are a contract
  addition for the bridge; consumers must not assume score 1.0 for "learn".
  Nothing committed.
- Committed as fb8f1b6 (not pushed): ranking v2, PRODUCT.md, plan, concept, README, team briefs.

- Pushed b9a404d and fb8f1b6 to origin/main after ruff, pytest (157 passed, 1 skipped), npm test and npm run build passed.

## 2026-11-19 — Lead: team meeting after M1

- Goal: the owner asked that the team meets after every stage and plans the
  next stage and the app's direction. Rule added to the "Team" section of
  `AGENTS.md`.
- Meeting: six read-only views (product-skeptic opus/medium; ranking,
  backend, frontend sonnet/medium; user-advocate sonnet/low; qa haiku/medium).
  Outcome recorded in `docs/plan/meetings.md`; `docs/plan/m1-m2.md` points to
  it from "Lanes and order".
- Decisions: M1 not closed until a non-author (synthetic newcomer) library
  passes; ranking lane runs in parallel with backend (generator, ablations,
  too_basic recall); thin path first (B1+B2 → freshness → B3a → B3b → B4 →
  B6a–c → B5 → B7; F0 → F2 → F6+F5 → F3 → F4 → F7); `review_cards` untouched
  in v4; disputed capped at 7 inside the new batch; `PendantLamp` cut; no
  interim 0.3.1; contract answers for backend (now, lookup time,
  reading_books, proper_noun from warnings only, exported_at incl. migrated,
  decision snapshot, settings defaults).
- Files: `AGENTS.md`, `docs/plan/meetings.md`, `docs/plan/m1-m2.md`,
  `WORKLOG.md`.
- Not verified: the reports were written from the plan, mostly without reading
  code line by line; contract answers are checked when B1–B4 start.
- Owner question: free open-source installer signing (recommend yes).

## 2026-11-19 - Claude (backend-engineer) - B1 schema v4 runner, B2 bulk catalog, freshness fix

- Goal: plan items B1+B2 and the freshness fix, per `docs/plan/m1-m2.md` as
  changed by the meeting after M1.
- B1: new `kindle_vocab_app/library_migrations.py` replaces the idempotent
  `_initialize`/`_create_schema`. Reads the version without writing; if < 4
  and the file has tables, copies it with the backup API to
  `.app-data/backups/kindle_cards.v<old>.<utc>.sqlite3` (journal DELETE,
  `integrity_check` + lexeme count verified, newest 3 kept, exclusive file
  claim so parallel starts never share a name) before any write; then
  `BEGIN IMMEDIATE`, re-reads the version, runs statements one by one, writes
  the version row, commits; on failure rolls back and raises «Не удалось
  обновить библиотеку; копия сохранена» (backup failure: «...; библиотека не
  изменена», nothing written). v4 adds `word_decisions`, `card_edits`,
  `export_runs`, `export_items` as in the plan, and backfills `migrated` runs
  grouped by (destination, timestamp) from `destinations` (anki/quizlet
  exported -> anki/csv, obsidian synced). A lost timestamp becomes the
  migration time. `review_cards`, `analyses`, `destinations` untouched; no
  decisions seeded; lexemes never deleted.
- Also: legacy JSON migration no longer runs when SQLite already has lexemes
  (before, a missing marker row would have replaced the library from JSON).
- B2: `load_catalog` runs 7 whole-table queries instead of ~4 per lexeme.
  Golden payload of `load_catalog` and bridge `load_library` captured on the
  old code (`tests/fixtures/library_v3_golden.json`) and matched after.
- Freshness: `merge_kindle` demotes the previous `new` batch only when the
  sync adds a lexeme.
- Real-size check on a scratch copy (deleted afterwards): 1961 lexemes before
  and after, occurrences unchanged, 20 export runs / 1022 items (all
  obsidian), backup verified ok, first start with migration 0.15 s, next
  start 0.007 s; old and new `load_catalog` identical, 0.084 s -> 0.075 s.
- Tests: `tests/test_library_migrations.py` (data survives, backup before
  writes, idempotent, keep 3, threads and two processes, rollback, backup
  failure, fresh DB, legacy guard, golden, query count),
  `tests/library_fixture.py` (frozen v3 DDL, synthetic rows),
  `tests/test_vocab_catalog.py` (freshness). Ruff on the CI list plus new
  files clean. Full pytest: 169 passed, 1 skipped, 2 failed in the ranking
  lane's uncommitted work (`test_ranking_eval` DatabaseTests: no column
  `word`; `test_ranking` REASON_CODES `thin_evidence`), not touched here.
  Bridge `load_demo` / `load_library` on a temp workspace: clean JSON.
- Files: `kindle_vocab_app/library_migrations.py` (new, add to CI ruff list),
  `kindle_vocab_app/library_repository.py`, `kindle_vocab_app/vocab_cache.py`,
  tests above, `tests/fixtures/library_v3_golden.json`.
- Not verified: migration on a library from before SQLite with real JSON;
  behaviour when the disk is full during backup. Nothing committed.

## 2026-11-19 - Claude (backend-engineer) - B1/B2 code-review fixes

- Backup race: the copy is now made after `BEGIN IMMEDIATE` and the version
  re-read, through a second reader connection (the locking connection cannot
  be a backup source: SQLite returns LOCKED and Python retries forever), so
  concurrent starts queue and only the one that still finds an old schema
  copies it. Six threads and four processes: exactly one real v3 backup.
- A failed or unverifiable copy is deleted; `list_backups` ignores empty and
  header-less files, so they never count toward keep-3.
- `load_catalog` reads all 7 queries in one read transaction (snapshot);
  tested with a commit from another connection between two queries.
- Legacy JSON: marker and "library has words" are re-checked inside the
  `BEGIN IMMEDIATE` transaction that replaces the catalog.
- History check: schema v1 -> v2 added `review_cards`, v2 -> v3 added
  `enrichments`; no ALTERs or column changes ever existed, so the v3
  baseline (`CREATE ... IF NOT EXISTS`) covers v1/v2; tested from v1.
- Lead confirmed: a lost export timestamp becomes the migration time.
- Checks: CI ruff list + new files clean; full pytest 178 passed, 1 skipped;
  real-size scratch copy unchanged numbers (1961 lexemes, 20 runs / 1022
  items, backup ok, 0.15 s); bridge `load_demo`/`load_library` clean JSON.
- Files: `kindle_vocab_app/library_migrations.py`,
  `kindle_vocab_app/library_repository.py`, `tests/test_library_migrations.py`.
  Nothing committed.

## 2026-11-19 - Claude (ranking-engineer) - M1 closing check: newcomer replay, synthetic newcomer, ablations

- Goal: does ranking v2 hold for a reader who is not the author (meeting
  decision 1)? Measured on a copy of the real library (aggregates only;
  nothing printed or logged but numbers) and on a synthetic newcomer library.
- Instrument (`ranking_eval.py`, additions only; the default report and
  `ranking_v2` are unchanged, so the headline numbers did not move: v2 AUC
  0.653 / lift@50 2.8 over the 2 comparable rounds, current_score 0.559 / 1.0):
  `--reader-file` (KOReader/Kobo/Kindle file instead of the library),
  `--newcomer [--first-books N --first-days D --step-days --start-days]`,
  `--ablation [--include-rejected]`, `--too-basic`. Metrics over several
  cutoffs are the mean per cutoff, bootstrap resamples words inside each cutoff
  and gives paired differences (same words for both rankers). The loader now
  reads export times from `destinations` (tolerates a library without them) and
  derives a proper-noun flag from each occurrence word + context (capitalised
  away from the sentence start, unknown to WordNet; every pre-cutoff lookup
  must look like a name). Both reach the ranking only through
  `v2_variant(exports=, proper_nouns=)`.
- Newcomer replay, real library (9 books; the first book is only 17 days, so
  "first book" is meaningless; I used the two long books and time cuts). Weekly
  cutoffs from day 14, window 21 days, lift@50, v2 vs current_score:
  one long book, first 56 days (1227 lookups, 3 cutoffs): AUC 0.614
  [0.57-0.66] vs 0.540 [0.50-0.58], lift 1.93 [1.40-2.77] vs 0.84 [0.54-1.18];
  two books, first 56 days (1349 lookups): AUC 0.594 [0.56-0.63] vs 0.598
  [0.57-0.63] (tie), lift 1.56 [1.27-1.99] vs 1.18 [0.94-1.44];
  two books, first 84 days (1789 lookups, 7 cutoffs): AUC 0.634 [0.61-0.66] vs
  0.582 [0.56-0.60], lift@50 1.77 [1.40-2.20] vs 0.95 [0.77-1.10], lift@20 2.18
  [1.48-3.08] vs 0.95; whole library, first 84 days (5 books): AUC 0.633
  [0.60-0.66] vs 0.571, lift@50 1.64 [1.23-1.89] vs 1.12, lift@20 1.99
  [1.28-2.55]. It COLLAPSES with less: whole library first 56 days (1378
  lookups, 3 cutoffs) AUC 0.602 [0.55-0.68] vs 0.548, lift@50 1.10 [0.55-1.57]
  vs 1.03; first 42 days (760 lookups, window 14): AUC 0.577 [0.47-0.67] vs
  0.572, lift@50 1.38 [0.70-2.00] vs 1.39. So: v2 is never significantly worse
  than the current score and beats it at the top from about 8 weeks / 1000+
  lookups; below about 6 weeks / ~750 lookups no ranking shown here is
  distinguishable from chance at the top (plain "number of lookups" is as good).
  The author reads ~14 lookups a day; a typical newcomer has fewer, so the
  threshold in calendar time is longer for them.
- First-sync shelves on the real replays (all words looked up in the window,
  now = last lookup): worth 31-56%, not_worth 14-60%, disputed 3-10%, but 31%
  disputed for one book at 29 days. Cause: single lookups 5-10 days old score
  inside [0.19, 0.22) (recency alone puts them there), and a first sync has many
  of them at once. The product caps disputed at 7 per batch, so the reader does
  not see the pile; the shelf count itself is large. Not changed (thresholds
  must not be tuned to one library).
- Synthetic newcomer (`ranking_synthetic.py`, seed 20261119): 475 lookups, 360
  words (320 invented pseudo-words, 30 common words, names and glued words as
  rejected junk), 2 books, 89 days, planted sticky words that come back within
  weeks and across books. Written as a KOReader `vocabulary_builder.sqlite3`
  and a Kobo `KoboReader.sqlite` and read back with `reader_sources`
  (read-only). Window 21 days, 7 cutoffs: v2 AUC 0.700 [0.63-0.76] vs
  current_score 0.507, lift@50 1.94 [1.5-2.5] vs 0.94, lift@20 2.15; first
  sync worth 123 / disputed 39 (10.8%) / not_worth 198. Five other seeds: v2
  AUC 0.72-0.81, lift@50 1.99-2.58, current 0.8-1.15. The plant matches the
  model's own assumptions (recency alone scores AUC 0.73 here), so this is a
  regression guard for the path import -> evaluate -> shelves, not evidence of
  generalisation; the real replay above is the evidence.
- UNVERIFIED, from memory: real KOReader keeps each word once (UNIQUE on
  `word`) and Kobo's WordList one row per word and book. If so, a KOReader or
  single-book Kobo newcomer has NO repeat-lookup signal at all (the synthetic
  `repeats=False` files show it: nothing comes back, so nothing can be
  evaluated), and ranking leans on recency, frequency band and junk. Worth
  checking on a real KOReader file before promising a ranking to those readers.
- Ablations on the real library (4 monthly cutoffs, rejected words included,
  lift@20/50, paired difference against v2 without the feature, 95% interval):
  after_export (export evidence = the one Obsidian reconcile of 2026-07-14,
  2044 of 3590 word-cutoffs have it, 202 were looked up again after it, 47 of
  them came back = 23% vs 12.8% base): old weight 2.0 AUC -0.001 [-0.002,
  +0.000], lift@50 -0.15 [-0.47, +0.22]; weight 1.0 AUC -0.001 [-0.002, +0.001],
  lift@20 -0.02 [-0.47, +0.62], lift@50 -0.12 [-0.47, +0.26]; 0.5 and 3.0 the
  same. Nine weekly cutoffs after the reconcile (908 of 12607 looked up
  again after it, 217 came back = 24% vs 11%): AUC -0.001 [-0.002, 0.000],
  lift@50 +0.06 [-0.20, +0.37]. In the noise: the word is already ranked high by its repeat and
  recency. Decision: after_export 2.0 -> 1.0 (neutral in the metrics, and the
  measured odds ratio of 2.1-2.4 is log 0.7-0.9, so 2.0 over-claimed); this is
  the only DEFAULT_WEIGHTS change. proper_noun: 7 of 3590 word-cutoffs carry
  it (0 came back), effect on every metric is exactly 0.000 at weights -0.75,
  -1.5, -3; the library cannot show it helps or hurts. Weight left at -1.5; the
  meeting rule says a feature with no gain goes, so recommend the backend does
  NOT build plumbing for it (WordFacts.proper_noun stays, defaults False).
- too_basic recall (4 cutoffs, flagged words incl. rejected): 45 flagged
  word-cutoffs; 37 land on not_worth (2 worth, 1 disputed, 5 junk); 3 of the 37
  came back = 8.1% [2.8-21.3] vs 12.8% [11.7-13.9] for the other 3545 words:
  no sign that hiding them costs the reader anything (n is small).
- Every not_worth word carries a negative reason: the grid test found words
  that did not (single lookup, mid-frequency band, lookup 33-54 days old: only
  the bias is against them). `rank` now appends `thin_evidence` (weight 0.0, "искали
  один раз, других признаков нет" / "мало признаков, что слово вам нужно"),
  only on not_worth and only when no negative contribution exists; scores are
  unchanged and still decompose. New reason code in `REASON_CODES` (contract
  addition for the bridge and the UI). A reader's own "не учить" is its own reason.
- Tests: `tests/test_ranking_synthetic.py` (new, 13: determinism, newcomer
  shape, both files import and agree, repeats=False has nothing to evaluate,
  `--reader-file` command, lift@50 > 1.5 with an interval above chance, v2 beats
  current with the lower bound > 0, shelves worth/disputed/not_worth each >= 5%
  and disputed <= 25%, no lookups after a cutoff in features);
  `tests/test_ranking_eval.py` (+11: restrict/step cutoffs, paired deltas,
  too_basic counting, export times and proper nouns from a library, older
  schemas load, ablation); `tests/test_ranking.py` (+3: negative reason grid,
  wording, decomposition). CI ruff list + `ranking_synthetic.py` + the three
  test files clean; full pytest 203 passed, 1 skipped.
- Files: `kindle_vocab_app/ranking.py`, `kindle_vocab_app/ranking_eval.py`,
  `kindle_vocab_app/ranking_synthetic.py` (new, NOT yet in the ci.yml ruff
  list: lead to add), the three test files.
- Risks: newcomer evidence is one author's reading at two paces, 1-7 cutoffs per
  scenario with overlapping windows (the intervals ignore that, so they are a
  little optimistic); the export signal is a proxy (one reconcile date), not
  real exports; the loader reads `destinations` only, not the new
  `export_runs`/`export_items` (add when real runs exist; a migrated run is
  stamped with the migration time, so it will never look "looked up again
  after export"); the pace dependence of the 8-week threshold. Nothing committed.

## 2026-11-19 — Lead: stage "B1+B2 and ranking for newcomers" integrated

- Backend (opus/high): schema v4 runner `library_migrations.py`, bulk
  `load_catalog`, freshness fix. Code review found a backup race, junk backup
  files eating retention, non-snapshot catalog reads and a legacy-import guard
  outside the replace transaction; all fixed with tests. Contract answer:
  an old export without a timestamp gets the migration time.
- QA (sonnet/medium) on a copy of the real library through the bridge: v3→v4,
  one verified backup, all table counts equal, 4 concurrent starts fine,
  second start makes no backup; no defects. Not covered: non-empty
  `review_cards`, full disk, packaged app.
- Ranking (sonnet/high): newcomer replay, synthetic library, ablations,
  too_basic recall, `thin_evidence` reason; `after_export` 2.0 → 1.0;
  `proper_noun` measured as zero effect (backend will not wire it). M1 holds
  from ~8 weeks of history and collapses at 6 weeks. Code review: one Windows
  log-handle leak in `tests/test_ranking_synthetic.py`, fixed by the lead.
- Verified by the lead: KOReader keeps one row per word
  (`reader_sources.py` reads `vocabulary` by word), so KOReader/Kobo readers
  have no repeat-lookup signal. First topic for the next meeting.
- CI ruff list: added `library_migrations.py`, `ranking_synthetic.py`.
- Checks: ruff clean; pytest 203 passed, 1 skipped; npm test 25 passed;
  npm run build ok. cargo check not run (no Rust change).

## 2026-11-19 — Lead: team meeting after "B1+B2 and ranking for newcomers"

- Six read-only views (skeptic opus/medium; ranking sonnet/medium; backend,
  frontend, advocate sonnet/low; qa haiku/low). Outcome in
  `docs/plan/meetings.md`, pointer in `docs/plan/m1-m2.md`.
- Decisions: honest first-weeks promise (short list, no personal-ranking
  claim, one line about rough order); library-wide ranking mode
  learning|full; check whether KOReader updates a row on re-lookup; disputed
  cap 5; lean list payload; next stage C0 contract then B3a+B3b, F0+F2 and
  ranking mode in parallel; B4 after.
- README: two lines made true for 0.3.0 (KOReader note, "usually finds").
- Owner questions: reword the M1 criterion, fiction frequency list, installer
  signing (recommendations recorded).
- Not committed yet.

## 2026-11-19 — Backend: C0 bridge contract draft (contracts only)

- Goal: a contract the lead can approve so B3/B4 and the frontend build in
  parallel. No bridge, UI, ranking or docs behaviour changed.
- Added `kindle_vocab_app/contracts.py`: TypedDicts and literals for
  `ranking`, `decision`, `card`, `export`, `is_new`, library-level
  `rankingVersion`, `rankingMode`, `historyDays`, `repeatSignal`, `shelves`,
  `newBatch`, `disputed`, `again`; action shapes for `set_decision`,
  `save_card_edit`, `export_preview`, `export_words`, `load_lexeme_details`;
  `ERROR_CODES` with Russian `ERROR_TEXTS` and `error_response`; settings
  bounds (`export_destination`, `export_batch_size` 5..100, default 20);
  `validate_library`, a pure validator the bridge tests can reuse. Literals
  are tied to `ranking.py` (`SHELVES`, `REASON_CODES`, `RANKING_MODES`,
  `DECISIONS`, `RANKING_VERSION`) by tests.
- `src/types.ts`: additions only. New lexeme fields are optional on
  `LexemeRecord` (old mock and screens keep compiling); `LexemeRecordV4` and
  `LibraryResultV4` make them required; `AppSettings` gets optional
  `export_destination`, `export_batch_size`.
- Key case follows the existing payload: lexeme-level and request keys
  snake_case, library-level and result aggregates camelCase (`runId`,
  `blockedReason`, `disputedLeft`).
- Shared fixtures `tests/fixtures/bridge_library_v4.json` (10 invented words,
  every shelf, a decision, an edited card, an exported word with `again`,
  two disputed, one unprocessed; mode full) and
  `bridge_library_v4_learning.json` (repeatSignal false, again unavailable).
- Tests: `tests/test_bridge_contract.py` (22: fixtures valid, validator
  catches 12 kinds of breakage, literals equal ranking.py, `types.ts`
  unions and constants equal contracts.py); `src/lib/bridge-contract.test.ts`
  (6; the fixture is cast to `LibraryResultV4`, key lists typed with `keyof`).
- Checks: ruff clean on contracts.py and the new test; full pytest 233
  passed, 1 skipped; npm test 31 passed; npm run build ok. Cargo not run.
- Open for the lead: see the report (disputedLeft duplicate, camelCase
  `runId`, `meaning_ru: ""` clears an edit, newBatch order, error codes
  beyond the five named). `contracts.py` is not yet in the ci.yml ruff list.
- Nothing committed.
- C0 revised per lead: `newBatch` = `{count, ids}` worth words only (disputed live in `disputed.ids`, not in the batch); `set_decision` returns `{entry, shelves, newBatch, disputed, again}` (no `rankings`, no `disputedLeft`); fixtures and tests updated; pytest 240 passed, npm test 31, build ok.

## 2026-11-19 — Ranking engineer: library-wide ranking mode `learning | full`, no-repeats replay, KOReader re-lookups

- Goal (meeting decisions 2 and 3): a library-wide mode for readers whose
  source keeps no repeat lookups or whose history is short; measure it as
  "not worse than frequency or the plain lookup count"; find out whether
  KOReader updates a row on a repeated lookup.
- Code (`ranking.py`): `RANKING_MODES`, `FULL_MODE_MIN_DAYS = 56`,
  `library_mode(history_days, repeat_signal, min_days=56) -> "full"|"learning"`,
  `rank(facts, now, weights=DEFAULT_WEIGHTS, mode="full")`, `Ranking.mode`
  (new field, default "full"). In `learning` the score and the reasons drop
  `repeat_lookups`, `several_books` and `after_export`; the frequency band,
  `reading_now`, recency, junk evidence, the negative-reason rule and the
  reader's decisions are unchanged; `known_again` stays as a weight-0.0 note.
  No weight, threshold or REASON_CODES change; `mode="full"` is the old
  behaviour. The short list in learning mode is the top N by `score` (ties:
  the backend breaks them by lexeme id); no separate sort key was needed.
- Instrument (`ranking_eval.py`): `collapse_repeats(library)` (first lookup per
  word), `build_examples(..., outcome=)` (features from one library, "came
  back" label from another), `blind_report(features, outcome, ...)`,
  `ranking_learning` in BASELINES, `shelf_counts(..., mode=)`, CLI flag
  `--no-repeats` (`--first-days`, `--step-days`, `--start-days` apply). Proxy:
  the rankers see only first lookups, the label is "looked up again in the
  window" in the same library with its repeats. WEAK EVIDENCE: a source that
  keeps no repeats never gets that label, and the proxy borrows it from a
  reader who did repeat words.
- Numbers, real library copy (2820 lookups, 163 days, 9 books, one reader; weekly
  cutoffs from day 14, 21-day window; mean over cutoffs, 95% intervals;
  `learning` = ranking v2 without repeat/books/export, features from first
  lookups only; lift = precision@k over the base rate):

  | history | cutoffs | ranker | AUC | lift@20 | lift@50 |
  | --- | --- | --- | --- | --- | --- |
  | 56 d | 3 | learning | 0.597 [0.544..0.657] | 0.73 [0.18..1.67] | 1.62 [1.07..2.17] |
  | | | frequency | 0.543 [0.479..0.595] | 1.03 [0.29..1.66] | 0.96 [0.51..1.41] |
  | | | lookups (all tied) | 0.500 | 1.00 | 1.00 |
  | 70 d | 5 | learning | 0.612 [0.578..0.649] | 0.98 [0.44..1.67] | 1.55 [1.16..2.01] |
  | | | frequency | 0.561 [0.520..0.591] | 1.03 [0.44..1.43] | 1.07 [0.67..1.30] |
  | 84 d | 7 | learning | 0.629 [0.593..0.660] | 1.37 [0.72..1.94] | 1.72 [1.33..2.17] |
  | | | frequency | 0.568 [0.539..0.592] | 0.86 [0.37..1.36] | 0.96 [0.62..1.22] |

  Paired learning - frequency: 56 d AUC +0.054 [-0.013..+0.126], lift@20
  -0.29 [-1.16..+0.78], lift@50 +0.66 [-0.16..+1.31]; 70 d +0.051
  [+0.005..+0.098], -0.05 [-0.77..+1.06], +0.48 [+0.02..+1.11]; 84 d +0.061
  [+0.021..+0.098], +0.51 [-0.33..+1.24], +0.76 [+0.34..+1.28]. Versus the
  lookup count at 84 d: AUC +0.129 [+0.093..+0.160], lift@20 +0.37
  [-0.28..+0.94], lift@50 +0.72 [+0.33..+1.17]. Reading: not worse than either
  at the top; clearly better over the whole list and at 50; at the top 20 the
  difference is inside the noise (17-95 words came back per cutoff). At 42 days
  (one cutoff, 17 of 150 came back) there is nothing to say: AUC 0.48 for
  learning, 0.53 for frequency, intervals +-0.12.
- Synthetic library (`repeats=False`, label from the same library with
  repeats, 21-day window, 8 cutoffs, default seed): learning AUC 0.652
  [0.576..0.707], lift@20 2.91 [1.88..3.84], lift@50 1.99 [1.57..2.36];
  frequency 0.499 / 0.53 / 0.97; lookups 0.500 / 1.0 / 1.0; plain recency
  0.663 (learning - recency AUC -0.011 [-0.058..+0.029]). Mean over 5 seeds
  AUC 0.703 vs frequency 0.534. First 42 days only: 0.635 vs 0.577, one cutoff
  (intervals cross zero). The planted process rewards recency, so this is a
  regression fixture, not evidence.
- Before / after: on a source without repeats the old v2 and `learning` give the
  SAME order (nothing to count), so the numbers do not move; what changes is
  that the contract names the mode and the reasons are guaranteed free of
  repeat claims. On the Kindle-shaped real library with repeats kept,
  `learning` vs v2: AUC +0.002 [-0.019..+0.019] (56 d), +0.010 [-0.004..+0.022]
  (70 d), +0.011 [+0.001..+0.024] (84 d); lift@20 -0.38, -0.72, -0.52 (all
  intervals cross zero, v2 ahead in point estimate); lift@50 +0.50, +0.13,
  +0.05. Horizon 14 days agrees (56 d AUC +0.006, 70 d +0.007).
  SURPRISE for the lead: on this one library the repeat signal does not make
  the whole-list order better than band + reading + recency at any history
  length measured (at most a lift@20 edge inside the noise). "full" is
  therefore not proven better than "learning"; it rests on the prior from the
  earlier meeting (v2 beats the old score from ~8 weeks).
- Threshold: `FULL_MODE_MIN_DAYS = 56` (8 weeks), kept from the previous
  replay (v2 held from ~8 weeks, collapsed at 6). The new numbers do not
  separate 56 from 70 or 84 (differences in the noise), so no better number
  exists in this library; and the choice is cheap: the two orders differ by
  <= 0.011 AUC. Not tuned to this round.
- Shelves in learning mode (thresholds unchanged): at the first cutoffs nearly
  every word is fresh and in the book being read, so `worth` is 90% of the
  list (135 of 150 at day 14, 17 of them came back = 13% vs 11% base; not_worth
  8, none came back). The shelf is coarse there; the short list must be cut
  by rank (top N), as the plan already says. Not tuned ("no fine-tuning").
- KOReader re-lookups (source: koreader/koreader,
  `plugins/vocabbuilder.koplugin/db.lua`, `VocabularyBuilder:insertOrUpdate`;
  https://github.com/koreader/koreader/blob/master/plugins/vocabbuilder.koplugin/db.lua).
  `word` is UNIQUE; an existing word is upserted with `ON CONFLICT(word) DO
  UPDATE SET title_id = excluded.title_id, create_time = excluded.create_time,
  ...` (it also resets the streak, lowers review_count and keeps the old
  contexts when the new ones are null). So a repeated lookup OVERWRITES
  `create_time` with the newest lookup time and the book with the newest book;
  the first lookup and any counter are lost. Consequences: `repeat_signal`
  stays false for KOReader (one row, no count); recency and "book being read"
  are real (the stored time is the LAST lookup); and "снова искали после
  экспорта" CAN work: a word exported at time T whose row now has create_time
  > T was looked up again after the export. That holds only if the app keeps
  the newest timestamp on re-sync (backend: a changed create_time of an already
  known `koreader:<word>` must update/append the occurrence, not be dropped as
  a duplicate). Kobo `WordList`: closed firmware, no source to read: UNKNOWN
  whether a repeated lookup adds a row or changes `DateCreated`.
- Tests: `tests/test_ranking.py` (+7 RankingModeTests: library_mode edges,
  default unchanged, bad mode refused, no repeat/books/export reasons and score
  equals the single-lookup score, band/reading/recency order, decomposition and
  decisions, junk and negative reason, known_again note);
  `tests/test_ranking_synthetic.py` (+6 LearningModeTests: collapse equals the
  repeats=False file, learning beats frequency / lookups / current_score with
  intervals above zero at lift@50, full == learning without repeats, labels
  from outcome, CLI `--no-repeats`, shelves). ruff clean on the CI list plus
  `ranking_synthetic.py` and the three test files; full pytest 241 passed,
  1 skipped.
- Files: `kindle_vocab_app/ranking.py`, `kindle_vocab_app/ranking_eval.py`,
  `tests/test_ranking.py`, `tests/test_ranking_synthetic.py`.
- Risks: proxy label (weak); one real library, one reader, 3-7 overlapping
  cutoffs (intervals optimistic); 42-day windows say nothing; `full` not
  proven better than `learning`; the learning shelf is coarse; Kobo re-lookups
  unknown; the whole-library window was not finished (84 days is the longest
  measured). Nothing committed.

## 2026-11-19 — Backend: B3a user writes + B3b re-link (repository level)

- Goal: the reader's decisions, card edits and export items are written
  directly and never lost when the catalog is replaced or keys merge. No
  bridge action yet (B5); contracts.py, fixtures, bridge, ranking, src untouched.
- New `kindle_vocab_app/library_state.py`: `set_decision` (validates against
  `ranking.DECISIONS`, stores language + canonical_key hint, `decided_at`,
  `shelf_at`/`score_at`/`ranking_version`; None deletes the row),
  `save_card_edit` (meaning trimmed, <= `MEANING_MAX_LENGTH`, "" or None
  clears; example must be an occurrence of this lexeme, its context and form
  are stored too; an edit with nothing left is removed), each one
  `BEGIN IMMEDIATE`; `read_decisions` / `read_card_edits` (one query each,
  linked rows only) for B4; `LibraryStateError(ValueError)` with `.code` and
  the Russian `ERROR_TEXTS` text (`bad_decision`, `unknown_lexeme`,
  `too_long`, `example_not_found`). Internal argument misuse raises TypeError.
- Re-link: `_replace_catalog` refreshes hints from the current lexemes before
  the delete and re-links orphans after the insert; `save_catalog` and
  `save_processed_lexeme` now run in one `BEGIN IMMEDIATE` and re-link in the
  same transaction. Target order: old->new id map from
  `_canonicalize_catalog` (new `id_map` key), then (language, canonical_key),
  then a form of exactly one lexeme. Merge conflict: newest row stays linked,
  the other is kept under `<id>#merged` so it is never re-linked (no
  resurrection after the reader clears a decision). export_items: every row
  re-linked; a same-run duplicate stays as an orphan. Log line has counts only.
- `library_repository.py`: repository methods `set_decision`,
  `save_card_edit`, `load_decisions`, `load_card_edits`; ruff fixes (imports,
  `datetime.UTC`); now ruff-clean.
- Tests `tests/test_library_state.py` (12, invented words): writes and
  validation codes, bulk readers 2 statements, survive two saves, process-queue
  key change then id recompute, merge keeps newest + orphan, form fallback,
  merge_kindle syncs leave user tables byte-equal, counts-only log, v3 with
  three review_cards intact through migration, a save and a restart.
  Mutation check: disabling relink fails 4 tests, disabling hint refresh 1.
- Checks: ruff clean (CI list + library_state.py + library_repository.py +
  the new test); full pytest 253 passed, 1 skipped; bridge smoke load_demo and
  load_library (empty and a migrated v3 fixture with user rows) ok, clean stderr.
- For the lead: add `kindle_vocab_app/library_state.py` and
  `kindle_vocab_app/library_repository.py` to the ci.yml ruff list.
- Risks: orphan export_items from same-run merges stay orphans (counted at
  DEBUG on every save); `save_processed_lexeme` conflict check still runs in a
  separate connection before its transaction (pre-existing). Nothing committed.

## 2026-11-19 — Frontend: F0 (mock split, pencil controls) and F2 (shell, early deletions)

- Goal: a browser mock that speaks the C0 contract, the pencil controls of the concept screens, the new
  shell, and the old Books/Insights/Review screens gone. Nothing committed.
- F0: `src/lib/mock-backend.ts` (split out of `backend.ts`, imported lazily so the Tauri build never loads
  it; build emits it as its own chunk). Returns the C0 fields beside the old ones; keeps decisions, card
  edits and export runs in memory; implements `set_decision`, `save_card_edit`, `export_preview`,
  `export_words`, `load_lexeme_details`; coded errors as `BridgeError` (new in `backend.ts`, carries `code`).
  Invented library grew from 6 to 12 words (every shelf, two repeat lookups, a word without a meaning).
  Scenarios: mixed, `no-new`, `export-error` added; disconnected, slow, operation-error, lexeme-failure,
  showcase and the rest kept. `resetMockBackend({scenario, instant})` for tests.
- Tests: `src/lib/mock-backend.test.ts` (11) holds the mock to the fixture's assertions, which now live as
  functions in `src/lib/contract-assertions.ts` (the lead may point `bridge-contract.test.ts` at them);
  `pencil-controls.test.tsx` (7, server-rendered markup: states and aria); `features/shell/views.test.ts` (3).
- `src/components/ui/pencil-controls.tsx`: `PencilButton` (lit/drawn, loading, kbd hint), `PencilChoice`
  (aria-pressed), `PencilLink` (button or anchor, lit, loading), `PencilRadioGroup` (roving tabindex, arrows),
  `PencilField` (wraps `Input`; label, hint, error, loading, commit on Enter/blur when changed). Buttons
  reuse `ui-button-*` states; `src/design/cabinet.css` holds only what the concept adds (`kc-*`).
  Checked in a throwaway gallery page (night and day, Tab focus ring), then removed.
- F2: `features/shell/views.ts` (`home|words|triage|export|settings`, `navViewOf`, `parseView`); nav is
  Главная, Слова, Настройки; the sconce maps triage/export to Слова; those two views open the library
  workspace until they ship. No Слова badge yet (the controller has no disputed ids).
- Deleted: `books-view.tsx`, `insights-view.tsx`, `review-view.tsx`; their CSS and the review card of the
  home screen (`.home-review*`, `.home-curl*`); `load_review` call and `dueCount` in `main.tsx`; helpers
  `bookStats`, `activityDays`, `lookupsForBook`, `repeatedLookupStats`, `reviewMinutes` and their tests.
  `ReadingHome` lost the review card, the "Все книги" links (one became "Все слова") and the clickable
  spines; its lower grid is two columns. `book-jacket.tsx` stays (home hero).
- Checks: `npm test` 51 passed; `npm run build` ok; preview `vite-preview` Главная and Слова in mixed and
  no-new at 1440 and 1280, view=triage lights Слова, no console errors.
- Not verified: Tauri build against the real bridge (types only; old fields untouched); docs/screenshots
  not refreshed (outside lane): `books.png` is stale, `home.png` changed (no review card).
- Open: Rust turns `{ok:false}` into a plain string, so `code` is lost on the real bridge; the UI should
  not depend on `BridgeError.code` until the lead settles that.
- Design review fixes (F0/F2): `--on-lamp` token replaces the ink-on-lamp literal everywhere; kbd hint in the hand font without a box; radio hover is a lamp stroke, not a plate; busy radio group no longer double-dims; field error has a dashed line and a hand-written note; control radii are `--kc-radius*` vars. Spines already had no hover/cursor. npm test 51, build ok.

## 2026-11-19 — Backend: B3 review fixes

- Rows whose hint no longer matches the word on their id are orphans (parked, re-linked by id map/key/form, else returned and ignored by readers; writes detach such a stale row instead of overwriting it); pre-delete hint refresh replaced by `follow_key_change` for the processed word only; `meaning_ru` whitespace runs collapse to one space before the length check; `save_processed_lexeme` merge check runs inside its `BEGIN IMMEDIATE`. +4 tests (16 in `tests/test_library_state.py`); ruff clean; pytest 257 passed, 1 skipped; bridge smoke ok. Nothing committed.

## 2026-11-19 — Lead: stage "C0 contract, B3, F0+F2, ranking mode" integrated

- C0 (backend, sonnet/high): `contracts.py`, `src/types.ts` additions, two
  shared fixtures, tests on both sides. Lead decisions: snake_case per lexeme
  and in requests, camelCase aggregates; `newBatch.ids` = worth words by rank
  cut at the batch size, disputed separate (≤5); `set_decision` returns
  `{entry, shelves, newBatch, disputed, again}`.
- B3a+B3b (backend, opus/high): `library_state.py`; decisions and card edits in
  their own transactions; re-link after catalog saves; merged losers kept as
  `#merged`. Review: no high-confidence bug; three lower ones fixed (stale id
  re-link, whitespace in translations, merge check inside the transaction).
  QA on a library copy: 50 decisions + 20 edits survive two saves and a sync,
  0 orphans, 10 s of concurrent writers without loss.
- Ranking mode (ranking, sonnet/high): `library_mode`, learning drops repeat,
  several-books and after-export signals; not worse than frequency at the
  top. KOReader's plugin overwrites `create_time` on a repeated lookup, so
  "looked up again after export" can work for KOReader. The agent was stopped
  after its report (it kept a background replay running).
- F0+F2 (frontend, sonnet/high): mock split with v4 fields and actions, pencil
  controls, nav Главная/Слова/Настройки, Books/Insights/Review deleted. Design
  review: 5 must-fix applied. QA in preview: pass; the reading home flashes
  the onboarding during a slow load (F6 must have a real loading state).
- Open for the lead: Rust turns `{ok:false}` into a plain string, so error
  `code` does not reach the UI (decide at B5).
- Checks: ruff (CI list) clean; pytest 257 passed, 1 skipped; npm test 51;
  build ok. cargo check not run (no Rust change).

## 2026-11-19 — Lead: team meeting after "C0 contract, B3, F0+F2, ranking mode"

- Views: skeptic (opus/medium), backend and frontend (sonnet/low),
  ux-clarity on Главная/Экспорт before building (sonnet/low). Outcome in
  `docs/plan/meetings.md`.
- Decisions: next stage is the thin path only (B4 + B6 core + Rust error
  code + F6 Главная with export states); cut export_preview, again-scope,
  Obsidian in export_words, the separate Экспорт screen, F4 for now;
  default destination stays today's Anki behaviour (AnkiConnect, else .apkg).
- Committed earlier as 2f9baec; this entry and the meeting note uncommitted.

## 2026-11-19 — Frontend: F6 Главная on the mock (short list, inline export)

- Goal: the thin path on Главная: one question «Что выгрузить сейчас?», the short list
  (`newBatch.ids`) with one reason and a translation per word, one lit button «Экспортировать N»,
  export states inline. Nothing committed.
- New `src/features/home/`: `home-domain.ts` (word plural, button label, «С прошлого раза» line,
  `shortList`, `pickReason` = strongest positive reason, `rankingNote`, `homeMode`, export state
  reducer idle/running/done/empty/error, done/error texts, `rankingOf` for the lean library answer),
  `use-home-export.ts` (`export_words {scope:"new", ids}` with exactly the listed ids, reload after
  success, `open_path` for «Открыть папку»), `home-view.tsx` (presentational), `home-screen.tsx`
  (controller glue), `home.css`. Skeleton until the first load, so the reader path never flashes.
  The desk lamp is lit only over a list (or over the reader path with a reader connected); out
  with a handwritten note otherwise.
- Controller: keeps `ranking` (short-list parts of the last answer), `demo`, `loadDemo`
  (`load_demo`, queue idle while shown), `exitDemo`; reloads the library after `process_queue`
  processed words so the list follows. `backend.ts`: `parseBridgeError` turns the Rust JSON text
  `{"error","code"}` into `BridgeError {code, message}` (plain strings pass through);
  `BridgeError.toString()` is the bare message so `String(error)` call sites stay clean.
- Mock: scenarios `learning`, `no-repeats` (learning mode, no repeat reasons, `again.unavailable`),
  `empty` (no words, no reader; `load_demo` returns the example library), `slow` also delays the
  first `load_library`; `load_demo` action. Removed: `reading-home.tsx`, `book-jacket.tsx` and their
  CSS (`home-*`, `dict-*`, `book-jacket*`). `ImportFileButton` got `look="pencil"|"link"`.
- Tests: `home-domain.test.ts` (26), `home-view.test.tsx` (9), `backend.test.ts` (4); npm test 90
  passed, npm run build ok. Preview (`vite-preview`): mixed, no-new, export-error (click), export
  done, disconnected, empty + demo, learning, slow (skeleton then list) at 1440 night, 1280 day;
  focus ring on rows checked; no runtime errors after reload.
- Not verified: Tauri build against the real bridge; docs/screenshots/home.png not refreshed (the
  browser pane cannot save files, and docs/ is outside this lane); 1280 night and 1440 day not
  all walked scenario by scenario; no-repeats scenario checked by test only, not by eye.
- Open for the lead: `load_demo` must return the v4 ranking fields or the demo list is empty;
  while words are unprocessed the list is short and grows after processing (the button is
  disabled and says so).
- Review fixes (design-language + ux-clarity): desk line and padding driven by `--home-pad-l/r`; status line always in the page (visually hidden when empty); no lede over the list; one status line by priority (`deskStatus`: error > done > busy > demo > rough order); rows are not clickable until F3; copy («Слова на этот раз», «Загрузить слова с читалки», «Выгружаю…», «Ищу читалку…», new apkg hint and empty note; «С прошлого раза» only when N differs from the list); error as a graphite cross. npm test 96, build ok; checked at 1280 and 600 px, no horizontal scroll.

## 2026-11-19 — Backend: B4 ranking in load_library, B6 core export_words, error codes

- Goal: the thin path through the real bridge: `load_library` returns a ranked short list and `export_words`
  sends it to Anki (or a file).
- New modules: `library_view.py` (`decorate`: WordFacts from the catalog, `now` = latest lookup,
  `historyDays`, `repeatSignal` from book-key prefixes, `library_mode`, per-entry `ranking`/`decision`/`card`/
  `export`/`is_new`, `shelves`, `newBatch`, `disputed`, `again`), `card_fields.py` (`resolve`: edited > LLM >
  dictionary, chosen occurrence > longest context; a dictionary meaning is cut to 200 chars on a sense
  boundary), `export_policy.py` (`is_exportable`), `export_cards.py` (`export_words`), `coded_error.py`.
- `tauri_bridge.py`: `export_words` action; `error_response` adds `code` to `{ok:false}`; the library
  decoration runs in `_catalog_response` and also in responses that hand back `entries` (process queue,
  enrichment, Obsidian sync) so a screen swapping its entries never loses the ranking; `load_demo` now
  builds a processed demo library (9 invented words, every kind of shelf) without touching SQLite.
- `library_state`/`library_repository`: `read_last_exports`, `record_export_run` (one transaction),
  `load_reader_state`. `anki_export`: `build_note_fields`/`write_apkg` take the reader's edits and
  `require_eligible`. `settings`: `export_destination`, `export_batch_size` with Russian validation.
- `src-tauri/src/main.rs`: on `{ok:false}` Err is the JSON text `{"error": text, "code": code|null}`.
- Tests: `test_library_view.py` (18, incl. perf), `test_export_words.py` (19); the v3 golden test now strips
  the new fields and validates the migrated library. Checks: ruff (CI list + new modules) clean, pytest
  293 passed / 1 skipped, cargo check ok, bridge smoke ok. Real-size check on a temp copy of the library
  (1,961 words): load 0.45 s, payload 4.41 MB before, 6.40 MB after; csv export of 20 words 0.19 s, the
  next load's batch shared no word with the exported one.
- Perf: decorating 3,000 synthetic lexemes 74 ms best of 3 (budget 150, CI gate 450).
- Open: `contracts.validate_library` demands a negative reason on every `not_worth` word, but ranking emits
  zero-weight `thin_evidence` and `decision_skip` (119 of 1,961 on the real copy); tests set that one
  message aside. Old actions (`export`, `export_apkg`, `push_anki`) still stamp `destinations`, not
  `export_runs`, so words sent through them stay in `newBatch` until B7 removes them.
- Nothing committed.
- Follow-up: tests validate the real payload (validator relaxed by the lead); `save_settings` merges the payload over current settings so omitted keys are kept (tested); ruff clean, pytest green.
- Review fixes in export_cards: export file names are unique (" (2)" suffix when taken), the .tsv.tmp is removed in a finally, the csv file is plain text (no HTML escaping; Anki notes keep their own escaping); +2 tests.

## 2026-11-19 — Lead: stage "thin path" integrated

- Backend (sonnet/high): B4 `library_view.py` (ranking, newBatch, disputed,
  rankingMode in load_library, load_demo and processing responses; 3,000
  words decorated in 74 ms); B6 core `export_policy.py`, `card_fields.py`,
  `export_cards.py`, `coded_error.py`; `export_words` to anki (AnkiConnect,
  else .apkg) and csv, recorded only after success; settings
  `export_destination`/`export_batch_size`, saves merge over current values;
  Rust returns `{"error","code"}` JSON text on ok:false.
- Frontend (sonnet/high): new Главная in `src/features/home/` with inline
  export states, rough-order lines, no-reader path, skeleton; old reading
  home deleted; backend.ts parses coded errors.
- Reviews: design-language and ux-clarity on Главная (6 must-fix + copy
  applied); code review of B4/B6 (no high-confidence bug; unique export file
  names, tmp cleanup, no HTML escaping in csv fixed). Lead relaxed
  `validate_library` (thin_evidence / decision_skip count as a reason
  against) and moved focus to the export result when the button disappears.
- QA on a library copy through the bridge: 1961 words, 470 worth / 80
  disputed / 1408 not_worth / 3 junk, newBatch 20, disputed 5, 0 contract
  problems; csv export of 10, list moves on; .apkg without Anki; error codes;
  settings persist. Preview: all scenarios pass.
- Accepted: an .apkg written when Anki is closed counts as exported (the
  screen tells the reader to open the file). Payload grew 4.4 → 6.4 MB (lean
  payload is B7).
- Not verified: the Tauri app against the real bridge, a real Anki.
- Checks: ruff clean; pytest 296 passed, 1 skipped; npm test 96; build ok;
  cargo check ok.

## 2026-11-19 — Lead: team meeting after "thin path"

- Views: skeptic (opus/medium), user-advocate, frontend, backend
  (sonnet/low); three were interrupted by the usage limit and resumed.
- Decisions: release 0.4.0 after a release minimum (remove Слова's old
  export buttons and the statistics line, real Tauri walkthrough with a real
  Anki, first-five-minutes copy, README and release notes); then B5 + F3
  simplified and «снова искали после экспорта»; F4 deferred; lean payload
  only if measured slow. Recorded in `docs/plan/meetings.md`.

## 2026-11-20 — Codex release_review — Настройки выгрузки и Obsidian для новой главной

- Аудит копии на `4675378`: новая выгрузка читает `export_destination`, а настройки меняли только legacy `default_export_format`; кнопки на «Слова» обходили новую историю выгрузок. Фоновая сверка Obsidian из предыдущей рабочей копии отсутствовала. Состояние выгрузки сбрасывалось при смене вкладки.
- В `settings-view.tsx` выведены назначение Anki/TSV, размер списка и явная синхронизация Obsidian. Недоступная папка отображается в этой секции; повтор проверки только перечитывает существующие карточки.
- В контроллере сохранения настроек идут частичными патчами по очереди. Изменение размера обновляет библиотеку; выгрузка ждёт сохранения. Сверка Obsidian идёт отдельно от загрузки и объединяет только сведения о наличии карточек, не подменяя список, рейтинг и остальной статус выгрузки.
- Старые UI-обработчики TSV/APKG убраны из контроллера; общий экран держит состояние новой выгрузки между вкладками. У завершённой обработки скрыта строка внутренних счётчиков; ошибки обработки сохранены. Просмотр примера не запускает фоновую сверку или автоперевод.
- Mock поддерживает частичное сохранение и read-only проверку Obsidian. Тесты проверяют сохранение назначения и доступность TSV, безопасное объединение результатов сверки и отказ от вызова без настроенного пути.
- Проверки: 44 теста Python для импорта, миграций, выгрузки и Obsidian на исходном `4675378` с тестовыми данными. TypeScript прошёл. Vitest внутри песочницы заблокирован доступом esbuild к родительской папке; вне песочницы 100/100. Реальный vault, Kindle и Anki не использованы. Сборку и визуальную проверку ведёт основной агент. Коммит не создан.

## 2026-11-20 — Codex — Перенос основной копии Kindle Cards и восстановление работы

- Найдена исходная рабочая копия Anki Cards. Подтверждено, что прежний HEAD `59ac6de` — предок `4675378`. Ветка main в текущей рабочей области переведена на `4675378` с исходной историей (36 коммитов). Перенесены более поздние заметки встречи и 41 отсутствовавший раздел WORKLOG. Старое содержимое журнала сохранено побайтно. Исходная папка, личные базы и настройки не изменялись.
- В recovery собраны архивы проекта Claude Design и локальная история Claude Code/Desktop. Проектные документы, пользовательские макеты и основные указания взяты из новой копии. Два каталога с материалами личного аккаунта исключены из Git. Перед переносом прежние незакоммиченные правки проверены трёхсторонним сравнением: закрытие SQLite и пропуск POSIX-теста уже были в новой ветке; исправления Obsidian перенесены поверх неё.
- Продолжен этап перед 0.4.0: экспорт с главной учитывает историю и сохраняет состояние при уходе со вкладки; выбор Anki/TSV и размер списка в Настройках, там же действие Obsidian. Удалены старые кнопки экспорта на экране Слова. Главная объясняет ручную загрузку файла и открытие .apkg. Имя файла резервируется эксклюзивно, чтобы параллельные выгрузки не перезаписывали друг друга. Сверка Obsidian сохраняет только состояние назначения, поэтому не откатывает параллельный импорт.
- Проверки: 303 Python-теста прошли, один пропущен; 100 frontend-тестов и сборка Vite прошли; cargo check и нативная сборка Windows прошли. В браузере на 1440 и 600 px проверены переходы между вкладками, .apkg, выбор TSV, повтор проверки недоступной папки, ошибка экспорта и демо. Найдено и исправлено исключение обработчика повторной проверки Obsidian; итоговый Playwright прошёл без ошибок консоли, снимки просмотрены.
- Нативный сценарий с изолированной SQLite и шестью вымышленными словами прошёл через WebView2, Rust и Python: пять строк записаны в TSV, выгрузка отражена в SQLite, одно слово осталось в списке. Первый запуск WebView2 из песочницы оборвал CDP-соединение; с тем же изолированным профилем вне песочницы проверка прошла. Установка npm зависла в песочнице, восстановлены локальные зависимости из исходной копии после сверки lockfile. Для Vite потребовалась проверка вне песочницы из-за доступа esbuild к родительскому каталогу.
- Реальные Kindle, Anki и Obsidian не использовались. Версия 0.4.0 не выпускалась. Новые правки оставлены в рабочей области, коммит и push не выполнялись.

## 2026-11-20 — Codex — Сверка формата командной работы Claude

- Сопоставлены роли и правила в AGENTS.md с памятью Claude, восстановленными отчётами и протоколами этапов. Подтверждена практика отдельных задач, контрактов перед реализацией, письменных обсуждений и итога ведущего. Зафиксированы реальные примеры по рейтингу, схеме SQLite и маршруту экспорта.
- Изменён только WORKLOG.md. Проверка документальная, код и тесты не затрагивались, коммита нет.

## 2026-11-20 — Codex QA — Релизный путь на командной планёрке

- Проверил текущий рабочий кандидат над `4675378`, предыдущий протокол, покрытие импорта, миграции и Anki, логику записи истории и сценарий установки. Изменён только WORKLOG.md, коммита нет.
- В Windows conda `kindle_app` прошли 53 из 53 целевых Python-тестов. Через отдельные процессы JSON-моста повтор импорта вымышленного KOReader-файла дал 1 → 0 новых слов, всего 1 слово и 1 контекст. Для трёх вымышленных слов сохранённый `.apkg` остался валидным, при следующей загрузке список пуст, путь файла в ответе отсутствует.
- При управляемом перекрытии двух запросов выгрузки одних и тех же трёх слов оба вернули успех: два разных TSV с одинаковыми строками, шесть строк истории. Тест на параллельную запись разных слов покрывает коллизию имён. При искусственном отказе записи истории файл сохранился, а повтор создал второй файл. Частоту этих ситуаций в штатном интерфейсе не измерял.
- Проверил глобальную новизну: после TSV смена назначения на Anki оставляет список пустым и повтор этих IDs даёт `nothing_to_export`. Это текущее правило `scope:new`, расширение повторной отправки отложено. Мигрированная история может включать Obsidian, поэтому это правило важно оговорить для старых библиотек.
- Рекомендация для 0.4.0: собрать локальный кандидат, перед публикацией пройти чистую установку, ручной импорт, TSV и оба маршрута Anki в изолированном профиле. При закрытии сразу после записи колоды файл должен повторно находиться по ссылке или указанной папке, два импорта пакета должны дать то же число и те же идентификаторы заметок. Параллельный дубль проверять отдельно через две обычные копии приложения. Автообнаружение и чтение Windows MTP/WPD требуют устройства.
- Реальный Anki, установщик и Kindle не запускал. Личные базы, исходники и версии не менял. Действующий релизный workflow собирает артефакт, но не проходит пользовательский сценарий после установки.

## 2026-11-20 — Codex, ведущий и рецензенты — Полноценная планёрка перед 0.4.0

- Цель встречи — выбрать ближайший этап после переноса проекта и проверить, что мешает первому экспорту. В AGENTS.md закреплены независимые позиции, раунд возражений, решение ведущего, ответственные и критерии приёмки. Владелец делегирует выбор моделей и исключает Astra для субагентов.
- Шесть участников на gpt-6.2-sol. Продуктовый скептик сравнил приёмку первого экспорта, инспектор и сценарий возврата. Представитель читателя проследил получение и поиск колоды после перерыва. QA отдельно записал результаты воспроизведений выше. Backend предложил изменить обработку отказа Anki и после возражения согласился сохранить очередь и доступ к уже созданному файлу. Специалист по ранжированию сверил слабые данные для первых 20 слов с поведением первой загрузки. UX-рецензент уточнил приёмку ссылки на каталог, управление с клавиатуры и текст при потере подтверждения от Anki.
- В docs/plan/meetings.md записаны решения, возражения и порядок работ. Приоритет — установленная сборка, в которой можно закончить импорт после перезапуска. Во время первой обработки Главная должна отличать ожидание от закончившегося пустого списка. Гонку двух запросов проверим через штатный запуск двух экземпляров. Порядок B5/F3 и последующего сценария повторного поиска сохранён.
- В этой работе изменены AGENTS.md, docs/plan/meetings.md и WORKLOG.md. Проверены локальные ссылки протокола и git diff --check. QA прогнал 53 целевых теста на синтетических данных. Известные границы — проверка состояний Главной по исходникам, воспроизведение гонки на backend, реальные Kindle, Anki и текущий установщик остаются для этапа приёмки. Коммит и релиз не создавались.


## 2026-11-20 — Codex backend — Безопасная выгрузка и доступ к сохранённым файлам

- Цель — дать найти сохранённую колоду или TSV после перезапуска и не отправлять одни и те же слова из двух процессов. Изменены `anki_connect.py`, `contracts.py`, `export_cards.py`, `tauri_bridge.py`, `test_anki_connect.py` и `test_export_words.py`. Незакоммиченные правки предыдущего этапа сохранены.
- `export_folder_status` возвращает наличие непустого готового `.apkg`/`.tsv` в каталоге текущей библиотеки. `open_export_folder` открывает этот фиксированный каталог и возвращает `opened: false`, если готового файла уже нет или открытие не удалось. Проверка не создаёт каталог. Временные файлы, пустые резервы и каталоги со сходными расширениями не учитываются.
- AnkiConnect: успешный ответ подтверждает отправку, недоступность до отправки оставляет штатную выгрузку в файл. После попытки `anki_import_unconfirmed` и `anki_import_rejected` сохраняют созданный `.apkg` и слова в очереди. После сбоя записи истории TSV текст прямо сообщает об уже созданном файле и новом файле при повторе.
- `scope:new` удерживает неблокирующую файловую блокировку на рабочую область от чтения состояния до записи истории. Второй процесс получает `export_busy`. ОС освобождает блокировку при выходе, SQLite не держит долгую транзакцию. Проверены одинаковые и пересекающиеся IDs, повтор обрабатывает только оставшиеся слова, принудительное завершение процесса освобождает блокировку.
- Проверки в Windows conda `kindle_app`: 34 целевых теста, полная серия 311 прошли и 1 пропущен, `compileall`, ruff по списку CI и изменённым тестам, `git diff --check`. HTTP-сценарии Anki отработаны на локальном двойнике. Открытие Проводника, POSIX-ветку блокировки, замороженный мост, реальные Anki и Kindle в этой работе не запускали. Коммит не создавался.

## 2026-11-20 — Codex QA — Реальный Anki и обнаружение Kindle на Windows

- Цель: проверить ручной и подключённый экспорт перед 0.4.0 с установленным Anki 25.09.4. Использованы вымышленные слова, отдельные SQLite-библиотеки Kindle Cards, временные базы Anki и свежие профили с отключёнными синхронизацией и проверкой обновлений. Перед запуском проверено отсутствие Anki и слушателя 8765.
- Закрытый Anki: вызов export_words через настоящий процесс JSON-моста записал .apkg с тремя словами, список 3 → 0. Backend Anki дважды импортировал один и тот же файл. Осталось три заметки и три карточки с теми же идентификаторами, GUID, словами, контекстами и переводами. Сверены отрендеренные вопрос и ответ.
- Ручной вариант через стандартный диалог Qt Anki: первый импорт сообщил 3 новых записи, повтор того же файла 3 уже присутствующих. Подтверждены количество, идентификаторы и содержание обеих сторон. В песочнице Qt WebEngine не загрузил содержимое диалога ни в offscreen, ни в Windows-режиме. Обычный Windows-режим вне песочницы прошёл с тем же скриптом и новым временным профилем.
- Подключённый Anki: штатным загрузчиком AnkiWeb получено дополнение 2055492159. Только официальный код и стандартный config помещены во временный профиль; слушатель 127.0.0.1, API 6. Через реальный процесс JSON-моста получено pushed=3, path=null, список 3 → 0. Повтор этого же пакета через дополнение сохранил идентификаторы, поля и число карточек. Дополнение выводит предупреждения requireReset/save об устаревших вызовах, импорт проходит.
- Пассивное обнаружение Kindle вернуло «не найден». В выводе Windows PnP для подключённых устройств нет Kindle или USB VID_1949. Содержимое накопителей и vocab.db не открывались. После проверки Anki закрылся и порт 8765 свободен.
- Проверен мост рабочего дерева, отдельно проверен стандартный диалог установленного Anki. Установщик Kindle Cards и физические маршруты диска или MTP/WPD этим прогоном не проверены. Личные настройки и данные не использовались. Изменён только WORKLOG.md, коммита нет.

## 2026-11-20 — Codex frontend — Ожидание первой порции и доступ к сохранённой выгрузке

- Главная отличает поиск читалки, очередь обработки, остановку с возможностью продолжить и готовый пустой список. При завершении очереди ждёт актуального рейтинга; у демо отдельный цикл ожидания и закрытия. Изменены экран, модель состояний, контроллер и настройка назначения. Тексты уточняют, что читалка не найдена, порядок может быть примерным, а выбор назначения влияет на следующие выгрузки.
- Единственное действие «Открыть папку выгрузок» проверяет наличие файлов через `export_folder_status` на Главной, после экспорта и при возврате в окно. `open_export_folder` открывает каталог, а `open_path` открывает сохранённую колоду в Anki. Отказ открытия с файлами отличён от исчезновения последнего файла. Интерфейс различает `anki_import_unconfirmed`, `anki_import_rejected` и `export_busy`.
- После рецензии предупреждение о неподтверждённом импорте стоит перед вторичной повторной отправкой. Успешное сохранение колоды объясняет подтверждение импорта. Кнопка папки остаётся фокусируемой при выполнении, возвращает фокус к сообщению при исчезновении только если была сфокусирована и не перехватывает Tab. В узкой оболочке устранено обрезание заголовка из-за минимальной высоты flex-элемента.
- TypeScript и Vite build прошли; 105/105 Vitest. Browser plugin отсутствует, использован Playwright Chromium с локальным dist и моками. Пройдены 13 сценариев на 1440 и 600 px, включая повторное открытие, отказ, удаление при клике и возврате в окно, сохранение фокуса, Tab, продолжение очереди и выход из демо. Ошибок консоли и перекрытий интерфейса в финальном прогоне нет. Просмотрены шесть снимков во временном каталоге. Промежуточные проверки выявили старый список кодов в тесте, потерю aria-busy в примитиве, автоматическую синхронизацию в момент Tab в сценарии и срез заголовка; повторные проверки прошли.
- В этой задаче не проверялись физический Kindle, Проводник, установленный Tauri и реальный Anki. Коммит и публикация не выполнялись.

## 2026-11-20 — Codex QA — AnkiConnect и файл из установленного кандидата 0.4.0

- Проверен установленный Kindle Cards 0.4.0 из финального NSIS (SHA-256 C2F38D8B…); SHA-256 установленного EXE f00e731e5dc4a0df1283f958fbbd8a55a6f5f91f0ee23daa46c93b767ef032ad. Использованы штатное окно Tauri, упакованный мост, отдельная SQLite с пятью вымышленными словами и свежий профиль установленного Anki 25.09.4 с официальным AnkiConnect API 6 на 127.0.0.1.
- Перед запуском трижды подтверждено отсутствие Kindle через Windows PnP и пассивный детектор приложения. Перед нажатием проверка повторена. Скрипт сверил точное множество из пяти строк на Главной и только затем нажал обычную кнопку экспорта.
- Главная подтвердила «Готово: 5 слов в Anki». В Anki созданы ровно пять заметок и пять карточек. Сверены слово, исходное предложение, русский перевод и обе стороны карточки. В SQLite приложения один запуск выгрузки на пять разных слов. После перезапуска список пуст, кнопки экспорта нет. Повтор того же .apkg через AnkiConnect оставил те же идентификаторы заметок и карточек.
- Отдельно пакет fallback, сохранённый Главной установленной сборки при выключенном AnkiConnect, дважды открыт штатным движком Anki в новой временной коллекции. Первый импорт добавил восемь заметок и карточек, второй не добавил ни одной и сохранил ID и GUID. Точные предложения проверены для всех восьми слов на обеих сторонах.
- Окна кандидата и тестовый Anki завершились. Подключённый экспорт проверен без физического Kindle, устройство проверял ведущий другим прогоном. Личные коллекции и синхронизация Anki не использовались. Изменён только WORKLOG.md, коммита нет.

## 2026-11-20 — Codex, ведущий — Приёмка и локальная установка 0.4.0

- Выполнен этап из протокола 20 ноября. Сохранён доступ к выгрузкам после перезапуска, разделены обработка и пустой список, межпроцессная защита устранила двойную выгрузку, интерфейс различает отказ Anki и потерю подтверждения. Включены замечания рецензента по порядку предупреждения, ручному подтверждению импорта и фокусу клавиатуры. Описание шагов для 0.3.0 и кандидата разведено в README, добавлены заметки docs/releases/0.4.0.md. Согласованы версии npm, Python, Cargo и Tauri.
- Первая сборка release встретила ошибки Windows 5/32 при запуске служебного build-скрипта Cargo. С диагностическими символами зависимостей сборки (CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_DEBUG=true) оптимизированный Rust и штатный NSIS собрались. Замороженный Python-мост проверил демо, конфигурацию и равенство обработки трёх слов с dev-Python. В нативном прогоне выявлен запрет подписки на события прогресса. src-tauri/capabilities/main.json разрешает локальному главному окну только подписку и отписку от событий. После пересборки ошибка исчезла.
- После разрешения владельца сохранена локальная копия предыдущих программных файлов 0.1.0, существующая установка обновлена штатным NSIS в режиме /UPDATE. Окончательный установщик x64 имеет размер 43 693 750 байт, SHA-256 c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826. Ярлык меню «Пуск» ведёт на 0.4.0. Tauri при упаковке ставит в EXE признак типа пакета, поэтому сравнение с рабочим cargo-выходом сначала дало расхождение. Побайтное сравнение обеих установленных программ с извлечёнными из самого NSIS прошло. Тестовые окна запускались с отдельными библиотеками.
- Финальная установленная сборка: восемь вымышленных строк в файле формата Kindle обработаны и выгружены, после перезапуска Проводник открыл правильный каталог по клавиатурному действию, повторная загрузка файла оставила восемь контекстов. На двух одновременно работающих экземплярах одна попытка заняла выгрузку, другая вернула export_busy; итог — один TSV с пятью уникальными словами и одна запись выгрузки. Прогон временной v3-библиотеки упакованным мостом подтвердил v4, сохранность слов и истории и целую резервную копию v3. Настоящий Anki и конечный NSIS, проверка пяти и восьми карточек описаны в записи QA.
- Проверен подключённый владельцем настоящий Kindle по Windows MTP/WPD. До физического отключения два чтения дали 2 551 поиск и 1 815 слов. Наблюдались исчезновение и новое появление USB-устройства. После переподключения в самой базе Kindle стало 2 552 поиска и 1 816 слов, повторное чтение вернуло те же числа. Прежнее условие теста об отсутствии изменений в источнике оказалось неприменимо. Для проверки корректного приращения использовали временную локальную копию базы без одной последней записи, затем дважды прочли настоящий Kindle в ту же тестовую библиотеку. Все 2 551 прежних идентификатора наблюдений сохранились, добавились один новый идентификатор наблюдения и одно слово, следующий проход добавил ноль. Чтение устройства и тесты Anki разнесены, выгрузок реального словаря не выполнялось.
- Проверки: Python 311 прошли, 1 пропущен; frontend 105/105; 13 браузерных сценариев, финальная сборка Windows, реальные WebView2, Проводник, MTP и Anki 25.09.4. Проверен git diff --check. Закрывающая встреча, альтернативы и условие следующего этапа записаны в docs/plan/meetings.md. Согласие получено на локальную установку. Публичного релиза, push и нового коммита не было. Опыт независимого нового пользователя, другие модели читалок и установка на отдельную чистую Windows в этом прогоне не проверялись.

## 2026-11-20 — Codex, рецензент — Состав публикации 0.4.0

- Проверил имена файлов в 36 коммитах относительно сохранённого origin/main, рабочую дельту, заметки и workflow релиза. Ведущий подтвердил фактический удалённый HEAD `fb8f1b6`: над ним три локальных исторических коммита.
- В просмотренных деревьях нет пользовательских баз, выгрузок и архивов восстановления. Поиск типовых форматов токенов и закрытых ключей совпадений не дал. Рекомендовано оставить локальные журналы и recovery вне дельты публикации, обновить формулировки README и заметок до версии 0.4.0 и учесть автоматическую сборку при выборе проверенного установщика.
- Проверка по именам и шаблонам не заменяет анализ двоичных файлов. Установщик не исследовал. Добавлена только эта запись, коммита и публикации не было.

## 2026-11-20 — Публичный выпуск Kindle Cards 0.4.0

- По запросу владельца опубликовал стабильный выпуск в GitHub Releases. Публичные main и аннотированный тег v0.4.0 указывают на 16b6c0c9015c3cd6620f0fe8a2c5a8c5f2ce0254 поверх fb8f1b6. Предыдущий локальный HEAD сохранён в codex/before-public-0.4.0. В рабочей области main синхронизирована с origin/main. Внутренние записи разработки и архивы восстановления в релизную дельту не вошли.
- Подготовил README.md и docs/releases/0.4.0.md для публичного скачивания и обновления. В pyproject.toml ограничил стандартный поиск pytest каталогом tests после того, как локальный прогон захватил тесты сторонней зависимости из каталога уже собранного приложения. Штатный прогон завершился с 311 passed, 1 skipped. Vitest — 105 passed. Ruff и git diff --check прошли.
- GitHub Actions CI (44707393164) и Release (44707393179) успешно завершились на Windows. Установщик CI сохранён артефактом этой сборки. В черновик релиза загрузил установщик, ранее прошедший приёмку на настоящих Kindle и Anki, и SHA256SUMS.txt. До публикации сверил размер и digest обоих вложений. После публикации проверил latest, текст заметок и повторно скачал оба файла по общедоступным ссылкам. SHA-256 и размеры совпали с оригиналами. Установщик Windows x64 — 43 693 750 байт, SHA-256 c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826.
- Публичная страница https://github.com/Rescue5/kindle-anki-cards/releases/tag/v0.4.0. Версия установлена у владельца ранее. Цифровой подписи Authenticode у установщика нет.

## 2026-11-20 — Codex, инженер интерфейса — Критерий приёмки редактора карточки

- Сверил описание роли, PRODUCT.md, DESIGN.md и решение по B5/F3. Предложил проверить один сценарий с клавиатуры: изменить перевод и выбрать предложение из книги на экране «Слова», после перезапуска увидеть сохранённые значения и подтвердить, что оба попали в экспорт.
- Изменён только WORKLOG.md. Реализация и проверка сценария ждут отдельного поручения. Коммита нет.

## 2026-11-20 — Тимлид: постоянные чаты команды Kindle Cards

- По просьбе владельца координирующий чат переименован в «Тимлид». В этом проекте созданы отдельные чаты десяти субагентов Codex с их собственными историями. Для двух специальных ролей исходной команды Claude — фронтенд-разработчика и рецензента визуального дизайна — открыты чаты по сохранившимся описаниям ролей.
- В AGENTS.md закреплены имена двенадцати специалистов и порядок взаимодействия. Тимлид назначает задачи в профильных чатах, на планёрках передаёт участникам конкретные возражения и фиксирует решения. При передаче ролей использована модель gpt-6.2-sol.
- Через инструменты чатов проверены состав проекта, названия и ответы всех двенадцати специалистов. Для следующей продуктовой планёрки зафиксирован вопрос о минимальном редакторе перевода и предложения из книги. Код приложения не изменён, публикации не выполнялись.

## 2026-11-20 — Тимлид: модели для рабочих чатов

- По просьбе владельца распределены модели и глубина рассуждения у двенадцати специалистов. Бэкенд и ранжирование получили gpt-6.2-sol, четыре чата разработки и продуктовых решений — gpt-6.1-sol, три чата визуальной работы и приёмки — gpt-6.1-terra, ещё три для типовых задач и работы с архивом — gpt-6-luna. Точные назначения приведены в AGENTS.md.
- Настройки переданы в каждый существующий чат. У всех двенадцати завершился ход с ожидаемыми моделью и глубиной по метаданным выполнения. В AGENTS.md закреплены базовые назначения и возврат к ним после сложной задачи. Расход в деньгах не измерялся.

## 2026-11-20 — Тимлид: продуктовая планёрка после 0.4.0

- Провёл два раунда в постоянных чатах продакт-менеджера, UX-исследователя, инженера ранжирования и UX-дизайнера. Сопоставил предложения с приёмкой, данными GitHub, инструкцией Kindle2Anki и публичным запросом читателя Readest. На момент обсуждения у установщика два скачивания, одно из скачиваний делала команда. Подтверждённых внешних повторных использований пока нет.
- Следующий этап — пять наблюдаемых первых сеансов на действующей 0.4.0 и повторный контакт через 7–10 дней. Проверяем интерес к короткой подборке слов из своей книги, использование карточек и самостоятельную повторную выгрузку. На втором раунде убрали предварительный выбор слов, разделили привлекательность приглашения и удобство установки, зафиксировали, как учитывать читателей без новых поисков.
- Дополнен docs/plan/meetings.md. В протоколе есть выбор аудитории, альтернативы, владельцы задач, черновик приглашения и условия перехода к редактору, пересмотру отбора или исправлению установки. Рассылок, контакта с читателями и программных изменений на планёрке не было. Пороги остаются рабочей гипотезой для пилота.

## 2026-11-20 — Бэкенд-разработчик: первый раунд B5

- Проследил правку от `LibraryRepository.save_card_edit` через повторный импорт до эффективных полей в Anki и TSV. Предложил зарегистрировать предусмотренное контрактом `save_card_edit` с ответом `{entry}` и существующими кодами `too_long`, `example_not_found`, `unknown_lexeme`. Редактор получает предложения из `entries[].occurrences`; мок требует сверки очистки выбора и нормализации пробелов.
- Для приёмки предложил сквозной прогон JSON-моста на временной библиотеке: две правки, перезапуск, импорт того же файла, совпадение перевода и выбранного контекста в `.apkg` и TSV на отдельных копиях. Отдельный случай для обсуждения — повторный импорт заменяет старый ID наблюдения, экспорт читает сохранённый текст, а текущий payload его не передаёт. Повторная выгрузка уже отправленных слов требует отдельного согласования.
- Проверка по исходникам и существующим тестам на базе `16b6c0c`. Добавлена только эта запись. Тесты и реальные приложения не запускал, новый коммит не создавался.

## 2026-11-20 — Инженер ранжирования: объяснение частоты и проверка «Не учить»

- Цель — убрать догадку о значении слова, которую признаки не подтверждают, и проверить сохранность персонального исключения между порциями. В ranking.py текст frequency_common заменён на «очень частое слово». Код причины, вес, пороги и сортировка сохранены. В tests/test_ranking.py проверены оба режима на Zipf 5,6: вклад −0,6, оценка 0,231475, полка worth.
- Синтетический ranking_eval на штатном seed, без повторов в признаках, с окном 21 день и восемью срезами: AUC 0,652102 → 0,652102, lift@20 2,911293 → 2,911293, lift@50 1,991826 → 1,991826. На срезе 14-го дня среди 59 слов код frequency_common остаётся у одного слова, необоснованная фраза исчезла (1 → 0). Это проверка сохранности отбора на синтетике.
- Во временной SQLite на вымышленных данных через dispatch/set_decision исключил лидера пятёрки. Новый поиск того же слова и новая запись в каталоге сохранили skip, явный запрос export_words для его ID вернул nothing_to_export. Снятие решения вернуло слово на полку worth. При равной оценке двух лидеров сортировка по ID устойчива на повторных загрузках. Аудит охватывает тот же канонический ID, новую порцию, SQLite и scope:new; UI, настоящие базы и другие маршруты выгрузки не проверялись.
- Первый целевой прогон выявил оставшуюся проверку старого текста, её заменил тест нового объяснения. Итоговый pytest: 315 прошли, 1 пропущен. Ruff для изменённых файлов и git diff --check прошли. Личные данные, зависимости и внешние сервисы не затрагивались. Базовый коммит 16b6c0c, новый коммит не создан.

## 2026-11-20 — Инженер интеграции с Anki — Сохранение карточек и решений в контроллере

- В use-library-controller.ts добавлены Promise<void> методы saveCardEdit и setWordDecision для действий save_card_edit и set_decision. Обновляется изменённая запись и ответные счётчики, затем перечитывается весь актуальный рейтинг, включая ранги остальных слов. Записи выполняются по очереди; отказ возвращает русское сообщение.
- Новый library-edits.ts хранит версии ответов и переключений библиотеки. Старые load_library, сведения Obsidian и ответы фоновых действий не применяются после правок или смены библиотеки. Во время demo/loading, неизвестного ID и текущей операции сохранение отклоняется. На время записи не запускаются синхронизация/обработка, способные заменить каталог. Незавершённые записи не подменяют демо.
- Mock выровнен с Python: выбирается самый длинный контекст, последовательности пробелов перевода схлопываются, пустой ID снимает выбор, явный выбор даже исходного примера считается правкой, длина перевода считается в Unicode code points.
- Добавлены восемь тестов helper на payload, повторное чтение, skip/снятие и замену подборки, очереди, отказы, старые ответы и смену сессии. В mock suite добавлен сценарий очистки выбора/перевода и Unicode. Финальные проверки TypeScript и 117 Vitest прошли; Vitest запускался вне песочницы после отказа esbuild читать родительский каталог. Ошибка первой тестовой выборки исправлена добавлением шестого подходящего слова, ожидаемая замена подтверждена.
- Сохранение после перезапуска проверено повторным чтением mock-состояния, реальное окно и bridge storage проверяются ведущим вместе с backend. Личные app data не использовались, код Python/UI/Home/main не менялся. Коммита нет.

## 2026-11-20 — Бэкенд-разработчик: B5, правки карточки и «Не учить»

- Подключил `save_card_edit` и `set_decision` в `tauri_bridge.py` по v4. Частичный патч сохраняет второе поле, пустая строка сбрасывает правку, `skip` исключает слово из нового списка, `null` снимает решение. Для решения сохраняется снимок полки, оценки и версии до изменения. В ответе — пересчитанная карточка, а для решения также сводки полок и списков. Новых полей JSON и миграции нет.
- Импорт и USB-синхронизация возвращают каталог, перечитанный из SQLite после записи. В `vocab_cache.py` и `library_repository.py` при замене старого ID наблюдения на стабильный выбор примера переносится в той же транзакции, если новый пример принадлежит той же карточке. Экспорт по явным ID перечитывает ограничения через существующую политику. Anki и TSV получают перевод и выбранное предложение через существующий `card_fields.resolve`.
- `tests/test_export_words.py`: новый JSON-процесс видит обе правки, ошибки валидации не сохраняют часть патча, `skip` исключает слово даже из старого запроса и снимается через мост, повторный импорт вымышленного KOReader-файла сохраняет правки и решение, `.apkg` и TSV содержат выбранные поля. Целевые проверки: 73 прошли. В первом полном прогоне во время параллельной правки текста причины изменившийся тест ранжирования упал, отдельно прошёл после обновления. Повтор полного прогона: 315 прошли, 1 пропущен. Ruff по списку CI и изменённым тестам, `compileall`, `git diff --check` прошли. В дополнительном lint `vocab_cache.py` есть прежние замечания к импорту и UTC вне списка CI.
- Настоящие Kindle, Anki и UI в этой работе не запускал. Исходный коммит `16b6c0c`, коммит и публикация не выполнялись.

## 2026-11-20 — QA-инженер — Независимая техническая приёмка B5

- Проверил рабочий checkout после регистрации save_card_edit и set_decision в Python-мосте. Временная синтетическая база Kindle содержит три слова и шесть предложений. Прогон через 24 отдельных процесса JSON entrypoint подтвердил правку перевода с нормализацией пробелов, выбор второго предложения, сохранность после перезапуска, повторный импорт без новых слов и контекстов, отказ чужого occurrence без частичной записи нового перевода, skip и снятие решения через null.
- На двух отдельных копиях библиотеки устаревший список IDs включал исключённое слово. TSV и APKG содержат только два разрешённых слова; исправленный русский перевод и выбранное второе предложение совпадают с карточкой. После создания файлов содержимое пакета проверено прямым чтением SQLite.
- Перед APKG появился неизвестный слушатель AnkiConnect на 8765. После согласования ведущего только тестовая обёртка отдельного процесса задала ANKI_CONNECT_URL на проверенный закрытый loopback-порт 9 и вызвала стандартный JSON entrypoint через runpy. Это проверяет штатный fallback-файл. Настройки продукта и личный Anki не изменялись.
- Движок установленного Anki через Collection API импортировал пакет в новую временную коллекцию. Получены две заметки, точные Meaning и Context совпали с пакетом. Повторный импорт сохранил те же ID и число заметок. GUI Anki, живой AnkiConnect и установленный Tauri в этом прогоне не проверялись.
- Полный pytest прошёл: 315 passed, 1 skipped. Ruff по точному списку CI чистый, Vitest 117/117, TypeScript и Vite build прошли. Первый Vitest внутри песочницы остановился на доступе esbuild к родительской папке; повтор вне песочницы успешен. В проверочном скрипте исправлен формат payload save_settings до выполнения финального прогона.
- Дефектов в проверенном сценарии не выявлено. Исходники не редактировал, добавлен только этот раздел журнала. Базовый релизный коммит 16b6c0c; проверенный tauri_bridge.py SHA-256 f1ca5c6e55431e76ab956c9141c08a80462b803a18a157e43a427e0f06553cc3. Коммита и публикации нет.

## 2026-11-20 — Инженер интеграции с Anki — Фактический текст reading_now в mock

- В двух причинах reading_now в src/lib/mock-backend.ts текст изменён на «Из книги с недавними поисками», как согласовано с ведущим. Формулировка описывает наблюдаемый сигнал.
- Проверены существующие mock-backend и home-domain suites: 43 теста прошли. git diff --check прошёл. Реальные данные и приложения не использовались, коммита нет.


## 2026-11-20 — Инженер ранжирования: объяснение недавних поисков

- В production-ранжировании reading_now текст «читаете сейчас» заменён на «Из книги с недавними поисками». Взята та же формулировка, которую выбрали для моков в параллельной работе. Сигнал означает поиск в этой книге за 14 дней до последнего поиска в библиотеке. Вес, код причины и расчёт сохранены.
- Обновлён тест текста в tests/test_ranking.py. Целевые pytest test_ranking и test_library_view: 70 прошли. Ruff для изменённых файлов и git diff --check прошли. Интерфейс и реальные данные в этом прогоне не проверялись. Файлы mock и общие фикстуры контракта не редактировал. Базовый коммит 16b6c0c, нового коммита нет.

## 2026-11-20 — Релиз-инженер — Подготовка внутренней сборки редактора

- По поручению тимлида подготовлены ignored build/internal-card-review и временный Tauri override с identifier com.kindlevocab.cards.preview и явным заголовком внутреннего окна. Финальная сборка приложения ожидает отдельного сигнала «финализировать».
- В существующей Conda kindle_app штатный packaging/build_bridge.py собрал автономный мост. Проверки load_demo, llm_config и process_queue прошли; анализ трёх вымышленных слов совпал с dev-Python. Копия моста сохранена в bridge рядом с будущим EXE. Зафиксированы хеши Python-исходников для проверки необходимости перезаморозки.
- SHA-256 обеих локальных копий публичного NSIS 0.4.0 совпал с опубликованным c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826 и сохранился после заморозки. Исходники и постоянные конфиги не менялись. Запускаемый Tauri EXE и приёмка конечной папки ещё впереди. Коммита нет.
## 2026-11-20 — Инженер ранжирования: тексты причин в фикстурах контракта v4

- Сверил WORKLOG, contracts.py и тесты. bridge_library_v4.json и bridge_library_v4_learning.json — общие вымышленные примеры текущего контракта Python/TypeScript. Отдельный library_v3_golden.json служит снимком миграции. Генератора этих двух примеров в репозитории не найдено.
- Вручную обновил три значения text: оба reading_now приведены к «Из книги с недавними поисками», frequency_common к «очень частое слово». Схема, числа, production и снимок миграции не затронуты.
- Python contract: 24 прошли. Первый Vitest из песочницы остановился при чтении Vite-конфигурации через esbuild; повтор официальной локальной командой вне песочницы: 6 прошли. git diff --check прошёл. Установленная сборка не проверялась. Базовый коммит 16b6c0c, нового коммита нет.

## 2026-11-20 — Фронтенд-разработчик — Редактор карточки и упрощение «Слов»

- По поручению тимлида реализовал `LibraryWorkspace` в выделенной области `src/features/library/`. Два фильтра «Стоит учить» / «Остальные», поиск и книга, виртуализированный список, инспектор с переводом и выбором предложения. Загрузка, повтор обработки и перевода доступны через раскрытие; причины, формы, сведения анализа и все исходные контексты — через «Подробнее о слове».
- Редактор передаёт только изменённые поля, проверяет предел 200 Unicode-символов, позволяет снять ручной перевод и явное решение. Книга всегда берётся из выбранного occurrence; потерянный ID не подменяется другим контекстом. Demo доступно только для просмотра. Ошибка сохраняет ввод. Прямой вход из подборки имеет приоритет перед фильтрами, фокус получает заголовок слова. На узкой ширине редактор заменяет список; возврат восстанавливает фокус строки.
- По замечаниям UI/QA сделал поля прозрачными, сохранил читаемые option; отделил pending от dirty, блокировал возврат и выбор другого слова на время записи. Флаг `onDraftChange` передаёт dirty/pending оболочке, при размонтировании сбрасывается. Фильтр использует ranking.shelf перед legacy decision. Кнопка возврата исходного перевода показана только для ручной правки; подсказка сброса учитывает LLM fallback.
- Файлы: library-workspace.tsx, library-workspace.css, card-editor.tsx, card-editor-domain.ts и два новых тестовых файла. Контроллер, общий bridge и main меняли другие участники. Коммита нет.
- Проверки: сборка TypeScript/Vite и 119 frontend-тестов прошли. Playwright на браузерном mock проверил сохранение, сброс перевода, запрет 201 символа, skip/снятие через «Остальные», возврат фокуса строки и Enter на 600 px, прямой вход из подборки и возврат после skip с одного нажатия без confirm. Снимки 1440 и 600 px сохранены в локальных данных и просмотрены. diff --check для области library прошёл. Сборка в песочнице встретила известный отказ esbuild читать родительский каталог; вне песочницы прошла. Playwright CLI потребовал временный npm cache и загрузку CLI вне песочницы; первые inline run-code команды отклонены парсером, сценарии из файлов прошли.
- Реальный Tauri, SQLite после перезапуска и выгрузка Anki в этой фронтенд-задаче не проверялись. Ошибки записи проверяет отдельная QA-линия; собственный браузерный прогон здесь проверял успешные операции. Итоговое визуальное ревью и сквозную приёмку координирует тимлид.

## 2026-11-20 — Фронтенд-разработчик — Восстановление перевода одного слова

- По точечному поручению тимлида вернул в «Подробнее о слове» перевод одного подходящего слова и повтор неудачного перевода. Действие использует enrichWords с одним ID; условия isCardEligible, llm_enabled, ready/failed сохранены. Demo, занятость, ожидание записи и несохранённый черновик отключают кнопку. Готовые example_en/example_ru показаны отдельно как сгенерированный пример; context_ru не прикрепляется к выбранному альтернативному контексту.
- onDraftChange теперь передаёт отдельные dirty и pending и сбрасывает оба при размонтировании. Изменены только card-editor.tsx, card-editor.test.tsx и library-workspace.tsx.
- Добавлены два регрессионных теста на условия индивидуального действия, disabled, готовые примеры и отсутствие чужого context_ru. Vitest 121/121, сборка TypeScript/Vite и diff --check области library прошли. Реальный LLM-запрос и новый браузерный прогон не выполнялись. Локальный Vite на 1420 остановлен через собственную exec-сессию; порт больше не слушается. Коммита нет.

## 2026-11-20 — Бэкенд-разработчик: цитата, перевод и книга в Anki

- Исправил B5-регрессию в `anki_export.py`: поля заметки и тег `book::` строятся по одному выбранному наблюдению. Для сохранённой копии исчезнувшего примера `card_fields.py` не заимствует автора и книгу у другой цитаты.
- `enrichment.py` и Anki используют порядок исходного запроса: по длине, при равенстве в порядке наблюдений. Новое обогащение сохраняет в существующем JSON отпечаток точной первой цитаты. Для старого prompt v1 перевод возвращается при совпадении с восстанавливаемой цитатой, пока время последнего импорта слова не превышает время обогащения. При неясном источнике или когда модель получила только префикс более длинной цитаты, поле перевода остаётся пустым. Новых сетевых вызовов и миграции нет.
- `test_anki_export.py` проверяет SQLite заметок в `.apkg` с двумя книгами, смену цитаты и возврат к исходной, порядок равных длин и устаревшую запись. `test_enrichment.py` проверяет точный отпечаток запроса и выбор прежней цитаты после появления более длинного примера. 72 целевых теста и полный прогон (317 прошли, 1 пропущен), Ruff для изменённых файлов, `compileall`, `git diff --check` прошли.
- Ручной интерфейс Anki и замороженный мост не запускал. Базовый коммит `16b6c0c`, коммит и публикация не выполнялись.

## 2026-11-20 — Релиз-инженер — Финальная внутренняя сборка редактора

- После сигнала готовности Anki-полей повторно заморожен штатный Python-мост, собран свежий production-фронтенд и оптимизированный Tauri EXE. Автономная папка build/internal-card-review содержит kindle-cards.exe и bridge/kindle-bridge.exe с ресурсами. Временный override задаёт com.kindlevocab.cards.preview, явный внутренний заголовок и minWidth 600. Использован CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_DEBUG=true.
- Сборка esbuild в песочнице получила отказ чтения родительской папки; та же Tauri-команда с расширенным доступом успешно завершилась. Постоянные конфиги и продуктовые исходники релиз-инженер не изменял.
- Хеши всех входных файлов Python, frontend и оболочки совпали до и после сборки и smoke; хеши dist после Vite, окончания Cargo и smoke также совпали. Smoke из конечной автономной папки проверил load_demo, llm_config, process_queue на вымышленной библиотеке; анализ трёх слов совпал с dev-Python. Обе локальные копии публичного NSIS 0.4.0 сохранили исходный SHA-256.
- SHA-256 kindle-cards.exe: 72193879243ae134fb7d0c0058ea4566f3a7ec07b2fc2bdbcd1d5a35422c997d. SHA-256 bridge/kindle-bridge.exe: eec5b01decedd33e050581db3c101d8fd629d1843dee6fa938cbc41dba28d61d. Контрольные суммы сохранены в SHA256SUMS.txt рядом с EXE.
- Проверку native UI на отдельной библиотеке выполняет тимлид. Установка, публикация и запуск публичных workflow не выполнялись. Коммита нет.
## 2026-11-20 — Релиз-инженер — Перезаморозка UTF-8 исправления

- По сигналу тимлида перезаморожен мост после изменений tauri_bridge.py и build_bridge.py. Исходные файлы сохранили хеши на протяжении сборки и проверки. Обновлена только конечная папка bridge внутреннего приложения и локальные контрольные суммы.
- Обновлённый штатный smoke и verify_final.py на конечной копии проверили load_demo, llm_config, process_queue и русскую правку save_card_edit с ensure_ascii=False. Отдельный запуск load_library подтвердил сохранность русского текста после перезапуска. verify_final.py динамически загрузил актуальный smoke и вывел UTF-8 preserved after restart.
- SHA-256 bridge/kindle-bridge.exe: bacb63c4709784b95c9d7322096d799be7877b06e4966e4b0df3a3785739941c. Оболочка сохранила 72193879243ae134fb7d0c0058ea4566f3a7ec07b2fc2bdbcd1d5a35422c997d. Обе локальные копии публичного NSIS сохранили исходный SHA-256. Проверку native UI продолжает тимлид. Коммита и публикации нет.
## 2026-11-20 — Тимлид — Внутренняя сборка для проверки подборки и карточек

- По решению владельца отложили внешний набор. На планёрке согласовали единый сценарий для внутреннего просмотра. С Главной открывается конкретное слово, читатель может поправить перевод, выбрать исходную цитату или исключить слово из будущих порций. После возврата фокус восстанавливается. В «Словах» появились две полки, отдельный вид карточки для узкого окна и защита черновика.
- Изменения затронули home, library, оболочку React, bridge, SQLite, поля Anki и TSV, обработку причин ранжирования и упаковку. Запись решения и правок проверена после нового импорта. Команда устранила несоответствие между выбранной цитатой, её переводом и тегом книги в Anki. Восемь синтетических срезов дали прежние AUC 0,652, lift@20 2,91 и lift@50 1,99. Весовые коэффициенты сохранены. Пригодность порядка для владельца на его книгах предстоит проверить.
- Проверил оба размера окна в браузере, ошибку записи с сохранением ввода и возврат с клавиатуры. В ходе проверки устранили ложное предупреждение при выходе после исключения слова и непрозрачные поля редактора. Независимая QA-проверка охватила 24 отдельных процесса моста, повторный импорт, TSV и реальный импорт APKG движком Anki во временную коллекцию без дублей.
- В настоящем Windows-приложении воспроизвёл порчу кириллицы в замороженном Python. Исправил чтение stdin в UTF-8 и добавил проверку сохранения и перечитывания через два процесса в обычные тесты и в проверку сборки. После пересборки два запуска WebView2 с одной вымышленной библиотекой подтвердили русский текст, точную цитату, работу при ширине 600, возврат фокуса, замену исключённого слова в пятёрке и точные поля готового TSV.
- Итоговые проверки прошли. Python — 318 тестов и один пропуск, Vitest — 121 тест, production-сборка Vite, Ruff в объёме CI, git diff --check и упаковочная проверка кириллицы. Полный дополнительный Ruff показывает те же 49 замечаний, что и базовый коммит.
- Исходники сохранены локальным коммитом 6e4360c ветки codex/card-review на базе 16b6c0c. Внутренняя сборка лежит в build/internal-card-review, использует отдельный каталог данных и запускается без установки. Сверены контрольные суммы оболочки, обновлённого моста и публичного установщика 0.4.0. Публикацию и внешние сессии отложили до решения владельца.

## 2026-11-23 — Фронтенд-разработчик — Подготовка подборки на Главной

- По согласованному поручению изменены только home-view.tsx, home.css и home-view.test.tsx. Добавлен обязательный processingProgress из home-domain, три фазы waiting/processing/finishing. До первой порции заголовок «Готовлю подборку», объяснение автоматического появления подборки и реальный native progress при известном total. Числа не входят в live-регион; неопределённая индикация поддерживает reduced-motion.
- При уже готовой порции список остаётся на экране, компактный прогресс стоит у заголовка, причина блокировки связана с экспортной кнопкой через aria-describedby. Существующие сообщения об ошибке/результате выгрузки и доступ к папке сохранены. В preparing скрыта строка повторного импорта. Для подготовки ограничена ширина и выровнена по высоте сцена, размер хоста вмещает рисунок лампы. Под 680 скрываются все её слои вместе с pool.
- Добавлены три регрессионных теста и обновлена проверка заголовка подготовки. 19 view-тестов, TypeScript, production Vite и diff --check назначенных файлов прошли. Данные подключает тимлид, native сборку выполняет релиз-инженер. Код передан тимлиду для визуальной проверки. В этом прогоне браузерные снимки и native UI ещё не проверены. Коммита нет.

## 2026-11-23 — QA-инженер — Восстановление после ошибки ожидания

- Независимо проверил браузерный маршрут cold-start-error на Vite ведущего, порт 1433, Chromium Playwright, 1280×850. Browser plugin отсутствует. После ошибки видны «Обработка слов остановилась», доступная кнопка продолжения и причина в подвале. «Слова» и «Настройки» открываются, подвал сохраняется, в Настройках доступен повтор операции.
- После возврата на Главную кнопка «Продолжить обработку» достигнута последовательными Tab и нажата Enter. Показано «Готовлю подборку», затем готовый список из трёх слов и доступная выгрузка; сообщение остановки исчезло. Просмотрены снимки ошибки, продолжения и итогового списка.
- В штатном mock slow готовая подборка остаётся видимой во время обработки. Выгрузка disabled, её aria-describedby указывает на пояснение ожидания. Соседние вкладки доступны. После завершения и возврата на Главную выгрузка снова активна. Снимок этого состояния просмотрен, ошибок console/pageerror и Vite overlay в финальном прогоне нет.
- Исходники не менял. Дефектов проверенного маршрута не выявил. QA-скрипты и снимки сохранены во временном каталоге. Первый запуск Chromium остановился на запрете папки daemon в песочнице; повтор вне песочницы прошёл. В проверочном скрипте уточнил фактический заголовок Настроек после первого неверного ожидания текста.
- Размеры, ночь/день, настоящее число 649 и нативное окно проверяет ведущий. В этой задаче не запускал физические устройства, установщик и дополнительные тестовые suites. Собственная сессия qa-waiting закрыта, Vite ведущего оставлен работающим. Коммита нет.

## 2026-11-23 — QA приёмки — Изолированная очередь в прежнем native EXE

- Подготовлен временный драйвер с синтетической библиотекой из 15 pending слов. Тестовый прокси отвечает disconnected на connector_status и пропускает только load_library, load_settings, process_queue и export_folder_status в штатный frozen bridge; все остальные действия блокируются. Проектные исходники не менялись.
- По исходникам load_library отключает сверку Kindle, process_queue обрабатывает каталог SQLite и локальный анализ. Базовый EXE открыл WebView2 с временными workspace и профилем, показал подготовку и дошёл до доступной кнопки экспорта. Снимок старой сборки сохранён во временном каталоге. Читалка и данные владельца не использовались.
- Проверка выполнялась в отдельном запущенном тестом процессе, который завершён. Видимый счётчик новой сборки, лампа и полная визуальная сверка ждут новый EXE. Коммита нет.

## 2026-11-23 — Фронтенд-разработчик — Лампа в короткой и узкой сцене

- По результатам визуального прогона тимлида уменьшил обычную настольную лампу до масштаба .56 при высоте стола 340px, а в среднем контейнере до .5. Подготовительная широкая сцена сохраняет .7/440px. Положение луча и рисунка масштабируется общей переменной.
- В preparing до 680px компактная лампа .4 возвращена справа с местом для текста. До 420px рисунок поднимается выше текста, рисунок, beam, pool, bloom и настольный свет используют общий уровень основания 204px. Пояснение и счётчик занимают полную ширину; motes скрыты. Сокращён отрыв линии от содержимого.
- Подпись чисел теперь «Обработано X из Y», aria-valuetext уточняет «Обработано слов X из Y», тысячи группируются по ru-RU. Добавлен один постоянный polite-регион фазового объявления, числовые обновления остаются вне него. Тест подтверждает одинаковое объявление при смене current и корректный случай 1 из 1.
- 20 view-тестов, TypeScript, production-сборка Vite и diff --check прошли. Первое применение patch остановилось с частично записанными hunks; содержимое сверено, оставшиеся правки применены последовательно. Область передана тимлиду для повторного visual на узком экране и проверки готовой/пустой Главной. Собственный browser/native прогон не выполнялся. Коммита нет.

## 2026-11-23 — Релиз-инженер — Переносная сборка новой Главной

- После сигнала тимлида собраны свежие frontend и оптимизированная оболочка из базы 6e4360c и текущих правок. Автономная папка build/internal-card-review-2026-11-23 использует прежний com.kindlevocab.cards.preview, внутренний заголовок и minWidth 600. Путь передан тимлиду для QA сразу после копирования EXE и моста.
- Мост скопирован без перезаморозки, все его файлы побайтно сверены по SHA-256 с предыдущей автономной папкой. Исходники Python и упаковки относительно 6e4360c не менялись. Сигнатуры входных файлов совпали до и после сборки, dist сохранился после упаковки и smoke. Предыдущий EXE сохранил свой хеш.
- verify_final.py адаптирован к новой папке. Первый запуск ещё использовал прежний путь, после исправления выполнен повторный smoke именно новой копии. load_demo, llm_config, process_queue и сохранение русской правки после перезапуска прошли. Публичный NSIS 0.4.0 сохранил исходный SHA-256.
- SHA-256 нового kindle-cards.exe: 872060308eed2dcb1606f3290ec0ac8f5ad7447e44a8a3a5f6aeaf5a5814518c. Мост: bacb63c4709784b95c9d7322096d799be7877b06e4966e4b0df3a3785739941c. Итоги сохранены в SHA256SUMS.txt. Native UI проверяет QA. Продуктовые исходники не редактировались, коммита и публикации нет.
## 2026-11-23 — QA приёмки — Native счётчик обработки

- В отдельном WebView2 проверена внутренняя сборка с временной библиотекой из 15 синтетических pending-слов. Прокси блокировал обнаружение и импорт читалки, разрешённые действия передавались штатному frozen bridge. Процесс теста завершён, пользовательская библиотека и работающий экземпляр не затронуты.
- История progress: 0, 1, 2, 3, 8–14 при постоянном max 15; после обработки доступна кнопка экспорта. Заголовок «Готовлю подборку», одна полоса, подвал во время подготовки скрыт. В viewport 1320×840 лампа целиком в пределах сцены, снимок просмотрен.
- Два старта тестового драйвера остановились до проверки из-за навигации WebView, третий выявил отсутствие скрытого подвала; ожидание страницы и обработка отсутствия подвала исправлены в временном драйвере. Эксперимент из 80 вымышленных слов прерван при ожидании экспорта: фикстура не гарантировала пригодные слова. Финальный прогон с обычными словами прошёл. Исходники не менялись; коммита нет.

## 2026-11-23 — Тимлид — Подготовка подборки в окне Windows

- После двух раундов с продактом и UX-дизайнером приняли один вид подготовки с текущим действием и настоящим ходом очереди. План в docs/plan/meetings.md. В первом импорте Главная центрирует заголовок, пояснение и индикатор под настольной лампой. При повторном импорте текущая порция остаётся видимой. Обрабатывается именно текущая очередь. До подтверждения её размера и при перечитывании итогового рейтинга показаны отдельные фазы.
- Подключил события операции к HomeScreen и убрал дублирующий статус на Главной. Состояния соседних экранов и возможность повторить после ошибки проверены. HomeView, стили, разметка для чтения с экрана и тесты реализовал фронтенд-разработчик. После визуального ревью на 600 px вернули целую компактную лампу. Отдельно устранена обрезка плафона во время обработки при уже готовой порции. Рецензент принял широкую и узкую сцены после повторного просмотра.
- В Playwright воспроизвёл исходные 649 из 1820 и последующее изменение до 1083, ожидание, получение подборки и вариант с готовыми словами. Визуальная проверка при ширинах 390, 600, 1280, 1440, 1628 и 2442 CSS-пикселя, в дневной и ночной темах. Перепроверил границы плафона, доступный progressbar, отсутствие горизонтального скролла и ошибок консоли. Первый прогон нашёл плафон на 12 пикселей выше границы; повтор прошёл. QA отдельно проверил ошибку и повтор с клавиатуры. Проверки прошли — 128 тестов Vitest, 318 Python и 1 пропуск, production-сборка, git diff --check.
- В нативном WebView2 на временных 15 словах штатный замороженный мост передавал реальные значения очереди. Проверены изменение счётчика с неизменным максимумом, один видимый индикатор, целая лампа при 1320×840 и доступный экспорт после появления списка. Доступ к устройству был отключён тестовым прокси. Личный импорт владельца во время этого прогона не воспроизводили.
- Локальный коммит 4a96284 в ветке codex/card-review. Сборка лежит в build/internal-card-review-2026-11-23, с прежним внутренним идентификатором и библиотекой. Открытый владельцем экземпляр сохранён. Релиз-инженер сверил контрольные суммы и проверил конечную папку. Вид подтверждён для Windows, внешней публикации не было.

## 2026-11-23 — Фронтенд-разработчик — Два раунда обсуждения живой лампы

- Исследовал существующие DeskLamp, HomeView, CSS света, адаптивные сцены и обработчики. Рисунок и свет разделены на слои с общим масштабом и независимыми координатами; текущая лампа не интерактивна. Framer Motion уже установлен, готового popover-компонента нет. Предложил сначала CSS-реакции света с остановкой при скрытии окна, без покадровых React-обновлений; шарнирное движение требует общей модели геометрии.
- Для согласуемого MVP с ушками предложил состояния gaze rest/peek, motion off/quiet и управляемое bubbleOpen с onOpenBubble. Оглядывание выражается наклоном ушек при неподвижном якоре плафона и света. Открытие облачка — добровольное действие отдельной кнопки, состояние движения учитывает reduced-motion. Автоматическое открытие и полноценную артикуляцию плафона предложил отложить.
- Критерии проверки: исходная и компактная сцены на 390/600/1440 px, день/ночь, общая привязка ушек и hit-target, отсутствие перекрытия текста, клавиатура/Escape/возврат фокуса, остановка idle вне видимой области и при скрытом окне. Код, ассеты и зависимости не менялись; браузерные измерения и тесты прототипа не выполнялись. Окончательное решение и протокол ведёт тимлид. Коммита нет.

## 2026-11-23 — Тимлид — Концепция лампы-маскота

- В постоянных чатах с продактом, UX- и UI-дизайнерами и фронтенд-разработчиком провёл два раунда. Сверили текущий DeskLamp, рисунок и отдельные координаты луча, правила доступности и компактный вид после исправления Главной. Продакт выбрал любопытный характер. UI предложил выразить первую реакцию ушком, UX — добровольное приветствие и закрываемое облачко. Обсудили цену сложного движения плафона и отвлекающих повторов.
- Предложил внутренний эскиз с двумя металлическими ушками в сравнении с глазом-заклёпкой. Через imagegen получен и визуально просмотрен лист на основе скриншота с вымышленными данными. Сохранил docs/concept/lamp-mascot-study.png и протокол в docs/plan/meetings.md. Уточнил подходящие локальные навыки и проверил авторские animate и review-animations по первоисточнику. Установок не выполняли.
- Зафиксировали жест простоя, взгляд, реакцию на появление списка, текст по нажатию, клавиатуру и тихий вариант. План применяет состояния текущего интерфейса. Нужны выбор владельца и проверка размеров и движения на прототипе. Готовность маскота и влияние на повторное использование пока не проверены. База 4a96284, программных изменений, сборки, коммита и публикации нет.

## 2026-11-23 — Релиз-инженер — Скрипт автономной сцены лампы

- Создан packaging/build_lamp_study.mjs с отдельным Vite JS API без загрузки общего конфига. Сборка выполняется в памяти, объединяет JS, встраивает CSS и ресурсы и пишет только build/lamp-study/index.html. Добавлена проверка остаточных ссылок на внешние ресурсы. Новых зависимостей нет.
- node --check и diff --check прошли. Входные HTML и TSX сцены на момент проверки отсутствуют, поэтому сборка и file:// проверка ожидают готовности кода тимлида. Сигнал о готовности скрипта передан в чат тимлида. Обычная сборка приложения не запускалась, коммита нет.
## 2026-11-23 — Фронтенд-разработчик — Переиспользуемая лампа-маскот

- По одобренному левому эскизу добавил безопасный opt-in mascot в DeskLamp. Родной SVG получил два асимметричных металлических ушка с тёмными сгибами, прищур и более округлое тело; исходные рот света, конус и координаты источника сохранены. Обычный DeskLamp сохраняет прежний рисунок.
- Новый MascotLamp принимает phase preparing/ready и motion. Возвращает фрагмент для home-desk.lamp-host. Кнопка 44px у головы открывает закрываемую бумажную реплику для текущей фазы, поддерживает повторное приветствие, Escape, закрытие снаружи и возврат фокуса при закрытии из облачка. Само открытие не перемещает фокус.
- Одно ушко двигается через Web Animations API, 850мс. Idle один раз после 25 секунд видимого preparing, остаток ожидания сохраняется при паузе; число обработанных слов не является зависимостью. Переход preparing→ready даёт один жест. IntersectionObserver, visibilitychange, ResizeObserver и системный reduced-motion управляют активностью, очистка отменяет таймеры, наблюдатели и анимацию. motion=false отключает жесты и прежние пыль/прогрев; приветствие доступно.
- В собственном CSS кнопка/облачко используют --lamp-s и компактный уровень основания. Для lamp-study на600 зарезервирован карман208px, в самом узком preparing облачко находится выше текста. Кнопка скрывается вместе с обычным скрытым рисунком. Родитель подключает сцену, slot и контролы.
- Файлы: lamps.tsx, новые mascot-lamp.tsx, mascot-lamp.css, mascot-lamp.test.tsx. Два локальных теста и общий Vitest 130/130 прошли, TypeScript/Vite сборка и diff --check прошли. Визуальное соответствие реальному размеру, геометрию открытого облачка, WebView2 и таймеры в браузере ещё предстоит проверить на подключённом стенде тимлида. Исходники за пределами выделенной области не менял, коммита нет.

## 2026-11-23 — Фронтенд-разработчик — Toggle приветствия и скрытая лампа

- Исправил повторное нажатие click/Enter на переключение открытия и закрытия облачка по принятому плану. Проверка фактической видимости рисунка и hit-target выполняется после смены phase, при resize и наблюдении хоста. Когда рисунок скрыт, открытая реплика удаляется; фокус с скрываемой головы или содержимого облачка переносится на заголовок Home. При возвращении ширины облачко остаётся закрытым.
- Самостоятельно проверил стенд через Playwright. Click/Enter toggle и Escape с возвратом фокуса прошли. На600 подготовка с открытым облачком перешла в ready без висящей реплики и скрытого фокуса, расширение до1440 ничего не восстановило. Просмотрел снимки600 и1440, дневную и ночную темы. Ушки читаются по силуэту, реплика на600 не перекрывает прогресс. Прищур сдвинут на бок плафона и усилен, чтобы выходить из светового ореола.
- Два локальных теста, TypeScript/Vite и diff --check прошли. Первый сценарий после автоматического завершения подготовки не нашёл скрытый target600; сценарий исправлен явным перезапуском подготовки и прошёл. В консоли стенда единственный404 favicon.ico, исключений приложения нет. Idle25s, native WebView2 и все комбинации reduced-motion отдельным браузерным прогоном в этой правке не проверял. Коммита нет.

## 2026-11-23 — Релиз-инженер — Первый автономный HTML маскота

- Скрипт собрал build/lamp-study/index.html размером 1 585 416 байт. Исправлено ложное срабатывание CSS-проверки на JS: url теперь анализируются только внутри style. Шрифты, JS и CSS встроены; зависимости общего приложения не менялись.
- По прямой просьбе владельца установлен Playwright CLI в ignored build/lamp-study-tools. Запуск потребовал расширенного доступа к служебному каталогу и отдельного тестового разрешения file-протокола. Встроенное управление Chrome ранее не получило разрешение.
- Через file:// и с offline network проверены загрузка, счётчик, открытие реплики и переход к подборке. В журнале запросов только два чтения самого HTML, ошибок и предупреждений консоли нет. Снимок сохранён в ignored build/lamp-study/first-offline.png и просмотрен. Сцена использует синтетическую JSON-фикстуру, сетевых импортов во входном TSX не найдено.
- SHA-256 первого HTML 102c643a012445b258e1539feea977bdd989985f53fd8307f1d64bcb4fa16691. node --check и diff --check прошли. Итоговый повтор сборки ожидает правок QA. Коммита и публикации нет.
## 2026-11-23 — Фронтенд-разработчик — Узкое облачко и повторные циклы

- Исправил геометрию облачка до420px: его правый край отступает от головы по той же координате430×scale, хвостик смотрит вправо к плафону. Постоянная окружность expanded удалена, клавиатурный focus сохранён. Карман600 не менялся.
- Новый переход ready→preparing сбрасывает idleRemaining к25 секундам и idleDone. Переход в ready при отключённом движении не сохраняет отложенный жест; выключение движения также очищает readyPending.
- В Playwright на390 и360 проверил фактический elementFromPoint в центре головы при открытой реплике и отсутствие пересечения bubble с44px target. Второй pointer-click по голове закрыл облачко в обоих размерах. Снимки просмотрены. Отдельно600: облачко и progress не пересекаются, повторный click работает.
- Через часы Playwright и счётчик реальных вызовов animate проверил первый idle после25 секунд, новый idle через25 секунд после повторного цикла и отсутствие жеста ready после60 секунд ожидания с движением off и последующего включения. Два component-теста, TypeScript/Vite и diff --check прошли. Native и автономный HTML после этой правки не проверял, коммита нет.

## 2026-11-23 — Релиз-инженер — Финальная автономная сцена маскота

- После сигнала владельца повторно собран build/lamp-study/index.html из обновлённых входных файлов. Итог — 1 586 266 байт.
- В Playwright файл открылся через file:// при отключённой сети. Статус и интерфейс присутствуют, журнал показывает только чтение самого HTML; ошибок и предупреждений консоли нет. Проверен production файл после правок шапки, favicon и статуса TSV.
- SHA-256: 42b2567b60bc1b0d1cc9b993e8008a9279cb8cc240eb1b623f2487301e4a018b. Других файлов проекта не менял. Сборка общего приложения и публикация не выполнялись. Коммита нет.
## 2026-11-23 — QA-инженер — Функциональная приёмка пробы маскота

- Проверил Vite-сцену на 1435 и окончательный автономный build/lamp-study/index.html, SHA-256 42b2567b60bc1b0d1cc9b993e8008a9279cb8cc240eb1b623f2487301e4a018b. Chromium Playwright CLI, 1440×900 и 600×900, вымышленные слова контрактной фикстуры. Browser plugin отсутствует, артефакты и скрипты сохранены во временном каталоге.
- Пройдены click/repeat-click, настоящий Tab до головы, Enter, Space, Escape, видимое закрытие и возврат фокуса, переключение темы и движений с aria-pressed. После закрытия доступна карточка ephemeral и выбор второго предложения. При узкой сцене скрытые кнопка/облачко исчезают из Tab; фокус с головы переносится на home-title.
- На финальном HTML без ускорения таймеров зарегистрирован один idle-жест через 25,12 с. До этого счётчик дошёл 7/10 без жестов на каждое число. Переход к подборке дал один ready-жест, дальнейшего повтора и автоматических реплик не было. Reduced-motion сохраняет приветствие и исключает ear.animate при фокусе, нажатии и готовности.
- Ветка visibilitychange проверена отдельно с моделируемыми document.hidden и visibilityState: за 27 реальных секунд жестов 0, счётчик не менялся; готовность в скрытом состоянии не двигала ушко, возврат видимости вызвал один отложенный жест. Настоящее скрытие вкладки headless Chromium не подтвердилось при переключении foreground на вторую вкладку, поэтому результат этой проверки ограничен моделированием состояния.
- Финальный file:// прогон при отключённой сети прошёл, HTTP-запросов 0, ошибок JavaScript не обнаружено. Просмотрены снимки ожидания и узкой реплики. В dev-прогонах отмечены favicon 404 и предупреждение повторного createRoot при HMR; финальный автономный файл этих сообщений не выдавал.
- Предварительное расхождение повторного клика передано ведущему и исправлено владельцем области до окончательной проверки. Первый timing-прогон затронут HMR, повторный наблюдатель задвоил записи в QA-скрипте; чистая сессия дала указанные единичные жесты. Исправлено QA-ожидание скрытого role-локатора, зависший npm-вызов остановлен, дальнейшие команды шли через уже загруженный CLI.
- Продуктовые исходники не редактировал, изменён только этот раздел WORKLOG. Обе собственные браузерные сессии закрыты. Внешний вид и TSV отдельно проверяет ведущий. Нативное приложение, устройства и личные данные не использовались. Коммита и публикации нет.

## 2026-11-23 — Фронтенд-разработчик — Прищур и положение облачка

- По двум блокирующим замечаниям UI-дизайнера расширил прищур до одного плавного штриха, усилил контраст и освободил от штриховки бумажное поле на боку плафона. Поле и прищур нарисованы после halo, сохраняя исходные координаты источника света.
- В контейнере421–680 облачко поднято над головой и стойкой, хвост направлен вниз к плафону. В широком виде хвост привязан к координате317×scale вместо доли ширины облачка. Геометрия до420 сохранена. Изменены только lamps.tsx и mascot-lamp.css.
- Самостоятельно снял и просмотрел600 день и1440 ночь на локальном стенде. Прищур виден в обеих темах; bbox-проверка600 подтвердила, что нижний край облачка выше44px кнопки головы. Два component-теста, TypeScript/Vite и diff --check прошли. Остальные сценарии поведения не изменялись; native и новый автономный HTML не проверялись. Коммита нет.

## 2026-11-23 — Релиз-инженер — Пользовательская версия сцены маскота

- После последних визуальных правок очищенного прищура и стойки повторно собран автономный build/lamp-study/index.html.
- Открытие через file:// при offline прошло. В журнале запросов только HTML, консоль без ошибок и предупреждений. Размер 1 586 751 байт.
- SHA-256: 89e011f93d38a8013f805f2a81aca8b1d791f3cf80cff8aae79131e97bae55e7. Исходники проекта не редактировал. Коммит и публикация не выполнялись.
## 2026-11-23 — Тимлид — Автономная проба ушастой лампы

- Владелец предпочёл левый эскиз. На той же Главной собрана отдельная локальная сцена с вымышленными данными, доступным приветствием, ожиданием и готовой подборкой. Основная сборка использует штатную лампу. Контракт бэкенда, личная библиотека и установленный EXE не затронуты.
- Изменения интеграции в home-view.tsx, исходная страница в docs/concept/lamp-study.html, сцена и стили в src/preview/. Исходники компонентов, сборщика и сценария сохранены в локальном коммите 0a23b6d. Решение по выбору и итог рецензии добавлены в протокол планёрки.
- По визуальному ревью освободили поле вокруг прищура, изменили положение облачка на 600 px и вернули доступ к плафону при открытой реплике на 360 и 390 px. UI-дизайнер повторно подтвердил читаемость при дневном и ночном освещении. Проверил финальную геометрию и доступность закрытия на 421×620, 600×480 и 680×550.
- Итоговый HTML в build/lamp-study/index.html. Проверил работу без сети, клавиатуру, закрытие и возврат фокуса, обе темы и экспорт трёх строк TSV с выбранным вторым предложением. 130 тестов интерфейса и сборка TypeScript/Vite прошли, git diff --cached --check чист. Просмотрены снимки финальной сцены.
- Первые прогоны Playwright не переводили страницу в реальное фоновое состояние. Повторил в отдельном видимом окне Edge с двумя обычными вкладками и чистым профилем, без эмуляции фокуса. Зарегистрированы реальные переходы hidden и visible. За 26 секунд в фоне не появилось жестов и не изменился прогресс, при возвращении счётчик возобновился. Тем самым закрыто ограничение первоначального отчёта QA.
- Итогом этапа служит автономный прототип для оценки владельцем. Интерес читателей и уместность поведения в ежедневной работе ещё не оценивали.

## 2026-11-23 — Тимлид — Четыре образа лампы на Главной

После отзыва владельца подготовил четыре отдельных статичных макета встроенным ImageGen на основе одного настоящего снимка подготовки слов. Сохранил изображения в docs/concept/lamp-characters. Зимородок освещает стол из-под клюва, керамический гриб из-под широкой шляпки, у механического светлячка источник света в загнутом янтарном брюшке, у маленького смотрителя над глазами бумажный абажур. На четырёх PNG проверены положение персонажей, свободная область текста и видимость прогресса. UX-дизайнер определил условия сравнения. UI-дизайнер дополнительно просмотрел птицу, гриб и смотрителя. Выбор владельца открыт. Это изображения широкого окна в ночной теме. Код приложения, анимации и сборку в этом цикле не меняли.

## 2026-11-23 — Тимлид — Лис с фонарём

По выбору владельца переработал образ смотрителя в антропоморфного лиса. Ориентир для силуэта и светлых глаз — герой Limbo. Сгенерировал статичный ночной экран в ImageGen, проверил видимость хвоста, ушей, фонаря в лапе и счётчика. Макет сохранён в docs/concept/lamp-characters/05-fox-lantern.png и сверен по SHA-256. Образ передан на выбор владельцу.

## 2026-11-23 — Релиз-инженер — Предварительная проверка fox preview

- Прочитан текущий WORKLOG. В существующей папке внутренней сборки доступен замороженный bridge/kindle-bridge.exe; Python 3.11.15, Cargo 1.96.1 и Node v26.4.0 доступны через Conda kindle_app. Предыдущий процесс kindle-cards сейчас не запущен.
- Новая папка build/internal-fox-preview не создана до сигнала финального рендера. Preview ID остаётся com.kindlevocab.cards.preview. Проверены только исполняемые версии и существование артефакта, bridge запускать не потребовалось. Продуктовые исходники не менялись. Коммита и публикации нет.
## 2026-11-23 — QA-инженер — Лис на Главной и в автономной пробе

- Независимо проверил настоящую браузерную Главную с cold-start на Vite 1436 и build/fox-lantern/index.html. Финальный проверенный HTML SHA-256 e6bfe4d697714262eb3600bc96c75fd3b41aee32c4c078d925758a763cd19ce7. Chromium Playwright CLI, синтетический mock/контрактная фикстура. Browser plugin отсутствует, применён прежний отдельный CLI, скрипты и снимки во временном каталоге.
- Главная: 1440×900 ночью и 600×900 днём с reduced-motion. Кнопка «Поприветствовать лиса» работает через click/toggle, Enter и Space, Escape и видимое закрытие возвращают фокус. До обращения автоматической реплики нет. При штатном окончании mock-обработки лис и реплика размонтируются, фокус из кнопки закрытия переходит на home-title. После этого штатный mock-export успешно завершается.
- Автономная проба: offline file://, 0 HTTP-запросов, 1440 и600 в дневной и ночной темах. Настоящий Tab достигает приветствия, Enter/Space открывают, Escape/внешний click/повторный click закрывают реплику. Проверены переключатель движения и aria-pressed, отсутствие анимации глаз при reduced-motion и при отключённом движении. При готовности сцена исчезает с переносом фокуса на заголовок, экспорт запускает загрузку TSV.
- Консоль без ошибок, pageerror отсутствуют, горизонтального переполнения нет. Два дневных снимка просмотрены. Собственная браузерная сессия qa-fox закрыта; Vite ведущего не останавливал.
- Продуктовые исходники не менял. Нативный EXE, настоящий bridge/Anki, устройства, личная библиотека и качество нового изображения не входили в эту проверку. Пригодность внешности отдельно оценивают ведущий и UI-дизайнер. Добавлен только этот раздел WORKLOG, коммита и публикации нет.

## 2026-11-23 — Фронтенд-разработчик — Интерактивный FoxLantern

- В выделенной области создал только fox-lantern.tsx и fox-lantern.css. FoxLantern принимает необязательный motion, использует отдельный FoxFigure тимлида и предназначен для preparing. На широком экране лис справа с зарезервированным местом для текста, до520px — ниже текста справа. Текст и прогресс имеют полную ширину в узкой сцене. Масштаб рисунка привязан к viewBox500×450.
- Кнопка44px совпадает со стеклом по10%/74% сцены, открывает добровольную реплику «Я посвечу.», повторный click/Enter закрывает её. Escape, outside и Закрыть поддерживают фокус. При размонтировании с фокусом внутри сцены layout-cleanup передаёт фокус следующему home-title через microtask только если другой живой control ещё не получил фокус. Изоморфный выбор useEffect для SSR устранил предупреждение; браузер сохраняет layout-cleanup.
- Редкое мягкое моргание группы fox-eyes через CSS с периодом18секунд. IntersectionObserver и visibilitychange приостанавливают его вне видимой области и в фоне. motion=false и системный reduced-motion отключают анимацию. Таймеров подсказок, смены состояния и покадрового React-state нет.
- По просмотру собственных снимков и замечанию тимлида реплика перенесена вправо от лица над хвостом, хвостик направлен влево к лису; на600 текст короткой реплики переносится на2строки. Вся сцена с hit-target сдвинута вниз на1.333333% высоты, чтобы ступни y444 из450 совпали с линией стола.
- Проверки:130 frontend-тестов без SSR-предупреждения, TypeScript/Vite и diff --check прошли. На стенде1436 Playwright проверил360/390/600/1440, точное положение кнопки на стекле, отсутствие коллизий реплики с прогрессом и глазами, pointertoggle, Enter/Escape с возвратом фокуса, размонтирование из реплики с фокусом на следующем заголовке, motionoff и systemreduce. Финальные снимки четырёх размеров просмотрены. Один повтор геометрии встретил уже завершившееся ожидание; после нового запуска подготовки прошёл. Ошибок приложения в консоли нет.
- Реальное переключение вкладок в фоне, моргание в native WebView2, дневную тему и финальный автономный HTML в этом прогоне не проверял; их проверяет основная QA-линия. FoxFigure, Home и стенд менял тимлид. Коммита нет.

## 2026-11-23 — QA-инженер — Финальный HTML лиса на 600px

- Коротко повторил независимую offline file:// проверку build/fox-lantern/index.html с SHA-256 beaa05c68fda3ff8df50eb33f41844d6f0a0a0e46d558d35c081b4f1b9fa5f40 после визуального ревью.
- При 600×900 нажатие мышью в центр кнопки на фонаре открывает реплику. Bounding boxes подтверждают отсутствие перекрытия репликой глаз и прогресса, горизонтального переполнения нет. Дневной и ночной снимки с открытой репликой просмотрены: лицо и счётчик видны.
- Escape закрывает реплику, переход к подборке и скачивание kindle-cards-example.tsv прошли. HTTP-запросов при отключённой сети 0, ошибок JavaScript нет. Собственная qa-fox-final сессия закрыта, исходники не редактировал, коммита нет.

### 2026-11-23 — изолированная native-приёмка fox preview
- Цель: проверить Главную и приветствие лиса во время обработки на переносной внутренней сборке.
- В отдельном временном профиле подготовлены 15 вымышленных слов; прокси запрещал доступ к читалкам и передавал разрешённые действия штатному bridge. Личная библиотека и открытое приложение не использовались.
- Native WebView2: наблюдались значения очереди 0, 1, 2, 7, 8, 9, 10, 11 при постоянном максимуме 15; кнопка приветствия доступна, Enter показывает реплику, после обработки видны список и экспорт. Ошибок страницы не обнаружено. Сохранены снимки подготовки и приветствия.
- Исходники не менялись, коммит не создавался. Реальное устройство и пользовательская библиотека в этом прогоне не проверялись.

## 2026-11-23 — Релиз-инженер — Переносной Fox preview

- По сигналу владельца пересобран production dist командой npm run build, затем собрана оптимизированная Tauri оболочка без bundle/установщика в build/internal-fox-preview. Использован прежний preview ID com.kindlevocab.cards.preview, копия автономного проверенного моста.
- Первый Vite запуск в песочнице не прошёл из-за отказа esbuild читать родительский каталог; повтор с расширенным доступом прошёл. Tauri/Cargo собрал EXE. Все хеши исходников и dist совпали после сборки, отдельный ID проверен.
- verify_final.py на конечной папке проверил load_demo, llm_config, process_queue и русскую правку после перезапуска. Три анализа совпали с dev Python. Публичный установщик 0.4.0 не менялся. Native UI QA передан принимающей линии.
- SHA-256 kindle-cards.exe: 3146963ff433dbf048019272a096c476bb25fd42c44ff7af35bd997e299606a1. Мост bacb63c4709784b95c9d7322096d799be7877b06e4966e4b0df3a3785739941c. Контрольные суммы записаны в SHA256SUMS.txt. Установки и публикации нет, исходники не менял, коммита нет.
## 2026-11-23 — Тимлид — Первая рабочая версия лиса

- Одобренный пятый эскиз сохранён с реализацией. По координатам исходного изображения воспроизведены контур, положение глаз, рукоять и стекло фонаря. SVG задаёт свет относительно пламени. Днём остаются стекло и фитиль, ночью лис освещает стол. Фронтенд-разработчик поставил доступную кнопку на фонарь, добавил добровольную реплику и редкое моргание с учётом reduced-motion и видимости.
- После двух раундов планёрки лис появился при подготовке на обычной Главной. В готовой подборке работает прежний экспорт. Автономный пример на тестовых словах использует тот же HomeView. Сборка примера — node packaging/build_lamp_study.mjs --fox.
- По визуальному ревью скорректированы свет, прилегание лап к столу и положение открытой реплики на компактном экране. На финальных снимках UI-дизайнер подтвердил исправления. Независимая QA прошла клавиатурное приветствие и закрытие, восстановление фокуса, готовность списка, обе темы и скачивание TSV без сети. Проверены окна от 360 до 1628 px. 130 тестов интерфейса, TypeScript, production Vite, сборка Tauri и git diff --cached --check прошли. Внутри Windows WebView2 испытана очередь из 15 вымышленных слов с настоящими изменениями счётчика, приветствием и доступным экспортом после обработки.
- Внутренняя сборка находится в build/internal-fox-preview, автономный файл в build/fox-lantern/index.html. Контрольные суммы сборки и мост проверены релиз-инженером. Локальный коммит 94563cc. Публичного релиза и установки не выполнялось. Для проверок использована временная тестовая библиотека.

## 2026-11-23 — Релиз-инженер — Проверка окружения fox motion

- Прочитан текущий WORKLOG. Мост из build/internal-fox-preview доступен, SHA-256 bacb63c4709784b95c9d7322096d799be7877b06e4966e4b0df3a3785739941c. Python 3.11.15, Cargo 1.96.1 и Node v26.4.0 доступны через kindle_app. Предыдущий preview процесс не запущен.
- Подготовлена к использованию отдельная папка build/internal-fox-motion; на момент проверки её ещё нет. Жду сигнал о готовности SVG и CSS анимаций перед Vite/Cargo. Исходники и прежняя сборка не менялись, установки и публикации нет.
## 2026-11-23 — Фронтенд-разработчик — Общая хореография лиса

- В выделенной области изменены fox-lantern.css и только атрибут data-speaking в fox-lantern.tsx для паузы при открытой реплике. SVG и остальные файлы не редактировал. Повороты используют согласованные pivot головы, ушек, хвоста и обоих экземпляров фонаря; взгляд и моргание имеют отдельные группы.
- После возражения продакта заменил независимые длительности одним циклом40с. Голова2.8–6.4с, взгляд3.0–6.4с; ближнее ушко8.0–9.6с, дальнее9.6–11.2с; фонарь и его проекция13.2–18.4с; хвост22.0–27.2с; моргание31.2–31.68с. Остальное время покой. Амплитуды: голова−7/+1.8°, ушки−15/+8° и+12/−5°, фонарь+3.8/−2.4/+1.4/−.6°, хвост+8/−5/+2°. Общая фаза сохраняется при паузах, наложение разных окон на последующих циклах исключено общей длительностью.
- Все семь классов жестов ставятся на паузу при data-active=false и data-speaking=true. motion=false и системный reduced-motion снимают все анимации. Существующая SVG-привязка видимости света к lamp-glow сохранена. Новых библиотек, таймеров и React-state на кадрах нет.
- Проверки:130 frontend-тестов, TypeScript/Vite и diff --check прошли. Playwright на1437 проверил8 CSS-animation экземпляров с40с, активность только ожидаемых групп в6 опорных точках, совпадение второго цикла, равенство matrices обоих фонарей, нахождение стекла внутри44px target на максимальном качании, паузу всех жестов при открытой реплике и вне viewport, motionoff, reduced-motion и нулевую видимость света днём. Снимки оглядывания1440 и хвоста600 просмотрены.
- Первый shell-запуск получил1223 от setup helper; чтение через login=false прошло. Patch общего цикла остановился на неверном ожидаемом тексте keyframe; файл перечитан и исправлен последовательной заменой, браузерная проверка финального цикла прошла. Реальное hidden-переключение вкладок и native после этой правки не проверял. Собственный Vite1437 оставлен для основной QA по сообщению тимлиду; тестовый браузер закрыт. Коммита нет.

## 2026-11-23 — QA-инженер — Анимация частей лиса и связанный свет

- Независимо проверил Vite 1437 и окончательный offline HTML build/fox-lantern/index.html, SHA-256 4bf3e79b6429396c072182cf5dfbb69a16c55ad6fa66302bf576e83e8501892b. Chromium Playwright, вымышленные слова, артефакты и скрипты во временном каталоге. Продуктовые исходники не редактировал.
- На общей40с шкале управляемая выборка currentTime показала head+gaze в3,6с, ближнее ухо8,6с, дальнее10,2с, фонарь14,4с, хвост23,2с, моргание31,4с. Вне каждой фазы остальные группы нейтральны, кроме совместного head+gaze. К34с все семь матриц вернулись в исходное положение.
- Дополнительно наблюдал два полных реальных цикла,82с и820 выборок с шагом100мс. Перекрытий независимых жестов не обнаружено. В каждом цикле около227–228 выборок шесть основных групп находились в покое. Для продолжительности теста только браузерная обёртка продлила интервал синтетического счётчика3800→380000мс; CSS-время не ускорялось. Реплики автоматически не открывались.
- Обе местные матрицы .fox-pendant совпадают. Воздушный свет имеет CTM фонаря; отражение соответствует матрице статического сплющивания, умноженной на матрицу фонаря, максимальная численная ошибка около6,1e-6. Быстрый mouse.click по screenCTM-точке стекла50,333 на пике при playState=running открыл приветствие на1440 и600px. Снимок600 просмотрен.
- Непрерывная анимация меняет матрицу без ручной остановки; открытое приветствие удерживает позу. Моделируемая hidden-ветка visibilitychange удерживает матрицу; настоящее переключение вкладки в этой задаче не проверял. Тихий режим и prefers-reduced-motion оставляют0анимаций. Днём все пять световых opacity равны0.
- Обычная Главная с cold-start прошла1440ночь и600день+reduce: клавиатура, закрытие, focus из приветствия на home-title после готовности, штатный mock-export. Финальный file:// проход не делал HTTP-запросов и не дал pageerror. Собственная qa-fox-motion сессия закрыта.
- Предварительно на старых циклах23/27/30/31/34с зафиксированы пересечения, о которых сообщено ведущему; после переноса на общую шкалу повторные проверки прошли. Первое QA-ожидание нейтрального translate исправлено по фактическому CSSOM. Полные suites, native WebView2, устройства и пользовательская библиотека в этом прогоне не проверялись. Добавлен только этот раздел WORKLOG, коммита и публикации нет.

## 2026-11-23 — Native-проверка fox motion
- Изолированный запуск новой сборки на 15 вымышленных словах с блокировкой доступа к читалке: очередь продвинулась от 0 до 14 при максимуме 15, затем появился экспорт; приветствие по Enter работает, ошибок страницы нет.
- В WebView2 обнаружены анимации лиса; у фонаря при 36% цикла матрица изменилась с единичной на поворот около 3,8°. Остальные движения и геометрия зоны на максимуме отдельно не проверены. Снимки сохранены в визуализациях.
- Первый запуск теста не нашёл Playwright в conda; повтор через отдельное окружение прошёл. Личные данные и устройство не использовались, исходники не менялись.

## 2026-11-23 — Релиз-инженер — Проверка поставки fox motion

- Завершена проверка переноса в build/internal-fox-motion. Хеш EXE совпал с бинарником после Cargo. Автономный мост и все ресурсы побайтно совпали с эталоном build/internal-fox-preview; SHA-256 моста bacb63c4709784b95c9d7322096d799be7877b06e4966e4b0df3a3785739941c.
- Входные сигнатуры Python, frontend и оболочки сохранились, production dist после Vite совпадает с зафиксированным до Cargo. Preview ID — com.kindlevocab.cards.preview. verify_final.py проверил load_demo, llm_config, process_queue и UTF-8 сохранение русского изменения после отдельного запуска. Три синтетических анализа совпали с dev-Python.
- Публичный установщик не изменён. SHA256SUMS.txt добавлен в новую папку. SHA-256 kindle-cards.exe ec03353ae309e7cc81c0bb4e211f32536461342e34fbc595186f9f30f403ca46. Исходники и старые сборки не менял. Установки и публикации не было. Коммита нет.
## 2026-11-23 — Фронтенд-разработчик — Закрытие стенда после QA

- По поручению тимлида остановил свой Vite1437 через исходную exec-сессию. Повторная проверка не обнаружила слушателя1437.
- В .playwright-cli оставались только два файла собственной сессии fox-motion, console и page от11:32. Переместил их в игнорируемую .app-data/frontend-playwright-logs; git check-ignore подтвердил исключение. Продуктовые исходники не менял, коммита нет.

## 2026-11-23 — Native-проверка движений лиса
- В изолированном WebView2 на новой очереди из 15 вымышленных слов проверены матрицы головы и взгляда на 4 с, ближнего уха на 8,6 с, дальнего на 10,2 с, обоих элементов фонаря на 14,4 с и хвоста на 23,2 с: все отличаются от исходных. В точке фонаря на максимуме elementFromPoint нашёл кнопку приветствия; анимации возобновлены.
- Приветствие по Enter и готовая подборка с экспортом прошли, ошибок страницы нет. Первый вариант временного сценария ошибочно выбирал SVG и исправлен; повтор прошёл. Личная библиотека, устройство и исходники не затронуты.

## 2026-11-23 — Тимлид — Движения лиса и свет фонаря

- В ответ на пожелание владельца разделил исходный вектор лиса на голову, два уха, корпус и хвост. Соединения находятся внутри силуэта. Дужка, стекло, пламя, ореол и луч качаются вокруг точки хвата. Отблеск использует тот же поворот в проекции на стол. Фронтенд-разработчик добавил движения в `fox-lantern.css` и паузу при приветствии в `fox-lantern.tsx`. Изменение рисунка находится в `fox-figure.tsx`.
- На планёрке согласовали редкие жесты и постоянную область нажатия на стекло. Первая проба с разными периодами давала наложения. После замечаний продакта и UX перешли на один цикл в 40 секунд. UI-дизайнер сверил кадры в крайних положениях и признал пригодными стыки, освещение и композицию узкой дневной сцены. Его оценка относится к отдельным позам. Ритм проверил QA в работающем браузере на двух полных циклах.
- 130 тестов интерфейса, сборка TypeScript/Vite и проверка diff прошли. В браузере проверены наклон фонаря и проекция отблеска, выбор фонаря мышью на ходу, клавиатура, возврат фокуса после появления подборки, системное уменьшение движения и остановка при реплике. Для ожидания двух циклов в тестовой вкладке продлевался интервал синтетического счётчика. Скрытие вкладки проверялось моделированием. В WebView2 отдельная очередь из 15 вымышленных слов дошла до готовой подборки.
- Собраны автономный пример `build/fox-lantern/index.html` и отдельная внутренняя версия `build/internal-fox-motion/kindle-cards.exe`. Рядом с HTML сохранён фрагмент `fox-motion.webp` длительностью 33 секунды, снятый по ключевым кадрам работающей сцены в исходном темпе. Личную библиотеку для проверок не открывали. Локальный коммит `5cc84e2` в ветке `codex/card-review`.

## 2026-11-23 — Релиз-инженер — Именованный Fox preview

- Собран дополнительный EXE Kindle Cards - Fox.exe, не заменяя ранее зафиксированный kindle-cards.exe. Временный Tauri config задаёт заголовок «Kindle Cards — Лис-фонарщик · внутренняя сборка 5cc84e2» и сохраняет preview ID com.kindlevocab.cards.preview.
- Production frontend не менялся: хеши dist до/после Cargo совпали. Мост и ресурсы совпали с эталонным bridge. SHA-256 прежнего EXE до и после сборки остался EC03353AE309E7CC81C0BB4E211F32536461342E34FBC595186F9F30F403CA46. Новая оболочка имеет отдельный новый SHA-256.
- Установщик не создавался. Открытые процессы не останавливались. Исходники и публичная установка не затронуты. Контрольные суммы записаны в SHA256SUMS-fox.txt. Коммита и публикации нет.
## 2026-11-23 — Native-проверка именованного Fox preview
- Проверен именованный EXE с SHA-256 f263d77a70dd615d41f26634d9c8f104e70a7bf0301d2d9b2aadd2a3ca0d80c2 в отдельном временном профиле на 15 вымышленных словах. Видны подготовка с лисом, приветствие по Enter и готовая подборка с экспортом; ошибок страницы нет.
- Доступ к устройству заблокирован, личная библиотека не использовалась, закрыт только тестовый процесс. Исходники не менялись.

## 2026-11-23 — Тимлид — Проверка ссылки на внутреннюю сборку Windows

Владелец уточнил, что открывал ссылку из чата. Запуск именно `build/internal-fox-motion/kindle-cards.exe` до исправления подтвердил ожидаемую контрольную сумму `ec03353a…`, общий заголовок «внутренняя версия редактора» и обычную Главную с готовой подборкой. Доступный заголовок экрана и наличие списка прочитаны без вывода слов. На этом экране показывается настольная лампа. Лис в текущей реализации появляется при подготовке первой подборки. Ярлыки рабочего стола и меню «Пуск» ведут к отдельно установленной 0.4.0 и в описанном владельцем запуске не участвовали.

Релиз-инженер пересобрал оболочку с названием «Kindle Cards — Лис-фонарщик · внутренняя сборка 5cc84e2». После сверки новой сборки с результатом Cargo тимлид атомарно обновил исходный путь ссылки, сохранил резервную копию и обновил конфиг и SHA256SUMS внутренней поставки. Новый SHA-256 `f263d77a70dd615d41f26634d9c8f104e70a7bf0301d2d9b2aadd2a3ca0d80c2`. По исходному пути запущено и оставлено открытым проверенное окно с новым заголовком. Приёмка того же бинарника на отдельной тестовой очереди подтвердила появление лиса, приветствие по Enter и открытие готового списка. Сценарий Главной, установленная программа, её ярлыки и публичные поставки не менялись. Изменение относится к локальной сборке, исходный коммит приложения `5cc84e2`.

## 2026-11-23 — Фронтенд-разработчик — Постоянный лис на Главной

- В HomeView лис теперь постоянно занимает одну JSX-позицию во всех состояниях loading/no-reader/empty/preparing/list/processing-stopped. Условное размонтирование заменено стабильным FoxLantern. Исторический deskLamp override сохранён. В fox-lantern.tsx обновлено описание жизненного цикла; обработчики приветствия и анимации сохранены.
- Scoped-геометрия FoxLantern распространена на все состояния Home. В компактном контейнере уменьшены фигура, заголовок и отступ до списка; в самом узком виде фигура140px у заголовка, действия и прогресс ниже на всю ширину. Открытая реплика получает отдельную верхнюю полосу104px, чтобы не обрезаться и не закрывать текст. При коротком окне подготовка выравнивается к верху. home.css и остальные экраны не менял.
- Обновлены тесты постоянного интерактивного лиса во всех шести состояниях и сохранности deskLamp override. Все131 frontend-тест и production TypeScript/Vite прошли, diff --check чист.
- На сервере тимлида1441 Playwright проверил готовую/занятую Главную600×480, готовую390 и1440, no-reader/empty/loading/processing-stopped600×480. Снимки просмотрены: основное действие и первая строка либо прогресс доступны без прокрутки, лис виден. DOM-маркер на стенде600×480 подтвердил тот же trigger, открытое приветствие и focus после preparing→list; Enter продолжил закрывать реплику. Реплика не открывается автоматически.
- Свой временный Vite1438 остановлен; сервер1441 тимлида не тронут. Собственные browser-логи перемещены в игнорируемую папку после закрытия сессии. Native, устройства и личная библиотека в этой линии не проверялись. Коммита нет.

## 2026-11-23 — QA-инженер — Один лис на каждом экране

- На Vite1441 независимо проверил32состояния: Главная/list, no-reader, Слова, Настройки, прямые view=triage иexport, карточка из подборки и возврат. Все сочетания1440/600px иday/night. Во всех состояниях одна видимая .fox-figure в пределах viewport; прежние desk/clip/sconce и элементы старого знака отсутствуют. Отдельный .fox-mark бренда соответствует согласованному исключению.
- Вне Главной .fox-vignette имеет aria-hidden и не содержит focusable controls; кнопки приветствия нет. На Главной приветствие доступно в готовом списке, без читалки и при подготовке. Четыре cold-start→list прогона сохранили открытое приветствие и фокус на «Закрыть»; Escape/Space и последующий штатный mock-export работают.
- В Словах дополнительно открыта карточка из обычного списка: на600px возврат восстановил фокус строки, на1440px список остаётся доступным рядом и позволяет выбрать другое слово. В каждом варианте основной лис один. Первое ожидание отдельной кнопки возврата на широком экране исправлено в QA-скрипте после сверки штатной компоновки.
- Сохранены восемь снимков Settings/карточки на1440/600 в обеих темах; просмотрены широкие дневные и узкие ночные. Горизонтального переполнения, framework overlay и ошибок console/pageerror нет. Browser plugin отсутствует, применён Playwright CLI с отдельной сессией и временными артефактами.
- Продуктовые исходники не редактировал, синтетические mock-данные. Сессия qa-fox-screens закрыта, Vite ведущего не остановлен. Native, пользовательская библиотека и реальные экспорты не проверялись. Добавлен только этот раздел WORKLOG, коммита нет.

## 2026-11-23 — Внутренняя сборка aa4f033 оставлена архивной
- Цель: подготовить отдельную переносную сборку по подтверждённому запросу, затем учесть уточнение о смене объёма.
- Решение: после указания владельца не продвигать `aa4f033` остановить публикационные действия; не менять старый путь и не запускать приложение. Отдельный артефакт сохранён в `build/internal-fox-everywhere/` как архивный кандидат; дальнейшую сборку ждать до нового commit и staging-папки.
- Артефакты: `kindle-cards.exe` (9,825,280 байт, SHA-256 `6613BB7A5D605F1753B97A259D81E5FAFA4C8E3B42AA77CDFD2115298951BA02`); bridge SHA-256 `BACB63C4709784B95C9D7322096D799BE7877B06E4966E4B0DF3A3785739941C`.
- Проверки: production Vite build завершился успешно. Повтор Tauri build остановлен до проверки smoke из-за уточнения объёма; EXE и bridge только проверены на наличие и хеш. Старое открытое приложение не затронуто.
- Риски/остаток: этот артефакт не считать приёмочным; ждать новый commit и staging-путь. Публичная установка и старые ссылки не менялись.

## 2026-11-23 — QA-инженер — Уточнение: лис только вместо настольной лампы

- Адресно перепроверил окончательный Vite1441 на синтетическом mixed в1440/600px иday/night. На Главной один интерактивный лис, настольная лампа отсутствует. Приветствие открывается и закрывается Escape во всех четырёх сочетаниях.
- На Словах, в карточке и Настройках лиса нет. В карточке восстановлен ClipLamp, исходный бренд и бра возвращены. На1440бра видимо, на600скрыто штатной компоновкой. Возврат из карточки ведёт к Главной с доступным приветствием лиса.
- Проверены12основных состояний и четыре карточки/возврата, ошибок console/pageerror и горизонтального переполнения нет. Сохранены восемь новых снимков карточки и Settings вtemp, просмотрены карточка600ночь иSettings1440день. Собственная qa-home-only сессия закрыта.
- Этот результат заменяет прежнюю приёмку варианта «лис на каждом экране» по уточнению владельца. Остальные сценарии поведения Главной проверены предыдущим прогоном; native и личные данные в этой задаче не использовались. Продуктовые исходники не редактировал, добавлен только этот раздел журнала. Коммита нет.

## 2026-11-23 — Native-приёмка лиса только на Главной
- Изолированный WebView2 smoke сборки 6db84bb, SHA-256 EXE 911b59d13ce1f4553f5389ef2f0961356d75a0041070ae571031793f7e573f54: очередь 15 вымышленных слов обработана, приветствие по Enter работает, в готовой подборке видны лис и экспорт.
- На широком экране видно бра; в Словах и Настройках лиса нет, карточка открывается и содержит ClipLamp. Ошибок страницы нет. Доступ к читалке блокирован, личная библиотека и другие окна не затронуты, исходники не менялись.

## 2026-11-23 — Тимлид — Лис на месте основной настольной лампы

Владелец уточнил смысл «везде»: лис занимает место большой лампы на Главной во всех состояниях. Бра, лампа у карточки, знак приложения и остальные экраны сохраняют прежнее оформление. До уточнения команда проверила более широкую замену на отдельном стенде, затем убрала её. Общий коммит aa4f033 не передавался на пользовательскую ссылку. Итоговый локальный коммит 6db84bb. Сверка с 5cc84e2 показала изменения только в документах, HomeView и его тесте, FoxLantern и переключателе движений автономного примера.

На Главной сохраняется один экземпляр интерактивного персонажа при смене подготовки готовой подборкой. При открытом приветствии фокус и реплика сохраняются. В узком окне лис, пояснение, действие и список занимают отдельные места. QA проверил все состояния Главной, обе темы, карточку, возврат, навигацию и настройки на 600 и 1440 px. Визуальное ревью подтвердило видимый силуэт рядом с готовым списком и восстановленное оформление других разделов. Все 131 тест интерфейса прошли, TypeScript/Vite и сборка Tauri завершились успешно. Автономный пример открылся без сети и сохранил лиса и переключатель движений после показа подборки.

Внутреннюю сборку обновили по прежнему пути build/internal-fox-motion/kindle-cards.exe, сверили второе имя EXE и мост, сохранили копии предыдущего бинарника. SHA-256 новой сборки 911b59d13ce1f4553f5389ef2f0961356d75a0041070ae571031793f7e573f54. Штатно закрыли ранее открытое тимлидом окно после проверки готовности. Запустили обновлённый EXE по пути из чата и в обычном открытом окне подтвердили одновременно заголовок списка «Слова на этот раз» и кнопку «Поприветствовать лиса». Установленная версия и публичный установщик для этой задачи не менялись.

## 2026-11-23 — Приёмочная сборка 6db84bb
- Цель: подготовить отдельную переносную Windows-сборку для внутреннего QA в `build/internal-fox-home/`.
- Решение: использованы preview identifier `com.kindlevocab.cards.preview`, согласованный заголовок сборки `6db84bb` и прежний проверенный bridge. Старый путь/EXE и открытую версию не заменял и не запускал; публичную установку не менял.
- Артефакты: `kindle-cards.exe` (9,826,304 байт, SHA-256 `911B59D13CE1F4553F5389EF2F0961356D75A0041070AE571031793F7E573F54`), bridge (SHA-256 `BACB63C4709784B95C9D7322096D799BE7877B06E4966E4B0DF3A3785739941C`), `SHA256SUMS.txt`; только локальные файлы в `build/internal-fox-home/` и эта запись журнала.
- Проверки: `tauri build --no-bundle` завершился успешно; production dist содержит ожидаемые `index-0lxHn7To.js` и `index-DPbOqSle.css`. Совпали SHA всех 258 файлов bridge с проверенным источником. В EXE найдены ожидаемые identifier и заголовок. Bridge smoke: `load_demo`, `llm_config`, очередь из 3 синтетических слов идентична dev Python, UTF-8 round-trip `save_card_edit` после перезапуска. SHA старого EXE совпал с ранее сохранённой контрольной суммой.
- Не проверено: ручное открытие нового окна и визуальная приёмка владельцем; smoke покрывал bridge, не UI. Ошибок сборки/bridge smoke нет. Публичная установка и старые ссылки не менялись.


## 2026-11-23 — Инженер ранжирования: исходный замер и контракт шкалы полезности

- До изменений на базе 6db84bb запустил ranking_eval в Windows conda kindle_app. SQLite открывалась только на чтение, оба реальных прогона увидели 2 564 поиска и 1 768 слов. В ignored-каталоге .app-data/ranking_eval/usefulness-baseline-2026-11-23 лежат команды и агрегаты. Копию базы не создавал.
- В зрелой истории ranking_v2: AUC 0,642, P@20 0,38, P@50 0,32, lift@20 3,1, lift@50 2,6 на двух сопоставимых срезах. На прокси короткой истории без повторов, три среза: ranking_learning 0,591 / 2,176 / 1,278 по AUC / lift@20 / lift@50. Штатная синтетика, восемь срезов: 0,652102 / 2,911293 / 1,991826. Оба CLI и синтетический прогон завершились, каталог проверен через git check-ignore.
- Предложил производную от полки и исходной оценки шкалу 1–10 отдельно от ранга экспорта. Записи без анализа получают предварительную середину; 10 резервируется для фактической полки junk, включая личное решение «Не слово». Порядок детерминирован по уровню, уверенности, исходной оценке и ID. Проверка при реализации: все состояния, монотонность, приоритет решений, сохранность состава и порядка новой порции, повтор исходных замеров.
- Слабые стороны: относительный сигнал повторного поиска, зависимость реального сравнения от состояния библиотеки и отсутствие оценки необработанных слов в ranking_eval. Продуктовый код и тесты не изменялись, нового коммита нет.


## 2026-11-23 — Инженер ранжирования: study_priority и проверка общего порядка

- В ranking.py добавил study_priority по согласованным абсолютным границам и с исходной точностью score. Оценка не зависит от решений, включая истёкшее «Знаю». Уровень 10 требует непустой записи без букв Unicode. Имена, буква ё, дефисы, слова с цифрами, отсутствие в словарях и старые флаги non_word/non_english сами по себе не дают уровень 10. Пояснения отличают неполную словарную проверку от отсутствия слова в доступных словарях.
- В tests/test_ranking.py добавил четыре проверки: точные границы, независимость решений, структурные признаки и словарная неопределённость. Целевые тесты ранжирования и представления библиотеки: 134 прошли. Полный pytest: 326 прошли, 1 пропущен. Ruff для изменённых файлов и git diff --check прошли. Файл ranking.py заморожен для упаковки, SHA-256 CDE99A3B2299E3511C33B6D83EBFF2C972E8D55C8383BACEED67B93F62070054.
- Повтор ranking_eval дал одинаковые агрегаты, в зрелом JSON разница только generated_at. Отдельный ignored-скрипт пересчитал production decorate и фактический новый компаратор с ранее rejected. Все 15 срезов дали одинаковые списки первых 20 по сравнению с исходным score без округления. AUC / lift@20 / lift@50 до = после: локальные месячные 0,586528 / 1,977598 / 1,925094; короткие 0,574097 / 2,144812 / 1,257266; синтетика 0,659112 / 2,967686 / 2,028826. В первом сравнении округлённый score ошибочно создал искусственные ничьи, это исправлено в скрипте.
- Бенчмарк включает 0–17 rejected на срез, проверяет повторный поиск как прокси. Уровень 10 и предварительные записи в этих исторических срезах отсутствовали, соответствующие ветки проверены на вымышленных данных. Реальная SQLite только читалась. Интерфейс и установленную сборку в этой задаче не проверял. Отчёты под ignored .app-data/ranking_eval, исходный коммит 6db84bb, нового коммита нет.

## 2026-11-23 — Бэкенд-разработчик: шкала study_priority в библиотеке

- В `library_view.py` добавил `study_priority` всем каноническим записям и переиспользовал результат существующего rank для слов без ручного решения. Незавершённое состояние, отсутствие достаточного анализа или даты поиска дают предварительные 6/0 с отдельной причиной. Расчёт уровня находится у инженера ранжирования. Подборка, полки, спорные и допуск к экспорту используют прежние поля. Изменения схемы и повторный анализ не требуются.
- Обновил `contracts.py`, обе `bridge_library_v4*.json`, проверки библиотеки и контракта, исключение полей представления при сверке миграционной фикстуры. Синтетические проверки включают pending/processing/failed, legacy без измеренных признаков, отсутствие даты, истёкшее «Знаю» и реальный TSV для `rejected + learn`. Отдельного `bridge-contract.md` нет.
- На временной копии реального SQLite v4 1 762 из 1 762 слов получили оценку. По сравнению с `6db84bb` эквивалентны все прежние поля записей, очереди, полки и списки. Совпали 325 экспортируемых ID в порядке выдачи и короткий список из 20. SHA-256 исходной базы и копии до/после совпали. Целевые тесты: 95 прошли. Полный Python: 326 прошли, 1 пропущен. Ruff, compileall и git diff --check прошли. UI и замороженный мост не запускал.
- Дополнительно прогнал обычный `import_reader_file` и `scan` с контролируемым источником и настоящей синтетической схемой Kindle. Оба сохраняют цифры и дефис, `?!` и пробельная строка не получают канонический ключ. После штатной очереди сохранённые записи без букв переходят в rejected, но остаются preliminary 6 из-за отсутствия лексических признаков. Предложил сохранить непустую исходную форму только при пустом результате нормализации и разрешить структурное основание 10 для завершённого анализа. Код после сигнала готовности для упаковки не менял. Коммит не создавался.

## 2026-11-23 — Подготовка staging для study-priority
- Цель: подготовить отдельный приватный staging-путь под новую frozen bridge и Tauri сборку.
- Решение: создан `build/internal-study-priority/` и предварительный `tauri.study-priority.json` с preview identifier; до конкретного нового commit PyInstaller/Tauri не запускаются.
- Изменённые файлы: только ignored staging-конфиг в `build/` и эта запись WORKLOG. Источники и существующие сборки не изменялись; публичной упаковки нет.
- Проверки: синтаксис JSON подготовленного конфига проверяется следующим шагом; сборка и smoke не запускались.
- Риски/остаток: обновить заголовок и зафиксировать сигнатуры по commit владельца перед упаковкой.

## 2026-11-23 — QA-инженер — Независимая приёмка study_priority

- На вымышленных данных проверил24точки около восьми включительных порогов уровня, типы study_priority у девяти канонических записей, пять вариантов provisional6/score0 с конкретной причиной и независимость приоритета отвергнутого слова от learn/skip/junk/known/null. Подтверждено, что буквенное имя и отсутствие словаря сами по себе не дают10.
- Через отдельные процессы JSON-моста проверены load_library и set_decision с повторным чтением. В CSV после ручного learn присутствует прежде отвергнутое vigilant, а пропущенное glimpse из устаревшего списка IDs отсутствует; число и причина vigilant сохранились. Этот сценарий создавал каталог напрямую и не покрывал reader-канонизацию.
- После сообщения ведущего о дефекте настоящего импорта и исправления structural_study_priority независимо прошёл import_reader_file→process_queue→load_library→повторный import→load_library. Синтетический Kindle vocab.db с семью записями полностью сохранился: ?!,123,00:17 получили окончательный10, Aldric/zqvrel/vigilant/glimpse не получили10. Повторный импорт добавил0слов, осталось7контекстов, ID и study_priority сохранены. Использовано пять отдельных JSON-процессов на финальном Python.
- Браузер Chromium/Vite1442, mixed на1440/600×day/night: все13слов доступны, порядок совпадает с независимым levelASC/provisionalfalse/scoreDESC/idASC. Поиск, фильтры уровней9/10 и книги, восстановление vigilant через Учить с неизменным8, Home→карточка→назад→mock-export прошли. Дополнительная tie-выборка helper подтвердила все ступени порядка при равном уровне.
- Cold-start600 показал три предварительных6 и причину ожидания; после обработки уровни обновились на2,2,3. Финальный обзор групп подтвердил admit1, sundry/languid6, vigilant8, aldric9,00:1710. Просмотрены снимки широкого списка и узкой карточки/предварительного слова; пути переданы ведущему.
- До последнего исправления импорта полный pytest дал326passed/1skipped. После него89целевых тестов ranking/library_view/reader_bridge/vocab_catalog прошли, точный список Ruff CI чистый. Vitest136/136 прошёл вне песочницы. Production build ведёт релиз-инженер, свой не запускал во избежание одновременной записи dist.
- Console/pageerror, framework overlay и горизонтальных переполнений в браузерных прогонах нет. Browser plugin отсутствует, применён отдельный Playwright CLI. Сессия qa-priority закрыта, исходники не редактировал, добавлен только этот раздел журнала. Native, установленная сборка и настоящий Anki в этой задаче не проверялись, личные данные не использовались. Коммита нет.

## 2026-11-23 — Бэкенд-разработчик: сохранение записей без букв при импорте

- `vocab_cache.py`, `library_repository.py`, `tauri_bridge.py`: общий канонический нормализатор сначала применяет прежнее правило, при пустом результате сохраняет непустой исходный токен. Пустые и пробельные слова пропускаются до присвоения ID. Записи с уже существовавшим ключом используют прежнее значение.
- `ranking.py`, `library_view.py`: общий `structural_study_priority` определяет непустые строки без букв Unicode. Для завершённой записи присваивает уровень 10, score 0, с причиной «В записи нет букв» без требования времени или словаря. Pending остаётся предварительной 6. Полки, история и допуск к выгрузке не пересчитываются по новой шкале.
- `test_tauri_bridge_smoke.py` проверяет scan с подменённым обнаружением и реальный import_reader_file на синтетическом Kindle SQLite, настоящий process_queue и повтор. Сохраняются 00:17, ?!, 123, Unicode-слово и обычное ready-слово, пустоты отсекаются, контексты не дублируются. `test_library_view.py` покрывает ready без словарных признаков и даты. На копии реальной v4-библиотеки запись каталога сохранила 1 762 канонических ID, порядок выгрузки и очередь, SHA-256 оригинала не изменился.
- 135 целевых тестов прошли. Полный Python: 328 прошли, 1 пропущен. Ruff для файлов CI и изменённых тестов, compileall и git diff --check прошли. Физический Kindle, UI и замороженный мост не запускал. Исходный коммит `6db84bb`, коммита нет.
- SHA-256 упаковки: `vocab_cache.py` 1F930A590E9EF693728B1E0E5C8D4343BA8C39D59B52AC66E774F9FB0FF8D900; `library_repository.py` C27809C883473A56596844C143FA105D1E99A39C3F72D0102F25FD6B80918BDA; `tauri_bridge.py` 5E47180B3FB7411093C52DFD5ECBFDFB6FF7D6861BCD65650E56ECAC6D6DA36C; `ranking.py` 208BD18E972AA08C415A2AC212CBF1A844AE15A6FFBC999B616CDE7368F4E7CA; `library_view.py` 951C4359EE365306324013066E9A4DFC03DA8A7C8F3C74F42FD4AEA6A37B306C.

## 2026-11-23 — Фронтенд-разработчик — Все слова и шкала приоритетов

- По согласованной планёрке «Слова» по умолчанию показывают все канонические записи, включая старые, rejected и низкие уровни. Новый study-priority.ts читает snake_case поле study_priority; для старого payload без поля сохраняет запись как предварительную6 с причиной отсутствия данных. Сортировка level ASC, provisional false раньше true, score DESC, id ASC. Пороги на фронтенде не вычисляются.
- Поиск и книга пересекаются с точным уровнем в одном Select. По итоговому поручению владельца те же10 options сгруппированы нативными optgroup1–3/4–6/7–9/10, значения и названия «Приоритет N» сохранены, All остаётся значением по умолчанию. На строках показан уровень и «предварительно», направление шкалы пояснено. В карточке приоритет и его причина отделены от «Моё решение».
- Из любой карточки можно выбрать Учить/Не учить, сменить или снять существующее решение. Demo/busy/pending/dirty сохраняют блокировки, ожидание и ошибки не сбрасывают ввод. Неиспользуемый worthLearning и его прежний тест двух полок удалены. filterLexemes получил необязательный comparator: существующие вызовы сохраняют legacy сортировку, новый каталог сортируется один раз.
- Исправлена обнаруженная браузером гонка возврата focus к виртуализированной строке ниже viewport. WordList ждёт отрисовки и ненулевой высоты, поиск получает фокус только если записи нет в текущем фильтре. Прямой вход по ID из подборки по-прежнему обходит фильтры. Breakpoint последовательного списка/инспектора поднят до1100px, чтобы900–1024 не сжимали таблицу; поиск показывает «Найти слово» с прежним полным aria-label.
- В UI review первоначальное замечание о сокращении цитат снято: полный выбранный контекст уже доступен в blockquote, после новой компоновки на1000 он также помещается в select. UI-дизайнер просмотрел промежуточные дневные список и карточку, новых дефектов не отметил. Самостоятельно просмотрены1440/600 и промежуточные1000/1024, проверена полная цитата при смене выбора.
- Проверки:136 frontend-тестов, TypeScript/Vite и diff --check прошли. Новые4 теста проверяют полноту, четыре ключа сортировки, пересечение поиска/книги/уровня и fallback старого payload; тест карточки — независимое личное решение и demo. Playwright1442 проверил All,00:17=10, имя aldric=9, vigilant=8, фильтр10 и поиск,4 optgroup и11 options, Learn/Skip/снятие без смены приоритета, возврат focus600, восстановление rejected vigilant в подборку на Главной и обычный mock-экспорт. Браузерная консоль без исключений приложения.
- Первый sandbox shell остановился на Windows1326, чтение и проверки с расширенным доступом прошли. В первом тесте disabled не учитывался вложенный PencilFrame; тест уточнён. В первом браузерном селекторе имени уточнён регистр lemma. Реальный Tauri/SQLite/Anki и личную библиотеку не проверял. Стенд1442 принадлежит тимлиду. Изменены только файлы src/features/library/ и эта запись; TypeScript types/mock менял тимлид. Новые study-priority.ts и study-priority.test.ts нужно включить при коммите. Коммита нет.

## 2026-11-23 — Тимлид, полный каталог по приоритету изучения

- Владелец выбрал полный каталог с приоритетами от 1 (учить первым) до 10 (возможная ошибка записи). Продакт, UX-дизайнер, инженер ранжирования и бэкенд обсуждали направление шкалы, ручные решения и незавершённый анализ. Итог и разногласия добавлены в docs/plan/meetings.md. У неподготовленного слова видна временная 6 с причиной. Приоритет независим от личного решения. Короткая подборка сохраняет свой лимит.
- Коммит d48dad3 содержит контракт, интеграцию ранжирования всех канонических записей, сохранение непустых токенов из знаков, v4-фикстуры и тесты. ed88fa9 добавляет типы и browser mock, каталог, четыре группы уровней, фильтры, действие «Учить» и продуктовую документацию. В UI-дизайн не добавляли цветовые индикаторы. После ревью исправили возврат фокуса в виртуализированный список и размещение карточки при 1000 px. UI-дизайнер повторно проверил карточку и снял замечание по цитате.
- На копии библиотеки подтверждены все 1762 канонических ID и прежний порядок 325 кандидатов. У исходной кэшированной базы Kindle каждый словарный токен связан с поиском. Независимый сквозной импорт семи искусственных записей проверил очередь, повторный запуск и ноль новых слов при повторном импорте. Записи из цифр или знаков приходят на уровень 10 после обработки. Буквенные имена и незнакомые слова доступны для проверки в общем списке.
- Проверили реальные границы уровней, решения и CSV. Сравнение результатов на 15 срезах сохранило первые 20 слов; эти замеры относятся к повторным поискам. Они не доказывают, что читатель согласится с оценкой каждого слова. Vitest 136/136 и TypeScript/Vite прошли. В браузере проверены 600/1000/1440, темы, поиск, книга, выбор уровня, возврат в карточку и «Учить» при неизменной оценке. Физическое устройство и личная колода для этого изменения не использовались. Внутренняя сборка и её изолированная приёмка идут отдельно.

## 2026-11-23 — Поставка внутренней сборки ed88fa9, study-priority
- Цель: новый frozen Python bridge и отдельный Tauri EXE в `build/internal-study-priority/` для native QA.
- Собран свежий bridge PyInstaller 6.22.3 / Python 3.11.15 из backend d48dad3; Python byte-for-byte совпадает с финальным ed88fa9. Первоначальная постобработка ошиблась в DIST; исправлено только staging-направление на фактический bridge-build/kindle-bridge, затем prune, ресурсы и smoke выполнены успешно. Старый bridge не использован как бинарник.
- Tauri production build --no-bundle завершился exit 0. EXE SHA256 `397CB1F36A79BB6D44A1971EADC44C966184F4050276A1986890DEC8918C6C01`; новый bridge SHA256 `2C71128EFE95FC82A46DD100CB5FEF14C52754C81EAB5BCECB1026371FE777A1`. Embedded identifier com.kindlevocab.cards.preview и заголовок «Kindle Cards — Приоритет изучения · ed88fa9» подтверждены.
- Проверки delivery bridge: load_demo, llm_config, process_queue (3 синтетических слова идентичны dev Python), UTF-8 save_card_edit после перезапуска, study_priority во frozen load_library — успешно. Bundled офлайн-словарь совпадает SHA256 с исходным; NLTK WordNet проверен штатным smoke с изолированным APPDATA. Созданы SHA256SUMS.txt для EXE и всех файлов bridge и source-signatures.json.
- Изменены только ignored staging-артефакты и append WORKLOG. Старые ссылки, открытые окна, установленная копия и публичные артефакты не изменялись. Native UI, физический reader и реальная пользовательская библиотека не проверялись; путь передан ведущему для приёмки.

## 2026-11-23 — Приёмка bridge приоритета
- На временной синтетической базе проверен обычный импорт новым frozen bridge и обработка очереди: 00:17 и ?! получили окончательный уровень 10 с причиной «В записи нет букв», имя aldric — 8. Данные пользователя и устройство не использовались.
- Подготовка отдельного native-сценария прервалась из-за ошибки экранирования Windows-пути в тестовом скрипте; окно не запускалось. Проверки интерфейса, решения «Учить» и экспорта остаются открытыми. Исходники не менялись.

- Повтор native-сценария после исправления тестового пути прошёл: в отдельном окне через поиск открыта карточка импортированного 00:17, показаны приоритет 10 и причина «В записи нет букв». Снимок списка сохранён. Ручное решение и экспорт в этом прогоне не проверены.

## 2026-11-23 — Продолжение native-приёмки приоритета
- После загрузки синтетического списка проверен порядок уровней 1, 1, 8, 10, 10; снимок готового списка просмотрен. В карточке 00:17 нажато «Учить»: решение сохранилось, приоритет остался 10 после перехода на Главную и обратно, запись появилась в короткой подборке.
- Экспорт файла в этом прогоне не проверен. Использовались только временная библиотека и свой процесс, устройство и пользовательские окна не затронуты.

## 2026-11-23 — Тимлид, поставка ed88fa9 и постоянная ссылка

- Внутренний build/internal-study-priority/kindle-cards.exe собран со свежим Python-мостом. Контрольные суммы SHA-256 у EXE 397cb1f36a79bb6d44a1971eadc44c966184f4050276a1986890dec8918c6c01, у bridge 2c71128efe95fc82a46dd100cb5fef14c52754c81eab5bcecb1026371fe777a1. При первой подготовке one-folder исправлена ссылка скрипта упаковки на каталог ресурсов. Конечный мост проверен на полноценном офлайн-анализе и сохранении кириллицы.
- Полный pytest на итоговом коде: 328 прошли, 1 пропущен. В запущенном нативном приложении с тестовой базой виден порядок 1, 1, 8, 10, 10. Готовый список просмотрен визуально. Нажатие «Учить» вернуло запись уровня 10 в короткую подборку, переходы между разделами сохранили число и решение. Активное устройство и личные словари для нативной приёмки не использованы.
- Для ранее выданной ссылки подготовлена отдельная полная копия. EXE, именной вариант и все файлы bridge сверены по SHA-256. После проверки отсутствия работающего старого экземпляра каталог build/internal-fox-motion переключён на новую копию. Предыдущий каталог с его собственным мостом и прежними архивами сохранён рядом в build/internal-fox-motion-backup-6db84bb. Проверка demo через прежнюю точку запуска вернула уровни 1, 2, 3, 6 и 9. Публичный установщик и установленные программы не изменялись.

## 2026-11-23 — Закрытие проверки локальной выгрузки
- Новый frozen bridge через штатные load_settings/save_settings/export_words со scope=new и назначением csv создал TSV из 3 синтетических записей в отдельном временном профиле. Файл прочитан как TSV, Base form содержит 00:17 с ранее сохранённым решением «Учить». Отправка в Anki не выполнялась (pushed=0).
- Проверки порядка, независимости приоритета от решения и локальной выгрузки завершены. Личная база, устройство и пользовательские процессы не затронуты; продуктовые исходники не менялись.

## 2026-11-24 — Подготовка staging читательского стола
- Создан отдельный ignored-каталог build/internal-reading-desk и проверен шаблон Tauri-конфига с preview ID.
- Проверены локальные Python 3.11.15, PyInstaller 6.22.3 и наличие прошлых offline NLTK/словарных ресурсов.
- Сборка не запускалась до сигнала. Python и frontend изменены; старую сборку целиком не копировать. После финального hash сформировать заголовок. Публичных действий нет.


## 2026-11-24 — Подготовка native-приёмки читательского стола
- Изучены прежний изолированный драйвер и текущие точки интерфейса для поиска Kindle, полного экспорта и меню приоритетов. Для проверки потребуется отдельный профиль с синтетикой и прокси, блокирующий реальное обнаружение устройства; после сигнала будет проверена готовая сборка и её bridge.
- Запуск и проверки новой сборки пока не выполнялись; личные данные и устройство не использовались.


## 2026-11-24 — Инженер ранжирования: доказательства и фильтр в каталоге

- В library-workspace.tsx/css причина study_priority видна в каждой строке до двух строк. Виртуализация использует ту же высоту 92 px, что CSS. В card-editor.tsx причина доступна целиком, рядом выводятся только числа уникальных сохранённых записей читалки и известных ключей книг. Записи legacy не считаются, неизвестная книга не превращается в новую. Функция и тест в study-priority.ts/test.ts.
- Нативный выбор приоритета заменил на Radix DropdownMenu с группами, RadioItem, индикатором и прокручиваемым порталом в обеих темах. Стрелки, End/Enter, Escape и мышь проверены. На 600×570 End доводит до 10, пункт получает hover и остаётся над приложением. На 1440×900 видны все четыре группы; активный фон, текст и контур проверены по снимкам. Тексты причин и уровни backend не менялись.
- У нижней виртуализированной строки воспроизвёл потерю фокуса при возврате. Повторная попытка теперь следует за обновлением окна виртуализации. Сценарий карманной ширины подтвердил тот же фокус и одинаковую прокрутку 1029 px. Поиск сохраняется при возврате. Первый тест клавиатуры послал End до появления меню; адаптированное ожидание и повтор прошли.
- Проверки: TypeScript и Vite production build во временный каталог прошли, 10 адресных тестов прошли. В последнем общем Vitest 138 прошли, 1 упал вне моих файлов в mock-backend.test.ts (сценарий no-new). На действующем стенде 1443 отдельной сессией Playwright проверены четыре сочетания ширин/тем, без overlay и ошибок консоли в финальном проходе; шесть снимков и снимок прокрутки сохранены во временном каталоге и просмотрены выборочно. Browser plugin отсутствует. Собственная сессия закрыта, общий Vite оставлен.
- Проверено на синтетических данных Chromium. Нативная сборка, иные браузеры и пользовательские данные не проверялись. Home, backend, use-library-controller и main не редактировал, новых зависимостей и коммита нет.

## 2026-11-24 — Инженер интеграции с Anki — Повторная выгрузка полного каталога

- Цель: принять две последовательные колоды штатным import_anki_package установленного Anki25.09.4 в отдельных временных коллекциях. Использованы вымышленные слова, явные поля перевода, заданное расписание и одна строка revlog. AnkiConnect владельца и его коллекции не открывались, продуктовые исходники не менялись.
- Прямой write_apkg проверен в шести режимах: стандартный импорт, явные IF_NEWER/ALWAYS/NEVER, with_scheduling=True, равные timestamp. Первая колода — две заметки, вторая — изменённое старое слово и новое при исключении второй исходной заметки. Каждый режим оставил три заметки и карточки, прежние note ID/GUID/card ID, поля расписания и revlog. Исключённая заметка сохранилась. При более позднем notes.mod стандартный импорт/IF_NEWER/ALWAYS и режим с расписанием обновили перевод; NEVER сохранил прежний перевод и добавил новое слово.
- Сквозной scope=library выполнен через отдельные процессы dispatch на временной SQLite. Первый запрос с ids двух слов и levels1..10 выгрузил две карточки. Затем сохранён новый перевод, добавлено слово, второй запрос с ids трёх записей и levels=[1] выгрузил две карточки, исключив уровень10. Штатный Anki подтвердил одну updated и одну new, итог2→3. Повтор второго файла дал duplicate=2 и ноль новых. Исходная карточка уровня10 целиком сохранена, расписание и история прежних карточек совпали. SQLite содержит два export_runs со scope=again и word_count2. В temp-wrapper адрес AnkiConnect задан как закрытый loopback-порт9 для принудительного файлового маршрута.
- Ограничение: genanki сохраняет notes.mod с секундной точностью. Контрольные колоды с одинаковым timestamp при стандартном импорте оставили прежний перевод. Дополнительный прогон с update_notes=ALWAYS также оставил прежний перевод, поэтому рекомендация ALWAYS как обхода этой коллизии отозвана ведущему. Условие более позднего timestamp для успешно обновившихся колод проверено. Эта граница воспроизведена управляемым timestamp в тестовой генерации; сквозной штатный экспорт без подмены времени прошёл.
- Пробы запускались native PowerShell и conda kindle_app Python3.11; импорт выполнял установленный Anki Python3.13 с его Rust backend. Новая версия Anki, окно ручного диалога, AnkiConnect и замороженная сборка для этого изменения не проверены. Коммита и публикации нет.

## 2026-11-24 — Фронтенд: редкие реплики лиса и живой огонь
- Область: только fox-lantern.tsx/css, fox-figure.tsx и новый локальный fox-lantern.test.tsx. Добавлен quiet для подавления речи при занятости/ошибке; Home и подключение остаются у ведущего. Исторический прототип не содержал обещания приветствия кликом, поэтому не изменён.
- Реплики: первая через 8 секунд активной сцены, следующие через 60 секунд после закрытия предыдущей; четыре короткие русские фразы идут без немедленного повтора. Общий для экземпляров отсчёт сохраняет паузу при навигации. Кнопка «Реплики лиса» с aria-pressed хранит выбор в localStorage, переключение откладывает речь на минуту. Фонарь больше не является кнопкой приветствия. Escape убирает текущую реплику, фокус не захватывается.
- Unicode-набор по кодовым точкам, полный текст доступен отдельно при aria-live=off. Reduced motion и motion=false дают целый текст без анимации. Visibility/IntersectionObserver приостанавливают речь и жесты. Таймеры удаляются, передача фокуса при unmount сохранена. Бумажное облачко получило собственный округлый SVG с общим изогнутым хвостом, Caveat 23px и чуть тёплую бумагу; фиксированная пустая высота и прежний PencilFrame удалены. Скрытый полный текст резервирует размер конкретной фразы, полоса под постоянный переключатель не прыгает.
- Пламя и две группы источника/отражения синхронно колышутся за 5.8 секунды с неравными акцентами 18/31/48/73/81%, яркость 94–104%. Общая дневная прозрачность сохранена. Прежняя 40-секундная режиссура тела не изменена.
- Проверки: финальные npm run build и два focused Vitest прошли. Полный Vitest в промежуточном состоянии общего checkout: 138/139, один внешний сбой mock-backend.test.ts ожидал newBatch без нового availableIds; ведущий уведомлён. Первый build временно остановился на параллельном quantity/HomeViewProps, после интеграции прошёл. В браузере 1443 проверены первая речь, cooldown после переключения, сохранение выбора после reload, Escape, отсутствие захвата фокуса, статичный reduce, пауза hidden и вне viewport, отсутствие дневного пламени. Скриншоты реальной Главной 600/1440 в обеих темах в ignored .app-data/fox-home-*.png; кадры hold с opacity 1. Дополнительно просмотрен 390 и исторический стенд. Передано ведущему наблюдение о возможном выходе длинной подсказки экспорта под фигуру на 600; чужая Home-область не менялась.
- Ограничения: native/Tauri и реальный screen reader не запускались; окончательная визуальная приёмка у ведущего/UI/QA. В preview при HMR встречалось существующее предупреждение повторного createRoot; предупреждений SSR useLayoutEffect от компонента нет. Без коммита.

## 2026-11-24 — Инженер интеграции с Anki — Приёмка устранения секундной коллизии

- По поручению ведущего согласовал проверку с бэкенд-разработчиком и проверил итоговые _package_timestamp/_previous_anki_seconds через полный export_words(scope=library). Продуктовые исходники не редактировал.
- Первый естественный тест со стартами двух запросов в одну wall-second не достиг условия: первый экспорт на этой Windows занял около1.95с. У другой временной колоды notes.mod и filesystem mtime различались на1с. Это ограничения тестового тайминга, импорта Anki между генерируемыми колодами в таком тесте не было.
- Для контролируемой приёмки первый настоящий temp .apkg получил mtime=T+.1, что моделирует завершение записи в ту же секунду. Только локальные функции anki_export.time/sleep второго export_words управляются тестом: старт T+.2, реальная логика запросила ожидание0.8с, тестовые часы продвинулись в T+1.001. Внутри второго .apkg notes.mod строго увеличился T→T+1. Системные часы и пользовательские профили не менялись.
- Штатный import_anki_package установленного Anki25.09.4 без options обновил ровно одну старую заметку и добавил одну новую (2→3). Перевод проверен по сохранённым полям. Исключённый при повторной выгрузке уровень10 остался целиком, прежние note ID/GUID/card ID, заданное расписание и строка revlog сохранены. Повтор второго файла дал duplicate2, новых0.
- Дополнительный естественный прогон через отдельные JSON-процессы без подмены времени также подтвердил updated1/new1, сохранность прежних карточек и duplicate2 при повторе. Оба прогона выполнены на отдельных временных SQLite и коллекциях, AnkiConnect принудительно направлен на закрытый loopback-порт9. GUI и замороженный мост в этом изменении не проверены. Коммита нет.

## 2026-11-24 — Бэкенд-разработчик: выбор объёма и повторный экспорт

- `library_view.py`, `contracts.py`, `export_cards.py`: `newBatch.availableIds` даёт все подходящие к новой выгрузке ID в том же порядке, что и прежняя порция. `ids` — префикс, `count` — её размер. Писатель повторно фильтрует присланные ID по актуальному каталогу и тому же рассчитанному списку. В обеих v4-фикстурах добавлено поле. Регрессия выгрузила 103 записи, отсеяла прежний экспорт, `skip`, повторяющийся ID и необработанную запись даже с `learn`, включила `rejected + learn`.
- По уточнению владельца `export_words scope=library` выгружает только явно переданные ID, включая предварительные, ранее отправленные и исключённые вручную. Проверяет актуальные `levels` от 1 до 10, сохраняет порядок запроса, удаляет повтор ID в запросе. После успешной записи файла или подтверждения Anki сохраняет историю со схемным scope `again` и фактическим `is_repeat`; личные решения не меняет. TSV использует штатную схему. Для Obsidian возвращается `no_destination`. Отдельный `export_library_file` не добавлялся, миграции нет.
- `anki_export.py`: повтор для того же ID использует прежний GUID, текущие поля и тег «повтор». Исправлен одинаковый `notes.mod` при экспорте в ту же секунду. Под блокировкой учитываются история выбранных слов и время готовых `.apkg` в папке, в том числе после потери ответа AnkiConnect. Перед записью пакет однократно ждёт границу секунды и перечитывает часы. При откате нет ожидания до будущего времени и искусственных отметок. Контрольные тесты проверили историю, файл без подтверждения и откат часов.
- Целевой прогон 127 прошли, полная серия после синхронизации TS-контракта 337 прошли, 1 пропущен. Ruff для изменённых Python и тестов, compileall и git diff --check прошли. Первое чтение новых тестов остановилось на лишней запятой в тестовом comprehension; исправлено до прогона. Сам проверял содержимое `.apkg` и локальный двойник AnkiConnect. Нативный прогон Anki ведёт инженер интеграции, замороженный bridge и устройство здесь не запускал.
- Отдельное наблюдение: временный экспорт `chose` до анализа, затем канонизация `choose` сохраняют историю, но дают другой GUID после смены канонического ID. Проблема воспроизведена на временной базе, озвучена тимлиду и требует отдельного решения о сохранении идентичности карточки при смене ID. Фикс равных секунд этого сценария не покрывает.
- SHA-256 к упаковке: `anki_export.py` E34531B58F224E4E7D0FE274712E531DA344422AB231CE49736CDB17EAA03212; `export_cards.py` 3F8F3080D3073F15574162FCCADAEBB5526A792C397413D5C0A95E6718C24243; `contracts.py` CFADB0660466253E959CAF8208A5EA5F8098B6BC921731DBC7E639398EABC102; `library_state.py` BFCEFA733CF45A8595E26BD723B312C84523C43A2387F5920599618B0FD4B7A3; `library_view.py` 348DA2C1CA840E3AA715F6E409F95B1D6328CA73DA6AF109FDF605505BDFE6B7. База ed88fa9, коммит и публикация не выполнялись.

## 2026-11-24 — QA-инженер: независимый браузерный smoke читательского стола

- Проверен стенд 1443 в отдельном Chromium с синтетическими mixed, large, export-error и no-reader. Browser plugin отсутствует, использован локальный Playwright CLI. Продуктовые исходники, личная библиотека и устройство не затронуты. Сборку, общий CI и native по распределению тимлида выполняют другие линии.
- Полный режим по умолчанию: 133 слова, предпросмотр первых пяти. После решения «Не учить» для admit полный запрос всё равно содержит его и 00:17, scope=library, 133 ID и уровни 1..10. Повторная выгрузка содержит те же 133. Исключение уровня 10 даёт 132 и удаляет уровень и соответствующий ID из запроса. Выбор TSV в Настройках и выгрузка 132 завершились состоянием готового файла. Payload наблюдался тестовой вставкой логирования в ответ mock-модуля браузера без изменения поведения и файлов продукта; это не проверка настоящего файла или Anki.
- Порция 101 отправляет scope=new и 101 ID; последующий режим всех новых отправляет оставшиеся 24 без пересечения. Ноль, отрицательное, дробное и пустое число блокируют выгрузку. Все снятые уровни блокируют кнопку, уровень 8 сохраняет вручную отклонённый vigilant в предпросмотре. Замечание о фиксированных размерах в Настройках снято после уточнения: произвольный разовый размер вводится на Главной.
- Первая реплика появилась примерно через 8 секунд, текст рос посимвольно, фокус оставался на BODY. Полный текст доступен отдельно, aria-live=off, Escape закрывает. Отключение реплик сохраняется после reload, за следующие 8.5 секунды сообщения нет. Reduced-motion сразу показывает полную реплику без печати, animation:none для огня и световых групп. Огонь меняет transform в обычном режиме. При тестовой подмене visibilityState и событии visibilitychange сцена неактивна, transform неподвижен и реплика не появляется за 9 секунд; после возврата таймер продолжается. Это имитация скрытия, не проверка настоящей фоновой вкладки. «Найти Kindle» убирает открытую реплику; ошибка экспорта подавляет её более 8.5 секунды, повтор и навигация доступны. Поиск в no-reader заканчивается и снова доступен. Финальный проход без pageerror.
- Меню приоритетов проверено на 1440 и 600 в тёмной теме: Enter/Space, Home/End, Enter выбора, Escape с возвратом фокуса; 11 radio-пунктов и четыре смысловые группы, выбор 10 оставляет 00:17. Нативный SELECT книги сохранён. Видимые виртуализированные строки содержат непустые причины, совпадающие с mock study_priority.reason. Меню помещается в окно, горизонтального переполнения на 600 нет. Снимки 1440 dark, 600 day и меню dark на обеих ширинах сохранены во временном каталоге kindle-home-speech-qa и просмотрены; дневная сцена без видимого пула света.
- Во время разработки HMR давал временную ошибку несовместимых main и export hook; на свежих загрузках не воспроизведена. Таймауты тестового стенда из-за переименованных заголовка и кнопки «Попробовать снова», узкой навигации и отложенного фокуса Radix исправлены в проверках, за дефекты продукта не приняты. Порционный проход дошёл до всех утверждений, затем остановился на отсутствующем в узкой навигации переключателе темы; дневной снимок получен штатно через Настройки.
- Ограничения: следующий интервал реплик 45–80 секунд, полный обход всех виртуализированных строк, реальная фоновая вкладка, физическое устройство, настоящий Anki/TSV, frozen bridge, установщик и другие браузеры в этой партии не проверялись. Дефектов, блокирующих проверенный браузерный маршрут, не найдено. Коммитов нет.

## 2026-11-24 — Фронтенд: компактная геометрия лиса после ревью
- Только fox-lantern.css: убран безусловный верхний резерв 104px. На 521–680px сцена сохраняет правый карман речи и фигуры, текст ограничен с учётом ширины облачка. Под 520px постоянный float резервирует колонку персонажа, а ниже него текст возвращается на всю ширину. Высота зависит от содержимого, речь не меняет геометрию. Локальная карандашная линия под лапами привязана к baseline фигуры в узкой композиции.
- Проверены Range.getClientRects всех видимых текстовых узлов против bbox головы, тела, хвоста, фонаря и облачка: 600/390/360 × заполненная/пустая Главная × открытая/закрытая речь — 12 сочетаний без пересечений, координаты h1 и сцены до/после речи совпали. Дополнительно получены кадры preparing на этих ширинах. Снимки fox-geometry-* в ignored .app-data. Итог 600 просмотрен и принят ведущим. npm run build прошёл; предыдущие focused тесты остаются пройдены, изменения только CSS. По замечанию ведущего удалена лишняя пустая строка в конце, git diff --check по CSS чистый. Без коммита, native не запускался.

## 2026-11-24 — Инженер интеграции с Anki — Предварительная форма после канонизации

- По поручению ведущего согласовал fixture с бэкенд-разработчиком. На временном Kindle vocab.db сохранены chose со stem=chose и контекст «She chose a book from the shelf». Все действия import_reader_file, save_card_edit, export_words, process_queue и load_library выполнялись через отдельные свежие Python-процессы JSON-dispatch.
- Первая полная выгрузка до обработки импортирована штатным import_anki_package Anki25.09.4 с настройками по умолчанию: new1. Карточке заданы review type/queue, due411, interval31, factor2450, reps7, lapses1 и одна запись revlog.
- process_queue обработал одно слово; повторный импорт той же базы закрепил choose с другим каноническим ID. Сохранённый перевод пережил переход, затем для нового ID задан новый перевод и сделана повторная полная выгрузка. Anki подтвердил updated1/new0: ровно одна заметка и карточка с прежними GUID/noteID/cardID, полным расписанием и revlog. Lemma стала choose, LexemeId соответствует новому ID, Meaning обновился; исходные Word и Context сохранились. Повтор второго пакета дал duplicate1/new0.
- Использованы новая временная SQLite и отдельная коллекция установленного Anki Python backend. AnkiConnect в test-wrapper направлен на закрытый loopback-порт9; личные данные и профили не открывались. Код приложения не менялся, схема и исправление принадлежит бэкенду. GUI, frozen bridge и объединение двух уже выгруженных форм здесь не проверялись. Изменён только WORKLOG.md, коммита нет.

## 2026-11-24 — Тимлид. Читательский стол и полная выгрузка

Планёрка с продактом и UX зафиксирована в docs/plan/meetings.md. Владелец выбрал полную выгрузку в обычное назначение и исключение отдельных уровней. Пересмотренный контракт отражён в PRODUCT.md и README.md с отдельным описанием для внутренней версии. Текущее основание — ed88fa9. Публикация не запрашивалась.

В main.tsx, Home, контроллере библиотеки, настройках, типах и browser mock подключены три режима. Весь каталог отправляет снимок ID и уровней, новые учебные — весь остаток либо указанную на Главной порцию. На кнопке фактический размер, в списке максимум пять примеров. Учебный размер по умолчанию сохраняет прежние значения настроек. Ручной поиск обходит задержку фонового опроса, совместно использует выполняющийся запрос и показывает результат. Поиск использует действующее обнаружение дисковых и MTP/WPD устройств.

На ревью попросил переделать прямоугольное облачко, добавить неровное мерцание, убрать пустой верхний отступ и освободить текст от пересечений с рисунком при 600 px. Проверены итоговые кадры. UI-дизайнер принял образ, предложил равномерно разложить десять уровней выбора. Теперь у уровней две строки по пять. UX-исследователь проверил видимое до отправки пояснение о правках в Anki и доступную кнопку поиска, согласовал внутреннюю поставку. Код библиотеки показывает причину в строке, число реальных сохранённых записей поиска и известных книг в карточке. Открытое меню ночной темы просмотрено.

Проверены 142 frontend-теста и штатный Vite build. QA проверил 133 слова, 132 после снятия уровня 10, порцию 101 и следующие 24 без пересечения, пустой выбор, клавиатуру, автоматическую печать и уменьшение движения. Для большого объёма использовали синтетику. Штатный Anki в отдельной коллекции подтвердил обновление перевода, добавление нового слова, сохранение расписания и пропущенного уровня. Нашли два краевых случая — одинаковую секунду сохранения и смену ID предварительной формы после обработки. Бэкенд учёл секундную точность времени импорта и сохраняет идентичность Anki при канонизации. На тестовой паре chose → choose после канонизации подтверждены одна заметка, прежние идентификаторы и история повторений. Автоматическое обновление полей зависит от настроек Anki. Проверка в этой коллекции использовала импорт пакета, а не пользовательский AnkiConnect.

## 2026-11-24 — Бэкенд-разработчик: GUID Anki после канонизации

- `library_state.py` и `library_repository.py` сохраняют ключ заметки отдельно от текущего ID лексемы в существующей таблице metadata. Резервирование идёт транзакционно до записи пакета. Смена ключа под тем же ID и последующая замена каталога переносят привязку. Перед заменой каталогов прежние ID принимаются из сохранившейся истории Anki и legacy-назначения. Если при слиянии у сохранившейся формы есть ключ, используется он. Ключ второй заметки остаётся зарезервированным, чтобы другой лексеме не достался прежний GUID. Операций удаления в Anki и новой миграции нет.
- `export_cards.py`, `anki_export.py` и `tauri_bridge.py` используют резервацию в штатном и совместимом .apkg-путях. GUID строится из сохранённого ключа, поле LexemeId содержит текущий ID. `tests/test_export_words.py` проверяет обычный импорт, очередь и повторный импорт при chose → choose, перенос из старой истории и выбор заметки при слиянии двух уже выгруженных форм.
- Инженер Anki проверил весь переход через отдельные процессы JSON-моста и штатный импорт Anki 25.09.4 на временной коллекции. Импорт обновил одну заметку и добавил ноль. Совпали GUID, note/card ID, расписание и revlog. Lemma, LexemeId и Meaning обновились. Повтор дал одну уже существующую заметку и ноль новых.
- Целевой прогон 100 прошли. Полный pytest 340 прошли, 1 пропущен. Ruff по списку CI и изменённому тесту, compileall и git diff --check прошли. Восстановление до появления резервации ограничено прежними связями, которые ещё есть в SQLite. Замороженный мост и физический Kindle здесь не проверял. База ed88fa9, коммит не создавался.
- SHA-256 для упаковки: `anki_export.py` C196156C191A084CCA8E3667F65ACCC6323F3186E506773865E3D8D386E8D2BC, `export_cards.py` A7A60523155654912800D029BA529E37553B1AC5D8B1E433AA0328D9366B6BD6, `library_repository.py` 108569C932B88A239F83719B4227984F21953D9991B4885FAF7EFB7F4B434ACB, `library_state.py` 776F0BB86A2D1EE61845D3E95524F903D0EAD18BFA10A5CA5029D154CF0A2CAA, `tauri_bridge.py` 533C31E9E4E3BA68EFC69BE3D4EF74D98AD4293B95CA05853A79C29DC3CD6BB3.

### Внутренняя сборка читательского стола

Производственный код, тесты и продуктовые документы зафиксированы локально в 9f77358. Итог Python — 340 passed, 1 skipped, Ruff прошёл. Для внутреннего EXE используется com.kindlevocab.cards.preview и заголовок «Kindle Cards — Читательский стол · 9f77358». Первая попытка Cargo с неполным окружением попыталась пересобрать зависимости и остановилась на блокировке build-script Windows. Сборка с conda kindle_app и прежним профилем build override прошла.

При сверке обнаружилась вложенная копия bridge после повторного PyInstaller. Тимлид сохранил исходную staging-папку отдельно и перенёс чистый конечный результат. SHA-256 итогового EXE 99918291010cbc00d1877af6338c47b53ccf8c8d5d75bf981385c09c9e74b941; итогового bridge 6fbb5a4f9400cb748106d49c5a1ac2d80318c9ad36044ff24b74d5950d089c63. Все 258 файлов совпали с результатом повторной упаковки; его smoke проверил штатную обработку и чтение UTF-8 после перезапуска. Список контрольных сумм лежит рядом с EXE в build/internal-reading-desk. Предыдущая версия запущена у владельца, новая выдана отдельным путём. Личные данные и открытое старое окно для приёмки не используются.

Финальная нативная приёмка 9f77358 пройдена на чистом временном профиле Windows WebView2 с тремя вымышленными словами. В действительном окне лис автоматически показал полную рукописную реплику. Кнопка поиска вернула состояние отключённой читалки через тестовый адаптер. Просмотрены снимки Главной и раскрытого ночного меню «Слова». Проверены три отдельных TSV из поставляемого bridge, включая состав строк по Base form. Без приоритета 10 записались glimpse и harbor, полный файл добавил 00:17, повтор сохранил все три слова. Ошибок страницы не зарегистрировано. Нативный поиск с физической читалкой в этом прогоне не выполнялся. Первый сценарий QA пытался ждать реплику сразу после нажатия поиска 30 секунд, что короче предусмотренной паузы; в завершающем сценарии естественная реплика проверена до поиска. Окно закрыто только для собственного тестового процесса.

## 2026-11-24 — Первая попытка native-приёмки читательского стола
- Запущена отдельная сборка в изолированном временном профиле с синтетической библиотекой и подменой connector_status; действие «Найти Kindle» завершилось состоянием «Читалка не найдена».
- Сценарий остановился на ожидании автоматической реплики через 30 секунд: после поиска штатный quiet откладывает её на 60 секунд. Окно теста закрыто своим процессом; выгрузки и снимки в этом прогоне не проверены. Завершающий прогон передан ведущему. Реальные данные, устройство и другие окна не затронуты.

## 2026-11-24 — Тимлид. Планёрка об общей полезности слова

Продакт, инженер ранжирования, бэкенд и QA независимо рассмотрели запуск без истории, затем разобрали взаимные возражения о частых связках, артиклях, фразовых глаголах и метрике повторов. На 9f77358 воспроизведён штатный импорт синтетического vocab.db, обработка и загрузка восьми записей с одним поиском в одной книге. У enough уровень 4, although 3, sword и borrow 1. В контроле без штрафа за высокую частоту the поднимается с 8 до 1. Бэкенд отдельно подтвердил потерю признака выражения take off и ограниченность восстановления старых ключей. Наблюдения характеризуют поведение модели, а не предпочтения читателей.

В docs/plan/meetings.md записаны альтернативы, возражения, решение и обязанности. Сначала сравним действующую модель, одну частоту, снятие штрафа и ограниченный гибрид. Книжный охват и учебное ядро NGSL остаются отдельными исследовательскими гипотезами. Первый опыт — слепые пары, следующий — отложенные книги и отдельная проверка длинной истории. Открыты описания источников; загрузок наборов, правок модели, пересчёта личной библиотеки и новой сборки не было. Рабочая версия остаётся 9f77358.


## 2026-11-24 — Инженер ранжирования: офлайн-прототип по открытым словарным признакам

- В scripts/research/reading_priority.py добавлены точное нормализованное сопоставление формы CYP-LEX, Zipf wordfreq для одиночной формы, CEFR только при однозначном POS и уровне. Контракт четырёх векторов включает сглаженный logit книжного охвата, индикаторы пропусков и опциональный CEFR one-hot. CLI читает веса из JSON и выводит исследовательские уровни и причины. Без весов показывается доля книг и отдельно частотный резерв. B1 не задаёт уровень автоматически. Только непустые записи без букв получают 10; недостаток признаков даёт предварительную 6.
- Восемь тестов тестового модуля, Ruff и diff --check прошли. Первый pytest встретил отказ доступа к общему Windows temp, отдельный ignored --basetemp устранил проблему. Smoke CLI на имеющихся локальных CYP-LEX и CEFR проверил точные формы, POS, выражение и запись из цифр и знаков. Для вывода о пользе читателям требуется независимая выборка; оценщик и обучение ведёт тимлид. Продуктовые файлы, личная библиотека и пользовательские данные не использовались. Коммита нет.


## 2026-11-24 — Инженер ранжирования: человеческая оценка поверх книжного прогноза

- Выделены scripts/research/study_value.py и tests/test_study_value_research.py. Единый загрузчик исключает 30 единиц контрольных испытаний Wang et al., пустые строки и все варианты дублированного ключа после NFKC/casefold. Raw и независимо подготовленный clean TSV дают один и тот же словарь из 82 848 форм. Ручной POS не выбирает значение в BWS.
- Базовый книжный прогноз берётся из JSON. При неизвестном книжном охвате используется отдельно обученный частотный прогноз, когда доступна Zipf. С наблюдаемой оценкой людей одиночная форма получает ограниченную поправку по остатку к ожидаемой оценке. Максимальное изменение 0,05, strength 0 сохраняет базовый балл. Если книжного прогноза нет, прямая человеческая оценка остаётся видимой у предварительного уровня 6 и разрешает равенства в этом классе. Уровень 10 сохраняет структурный смысл.
- 16 focused тестов обеих линий, Ruff и diff --check прошли. CLI проверен на синтетических JSON и TSV в отдельном процессе. Влияние поправки и её значение по умолчанию определяет внешняя оценка ведущего. Продуктовая модель и личная библиотека не использовались. Коммита нет.


## 2026-11-24 — Исследование внешних оценок полезности слов

- Сверил первоисточник Wang, Brysbaert & Günther (2026, DOI 10.3758/s13428-026-03051-8) и OSF 4nwgx. Балл Utility основан на ответах 5 526 взрослых носителей английского из США и Великобритании. GPT использован для предварительного отбора по знакомости и анализа признаков. В исследовании 82 880 основных стимулов, включая 47 987 выражений. Оценки даны без контекста. Сама статья CC BY 4.0, а агрегат явно открыт для науки и образования, отдельная лицензия OSF для поставки не указана.
- Добавил scripts/research/prepare_study_utility.py на стандартной библиотеке. Исходные XLSX и список контрольных предъявлений хранятся во временной папке. Из 82 892 строк исключены 30 контрольных единиц, 12 строк с 6 дублированными формами и 2 строки без Utility. Повторная конвертация дала 82 848 строк и тот же SHA-256 86ed5370b7643e99e794e588a0b841fe20b102a2cd6fe96fc0800843065b8d22.
- Из опубликованного Appendix 10 Dang, Webb & Coxhead (DOI 10.1177/1362168820911189, CC BY-NC 4.0) извлечены все 146 строк. Прямой загрузчик PDF и ссылки Wiley на таблицу He & Godfroid вернули 403. Приложение Dang удалось прочитать через веб-инструмент, локальный PDF не получен. На 145 совпадающих формах Spearman с оценкой преподавателей: Wang .090, Multilex Zipf .282, CYP-LEX 13+ охват книг .053, CYP-LEX 13+ Zipf .178. Это усечённая выборка со средними баллами 4.00–4.82 и знанием не менее 90%, без подтверждения переноса на читательский выбор.
- Скачал размеченные тестовые TSV CompLex CC BY 4.0 (917 отдельных слов и 184 выражения) для проверок контекстной сложности. В репозиторий вошёл только конвертер. Данные читателей не использованы, продуктовый рейтинг не менялся. Ruff в conda kindle_app, py_compile, повтор конвертации, сверка checksum и diff --check прошли. В базовом Python Ruff отсутствует. Коммита нет.



## 2026-11-24 — Инженер ранжирования: справочный корпус для непокрытых форм

- В study_value.py добавлен опциональный JSON справочных книг и режим --resources. Точное попадание при отсутствии базового прогноза даёт сглаженный счётчик книг с указанием охвата выборки. Непокрытая одиночная форма из ASCII-букв получает временный балл класса с прежними порогами и флагом provisional. Непокрытые выражения сохраняют предварительный уровень 6 и имеющуюся человеческую оценку, структурные записи — уровень 10. Продуктовый интерфейс не менялся.
- 18 focused тестов, Ruff после устранения замечаний о склейке строк и diff --check прошли. Проверены отдельные файлы и --resources в изолированном CLI. Интеграцию собранного справочного корпуса и внешнюю оценку ведёт тимлид. Пользовательские данные не использовались. Коммита нет.

## 2026-11-24 — Тимлид. Внешние данные и исследовательское ранжирование для чтения

- Запрос владельца уточнён в двух раундах. Обязательный B1→1 снят. Для исследования применены 6.2 Sol и отдельная методологическая рецензия 6.2 Astra. В AGENTS.md исправлены старые назначения Sol и blanket-запрет Astra по выбору владельца. Обсуждение зафиксировано в docs/plan/meetings.md, подробный протокол и источники в docs/plan/reading-priority-research.md.
- Исследовательские программы находятся в scripts/research. Проверены исходные CYP-LEX, CEFR-J/Octanove, ELTeC, Gutenberg, нормы Wang, оценки Dang. Рабочие ресурсы, модели и отчёты подготовлены в игнорируемой .app-data/reading-priority-study. Данные OSF Wang имеют разрешение для исследований и образования; включение в публичную поставку не согласовано. Продуктовую версию 9f77358, личную базу, настройки и экспорты исследование не меняет.
- 8 000 форм, 400 списков по 20, 42 обучающих, 17 проверочных и 22 отложенных романа разных групп авторов. При равном единичном синтетическом поиске контроль функции rank даёт 0,2299 nDCG@5, общая частота 0,6111, книжный охват 0,6662, их комбинация с CEFR 0,6735. Это оценка повторной встречи. Педагогическую модель проверяли на 6 664 скрытых формах и независимых оценках 145 слов преподавателями. Рабочий CLI с поправкой 0,5 даёт 0,6669 по книжному критерию против 0,6708 при нулевой. Улучшение учебной пользы для целевой аудитории пока не установлено.
- В пилоте равные линейные пороги помещали слишком много редких форм в одну группу. Сравнили фактический порядок CLI после переноса на фиксированные неравномерные интервалы. Для непокрытых слов предусмотрен предварительный прогноз класса, для выражений — отдельный счётчик точной последовательности в обучающих книгах. При обновлении границ два теста ещё ожидали прежний порядок; ожидания скорректированы и целевой прогон полностью пройден. Для сборки учебного набора не добавлены зависимости в приложение. Проверены обычный CLI на локальных наборах, режим без поправки, единичные слова, фразы, неизвестная форма и структурная запись. 131 тест ранжирования и исследовательской линии прошёл, Ruff и git diff --check прошли. Пользовательская сборка и личный ranking_eval не запускались.

Независимая заключительная проверка. Исследователь корпусов повторил оба обучающих CLI из исходных таблиц и текстов в отдельный временный каталог. Все шесть JSON побайтно совпали с локальным исследовательским набором. Фактические уровни примеров подтверждены. По его замечанию в отчёте уточнено ограничение поправки концами шкалы 0 и 1, применение только к непредварительным одиночным формам и добавлена контрольная сумма таблицы авторов ELTeC.

## 2026-11-24 — Подготовка приватной сборки Open Research
- Подготовил ignored staging `build/internal-openresearch-coverage/` и Tauri-конфиг с ID `com.kindlevocab.cards.preview`. Проверил PyInstaller 6.22.3, Cargo 1.96.1, Node v26.4.0 и наличие Tauri CLI и локальных NLTK-ресурсов.
- Frozen lookup ожидает компактную модель рядом с мостом в `models/rp-v2-coverage.sqlite`. Исходная локальная модель существует. Условия CONLIT остаются в исследовательской документации. Модель пока не копировал.
- После сигнала сверить ревизию и входные SHA-256, собрать новый мост и Tauri, положить модель только в staging `bridge/models`, проверить синтетический import/reload/export и сверить SHA-256. Компиляцию и smoke пока не запускал. Менял только staging-конфиг и журнал.

## 2026-11-24 — Инженер ранжирования. Локальная проекция RP-V2

- Добавлены kindle_vocab_app/book_coverage.py, scripts/import_openresearch_coverage.py и tests/test_book_coverage.py. Импорт проверяет фиксированный SHA-256 ranker.json.gz, читает исходный gzip или тот же вложенный ресурс из research-kit-v2.zip и атомарно заменяет игнорируемую .app-data/models/rp-v2-coverage.sqlite. В проекции только точные значения coverage, связи aliases и хеш источника. Равный вес авторов указан в русской причине доли современных романов. Для непокрытых, невалидных форм и выражений используется отдельная причина предварительного уровня 6. Уровни 1–9 используют восемь исследовательских порогов, математический ноль отличается от пропуска, небольшие положительные доли не округляются до нуля.
- Текущий workspace заполнен из имеющегося research-kit-v2.zip. Импорт напрямую из gzip в отдельный игнорируемый каталог дал побайтно тот же результат. SHA-256 проекции 17987a224bb01452aef7e87379552c52355e75dc45537c2c442fb6f922de6e1e, 4 628 480 байт, 184 933 строки, 1 885 aliases, 3 263 NULL. SQLite integrity_check и полная сверка таблиц с исходником прошли. 186 827 вызовов совпали по числу или его отсутствию с rank.py score_record для coverage. Переход к одной транзакции чтения на запрос уменьшил время замера 10 000 индексных обращений с 2,236 до 0,086 с на этой машине.
- Четыре адресных pytest, Ruff и diff --check прошли. Точный ноль проверен синтетикой, поскольку в зафиксированном источнике его нет. Первый запуск временной сверки через -m с относительным именем модуля отклонён Python, запуск файла с рабочим корнем в PYTHONPATH прошёл. Portable fallback рядом с frozen sys.executable проверен синтетически, реальный frozen bridge в этой линии не запускался. Корпус и пользовательские данные не скачивались, упаковка и пользовательская библиотека не менялись, коммита нет.

## 2026-11-24 — Подготовка native-приёмки RP-V2
- Подготовлена временная копия изолированного драйвера с пятью вымышленными записями и проверкой списка и карточек. Прокси возвращает отключённый Kindle и пропускает только необходимые операции к штатному bridge.
- До получения точного EXE приложение и тест не запускались. Итоговые уровни и причины необходимо сверить после готовности модели и сборки; личная библиотека и устройство не использовались.

## 2026-11-24 — Бэкенд-разработчик. RP-V2 в библиотеке и экспорте

- Подключил один локальный снимок книжного охвата к ответам библиотеки, решениям и экспорту. В `library_view.py`, `tauri_bridge.py`, `export_cards.py` и `contracts.py` добавлен `studyPrioritySource`; без модели остаются прежние приоритет и порядок новой порции. При наличии модели готовые и отклонённые записи оцениваются без обязательной даты поиска, ожидающие и ошибки получают предварительный 6, а обработанные записи без букв — 10. Совпадающая исходная форма разрешает alias. Многословный display_form сохраняется для оценки целого выражения. Старые полки, допустимость новых слов и Anki-ключи не менялись.
- Новая порция сортирует допущенные слова по группам: измеренные, предварительные, структурные 10. При равном уровне учитываются балл и ID. Полный экспорт требует явный снимок ID, сохраняет его порядок и проверяет текущий уровень.
- В `tests/test_export_words.py` отдельные процессы JSON-моста проверяют режимы без локальной модели и с синтетической SQLite-моделью, решение, явный и неявный scope=new, scope=library с уровнями и отказ при пропущенном снимке. Прошли 71 проверка экспорта, библиотеки и загрузки модели, Ruff для изменённых файлов с исключением старого BLE001 в tauri_bridge.py, а также git diff --check.
- Нативная сборка, личная библиотека, устройство и Anki в новом сценарии не запускались. Ранее утраченная при канонизации исходная фраза из SQLite не восстановится. Коммит не создавал.


## 2026-11-24 — Фронтенд. Порядок RP-V2 по книжному охвату

- Источник studyPrioritySource проходит из снимка библиотеки в Главную и каталог, а после set_decision читается из ответа или наследуется для старого моста. Каталог и полный экспорт сортируют общим компаратором RP-V2 по классу (измеренные 1–9, предварительные, структурный 10), уровню, баллу по убыванию и ID. Главная считает уровни отдельно от порядка; фильтр полного экспорта сохраняет последовательность выбранных записей. Состав «Все новые» и «Порция» прежний, их порядок уже приходит в newBatch.availableIds от backend. Точный фильтр уровня и смысл галочек сохранены.
- При RP-V2 скрыты старые объяснения важности и предупреждение о малом числе поисков. Причина приоритета приходит из study_priority, реальные числа сохранённых поисков и книг в карточке доступны отдельно. Legacy порядок и объяснения сохранены. Браузерный пример ?scenario=coverage использует вымышленные фиксированные доли, неизвестные уровни и структурную запись. Старые сценарии mock сохранены.
- Сверены с backend порядок новых слов, фильтрация снимка и порядок экспорта каталога. TypeScript, production Vite в отдельный игнорируемый каталог, полный Vitest (145/145) и diff --check по src прошли. Первичный Vitest в песочнице Windows упал при чтении esbuild родительского пути конфига; повтор вне песочницы прошёл. npm сообщил о предупреждении существующего allow-scripts.
- Ручной браузер, нативный Tauri и файловый экспорт этой линией не запускались. Правки только src и эта запись; без коммита.


## 2026-11-24 — QA-инженер. Независимая проверка RP-V2

- Chromium, локальный Vite, сценарии coverage и mixed. На 1440×1700 проверены все 13 строк: восемь рассчитанных, включая уровни 8 и 9 перед четырьмя предварительными 6, структурный 10 в конце. Равные баллы dread и glimpse сохраняют порядок ID. Фильтр уровня 6 оставляет сначала рассчитанное слово, после сброса возвращаются исходный состав и порядок. Первые пять на Главной совпадают с каталогом, выключение и включение уровня 2 сохраняет порядок. В mixed сохранились прежнее возрастание уровней и порядок предпросмотра. Ошибок страницы нет.
- На 600×900 проверены порция из трёх слов и полный режим с выключенным уровнем 10. Порядок ID порции совпадает с предпросмотром, полный запрос содержит 12 ID и уровни 1–9. Оба mock-экспорта завершились. Запросы наблюдались через временное логирование в браузерной копии mock-модуля. Снимки сохранены во временном QA-каталоге, узкий кадр просмотрен, горизонтального переполнения нет.
- Реальная локальная проекция импортирована из имеющегося ranker.json.gz во временный профиль с 13 синтетическими записями. Отдельные штатные JSON-процессы проверили load_library и export_words. Сортировка newBatch совпала с независимой проверкой по SQL-значениям, включая разные баллы одного уровня и готовый 9 перед предварительным 6 и структурным 10. Порция дала пять строк TSV в порядке рейтинга при обратном списке ID запроса. Полный режим без 10 дал 12 строк в порядке снимка, включая прежние пять. После снятия модели мост вернул legacy и все 13 записей. 71 адресный pytest прошёл.
- При первичном обзоре передано отсутствующее подключение source в каталоге промежуточного дерева. Финальный smoke подтвердил исправление. Перезапуск Vite после запрета esbuild на обход родительского каталога прошёл с одобренным запуском. Риск замены модели между preview и выгрузкой рассмотрен по коду, гонка не воспроизводилась в проверке. Установщик, физическая читалка, реальные Anki и личная библиотека не использовались. Исходники не менялись, основа 9f77358.

## 2026-11-24 — Внутренняя сборка Open Research
- Подготовлена приватная Tauri-сборка и свежий frozen bridge из текущего рабочего дерева. Модель `rp-v2-coverage.sqlite` скопирована только в `build/internal-openresearch-coverage/bridge/models/` после сверки ожидаемого SHA-256.
- Проверки bridge: стандартный frozen smoke, synthetic load_library с источником `rp-v2-coverage`; все 3 demo-записи получили приоритет. Офлайн модель совпала с утверждённым SHA. Vite и Tauri `--no-bundle` завершились успешно.
- Артефакты находятся только в ignored `build/internal-openresearch-coverage/`. Старые установленные/публичные сборки не менялись. Ручной native QA не выполнялся. Условия CONLIT сохранены в исследовательском документе и не перенесены в ресурсы поставки.

## 2026-11-24 — Изолированная native-приёмка RP-V2
- В отдельном WebView2 с пятью вымышленными заранее обработанными записями: borrow — уровень 2 и охват 72,32%, sword — 3 и 45,55%, harpoon — 7 и 4,64%. Они идут в этом порядке; причины указывают современные романы выборки и равный вес авторов.
- give up сохранилось как выражение с предварительным уровнем 6 и причиной отсутствия расчёта для целой фразы; 00:17 — уровень 10, «В записи нет букв». Карточки и читаемый ночной снимок списка проверены.
- Первый временный сценарий слишком рано снял очередь и показал предварительные оценки; повтор использовал готовые записи. Реальный импорт и переход очереди в этой приёмке не проверялись. Реальные данные, устройство и прочие окна не использовались; исходники не менялись.

## 2026-11-24 — Тимлид. Книжный охват Open Research RP-V2 в Kindle Cards

- Прочитал отчёт, определения исходов, исходный код ранжировщика, исследовательский реестр и исходную таблицу сравнения из комплекта RP-V2. Проверены SHA-256 архива и 128 записей манифеста. Зафиксированы обучение на 771 романе 636 авторов, проверка на 393 романах 315 авторов и результаты P@5 для охвата с равным весом авторов 0,7710, доли книг 0,7711, общей частоты 0,6442 и прежнего исследовательского варианта 0,6913. Методика и основания для локальной поставки описаны в PRODUCT.md и docs/plan/openresearch-integration.md, обсуждение записано в docs/plan/meetings.md.
- Согласовал единый порядок для каталога, предпросмотра, порций и полного экспорта. Продакт предложил общую частоту для пропусков; оставлена предварительная 6 с конкретной причиной, чтобы значение процента в списке было однозначным. UX-дизайнер указал, что стрелка сортировки вводит в заблуждение при 9 перед предварительной 6. Убран знак в заголовке, рядом с фильтром пояснён порядок. UI-дизайнер проверил узкое окно. Режим точных выражений на 422 пересказах доступен в локальной копии исследовательского CLI. Его результаты и off-line smoke подтверждены напрямую.
- Добавил необязательную проверку --coverage-workspace в ranking_eval.py. При одних и тех же двух общих временных срезах personal ranking_v2 дал AUC 0,642 и P@50 0,32; RP-V2 дал 0,589 и 0,05. Измеряется повторный поиск за 42 дня в одном профиле. В исследовании измеряется встреча в новой книге. Существующие показатели совпали до и после. Исходные записи читателя и личные слова в журнал не внесены.
- Первый полный pytest обнаружил, что проверка старого формата сравнивала новый необязательный ключ studyPrioritySource с прежним снимком. В tests/test_library_migrations.py добавил ключ в список расширений старого формата и отдельную проверку legacy. Финал — 363 passed, 1 skipped; frontend 145/145, TypeScript/Vite, Ruff изменённых модулей, compileall и diff --check прошли. Команда проверила браузер, реальный порядок TSV, обе ветви bridge и явно выбранные уровни. Условия CONLIT требуют уточнения для внешнего распространения.
- Выпущена локальная переносная сборка в build/internal-openresearch-coverage/ с отдельным именем и моделью в bridge/models. SHA-256 EXE 92f25096d735842e3d7d5a8cb1b500067efb947373949bbb3d728b771b94bf20. Проверил SHA-256 EXE, bridge и модели; сохранил манифест и указание источника рядом с EXE. Приёмщик проверил карточки в настоящем окне на пяти подготовленных записях. Дополнительно прогнал через frozen bridge импорт вымышленного vocab.db → очередь → загрузка новым процессом → повторный импорт. Получены уровни 2/3/7 для borrow/sword/harpoon, предварительная 6 для give up и 10 для 00:17. Повторный импорт добавил ноль слов. Коммерческая поставка, физическое устройство и реальная коллекция Anki не проверялись в этом изменении. Публичный релиз не выполнялся.

## 2026-11-24 — Подготовка staging Personal Priority
- Создан отдельный ignored-каталог `build/internal-personal-priority/` и проверен Tauri JSON-шаблон с preview ID `com.kindlevocab.cards.preview`.
- Подготовлен путь модели `.app-data/models/rp-v2-coverage.sqlite` для последующего копирования только в staging bridge/models. Production backend пока не замораживался, PyInstaller и Tauri не запускались.
- После сигнала обновить commit в заголовке, снять сигнатуры источников и собрать свежие bridge/EXE по прошлому рабочему staging-процессу. Проверки, smoke и WORKLOG выполнить после сборки.

## 2026-11-24 — Подготовка native-проверки Personal Priority
- Подготовлен отдельный временный сценарий с двумя синтетическими профилями: один поиск sword и отдельный профиль с поисками sword и give up в двух вымышленных книгах; также включена запись 00:17. Сценарий использует изолированный WebView2 и блокирует обнаружение читалки.
- Сборка до сигнала не запускалась. Ожидаются проверка причин, процентов и уровней в карточках и снимок; реальные данные и устройство не использованы.


## 2026-11-24 — Инженер ранжирования: поправка к книжному охвату по личным эпизодам

- В book_coverage.py реализовал чистую personalized_priority(base, lookups). Считает разные пары UTC-день и ключ книги, исключает записи без даты или ключа и источники с ключами koreader:/kobo:. Отдельного синтетического ключа без книги в исходниках не найдено, существующие резервные даты подставляются с пустым ключом. Первый поиск ничего не меняет, поправка ограничена множителем шансов 2.
- В результате coverage_score хранит исходный охват либо null. Неизмеренная запись остаётся на предварительном уровне 6, её score служит только для порядка среди предварительных. Прибавка сопровождается пояснением фактов, исходный процент не изменяется. У нулевого и полного охвата и структурных записей личной поправки нет.
- Первый граничный тест воспроизвёл пересечение двух порогов из-за округления непосредственно ниже 0,20. Явно ограничил повышение одним уровнем, сохранил формулу оценки. Первый прогон tmp_path также получил WinError 5 в общем каталоге pytest; повтор с отдельным ignored basetemp прошёл.
- tests/test_book_coverage.py: 15 прошли, Ruff и diff --check прошли. Проверены пороги, UTC и дубли, неполные источники, 0/null/1, разные пары эпизодов, предварительные записи и неизменность исходного объекта. Интеграция, итоговая сборка и ranking_eval с реальной библиотекой ведутся отдельно. Изменены только собственные файлы и эта запись. Базовый коммит 9f77358, собственного коммита нет.


## 2026-11-24 — Инженер ранжирования: точная граница личной поправки

- Устранил обнаруженный QA пограничный случай в personalized_priority. При C=0,60 и множителе 2 прежняя арифметика float давала 0,7499999999999999. Теперь поправка и классификация идут в точных дробях от кратчайшего десятичного представления входа, в payload возвращается float. Пороги заданы единым набором точных значений, включая 1/3. Прежний предел повышения на один уровень сохранён.
- Регрессия в tests/test_book_coverage.py проверяет 0,60 и соседний меньший float: первый даёт уровень 1 и score=0,75, второй остаётся на уровне 2. Целевые pytest 16 прошли, Ruff и git diff --check прошли. open_model и источник модели не трогал. Изменение в моей зоне заморожено; сборка и полный набор тестов не запускались. База 9f77358, собственного коммита нет.

## 2026-11-24 — Фронтенд: персональный приоритет RP-V2
- В src/types.ts добавлены rp-v2-personal и необязательный nullable coverage_score. Общий компаратор двух источников RP-V2 используется в каталоге, порядке выгрузки на Главной и mock-подборке: измеренные, предварительные (порядок по баллу при равном уровне), затем структурный 10.
- Главная и каталог выводят точное предложение моста о найденном основании для повышения, карточка показывает полный текст и отдельно фактические записи поиска. Если ожидаемого предложения нет, выводится полная причина. Для personal добавлена подсказка об охвате и повторных поисках. Режим выбирается по ответу моста.
- В mock ?scenario=personal есть зафиксированные ответы, без реализации формулы. Синтетический dread имеет три книги, книжный охват .60, итоговый .75 и уровень 1. Закреплены порядок, история примера, первое место новой порции, короткая причина и отсутствие прежних причин в карточке обоих режимов. Coverage остался отдельным совместимым сценарием.
- Vitest 147/147, TypeScript/Vite и git diff --check по src прошли. Browser plugin not available, использован Playwright. На 1440/600 проверены переход из Главной в карточку, короткая и полная причины, уровень 1 и подсказка каталога. Совместимый coverage проверен отдельно. Первый браузерный прогон выявил длинную причину в строке каталога, после общей функции сокращения повторный прогон прошёл. Снимки в игнорируемой папке .app-data/rpv2-personal-*.png. Нативный клиент, физическая читалка и личная библиотека не проверялись. Без коммита.
- При заморозке базовый mock coverage для dread также установлен на .60 (уровень 2). Регрессия сопоставляет его напрямую с coverage_score персонального сценария, где итог .75 и уровень 1. Повторные Vitest 147/147, TypeScript/Vite и diff --check по src прошли.


## 2026-11-24 — QA-инженер. Персональный приоритет RP-V2

- Проверен штатный внешний JSON-мост на изолированном профиле. 21 синтетическая запись проверяет единичный поиск, повтор в одной паре книга/UTC-день, границы UTC при разных смещениях, несколько книг, потолок прибавки, невалидную дату, пустую книгу, KOReader/Kobo в смеси с Kindle, записи Obsidian, края книжной шкалы, предварительную группу и структурный 10. Временная проекция содержит независимые значения C и не затрагивает ресурс поставки.
- В промежуточном коде воспроизведён пограничный дефект C=0,60 и m=2. Округление давало 0,7499999999999999 и уровень 2. После исправления подтверждены 0,75 и уровень 1; при C=0,599999999 уровень остаётся 2. Объяснение хранит исходные 60%. Независимый повтор прошёл целиком.
- Ручное «не учить» сохраняет приоритет и исключает запись из новых. Новая порция записала пять строк TSV в порядке рейтинга, полная выбранная выгрузка без уровня 10 записала четыре строки в порядке снимка. Перезагрузка после выгрузки не изменила приоритеты. Импорт вымышленного vocab.db через обычный вход и очередь дал три записи в двух книгах, m=1,5. Повторный импорт добавил ноль слов и сохранил три записи и оценку. Снятие модели включило legacy. 45 адресных pytest прошли.
- Chromium на отдельном Vite, сценарии personal, coverage и mixed. Проверены каталог, карточка, совпадение первых пяти с Главной, короткая причина повтора, исходные 60% в полной причине, лидер среди предварительных уровня 6 и структурный 10 в конце. Фильтр и сброс восстанавливают порядок, ручной пропуск исключает только из новых, legacy сохраняет прежний порядок. На 600×900 два вызова mock-выгрузки завершились: порция 3 с ID в порядке предпросмотра и полные 12 ID без уровня 10. Снимки сохранены во временном каталоге, узкий просмотрен. Финальный проход без ошибок страницы.
- Первые браузерные попытки выявили промежуточный HMR и неактуальное ожидание полного книжного пояснения в короткой строке; стабильная загрузка и проверка полной причины в карточке прошли. В промежуточном mock также передано несоответствие уровня и оценки dread. Исходники продукта не менялись. Нативное окно, реальный Anki и устройство в этой партии не использованы. Финальный расширенный корпус ожидается для отдельного контрольного прогона.

## 2026-11-24 — Инженер корпуса. Пересчёт авторского охвата современных романов

- В scripts/research/expand_novel_coverage.py воспроизвёл исходную модель на локальном CONLIT v1. Проверены SHA-256 обеих исходных таблиц и пяти замороженных файлов RP-V2. Совпали все 181 670 исходных измерений и контрольное P@5. Добавлены 251 взрослый англоязычный роман 2002–2016 годов, 189 авторов, ранее валидационная часть. Итого 1022 книги 825 авторов, 2001–2016. Не пересекаются ни идентификаторы, ни авторы обучения, 393 тестовых и всех 161 исходных книг, в том числе 24 источников списков, и юношеской части. Каждый автор по-прежнему имеет один голос.
- Приватный вывод .app-data/expanded-corpus/ranker.json.gz содержит 212 857 ключей, среди них 27 924 новых, плюс 1885 исходных соответствий форм. 126 ранее неизмеренных ключей получили охват, осталось 3137 null. Зарезервированные написания исходных alias не перехватывают прежние соответствия. Новые строки включают также имена и варианты написания. Из мешка слов порядок выражений не восстанавливался. Два независимых запуска дали одинаковый SHA-256 952f50b48899fa4e8fc34a85c8997a16f8e623ae97d589ca0a6ce180f307b842.
- На 240 неизменённых списках по 20 слов и 393 тестовых романах (315 авторов) P@5 с равным весом авторов 0,77100331 → 0,77094175. Из 471 600 сырых позиций попаданий 365 500 → 365 454. Состав пятёрки поменялся в 25 из 240 списков. Парная разность −0,00006155, 95% процентильный интервал для 5000 перевыборок тестовых авторов с фиксированными источниками [−0,00037610; +0,00025594]. Преимущество не установлено. Сохранился контрольный evaluation.json с числами и хешами входов. Тест оценивает встречу в книге. Тексты и данные читателей не использовались.
- Для внешних новых романов добавлен отдельный --supplement с проверкой метаданных, псевдонимов/фамилий контрольных авторов и дедупликацией произведений. По всем 2754 строкам CONLIT отсутствуют фамилии шести намеченных независимых авторов проверки. В tests/test_expand_novel_coverage.py прошли 3 проверки веса по автору и запрета пересечений. Первое замечание Ruff к оформлению исправлено, финальный Ruff и diff --check чисты. Данные и модель хранятся только в ignored .app-data. Личные поиски, качество запоминания, UI и native этой линией не проверялись. Коммита нет.


## 2026-11-24 — Инженер ранжирования: краткая причина личной поправки

- В personalized_priority добавлено опциональное personal_reason только при фактической прибавке. Оно описывает поиски в разные дни одной книги, поиски в разных книгах или обе причины. Для предварительной группы поле также присутствует, когда поправка влияет на порядок. Полное reason, исходный coverage_score, формула и open_model этой правкой не изменены.
- В своих тестах проверил три формулировки, предварительную группу и прежнее отсутствие поля без поправки, в том числе при нулевом и полном охвате. Целевой pytest: 17 прошли. Ruff и diff --check прошли. UI, полный набор и сборка в этой задаче не запускались. Собственного коммита нет.


## 2026-11-24 — QA-инженер. Расширенный ресурс RP-V2

- Кандидат ranker.json.gz с SHA-256 952f50b48899fa4e8fc34a85c8997a16f8e623ae97d589ca0a6ce180f307b842 совпал с разрешённой контрольной суммой загрузчика. Штатный импорт построил expanded SQLite в отдельном временном профиле. Внешний load_library при наличии обеих проекций выбрал расширенную: контрольная лемма получила обновлённый C и ожидаемый C′ с m=1,25, другая получила измеримый охват вместо предварительного.
- Повреждение только тестовой копии expanded восстановило прежние значения RP-V2, отсутствие обеих проекций включило legacy. В первом диагностическом запросе выбрана слишком широкая разница долей 5 п.п., подходящей строки не оказалось. Повтор с 0,1 п.п. дал наблюдаемую пару, критерий совпадения значений остался точным. Проверена загрузка ресурса и его приоритет, а не перенос качества на читателей. Исходники, рабочая библиотека, frozen bridge и установщик не менялись.

## 2026-11-24 — Фронтенд: короткая причина персонального приоритета
- После UI-ревью добавил необязательное personal_reason в StudyPriority и сценарий personal. Строки Главной и каталога берут его или reason, карточка сохраняет полную причину с исходным охватом. Разбор русского предложения и зависимость от пунктуации удалены. Регрессия проверяет самостоятельные формулировки и запасной вариант для coverage.
- Vitest 147/147, TypeScript/Vite и diff --check по src прошли. Финальная проверка этой правки выполнена на браузерных данных через Vitest, нативное окно и визуальный прогон после смены текста не запускались. Без коммита.


## 2026-11-24 — Бэкенд-разработчик: персональный приоритет RP-V2 в мосте

- В library_view.py подключил гибрид к готовым и отклонённым записям, для которых мост уже строил RP-V2. Продукт и оценка используют один фильтр is_personal_lookup: принимает датированные поиски Kindle с идентифицируемой книгой, точное выражение либо однословную форму из канонической группы. Пустые ключи книги исключены, поскольку хеш SQLite скрывает префикс исходного ID KOReader/Kobo. Структурные и ожидающие записи сохраняют прежнюю оценку, учёт ручных решений и экспортных событий прежний.
- В contracts.py описал rp-v2-personal, исходный coverage_score с возможным null и необязательную непустую строку personal_reason. Валидатор и подборка используют один порядок RP-V2. Регрессия обнаружила прежнюю проверку порядка по старому рангу и прошла после сверки с компаратором моста.
- В tests/test_export_words.py проверил порцию, фильтр полного TSV, сохранение приоритета после ручного решения, старые однословные формы, точное выражение, предварительную оценку и повторный импорт KOReader без книги. Отдельно проверены допустимые и недопустимые personal_reason. До последнего поля прошли 89 целевых тестов, с полем прошли 46 целевых тестов. Ruff, compileall и git diff --check в своей области прошли.
- Первый полный прогон дал 377 passed, 1 skipped и нестабильный PermissionError в тесте повторной загрузки обложки. Группа из 42 тестов с тем же тестом прошла. Физический Kindle, личная библиотека и упакованный клиент в этой проверке не задействованы.
- SHA-256 для заморозки: library_view.py D135447B, contracts.py A0AE610C. База 9f77358, собственного коммита нет.


## 2026-11-24 — Бэкенд-разработчик: итоговая проверка RP-V2

- Повторный полный pytest с отдельным basetemp прошёл: 382 passed, 1 skipped. Ошибка прав доступа в тесте обложки не повторилась. Финальные 46 целевых тестов прошли с personal_reason, сформированным моделью. Хеши моста совпадают с указанными при заморозке.

## 2026-11-24 — Пересборка frontend Personal Priority
- По подтверждённому финальному frontend состоянию (147 тестов, `personal_reason` без regexp) выполнены production Vite и Tauri `--no-bundle` в `build/internal-personal-priority/`.
- EXE пересобран с заголовком шаблонного commit и preview ID. SHA-256 промежуточного frontend EXE: `B0428BE4D789D3FDAD0E057F3D22D018A67B37297CB49DE98C620768C928E076`.
- Bridge и `rp-v2-expanded.sqlite` ещё ожидают отдельный pin, поэтому комплект не финализирован. Публичные артефакты не менялись.

## 2026-11-24 — Инженер по открытым текстам: современный роман для обучения

- Проверен полный англоязычный роман HarryBlank (Harry Blank) «The Breach Goes On: Bury the Survivors», опубликованный автором в SCP Wiki, завершён 2022-10-10. Источник https://scpwiki.com/bury-the-survivors-hub, CC BY-SA 3.0 https://creativecommons.org/licenses/by-sa/3.0/. Все 18 глав имеют отдельную атрибуцию автора и лицензию. Загружены HTML, в подсчёт вошли только абзацы между заголовком и навигацией. Иллюстрации, заголовки, элементы навигации, сноски и лицензии в текст не попали. Аудит 6671 абзаца не нашёл HTML-комментариев, служебных строк, повторов длинных абзацев или повторов четырёх последовательных абзацев длиной от 120 слов. Жанровый перекос одного романа ограничивает выводы об охвате современной прозы.
- scripts/research/open_training_novels.py сверяет автора и название со всеми 2754 строками CONLIT, автора дополнительно с замороженными группами и списком независимого внешнего контроля. POS Treebank/NLTK и WordNet отличаются от исходной токенизации CONLIT. Для совместимости исключены размеченные имена собственные и прописные акронимы, применены замороженные алиасы RP-V2, леммы ограничены положительными ключами train+validation. Словари тестовых книг для фильтрации не читались. Получено 186007 слов, 9331 лемма. Локальный манифест хранит SHA-256 исходных страниц, аудиты и версии NLP.
- Замороженные ignored-файлы .app-data/novel-training/training-presence.json и source-manifest.json в повторном прогоне из отдельной копии получились побайтно идентичными. SHA-256 соответственно 2d90f0cc8716640ad13e4e54cd31272ad50f0ff851dc12da5b9b861eaa805423 и 554127b2df933c488bb18f30d282a76431e92ec5c8b590959b8182ca9211b5cd. Ruff, py_compile и diff --check прошли. Первый расчёт выявил неверное имя поля метаданных, исправлено на Work_Title. Первые PowerShell HTTP-запросы завершились ошибкой TLS, штатное TLS-подключение Python к официальному домену успешно. Itch автора второго кандидата вернул 404, источники других кандидатов в замороженный набор не вошли. По согласованию оставлен один новый роман. Тексты не передавались наружу; интеграция в модель и проверка распространения находятся у ведущего. Базовый коммит 9f77358, собственного коммита нет.

### 2026-11-24 — Инженер корпуса. Заморожена итоговая модель с внешним романом

- В новом отдельном голосе автора учтён HarryBlank (Harry Blank), «The Breach Goes On: Bury the Survivors» (2022, SCP Wiki, CC BY-SA 3.0). Получены 18 глав, 186 007 токенов и 9331 уникальная сопоставленная лемма. Соседняя линия сохранила атрибуцию, ссылки, хеши, правила лемматизации и проверила дубли. Внешние формы сопоставлялись с пространством train+valid, имена собственные и акронимы отфильтрованы на этом этапе. Поэтому новые строки появились от 251 книги CONLIT; внешний текст изменил оценки присутствия уже известных лемм. Полные главы в Git не добавлялись. Атрибуция первоисточника — https://scpwiki.com/bury-the-survivors-hub .
- Итоговые 1023 книги, 826 авторов, 2001–2022 годы. Доля исходных и дополнительных книг распределена по прежнему правилу одного общего голоса на автора. В .app-data/expanded-corpus/extended сохранены ranker.json.gz, evaluation.json, training-presence.json и source-manifest.json. SHA-256 gzip 60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db; входа внешних лемм 2d90f0cc8716640ad13e4e54cd31272ad50f0ff851dc12da5b9b861eaa805423. Итоговые значения для публичных контрольных лемм borrow 73,397%, sword 47,312%, harpoon 5,089%.
- Вклад последней книги проверен отдельно относительно корпуса из 1022. На прежних 240 списках состав всех пятёрок совпал. В обеих версиях по 365 454 попадания, P@5 0,77094175, условный парный интервал разницы [0; 0]. По отношению к исходным 771 книге результат совпадает с предыдущей записью. Это проверка фиксированных списков и данных авторов, не обобщение о современной прозе 2020-х. Модель заморожена до раскрытия результатов внешней проверки. Сценарий считывает и хеширует одни и те же байты supplement. Ruff и три адресных теста повторно прошли; интеграция и личная проверка выполняются другими линиями. Коммита нет.


## 2026-11-24 — QA-инженер. Финальный ресурс Personal Priority

- Проверен extended ranker.json.gz с SHA-256 60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db. Штатный импорт во временный каталог дал побайтно ту же SQLite, что рабочая проекция, SHA-256 a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75. В двух изолированных профилях с одной и двумя книгами запущен внешний load_library. У sword книжный охват 47,31%, score 0,473119425 → 0,573914167, уровень 3 → 2. У harpoon охват 5,09%, score 0,050887813 → 0,074437732, уровень 6 → 6, статус рассчитанный в обоих профилях. Множитель двух книг 1,5, книжный охват сохраняется, personal_reason приходит только при повышении score.
- Текущие Главная и каталог выбирают явное поле personal_reason с fallback на reason, карточка показывает полный reason. 70 адресных Vitest в четырёх файлах прошли. Финальный frontend проверен адресными тестами и чтением пути отображения. Отдельного браузерного или нативного прогона на этом SHA не было. Исходники не менялись.


## 2026-11-24 — ML-инженер: независимая проверка на новых полных романах

- Изолировал шесть оригинальных англоязычных романов пяти авторов, 2018–2025, 481 788 токенов. Barbara Fister — Runtime (2023) и In the Dark (2020), CC BY-NC 4.0. Jim Bowering — The Plainsrunner (2018, выпуск под CC BY-SA в 2025). Nume Mashinini — Vumani (2025, UJ Press, CC BY 4.0). Anne Currie — Utopia Five (2019, CC BY-NC 4.0 с явным разрешением некоммерческого ML). Daniel Meyer-Dinkgräfe — The View across the Bay (2018, CC BY-NC-ND 4.0). Первичные страницы, прямые URL, SHA-256 оригиналов и выделенного основного текста в .app-data/novel-supplement/manifest.json. Полные тексты и словарные множества лежат только в ignored-каталоге для локального некоммерческого исследования.
- Добавил scripts/research/acquire_open_novels.py. Провёл вычленение по главам EPUB, по основному Story XML издателя Vumani и по диапазонам PDF с исключением оглавления, колонтитулов и дополнительных материалов. EPUB Vumani содержал ошибочные поля автора и названия в OPF, поэтому использован официальный XML с совпадающими издательскими полями и полным текстом. Far Less, Growland и другие романы Cal Poly не включены. Сервер Digital Commons вернул 403 на издательские ссылки. Первый curl остановился на Schannel SEC_E_NO_CREDENTIALS, прямой urllib успешно загрузил включённые источники. В двух PDF фразы не измерялись из-за неоднозначных границ абзацев.
- Заморожены 240 редких списков по 20 ключей и вторичная панель из 240 всех слов. Одна и та же нормализация и алиасы исходного ranker для обеих моделей, исключение CLOSED_CLASS и равновероятное разрешение ничьих. Поиск ключа в полной книге, P@5 с равным весом 24 исходных книг и 5 целевых авторов, парный bootstrap по обеим осям. Фамилии внешних авторов не найдены в исходном reference/split.json, новые обучающие авторы согласованы отдельно. Непересекаемость скрытых источников wordfreq подтвердить нельзя.
- Rare P@5: исходная 62,075%, расширенная 61,783%, общая частота 62,538%. Разность расширенная−исходная −0,292 п.п., 95% интервал [−0,733; +0,117] п.п. All: 82,692%, 82,600%, 82,075%, разность −0,092 п.п. [−0,433; +0,200]. Пятёрки c одинаковыми весами у кандидата на 1022 романах и итогового extended совпали на обеих панелях. Исходная модель d75e5ba0…e686, extended 60bc1a8f…15db. Раздельные отчёты evaluation-1022.json и evaluation-extended.json содержат данные по каждой книге и автору. На этой небольшой жанрово неоднородной выборке новое расширение не дало подтверждённого выигрыша. Измерялось появление ключа, человеческих меток полезности нет.
- Проверки: Ruff, py_compile и проверка пробелов прошли. Ошибку кавычек PowerShell при фразе с апострофом устранил повтор с двойными кавычками. Повтор с заблокированным urlopen дал побайтово одинаковый отчёт (SHA-256 467a462f…0dc5). Проявление точных поверхностных фраз диагностировано только в четырёх структурированных EPUB/XML, без вывода о значениях. Коммита нет. База кода 9f77358. Пользовательские книги и данные не использовал.

## 2026-11-24 — Финальная личная сборка RP-V2
- Подготовлена внутренняя папка `build/internal-personal-priority/` с EXE и свежим frozen bridge. Expanded SQLite размещена только под `bridge/models/`; книжные материалы не поставлялись.
- Исправлена раскладка frozen one-folder в staging: содержимое `_internal` сохранено внутри собственного каталога. Первичная проверка выявила ошибочную плоскую копию и не загрузившуюся `python311.dll`; staging очищен только в пределах целевой папки, после корректного копирования frozen smoke и lookup прошли.
- Smoke: load_demo, llm_config, process_queue (3 слова совпадают с dev Python), UTF-8 save_card_edit/load_library и `rp-v2-personal` для 3 синтетических записей. Модель совпала с pin исходного корпуса `60bc1a8f…e15db`; SHA SQLite зафиксирован отдельно. SHA256SUMS создан для EXE, bridge и модели.
- Vite/Tauri EXE собран ранее в этом staging. Публичные/установленные сборки не менялись. Native UI приёмка остаётся QA владельца.

## 2026-11-24 — Native-приёмка Personal Priority
- После исправления раскладки frozen bridge последовательно проверены два изолированных профиля с готовыми синтетическими записями. При одном поиске sword: уровень 3, книжный охват 47,31%; при поисках в двух книгах: уровень 2, тот же охват, отдельная причина «Вы искали в разных книгах». Карточка подтверждает две записи и две книги.
- give up при двух книгах осталось предварительным уровнем 6 с пояснением отсутствия книжного охвата выражения и учёта поисков; 00:17 сохранило уровень 10 и причину отсутствия букв. Ночной снимок списка просмотрен.
- Первые два запуска на некорректной раскладке не загрузили интерфейс и были остановлены; после исправления оба прошли. Использованы только временные данные и собственные процессы, устройство и пользовательские окна не затронуты. Реальный импорт в этом прогоне не проверялся, исходники не менялись.

## 2026-11-24 — Тимлид. Расширенная выборка романов и персональный приоритет

- Владелец подтвердил две задачи — совместить оценки и действительно расширить книжный корпус. Специалисты по продукту, ранжированию, корпусам, UX и QA согласовали единый порядок. При одном поиске сохраняется книжный балл. Достоверные возвраты в другой книге или в той же книге в другой день получают ограниченный множитель шансов. Повышение ограничено одним уровнем, решения о выгрузке остаются отдельными. Книжный процент отделён в контракте от гибридного балла. Проценты, объяснение и приоритет проверены в каталоге, карточке, предпросмотре и TSV. Полная методика и ограничения записаны в docs/plan/personalized-book-priority.md, PRODUCT.md и docs/plan/meetings.md.
- Подключил новую таблицу в обычный и frozen поиск модели и импорт. Поддержаны варианты 1 022 и 1 023 книг и исходная таблица RP-V2. Финальная версия — 1 023 романа 826 авторов, 209 720 измеренных ключей, прирост 28 050. SHA-256 ranker.json.gz 60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db. Исходные 393 контрольных романа и их авторы не вошли в обучение. Шесть внешних книг 2018–2025 годов выделены до оценки. На прежней панели P@5 77,100% → 77,094%, на новых книгах в основной диагностике 62,075% → 61,783%. Улучшение точности следующей книги не установлено; больше ключей теперь обеспечено измерением.
- В ranking_eval добавлены наблюдения по тем же правилам происхождения, точных выражений и времени, что и в продукте. Сравнены книжная и гибридная оценки на одних и тех же прошедших срезах, с чистым чтением профиля. При расширенной выборке AUC для повторного поиска 0,589 → 0,595, P@50 6% → 6%; чистая прежняя личная модель дала 32% на срезах, ранее использовавшихся при её разработке. Тест проверяет границу времени и источник наблюдений. Значимость маленькой разницы на одном профиле не утверждается.
- Независимые проверки выявили погрешность на границе 0,75 и двусмысленность сокращённого текста в каталоге. Исправлены точные сравнения и добавлено поле personal_reason. Итоговый pytest 382 passed, 1 skipped; Vitest 147/147, TypeScript/Vite, Ruff, compileall и diff --check прошли. При первой проверке поставки обнаружена неверная раскладка библиотек PyInstaller. Релиз-инженер исправил конечную папку bridge/_internal, проверены именно поставляемые EXE/модель и их хеши. Native QA на отдельных профилях прошла после исправления. SHA-256 EXE b0428be4d789d3fdad0e057f3d22d018a67b37297cb49de98c620768c928e076.
- Самостоятельный сквозной прогон через конечный frozen bridge: обычный импорт вымышленного vocab.db, обработка, добавление второго поиска в другой книге, повторный импорт и загрузка новым процессом. У sword книжная доля 47,31% сохранилась при изменении приоритета 3→2. У give up предварительная 6 и отдельная личная причина. 00:17 остался на 10. При повторном импорте ноль новых слов, с фильтром уровней 2 и 6 TSV содержал ровно три ожидаемых строки в порядке снимка. Новый исполняемый файл, манифест SHA и SOURCES.txt с атрибуцией CONLIT и HarryBlank — в build/internal-personal-priority/. Проверка понимания у читателей, реальный Anki и физическое устройство в эту задачу не входили. Пользовательские данные и тексты книг не входят в поставку; публичной публикации не было.


## 2026-11-24 — Коммит и отправка персонального ранжирования

По запросу владельца тимлид отправил ветку codex/card-review в origin. Коммит 6338407 объединяет код книжного и персонального ранжирования, протокол исследования, инструменты подготовки корпуса и тесты. Хеш вершины проверен через git ls-remote. В индекс отобран 41 файл. Личные данные, исходные романы, локальная модель, сборки и рабочие журналы остались в рабочей области.

Перед коммитом прошли git diff --cached --check, TypeScript/Vite, 147 тестов интерфейса и 382 теста Python с одним пропуском. При первом запуске песочница ограничила доступ Vite к конфигурации и pytest к временному каталогу. Итоговая проверка Python прошла с отдельным basetemp. Отправка включила десять более ранних коммитов этой ветки. Готовый бинарный ресурс ранжирования поставляется отдельно от исходников.


## 2026-11-27 — QA-инженер. Обогащение карточек и сохранение контекста

- На 6338407 проследил текущие Настройки, «Слова», карточку, JSON-мост и оба штатных экспорта. Настройки показывают провайдера, модель, состояние ключа и пробное подключение. Описание облачной передачи перечисляет слово и предложения, но синтетический запрос также содержит лемму, часть речи и название книги. Кнопка каталога и автоматический режим выбирают все допустимые слова, карточка передаёт один ID. Допуск опирается на старые ready/accepted/importance 3–10, независимо от ручного решения. Тестовый FakeClient получил слово с «Не учить».
- В двух временных профилях проверены обогащение FakeClient, чтение SQLite, штатный TSV и поля заметок реально сформированного .apkg при отключённом AnkiConnect. Ручной перевод и выбранное исходное предложение сохранились. Генерируемый пример отделён от книжного. TSV не содержит перевода книжной цитаты. Карточка показывает сгенерированный пример и определение под «Подробнее», перевод исходной цитаты там отсутствует.
- Провайдер получает до двух длиннейших цитат по 400 символов, независимо от ручного выбора. .apkg сохраняет выбранную цитату полностью. Перевод исходной цитаты появляется при совпадении короткой цитаты с первой в запросе. При альтернативном выборе и при совпадении длинной цитаты свыше 400 символов поле ContextTranslation пустеет, потому что сравниваются хеши усечённого и полного текста. Готовое обогащение не запускается снова после такого выбора. Причины переданы тимлиду с точными местами.
- Прошли 17 адресных pytest, включая тесты обогащения и Anki. Первоначальное предположение о пропаже оформленных полей после enrich опровергнуто штатным dispatch. Маршрут применяет _with_ranking, ответ сохраняет card, decision, ranking и study_priority. Исходники продукта не менялись. Реальный провайдер, ключи, пользовательская библиотека, импорт Anki и браузерный макет в этой партии не использовались.


## 2026-11-27 — Тимлид. Проверка контекстного обогащения GPT-6 Luna

По просьбе владельца проверен действующий путь Настройки → test_llm и enrich_lexemes → SQLite → TSV и поля Anki. Использованы два изолированных профиля с одинаковыми восемью вымышленными записями и официальный OpenAI API. У модели gpt-6-luna стандартный reasoning medium; приложение не передаёт отдельный параметр. Ключ использовался только в памяти, данные личного словаря и ключ в артефакты не включались. Исходники продукта и настройки владельца не менялись. Коммита нет.

Первый вызов test_llm занял 7,906 с в bridge, 4,396 с в SDK. Два независимых заполнения восьми карточек заняли 6,481 и 8,451 с, по одному сетевому вызову каждое. Повтор в тех же профилях 0,036 и 0,048 с без обращений к API. Фиксировались длина ответа, токены и реальные шесть полей. Обе партии верно передали значения bank, spring, fine, light, give in; для имени вернули помету, для слова без исходного предложения оставили перевод цитаты пустым. Перевод фразы с address во втором прогоне звучит неестественно. Это две партии на коротких синтетических контекстах, не оценка всей библиотеки. Обе выгрузки TSV содержали по восемь строк. Отдельно записан и затем открыт тестовый пакет Anki первого ответа, проверены восемь заметок и значения ContextTranslation, Example, ExampleTranslation. Anki пользователя не запускался.

Ошибку выбора контекста воспроизвели на bank: при выборе финансовой цитаты вместо речной готовые значение и новый пример остались про берег, перевод выбранной цитаты в Anki пуст. Независимая QA дополнительно обнаружила расхождение критерия обогащения с выбором «Учить», поведение длинных цитат при отсечке 400 символов и лишнее относительно описания в Настройках поле названия книги в запросе. Результат с ответами модели, размеры запросов, замеры и тестовый пакет лежат в локальной игнорируемой .app-data/llm-audit-20261127. Изначально песочница сбрасывала прямое TLS-соединение; официальный адрес проверен по HTTPS, затем живой прогон выполнен через обычное подключение. Первая попытка инициализации одноразовой локальной передачи секрета в Windows завершилась до обращения к провайдеру; после исправления использован только успешный вариант. Дополнительных расходов на повторное обогащение в заполненном профиле не было.

## 2026-11-27 — Подготовка Parallel Enrichment staging
- Подготовлен новый ignored каталог `build/internal-parallel-enrichment/` с копией принятого UI EXE под целевым именем, Tauri config и expanded SQLite в `bridge/models/`. Старую сборку не менял.
- В conda `kindle_app` доступен OpenAI SDK 2.44.0. До заморозки проверить PyInstaller inclusion, при необходимости добавить hidden imports только в staging-команду.
- Python исходники ожидаются. Frozen bridge и smoke отложены до сигнала владельца. Внешние API и ключи не использовались. Публичная установка не менялась.


## 2026-11-27 — Бэкенд-разработчик. Блокировка профиля и параллельный клиент обогащения

- В workspace_lock.py вынес общую неблокирующую файловую блокировку и добавил enrichment_run_lock(workspace). Мост тимлида берёт отдельный .app-data/enrichment.lock до выбора кандидатов, занятый профиль получает понятную ошибку. ОС освобождает замок при завершении процесса. В export_cards.py сохранены путь export.lock и прежние коды и тексты ошибок экспорта.
- В llm/openai_compatible.py синхронизировал выбор режима JSON. Параллельные отказы одного формата сдвигают общий указатель не дальше чем до следующего уже подтверждённого отказом режима, HTTP-запросы выполняются вне блокировки. Ответы HTTP 408, 409 и 5xx временные, 429 и ошибки доступа остаются фатальными.
- tests/test_enrichment_lock.py покрывает второе обращение через штатный dispatch, принудительную остановку владельца замка, независимость профилей и экспорта, гонку отказов json_schema и классификацию HTTP через MockTransport. Полный pytest: 391 прошёл, 1 пропущен. Прогоны обогащения и экспорта: 65 прошли, актуальные адресные тесты после интеграции: 20 прошли. Ruff, compileall и git diff --check прошли. При переносе Ruff обнаружил лишний import os, удалил его.
- Проверено нативно на Windows, без сетевых запросов к провайдеру и без личных данных. POSIX-ветку отдельно не запускал. База 6338407, собственного коммита нет.


## 2026-11-27 — QA-инженер. Параллельное обогащение OpenAI

- Проверена штатная JSON-точка входа enrich_lexemes на двух временных SQLite-профилях с одинаковыми 1000 вымышленными словами. В контроле переопределён только max_parallel_batches с 4 на 1. FakeClient одинаково ждал 80 мс и возвращал элементы партии в обратном порядке. Замер полного вызова моста, включая сохранение и сборку ответа, составил 29,252 с при одном слоте и 21,675 с при четырёх, ускорение 1,35 раза в этом опыте. Обе ветви сделали ровно 125 запросов по 8 слов, с пиками 1 и 4, сохранили одинаковые 1000 пар слово/перевод. Повтор дал 0 запросов. JSON stdout и ключи ответа совпали. В каждой ветви 125 монотонных событий об обработанных результатах.
- Временный сбой одной партии из 125 оставил 992 сохранённых результата и остановленный прогресс 992/1000. Следующий запуск отправил ровно 8 оставшихся слов одним запросом. При фатальной ошибке после запуска четырёх партий новых запросов не было, три успешные партии сохранили 24 слова, финал остановлен на 24/48. Повтор обработал только оставшиеся 24.
- Два отдельных процесса JSON-моста одновременно запросили один профиль с 80 словами. Второй получил понятную ошибку занятости, суммарный пик остался 4. Первый сохранил все 80 слов за 10 обращений, дубли отсутствуют. Для Anthropic, DeepSeek, OpenRouter, Custom, LM Studio и Ollama подтверждён пик 1 и неизменные размеры партии 8 для облачных и 2 для локальных моделей.
- Подставной конструктор SDK подтвердил max_retries 2 для одной партии OpenAI, 0 для нескольких, прежние 2 для DeepSeek и 0 для Ollama. Адресные tests/test_enrichment.py прошли 11/11. Продуктовые исходники не менялись. Реальные секреты, API, пользовательская база, браузер и frozen bridge не использовались. Замер характеризует только фиксированную задержку стенда. Основа 6338407, изменения в общем дереве проверялись до коммита.

## 2026-11-27 — Внутренняя поставка Parallel Enrichment
- В build/internal-parallel-enrichment размещены принятый UI EXE и расширенная SQLite-модель, побайтно совпадающие с Personal Priority, новый PyInstaller bridge и перенесённая атрибуция SOURCES.txt. SHA256SUMS.txt охватывает EXE, атрибуцию и весь каталог bridge.
- Frozen HTTP smoke сначала выявил несовместимые DLL OpenSSL: libcrypto была взята из среды Codex, libssl из conda. В итоговом staging заменены обе на согласованную пару из kindle_app. Проверены размещение _internal, полный состав и хеши файлов моста с учётом этой замены.
- Штатный bridge из staging через OpenAI SDK отправил на 127.0.0.1 четыре пакета по 8 слов с пиком 4. Повтор из нового процесса отправил 0 запросов. При загрузке подтверждены 32 сохранённых результата и источник rp-v2-personal. Только синтетический профиль и фиктивный токен.
- Снимок сигнатур Python сохранён после сборки: исходный файл сигнатур не появился. Основа сборки 6338407 с рабочими изменениями. Нативное окно не запускалось. Публичной упаковки нет.

## 2026-11-27 — HTTPS-проверка Parallel Enrichment
- В конечном frozen bridge выполнен list_llm_models с чистым временным профилем и заведомо фиктивным токеном. Официальный API по HTTPS вернул HTTP 401, мост выдал штатную ошибку аутентификации. Запрос списка моделей выбран для проверки без передачи слов. Реальный ключ не использовался.
- Проверены Python 3.11.15, OpenAI SDK 2.44.0, PyInstaller 6.22.3, OpenSSL 3.6.3 и побайтовое соответствие обеих DLL из staging окружению kindle_app. Шаги воспроизведения и полные SHA-256 сохранены в BUILD-OPENSSL.txt. Локальный HTTP smoke на четырёх пакетах и повтор без запросов пройдены в предыдущем шаге. Бинарники и продуктовые исходники в этом шаге не менялись.


## 2026-11-27 — Тимлид. Большие очереди контекстного перевода

Встроенный OpenAI теперь выполняет до четырёх запросов одновременно, каждый на восемь слов. Диспетчер передаёт ответ только его исходной пачке, пишет SQLite и сообщает прогресс после сохранения. Захват замка происходит до выбора кандидатов. Четыре потока не держат общую блокировку на время сетевого запроса. После 429/fatal новые пачки не отправляются; успешные соседи сохраняются, оставшиеся слова можно перевести повторно. Повторы SDK отключены для параллельного запуска. Профиль допускает одну активную очередь. Прочие провайдеры обрабатывают пачки последовательно. Протокол планёрки дополнен. Изменены enrichment.py, llm/presets.py, llm/openai_compatible.py, tauri_bridge.py, workspace_lock.py, export_cards.py, тесты и справка docs/TECHNICAL.md.

Вызовы штатного JSON-диспетчера к gpt-6-luna на 32 одинаковых вымышленных словах (стандартный medium) дали 24,609 с последовательно, 14,240 с при двух слотах и 7,315 с при четырёх в успешном повторном сравнении. В первом четырёхпоточном опыте три пачки ответили за 4,98–5,61 с, одна получила APITimeoutError. Длительность того запуска 120,087 с, готовы 24/32. Оба опыта сохранены раздельно в игнорируемом каталоге, провайдер получил только искусственные предложения; сам ключ использовался в памяти. Тысяча слов не отправлялась в облако. На 1000 синтетических слов в штатном bridge с задержкой 80 мс тестовый провайдер получил ровно 125 запросов; 1 и 4 слота заняли 29,252 и 21,675 с. Пик 4, повтор 0. При тайм-ауте одной пачки сохранились 992 слова, повтор затронул только 8. Отдельно проверены отказ по квоте с поздними успешными ответами, блокировка второй копии и освобождение после остановки процесса, корректная привязка переводов, цитат и прогресса.

Полный pytest на Windows: 393 passed, 1 skipped; набор Ruff из CI и дополнительные проверки изменённых модулей и тестов прошли. В расширенном линте всего tauri_bridge.py осталось прежнее BLE001 за пределами изменённого кода. Собрана отдельная внутренняя Windows-папка с прежним UI, новым мостом, согласованными OpenSSL DLL и расширенной SQLite-моделью; frozen SDK проверен локальным HTTP-сервером. Нативный UI, POSIX-замок и личная библиотека в этот прогон не входили.

## 2026-11-27 — Фронтенд. Планёрка по назначениям выгрузки

- Проследил выбор назначения, сохранение настроек, снимок scope/ids/levels, состояния Главной, открытие файлов и старую синхронизацию Obsidian. Согласовал с UX-дизайнером предложение из пяти назначений, одной кнопки с количеством на Главной, одного поля корня хранилища и следующего шага по результату.
- Передал ведущему точки контракта. Текущий open_path принимает только файл из папки выгрузок. Результат Obsidian нужно отличать по назначению, а отсутствие каталога выгрузок не должно сбрасывать состояние записи в хранилище. Нужны согласованные IDs, формат предупреждений и политика открытия каталога и read-only автосверки старых профилей. Передал также расхождение общего индикатора занятости и состояния useHomeExport.
- Просмотрены исходники и UX-ответ. Продуктовый код не менял и тесты не запускал. Реализация после сигнала ведущего и фиксации контракта. Без коммита.

## 2026-11-27 — Подготовка внутренней сборки Study Exports
- Создан игнорируемый staging build/internal-study-exports с конфигом Tauri: окно Kindle Cards — Study Exports, ID com.kindlevocab.cards.preview, отключена упаковка установщика.
- Проверены Python 3.11.15, PyInstaller 6.22.3, OpenAI SDK 2.44.0, OpenSSL 3.6.3, Node 26.4.0 и Cargo 1.96.1 в kindle_app. Принятая rp-v2-expanded.sqlite из Parallel Enrichment совпадает с SHA-256 a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75. Там же доступны wordnet.zip, POS tagger и атрибуция.
- После freeze собрать новые EXE и frozen bridge. Перенести модель, атрибуцию и локальные NLTK-ресурсы, сверить пару OpenSSL DLL с conda, прогнать smoke выгрузки в отдельном синтетическом профиле и записать SHA-256. Компиляция и smoke пока не запускались.

## 2026-11-27 — Инженер интеграции с Anki — Файлы для Quizlet и RemNote

- Сверены официальные инструкции Quizlet Creating sets by importing content и RemNote How to Import Flashcards from Text. Согласованный с ведущим writer write_study_file(output_path, destination, lexemes, edits) выдает Quizlet UTF-8 TSV с Tab и New line, RemNote UTF-8 TXT с одной Basic forward строкой «слово >> ответ» на запись. Оба формата без заголовка и BOM. Перевод и выбранная цитата берутся из card_fields.resolve, отсутствие перевода обозначается явно.
- В полях управляющие пробелы и переносы сведены в пробелы. В RemNote известные управляющие сочетания и маркеры начала сторон получают видимые заменители. Пишется уникальный временный файл рядом с зарезервированным путём и заменяется атомарно. При отказе writer убирает свой временный файл и оставляет резерв владельцу.
- В tests/test_study_formats.py три проверки на синтетике покрывают Quizlet контекст и пустой перевод, RemNote одну строку и один разделитель, отказ replace с чужим временным файлом. Первый pytest столкнулся с отказом доступа к общему каталогу pytest, выделен уникальный basetemp. В первом прогоне ожидаемый вывод выявил пропущенный RemNote маркер «;-», исправлен. Повтор: 3 passed, Ruff и compileall прошли.
- Код export_cards и мост оставлены ведущему. Живые импорты внешних сервисов не проверялись, аккаунты и личная библиотека не использовались. Коммита нет.


## 2026-11-27 — Инженер ранжирования: миграция истории экспорта SQLite v5

- В library_migrations.py добавлен шаг 4 → 5 с разрешёнными destination quizlet и remnote. История копируется с исходными ID, строками и именами. Обе таблицы заменяются в одной транзакции с включёнными FK. Сохранены ON DELETE CASCADE, индекс по лексеме и следующий AUTOINCREMENT даже после удаления прежнего максимального ID. Имена существующих csv записей не изменены. Дублированного ограничителя в library_state.py нет.
- В tests/test_library_migrations.py проверены синтетические базы v1/v3/v4, чистое создание, два отдельных запуска на одной v4, история и резервная копия до шага, запись фактических quizlet/remnote, FK, каскад и откат после перестройки таблиц с успешным повтором. 18 адресных тестов прошли. Ruff и git diff --check прошли.
- Расширенный запуск с tests/test_library_state.py: 33 прошли, один упал на фиксированном ожидании версии 4 в ReviewCardsMigrationTests. Этот файл вне порученной области, точное место передано тимлиду. Личная БД, упаковка и тесты реальных назначений не использованы. База 6338407, собственного коммита нет.

## 2026-11-27 — Совместимость с официальным Obsidian Spaced Repetition
- Исполнены TypeScript parser, TopicPath и NotesDataStore официального тега 1.15.4 (22fbea0) на синтетике. Метаданные Obsidian поданы макетом. Порядок тегов влияет на выбор: первый подходящий родитель перехватывает вложенную колоду. Один вложенный тег работает при корне #flashcards. Folder mode берёт путь родительской папки и игнорирует теги заметки.
- Штатный многострочный разделитель вопроса и ответа — ?. Между карточками bare --- склеивает две карточки в одну с настройками по умолчанию. Пустые строки вокруг --- дают две карточки; явное назначение --- маркером конца тоже работает. Изменение ? на ^ перестаёт читать старый формат.
- NotesDataStore прочитал inline HTML-комментарий с датой, интервалом 4 и ease 270. Доступен StorageType.NOTES, FOLDER закомментирован в официальном теге. Git Schannel и общий npm-кэш не сработали, обход через OpenSSL и временные зависимости прошёл. Приложение Obsidian, личные профили и заметки не открывались; продуктовые файлы не изменены.

## 2026-11-27 — Штатный экспорт Obsidian на парсере SR
- Штатный export_words из отдельной синтетической SQLite создал по три заметки уровней 1, 8, 10 в трёх профилях: стандартный ?, пользовательский %%card%% и %%end%% с вложенным корнем #study/custom, режим колод по папкам. TopicPath и parser официального SR 1.15.4 подтвердили одну многострочную карточку на файл и нужную подколоду для каждой.
- Повтор после правки перевода сохранил путь, состав заметок и расписание. NotesDataStore прочитал дату, интервал 4 и ease 270 на нужной карточке в каждом профиле. Первое сравнение перевода в тестовом скрипте учло экранирование дефиса после просмотра результата.
- В промежуточном дереве выявлен повторный захват vault lock, сообщение передано ведущему. После появления lock_held=True обычный экспорт и повтор с расписанием прошли во всех трёх профилях. Метаданные кэша переданы макетом, Obsidian GUI и переносной EXE здесь не проверялись. Продуктовых правок нет.

## 2026-11-27 — Проверка открытия папки Obsidian
- Штатный open_obsidian_folder передал в функцию открытия абсолютный путь управляемой папки после экспорта. После временного снятия маркера владельца вернул opened=false без попытки открытия. Маркер восстановлен в синтетическом vault. Функция запуска ОС подменена для проверки аргумента; Проводник и личный vault не открывались.

## 2026-11-27 — Фронтенд. Пять назначений выгрузки

- В src подключены Anki, подробный TSV, Quizlet, RemNote и Obsidian · Spaced Repetition. В Настройках один список назначений, поле корня появляется только для Obsidian. Пустой и относительный путь ведут из Главной в Настройки. Старые поля и кнопка синхронизации удалены из интерфейса, авто-read старой схемы выключен при новом назначении Obsidian.
- Главная сохраняет scope/ids/levels и показывает действие с количеством и назначением. Файлы открываются через open_path, папка Obsidian через open_obsidian_folder с пустым payload. Полный message отображается независимо от наличия локальных выгрузок, включая exported=0 и пустой runId. Смена пути или назначения сбрасывает прежний результат. Во время выгрузки общий статус показывает занятость, действия записи в каталоге и смена назначения заблокированы.
- Vitest 153/153, TypeScript/Vite и diff --check по src прошли. Собственный Playwright на 600 и 1440 проверил пять назначений, открытие папки в mock, относительный путь и переход в Настройки. Первый прогон выявил, что reducer переводил все нулевые ответы в empty. Исправлено, добавлена регрессия, повторный прогон успешен. UI-дизайнер повторно просмотрел нулевой результат и снял блокер. Снимки в игнорируемом каталоге .app-data/export-destination-*.png. Реальные приложения и нативное окно в своей проверке не открывал. Без коммита.


## 2026-11-27 — Бэкенд-разработчик. Управляемая выгрузка карточек в Obsidian

- Сверил исходники и документацию Spaced Repetition 1.15.4. Подтверждены порядок выбора первого подходящего тега, активный inline-режим NOTES, текстовые разделители, варианты комментария расписания и отсечение заметок по префиксу или шаблону пути.
- Реализовал obsidian_export.py. Управляемая папка Kindle Cards имеет отдельный маркер владения. Новые карточки обоих режимов создаются в подпапках уровня 01–10 с читаемым именем и полным стабильным суффиксом. Повтор находит прежние имена и переименования внутри управляемой папки. Узнанные файлы остаются на прежнем пути при смене уровня. Свойство уровня и тег изменяются при проверенной исходной записи. Служебный хеш отличает исходный текст от ручных правок, а распознанный комментарий SR сохраняется.
- Общий vault_operation_lock разделяется со старым sync и находится вне vault, а managed_folder проверяет владельца и безопасные пути без записи. Чужие заметки, конфиг и расписание отдельно не меняются. При неизвестном внешнем режиме только добавляются новые карточки, а сложные правила исключения и неоднозначные папки настроек останавливают выгрузку. Отсутствующий или выключенный SR получает понятное сообщение.
- tests/test_obsidian_export.py проверяет режимы, custom separator и end marker, пользовательское редактирование, три формы расписания, safe escaping, конфликты по суффиксу без свойств, junction, чужой hardlink, общий lock, обнаружение внешней записи перед заменой и повтор после сбоя. Начальный Ruff обнаружил два недочёта в тестах, исправлено. Итоговые 51 адресный тест, Ruff, compileall и diff --check прошли.
- SHA-256 writer C914E773F6F04EB5FBA62E432715A0EF4BD1968726F77C1076F48EE5B90B6184. База 6338407, собственного коммита нет. Только искусственные vault. Живой Obsidian и POSIX-создание не запускал. Замок согласует процессы Kindle Cards. При одновременной записи Obsidian используется проверка байтов перед заменой, поэтому для обновлений остаётся короткое окно между проверкой и заменой. Поиск перемещённых заметок ограничен управляемой папкой.


## 2026-11-27 — Бэкенд-разработчик. Межмодульный прогон Obsidian

- Промежуточный полный pytest: 410 прошли, 1 пропущен, 3 падения воспроизведены адресно. Прежние тесты ожидали отказа для назначения obsidian, схемы 4 и синхронизации в тестовый путь без существующего корня vault. Все 18 собственных тестов writer на финальной версии прошли. Сопутствующие проверки переданы тимлиду, соседние файлы не редактировал.
- Независимая QA Chromium 1440×900 прошла по пяти назначениям, абсолютному/пустому/относительному пути Obsidian, частичному/нулевому результатам и ошибке моста. Проверены подходящие команды открытия, отсутствие legacy-кнопки и pageerror. Смена корня убирает предыдущий результат. Свой дополнительный прогон этого перехода на 600 px также прошёл.


## 2026-11-27 — QA-инженер. Пять назначений экспорта и совместимость Obsidian

- На 6338407 с рабочими изменениями проверен штатный export_words. Синтетическая библиотека содержит все десять уровней. Выбор уровней 1, 9 и 10 и перемешанных ID возвращает ровно 9→1→10, включая вручную пропущенное слово в полном режиме. Подробный TSV сохраняет ручной перевод и выбранную книжную цитату. Два .apkg сохраняют состав и одинаковые GUID. Quizlet и RemNote дали по три импортные строки, отдельная проба табов и >>/== внутри текста не создала дополнительных разделителей или строк.
- Синтетический vault без SR получил три Markdown-заметки и подсказку о включении плагина. Повтор сохранил файлы. Настройки folder-decks и разделителей ^^/!END дали папки 01/09/10. Inline SR сохранён при повторе и обновлении перевода. Ручная правка оставлена побайтно. Единственный конфликт дал exported=0 и пустой runId, частичный экспорт зафиксировал две строки. Незнакомая занятая папка, неверная конфигурация, внешние junction и файловая symlink оставлены нетронутыми. Отсутствующий корень назначения вернул no_destination.
- Legacy load сохраняет только сведения назначения, файлов не меняет. Прежняя карточка учитывается без копии. При старых карточках без нового каталога результат имеет path=null. После создания управляемого каталога штатное открытие передаёт ОС ровно vault/Kindle Cards, проверено подставным открывателем. Старый sync блокируется при наличии маркера нового writer даже с назначением TSV. Оба старых маршрута отклоняют ../, абсолютный cards_path, managed каталог в роли старого и junction. 25 адресных тестов Obsidian прошли.
- Chromium на 1452 через Playwright, 1440×900. Через Настройки по очереди выбраны Quizlet, RemNote, TSV и Anki. Каждое действие сохранило mock-файл, правильный следующий шаг и открытие ожидаемого расширения. Пустой или относительный путь Obsidian ведёт в Настройки без export_words, абсолютный путь открывает папку карточек. При смене vault предыдущий результат исчезает. Сценарии частичного 12/13, нулевого 0/13 и ошибки различимы. Старой кнопки синхронизации в Настройках и «Словах» нет, pageerror=0.
- Первый backend-прогон поймал двойной захват замка vault, после lock_held=True повтор прошёл. Браузерные пробы подстроены к обновившимся подписям и сохранению абсолютного пути при передаче через раннер. Продуктовые исходники не менялись. Физическое устройство, настоящий Anki/Quizlet/RemNote, установка SR и пользовательский vault не использовались. Точный разбор и сохранение расписания проверены на синтетическом inline-комментарии, а не через цикл повторения в настоящем приложении.

## 2026-11-27 — Нативный EXE Study Exports
- После freeze фронтенда собраны production Vite и Tauri --no-bundle (exit 0), основа 6338407 с рабочими изменениями. JS index-DcaVYn6f.js. Готовность EXE в 10:45:44 МСК, SHA-256 fc1ae74a55e31e10e2f0222c005a409d7a383cbb538156b9729083dddcbfaadb.
- В build/internal-study-exports перенесены подтверждённая expanded SQLite (хеш совпал) и SOURCES.txt. Проверка запуска и smoke остаются до нового frozen bridge после сигнала Python freeze.


## 2026-11-27 — Тимлид. Пять назначений выгрузки и карточки Obsidian по приоритетам

- Согласованы один выбор назначения, один путь к существующему хранилищу и привычный выбор слов на Главной. Источники форматов и правила работы со старыми карточками зафиксированы в протоколе встречи. Из двух текстовых форматов Quizlet использует две колонки, RemNote получает строки Basic forward.
- Интеграция в export_cards, tauri_bridge и contracts ведёт общую историю после записи. Для Obsidian учитываются подтверждённые карточки, конфликты остаются доступны. Папка открывается через отдельную проверку владельца. Прежняя синхронизация и новая выгрузка используют общую блокировку хранилища. Список старых карточек читается из проверенного вложенного каталога. Безопасный старый путь проверяется перед чтением, копированием и записью. Миграция SQLite до v5 сохраняет историю и допускает два новых назначения.
- По отзыву UX оставили одно поле корня. По отзыву UI исправили отображение результата при нуле записанных и наличии конфликтов. По отзыву приёмки исправили двойной захват блокировки и проверили parser, TopicPath и NotesDataStore SR 1.15.4 на файлах самого приложения в трёх конфигурациях. Файлы в подпапках 01–10 имеют читаемое начало имени и постоянный идентификатор. Смена уровня обновляет тег и свойство. Существующий путь остаётся для ссылок и расписания. README, PRODUCT и TECHNICAL описывают пользовательский маршрут и границы повторной выгрузки.
- Первый полный запуск нашёл три устаревших ожидания тестов — Quizlet как недопустимое назначение, фиксированную версию 4 и отсутствующий корень в тесте старой записи. Исправлены фикстуры и ожидания. Итоговый pytest 419 прошли, 1 пропущен на Windows. Vitest 153 прошли, TypeScript, production Vite, линтер для файлов CI и новых модулей прошли. Проверены выбор уровней, ручной перевод, выбранная цитата, повтор, частичный результат, пути, дубли старых карточек и обработка особых разделителей.
- На искусственных 1000 карточках writer создал 1000 Markdown-файлов в 10 папках за 8,51 с. Второй вызов занял 1,38 с, подтвердил все 1000 и сохранил тот же набор файлов с совпадающим SHA-256 каждого. Время относится к записи и сверке на этой машине. Личные заметки и настройки Obsidian при приёмке не изменялись. Веб-аккаунты Quizlet и RemNote не использовались. Поиск перемещённых заметок ограничен папкой Kindle Cards, при одновременной правке сторонним синхронизатором остаётся узкое окно между сверкой и заменой файла.

## 2026-11-27 — Финальная внутренняя поставка Study Exports
- SHA-256 Obsidian writer совпал с C914E773F6F04EB5FBA62E432715A0EF4BD1968726F77C1076F48EE5B90B6184. Новый PyInstaller bridge собран из замороженного дерева на основе 6338407, подписи входных файлов до и после совпали.
- В staging использованы локальные проверенные NLTK-ресурсы, согласованная пара OpenSSL DLL из conda, принятая расширенная SQLite и SOURCES.txt. Создан SHA256SUMS.txt для EXE, атрибуции и всего bridge.
- Конечный frozen bridge прошёл load_library с rp-v2-personal и штатный export_words в изолированных профилях: Obsidian создал одну Markdown-карточку, повтор сохранил её побайтно, Quizlet создал TSV с табуляцией, RemNote создал TXT с разделителем >>. Native UI и импорт в сторонние приложения не проверялись.
5268be21c3e8c1f38e7d69f77eded196251179afdc7d3bd678461bbd6d1a4b8e  bridge/kindle-bridge.exe
a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75  bridge/models/rp-v2-expanded.sqlite
fc1ae74a55e31e10e2f0222c005a409d7a383cbb538156b9729083dddcbfaadb  Kindle Cards - Study Exports.exe

## 2026-11-27 — Нативная приёмка Study Exports
- После изменения формата штатный экспорт и парсер SR 1.15.4 повторно проверены в стандартном, custom и folder mode. Физические подпапки 01, 08, 10 и читаемые имена с постоянным ключом появились во всех трёх профилях. Парсер и TopicPath дали по одной карточке и нужной колоде. Повтор с правкой сохранил расписание, проверено NotesDataStore.
- В отдельном native WebView2 обнаружены пять назначений. Через Настройки задан путь тестового vault, первый экспорт записал три заметки в подпапках 01, 06, 10 на замороженной модели, повтор показал 0 новых и 3 уже в хранилище. Содержимое файлов побайтно совпало; кнопка открытия папки видна. Ночной снимок проверен, ошибок страницы нет.
- Первый UI-прогон проверил select до монтирования. Повтор после ожидания прошёл. Коллекции, заметки владельца, устройство и другие окна не использованы. Продуктовые файлы не изменены; другие назначения проверены по наличию в UI.


Приёмка конечной переносной сборки Study Exports прошла на отдельном профиле WebView2. Из настроек выбран путь к синтетическому хранилищу. Первая выгрузка создала три заметки уровней 01, 06 и 10, вторая подтвердила те же три файла побайтно. Проверены пять назначений в нативном интерфейсе и экспорт Quizlet/RemNote конечным мостом. Тимлид сверил SHA-256 EXE fc1ae74a55e31e10e2f0222c005a409d7a383cbb538156b9729083dddcbfaadb, bridge 5268be21c3e8c1f38e7d69f77eded196251179afdc7d3bd678461bbd6d1a4b8e и ресурса модели с манифестом. Комплект расположен в build/internal-study-exports. Публичной поставки в этом этапе нет.

## 2026-11-27 — Фронтенд. Завершение стенда Study Exports

- После нативной приёмки остановил свой Vite, проверил освобождение порта 1452 и закрыл две собственные сессии Playwright. Продуктовый код не менялся.

## 2026-11-27 — Подготовка внутренней сборки Fox Guide
- Создан ignored staging `build/internal-fox-guide/` с Tauri-конфигом preview ID `com.kindlevocab.cards.preview` и новым заголовком. Полный принятый каталог bridge из Study Exports скопирован побайтно вместе с `_internal`, моделью и NLTK-ресурсами.
- Vite/Tauri не запускались. Предыдущая сборка и открытые окна не менялись.
- При первом старте Windows Tauri использует WebView2 Runtime. На современных Windows он обычно уже установлен. Если runtime отсутствует, окно может не открыться до установки Microsoft Edge WebView2 Runtime. Переносной EXE не включает сам runtime.
- Флаг реплик лиса хранится в `localStorage` под ключом `kindle-cards.fox-speech.enabled`. Сохранение выполняется с обработкой ошибки. При недоступном хранилище выбор действует только до завершения процесса, а реплики при старте включены по умолчанию. Профиль WebView2 и внутренний preview ID могут отделять это значение от другого приложения.
- Жду явного freeze для Vite/Tauri. После сборки проверить первый запуск и сохранение флага в отдельном профиле.

## 2026-11-27 — Подготовка нативной приёмки Fox Guide
- Подготовлен временный драйвер с пустым workspace, отдельным профилем WebView2 и подменой обнаружения читалки. Он позволяет запускать и закрывать только собственный процесс с сохранением профиля между запусками.
- До сигнала о freeze EXE не запускался. Проверка пропуска, фактического перезапуска и повторного прохождения через Настройки остаётся впереди. Продуктовые файлы не менялись.


## 2026-11-27 — QA-инженер. Экскурсия с лисом при первом запуске

- Два сквозных прогона Chromium через отдельный Vite 1453 на 6338407 с рабочими изменениями. Итоговый прогон использует шесть новых BrowserContext. Автопоказ начинается только после подтверждения пустой библиотеки на Главной. Замедленный ответ и ошибка загрузки не открывают диалог и не ставят seen. Маркер kindle-cards.fox-tour.v1.seen сохраняется сразу после открытия и переживает пропуск, reload в середине тура и реальное закрытие вкладки в том же профиле. В заполненной библиотеке и при первом входе в Настройки автоматического показа нет.
- Клавиатурой пройдены все четыре заголовка, возврат «Назад», переходы «Далее», «Готово», Escape и быстрый «Пропустить». Фокус на объявляемом заголовке каждого шага, Tab и Shift+Tab внутри диалога. Клик по фону не закрывает. После автозакрытия фокус на заголовке Главной, после ручного открытия возвращается к «Пройти обучение с лисом». Повтор из Настроек начинает с шага 1.
- Проверены 1440×900 ночь и 600×570 день, снимки первого и последнего шагов просмотрены. В коротком окне панель и кнопки внутри окна. Статические миниатюры исключены из списка активных кнопок. Аудит вызовов browser mock не обнаружил запуска импорта, демо, выгрузки, обогащения или изменения настроек от экскурсии. После закрытия обычные демо и ручная mock-выгрузка 13 слов прошли.
- 26 адресных Vitest прошли, ошибок страницы нет. Использованы синтетическая библиотека и отдельное хранилище Chromium, Playwright CLI. Запуск с реальным WebView2, устройство и программа экранного доступа в этой проверке не использовались. Исходники продукта не менялись.

## 2026-11-27 — Фронтенд. Диалог экскурсии лиса

- Добавил только fox-tour.tsx/css и fox-tour.test.tsx в src/features/onboarding. Четыре шага следуют реальному маршруту читателя. Реплики от первого лица показаны сразу, карандашная выноска связывает их с существующим FoxFigure. На каждом шаге один подписанный статичный учебный пример. Примеры не вызывают мост и не меняют библиотеку. Интеграция показа и флага ведётся отдельно.
- Radix управляет модальностью, Tab и Escape. При смене шага фокус переходит на заголовок с доступным номером, отдельный live-канал не используется. При закрытии фокус возвращается к запомненному инициатору или home-title. Открыв диалог повторно, читатель начинает с первого шага. Пропуск доступен сразу. В коротких окнах прокручивается только содержимое, футер остаётся доступным. Смена системной темы проверила ререндер родителя с новой функцией onDismiss без сброса шага или фокуса.
- Vitest 155/155, TypeScript/Vite и diff --check по onboarding прошли. Playwright 1453: день 1440×900, ночь 600×450 и 390×430, reduced motion, цикл Tab/Shift+Tab, смена шага и возврат фокуса после всех трёх способов закрытия, клавиатурная прокрутка в узком коротком окне, отсутствие повторного автозапуска после reload. Снимки в .app-data/fox-tour-*.png. Независимая browser QA прошла, UI-дизайнер не обнаружил блокирующих визуальных дефектов в просмотренных состояниях. Нативный экран и фактическая озвучка screen reader в этой линии не проверялись. Без коммита.

## 2026-11-27 — Фронтенд. Финальная правка экскурсии

- В fox-tour.tsx/css и тесте обновлены заголовок «Загрузим слова», текст шага 3, кегль причины borrow до 14 px и стык хвоста с рамкой выноски.
- Vitest 155/155, TypeScript/Vite и diff --check прошли. Первый браузерный вызов на 1453 получил connection refused. На временном собственном preview 1454 из итогового dist прошли повторный сценарий обеих тем, 1440×900, 600×450, 390×430 и клавиатурный проход. Просмотрены обновлённые кадры первого и второго шагов. Нативный интерфейс в этой правке не проверял. Freeze передан ведущему, коммита нет.

## 2026-11-27 — Внутренняя сборка Fox Guide
- Production Vite/Tauri --no-bundle завершились успешно с новым заголовком. Итоговый EXE — `build/internal-fox-guide/Kindle Cards - Fox Guide.exe`.
- Полный bridge Study Exports скопирован побайтно, все 259 файлов совпали. Frozen `load_demo` из нового каталога с отдельным профилем вернул 9 синтетических записей.
- SHA256SUMS.txt создан для EXE и всех ресурсов bridge. Старые сборки и открытые окна не изменялись. Нативная визуальная проверка onboarding не выполнялась.

## 2026-11-27 — Нативная приёмка Fox Guide
- В пустом временном workspace и отдельном WebView2 первый запуск показал экскурсию на шаге 1. Нажатие «Пропустить» закрыло диалог. После фактического завершения собственного процесса и нового запуска с теми же данными экскурсия автоматически не открылась.
- Через Настройки → «Пройти обучение с лисом» открылись все четыре шага; «Готово» закрыло диалог. Доступ к читалке заменён тестовым ответом, личные данные и другие окна не использовались. Исходники не менялись. Реальные screen reader и физическая читалка не проверялись.


## 2026-11-27 — Тимлид. Экскурсия с лисом и README

- Согласована экскурсия за четыре шага. Сценарий ведёт от загрузки слов до выбора выгрузки через приоритеты и правку карточки. Реплики принадлежат лису из приложения, все примеры доступны без читалки. Встроили экскурсию в основной shell, кнопку повтора в Настройки и приглушение обычных реплик на Главной на время обучения.
- Автопоказ учитывает успешный начальный ответ библиотеки. Существующим читателям оставили добровольный вход. Версионированная отметка WebView сохраняется при открытии, в том числе вручную. Неуспешное чтение базы не считается пустым профилем. Закрытие по Escape, «Пропустить» и «Готово» возвращает фокус. Мост и формат библиотеки не менялись.
- Решение команды записано в docs/plan/meetings.md. Продакт и UX отказались от обязательных практических действий внутри урока. После визуального ревью усилили связь реплики с рисунком и увеличили пояснение причины приоритета на втором шаге. В README учтены замечания UX-исследователя о папке выгрузок и пяти назначениях.
- Получены два штатных снимка Playwright с учебными данными для README: готовая ночная Главная в docs/screenshots/fox-reading-desk.png и дневной третий шаг с лисом, переводом и цитатой в docs/screenshots/fox-first-run.png. Оба просмотрены, проверены локальные ссылки, CRC PNG, размеры и альтернативные подписи. Ранний снимок с незаконченной обработкой заменён на готовую подборку. Для локального preview и проверки Vitest esbuild потребовалось разрешение на чтение конфигурации через родительские каталоги. Первый автоматический поиск пути Chromium вернул отсутствующую ревизию, использован уже установленный headless Chromium.
- Итог Vitest 155/155, production TypeScript/Vite/Tauri и diff --check прошли. Приёмка браузера на широком и узком окне в двух темах проверила пропуск, возврат, все четыре шага, заданный маршрут, загрузку с задержкой/ошибкой, заполненную библиотеку, повтор из Настроек и отсутствие команд записи от экскурсии. Отдельно проверили ручное первое открытие напрямую из Настроек, пропуск и последующий запуск на Главной. Browser plugin not available; проверка через Playwright. Читалка и данные владельца не использовались.
- Для тестирования собран отдельный build/internal-fox-guide/Kindle Cards - Fox Guide.exe, SHA-256 ae16c0baf16fdf7fd3dd0582d61dff692ee24a6ce7b73e3a44f16f26089a1352. Полный мост совпадает с принятой Study Exports. Публичный релиз не публиковался.

## 2026-11-27 — Тимлид. Планёрка по стабильной версии 1.0

- Провели два круга с продакт-менеджером, UX-исследователем, инженером ранжирования, бэкендом, QA и релиз-инженером. Решение и критерии по владельцам этапов записаны в `docs/plan/meetings.md`. Готовим закрытый кандидат Windows x64; публичный выпуск ожидает приёмки и решения владельца.
- Сверены PRODUCT, README, история v0.4.0 и рабочей ветки, версия схемы, релизный workflow, упаковщик моста, фактические поля облачного запроса, исследовательская записка и границы ранее проведённых проверок. Обнаружены расхождения между переносной и стандартной поставкой модели и между раскрытием данных ИИ и запросом. Выбрано сохранить книжный сигнал для одного поиска. Приняты возражения о повторной сборке по тегу и ограничениях автоматической резервной копии.
- Условия следующего решения — подтверждённый состав и происхождение ресурсов, один коммит и SHA установщика, успешные чистая установка и обновление 0.4.0, восстановление старого профиля, реальный Kindle, повторная выгрузка на тестовых данных и понятный объём экспорта. Приватный проход новичка и позднейший возврат после чтения оцениваем отдельно.
- Изменены только протокол и этот журнал. Выполнена сверка плана с исходниками и прошлыми отчётами. Сборка 1.0, повтор тестов продукта, приглашение читателей и публикация в эту планёрку не входили.

## 2026-11-27 — Подготовка частного RC1
- Создан `build/rc-1.0.0/`. Старый NSIS 0.4.0 сохранён в подкаталоге QA-копии; SHA подтвердился как c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826.
- В staging сохранены `rp-v2-expanded.sqlite` (SHA a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75) и имеющийся SOURCE атрибут. Исходный корпус ranker.json.gz pin 60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db.
- Сверка обнаружила неподтверждённое расхождение версий: package.json и pyproject.toml уже 1.0.0, Cargo и Tauri остаются 0.4.0. Рабочее дерево не зафиксировано на 6338407. Финальные сборка и заморозка ожидают сигнала backend/тимлида после выравнивания и принятия состава.
- Текущий attribution SOURCE указывает на разные условия CONLIT (Figshare CC BY 4.0 и статья CC BY-NC 4.0) и ограничивает сборку личным некоммерческим использованием. Использовать только для частного RC1; для публичного сценария нужна отдельная проверка условий. Public CI/workflow не менялся. Не устанавливалось в профиль и не публиковалось.

## 2026-11-27 — Подготовка изолированной приёмки RC1
- Прочитаны PRODUCT и решение планёрки. Найден установщик 0.4.0 SHA-256 c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826. 7-Zip извлёк его 265 файлов в отдельный временный каталог без запуска установщика.
- WindowsSandbox.exe и командлет Get-VM не обнаружены; vmcompute работает, опрос компонента Sandbox требует повышения. Реальной изолированной VM пока не подтверждено. Извлечение и отдельный WebView2-профиль помогут проверить файлы и UI, но не доказывают установку, обновление и ярлыки; безопасность NSIS /PPORTABLE не подтверждена.
- Ожидается конечный NSIS и SHA от релиз-инженера. Установщик не запускался, пользовательский профиль и реестр не менялись.


## 2026-11-27 — Бэкенд-разработчик. Раскрытие данных обогащения RC1

- В enrichment.py удалил поле book из общего формирования запроса и название из встроенной пробы. Номер, форма слова, лемма, предполагаемая часть речи и до двух фрагментов по 400 символов сохраняются. Prompt описывает возможное усечение. PROMPT_VERSION прежняя, готовые карточки не возвращаются в очередь из-за обновления.
- В settings-view.tsx перечислены поля запроса и предел цитат, объяснён возможный повтор после сбоя. Ручной и автоматический режимы используют один enrich_lexemes. Отдельный optimizer_cli.py вызывает llm_enricher.py и относится к явной CLI-команде за пределами desktop-моста, эту ветку не менял.
- В tests/test_enrichment.py проверил сериализованное тело обеих форм штатного bridge-вызова, отсечку третьей цитаты и обе длины, отсутствие обращения при выключенном переключателе, готовые слова при повторе и синтетический test_llm. 21 адресный pytest прошёл без ключа и сети. Ruff, compileall, TypeScript и diff --check прошли. Обычный Vitest столкнулся с ограничением чтения конфигурации esbuild, альтернативный загрузчик runner дал 155/155, production Vite с ним также прошёл.
- Префиксы SHA-256 для заморозки: enrichment.py D9C5306C, settings-view.tsx 3F811ED1, test_enrichment.py 135C1788. База 6338407. Упаковку, личные данные и настоящий провайдер не использовал, коммита нет.

## 2026-11-27 — Ранжирование. Происхождение и выбор модели RC1

- Добавил `packaging/ranking-model-notices.txt` для расширенной RP-V2. SHA-256 исходной `ranker.json.gz` — `60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db`. SHA-256 `rp-v2-expanded.sqlite` — `a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75`. Копии SQLite в локальном каталоге модели, Study Exports и Fox Guide совпали.
- Сверил Figshare CONLIT v1 (CC BY 4.0), раздел 3 статьи Andrew Piper (CC BY-NC 4.0 для того же набора), атрибуцию HarryBlank в SCP Wiki и её условия CC BY-SA 3.0, условия WordNet 3.0. Публичная поставка конкретной SQLite остаётся неподтверждённой. Открыты расхождение в условиях CONLIT, поставка сохранённых соответствий форм RP-V2 и применимость ShareAlike к объединённой статистике. Существующую частную сборку можно дать владельцу для локальной проверки. Внешних обращений, новых данных и модели не было.
- В `book_coverage.py` комплектная expanded-таблица frozen bridge теперь опережает прежнюю локальную expanded. Если комплектный файл отсутствует или не проходит проверку, остаются совместимые локальные ресурсы. Тест с двумя допустимыми expanded-вариантами проверяет фактически открытый файл на чистом и обновлённом профиле, сохранность локальной таблицы и восстановление при повреждении ресурса.
- Прошли 60 адресных тестов Python. Первый запуск остановился на запрете доступа к общему временному каталогу pytest. Повтор прошёл с отдельным basetemp в ignored build. Проверка исходного загрузчика в режиме frozen с фактической SQLite из Fox Guide подтвердила одинаковые первую пятёрку, уровни и причины на чистом профиле и при старой локальной RP-V2. Возврат к контрольному слову в другой книге поднял уровень 3 до 2, книжная доля 47,31% сохранилась. В первых двух попытках отдельной проверки исправил в проверочном коде сравнение служебного поля и путь импорта сортировки. `git diff --check` по изменённым Python-файлам прошёл.
- Новый frozen bridge, NSIS и обновление 0.4.0 этим этапом не запускались. Сборочный скрипт и workflow не менял. Без коммита.


## 2026-11-27 — Бэкенд-разработчик. Полная проверка приватности RC1

- Полный pytest прошёл: 421 тест, 1 пропуск. Текст о двух фрагментах по 400 символов найден в production bundle. Хеши трёх файлов совпадают с сообщёнными при заморозке.

## 2026-11-27 — Инженер интеграции с Anki — Репетиция приёмки RC1

- На исходном Python-мосте из рабочих исходников 6338407 с последующими локальными правками прошёл сценарий двух APKG. На синтетическом vocab.db импортированы два слова, записан исходный перевод и первый пример. Затем выбран второй исходный пример, изменён перевод и добавлено новое слово. Вторая колода включила изменённое и новое, третье из первой колоды исключено.
- Штатный import_anki_package Anki 25.09.4 в одной временной коллекции: 2→3, updated1/new1. Проверены выбранная цитата, новый перевод, прежние GUID/ID заметки и карточки, полное расписание и строка revlog. Исключённая карточка целиком сохранена, повтор второго пакета дал duplicate2/new0.
- Отдельный прогон того же сценария на официальном AnkiConnect API6 в новом временном профиле и на отдельном loopback-порту прошёл с теми же утверждениями. Тестовый прокси допускал только version/importPackage, проверял активный тестовый профиль и расположение .apkg в собственном workspace. Обычный local 8765 и личный профиль не использовались. Проверка процессов перед открытием Anki потребовала повышенного доступа. В первом запуске старый маркер завершения помешал перезапуску тестового Anki; исправлен временный runner, повтор обеих отправок прошёл.
- Ждём конечный frozen bridge RC1 и его SHA для привязанной к файлу приёмки. Нативный Kindle Cards в этом прогоне не запускался. Изменён только WORKLOG.md, коммита нет.

## 2026-11-27 — Подготовка нативного RC1 с обычным resolver
- Подготовлен временный сценарий с синтетическим Kindle vocab.db, отдельными workspace и WebView2. KINDLE_CARDS_PYTHON удаляется из окружения, поэтому оболочка выберет соседний frozen bridge по обычной логике.
- Финальный NSIS ожидается. Проверка интерфейса импорта и назначения будет выполнена после сигнала. Установка, пользовательский профиль и реестр не менялись.


## 2026-11-27 — Инженер интеграции с Anki — Приёмка собранного моста RC1

- Повторил два независимых прогона на сборочном `build/rc-1.0.0/bridge-build/kindle-bridge/kindle-bridge.exe`, SHA-256 `51ca7b5efda600c74e51301d75815f2b0ad974bec39e4424bb914e4fdb40fa49`. Синтетические читательская база и коллекция Anki отдельно для каждого прогона. Штатный Anki 25.09.4 обработал 2 новые заметки при первом импорте, 1 обновлённую и 1 новую при втором, 0 новых при повторе, итог 3. Подтвердил точный перевод и выбранную цитату, сохранение GUID/ID заметки и карточки, полей расписания, строки revlog и целой карточки, исключённой из второй выгрузки.
- Те же проверки прошли в новой временной коллекции штатного Anki через официальный AnkiConnect API 6 на отдельном loopback-порту (два вызова version и две отправки importPackage через собранный мост, повторный импорт второго файла оставил те же три ID). Завершил тестовый Anki. Профиль и порт 8765 пользователя не использовались.
- Проверка относится к собранному standalone-мосту. Экземпляр из NSIS и UI этим прогоном не проверялись. Изменён только WORKLOG.md, коммита нет.


## 2026-11-27 — QA-инженер. Миграция и назначения RC1

- Прошли отдельные сквозные прогоны на исходном мосте, предварительном frozen и финальном frozen. SHA-256 финального `kindle-bridge.exe` — `3172f5418c07e65798a3aff39f06571565616f70f597ea1c4dcba43fc88412f8`. Все 260 файлов испытанного комплекта совпали по SHA-256 с `build/rc-1.0.0/bridge`. Комплектная RP-V2 активна (rp-v2-personal, SHA-256 SQLite `a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75`).
- Настоящий мост 0.4.0 (SHA-256 `11858c7b64fe01d30fdad099a955f5e38fea33db19ae05bb0a986cfc392258e8`) извлечён 7-Zip из сохранённого NSIS (SHA-256 `c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826`). Первая неполная копия не стартовала из-за отсутствующих DLL. Полное извлечение позволило создать профиль реальным старым мостом. Для полей правки карточки и решения подготовлены синтетические строки непосредственно в таблицах v4, поскольку соответствующих действий в старом мосте нет; старый мост штатно прочитал эти строки при откате. Остальные данные подготовлены действиями моста.
- Миграция v4→v5 сохранила содержимое 13 таблиц, счётчик истории, 7 ID слов, 8 вхождений, ручные правки и решения, 1 запись повторения, 1 старый экспорт, настройки и оригинальный TSV. Очередь 1→0 после штатного возобновления в отдельной копии. Повторный запуск не плодит резервные копии. Если путь резервирования недоступен, схема и данные остаются v4. Откат выполнен восстановлением резервной SQLite и сохранённых отдельно настроек в чистом тестовом профиле. 0.4.0 открыл профиль и выгрузил APKG с выбранной цитатой и ручным переводом.
- KOReader и Kobo через `import_reader_file` дали по 1 новому слову и 0 при повторном импорте. Проверены ID, ключи книги и исходный контекст там, где его предоставляет формат. Размер порции по умолчанию 6, разово выгружено 101 из 130 допустимых новых, осталось 29. Снимок уровней 1–9 выгрузил 132, вся библиотека — 133, включая ранее выгруженное, пропущенное и приоритет 10. Сверены порядок и строки истории.
- Anki, TSV, Quizlet и RemNote выгрузили по 3 выбранных слова. Повторный APKG сохранил GUID, обновлённые перевод и цитата проверены внутри пакета. Obsidian записал 3/3/3/2 при первой выгрузке, повторе, обновлении и конфликте. Повтор не размножает заметки, SR-комментарий сохранён, столкнувшаяся ручная правка и чужая заметка остались побайтно прежними.
- Только синтетические профили. Проверен собранный мост, установка NSIS, нативный интерфейс, физический USB и импорт непосредственно в Anki остаются отдельными линиями приёмки. Исходники продукта не менялись. Единственное изменение в репозитории — эта запись, коммита нет.


## 2026-11-27 — Инженер интеграции с Anki — Финальный мост RC1

- Повторены два независимых сквозных прогона на `build/rc-1.0.0/bridge-build-final/kindle-bridge/kindle-bridge.exe`, SHA-256 `3172f5418c07e65798a3aff39f06571565616f70f597ea1c4dcba43fc88412f8`. Штатный импорт APKG в Anki 25.09.4 и реальный AnkiConnect API 6: 2→3, одна заметка обновилась и одна добавилась, повтор дал 0 новых. Сохранены GUID и оба ID, расписание, revlog и исключённая карточка. Исправленный перевод и выбранная цитата совпали.
- Только вымышленные слова и отдельные временные коллекции. Личный профиль и его порт 8765 не использованы. Тестовый Anki закрыт. Установщик и UI вне этого прогона. Изменён только WORKLOG.md, без коммита.

## 2026-11-27 — Тимлид. Заморозка исходников закрытого 1.0 RC1

- Согласованы версии Python, Cargo, Tauri и npm 1.0.0 и заголовок окна. В инструкции для локального NSIS закреплены ресурс ранжирования и его паспорт, а README различает кандидата и публичную 0.4.0. Добавили краткий маршрут проверки с читалкой, уточнили описание облачного перевода и поиска обложек.
- Первый полный pytest выявил ложное обнаружение Kindle по имени родительского каталога. Поиск присутствия проверяет метку тома и его собственное имя, сохраняя штатные WPD и файловый пути. Отрицательный тест теперь воспроизводит этот случай независимо от расположения каталога тестов. Повторный полный прогон дал 421 passed и один пропуск на Windows. Прошли 155 Vitest, cargo check, сборка TypeScript/Vite и целевые проверки приватности/модели.
- Владелец отдельно подтвердил обновление зарегистрированной установки и выбор библиотеки рабочей области. Создана отдельная сверенная копия SQLite и настроек. У выбранной библиотеки схема 2. На временной копии новым замороженным мостом проверены переход к схеме 5, точное сохранение исходных записей и восстановление истории из старых отметок выгрузки. Первые проверки самого тестового сценария предполагали наличие таблиц схемы 4 и равенство числа исторических выгрузок в схемах 2 и 5; ожидания сверены с фактической миграцией, повтор прошёл. Чтение по USB оставлено для ручной проверки владельца.
- Ресурс предназначен для закрытой проверки. Приёмка пакета и обновление установленного экземпляра фиксируются отдельно после сверки контрольных сумм.

## 2026-11-27 — Нативный smoke извлечённого NSIS RC1
- SHA-256 NSIS 1e92adc7553f7f178d424d8d998f6ce48dc4dd42a123f29f80067f8609bf1f06, извлечённого bridge 3172f5418c07e65798a3aff39f06571565616f70f597ea1c4dcba43fc88412f8 и EXE 525917ae1f04a03320c5647373098b530461bd9fc9d0e7aec04eb9798e1fe5a5. Отличие EXE от промежуточного тимлид сверил: три байта метки NSIS в .rdata.
- В отдельном пустом workspace/WebView2 запущен извлечённый EXE с обычным resolver и соседним frozen bridge. Экскурсия закрыта, синтетический vocab.db импортирован через поле файла, в списке найдено слово, настройки показали пять назначений, выбран TSV и штатно сохранён файл с этим словом. Ошибок страницы нет.
- Первый тестовый селектор искал «Выгрузить» вместо «Сохранить» для TSV; после исправления сценарий прошёл. Установка и ярлык в этой линии не проверялись. Физическую читалку не синхронизировали, личные данные и окна не использовались.

## 2026-11-27 — Тимлид. Приёмка и обновление установленной Kindle Cards

- Исходники приложения — коммит 832a8e5. Получен закрытый NSIS Windows x64 с SHA-256 1e92adc7553f7f178d424d8d998f6ce48dc4dd42a123f29f80067f8609bf1f06. 260 файлов поставляемого моста совпали с проверенной сборкой. У основного EXE из NSIS хеш 525917ae1f04a03320c5647373098b530461bd9fc9d0e7aec04eb9798e1fe5a5. Сравнение с промежуточным бинарником показало штатное изменение трёх байтов идентификатора формата Tauri (UNK → NSS). Проверены итоговая таблица книжного охвата и её атрибуция.
- На точном мосте прошли переход тестового профиля 0.4.0 со схемы 4 к 5, восстановление старой копии прежним мостом, повторный импорт KOReader/Kobo, пять назначений, защита ручных правок Obsidian, выбранные цитаты и число слов в порции. В отдельных настоящих Anki 25.09.4 и AnkiConnect проверены повтор, новые слова, расписание и история. На извлечённых из NSIS файлах проверены нативные экскурсия, файловый импорт, выбор назначения и сохранение готового TSV. Отдельной чистой Windows VM не было.
- С разрешения владельца фактический установщик обновил зарегистрированную Windows-копию 0.4.0 до 1.0.0 с нулевым кодом завершения. Сверены хеши установленных EXE, моста и SQLite. В пустой профиль назначения перенесены база и настройки из выбранной рабочей области. Копия до перехода хранится отдельно от установки и рабочей области. Проверены целостность установленной базы и сохранение количества слов, обращений и восстановленной истории. Запуск через существующий ярлык меню «Пуск» открыл отвечающее окно Kindle Cards 1.0.
- Физическое подключение Kindle оставлено владельцу. Публичная отправка и публикация не выполнялись. Команды CI по Rust, frontend и Ruff прошли. Дополнительный Ruff вне настроенного охвата CI указал на старые замечания в обработчиках WPD и оформлении импортов kindle_device.py. Уточнена проверка версий публичного workflow, её ожидаемая остановка для этого частного кандидата воспроизведена локально.

## 2026-11-27 — Релиз-инженер. Частный RC1 1.0.0

- Цель: подготовить закрытую Windows x64 поставку для личной проверки владельцем. Продукт собран из коммита 832a8e5 и согласованного локального bridge/model notice. Публичного выпуска, тега и публикации не выполнял.
- В `packaging/build_bridge.py` добавлены явные `--expanded-model`, `--model-notice` и изолированный `--output-dir`. Модель включается только по opt-in, фиксированным именем `rp-v2-expanded.sqlite`; до копирования проверяются SHA-256 A24E16FA…D96F75, SQLite schema v1 и provenance 60BC1A8F…E15DB. Для публичного режима добавлен `--public-release`, отвергающий наличие закрытой SQLite. Ruff прошёл.
- В `.github/workflows/release.yml` удалён автоматический запуск по тегу и attach к GitHub release; оставлен ручной artifact workflow с read-only правом. Публичный 1.0.0 блокируется до разрешения распространения модели, версии шести источников сверяются до упаковки. Передача кода workflow на финальную правку ведущему учтена; изменений после его замечания не делал.
- Свежий PyInstaller bridge собран в conda `kindle_app`. Стандартный smoke прошёл: `load_demo`, `llm_config`, одинаковая обработка очереди из трёх demo слов с dev Python, UTF-8 round-trip `save_card_edit`. Дополнительный smoke именно установленного расположения подтвердил модельные причины приоритета у 3/3 demo записей. SHA bridge EXE 3172F541…88412F8; модель A24E16FA…D96F75.
- Production TypeScript/Vite прошёл. Tauri/NSIS потребовал отдельный target после Windows `os error 32` общего Cargo build-script; с проверенным `CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_DEBUG=true` сборка завершилась. NSIS извлечён 7-Zip только для проверки, не запущен. Версия ProductVersion 1.0.0. Все 260 файлов `bridge/` совпали со staging; SHA модели внутри NSIS совпал. QA сообщил об успешном обновлении 0.4 → 1.0. Встроенный EXE из NSIS имеет SHA 525917AE…E1FE5A5; Tauri изменил три байта `.rdata` при замене bundle marker `UNK` на `NSS` до NSIS.
- Готовая поставка в `build/rc-1.0.0/`: NSIS SHA-256 1E92ADC7…09BF1F06, прежний 0.4.0 сохранён с SHA C2F38D8B…D41826. `SHA256SUMS.txt` содержит контрольные суммы всего каталога (кроме самого manifest), `BUILD-INFO.txt` и `SOURCES.txt` описывают сборку и атрибуцию. `git diff --check` прошёл.
- Ограничения: SQLite распространяется только внутри закрытой личной некоммерческой поставки; публичные лицензионные вопросы остаются открытыми. Не запускал установщик и не использовал пользовательский Kindle, библиотеку или профиль. Коммитов и внешних публикаций от релиз-инженера нет.

- После запуска выполнена полная сверка ресурсов на компьютере владельца. Все 260 файлов моста, входящих в NSIS, совпадают с установленными по SHA-256. После обновления поверх старой установки в каталоге моста также обнаружены 25 файлов вне манифеста. Их происхождение не подтверждено, они оставлены на месте. Изолированный нативный прогон использовал только файлы финального NSIS.

## 2026-11-27 — Релиз-инженер. OpenSSL в замороженном мосте Windows

- В `packaging/build_bridge.py` выбор пары теперь опирается на импорты `_ssl.pyd` сборочного Python. Обе DLL берутся из одного каталога внутри базового окружения: `Library/bin` в conda или каталог расширения `DLLs` в обычном CPython. После PyInstaller пара явно копируется в `_internal`; дубли в других каталогах поставки считаются ошибкой. PATH не используется при выборе.
- Стандартный smoke теперь вызывает `list_llm_models` через штатный OpenAI SDK и локальный HTTP-ответ на 127.0.0.1. Используется провайдер без пользовательского ключа, отдельный workspace и окружение без PATH. Проверяется точное имя модели из ответа.
- Проверены действующая conda, имитация раскладки setup-python и отказ искать недостающую DLL в PATH. На временной копии прежнего RC1 smoke воспроизвёл ошибку `_ssl`; после копирования пары повтор получил HTTP 200 и ожидаемую модель. Новый PyInstaller/NSIS в этой линии не собирался, установленная программа не менялась. Свежий полный комплект и реальная среда GitHub Actions остаются вне этого прогона. База 53f066f.


## 2026-11-27 — QA-инженер. OpenSSL в Windows-мосте RC1

- На неизменённом `build/rc-1.0.0/bridge` (SHA-256 EXE `3172f5418c07e65798a3aff39f06571565616f70f597ea1c4dcba43fc88412f8`) вызов `list_llm_models` к локальному HTTP `/v1/models` завершился ошибкой загрузки `_ssl` («Не найдена указанная процедура»). Сервер не получил запрос. У дочернего процесса только системные каталоги Windows в PATH, профиль временный, ключ синтетический через окружение.
- В PE-таблицах `libssl-3-x64.dll` 3.6.3 найдены пять импортов, которых нет в комплектной `libcrypto-3-x64.dll` 3.5.9: `CRYPTO_calloc`, `CRYPTO_malloc_array`, `CRYPTO_realloc_array`, `OPENSSL_sk_set_thunks`, `X509_STORE_CTX_set_ocsp_resp`. Все пять есть в DLL 3.6.3 из среды kindle_app. Комплектная libssl уже побайтно совпадает с libssl из этой среды.
- Временная копия с заменой ровно одной `libcrypto-3-x64.dll` (новый SHA-256 `5bd5c85c2863c624e1e715f736fe1c20869b106c3bd341df671187839124f2be`) получила HTTP 200 с двумя отсортированными моделями и штатную ошибку ключа при HTTP 401. HTTPS с локальным сертификатом через `SSL_CERT_FILE` вернул те же две модели. Без доверия подтверждён `CERTIFICATE_VERIFY_FAILED`, сервер не получил HTTP-запроса. Первая генерация сертификата OpenSSL завершилась кодом 1, повтор с явно заданным временным конфигом прошёл, полный прогон exit 0.
- Исходная сборка, исходники продукта, установка и личные данные не менялись. Внешний провайдер не вызывался. Изменён только журнал, коммита нет.

## 2026-11-27 — Закрытый NSIS RC1 с исправлением OpenSSL
- Собран отдельный NSIS 1.0.0 x64 currentUser в build/rc-1.0.0-ssl через Tauri bundle, на основе проверенного EXE из RC1 коммита 832a8e5. SHA-256 нового NSIS 56e025f795e58dd305f33c9483b6f24462e2341401f384301da57de1cfd7c928. Прежний NSIS сверён, его SHA-256 1e92adc7553f7f178d424d8d998f6ce48dc4dd42a123f29f80067f8609bf1f06.
- 7-Zip извлёк 267 файлов. Все 260 файлов bridge совпали со staging, относительно старого изменён только libcrypto-3-x64.dll, SHA-256 5bd5c85c2863c624e1e715f736fe1c20869b106c3bd341df671187839124f2be. libssl совпал с окружением и RC1, основной EXE остался побайтно прежним. Модель, её атрибуция и метаданные версии проверены. В новом каталоге сохранены SHA256SUMS и BUILD-INFO.
- HTTPS list_llm_models через извлечённый bridge на временном профиле с заведомо фиктивным токеном получил ожидаемый HTTP 401 и штатное сообщение о ключе. Реальный ключ и учебные данные не использовались. Успешный авторизованный список и установка в этом прогоне не проверялись.
- При первой упаковке Cargo отсутствовал в PATH, повтор с каталогом conda прошёл. Tauri предупредил о повторном патче уже маркированного NSIS EXE; двоичное совпадение извлечённого приложения с прежним NSIS подтверждено. Источники продукта и сборщика не менялись.

### 2026-11-27 — Тимлид. Исправление загрузки списка моделей в установленной 1.0

- Ошибка воспроизведена и в установленном приложении, и на чистом комплекте RC1 до отправки HTTP-запроса. Сборщик захватывал libcrypto 3.5.9 вместе с libssl 3.6.3. В действующей установке атомарно заменена только libcrypto на проверенную 3.6.3 с резервной копией. Тот же обработчик кнопки «Список» через установленный bridge получил корректный ответ на локальном сервере.
- В packaging/build_bridge.py закреплена пара из среды сборочного Python и добавлена проверка list_llm_models в собранном приложении. Полная новая сборка с нуля прошла проверку списка моделей, demo, настроек, очереди и сохранения UTF-8 при перезапуске. Ruff прошёл. 21 тест обогащения и блокировки прошёл с временным каталогом внутри build (первый вызов наткнулся на запрет чтения стандартного каталога pytest).
- Исправленный частный установщик в build/rc-1.0.0-ssl имеет SHA-256 56e025f795e58dd305f33c9483b6f24462e2341401f384301da57de1cfd7c928. Сверены все 260 файлов моста; проверены успешный список при доверенном тестовом сертификате, штатный отказ при недоверенном и ответ 401 от HTTPS API на фиктивный токен. Успешная авторизация у личного провайдера не проверялась. Отпечаток установщика обновлён в docs/releases/1.0.0-rc1.md.

## 2026-11-27 — Релиз-инженер. План внутренней сборки библиотеки и переводов

- Сверены инструменты среды kindle_app (Python 3.11.15, PyInstaller 6.22.3, Cargo 1.96.1) и ресурсы исправленного RC под build/rc-1.0.0-ssl. Локальная expanded SQLite совпадает с RC по SHA-256 A24E16FA…D96F75; эталоны libcrypto 5BD5C85C…F2BE и libssl B4A534D7…C367. Свободно около 122 ГиБ. На момент проверки cargo/rustc/makensis не запущены. База дерева bc4e9cd, в работе уже есть Python и frontend правки.
- После freeze снять манифест входов. Запустить свежий PyInstaller с явными --expanded-model и --model-notice в отдельном staging. Параллельно собрать Vite и Tauri --no-bundle с отдельными frontendDist и CARGO_TARGET_DIR, включая CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_DEBUG=true. Свести артефакты под build/internal-library-translation как именованный EXE и соседний bridge; тестировать с изолированным профилем. Раздельные пути убирают конфликты по dist и target; исходники общие и должны оставаться зафиксированными.
- Прогнать frozen smoke списка моделей через loopback и штатной очереди, сверить модель/атрибуцию/DLL и провести короткий нативный проход библиотеки и перевода на синтетике. На копии профиля проверить миграцию по согласованной схеме, если она изменится. Выдать путь, SHA256SUMS и отметку о фактическом источнике. На этапе подготовки сборок и изменений установленных приложений не было, ожидается явный freeze.

### Уточнение поставки для обновления установленной 1.0

- Обязательный артефакт после freeze — частный Windows x64 NSIS 1.0.0 в build/internal-library-translation. Сохраняются Kindle Cards, identifier com.kindlevocab.cards, заголовок Kindle Cards 1.0 и NSIS currentUser. SQLite остаётся на схеме 5. Действующий профиль остаётся целью обновления владельца; папка preview только опциональна.
- В изолированных каталогах собрать новые UI и bridge, после чего собрать NSIS с этими ресурсами. Извлечь артефакт без установки, сверить EXE, bridge, модель, notice и DLL по SHA-256, пройти проверку библиотеки и перевода на синтетическом профиле. Существующий частный NSIS с OpenSSL остаётся отдельным артефактом. Обновление приложения выполнит владелец. До freeze упаковка не запускалась.

## 2026-11-27 — Фронтенд. Каталог и подтверждение перевода выбранных слов

- По планёрке и UX-ревью проверил текущий WordList и сообщил ведущему о риске пустых ids и общего повтора без scope. Изменены library-workspace.tsx/css. Добавлены селекторы каталога, useCatalogueFilters для состояния навигации и четыре регрессии в catalogue-selectors.test.ts. Контракт перевода использует множество подходящих ID от интеграции ведущего, состояние модели, переход в Настройки и запуск явно переданного списка.
- Поиск, книга, решение, последнее пополнение и уровни пересекаются. Уровни выбираются совместно. «Не учить» скрыто по умолчанию с видимой подписью и отдельным фильтром. Последнее пополнение использует freshness=new, сортировка даты использует first_seen_at и отправляет отсутствующие даты в конец. Приоритетный режим сохраняет порядок оценки и показывает группы. Заголовки групп участвуют в расчёте смещений виртуального списка, при дате они исчезают.
- В диалоге полный список подходящих слов, количество, активные фильтры, модель и пояснение передаваемых полей. Запуск использует снимок непустых ID. Смена подбора или конфигурации до подтверждения требует повторного открытия. При отмене перевод не выполняется. Кнопка настройки сохраняет отбор через хук в main. DOM-цели для возврата фокуса library-translate и library-search.
- Vitest 160/160, tsc/Vite и diff --check по своей области прошли. Playwright 600/1440 на 1455: 12 подходящих → уровни 8/9/10 → 2 слова (vigilant и Aldric), структурная запись вне запроса, отмена сохраняет 2, подтверждение переводит только эти два, после сброса остаётся 10. Пустой запрос не запускается. Проверены настройки с сохранением отбора, группы и режим даты; на длинном списке в узком окне подтверждён возврат фокуса к строке внизу, при изменении решения на «Не учить» — к поиску и возврат слова отдельным фильтром. Первая попытка проверки длинного списка ожидала образец в неверной части сортировки, повтор с фактическим нижним словом прошёл. Снимки .app-data/catalogue-*.png. Нативный интерфейс и внешние провайдеры в этой линии не запускались. Без коммита.
- UI-дизайнер проверил 600/1440 без блокирующих замечаний. Дополнительно просмотрел ночной диалог 600 px и проверил клавиатурное открытие, удержание фокуса и возврат по Escape. QA передала успешный предварительный проход выбора, фильтра решений и карточки. Freeze передан ведущему, повтор после интеграции ведёт QA.


## 2026-11-27 — Бэкенд-разработчик. Контекстное обогащение v2

- В enrichment.py и tauri_bridge.py отправляется текущий разрешённый перевод и одна выбранная цитата до 400 символов. Запрос содержит номер, словоформу, лемму, предполагаемую часть речи и флаг примеров по значениям. Заголовки книг, их ключи, авторы и служебные ID в JSON не добавляются. Полные цитаты используются локально для проверки по хешу.
- В settings.py добавил llm_examples_per_sense, по умолчанию выключено. При включённой опции пачка до двух слов, ограничение трёх значений убрано. Валидируются номера, обязательные поля и полноценные EN/RU пары, капитализация не создаёт дубль значения. OpenAI-совместимый клиент отклоняет оборванный ответ даже с синтаксически корректным JSON. Неудачное обновление сохраняет прежний результат.
- Явный отбор допускает лексические ready и rejected любого уровня. Пустой список даёт ноль, дубли ID учитываются один раз, expected_count сверяется под замком до клиента. Записи без букв получают причину исключения. Автоматическая очередь сохраняет прежнюю видимость необогащённых слов для любого freshness с новыми в начале, кроме skip/known/junk и ранее готовых v1/v2. Готовые v1 остаются доступны для явного обновления.
- В card_fields.py и ответе моста разделены context_matches и review_matches. Смена настройки примеров меняет готовность к новому запросу, сохраняя прежнюю проверку для той же цитаты и исходного перевода. После изменения цитаты или исходного перевода результаты читаются по проверяемой связи. В legacy export_apkg передаются ручные правки. Поля v2 используют существующий payload_json, миграция SQLite отсутствует.
- 51 адресный pytest прошёл без сети, включая четыре валидных смысла, неполную пару, выбранную цитату, хеш фрагмента, смену перевода, сбой повторного запроса и отключённый маршрут. Ruff, compileall и diff --check прошли. Для целого tauri_bridge.py из Ruff исключена прежняя BLE001 в чтении обложек.
- Префиксы до интеграции: enrichment.py 287C26C6, tauri_bridge.py 50E11B36, settings.py C6C86787, card_fields.py E3A0663B, openai_compatible.py B0DADAC6, test_enrichment.py 52B2041C. База bc4e9cd. Настоящие провайдеры, личная библиотека, упаковка и коммит вне этого прогона.


## 2026-11-27 — Инженер интеграции с Anki — Выгрузка значений и пар EN/RU

- В `study_details.py` писатели используют общий `card_fields.enrichment_for_card`: актуальность v2 проверяется по исходному переводу и выбранной цитате независимо от режима дополнительных примеров. Ручной перевод сохраняет приоритет. При смене исходного перевода или цитаты старые дополнительные поля не подставляются. Для контекстного значения требуются уверенная оценка и совпадение хешей полной цитаты и отправленного текста. Для усечённого перевода используется отдельная подпись.
- В `anki_export.py` сохранил идентификаторы, поля, порядок и шаблон Anki. Детали добавлены к существующему блоку ответа, исходная пара примера осталась связанной. В `study_formats.py` Quizlet и RemNote сохраняют одну строку на слово, RemNote экранирует разделители в содержимом. В `obsidian_export.py` детали помещены в прежний оборот Markdown-карточки с экранированием SR. Схема подробного TSV сохранена.
- На временной коллекции штатный Anki 25.09.4 импортировал прежний APKG и обновил одну заметку новым пакетом (0 новых), сохранив GUID/ID, расписание и revlog. Повтор дал 0 новых. Проверен реальный HTML-рендер оборота с ручным переводом, исходной парой и двумя дополнительными парами. Отдельный прогон штатного export_words с v2 из SQLite сохранил пары в четырёх учебных форматах, проверил TSV и подавление устаревших деталей после ручной правки.
- Прошли 84 адресных теста экспорта и повторная проверка пяти затронутых сценариев с явной проверкой четырёх разных пар в Anki, Ruff и diff --check. Промежуточные 3 ошибки тестовых fixtures исчезли после перехода на итоговый review_fingerprint. Писатели: study_details.py 3562CE9189DF, anki_export.py 9F1A55D35C7F, study_formats.py 582771C3A17B, obsidian_export.py DD5892FED39A. Личные профили, внешний импорт Quizlet/RemNote и установщик не использованы. Коммита нет.


## 2026-11-27 — QA-инженер. Независимая приёмка вкладки «Слова»

- Финальный freeze на локальном Vite 1455, Chromium/Playwright, четыре независимых профиля с синтетикой. Проверены 1440×900 и 600×820 в дневной и ночной темах. Browser skill для отдельного Browser plugin недоступен. Обходные шаги стенда: esbuild требовал локального повышенного разрешения, вместо отсутствующей ревизии Chromium использована ранее установленная. Селекторы пробного сценария и фикстура дат приведены к замороженному UI, итоговый скрипт завершился кодом 0. Ошибок страницы и консоли нет.
- Без модели доступен вход в Настройки, возврат активируется после выбора модели. После настройки сохранены уровни 8, 9 и 10. Показ существующей записи 00:17 не сделал её доступной для отправки. Escape закрыл диалог, вернул фокус и оставил 0 запросов. Подтверждение отправило один вызов с lexeme-vigilant и lexeme-aldric, expected_count=2, retry_failed=true. Только эти две записи получили ready. Пустой поиск недоступен для запуска.
- На 600 px проверены клавиатурный выбор уровней, закрытие меню, скрытие «Не учить», возврат фокуса в поиск, восстановление слова фильтром и снятие решения. «Последнее пополнение» показало только freshness=new. При сортировке по разным синтетическим first_seen_at порядок убывает и группы скрываются, при возврате к приоритету группы появляются. Отдельно проверены фокус при открытии и возврат к строке. В обеих темах карточка сохранила выбранную вторую цитату и ручной перевод, после проверки показала значение в цитате и два отдельных примера ИИ. Снимки вне репозитория.
- Штатный исходный мост с синтетическим HTTP /v1/chat/completions принял 3 ID двумя пачками 2+1, сохранил ручное значение и выбранную цитату для kept, записал уточнённый перевод для refined и показал сгенерированный пример для weak. В запросе только утверждённые поля и одна выбранная цитата на запись. Неверный expected_count и попытка повторить уже готовую выборку не достигли сервера. Снятие флага примеров дало pending с review_matches=true, последующее изменение ручного перевода дало pending с review_matches=false. После реального импорта нового слова и точного повтора состав freshness=new остался тем же.
- Префиксы SHA-256 проверенного дерева: library-workspace.tsx CBE7D601EFA4, card-editor.tsx A91C8046B6C8, enrichment.py 287C26C66031, tauri_bridge.py 50E11B3615A1, база bc4e9cd. Нативный WebView2, собранный мост и настоящий поставщик моделей остаются отдельными линиями. Продукт и личные данные не менялись, коммита нет.


## 2026-11-27 — Бэкенд-разработчик. Совместимость старой библиотеки и обрывы ответа v2

- В первом полном прогоне 429 прошли, 1 пропущен, golden-проверка общего ответа моста ожидаемо обнаружила добавленные статусы и более осторожную автоочередь. В tests/test_library_migrations.py разделил проверку исторических полей и новой части ответа. Исходный golden JSON сохранён. Сравнение load_catalog по-прежнему полное. Отдельно проверены новые статусы всех семи записей стенда, два флага у старого ответа без доказуемого соответствия и pending 1 вместо 2, потому что готовое старое обогащение не уходит в автоматическую отправку.
- Повторный полный pytest после поправки golden: 430 прошли, 1 пропущен. В anthropic_client.py дополнительно распознаются исчерпание контекстного окна и прочие незавершённые ответы. Действующий max_tokens оставлен. 27 финальных адресных тестов прошли, включая Anthropic через подставной SDK. Ruff, compileall и diff --check прошли.
- Обновлённые префиксы SHA-256 для заморозки: anthropic_client.py 42F53B62, test_enrichment.py 35CA8FF6, test_library_migrations.py 102316DA. Остальные перечисленные выше хеши прежние.


## 2026-11-27 — Бэкенд-разработчик. Финальная проверка v2 после заморозки

- Полный pytest на наборе с итоговой проверкой обоих провайдерских сигналов обрыва: 431 тест прошёл, 1 пропущен. Рабочий комплект хешей совпадает с последним объявлением о заморозке.

## 2026-11-27 — Нативная приёмка перевода: блокер предварительного NSIS
- Из предварительного установщика SHA ED460FCF… извлечена пара EXE 676F8423… и bridge 6E270D36…. В отдельном WebView2 с синтетической библиотекой EXE открыл индекс файлов staging/frontend вместо приложения. Точный URL и способ воспроизведения переданы ведущему и релиз-инженеру. В конфиге обнаружен абсолютный Windows frontendDist, вероятно распознанный как URL.
- Перевод не запустился из-за отсутствия интерфейса. Тестовый сценарий с loopback-моделью и одной выбранной записью подготовлен; чистый повтор ожидает исправленный пакет. Профиль владельца и устройство не использовались, установщик не запускался, продуктовые файлы не менялись.

## 2026-11-27 — Релиз-инженер. Закрытый NSIS для проверки библиотеки и переводов

- После явного freeze собраны отдельные production Vite, Tauri и PyInstaller в build/internal-library-translation. Зафиксированы 137 входов рабочего дерева на базе bc4e9cd. Сохранились Windows x64 currentUser, ProductVersion 1.0.0, identifier com.kindlevocab.cards, заголовок Kindle Cards 1.0 и SQLite v5.
- После первого PyInstaller найдено изменение anthropic_client.py. В первом байткоде правки ещё не было. Мост собран заново, наличие ветки обработки model_context_window_exceeded подтверждено по извлечённому байткоду. Стандартный frozen smoke завершился успешно. Все 260 файлов bridge из итогового NSIS совпали со staging. Модель, notice и обе OpenSSL DLL совпали с исправленным RC, его NSIS сохранил SHA 56e025f7…7c928.
- QA обнаружила, что нативная оболочка промежуточной сборки открывала file URL каталога frontend. Относительный frontendDist от src-tauri устранил причину. Извлечённый финальный EXE на временном WebView2 открыл http://tauri.localhost/, отрисовал Главную и загрузил точные index-gnXkFhP7.js и index-BSn-oVBD.css. Первый прогон исправленной оболочки отрисовался, но скрипт возвратил ошибку при завершении уже закрывшегося процесса. После исправления завершения повтор вернул 0.
- На извлечённом frozen bridge прошли /v1/models и /v1/chat/completions через локальный сервер. В синтетической библиотеке из трёх слов перевелось только выбранное, запрос содержал одну цитату до 400 символов без полей книги. Ручной перевод и результат сохранились после перезапуска. Подтверждены источник книжного приоритета и целостность SQLite v5. Первый предварительный тест ошибочно ожидал одинаковую длину разных демо-наборов; исправленный сценарий выдержал повтор на финальном мосте.
- Финальный Kindle Cards_1.0.0_x64-setup.exe, 45 229 020 байт, SHA-256 0290c9fc085e14c41bc80805373bb87a7bc3f84c4e1994eb90e6a65dedace888. SHA-256 извлечённых EXE 92400818…f7985e и bridge 58525b6b…1f1d9. Сверены SHA256SUMS, манифест входов и манифест payload. Сам установщик не запускался, установленное приложение и профиль не изменялись, публикации и коммита не было.

## 2026-11-27 — Нативная приёмка исправленного NSIS перевода
- Из пакета SHA-256 0290c9fc085e14c41bc80805373bb87a7bc3f84c4e1994eb90e6a65dedace888 извлечены EXE 92400818… и bridge 58525b6b…. Новый временный WebView2 открыл Kindle Cards со встроенным интерфейсом после исправления frontendDist.
- Через Слова и Настройки включён перевод, выбран LM Studio и временная модель. Из двух вымышленных записей отфильтрован glimpse. Диалог показал ровно одно слово и локального получателя. Состоялся ровно один POST на собственный loopback, второй записи в запросе нет. Карточка показала уточнённый перевод, значение и перевод цитаты, пример. Итог 1/0, ошибок страницы нет. Созданы снимки подтверждения и карточки.
- Первоначальный синтетический ответ без definition_en и note_ru отклонён валидатором, после заполнения всех обязательных полей прогон прошёл. Тест использовал отдельные workspace/WebView2 и подмену обнаружения читалки. Установка, личный профиль и реальный провайдер не использовались. Продуктовых правок нет.

## 2026-11-27 — Тимлид. Выбор слов и проверка перевода в библиотеке

- Планёрка с продактом и UX зафиксирована в docs/plan/meetings.md. Отбор библиотеки теперь отделён от автоматической очереди и рекомендаций для Anki. Настройки ведут к выбору слов, каталог показывает полную выборку перед явным запуском. Сохраняются уровни, поиск и решения при возврате из настроек. Последнее пополнение определяется по факту импорта. В карточке различаются исходный перевод, значение в цитате и примеры отдельных значений.
- Объединены библиотечный UI, controller и mock, параметры провайдера, Python-контракт v2 и писатели учебных карточек. Настройки описывают передаваемые данные. Повтор ограничен исходным набором ID. Ручное решение о слове, исходный книжный пример и ручная правка перевода сохраняются. Обновлены README и PRODUCT.
- На финальных исходниках 161 тест Vitest прошёл. Полный pytest на промежуточном дереве выявил разъехавшиеся золотой ответ и тестовые данные авторизации проверки v2. После сверки контрактов итоговый полный прогон бэкенда: 431 прошёл, 1 пропущен. Проверены TypeScript, Vite, целевые Ruff, diff --check. Независимый Chromium на 600/1440 в обеих темах проверил выбранные ID и число, клавиатуру, фильтрацию решений, порядок добавления и две пары примеров для разных значений. Проверка HTTP использовала отдельный локальный ответ и синтетический профиль. Штатный Anki подтвердил обновление одной заметки с сохранением расписания.
- Предварительный NSIS открыл индекс локальной папки; его отклонили до установки. В окончательном NSIS frontendDist относителен, индекс/JS/CSS действительно встроены. В отдельном WebView2 из этого пакета пройден путь от выбора LM Studio до перевода одного подтверждённого слова. Личные слова облачным провайдерам не отправлялись; языковое качество отдельной коммерческой модели не оценивалось.
- После согласия владельца обновлена его зарегистрированная Windows-копия текущего пользователя. SHA-256 принятого частного NSIS 0290c9fc085e14c41bc80805373bb87a7bc3f84c4e1994eb90e6a65dedace888. 261 файл установки совпал с манифестом. До запуска установщика SQLite отклонил логическое резервирование исходного профиля, файл оказался короче длины из его собственного заголовка. До и после установки сверены точные копии исходных байтов базы, журналов и настроек. Проверена целая резервная копия до миграции, на отдельном дубликате успешно открывается текущим установленным мостом. Дальнейшее восстановление рабочего профиля согласуется отдельно. Установщик не публиковался.


## 2026-11-27 — QA-инженер. Завершение браузерной проверки каталога

- После завершения нативной приёмки проверен порт 1455. Vite уже был остановлен, активного слушателя нет. Все семь снимков предыдущей приёмки остались в прежнем временном каталоге вне репозитория. Исходники и снимки не менялись, коммита нет.


## 2026-11-27 — Бэкенд-разработчик. Диагностика повреждённого снимка библиотеки

- Диагностика выполнялась на отдельных временных дубликатах. В сырой копии были 892 из объявленных 1304 страниц SQLite, WAL пуст. Дополнение нулями не восстановило целостность. Здоровые исходный v2 и мигрированный v5 открылись read-only и выдержали integrity_check. Сырая копия и здоровый v5 совпали по хешам до и после.
- Обход сохранившихся ветвей подтвердил 1357 слов, 2141 вхождение, 1379 анализов и 2051 форму. Все сопоставились со здоровым v5 без изменений. У таблиц ручных правок, обогащения, решений и истории экспорта отсутствуют корневые страницы. 35 оторванных записей не удалось подтвердить по логическим ключам. В уцелевших состояниях назначений однозначно изменилось только время проверки Obsidian у 1450 строк.
- По согласованию создан отдельный кандидат на основе целого мигрированного v5. Перенесены только 1450 более поздних времён проверки Obsidian. Сравнение всех таблиц подтвердило отсутствие других изменений. Независимое read-only переоткрытие: integrity_check ok, foreign_key_check без строк, схема 5, журнальных файлов рядом нет. Кандидат содержит 1768 слов, 2564 вхождения, 3 записи о выгрузках и 3500 элементов выгрузки. Новые ручные правки, результаты ИИ и решения подтвердить не удалось. Рабочая БД и прежний здоровый кандидат не менялись.


## 2026-11-27 — Тимлид. Возврат рабочей библиотеки после обновления каталога

- После явного согласия владельца принята отдельная объединённая SQLite v5. У кандидата проверены контрольная сумма, целостность и внешние ключи. Перенесены 1450 подтверждённых отметок времени проверки Obsidian. Новейшие ручные правки, решения и результаты ИИ по сохранившимся страницам установить нельзя. 35 записей без надёжной привязки к таблицам остались в исходном снимке.
- Перед атомарной заменой при закрытом приложении сверены файлы рабочего профиля с побайтным резервом. Логическое содержимое новой рабочей БД совпало с кандидатом. Штатный установленный мост прочитал 1768 слов и 2564 книжных вхождения, у всех слов есть состояние проверки перевода. Исходный снимок повреждённой БД сохранён. Контрольная сумма настроек совпала с копией до восстановления.
- Запущен установленный исполняемый файл принятого пакета, окно Kindle Cards 1.0 отвечает. Слова владельца внешнему ИИ для проверки не отправлялись. Исходники каталога и проверки перевода зафиксированы в 956446b.


## 2026-11-27 — Фронтенд-разработчик. Диалог фильтров каталога

- Добавил catalogue-filter-dialog.tsx и catalogue-filter-dialog.css. Кнопка «Фильтры» считает активные категории. В диалоге все десять уровней видны сразу, на ширине до 640 px в два ряда. Решение, книга и последнее пополнение входят в один черновик.
- «Применить» передаёт снимок одним вызовом. Отмена, Escape и клик снаружи закрывают окно без применения. Сброс возвращает стандартный отбор, сохраняя сортировку. Открытие фокусирует заголовок, Radix возвращает фокус на кнопку. В коротком окне прокручивается тело, футер остаётся видимым. Локальная лампа заимствована из ClipLamp, её положение и свет ограничены стилями диалога.
- TypeScript, 161 тест Vitest и проверка пробелов в обоих новых файлах прошли. Интегрированный браузерный прогон и визуальное ревью ведёт тимлид. Установленное окно, установка и рабочий профиль не использовались. Коммита нет.


## 2026-11-27 — QA-инженер. Независимая проверка диалога фильтров

- Chromium на локальном 1456, отдельные синтетические контексты 600×720 (ночь) и 1440×720 (день). Книга, последнее пополнение и «Учить» совместно оставили одну ожидаемую запись. Другой запрос, книга или решение убирали её. Отмена и Escape сохранили применённый отбор, сброс с применением вернул стандартный отбор и сохранил поисковый запрос, порядок по дате и исходную последовательность видимых строк после очистки поиска.
- Начальный фокус на заголовке, Tab с последнего элемента вернулся на первый, Shift+Tab — обратно, закрытие вернуло фокус на «Фильтры». На cold-start статус очереди сменился на «Библиотека готова» при открытом диалоге и остался отдельным элементом role=status. Начальные ожидания тестового скрипта для текста подтверждения решения и названия статуса уточнены по фактической разметке, итоговый прогон exit 0.
- Блокирующих дефектов и ошибок Chromium в двух основных контекстах нет. Собственный браузер закрыт, стенд оставлен ведущему. Исходники не менялись, установленная копия и личный профиль не использовались.


## 2026-11-27 — Тимлид. Редизайн сортировки и фильтров «Слов»

- В library-workspace размещены поиск, меню сортировки и заметная кнопка «Фильтры». Активные условия снимаются отдельно. Штатное скрытие «Не учить» видно рядом со списком. Загрузка вынесена под каталог к отдельной полосе состояния. При смене отбора или порядка список начинается с первой записи. Правила отбора и выбор слов для ИИ продолжают использовать существующие селекторы.
- Фронтенд добавил единую панель с черновиком, уровнями, книгой, решением и последним пополнением. По итогам дизайн-ревью уточнены положение панели, графитовая опора зажима, пунктир клавиатурного фокуса и перенос отметки длинного списка уровней. При первой проверке общий класс lamp-host переопределил фиксированную позицию панели. Локальная специфичность устранила сдвиг. Протокол и критерии в docs/plan/meetings.md.
- Во встроенном браузере уровни 8/9/10 дали три видимые записи и две подходящие для ИИ. Проверены сортировка по дате, отмена, фокус и внутренняя прокрутка на 390×450 с видимым футером. Независимая проверка Chromium на 600×720 и 1440×720 прошла, включая пересечение с книгой, поиском и решением, сброс и фоновое изменение статуса обработки. Просмотрены снимки дневной и ночной темы. Vitest 161/161, TypeScript/Vite и diff --check прошли.
- Изменения проверены на демонстрационной библиотеке. Рабочее окно, установка и профиль владельца не затрагивались. Для всех привлечённых специалистов использован gpt-6.2-sol. Запрет Astra закреплён в AGENTS.md.


## 2026-11-27 — Тимлид. Проверка значений по нескольким частям речи

- Диагностика одной указанной карточки подтвердила активный режим отдельных примеров. Сохранённый ответ правильно описал выражение из цитаты, но подтвердил узкий словарный перевод и вернул одно значение. Исходный словарь выбрал статью по подсказке глагольной части речи.
- В enrichment.py подсказка части речи трактуется как гипотеза для контекста. Основные значения отдельного слова запрашиваются по всем употребительным частям речи. Для составных выражений значение цитаты и значения отдельно взятого слова запрашиваются независимо. Формат сохранённых результатов прежний.
- Готовая карточка получила «Перепроверить перевод». tauri_bridge допускает ровно один готовый ID, сохраняет старый результат при сбое или ответе без замены для уже имеющегося перевода. Перепроверка использует словарный или ручной исходник, а повтор после сбоя удерживает ID и режим. Обновлены контроллер, редактор и демонстрационный мост.
- 28 адресных Python-тестов прошли, включая ответы с существительным, глаголом и прилагательным, защиту прежней карточки и точный выбор. 161 Vitest и TypeScript/Vite прошли. Во встроенном браузере повторный запрос обработал ровно одну синтетическую запись. Ruff для изменений прошёл, обычный полный Ruff файла tauri_bridge.py обнаружил прежний BLE001 в загрузке обложек. Проверка не обращалась к внешней модели. Рабочий профиль читался только для диагностики указанной карточки, установленное приложение не перезапускалось.


## 2026-11-27 — Релиз-инженер. Закрытый NSIS каталога и многозначной проверки перевода

- Собран отдельный Windows x64 NSIS 1.0.0 в build/internal-catalogue-senses. Входы зафиксированы по SHA-256 на базе 1c5712c, включая оба новых файла диалога фильтров. Идентификатор com.kindlevocab.cards, заголовок Kindle Cards 1.0 и currentUser сохранены. Производственные JS и CSS собраны отдельно и обнаружены в извлечённом EXE. TypeScript и production Vite прошли. Первый вызов Vite с esbuild не прочитал родительский каталог в ограниченной среде, повтор с configLoader runner прошёл. Для Rust переиспользован свободный промежуточный Cargo target, прежний готовый установщик остался прежним по SHA-256.
- PyInstaller собран заново. Встроенные модель RP-V2 и атрибуция сверены с принятым комплектом, обе DLL OpenSSL совпали с той же парой в эталоне. Прошли штатные проверки списка моделей по loopback, demo, настроек, очереди из трёх записей и UTF-8 после перезапуска. 7-Zip извлёк 267 файлов без запуска NSIS. Все 260 файлов моста побайтно совпали со staging. Основной EXE отличается от промежуточного только штатной меткой упаковки Tauri. Сверены исходные файлы, MANIFEST.json, NSIS-PAYLOAD.sha256 и SHA256SUMS.txt.
- SHA-256 NSIS d11c2113f390941f3caef6862e05af2906a5167d5e8b97db43d464cd0575be9e. Извлечённые EXE dcddbc56ed87104408365934fd13ab23ccc2867d4513122f5cb620f95741bc8c, мост 2723faae1766c73ab827c3fecc2c91d3fd7b61c7ffa6ceb0bc1d582e39b38d98 и SQLite модели a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75. Манифест полезной нагрузки из 261 строки имеет SHA-256 e74e9f3b1562038bc3eec812b663b156fb9fca69be5263d6e162636db227900d.
- На извлечённом мосте и временном профиле проверены список моделей, активная RP-V2 Personal, три обращения на loopback для одной вымышленной карточки и запрос значений по частям речи. Ответ без перевода сохранил предыдущий результат. Следующий ответ сохранил две пары значений с примерами, ручной перевод остался в карточке. Проверка целостности SQLite v5 прошла. Первый сценарий искал книжный пример по полю сгенерированного примера, после выбора по исходным вхождениям повтор прошёл.
- Окно из NSIS передано отдельной линии нативной приёмки. Установщик не запускался. Пользовательские окна, рабочий профиль, настоящие провайдеры и публикация вне этой проверки. Исходники продукта не менялись, коммита нет.

## 2026-11-27 — QA-инженер. Закрытый NSIS, фильтры и перепроверка перевода

- Сверены NSIS D11C2113…BE9E, извлечённые оболочка DCDDBC56…BC8C и мост 2723FAAE…8D98. 18 адресных pytest обогащения прошли.
- Независимый прогон извлечённого моста на отдельной SQLite и LM Studio-совместимом loopback дал одну готовую карточку с одним значением. Штатный recheck сделал ровно один отдельный POST с одной записью, запросом значений по нескольким частям речи, исходным переводом и одной цитатой. После нового запуска моста видны две сохранённые пары существительного и глагола. Вторая запись не переведена.
- Нативный сценарий запускал извлечённую оболочку с временным WebView2 и штатным выбором соседнего моста. Playwright не подключился. При диагностике /json/version кратко ответил, но порт стал недоступен. Независимая попытка через raw CDP не получила целевую страницу. Проверка нативного диалога, фокуса и отрисовки результатов этим сценарием не завершена. Установщик, личный профиль и реальный провайдер не запускались, исходники не правились.


## 2026-11-27 — Тимлид. Установка обновлённых фильтров и проверки значений

- Объединены новый диалог фильтров и перепроверка готовой карточки в частный NSIS 1.0.0 под build/internal-catalogue-senses. SHA-256 установщика d11c2113f390941f3caef6862e05af2906a5167d5e8b97db43d464cd0575be9e, манифеста содержимого e74e9f3b1562038bc3eec812b663b156fb9fca69be5263d6e162636db227900d. Прежний пакет оставлен отдельно.
- Полный pytest: 432 прошли, 1 пропущен. Фронтенд: 161 тест и production build. Дизайн проверен в отдельном превью. Два сквозных прогона извлечённого моста проверили один локальный запрос перепроверки, отдельные пары значений существительного и глагола, сохранение старого результата при ошибочном ответе и сохранение ручной правки. Автоматизированное подключение к отдельному WebView2 не удержалось.
- После подтверждения пустой очереди штатно применён установщик. Проверенная резервная копия создана до обновления. Сверены все 261 файл установки, логическое содержимое SQLite на 2047 слов и побайтовые настройки совпали с копией. Установленная Kindle Cards 1.0 открылась и отвечает. По просьбе владельца проверка на его рабочем окне через Computer Use прекращена. Коммит и публикация не выполнялись.

## 2026-11-27 — Бэкенд. Настройка показа полного книжного охвата

- В kindle_vocab_app/settings.py добавлен show_full_book_coverage. Для нового профиля и старого settings.json без поля действует false. Включает показ только логическое true. Поле сохраняется штатным JSON настроек, в том числе при следующем частичном сохранении настроек старым интерфейсом.
- В tests/test_export_words.py добавлена проверка штатных load_settings/save_settings для нового и старого профилей, записи на диск, сохранения при частичном обновлении и выключения. Все 4 SettingsTests и diff --check прошли.
- Проверка интерфейса и сборки относится к интеграции. Установленное приложение и пользовательский профиль не открывались. Коммита нет.


## 2026-11-27 — Тимлид. Скрытие слов с охватом 100%

- В «Настройки → Общие» добавлен сохраняемый переключатель. По умолчанию выключен, включая профили без нового поля. Общий предикат каталога и рекомендаций сверяет точный книжный охват RP-V2. В совместимом режиме без отдельного поля берётся книжный балл только для рассчитанной оценки. Округление и персональный балл не влияют на скрытие. Полная выгрузка включает все записи выбранных уровней. Решение записано в docs/plan/meetings.md.
- Vitest 162/162, TypeScript и production Vite прошли. 51 тест экспорта и настроек прошёл. Отдельный headless Chromium показал применение переключателя в поиске, подборке, порции и полную выгрузку с точным составом. Приёмка использовала синтетические записи, Computer Use и установленное приложение не использовались.

## 2026-11-27 — QA-инженер. Настройка показа полного книжного охвата

- Независимый Chromium/Playwright на Vite 1456, отдельные синтетические профили 600×820 в ночной теме и 1440×900 в дневной. Временная подмена только тестовых значений ответа моста: dread с охватом ровно 1, admit с итоговым баллом 1 и книжным охватом 0,4. После штатного завершения очереди отбор проверен по фактическому DOM и вызовам mock bridge.
- По умолчанию dread скрыт и при прямом поиске, admit и предварительный ephemeral доступны. «Показывать слова с охватом 100%» с клавиатуры сохранил true и вернул dread в активный поиск, повторное переключение отправило false и вновь его скрыло.
- Главная: при выключенном показе «Все новые» отправили 4 ID, порция из двух отправила 2 ID, в обоих dread отсутствовал и порядок совпал с предпросмотром. «Вся библиотека» отправила все 13 ID, включая dread, с уровнями 1–10. При включении «Все новые» отправили 5 ID, включая dread. Все четыре mock-выгрузки завершились.
- Финальный сценарий завершился кодом 0. Ошибок страницы и консоли, Vite overlay и горизонтального переполнения нет. Снимки сохранены вне репозитория. В первом прогоне фикстура читалась до обработки, затем слишком узкий селектор статуса задержал проверку после отправки. Оба исправлены в временном сценарии. Стенд не останавливал, исходники не менял. Нативное окно, устройство и личный профиль не использовались.

## 2026-11-27 — Релиз-инженер. Частный NSIS с настройкой полного книжного охвата

- Собран закрытый Windows x64 NSIS в build/internal-full-book-coverage из снимка на базе 1c5712c с обоими файлами диалога фильтров и настройкой show_full_book_coverage. Сохранены 1.0.0, currentUser, com.kindlevocab.cards и заголовок Kindle Cards 1.0. Входы сверены после сборки.
- TypeScript прошёл. Первоначальный загрузчик Vite встретил ограничение доступа к родительскому каталогу, production сборка с configLoader runner прошла. Cargo в общем и отдельном target получал Windows os error 32 и один os error 5 для serde_core build script. Штатный ранее принятый профиль CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_DEBUG=true переиспользовал кэш, скомпилировал оболочку и позволил выполнить NSIS. Системная защита не менялась.
- В извлечённой x64 оболочке точно подтверждены сжатые production JS/CSS, побайтно совпавшие после Brotli-распаковки, и надпись «Показывать слова с охватом 100%». Все 260 файлов bridge совпали со staging. Модель RP-V2, атрибуция и обе OpenSSL DLL совпали с предыдущей поставкой. Манифест содержит 261 устанавливаемый файл приложения.
- Свежий PyInstaller прошёл load_demo, llm_config, loopback list_llm_models, штатную очередь из трёх синтетических слов и UTF-8 правку. Извлечённый bridge в отдельном временном профиле подтвердил false без файла и в старом settings.json, true после записи, сохранение true при частичном обновлении и повторное false. Дополнительно на извлечённом мосте прошли load_demo и loopback list_llm_models.
- SHA-256 NSIS 0a3f39deffd345d28660fe35e2b7b14db609795a82dd91c4e48c88fc1633fa1c, NSIS-PAYLOAD.sha256 4e419857fef9e6ac52c354449639ef4cd546516c8d2edba8a20af2fd2d4701f2. Извлечённые оболочка 98d09b77…c5482 и bridge d1dce2a3…05dce. Предыдущий принятый NSIS совпал со своим SHA. Установка, окно и рабочая библиотека остались за ведущим. Исходники не менялись, коммита и публикации нет.


## 2026-11-27 — Тимлид. Установка настройки показа охвата 100%

- Пользователь запросил сборку и обновление установленной Kindle Cards без Computer Use. Частный NSIS собран в build/internal-full-book-coverage. SHA-256 установщика 0a3f39deffd345d28660fe35e2b7b14db609795a82dd91c4e48c88fc1633fa1c, манифеста 4e419857fef9e6ac52c354449639ef4cd546516c8d2edba8a20af2fd2d4701f2. Встроенные ресурсы EXE и название переключателя сверены после распаковки. Штатный профиль Cargo с символами отладки зависимостей сборки устранил повторяющиеся Windows 5/32 без изменения системных настроек.
- Полный pytest: 433 прошли, 1 пропущен. Для тех же исходников прошли 162 Vitest, TypeScript и Vite, фильтрация подтверждена в отдельном headless-превью. Мост из установщика проверен на временном профиле.
- Перед обновлением пустая очередь и SQLite v5 с 2047 словами подтверждены. Создан проверенный снимок библиотеки и настроек. После установки сверены все 261 файл, логическое содержимое базы и байты настроек совпали с копией. Kindle Cards 1.0 запущена и отвечает. Независимый CLI-прогон установленного моста на временном профиле подтвердил выключенное исходное состояние, сохранение включения и повторное выключение. Computer Use и пользовательская настройка для теста не использовались.

## 2026-11-27 — QA совместимости карточек Obsidian

- Фактический вывод export_cards проверен парсером, разделением сторон и NotesDataStore официального Spaced Repetition 1.15.4 (22fbea0) в четырёх временных синтетических хранилищах: стандартный разделитель и пользовательские %%card%%/%%end%%, SM-2 и FSRS. До и после повторной записи определяется одна карточка. Цитата и источник на передней стороне, перевод, значение в цитате и три пары примеров на обороте.
- После обновления перевода и примеров расписание совпало целиком, байты комментария, путь заметки и настройки плагина сохранены. Третий экспорт побайтно прежний. Первое ожидание теста не учло штатное кодирование подчёркиваний, после правки фикстуры все сценарии прошли. GUI, клавиатура и личное хранилище не использовались. Исходники не менялись.


## 2026-11-27 — Тимлид. Дизайн выгрузки карточек Obsidian

- Экспорт Kindle Cards для Spaced Repetition выводит крупное слово и раскрываемую книжную цитату с источником на лице, отдельные секции перевода, смысла в цитате и примеров на обороте. Английский пример и русский перевод на разных строках. Отображение использует обычную разметку темы Obsidian. study_details предоставляет структурированные пары, плоские строки других форматов сохраняют прежний вид.
- Сохранены по одной физической строке на сторону, постоянный ID, границы заметки, inline-комментарии, проверка подписи исходной заметки и правило внешнего расписания. Строчный HTML на обороте оставляет callout FSRS отдельным блоком. Для старого формата добавлен тест перехода на новый вид с сохранением пути и расписания. В SR 1.15.4 обработчик клавиатуры забирает Enter и пробел с summary. Кнопку раскрытия проверяли в браузерном превью мышью.
- Ruff и diff --check прошли. Расширенный прогон дважды встретил разовые WinError 5 при атомарной замене файлов настроек и TSV в тестах вне сценария Obsidian. Повтор затронутых и ранее упавших тестов в новом системном временном каталоге: 40 прошли. Парсер и NotesDataStore SR 1.15.4 подтвердили обе стороны и сохранение SM-2/FSRS на реальном синтетическом экспорте. Просмотрены PNG и проверены раскрытие/перенос в headless Chromium на 1160 и 410 px. Рабочий vault и нативный интерфейс не открывались. Установка не обновлялась.

## 2026-11-27 — Бэкенд-разработчик. Однократная инициализация dev-профиля Windows

- `scripts/dev_profile.py` сохраняет существующий dev-профиль и при первом запуске публикует полный `.app-data` одной операцией переименования. Библиотека копируется через SQLite Online Backup с учётом подтверждённых записей в WAL. Копия проходит проверку целостности и версии схемы. В скопированных настройках выключается `llm_auto_enrich`, неизвестные поля сохраняются. Комплектная модель охвата и найденное уведомление об источниках переносятся отдельно в каталог моделей, проекция проверяется перед публикацией.
- `tests/test_dev_profile.py`: 8 синтетических тестов прошли в окружении `kindle_app`. Проверены видимость записи из незакрытого WAL, точное совпадение байтов исходной БД, активного WAL и настроек, повтор с локальными правками, пути с пробелами и кириллицей, повреждения базы, настроек и модели, изоляция пути и конкурентный старт. Ruff прошёл. Первый запуск pytest встретил WinError 5 при чтении общего pytest-temp, повтор с новым `--basetemp` прошёл.
- Чтение через `mode=ro` сохраняет данные источника. SQLite при работе с WAL использует служебные блокировки и может создать пустой WAL и SHM, если они ещё отсутствуют. Режим `immutable=1` в отдельной пробе пропустил подтверждённую WAL-запись и для библиотеки не используется. Личный профиль и внешние сервисы этой проверкой не использовались, коммита нет.

## 2026-11-27 — Тимлид. Повторяемый запуск Kindle Cards из исходников

- Добавлены scripts/run-dev.ps1 и scripts/run_dev.py. Команда из корня запускает Tauri, Vite и Python из kindle_app. Постоянный профиль отделён от установленной программы, блокируется на время запуска и сохраняет библиотеку, настройки и данные WebView2. Путь можно задать явно, для нового пути доступен пустой профиль. Обновлены docs/DEVELOPMENT.md и подсказка scripts/setup-dev.ps1.
- По умолчанию подготовлена однократная копия установленной SQLite и настроек с моделью книжного охвата. Быстрая проверка целостности и количества по семи таблицам совпали у источника и копии: 2047 слов и 2976 контекстов. Автообогащение в копии выключено. В llm/presets.py добавлен выбор отдельного пространства ключей для разработки с прежним значением по умолчанию для установленной версии.
- Два нативных запуска на отдельном синтетическом профиле открыли Kindle Cards (Dev), Vite ответил HTTP 200. Между запусками штатным мостом импортированы слово и цитата, записаны ручной перевод, решение и настройки. После закрытия и повторного запуска все данные сохранились. Закрыты только два окна проверки, без Computer Use.
- 42 адресных pytest прошли. Первый запуск pytest не смог открыть общий временный каталог Windows, полный повтор в новом временном каталоге прошёл. Установленная программа, физический Kindle и внешние сервисы в проверке не использовались, коммита нет.

## 2026-11-27 — Тимлид. Проверка и отправка накопленных изменений

- По запросу владельца подготовлены к отправке пять локальных коммитов и изменения каталога, проверки переводов, показа стопроцентного книжного охвата, карточек Obsidian и запуска из исходников в постоянном профиле. Проверены пять ранее подготовленных концепт-изображений. Экранные данные на макетах ограничены общим прогрессом, личных слов и путей нет. Независимая проверка состава подтвердила, что временные настройки инструментов и архивы восстановления остаются локально. Проверка исходящих добавлений по именам файлов и шаблонам ключей прошла.
- Первый общий pytest выявил пять WinError 5 при атомарной замене файла настроек или TSV. Четыре сценария прошли отдельно, а сохранение настроек повторно встретило блокировку. Добавлен ограниченный повтор атомарной замены для Windows 5, 32 и 33. Настройки записываются во временный файл с уникальным именем. Регрессия проверяет сохранность прежних настроек до успешной замены и удаление временного файла.
- После правки прошли адресные 13 тестов, полный pytest 443 passed / 1 skipped в новом системном временном каталоге, 162 Vitest, TypeScript/Vite, Ruff и git diff --check. Назначение отправки — существующая ветка codex/card-review.
