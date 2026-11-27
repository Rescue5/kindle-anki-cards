# Product

What Kindle Cards is for, who it is for, and what the team builds next. Agents
read this before planning work; the owner changes it when the direction
changes. `AGENTS.md` says how to work, `DESIGN.md` how it looks, this file why.

## Goal

A product that people other than its author actually use: a handful of readers
who installed it, came back after their next book, and would miss it if it
disappeared. Not a demo, not a portfolio piece.

## Who it is for

A Russian-speaking adult who reads English books on an e-reader (Kindle,
PocketBook, Kobo, Boox with KOReader) and looks words up while reading. They
already own a flashcard habit or want one (Anki, Quizlet, Obsidian), but do not
want to build cards by hand, and they are not data people. They open the app
when they plug the reader in — about once a week.

## The promise

"See every word you looked up, in the order it could be useful to learn.
Choose what to study and take the sentence from your book into your flashcard app."

## What the product does, and does not

Does:

1. **Collects** looked-up words from the reader (USB or a picked file — the
   file path is shown on the first screen, not hidden in a tooltip).
2. **Ranks every word** for reading the next contemporary English novel. A single
   lookup uses the share of novels containing the lemma, giving each author the
   same total weight. Returning to a word on another day in the same book or
   looking it up in another book can raise its priority by up to one level.
   The library and card explain the observed share and any personal adjustment.
   The card also shows the reader's recorded lookup and book counts.
   Measured words receive levels 1–9. Words awaiting processing, unmatched
   spellings and unmeasured expressions have a provisional 6. Repeated searches
   for the same unmeasured expression affect its order within that group. Level 10 flags
   possible recording errors. Readers can search and choose words at any level.
   Installations without the local model use the previous ranking. The choice,
   evidence and offline setup are in the [original integration note](docs/plan/openresearch-integration.md)
   and the [corpus and personalization results](docs/plan/personalized-book-priority.md).
3. **Lets readers choose what to take.** Home starts with the whole library
   and all ten priority levels selected, including previously exported and
   skipped words. Readers can exclude individual levels, choose every new
   word recommended for study, or enter a portion size. Home previews up to
   five words and displays the full number to be exported.
4. **Asks** only about the few words it is unsure of (at most 5–7 per sync,
   each with a default answer, all skippable).
5. **Lets the reader fix a card**: translation, which sentence from their book
   goes on it.
6. **Exports with one button** to the remembered destination. Anki receives
   a deck through AnkiConnect or an `.apkg` file. Obsidian receives one
   Markdown note per word in the reader's vault with priority decks for
   Spaced Repetition. Quizlet and RemNote receive local files for their text
   importers. A detailed TSV retains the full set of export columns.
   Re-exporting uses the same Anki note GUID. Anki's import settings
   govern field updates. A newer translation or example can replace edits
   made in Anki. Excluding a word from a later export leaves it in Anki.
7. **Says what did not stick**: words looked up again after their export are
   listed on Главная with an action (export again / fix the card). This is the
   only progress the app shows, and no comparable tool has it.

Reviewed by `product-skeptic` on 2026-11-19: separate Progress and Book
screens, manual book status, lookups per 10 pages, per-month cohorts, five
equal shelves, Quizlet as its own branch, and asking "where/what" on every
export were cut or deferred as things only the author would use.

Does not:

- Teach, drill or schedule reviews. No built-in spaced repetition.
- Show statistics for their own sake: no KPI tiles, streaks, habit calendars,
  trend dashboards.
- Send vocabulary anywhere. Everything is local; optional LLM enrichment uses
  the reader's own key.

## The loop

Plug in the reader or use «Найти Kindle» → see the ranked words → fix a
translation or example if needed → choose the library, levels or new words
to export → return after reading the next book.

The reason to come back is "since last time": new words waiting and the book
moving forward — never a streak.

## Concept screens

`docs/concept/*.dc.html` are the mockups in the Кабинет language; read the
markup inside `<x-dc>` and the demo data in `renderVals()`. They are the
reference for look and copy, but the scope above wins where they differ:

- **Главная** — choose the export scope, see a five-word preview, check the
  reader connection or open the complete library.
- **Слова** opens the complete library with measured words in priority order,
  followed by provisional assessments and possible recording errors,
  with search, book and priority filters. Each card explains the recommendation
  and lets the reader choose to study a word, edit its translation and pick an example.
- **Спорные** — one by one, at most 5–7, from the counter link.
- **Экспорт** — one button; the destination is remembered (chosen once, changed
  in Настройки); done/empty/error states.
- **Прогресс** and **Книга** concept screens are not built.

Navigation: Главная, Слова, Настройки. The existing Review and Insights screens
go away. The fox carrying a lantern is the permanent mascot on the Home desk,
including when the selection is ready. The fox occasionally speaks in a
handwritten bubble. Readers can turn its lines off. Empty states are said in words; a lamp may go out, but it never
explains the state on its own. The Кабинет look stays; milestones do not spend
time on new decoration. The implementation plan is `docs/plan/m1-m2.md`.

## Milestones

Each milestone ends in something a reader can feel, with checks that pass.

### M1 — A ranking worth trusting

- Ranking v2 replaces the importance score: personal signals (repeat lookups,
  several books, recency, the book being read) outweigh corpus frequency;
  every word gets a visible study priority and a reason. Internal shelves
  continue to serve the short list and export.
- The reader's decisions (Знаю / Учить / Не учить / Не слово) are stored and
  always win.
- Done when: on `ranking_eval` the new ranking beats the current score at the
  top (lift at top-50 at least 2× the base rate, vs 1.0× today), it also holds
  on at least one library that is not the author's (a KOReader/Kobo test
  library or a newcomer with 1–2 books), the bridge returns shelf, rank and
  reasons for every lexeme, and tests cover it.

### M3a — Stop losing newcomers (cheap, done before M2)

- README rewritten for a reader: one promise, a card screenshot, three steps,
  SmartScreen explained next to the download with why the app is safe; no
  promises of review or analytics; technical lists moved to `docs/`.
- The no-cable path (file locations per reader, what KOReader is) on the first
  screen; a «Посмотреть на примере» demo; copy without «лемма», «offline»,
  «Полезность N/10».
- Done when: the user-advocate walkthrough finds no stop it can fix with text.

### M2 — Two screens that do the job

- Главная and Слова (with the card inspector, Спорные from a counter link and
  one-button export), as scoped above; Review and Insights removed (UI, bridge
  actions; review data kept in a legacy table for one release).
- Done when: `product-skeptic` and both reviewers pass each screen,
  loading/empty/error states exist, `npm test`, `npm run build` and the Python
  suite pass, screenshots updated.

### M3b — The first five minutes, end to end

- A new reader gets from installer to cards in Anki without reading docs;
  release published with notes in the new terms.
- Done when: a first-user walkthrough of the built app finds no dead end.

### M4 — Come back, tell others

- "Since last time" and «снова искали после экспорта» work on real repeated
  syncs; a feedback path from the app; one honest post where the audience is
  (only with the owner's go-ahead).
- Done when: at least ten people outside the team have installed it and a few
  have reported back.
- Later, only if readers ask: macOS build; zero-click export on sync.

## How we know it works

- Ranking quality: `ranking_eval` numbers, before and after every change.
- Product quality: reviewers' findings closed; walkthroughs without dead ends.
- Real use (no telemetry, by design): release download counts, GitHub issues
  and discussions, direct feedback.

## Open questions for the owner

- Progress in lookups (fewer lookups per 10 pages from book to book) was the
  owner's own wish; the skeptic deferred it because book length is unknown
  for Kindle and differences between books are larger than the signal. Keep
  deferred, or build with a manual "pages in book" field?
- Signing the Windows installer (for example SignPath's free programme for
  open-source projects — unverified) would remove the SmartScreen warning,
  the biggest loss of newcomers. Apply?
- Reading percentage on Kindle needs the `.sdr` sidecar files; unverified on a
  device.
- A fiction-specific frequency list (for example Google Books Ngram, English
  Fiction) would need a one-time dataset download and bundling; licence and
  size to be confirmed before use.
- Where the audience is reached first (Habr, Telegram reading/English
  channels, r/kindle) is undecided.
