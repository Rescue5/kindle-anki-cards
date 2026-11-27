# Team meetings

After every stage the team meets (see "Team" in `AGENTS.md`): each role gives
a short written view, the lead decides disputed items and records the outcome
here. Newest last; earlier meetings are not rewritten. Where a meeting changes
`docs/plan/m1-m2.md`, the plan file is updated too.

## 2026-11-19 — after M1 (ranking v2 built)

Present: product-skeptic, ranking-engineer, backend-engineer,
frontend-engineer, user-advocate, qa-engineer.

### What we learned

- Ranking v2 beats the old score at the top (lift@50 2.8x on two comparable
  cutoffs, 2.08x over four), but only on the author's library. **M1 is not
  closed** until it holds on a library that is not the author's; a newcomer
  with 1–2 books has almost no repeat lookups, and their first sync is when
  they decide whether to keep the app.
- On the author's library the shelves are worth 272, disputed 71,
  not_worth 1615, junk 3. 272 is a pile, not a short list; 71 disputed words
  on view would read as a debt; 85% in «Не стоит учить» hurts trust unless
  every such word says why in one line.
- The backend stage is long and invisible to readers; the risk is weeks
  without anything a reader can feel.

### Decisions

1. **Ranking lane runs in parallel with backend** (its own files only):
   - a synthetic newcomer library generator with a fixed seed and no private
     data (invented words plus common English words, 1–2 books, 300–800
     lookups over about three months, KOReader and Kobo files, a planted
     "needed again" process); the M1 criterion is checked on it;
   - on/off ablation of the after-export and `proper_noun` weights with
     bootstrap intervals; a feature whose effect sits in the noise is dropped
     or kept minimal;
   - a recall check of `too_basic` → not_worth (how many come back);
   - every not_worth word carries at least one negative reason.
2. **Thin path first.** What a reader feels is "20 words → one button →
   Anki". Backend order becomes: B1+B2 (migration with bulk catalog, one v3
   fixture and a golden `load_catalog` payload) → freshness fix → B3a user
   tables and writes → B3b re-link → B4 decorate + perf gate → B6a
   `is_exportable` + `card_fields.resolve` → B6b export run recorder → B6c
   destination writers → B5 `set_decision` / `save_card_edit` + shared
   payload fixture → B7 removals (last, together with F7).
3. **Migration is simpler and safer:** backup before any write transaction,
   checked with `PRAGMA integrity_check`; never delete lexemes; **do not
   touch `review_cards` in v4** (no `legacy_review_cards` copy, no drop); it is
   removed in a later release once nothing reads it.
4. **Disputed:** counted only inside the new batch and capped at 7; the rest
   follow their `lean` silently. The Слова badge and `disputedLeft` use this
   count.
5. **Слова** opens on «Стоит учить» in rank order with the next-export batch
   marked; long lists are paged or virtualised (frontend gate: 3,000 words
   scroll without jank).
6. **Frontend starts on the mock** once the lead fixes the contract (C0:
   `src/types.ts`, `contracts.py`, one shared payload fixture). Order:
   F0 types/mock/pencil controls → F2 shell (and delete Books, Insights and
   Review screens with their CSS and the `load_review` call early) → F6
   Главная + F5 Экспорт → F3 Слова → F4 Спорные → F7. `use-library-controller`
   is split into small hooks, not extended. Keys 1/2/3 in Спорные work only
   when focus is not in a text field. A blocked export says where to choose
   the destination.
7. **Cut / deferred:** `PendantLamp` (Спорные uses an existing lamp); new
   mock scenarios are only `no-new` and `export-error` (existing ones stay);
   Obsidian export keeps working but gets no new work.
8. **No interim 0.3.1 release.** Wiring ranking into the old screens is work
   on screens that are about to be deleted. The next release is the thin path
   (Главная + Экспорт + Слова on the real backend), with release notes that
   say Review and Insights are gone and why.
9. **CI:** every new backend module is added to the ruff list when it is
   created; the perf gate runs at 150 ms locally and with a 3x margin in CI so
   `windows-latest` does not flake; QA walks the bridge on a copy of a
   real-size library after B1, B3b, B4 and B6.

### Contract answers for the backend lane

- `now` for ranking is the latest lookup time in the library (confirmed).
- Lookup time is the reader's lookup timestamp, never the import time.
- `reading_books`: books with a lookup in the 14 days before `now`.
- `proper_noun` comes only from existing analysis warnings at rank time; no
  WordNet call per lexeme and no backfill. If the ablation shows no gain, the
  feature goes.
- `exported_at` is the latest `export_items` row for the lexeme, including
  `migrated` runs (they are real past exports).
- `set_decision` stores `shelf_at`, `score_at` and `ranking_version` at the
  moment of the decision (training data for a later learner).
- Settings: `export_destination` defaults to `anki`; `export_batch_size`
  defaults to 20, validated to 5–100 in `settings.py`.

### Directions after M2 (backlog, each goes to product-skeptic first)

- Signed installer (both skeptic and advocate rank SmartScreen as the biggest
  loss of newcomers) — owner decision.
- Cold-start quality of the first sync.
- Learning from the reader's decisions (regularised, with a personal prior).
- A per-book summary «в этой книге вы искали N слов, вот 20 главных».

### Owner questions

- Apply for free open-source installer signing (e.g. SignPath)?
  Recommendation: yes.

## 2026-11-19 — after "B1+B2 and ranking for newcomers" (e2cb41d)

Present: product-skeptic, ranking-engineer, backend-engineer,
frontend-engineer, user-advocate, qa-engineer.

### What we learned

- Schema v4, bulk catalog and the freshness fix are done and verified on a
  copy of a real library. Readers see nothing yet.
- Ranking v2 beats the old score from about 8 weeks of history and is no
  better than a plain lookup count at 6 weeks.
- KOReader keeps one row per word (`reader_sources.py` reads `vocabulary` by
  word); Kobo's WordList has no counter either. PocketBook/Kobo/Boox readers
  have no repeat-lookup signal, so for them v2 is recency sorting and
  «Не стоит учить» is mostly noise. Whether KOReader updates `create_time`
  when a word is looked up again is unknown; if it does not, «снова искали
  после экспорта» is blind for these readers too.

### Decisions

1. **Honest promise for the first weeks.** The short list stays and matters
   more than the ranking: "words from your book worth learning — not too
   simple, with your sentence". No claim of a personal ranking until there is
   history. One line, never a banner or a screen, says the order is still
   rough. Reasons never cite a signal the source does not have.
2. **Ranking mode** (ranking lane, small): `ranking.py` gets a library-wide
   mode `learning | full` from history length and whether the source keeps
   repeat lookups. In `learning` the short list leans on the frequency band,
   the book being read and recency, and is measured as "not worse than
   frequency or lookup count" on the synthetic library with `repeats=False`
   and on a replay with repeats collapsed. No fine-tuning of the cold start
   beyond that.
3. **Check KOReader re-lookups** (ranking lane): read KOReader's vocabulary
   builder source to learn whether a repeated lookup updates the row. If not,
   «снова искали после экспорта» stays silent for KOReader/Kobo instead of
   implying "everything stuck".
4. **Disputed** capped at **5** (was 7). «Не стоит учить» is never shown as a
   verdict; everything outside «Стоит учить» lives behind «Остальные».
5. **Lean payload.** List payload carries what the list shows (shelf, rank,
   short reasons as code + text, decision, export state, card fields);
   analysis details are fetched on click. The UI virtualises the list
   (3,000-row gate); no bridge paging.
6. **Next stage, in parallel:**
   - C0 contract first (drafted by backend, decided by the lead):
     `src/types.ts`, `kindle_vocab_app/contracts.py`, one shared payload
     fixture read by both a Python test and the mock; adds `rankingMode`,
     `historyDays`, `repeatSignal`, error codes with Russian text, settings
     keys.
   - Backend B3a + B3b as one stage (user tables keyed for re-link by
     `(language, canonical_key)`; merged keys keep both users' data; a v3
     library with non-empty `review_cards` migrates intact); B4 is the stage
     after.
   - Frontend F0 + F2 on the mock (types, mock split, pencil controls, shell,
     early deletion of Books/Insights/Review).
   - Ranking: decisions 2 and 3.
7. **README now:** only what is true for the released 0.3.0 (KOReader note
   next to the readers list; "usually finds the words"). The text about the
   new order waits for the release that ships it.
8. `proper_noun` is not wired into the bridge; `after_export` stays at 1.0
   until real exports exist to measure it.

### Owner questions

- Reword the M1 criterion: "holds on a non-author library" cannot be measured
  for KOReader/Kobo readers. Recommendation: "on Kindle-style histories v2
  beats the old score from about 8 weeks; for every reader the short list is
  not worse than frequency".
- A fiction frequency list now matters more (the first weeks rest on
  frequency). Recommendation: approve checking licence and size, then decide.
- Installer signing (from the previous meeting). Recommendation: yes.

## 2026-11-19 — after "C0 contract, B3, F0+F2, ranking mode" (2f9baec)

Present: product-skeptic, backend-engineer, frontend-engineer,
ux-clarity-reviewer (on Главная and Экспорт before they are built). Ranking,
user-advocate and QA had nothing open for the next stage.

### Decisions

1. **The next stage delivers the thin path**: a short list of words with one
   reason each → «Экспортировать N» → Anki, working through the real bridge.
   Everything else waits.
2. **Backend:** B4 (ranking, `newBatch`, `disputed`, `rankingMode` really in
   `load_library`; `now` = latest lookup; one perf measurement on 3,000
   words, no harness) → B6 core: `export_policy.is_exportable` (decision
   `learn`, or no decision and shelf `worth`; processed words only),
   `card_fields.resolve`, the run recorder, and `export_words {scope:"new"}`
   to `anki` (AnkiConnect when it answers, otherwise an `.apkg` — today's
   behaviour, so no owner question) and `csv`. A run is recorded only after
   the push or the file succeeded; on failure nothing is stamped; Anki dedup
   by the stable GUID, so a retry never duplicates.
3. **Cut / deferred:** `export_preview` (the library's `newBatch` is enough);
   `scope:"again"`, `lookups_after` and the «повтор» tag (M4: there are no
   exports to come back from yet); Obsidian inside `export_words` (old
   `sync_obsidian` keeps working until B7); the separate Экспорт screen —
   running/done/error/empty states live on Главная; Спорные (F4) — disputed
   words simply stay out of the short list; the lean list payload (B7).
4. **Error codes reach the UI:** the smallest Rust change — on `ok:false`
   `python_bridge` returns the error object as JSON text; `backend.ts`
   parses it into `BridgeError {code, message}`; the mock throws the same.
5. **Главная (F6, on the mock, then on the bridge):** one question «что
   выгрузить сейчас?», one primary action «Экспортировать N» (the same N as
   `newBatch.count`). Short list with one reason per word; «Показать все»
   is not needed — the list is the batch. One grey line in learning mode:
   «Пока порядок примерный: он уточнится, когда накопится больше слов»; when
   `repeatSignal` is false: «Порядок примерный: читалка не сохраняет
   повторные поиски, поэтому слова идут в основном по частоте». No-reader
   path: file locations stay visible (PRODUCT.md M3a wins over hiding them)
   plus «Посмотреть на примере». A skeleton until the first load, so the
   newcomer onboarding never flashes for an existing reader.
6. **Copy:** one name — «слова», never «лексемы»/«карточки» in the UI; states:
   «Отправляю…», «Готово: N слов в Anki» (or «…в файле» with «Открыть
   папку»), «Новых слов для выгрузки нет. Подключите читалку после чтения»,
   «Не получилось: <причина>. Попробовать снова».
7. **Next stage after this:** B5 (`set_decision`, `save_card_edit`) + F3
   Слова with the inspector, then F4 Спорные and B7/F7 clean-up.

## 2026-11-19 — after "thin path" (4675378)

Present: product-skeptic, user-advocate, frontend-engineer, backend-engineer.

### Decisions

1. **Release 0.4.0 next — after a release minimum, not after Слова.** The
   short list and the one-button export are the product's promise; a card
   can still be fixed in Anki. Release minimum:
   - remove the old export buttons from Слова (they bypass the export
     history, so exported words come back) and the status-strip line
     «Обработано: N; принято…» (statistics);
   - a walkthrough of the real Tauri app with the real bridge: sync, list,
     export to a real Anki, `.apkg` with Anki closed, CSV, re-export without
     duplicates. No release without it — a broken first export loses the
     reader for good. It needs the owner's machine, reader and Anki;
   - first-five-minutes copy on Главная: what to do when the reader is not
     found (cable, MTP, charging mode, pick the file), KOReader named for
     PocketBook/Kobo, what an `.apkg` is before the export, the rough-order
     line saying why;
   - README steps 2–3 and «Что приложение уже делает со списком» rewritten
     (user-advocate's text), release notes that say Review and Insights are
     gone and Слова is still the old screen.
2. **After the release:** B5 `set_decision` + `save_card_edit` (translation
   and sentence only) + F3 Слова simplified («Стоит учить», «Остальные»,
   inspector — nothing else); then «снова искали после экспорта» (M4, the
   reason to come back; KOReader's overwritten `create_time` kept as a new
   lookup). F4 Спорные deferred until readers say the list misses words. The
   lean payload only if a measurement says the app is slow; B7/F7 removals
   merge into the release minimum where they block it.
3. Obsidian stays a destination in Настройки only.

### Owner questions

- Who does the real-app walkthrough: the owner (about 10 minutes with their
  reader and Anki), or the lead running the dev build on this machine? Either
  way the first start migrates the real library to v4 after a verified
  backup.
- Go-ahead for 0.4.0 once the walkthrough passes.
- Installer signing (recommend applying now).

## 2026-11-20 — Планёрка по первому экспорту в Anki и кандидату 0.4.0

**Решение ведущего.** Ближайший этап заканчивается установленной Windows-сборкой, в которой читатель получает первую карточку из своей книги и может закончить импорт после перерыва. Сначала восстанавливаем доступ к сохранённой колоде, затем проверяем весь путь из установщика. Упрощение экрана «Слова» остаётся следующим продуктовым этапом.

Участвовали ведущий и шесть субагентов на `gpt-6.2-sol`. Продуктовый скептик и QA работали с глубиной `high`, представитель читателя, backend-инженер, специалист по ранжированию и рецензент UX — с `medium`. Скептик, представитель читателя и QA сначала прислали независимые позиции, затем получили возражения друг друга. Backend отдельно разобрал семантику ошибок, специалист по рейтингу оспорил допущения о первой порции, а рецензент UX проверил принятый план. Реализация интерфейса и проверка его визуального языка закреплены за следующим этапом.

### С чего начали

В рабочей копии на базе `4675378` уже работают короткий список на Главной, выбор Anki или TSV и запись успешной выгрузки в SQLite. В предыдущем этапе прошли 303 теста Python (один пропущен), 100 тестов интерфейса и сборка Windows. В нативном прогоне через WebView2, Rust и Python из шести вымышленных слов пять ушли в TSV, одно осталось. Это свидетельство о конкретной dev-сборке и маршруте TSV. Установщик запускает отдельный упакованный Python-мост. Для текущего кода оставались открыты установка, USB на настоящей читалке и импорт в настоящем Anki. [Журнал предыдущего этапа](../../WORKLOG.md) · [Выбор моста в Tauri](../../src-tauri/src/main.rs) · [Локальная сборка NSIS](../../scripts/build-installer.ps1)

### Первый раунд. Во что вложить следующий этап

Во время встречи QA прогнал 53 целевых Python-теста. При повторной загрузке одного синтетического файла KOReader через отдельные процессы JSON-моста число новых слов изменилось с одного до нуля, в библиотеке остались одно слово и один контекст. Отдельный пакет из трёх слов сохранился на диске после перезапуска моста, новая порция была пуста, в ответе загрузки пути к колоде не было. Эти наблюдения дают исходные данные для испытания интерфейса.

| Предложение | Довод в пользу | Возражение и решение |
| --- | --- | --- |
| Довести путь от установки до первой колоды | Продуктовый скептик указал, что все остальные функции зависят от того, получит ли человек свои слова в Anki. QA предложил проверить реальный файл на стороне получателя. | Ожидание читалки могло бы остановить работу. Сборку, ручной импорт файла формата Kindle и импорт в отдельной базе Anki можно проверить независимо от USB. Принято. |
| Сначала разрешить исправлять перевод и выбирать предложение | Представитель читателя отметил, что неподходящее значение может обесценить даже удачный экспорт. | Готовую карточку уже можно исправить в Anki. Минимальный редактор B5/F3 возвращается на обсуждение раньше, если наблюдаемый читатель откажется выгрузить подходящий список именно из-за конкретной карточки. |
| Сначала показать слова, которые искали снова | Это даёт повод вернуться после следующей книги. | Для проверки нужны выгрузка и последующее чтение со значимыми новыми наблюдениями. Этап следует за редактором. Отсутствие повторов само по себе ничего не говорит об усвоении слова. |

### Второй раунд. Что изменили возражения

**1. Закрытие программы между сохранением и импортом колоды.** Представитель читателя и ведущий проследили обычный путь по коду. При закрытом Anki приложение создаёт `.apkg`, записывает успешную выгрузку и исключает слова из следующих порций. Кнопки «Открыть в Anki» и «Открыть папку» зависят от результата в памяти React. Перезапуск очищает его, как и новая операция загрузки с Kindle. Файл остаётся на диске. На Главной читатель может увидеть пустой список, даже если до первой карточки в Anki ещё один шаг. Это вывод по исходникам, проверка в установленной сборке входит в приёмку. [Состояние выгрузки](../../src/features/home/use-home-export.ts) · [Сброс при загрузке](../../src/main.tsx) · [Действия на Главной](../../src/features/home/home-view.tsx) · [Запись результата](../../kindle_vocab_app/export_cards.py)

QA допустил подсказку с путём в README. Представитель читателя возразил, что после прерывания человек ищет колоду там, где только что нажал «Экспортировать». **Решение** — вторичное действие «Открыть папку выгрузок» на Главной, доступное после перезапуска и при следующей порции. Основная кнопка остаётся доступной для новых слов. Сохраняем понятное имя файла. Существующий `open_path` принимает только файл в каталоге выгрузок. Backend и frontend согласуют открытие именно каталога приложения либо выделение конкретного файла в нём. Если файл был удалён, интерфейс сообщает об этом или открывает существующий каталог. Наличие пути в SQLite само по себе не устанавливает, импортировал ли читатель колоду вручную. Отдельная история выгрузок для этого сценария не нужна. [Открытие файла](../../kindle_vocab_app/tauri_bridge.py)

**2. Какие повторы действительно проверены.** QA воспроизвёл на трёх синтетических словах два одновременных запроса `export_words` с одинаковыми идентификаторами. Получились два разных TSV по три слова и шесть строк `export_items`. Резервирование имени защищает файлы от перезаписи. Выбор слов и запись истории разделены созданием файла. Обработчик React защищает от двойного нажатия в одном окне. Скептик предложил отличить достижимость гонки из установленной программы от воспроизведения на уровне backend. **Решение** — при испытании кандидата открыть его обычным способом дважды с общей тестовой библиотекой. Если два штатных запроса могут отправить одну порцию, устранить повтор до публикации и проверить на одинаковых и частично пересекающихся списках. Учитываем побочные эффекты в файлах и в истории. [Выбор слов и вывод](../../kindle_vocab_app/export_cards.py) · [Запись истории](../../kindle_vocab_app/library_state.py) · [Текущие проверки](../../tests/test_export_words.py)

**3. Что значит поменять TSV на Anki.** QA подтвердил, что `scope:new` учитывает предыдущие выгрузки во все назначения. В уже выгруженном TSV слова остаются, а следующая новая порция уйдёт в Anki. Это сохраняет согласованное значение «новых слов». У выбора назначения объяснить, что настройка действует на следующие выгрузки. Возвращать весь словарь в очередь при переключении назначения команда не предлагает. [История по словам](../../kindle_vocab_app/library_state.py) · [Настройки](../../src/components/settings-view.tsx)

**4. Где может остановиться новый читатель.** В README ссылка на опубликованный 0.3.0 предшествует инструкции для новой Главной, а оговорка о версии появляется только после шагов. На Главной строка «Читалка не подключена» утверждает больше, чем знает программа, если провод уже вставлен. Уточнить версию рядом со скачиванием, использовать «Читалка не найдена», оставить выбор файла на виду и объяснить ручной импорт `.apkg`. Для родного словаря Kobo предупредить об отсутствии предложения, для перевода из встроенного словаря учесть пропуски. Независимый первый читатель может проверить понятность без подсказок команды. Его участие желательно для обратной связи и не задерживает внутреннюю сборку. [README](../../README.md) · [Первый экран](../../src/features/home/home-view.tsx)

**5. Anki перестал отвечать после начала передачи.** Backend предложил считать любой такой исход готовым файлом и сразу списывать слова. Ведущий возразил, что это лишит человека повторной попытки после явного отказа Anki. Backend принял возражение. Сохраняем три исхода. Если AnkiConnect изначально недоступен, готовый файл считается успешной выгрузкой. Подтверждение Anki означает успешную отправку. Если после начала отправки получен отказ или потерян ответ, слова остаются для повтора, доступ к созданной колоде сохраняется. Для неопределённого исхода подходит «Anki не подтвердил импорт. Колода сохранена в папке выгрузок». При ошибке создания самого файла такой подсказки быть не должно. [Отправка колоды](../../kindle_vocab_app/export_cards.py) · [Проверка явного отказа и повтора](../../tests/test_export_words.py)

### Работы и порядок приёмки

**Холодный старт.** Специалист по ранжированию поставил под сомнение качество первых 20 слов у новичка. В историческом замере на данных одного читателя за 56 дней при искусственно скрытых повторах относительная доля повторно искавшихся слов в первых 20 составила 0,73 от базовой доли, при сортировке по частоте — 1,03. Интервал парной разницы от −1,16 до +0,78 допускает оба порядка. Рейтинг сохраняем. На коротком файле с одной книгой проверяем, что порция правильно работает и с числом подходящих слов меньше настройки. Если после завершения очереди подходящие слова теряются, сначала прослеживаем импорт и обновление списка. Когда подтверждено, что их вытесняет мусор уже на этапе ранжирования, возвращаемся к отбору и сравнению со свежестью. Отдельную оценку качества на библиотеке другого читателя оставляем открытой. [Исторические замеры](../../WORKLOG.md) · [Формирование порции](../../kindle_vocab_app/library_view.py)

**Пока готовится первая порция.** По коду главная область может советовать подключить читалку после следующего чтения в тот момент, когда общая строка ещё показывает обработку. Включаем в ближайшую правку состояния «загружено, обработка продолжается» и «обработка закончена, подходящих слов нет». Проверяем медленную первую обработку и появление списка без дополнительного нажатия. [Выбор состояния](../../src/features/home/home-screen.tsx) · [Текст пустого списка](../../src/features/home/home-view.tsx)

Рецензент UX уточнил проверку возвращения к файлу. Постоянная ссылка должна находиться в одной зоне Главной при пустом списке и при новой порции, открываться с клавиатуры и помогать опознать колоду среди нескольких файлов. В момент успешного сохранения показываем один переход к папке и явный следующий шаг «Открыть в Anki». При потере подтверждения предлагаем проверить, появились ли слова в Anki, прежде чем повторять отправку.

| Шаг и ответственный | Что делаем | Как принимаем результат |
| --- | --- | --- |
| 1. Ведущий, backend и UX | Зафиксировать контракт доступа к каталогу текущей библиотеки и текст для каждого результата Anki. | Можно различить подтверждённый импорт, сохранённый файл и ошибку. Предложенное действие открывает только каталог выгрузок приложения или файл внутри него. При ошибке создания программа сохраняет возможность повторить выгрузку. |
| 2. Backend и frontend, затем рецензенты UX и визуального языка | Реализовать восстановление доступа на Главной и согласованные тексты. Представитель читателя параллельно готовит шаги README и заметки о переходе с 0.3.0. | После сохранения `.apkg` закрываем программу до импорта. При следующем запуске находим прежний файл с Главной, в том числе после загрузки следующей порции. Пустой список, новая порция и удалённый файл дают понятный результат. С первой порции остаётся одно основное действие. |
| 3. Ведущий и QA | Из проверенного дерева собрать локальный Windows NSIS с упакованным мостом. Зафиксировать версию и контрольную сумму проверяемого файла. Установить в чистое окружение, сохранив личные библиотеки отдельно. | Приложение без Conda и подстановки dev-Python читает тестовый файл формата Kindle. После обработки показывает ожидаемые слова этой фикстуры. Для обновления проверить на тестовой v3-базе резервную копию, сохранность библиотеки и истории. Сверить шаги README со сборкой, на которую они ссылаются. |
| 4. QA и представитель читателя | Пройти получение и повтор карточки в отдельной базе настоящего Anki, затем файл TSV. Для испытания Anki можно задать временный каталог через `-b`. [Руководство Anki](https://docs.ankiweb.net/manual/files#startup-options) | На наборе с известными словом, переводом и предложением сверить обе стороны карточки. Отдельными прогонами проверить AnkiConnect, ручной импорт при закрытом Anki и TSV. Повтор **того же исходного файла** не добавляет слов. После перезапуска уже отправленные слова исчезают из новой порции. Повтор **того же .apkg в Anki** сохраняет число и идентификаторы заметок. В TSV набор строк соответствует показанным словам. |
| 5. QA и backend | Проверить одновременную выгрузку через два обычных запуска одного кандидата в общем тестовом профиле. При воспроизведении защитить участок от выбора слов до записи истории на уровне библиотеки. | Для одинаковой тройки остаётся один результат и три записи о словах. Для наборов `[a,b]` и `[b,c]` после первой выгрузки повторная отправляет только `c`. Защита освобождается после аварии до записи файла. Потеря ответа после создания файла проверяется отдельно. Фоновая обработка библиотеки остаётся работоспособной при ожидании Anki. |
| 6. QA и ведущий, затем владелец | На доступном физическом Kindle проверить подключение, чтение и повторное подключение под Windows. Записать модель, способ подключения (диск либо MTP/WPD) и результат. Составить итог о готовности к 0.4.0. | Повторное подключение после той же сессии чтения не дублирует слова. Реальный аппарат подтверждает именно проверенный маршрут. Для публикации нужны результаты установленной сборки, настоящего Anki, устройства и отдельное решение владельца. |

Без читалки работа продолжается до конца проверок установщика, файлов и Anki. Если доступно только тестовое окружение без Anki, QA может сверить структуру `.apkg` и GUID и оставить живой импорт открытым. Для оценки понятности представитель читателя отдельно наблюдает первый проход незнакомого с проектом человека без подсказок. Командный прогон подтверждает технический результат, наблюдение за читателем отвечает на вопрос, нашёл ли он нужное действие сам.

### После кандидата

Минимальные правки перевода и предложения, действия по слову и упрощённый экран «Слова» (B5/F3) остаются после 0.4.0. Затем проверяем пользу «снова искали после экспорта» на последующих загрузках. «Спорные», изменение весов рейтинга, новый датасет, уменьшение объёма ответа без замера и отдельный экран истории не входят в ближайший этап. Решение о подписи установщика остаётся у владельца отдельно от локальной сборки. Следующая командная встреча состоится по итогам прогона кандидата или раньше, если реальный пользователь упрётся в препятствие, меняющее порядок работ.

## 2026-11-20 — Приёмка установленного кандидата и выбор следующего этапа

Проверяли NSIS для Windows x64 версии 0.4.0, SHA-256 `c2f38d8b20484e30588b906c4f99311e2a1e399f107467da9a2f91be86d41826`. Владелец разрешил обновить рабочую установку 0.1.0. Прежние программные файлы сохранены. Команда использовала отдельные библиотеки для физических и синтетических данных.

### На чём основано решение

| Вопрос | Наблюдение |
| --- | --- |
| Как ведёт себя установленная версия? | После обновления ярлык в меню «Пуск» ведёт к 0.4.0. Основной EXE и упакованный мост совпали с файлами внутри NSIS. Приложение с отдельной библиотекой работает без dev-Python. На синтетической v3-базе сохранились слова и история, резервная копия прошла проверку целостности. |
| Можно ли закончить выгрузку после перерыва? | Из восьми синтетических записей Kindle получили восемь слов в колоде. После перезапуска из пустого списка клавиатурой открыли в Проводнике тот же каталог. Импорт именно этого файла в настоящем Anki добавил восемь заметок, повтор — ноль. Идентификаторы и контексты совпали. |
| Можно ли доверять сообщению «в Anki»? | При нажатии кнопки в установленном приложении AnkiConnect передал пять вымышленных слов в отдельный профиль Anki 25.09.4. Сверены поля и обе стороны карточек, число записей в SQLite, исчезновение слов из очереди после перезапуска и идентификаторы после повторного импорта. |
| Что происходит с одной порцией в двух окнах? | При двух одновременных нажатиях созданы один TSV, одна запись выгрузки и пять уникальных отметок. Второе окно получило сообщение о занятой выгрузке. |
| Что обнаружилось только в release-сборке? | Главное окно не могло подписаться на события прогресса Rust. Добавлены разрешения на подписку и отписку для локального главного окна. На исправленной сборке прогон WebView2 прошёл без этой ошибки. |
| Работает ли чтение физического Kindle после снятия и возврата USB-кабеля? | Windows обнаружила обе смены состояния, установленный мост снова прочитал базу через MTP/WPD. На устройстве оказалось на одну запись больше. Поэтому дополнительно сверили идентификаторы при добавлении последней записи к локальной копии. Все 2 551 прежних идентификатора сохранились, добавился один, повтор текущей базы дал ноль новых. Личные слова в Anki не отправлялись. |

### Независимые позиции и возражения

Продуктовый скептик сначала выбрал локальный кандидат до испытания USB. Альтернативой считал ограниченный тест по файлу с одним согласившимся читателем. После того как установленный мост дважды прочитал настоящий Kindle по MTP/WPD, скептик снял возражение против рекомендации к выпуску. Его условие — сохранность слов при физическом переподключении и подтверждение результата в самом Anki.

Представитель читателя поставил во главу критерия первую пригодную карточку и возможность найти колоду после перерыва. На рецензии команда поставила предупреждение о потерянном ответе Anki перед повторной отправкой, уточнила необходимость подтвердить импорт и сохранила клавиатурный фокус у действия с папкой. Итоговая проверка интерфейса прошла в 13 сценариях на ширинах 1440 и 600 пикселей. В ответ на предложение отложить выпуск до внешнего наблюдения оба участника согласились, что такое наблюдение измеряет понятность для новичка и может проводиться отдельно. Независимый читатель в этой приёмке не участвовал.

### Очерёдность

Ведущий и участники рекомендуют проверенный экземпляр 0.4.0 к выпуску. Оба условия последнего раунда выполнены на финальной сборке. Разрешение владельца распространялось на обновление его Windows-установки. Решение о публичном выпуске остаётся за ним. Проверка одного Kindle подтверждает его маршрут по MTP/WPD в данном окружении. Проверки других моделей по USB и независимая оценка первой порции остаются отдельными вопросами.

Следующий результат после 0.4.0 — читатель открывает ещё не выгруженное слово, исправляет перевод и выбирает сохранённое предложение из книги. Обе правки должны пережить перезапуск и попасть в следующую колоду. После этого упрощается список на экране «Слова». Приёмку экспорта переоткрываем при потере контекста, дублях, недоступности сохранённого файла или расхождении между сообщением об успехе и содержимым реальной колоды.

## 2026-11-20 — После 0.4.0: зачем читатель установит Kindle Cards и вернётся к ней

**Решение тимлида.** Ближайший результат — проверить на пяти внешних читателях, помогает ли короткая подборка превратить слова из своей книги в карточки, которые человек действительно повторяет. Берём опубликованную 0.4.0. Первой аудиторией выбрали русскоязычных читателей английских книг на Kindle, которые ищут слова встроенным словарём и уже повторяют карточки в Anki на Windows. У них можно наблюдать, заменяет ли приложение ручной отбор и перенос слов. Для остальных устройств и людей, впервые открывающих Anki, понадобится отдельная проверка.

**Что показать читателю.** «Kindle Cards выбирает короткую подборку из слов, которые вы искали в книге, и собирает карточки Anki с предложениями, которые сохранила читалка». Для первого знакомства достаточно одного изображения с вымышленным примером — слово на странице книги и обе стороны готовой карточки. Повод открыть приложение снова возникает после следующей главы с новыми поисками. Проверяем, захочется ли человеку повторить выгрузку по собственной инициативе.

### На чём основан выбор

- Команда уже проверила установленную 0.4.0 с настоящими Kindle и Anki. Приёмка показала, что карточки доходят и повторный импорт сохраняет их идентификаторы. Данных о самостоятельном использовании внешними читателями у команды пока нет. В момент планёрки GitHub показывал два скачивания установщика 0.4.0. Во время релизной проверки команда сама скачивала файл. Из этого счётчика нельзя узнать число читателей или повторных визитов. [Релиз](https://github.com/Rescue5/kindle-anki-cards/releases/tag/v0.4.0) · [Счётчики файлов](https://api.github.com/repos/Rescue5/kindle-anki-cards/releases/tags/v0.4.0)
- Kindle2Anki уже позволяет выбрать книги и слова и получить колоду Anki. В публичном запросе к Readest читатель отдельно попросил сохранить контекст и определение слова, убрать ненужное и выгрузить результат. Наше предположение — отбор небольшой порции сэкономит читателю время. Ни описание конкурента, ни этот запрос спроса на конкретный Windows-продукт пока не измеряют. [Инструкция Kindle2Anki](https://www.kindle2anki.app/how-to-use) · [Запрос читателя Readest](https://github.com/readest/readest/issues/789)

### Что изменилось в обсуждении

| Участник | Исходная позиция | Итог после возражений |
| --- | --- | --- |
| Продакт-менеджер | Начать с трёх удачных выгрузок и одного возврата. | Импорт может быть технически успешен даже с бесполезной колодой. Согласовали пять сессий и проверку, повторял ли человек карточки в обычном Anki. Стоит также наблюдать, достаточно ли ему убрать одно лишнее слово. |
| UX-исследователь | Позвать пять–восемь человек с подходящей техникой и узнать через неделю, захотят ли они вернуться. | Сначала даём человеку действовать самостоятельно. При повторном контакте спрашиваем о том, что он уже сделал. Учитываем и тех, у кого за неделю не появилось новых поисков. |
| Инженер ранжирования | Сравнить выдачу с заранее названными желанными словами. На короткой истории преимущество текущего порядка для новичка пока не установлено. | Предварительный список мог бы подсказать участнику задачу. Разбираем причины отказа после естественного прохода. Если жалуются на состав, сравниваем локально две порции одинакового размера без подписей — текущую и по свежести. Записываем только числа. |
| UX-дизайнер | Проследить путь от ссылки до повторного использования. | Изображение при наборе показывает результат. Участник начинает проход со страницы релиза без учебного видео. Слабый отклик на приглашение проверяем отдельно от затруднений тех, кто дошёл до установки. |

### Как провести первую пятёрку

1. **Набор.** Продакт-менеджер отвечает за приглашение, UX-исследователь — за отбор участников. Первых читателей ищем среди участников книжного клуба, читающего по-английски, и в русскоязычном сообществе Anki. Выясняем, на какой читалке и ОС они работают, как часто ищут слова и когда последний раз повторяли карточки. Считаем приглашённых, откликнувшихся и подходящих отдельно. Внешние обращения и площадку согласует владелец. Черновик приглашения — «Читаете английские книги на Kindle и пользуетесь Anki на Windows? Приглашаем попробовать Kindle Cards на своей книге и показать, какие карточки вам захочется оставить».
2. **Первый сеанс, около 20 минут.** UX-исследователь спрашивает, как читатель обычно поступает с незнакомым словом. Затем даёт ссылку на 0.4.0 и предлагает попробовать со своей книгой. Записывает, дошёл ли участник без подсказки до своей карточки в Anki, время, первую остановку и потребовавшуюся помощь. После попытки выясняет, какие из первых пяти карточек человек оставил бы для повторения и почему остальные не подходят. Разделяем причины — само слово, значение, предложение, техническая ошибка. С согласия участника пишем обезличенные итоги. Файл словаря и текст книги остаются у читателя.
3. **Через 7–10 дней.** Один нейтральный вопрос — «Что с того дня происходило со словами, которые вы искали во время чтения?» Затем уточняем факты: было ли новое чтение с поисками, повторял ли человек хотя бы одну карточку первой порции и выгружал ли следующую до нашего сообщения. Возвраты показываем двумя числами — среди всей пятёрки и среди людей, у которых появились новые поиски. Если возможности вернуться почти ни у кого не было, ждём следующего чтения.
4. **Разбор.** Тимлид и продакт-менеджер собирают следующий разбор после повторного контакта. Ориентир для продолжения — хотя бы трое из пяти повторили свои карточки в обычном Anki и хотя бы двое самостоятельно сделали следующую выгрузку после новых поисков. Эти ориентиры помогают выбрать следующий этап. Для оценки распространённости спроса нужна более широкая выборка. Неоднозначные наблюдения проверяем ещё на трёх читателях.

### Как наблюдения изменят разработку

| Что увидим | Следующее решение и ответственный |
| --- | --- |
| Мало откликов от подходящих читателей | Продакт меняет один элемент приглашения или пробует второй канал и сравнивает отклик. |
| Два читателя независимо останавливаются на одном шаге установки, подключения или импорта | QA воспроизводит конкретный шаг. UX-дизайнер и инженер, отвечающий за него, исправляют препятствие и проверяют путь со следующим новым читателем. |
| Слова подходят, но два читателя отказываются от нужных карточек или регулярно исправляют их в Anki из-за значения или предложения | Тимлид ставит минимальный редактор первым в разработку. Бэкенд и фронтенд обеспечивают исправление перевода, выбор предложения из книги и сохранность обеих правок после перезапуска и в колоде. Если проблема только в лишнем слове, сначала проверяем возможность просто пропустить его. |
| Часто отвергают сами слова; простая подборка по свежести возвращает нужные слова у нескольких читателей | Инженер ранжирования проверяет порядок на новых библиотеках. Если четверо из пяти отвергают большую часть подборки, предпочитают ручной отбор и не используют карточки, тимлид пересматривает само предложение автоматического отбора. |
| После новой главы читатели возвращаются и хотят разобраться со словами, которые искали снова | Проверяем небольшой список повторно встреченных слов с действием над карточкой. Повторный поиск сам по себе ничего не доказывает об усвоении слова. |
| Люди повторяли карточки, снова читали и искали слова, но к приложению не вернулись | UX-исследователь выясняет, как они в этот раз поступили со словами и сколько времени занял привычный способ. Тимлид решает, что может сделать следующую выгрузку полезнее, и проверяет идею до разработки. |

Редактор остаётся первой инженерной гипотезой из предыдущего протокола. Перед выделением времени на него команда проверит, какое препятствие возникнет у читателей в действующей версии. План и черновик приглашения готовы; набор и сессии ещё не проводились.

## 2026-11-20 — Внутренний этап по решению владельца

Владелец считает приглашение читателей преждевременным. Он выбрал два приоритета — отбор слов и качество карточек, удобство и внешний вид приложения. План пяти внешних сессий отложен. Следующая демонстрация предназначена владельцу.

Продакт предложил проверять результат на всей порции: убрать ненужное слово, исправить смысл другого и увидеть тот же выбор в выгруженной колоде. UX-дизайнер показал два препятствия. Строка на Главной не открывала карточку, а на узком экране инспектор находился под длинным списком. Бэкенд-разработчик установил, что SQLite уже хранит ручные правки, но рабочий мост не предоставлял интерфейсу соответствующие команды. Инженер ранжирования воспроизвёл утверждение о редком значении слова, сделанное лишь на основании его общей частоты.

Тимлид утвердил один сквозной сценарий. С Главной читатель открывает конкретное слово, видит перевод и предложение, меняет нужные поля и возвращается к той же строке. Выбор «Не учить» действует на следующие порции и снимается в библиотеке. Если есть следующий подходящий кандидат, он занимает место исключённого. При исчерпанной библиотеке порция становится короче. Продакт после обсуждения согласовал этот случай отдельно. Формулировка причины частоты должна соответствовать измеряемому сигналу. Для изменений порядка нужны воспроизводимые примеры ошибки.

Бэкенд отвечает за сохранение в SQLite и реальные поля экспорта. Инженер интеграции отвечает за контроллер, фронтенд-разработчик — за «Слова» и редактор, тимлид — за переход из порции и обратный фокус, инженер ранжирования — за проверку отбора. На приёмке проверяем клавиатуру и внешний вид на ширинах 1440 и 600, отмену несохранённого ввода, повторное чтение исходной базы, отсутствие исключённого слова и наличие исправленных полей в колоде. Сборка для внутреннего просмотра использует отдельные данные.

### Итог внутренней приёмки

Внутренняя сборка Windows доступна владельцу в `build/internal-card-review/kindle-cards.exe`. На вымышленной библиотеке в настоящем окне сохранили русский перевод и выбранную цитату, закрыли и заново запустили приложение, исключили другое слово и выгрузили пятёрку. В TSV оказались сохранённые поля и новый состав. Отдельно движок Anki импортировал исправленные карточки во временную коллекцию. Проверили широкий и узкий экран и возврат с клавиатуры.

Для следующего внутреннего разбора берём одну порцию из знакомой владельцу книги. Самое важное наблюдение — какие слова из первых пяти он действительно решил бы учить, какое пропущенное слово он предпочёл бы взять взамен и помогает ли предложение вспомнить смысл. На этом этапе технически подтверждены сохранение выбора и экспорт. Соответствие порядка личным предпочтениям остаётся открытым вопросом.

## 2026-11-23 — Главная во время обработки слов

Владелец показал широкое окно внутренней сборки после импорта. Из 1820 слов обработаны 649. Ход работы виден только на нижней полосе, заголовок предлагает экспорт раньше времени, плафон настольной лампы пересекает край окна.

В первом раунде продакт предложил назвать текущую задачу в заголовке и сохранить готовую порцию при повторном импорте. UX-дизайнер предложил собрать счётчик и ход обработки в освещённой зоне, а на узком экране отдать эту ширину тексту. Во втором раунде обсудили возражения. Предварительные карточки меняют состав по мере работы очереди и создают видимость готового результата. Повтор счётчика в нижней полосе перетягивает внимание и озвучивает каждый шаг. При наличии предыдущей подборки её исчезновение создало бы новую проблему.

Решение тимлида — при первом импорте показать подготовку по центру рабочего пространства. Числа берём из событий текущего задания. До первого события с объёмом показываем ожидание, после обработки последнего слова дожидаемся чтения подборки из библиотеки. При повторном импорте сохраняем существующий список и показываем ход работы рядом с ним. Экспорт доступен после актуализации списка.

Фронтенд-разработчик отвечает за Главную и свет, тимлид за связь с очередью и нижнюю строку, UI-дизайнер за визуальное ревью. QA проверяет остановку и повтор с клавиатуры. Для приёмки нужны широкое и узкое окно, обе темы, настоящий Python-мост с вымышленной библиотекой и отдельная внутренняя сборка Windows.

Приёмка завершена. В реальном приложении на Windows очередь из 15 вымышленных слов прошла до доступного экспорта. Счётчик обновлялся под главным заголовком. После замечаний рецензента уменьшенную лампу вернули и в окно 600 px, в повторной проверке плафон и основание помещаются целиком. Локальный коммит `4a96284`. Новая переносная сборка находится в `build/internal-card-review-2026-11-23` и открывает библиотеку прежней внутренней версии.

## 2026-11-23 — Настольная лампа как маскот

Владелец предложил дать лампе на Главной живой характер, редкие движения и короткие реплики. Цель этой встречи — выбрать образ и поведение для внутренней пробы. Подготовили [сравнительный эскиз двух ламп](../concept/lamp-mascot-study.png). Это лист для выбора характера. При переносе в приложение ориентиром для толщины линий, пропорций механизма и ночного света служит нынешняя Главная.

### Что обсудили

| Участник | Первоначальная позиция | Что решили после возражений |
| --- | --- | --- |
| Продакт-менеджер | Сравнить любопытную лампу, которая замечает слова, и сонного хранителя, который просыпается после обработки. | Любопытство работает и в покое, и при готовой подборке. Приветствие само по себе может доставлять удовольствие. Реплика о карточке уместна, когда читатель действительно может её открыть. Польза для возвращаемости остаётся гипотезой. |
| UX-дизайнер | Читатель сам знакомится с маскотом через плафон, отвечает только по желанию. | На наведение и клавиатурный фокус лампа коротко отзывается. Щелчок, касание, Enter или пробел открывают реплику. На компактном экране тексту нужно своё место. Если в этом состоянии окна сама лампа скрыта, её кнопка тоже исчезает из порядка Tab. |
| UI-дизайнер | Сравнить ушки, совиный силуэт и один глаз-заклёпку. | Для сравнения оставили ушки и глаз-заклёпку. Предпочтение — двум чуть разным загнутым металлическим ушкам. Их видно по силуэту в дневной теме. Небольшой поворот одного ушка передаёт внимание при неподвижном плафоне. |
| Фронтенд-разработчик | Жест можно собрать из текущего SVG и CSS. Смена общей позы сложнее из-за отдельных координат луча. | В первом прототипе двигаются только детали на плафоне. Источник света физически остаётся на месте. Для облачка выделяется отдельная кнопка у плафона, которая не перехватывает рабочую область. |

### Предложение для внутреннего прототипа

1. **Характер.** Чуть застенчивая лампа, которая читает через плечо. Два небольших жестяных ушка и одна карандашная черта на боку плафона. Сохранить низкое основание, пружины, графит и тёплый свет. Эскиз справа с глазом-заклёпкой остаётся альтернативой, если на настоящем размере он покажется выразительнее.
2. **Покой и взгляд.** В пробной сцене после примерно 25 секунд спокойного ожидания развернуть одно ушко к словам и вернуть его на место. Для первой пробы — один такой жест за ожидание. Наведение или фокус на самой лампе вызывают короткий взгляд в сторону читателя. При появлении готовой подборки оба ушка один раз обращаются к списку. Событием служит переход к списку с доступными карточками, обновление чисел на полосе прогресса его не вызывает.
3. **Приветствие.** Нажатие на плафон вызывает прищур и одно рукописное облачко. При подготовке пример реплики — «Я посвечу, пока собираются слова». При доступных карточках — «Откройте слово — можно выбрать любимую фразу из книги». Тексты локальные, короткие. Во время ошибки место и внимание остаются у причины и восстановления. Повторное нажатие закрывает облачко. Также работают Escape и видимое закрытие. Текст остаётся доступным, пока читатель его не закроет или не покинет сцену.
4. **Движение и свет.** Текст и экспорт сохраняют свои места. При `prefers-reduced-motion` доступно статичное приветствие. Внутренний просмотр сравнивает тихий и неподвижный варианты. Скрытое окно приостанавливает жесты. Засыпание, курсор по всему окну, звук и самостоятельные реплики отложили. Поворот всего плафона можно взять отдельным шагом, если для оглядывания нужна подвижная голова. Перед этим потребуется единая точка поворота для плафона, блика и начала светового конуса.

### Порядок проверки и инструменты

После выбора внешности UI-дизайнер перенесёт силуэт в масштаб настоящей Главной. Фронтенд-разработчик сделает изолированную сцену на существующем SVG и CSS. В ней сравним покой, приветствие и готовую подборку. `framer-motion` уже есть в проекте и пригодится, если понадобится прерываемое движение шарниров. Бэкенду достаточно существующих состояний Главной. Облачко использует текст, соответствующий состоянию, и доступную кнопку у плафона. Навигация и переключатель освещения сохраняют собственные роли.

Из локальных навыков выбрали `imagegen` для листа внешности, `react-best-practices` для отделения состояния маскота от частых обновлений очереди и `frontend-testing-debugging` с Playwright для проверки сцен. Для работы над характером движения проверили две внешние инструкции автора: [animate](https://github.com/emilkowalski/skills/blob/main/skills/animate/SKILL.md) для выбора длительности, кривой и прерывания и [review-animations](https://github.com/emilkowalski/skills/blob/main/skills/review-animations/SKILL.md) для отдельного ревью. На встрече изучили их описания, установки не проводили.

UX-дизайнер и QA проверяют, находит ли владелец приветствие без подсказки, может ли закрыть реплику и сразу открыть слово, видны ли счётчик и экспорт при ширинах 600 и 1440 px, узнаваема ли лампа при дневном свете. Повторяем взаимодействие несколько раз и проводим минуту в ожидании с неподвижным и живым вариантами. Если повтор жеста перетягивает взгляд при чтении, оставляем его по запросу. Через клавиатуру и при уменьшенном движении всё содержание доступно. Решение о внешности и переходе от прототипа к приложению остаётся за владельцем. Код приложения и сборка на этом этапе не менялись.

### Решение владельца и итог пробы

Владелец выбрал левый эскиз с двумя ушками. Фронтенд-разработчик перенёс силуэт и прищур на плафон настоящей Главной. Тимлид собрал сценарий подготовки и готовой подборки на демонстрационной библиотеке. Для знакомства достаточно нажатия на плафон. При подготовке лампа шевелит ухом после 25 секунд ожидания, при переходе к карточкам один раз отзывается на готовность. Ручной переключатель и системное уменьшение движения дают статичный вариант.

UI-дизайнер попросил убрать штриховку вокруг глаза и открыть стойку в компактном окне. После правок он подтвердил читаемость по снимкам 600 и 1440 px. На 360 и 390 px реплика помещается рядом с плафоном и сохраняет повторный щелчок по нему. QA прошёл сценарии с клавиатурой, сменой темы, выбором предложения и экспортом. Релиз-инженер собрал один локальный HTML со шрифтами и рисунком. Владелец может попробовать его в `build/lamp-study/index.html`. Перенос персонажа в основную сборку — следующее решение владельца после знакомства. Исходники пробы сохранены в локальном коммите `0a23b6d`.

## 2026-11-23 — Новый выбор внешности лампы

Владелец посмотрел автономную пробу и отклонил внешний вид настольной лампы. Он предложил заново выбрать персонажа по изображениям Главной и разрешил существенно отойти от первоначального эскиза. Прежнее предпочтение левого варианта больше не определяет внешний вид.

Для сравнения UX-дизайнер предложил использовать неподвижную сцену с одинаковыми темой, текстом и ходом подготовки. Тимлид взял за основу снимок ночной Главной и запросил в ImageGen четыре силуэта — зимородка из гнутого металла, керамический гриб, механического светлячка и маленького смотрителя в бумажном абажуре. Критерии выбора — читаемый в окне силуэт, понятный источник света, доступное место для текста и узнаваемый характер в покое. Итоговый образ выбирает владелец до следующей реализации.

## 2026-11-23 — Первый рабочий лис-фонарщик

Владелец одобрил чёрную фигуру с фонарём на пятом эскизе. На планёрке продакт предложил примерить её к реальному ожиданию и проверить, не принимают ли жест за признак готовности. UX-дизайнер потребовал сохранить место под счётчик в узком окне и клавиатурный путь к выгрузке. Обсудили вариант оставить лиса рядом с готовым списком. После взаимных возражений приняли персонажа только в состоянии подготовки. Признаком готовности служит сама подборка. При исчезновении лиса фокус переходит к заголовку только из приветствия или с фонаря.

Тимлид отвечает за силуэт и свет по одобренному изображению, интеграцию в обычную Главную и портативную сцену с вымышленными словами. Фронтенд-разработчик ведёт адаптивное размещение, открытие и закрытие приветствия и тихое моргание. Приёмка включает ночную и дневную темы, узкое окно, подготовку первой подборки, её смену списком и экспорт. Рецензент сверяет снимки с исходным образом, QA проверяет сценарии с клавиатурой, релиз-инженер собирает отдельную внутреннюю версию для Windows.

Приёмка рабочего лиса завершена. На Windows временная очередь из 15 слов прошла через фактическую обработку до готовой подборки. В том же окне Enter на фонаре открыл приветствие. В браузере проверены узкие и широкие окна, обе темы и доступ к экспорту. По визуальному ревью убрали отдельный блик слева и пламя при дневном свете, поставили ступни на линию стола и переместили реплику вправо от лица. Выбор владельца и его реализация сохранены в локальном коммите 94563cc.

## 2026-11-23 — Движение лиса в ожидании слов

Владелец попросил оживить уже выбранного лиса. Продакт предложил отделить жесты продолжительными паузами, чтобы читатель успевал следить за количеством обработанных слов. UX-дизайнер попросил проверить, попадёт ли читатель по стеклу качающегося фонаря на узком экране. Обсудив оба возражения, команда согласовала общую шкалу времени. Лис переводит взгляд и поворачивает голову, прислушивается обоими ушами по очереди, затем качаются фонарь и хвост. Открытая реплика ставит движения на паузу. Системное уменьшение движения даёт статичную сцену.

Тимлид разделяет рисунок на подвижные части, связывает свечение с дужкой и проецирует отблеск на поверхность стола. Фронтенд-разработчик отвечает за ритм жестов. UI-дизайнер оценивает силуэт, свет и читаемость счётчика на кадрах в крайних положениях. QA проверяет реальные преобразования в браузере, обе темы, клавиатуру и попадание по движущемуся стеклу. Релиз-инженер собирает отдельную внутреннюю версию, специалист по приёмке повторяет ожидание на вымышленной очереди Windows.

Нативная приёмка подтвердила все жесты в WebView2. Проверенная точка на стекле осталась внутри кнопки приветствия при максимальном наклоне. После возобновления анимации очередь завершилась, подборку стало можно выгружать. За 82 секунды браузерной проверки жесты сохраняли порядок и паузы в двух последовательных циклах. Реализация сохранена в локальном коммите `5cc84e2`.

## 2026-11-23 — Лис как постоянный маскот приложения

Владелец уточнил, что лис заменяет лампу во всём приложении. Это пересматривает прежнее решение показывать его только при подготовке слов. На планёрке продакт отметил риск отвлечения от перевода и выгрузки. UX-дизайнер предложил на рабочих экранах оставить неподвижный силуэт и исключить его из порядка Tab. После встречных возражений решили ставить его в самом содержимом: боковая навигация скрывается в узком окне. Знак у названия повторяет профиль лиса, текущий раздел по-прежнему виден по выделению.

На Главной лис остаётся живым во всех состояниях. На экране слов лис у списка, а при открытии карточки стоит рядом со словом. В Настройках он у заголовка. Фронтенд-разработчик отвечает за Главную и доступность приветствия. Тимлид отвечает за общую навигацию, карточку, список, настройки, документы и автономный пример. Приёмка проверяет готовый список сразу после старта, переход от подготовки к экспорту, правку слова и клавиатурный возврат. Проверяются обе темы, широкое окно и ширина 600, затем EXE по прежней ссылке.

### Уточнение владельца в ходе приёмки

Владелец уточнил место маскота: заменить только большую настольную лампу на Главной. Это отменяет принятое выше распространение фигуры на заголовки и навигацию. На Главной лис сохраняется при любом состоянии, в том числе рядом с готовым списком и после выгрузки. Вне Главной возвращены исходные рисунки, знак приложения и оформление. Промежуточный вариант aa4f033 не выдавался владельцу. Итоговую поставку сверяем с 5cc84e2 по файлам навигации, карточки, списка слов и настроек, а затем проверяем обычную готовую Главную в Windows.

В сборке 6db84bb проверены готовая Главная, сохранение приветствия при смене состояния и прежние светильники остальных экранов. Версия передана по тому же пути, который владелец открывал из чата. Проверка реального окна Windows подтвердила одновременное наличие готового списка и доступного приветствия лиса.

## 2026-11-23 — Полная библиотека по приоритету изучения

Читатель хочет сам проверить, почему слово оказалось в конце списка, и при желании учить его. Сейчас SQLite сохраняет канонические записи, но список по умолчанию показывает полку рекомендаций. Позиции внутри разных полок совпадают. Продакт предложил общий список с одной причиной и доступом к нижней границе. UX-дизайнер предложил сохранить поиск, фильтр книги и возврат в выбранную строку; направление шкалы после уточнения соответствует пожеланию владельца, от 1 к 10.

Инженер ранжирования предложил переиспользовать непрерывную оценку и отдельно ограничить уровень 10. После возражений продакта и бэкенда решили считать приоритет независимо от решений читателя, включая истёкшую отметку «Знаю». Имена, редкость и отсутствие слова в локальном словаре сами по себе не дают уровень 10. Для записи без достаточных данных бэкенд предлагал оценку по доступным наблюдениям. Для этой итерации берём середину шкалы, 6, с явной пометкой «предварительно» и причиной; это не утверждение о полезности. Новые данные уточняют приоритет автоматически.

Тимлид утвердил отдельное поле study_priority у каждой канонической записи. Уровни 1–9 используют фиксированные интервалы оценки. Уровень 10 требует проверяемого структурного признака возможной ошибки записи. Порядок внутри уровня задают полнота оценки, исходный балл по убыванию и устойчивый идентификатор. Короткая порция на Главной и правила допуска к экспорту сохраняются. Оценка для уже сохранённых слов появляется при чтении без миграции и без повторного запуска оптимизатора. При полном списке поиск по книге и уровню должен находить ранее отложенные слова; из их карточек можно явно выбрать «Учить» и отменить решение.

Инженер ранжирования отвечает за расчёт, краевые случаи и замеры на срезах. Бэкенд отвечает за все входы моста, очереди, контракт и фикстуры. Фронтенд отвечает за список, карточку, фильтры и клавиатуру. Тимлид ведёт типы, демонстрационный режим, продуктовый контракт и интеграцию. Визуальная и функциональная приёмка включают узкое окно, приоритеты 1 и 10, временную оценку и сохранность ручного решения. Релиз-инженер пересобирает Windows-приложение вместе с Python-мостом; финальная приёмка проходит с отдельной тестовой библиотекой.

## 2026-11-24 — Состав выгрузки и читательский стол

Читатель хочет забрать весь словарь с книги, при необходимости снять несколько приоритетов, увидеть основание оценки каждого слова и сразу проверить кабель. Число 20 оказалось настройкой учебной порции. Команда рассмотрела полную библиотеку как отдельный файл и как обычную отправку в Anki. Продакт обратил внимание на повторную отправку ранее выгруженных и отложенных записей, UX-дизайнер предложил разделить состав выгрузки и объём примера. Владелец выбрал полную библиотеку в обычном назначении, включая повторные карточки. Тимлид принял этот вариант. Объём будущей выгрузки показываем на кнопке, на столе оставляем пять слов. Все десять уровней изначально включены. Для другой задачи остаются все новые учебные слова и порция произвольного размера. Значения в настройках задают стартовый размер порции.

Лис иногда произносит короткую фразу. Облачко проявляется и гаснет, текст печатается. Огонь и падающий свет движутся согласованно. Речь можно выключить, скрытие окна останавливает время ожидания, при уменьшении движения фраза появляется целиком. Бра и лампа в карточке сохраняют свои роли. «Найти Kindle» запускает штатную проверку подключения и показывает результат. В каталоге рядом со словом видна реальная причина оценки, в карточке — полное пояснение и числа сохранённых записей и известных книг. Раскрытое меню приоритетов должно читаться в обеих темах.

Бэкенд проверяет точные идентификаторы и выбранные уровни, сохраняет идентичность карточек. Инженер Anki проверяет повторный импорт с новым словом, изменённым переводом, исключённым уровнем и существующей историей повторений. Фронтенд отвечает за речь и свет, инженер ранжирования — за причины и выбор уровня, тимлид — за Главную, выбор выгрузки, поиск читалки и стыковку. Приёмка требует полного экспорта более ста записей с пятью на Главной, повторного экспорта с исключением уровня, управления клавиатурой и просмотра при 600 и 1440 px. Релиз-инженер собирает внутренний EXE с новым мостом. Нативный QA проверяет приложение на отдельной библиотеке. Внешняя публикация не входит в этап.

## 2026-11-24 — Учебная ценность слова после единственного поиска

Тимлид собрал продакт-менеджера, инженера ранжирования, бэкенд-разработчика и QA-инженера. Они сначала разобрали задачу независимо, затем получили возражения друг друга. Читатель хочет получить полезную первую подборку уже после одной книги. Вопрос для оценки звучит так: «Какое из этих уже встреченных слов стоит взять в Anki, чтобы легче читать дальше?» Частота следующего обращения к словарю отвечает на отдельный вопрос.

### Что показала действующая версия

На 9f77358 тимлид импортировал искусственный Kindle vocab.db через import_reader_file, запустил process_queue и прочёл load_library. Одна книга, восемь записей, для каждой один поиск с одной и той же датой. Режим learning. У enough приоритет 4 (Zipf 5,54), although — 3 (5,30), borrow — 1 (4,00), sword — 1 (4,37), halberd — 7 (2,05), set — 4 (5,59), the — 8 (7,73), 00:17 — 10. Личные данные не использовали. Действующая модель вычитает баллы за высокую частоту выше порога 5 и почти не различает слова середины частотной шкалы с одинаковой историей. Причиной для enough в каталоге оказался недавний поиск. В отдельном контроле с одинаковыми входами rank и только обнулённым коэффициентом common слова enough, although, borrow, sword и the все получили 1. Это воспроизведение механизма, а не измерение качества будущей модели.

### Позиции и возражения

Продакт предложил оценивать, насколько слово пригодится при дальнейшем чтении, сохраняя личный интерес к редкому слову. Инженер ранжирования возразил против немедленного добавления учебного списка: корпусная частота и попадание в список могут дважды поощрять одно и то же свойство. Он требует сравнения с простым снятием штрафа и отдельного контроля, не заняли ли артикли верх списка. Продакт согласился выбрать простейший вариант, если он даёт сопоставимый результат. Общий запрет на служебные слова отвергли, поскольку он захватил бы полезные связки вроде although. Для отдельно записанного артикля проверим сохранение действующего ограничения. Слово в устойчивом выражении требует отдельного разбора.

Бэкенд обнаружил конкретную потерю на примере take off. Оптимизатор может определить фразу, однако ключ WordNet с пробелом пропускает доступную запись с подчёркиванием, а рейтинг использует максимум частот формы и леммы, включая частоту отдельного take. wordfreq вычисляет оценку многословной строки из частот компонентов. Она не подтверждает ни частоту выражения, ни частоту его значения. Распознать единицу и убедиться в наличии словарной статьи можно уже локально; для заявления «это частое выражение» нужны наблюдения выражения целиком. Сохранённый анализ старых записей бывает неполным. Записи без даты и незавершённый анализ включаем в отдельные сценарии.

QA возразил против обучения на одном будущем повторе как эталоне учебной пользы. Предложил отдельно оценивать видимый порядок и первые пять слов у читателей, сохранять ranking_eval как проверку на ухудшение для накопленной истории. В ответ инженеру предложил пары с одинаковыми датами, союз although, слово that в двух употреблениях и контроль, где только у одного слова появился новый независимый поиск.

### Решение тимлида

Первый этап — локальный сравнительный эксперимент на данных, уже входящих в поставку. Для каждого ранее встреченного слова исходную оценку даёт общеупотребительность с верхним пределом прибавки. Один поиск даёт основание рассматривать слово для изучения. Положительное личное свидетельство может поднять его выше, например новый поиск в другой день или книге. Повторные нажатия подряд проверяем как один эпизод. Долю личного вклада ограничиваем на уровне слова с учётом возможностей читалки. Длинная история других слов сама по себе не даёт оснований понизить слово, увиденное один раз. В книге с отсутствующей историей повторов сохраняется общий ориентир.

Сравниваем текущий алгоритм, сортировку только по частоте с насыщением, снятие верхнего штрафа и гибрид с ограниченной частотной прибавкой и личными свидетельствами. На одинаковом наборе сверяем и сортировку каталога, и доступную подборку новых учебных слов. Для карточки выбираем причину из реально использованного сигнала: «Часто встречается в английских текстах» либо «Вы искали это слово в двух книгах». Уровни 1–10 и ручные решения сохраняют прежний смысл. Отсутствие частоты или повторов фиксируется как неизвестность. Уровень 10 остаётся для проверяемого дефекта записи. Полная выгрузка по-прежнему включает все выбранные читателем уровни.

Два кандидата на следующий этап. Первый — широта употребления в книгах: в какой доле разных книг и у скольких авторов встречается слово, с контролем длины книги, повторных изданий и перекоса в сторону старой прозы. Это отличает слово, которое встречается во множестве книг понемногу, от слова, многократно повторённого в одном цикле. Второй — подтверждённое вхождение в учебное ядро NGSL как отдельный вариант для сравнения. Отсутствие в списке не служит штрафом. Сначала оцениваем, что источник добавляет сверх имеющихся частот, затем отдельно согласуем загрузку, условия распространения и размер офлайн-таблицы. Источники для исследования: [wordfreq](https://github.com/rspeer/wordfreq), [NGSL](https://www.newgeneralservicelist.com/word-lists), [книжный корпус SPGC и счётчики по произведениям](https://zenodo.org/records/2422561).

### Кто проверяет и как принимаем результат

- Инженер ранжирования фиксирует варианты и веса до закрытой проверки, сравнивает их на одинаковых входах. Бэкенд проверяет лемму и форму, выражение и его отдельные компоненты, неполный анализ старых записей и отсутствие дат. Диагностика на отдельных примерах не меняет оценку у пользователей.
- Продакт и QA готовят недорогой первый опыт — 40–60 пар с предложениями, случайная сторона показа, предпочтение или ничья, до раскрытия алгоритма. Обязательные случаи — одна книга без повторов, содержательное частое слово, артикль, связка, многозначное слово, фразовый глагол, редкий термин с повтором в другой книге, имя и запись без букв. Этот опыт отсеивает неудачные варианты.
- На закрытой проверке сравниваем первые 5 рекомендаций при библиотеке из 5, 20 и 50 разных слов. При пяти словах сравниваем порядок пар, поскольку состав пятёрки одинаков. QA предложил 12 отложенных книг разных авторов и слепые оценки читателей; для каждой книги одинаковый вес. Предлагаемый порог для замены — не меньше 60% предпочтений против текущей версии с учётом ничьих как половины голоса и нижняя граница 95% интервала выше 50%. Дополнительно простейший конкурент не должен давать тот же выигрыш; при сопоставимом результате берём его. Широкий интервал означает, что данных пока недостаточно.
- Отдельно сравниваем на временных срезах ranking_eval способность поднимать повторно нужные редкие слова при длинной истории. Разделяем по книге, автору и, при наличии, читателю; все признаки извлекаем только из доступного на дату среза префикса. Оценку учебной пользы, качество прогноза повтора и соблюдение правил показываем раздельно. При противоречии возвращаемся к конкретным парам и обсуждаем выбор с владельцем.

Результат этого этапа — диагностика и согласованный план эксперимента. Изменение модели, новая сборка и включение внешних наборов требуют следующего этапа.

Уточнение бэкенда после второго раунда. На синтетическом запросе take off был обработан, получил уровень 7 и остался за пределами подборки новых слов. Исключение частоты отдельного take в диагностической пробе изменило уровень на 4. Все 30 фраз из имеющегося списка нашлись в установленном WordNet при записи с подчёркиванием. Если в исходной библиотеке сохранился только ключ take, выбранное прежде выражение или значение нельзя уверенно восстановить по этому ключу. Влияние на реальные библиотеки предстоит измерить.

## 2026-11-24. Как оценить слово до появления личной истории

Владелец поставил цель ранжировать по ожидаемой пользе для чтения и уточнил, что B1 был примером источника. Обсуждали качество порядка всех слов после единственного обращения к словарю. Частота обращений, новые/старые записи, дата поиска и действия пользователя исключены из базового расчёта. Учебный уровень проверяется наравне с другими признаками.

Первый раунд. Инженеры ML и ранжирования проверяли крупные учебные списки, открытые корпуса и оценки людей. Продакт предложил измерять первые двадцать карточек в исходных цитатах. QA выступил за отдельную метрику первых пяти, контроль по авторам и сравнение с одним сильным признаком. Исследователь корпусов сверил книги и обнаружил общих авторов между исходными коллекциями. Методолог возразил против суммирования числа книг по словоформам и против оценки человеческой полезности на той же таблице, которую модель читает при применении.

Второй раунд. Инженер ранжирования хотел бы видеть хотя бы одно дополнительное полезное слово в пятёрке. Методолог указал, что при большом числе одинаковых пятёрок такие абсолютные требования могут быть недостижимы. Решение ведущего — измерять фактическую долю изменившихся выдач при слепой оценке, а до неё разделить три исхода: встреча в другой книге, оценка носителей и приоритет по преподавателям L2. Возражение продакта про артикли остаётся в протоколе. Лингвист нашёл человеческие метки Wang и независимое, но усечённое приложение Dang. Данные с ограниченными правами относятся к локальному исследованию.

Реализация и критерии. Инженер ранжирования отвечает за офлайн-расчёт, причины, структурную 10, неуверенные формы и отдельные фразы. Корпусный специалист отвечает за версии, списки авторов и счётчики. Ведущий отвечает за разбиение, обучение, сравнение, исполнимый набор и отчёт. Исследователи работают на 6.2 Sol, сложная независимая методологическая рецензия проведена на 6.2 Astra. Сначала выбираем простой и сложный книжные варианты на проверочных авторах, затем сравниваем на других авторах. Планка усложнения +0,03 nDCG@5 с положительной нижней границей авторского интервала. Для человеческой полезности скрываем оценки целых семейств форм. Окончательное применение определяется отдельным слепым сравнением на русскоязычных читателях и современной прозе.

Итог. Проверены компьютерно четыре книжные и четыре педагогические модели, запасные оценки, точные выражения и ограниченная человеческая поправка. Книжный охват даёт 0,6662 против 0,6111 общей частоты. Комбинация даёт 0,6735. Книжная основа остаётся простой. Исследовательский учебный вариант допускает небольшой сдвиг для слов, которые люди считают полезнее или менее полезными, чем ожидается по их частотности. При сравнении с 145 оценками преподавателей разница неопределённа. Отложили замену продуктового ранжирования и персональный слой до проверки с читателями. Полный протокол, источники, цифры и запуск приведены в [исследовании](reading-priority-research.md).

## 2026-11-24. Интеграция результата Open Research RP-V2

Читателю, открывшему слово впервые, нужен осмысленный порядок перед следующим современным романом. Инженер ранжирования сверил книжный результат и рекомендовал использовать сохранённый столбец coverage. Охват с нормировкой по авторам и обычная доля книг дали почти одинаковую первую пятёрку на 393 отложенных романах. Решение использовать равный вес авторов поддержали продакт и тимлид. Сюжетные поправки не дали подтверждённого улучшения при переносе на новые полные рассказы. Персональный прогноз повторного поиска измеряем отдельно.

Продакт предложил использовать общую частоту при отсутствии книжного охвата. Тимлид оставил предварительную оценку для пропусков: в единой выдаче цифра должна обозначать один и тот же наблюдаемый исход. Для сравнения целых выражений и слов остаётся исследовательский режим по 422 пересказам. Уровни от 1 до 9 служат для группировки, сортировка использует точную долю. Критерии приёмки — совпадение с исходным офлайн-кодом, сохранение причин, одного порядка списка и выгрузки, уровня 10 и ручных решений. В отдельном профиле без ресурса проверяем совместимость с прежним ранжированием.

Инженер модели отвечает за проверенный импорт таблицы и SQLite-проекцию, бэкенд — за оценки и выгрузки, фронтенд — за каталог и предпросмотр. QA отдельно проверяет порядок при фильтрации, TSV и интерфейс, релиз-инженер и QA по приёмке — изолированную переносную сборку. UX-дизайнер обнаружил двусмысленную стрелку возле заголовка приоритета и попросил пояснить место предварительных оценок. Убрали стрелку, добавили пояснение у фильтра. UI-дизайнер подтвердил читаемость причин на 600 px в обеих темах. Исследовательские правовые расхождения по CONLIT зафиксировали в заметке. На этом этапе модель поставляется локально для проверки владельцем.

[Данные, результаты и воспроизведение](openresearch-integration.md).

## 2026-11-24. Единый книжный и персональный приоритет и расширение корпуса

Цель читателя — понять, какое сохранённое слово полезно взять следующим при известных книжном охвате и собственных повторных поисках. Инженер ранжирования предложил учитывать повторные наблюдения по датам в одной книге и отдельно поиски в разных книгах. Продакт предложил защитить часто встречающиеся слова с одним поиском и ограничить личное повышение одним уровнем. UX-дизайнер потребовал указывать реальный процент книг отдельно от влияния истории на порядок. QA добавил проверки перехода на точной границе уровня, повторного импорта и нескольких записей за одни сутки.

Второй раунд. Абсолютная надбавка 0,15 могла бы сразу пройти несколько порогов для редкого слова. Принят ограниченный множитель шансов до двух; один повторный день добавляет к множителю 0,25, дополнительная книга — 0,50. Один поиск не меняет книжное место среди слов с такой же историей. Два независимых возврата в разных книгах весомее повторного открытия в той же книге. Один календарный день в одной книге учитывается один раз. Чистый книжный балл хранится отдельно. Для выражений без измерения повторы уточняют только место среди предварительных оценок. Историю KOReader/Kobo нельзя надёжно трактовать как последовательность запросов. Ручные решения по-прежнему отвечают за выбор в подборку.

Владелец отдельно подтвердил добавление новых романов. Корпусный инженер расширяет исходные 771 обучающих романов за счёт не использованных в таблице произведений, удерживая 393 тестовых романа и все книги-источники списков со своими авторами за пределами обучения. Инженеры внешних данных заранее разделяют дополнительно полученные открытые современные произведения на отдельные авторские группы для обучения и независимой проверки. Оценки — P@5 книжного охвата на одних и тех же списках и, отдельно, доля будущих повторных запросов по истории до среза. Ни величина личной поправки, ни пороги не подбираются по результатам теста. Бэкенд и фронтенд обеспечивают общий порядок каталога и экспорта; QA проверяет обычный bridge, браузер и частную Windows-сборку.

Итог приёмки. В учебную часть добавлены 251 роман 189 авторов CONLIT и полный роман Гарри Бланка 2022 года, в совокупности 1 023 романа 826 авторов. Выбор участников независимой панели из шести романов пяти других авторов зафиксирован заранее. Расширение добавило 28 050 измеренных ключей. Результат появления слов из первой пятёрки на 393 контрольных книгах изменился с 77,100% до 77,094%, на шести внешних книгах — с 62,075% до 61,783% для основной панели. Интервалы обеих разностей включают ноль. Включили более полную таблицу, учитывая выигрыш в наличии данных и отсутствие подтверждённого роста точности. На той же расширенной таблице личная поправка дала AUC 0,595 вместо 0,589 на двух общих локальных временных срезах; обе дали 6% повторов среди первых 50. У прежней персональной модели в этой задаче 32%, её параметры ранее разрабатывались на тех же окнах. Сохраняем умеренную, объяснимую роль повторов и отдельную цель книжного охвата.

UI-дизайнер обратил внимание, что короткое объяснение со словом «также» ссылалось на отсутствующий в строке текст. Ввели отдельную самодостаточную короткую причину от моста и сохранили полную причину в карточке. QA доказал ошибку на пороге 0,60 → 0,75: счёт в двоичной плавающей точке задерживал слово на уровне 2. Исправлено сравнение с точными порогами, соседнее меньшее значение осталось на 2. Все решения по источникам, расчёту и проверке приведены в [отчёте](personalized-book-priority.md).


## 2026-11-27 — Очередь перевода большой библиотеки

На прошлой проверке один запрос GPT-6 Luna обрабатывал восемь слов за 6,48–8,45 с. Читателю с тысячей подходящих слов приходится ждать 125 последовательных запросов. Продакт предложил ограничить встроенный OpenAI четырьмя одновременными пачками и проверить выигрыш на одинаковом наборе. QA потребовал считать сохранённые результаты и проверять их привязку к слову при обратном порядке ответов. Бэкенд отметил гонку выбора формата ответа, скрытые повторы SDK при ограничении API и риск второго платного запуска в другом окне.

Во втором раунде приняли предел четыре для встроенного OpenAI, прежний размер восемь и последовательный режим для остальных пресетов. Настройка скорости пользователю не требуется. При отказе в доступе или исчерпании лимита диспетчер заканчивает уже запущенные запросы и сохраняет успешные ответы. Последующие слова остаются в очереди. Текущий профиль допускает одну операцию обогащения, принудительное закрытие освобождает её блокировку. Перевод хранится в SQLite в основном потоке. Тимлид отвечает за рабочее окно запросов и замер с GPT-6 Luna, бэкенд за межпроцессную блокировку и согласование формата, QA за воспроизводимый прогон на 1000 вымышленных слов и частичные сбои, релиз-инженер за отдельную внутреннюю сборку. Приёмка требует 125 запросов по восемь слов, пика четыре и нулевого повторного запроса после успеха. Физическую читалку и реальную библиотеку для проверки не используем.


Приёмка на 1000 синтетических записей подтвердила 125 запросов, пик четыре, сохранение 992 записей при сбое одной пачки, повтор только восьми и отсутствие двойной обработки во втором процессе. На живом GPT-6 Luna 32 слова заняли 24,6 с последовательно, 14,2 с при двух запросах и 7,3 с в успешном прогоне при четырёх. В другом прогоне при четырёх запросах три пачки завершились примерно за пять секунд, одна истекла через 120 с. Ускорение зависит от времени ответа и лимитов провайдера, готовые карточки доступны для следующего запуска. Подробности поставки и проверок в WORKLOG.md.


## 2026-11-27 — Экспорт учебных карточек в Obsidian, Quizlet и RemNote

Читатель выбирает слова и одно место назначения на Главной. Kindle остаётся источником слов. Продакт и UX предложили сохранить Anki и подробный TSV, добавить два простых формата для ручного импорта, а для Obsidian запрашивать только корень хранилища. При повторном запуске важно сохранить уже назначенные повторения. Бэкенд и приёмщик сверили правила распознавания колод с официальным парсером Spaced Repetition. Один вложенный тег задаёт колоду в режиме тегов, каталог — в режиме папок. QA обнаружил, что прежняя отдельная синхронизация использует балл 3–10, может дублировать карточки и позволяет выход за выбранный каталог.

Во втором раунде согласовали отдельное пространство Kindle Cards, запись только по выбранным ID и текущим уровням 1–10, сохранение ручных правок и расписания, проверку принадлежности файлов и блокировку параллельных записей. Отключённый плагин получает понятную подсказку. Автоматически устанавливать расширение или менять параметры Obsidian не требуется. Существующие карточки из настроенной старой папки учитываются при повторе. Quizlet получает две колонки с табуляцией, RemNote — Basic forward с экранированием управляющих символов; оба формата сохраняются локально. Бэкенд отвечает за Markdown, инженер интеграции за текстовые форматы, инженер данных за миграцию SQLite, фронтенд за настройки и результат на Главной, тимлид за общую команду, QA за экспорт и повторы на временных хранилищах, релиз-инженер за отдельную Windows-сборку. Приёмка включает реальный парсер SR, особые настройки и чужие файлы, восстановление после частичного сбоя, проверку путей и прежних экспортов.


## 2026-11-27 — Первое знакомство с Kindle Cards

Владелец попросил короткое обучение с голосом лиса, быстрый пропуск и обновлённый README с маскотом. Продакт выделил цену лишнего шага до импорта. UX предложил проговорить реальные действия на примере и дать заполненной библиотеке добровольный вход. Фронтенд указал на риск принять учебную иллюстрацию за действующий элемент или открыть реальный экспорт. Во втором раунде согласовали четыре статичных примера и один переход вперёд на шаг. Открывать карточку, подключать читалку, передавать слова провайдеру и менять настройки для прохождения экскурсии не требуется.

Тимлид отвечает за проверенный момент входа, повтор из Настроек и README с настоящими кадрами. Фронтенд отвечает за диалог с родным FoxFigure, ясную речь лиса и управление с клавиатуры. QA проверяет первый запуск, мгновенный пропуск, повтор, разные размеры, сбой загрузки и отсутствие действий над словами. Релиз-инженер собирает отдельную внутреннюю сборку, приёмщик проверяет настоящий перезапуск с тем же профилем. Критерии — четыре шага от читалки до карточек, «Пропустить» и Escape с первой страницы, подходящий возврат фокуса и доступ к повтору. Решение о первом показе принимается после успешного чтения пустой библиотеки на Главной. Помечаем показ при открытии — закрытие программы посреди знакомства тоже засчитывается. В README отдельно обозначаем возможности внутренней сборки и публичный установщик 0.4.0.

## 2026-11-27 — Планёрка по стабильной версии 1.0 для Windows x64

**Решение тимлида.** Открываем подготовку закрытого релизного кандидата. Публичная 1.0 пока не готова. Читатель должен установить программу, принести слова со своей читалки, понять приоритет уже после первого поиска и получить карточку со своей цитатой. При следующем подключении его правки и расписание должны сохраниться. Платный ИИ для этого пути не требуется.

### От какой сборки отталкиваемся

- В README указан публичный NSIS 0.4.0. Версия 0.4.0 стоит в Tauri, Cargo, npm и Python. Последний коммит рабочей ветки — `6338407`; новый экспорт и обучение проверялись также с изменениями в рабочей копии.
- Переносная Fox Guide прошла нативную проверку первого запуска, пропуска, перезапуска и повтора экскурсии. На этапе Study Exports прошли 419 тестов Python, один пропущен на Windows. После добавления экскурсии прошли 155 тестов интерфейса. Есть отдельные прогоны реального Kindle, Anki и парсера Obsidian SR. Совокупность этих проверок даёт основу для RC. Установку 1.0 поверх публичной 0.4.0 ещё предстоит пройти.
- Стандартная сборка Windows упаковывает мост, но на чистом runner нет шага поставки таблицы книжного охвата. В Fox Guide таблица была добавлена отдельно. В [исследовательской записке](openresearch-integration.md) отмечено расхождение условий CONLIT между карточкой данных и статьёй. Расширенная таблица также использует произведение под CC BY-SA 3.0. Основание публичной поставки конкретного файла и требуемую атрибуцию ещё предстоит зафиксировать.

### Что решили после двух кругов обсуждения

| Разногласие | Решение и основание |
| --- | --- |
| Инженер ранжирования предложил выпустить прежнюю модель, пока выясняются условия корпуса. Продление подготовки отодвигает доступ к готовым импортам и экспортам. | После возражения о первом поиске инженер снял предложение. Сохраняем независимый книжный сигнал. Приоритетный путь — подтвердить возможность распространения текущей таблицы. Если это не удастся, вынести владельцу альтернативу с понятными условиями и сопоставить её с текущей таблицей на тех же отложенных книгах. Переход на первоначальную RP-V2 оставляет тот же вопрос по CONLIT. Изменение обещания о ранжировании решает владелец. |
| Релиз-инженер предложил проверить установщик и затем поставить тег. QA указал, что текущий тег запускает ещё одну сборку. Бэкенд предупредил, что старая программа может продолжить работу с более новой схемой. | Принимаем один файл по SHA-256. После одобрения продвигаем сохранённый файл с тем же хешем. Для репетиции возврата 0.4.0 сначала восстанавливаем **отдельную** копию старого профиля. Обновлённый профиль сохраняем, включая работу после обновления. |
| Продакт предложил самостоятельный проход внешнего читателя. UX-исследователь отделил понятность экрана от технической готовности и от возвращения после следующей книги. | Внутреннюю приёмку можно завершить с тестовым профилем. Для проверки понятности предлагаем один приватный проход без подсказок, когда владелец согласует приглашение. Пока его может отрепетировать владелец. Возвращение после реального чтения измеряем позднее. Количество скачиваний, набор десяти участников и рекламный анонс не входят в допуск кандидата. |
| В Настройках ИИ обещаны «только слово и предложения» и однократная отправка, хотя запрос включает название книги, лемму и часть речи, а сбой может привести к повтору. | Предлагаем убрать название книги из облачного запроса, описать оставшиеся поля и повторы, проверить фактический запрос на учебных данных. Отдельно описать фоновый поиск обложек по метаданным книги в Open Library. Без ключа должны работать импорт, приоритет, правка и выгрузка. |

### План приёмки

| Очерёдность | Ответственные | Что предъявить на следующей планёрке |
| --- | --- | --- |
| 1. Определить состав 1.0 | Инженер ранжирования, релиз-инженер, тимлид | Паспорт поставляемой модели с происхождением, условиями, атрибуцией и SHA-256. На чистом профиле и при наличии прежней локальной таблицы проверить фактически открытый ресурс и ожидаемые порядок, уровень и причину для контрольных однократных поисков. Отдельный повтор в другой книге изменяет личную оценку, а отображаемый книжный процент сохраняется. Проверка только поля `rp-v2-personal` версии таблиц не различает. |
| 2. Зафиксировать исходники и проверить поставку | Тимлид, релиз-инженер, бэкенд | Один проверенный коммит с согласованными версиями, исходниками обучения, файловых экспортов и иллюстрациями README. Исключить локальные профили, ключи и временные сборки. Полный pytest, Vitest, production frontend, Rust и smoke упакованного моста. Проверить состав синтетического запроса ИИ и отсутствие запросов к ИИ при выключенной опции. Собрать NSIS с обычным идентификатором приложения, сохранить его и SHA-256. |
| 3. Установить и обновить | QA, бэкенд, релиз-инженер | Чистая Windows x64 без инструментов разработки, установка от обычного пользователя и запуск с ярлыка. Затем обновление поверх настоящего установщика 0.4.0 в тестовом профиле. Сверить ID и число слов и цитат, перевод и выбранную цитату, решения, очередь, назначения, настройки и историю выгрузок. Проверить целостность SQLite и отказ при невозможности создать резервную копию. Автокопия перед миграцией схемы 4→5 покрывает SQLite. Для возврата взять снимок старых настроек и домиграционную базу, запустить 0.4.0 в изоляции и получить читаемую колоду. |
| 4. Пройти путь от книги до карточки | QA и приёмщик, инженер интеграции с Anki | Реальный Kindle по USB, включая MTP/WPD, плюс импорт из файла. Тот же снимок после переподключения даёт ноль новых записей, один новый поиск появляется один раз. Проверить файловые образцы KOReader и Kobo. На Главной полный счётчик и назначение видны до клика, пять строк служат предпросмотром. Сверить состав полной выгрузки, порции и выгрузки с исключённым уровнем. В тестовом Anki проверить .apkg и AnkiConnect, исправленный перевод и выбранную цитату, отсутствие дубля, сохранение интервала и истории при повторе. |
| 5. Проверить остальные назначения и встречу читателя | QA, UX-исследователь, тимлид | На том же установленном RC проверить повтор в отдельном хранилище Obsidian SR, распознавание карточек, сохранность расписания, пользовательской правки и чужой заметки. Для Quizlet, RemNote и подробного TSV сверить созданный файл, разделители, строки и инструкцию импорта. Из публичного README читатель должен попасть ровно в принимаемую версию. Перед нажатием спросить «Сколько карточек сейчас уйдёт и куда они попадут?» Проверить фактический результат, перезапуск и повтор с одним новым словом. |

Этапы подготовки данных, проверки приватности и подготовки тестового профиля можно вести параллельно. Для установки и окончательной приёмки нужен зафиксированный комплект. Если файл изменился после исправления, QA заново привязывает результаты к новому SHA и повторяет установку и затронутые маршруты. Кандидат с потерей данных, дублем карточки, сбросом расписания, незаявленной передачей данных или тихой подменой обещанного ранжирования не проходит.

**Границы 1.0.** Сохраняем Windows x64, текущие пять назначений и пропускаемое обучение. Новые платформы, назначения, анимации и эксперименты с весами отложены. В тексте релиза перечислим проверенные устройства и версии. Для Quizlet и RemNote обещаем подготовку файла для ручного импорта. Для функций из продуктового плана, включая отдельный разбор спорных слов, сверяем наличие работающего маршрута до упоминания в релизе.

**Следующее решение.** Тимлид собирает паспорт модели, идентификатор коммита и принятого установщика, результаты чистой установки, обновления, восстановления и читательского прохода, список открытых дефектов. До этого дату выхода оставляем открытой. У владельца остаются выбор альтернативы при смене продуктового обещания, приглашение внешнего читателя и окончательное разрешение на публичный выпуск. Изменения этой планёрки ограничены протоколом и журналом.
