"""Ranking v2: which looked-up words are worth learning, and why.

The ranking is a small logistic model over named features. Personal signals
come first: how often the reader looked a word up, in how many books, how
recently, whether it comes from a book being read now, and whether it was
looked up again after it had been exported. Corpus frequency only enters as a
band (very rare words are less worth learning; very common ones were probably
looked up for a rare sense). Evidence that the entry is not a word at all
sends it to "Не слова" or to "Спорные".

Every contribution to the score is named and becomes a reason in plain
Russian, strongest first. The reader's own decision always wins.

The module is pure and deterministic: no I/O, no randomness, no clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime

RANKING_VERSION = "r2"
# `full` uses every personal signal; `learning` is for a library that cannot support them yet (see `library_mode`).
RANKING_MODES = ("learning", "full")
DECISIONS = frozenset({"known", "learn", "skip", "junk"})
SHELVES = ("worth", "disputed", "not_worth", "junk", "known")
# Every reason code `rank` can emit. The sign of a reason's weight says "for" (>0) or "against" (<0).
REASON_CODES = (
    "decision_learn",
    "decision_skip",
    "decision_junk",
    "decision_known",
    "known_again",
    "repeat_lookups",
    "after_export",
    "several_books",
    "reading_now",
    "recency",
    "frequency",
    "frequency_common",
    "junk_non_word",
    "junk_non_english",
    "junk_unknown_word",
    "junk_glued_words",
    "junk_proper_noun",
    "thin_evidence",
)

# A book is about 90 thousand words, a page about 300; Zipf z means 10**z per 10**9 words.
WORDS_PER_BOOK = 90_000
WORDS_PER_PAGE = 300
# From here a word is simply «частое» (about once in 100 pages).
FREQUENT_ZIPF = 4.5
# Days of history from which a library that keeps repeat lookups is ranked in `full` mode; see `library_mode`.
FULL_MODE_MIN_DAYS = 56
# Contributions smaller than this do not become a reason (the frequency band always does).
MIN_REASON_WEIGHT = 0.1


@dataclass(frozen=True)
class WordFacts:
    """Everything the ranking needs to know about one lexeme at one moment.

    Where the fields come from:
    - zipfs, synset/pos counts and warnings: the stored optimizer analysis
      (`lemma_zipf`, `form_zipf`, `wordnet_synset_count`, `wordnet_pos_count`,
      `warnings`).
    - `proper_noun`: analyses do not store it. Set it when every occurrence
      passes `vocab_optimizer.is_probable_proper_noun(word, context, wordnet)`
      (capitalised away from the start of its sentence and unknown to WordNet);
      one ordinary lowercase occurrence makes it False. False when unsure.
    - `lookups`: (when, book_key) for every occurrence known at the moment of
      ranking; at least one.
    - `reading_books`: books with any lookup in the 14 days before `now`
      (the product infers "being read" from recent lookups).
    """

    lemma_zipf: float
    form_zipf: float
    synset_count: int
    pos_count: int
    warnings: frozenset[str]
    proper_noun: bool
    lookups: tuple[tuple[datetime, str], ...]
    reading_books: frozenset[str] = frozenset()
    decision: str | None = None
    exported_at: datetime | None = None
    # When the reader made `decision`; a "known" word looked up after it goes back to the model.
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.lookups:
            raise ValueError("WordFacts needs at least one lookup")
        if self.decision is not None and self.decision not in DECISIONS:
            raise ValueError(f"Unknown decision: {self.decision!r}")


@dataclass(frozen=True)
class Reason:
    code: str
    text: str
    # Contribution to the log-odds; positive means "more worth learning". `score` is always
    # sigmoid(bias + sum of these); a reader's decision is a reason with weight 0.0 that
    # overrides the shelf only, never the score.
    weight: float


@dataclass(frozen=True)
class Ranking:
    score: float
    shelf: str
    reasons: tuple[Reason, ...]
    # Suggested answer for a disputed word ('learn' | 'skip' | 'junk'); None on every other shelf.
    lean: str | None = None
    # The mode the word was ranked in; the reasons only cite signals that mode uses.
    mode: str = "full"


@dataclass(frozen=True)
class Weights:
    """Named weights on the log-odds scale and the shelf thresholds.

    Each personal weight is roughly the log-odds difference seen across all
    evaluation cutoffs, rounded; see the WORKLOG entry of 2026-11-19.
    """

    bias: float = -2.0
    # Per doubling of lookups (2 lookups: +1 x weight, 4: +2 x weight), capped at 8 lookups.
    repeat: float = 0.75
    repeat_cap: int = 8  # at least 1
    # Per doubling of distinct books; small because it mostly repeats what "repeat" already says.
    books: float = 0.25
    # Times 2**(-days / half life) - recency_reference: fresh lookups add, old ones subtract.
    recency: float = 1.2
    recency_half_life_days: float = 21.0
    recency_reference: float = 0.25
    # Looked up in a book the reader is reading now.
    reading: float = 0.5
    # Looked up again after the word had been exported: it did not stick. Measured on the only export
    # evidence the author's library has (words found in Obsidian): those words came back 1.8-2.1 times
    # as often as the rest, an odds ratio of 2.1-2.4 (log 0.7-0.9), and moving the weight between 1 and 3
    # changes AUC and lift@50 by less than their bootstrap noise. Halved from 2.0 to 1.0 to match.
    after_export: float = 1.0
    # Per Zipf unit below rare_zipf (capped at two units) and above common_zipf (capped at two).
    rare: float = -1.0
    rare_zipf: float = 3.0
    common: float = -1.0
    common_zipf: float = 5.0
    # Evidence that the entry is not a word to learn.
    non_word: float = -4.0
    non_english: float = -4.0
    unknown_word: float = -2.0
    glued_words: float = -1.5
    proper_noun: float = -1.5
    # Junk evidence (sum of the magnitudes above) at or over this goes to "junk", below to "disputed".
    strong_junk: float = 3.0
    # Shelf thresholds on the score.
    worth_from: float = 0.22
    disputed_from: float = 0.19

    def __post_init__(self) -> None:
        if self.repeat_cap < 1:
            raise ValueError("repeat_cap must be at least 1")


DEFAULT_WEIGHTS = Weights()

_DECISION_SHELF = {"learn": "worth", "skip": "not_worth", "junk": "junk", "known": "known"}
_DECISION_TEXT = {
    "learn": "вы отметили «учить»",
    "skip": "вы отметили «не учить»",
    "junk": "вы отметили «не слово»",
    "known": "вы отметили «знаю»",
}
_JUNK_FEATURES = (
    ("non_word", {"non_word"}, "не похоже на слово"),
    ("non_english", {"non_english", "unsupported_language"}, "не английское слово"),
    ("unknown_word", {"unknown_to_local_lexicons"}, "нет в словарях"),
    ("glued_words", {"possibly_glued_words"}, "похоже на слитые слова"),
)
_STUDY_LEVEL_THRESHOLDS = (0.34, 0.30, 0.26, 0.22, 0.205, 0.19, 0.12, 0.06)


def library_mode(history_days: int, repeat_signal: bool, min_days: int = FULL_MODE_MIN_DAYS) -> str:
    """The ranking mode of a whole library: `full` or `learning`.

    `full` needs two things: the source keeps repeat lookups (`repeat_signal`; Kindle does, KOReader and Kobo keep
    one row per word) and at least `min_days` days between the first and the last lookup (`history_days`). Otherwise
    the personal signals behind `full` are missing or still too thin, and `learning` orders by what the reader's
    first lookups can tell: the frequency band, the book being read now and recency.
    """
    return "full" if repeat_signal and history_days >= min_days else "learning"


def rank(facts: WordFacts, now: datetime, weights: Weights = DEFAULT_WEIGHTS, mode: str = "full") -> Ranking:
    """Score one word at the moment `now` and place it on a shelf, with reasons.

    In `learning` mode repeat lookups, the number of books and "looked up again after export" take no part in the
    score and never appear as reasons; everything else works as in `full`.
    """
    if mode not in RANKING_MODES:
        raise ValueError(f"Unknown ranking mode: {mode!r}")
    now = _aware(now)
    contributions = _contributions(facts, now, weights, mode)
    logit = weights.bias + sum(reason.weight for reason in contributions)
    junk_evidence = -sum(reason.weight for reason in contributions if reason.code.startswith("junk_"))
    score = _sigmoid(logit)
    reasons = tuple(sorted(contributions, key=lambda reason: -abs(reason.weight)))

    decision = _effective_decision(facts)
    if decision is not None:
        decided = Reason(f"decision_{decision}", _DECISION_TEXT[decision], 0.0)
        # The score stays the model's; "учить" and the other decisions only fix the shelf.
        return Ranking(score=score, shelf=_DECISION_SHELF[decision], reasons=(decided, *reasons), mode=mode)
    if junk_evidence >= weights.strong_junk:
        return Ranking(score=score, shelf="junk", reasons=reasons, mode=mode)
    if junk_evidence > 0:
        # Some evidence that it is not a word: the reader decides, the suggestion is "не слово".
        return Ranking(score=score, shelf="disputed", reasons=reasons, lean="junk", mode=mode)
    if weights.disputed_from <= score < weights.worth_from:
        middle = (weights.disputed_from + weights.worth_from) / 2
        lean = "learn" if score >= middle else "skip"
        return Ranking(score=score, shelf="disputed", reasons=reasons, lean=lean, mode=mode)
    if score >= weights.worth_from:
        return Ranking(score=score, shelf="worth", reasons=reasons, mode=mode)
    return Ranking(
        score=score, shelf="not_worth", reasons=_with_negative_reason(reasons, len(facts.lookups)), mode=mode
    )


def structural_study_priority(token: str) -> dict[str, int | float | bool | str] | None:
    """A non-blank token with no Unicode letters needs no lexical or time evidence."""
    token = token.strip()
    if token and not any(character.isalpha() for character in token):
        return {"level": 10, "score": 0.0, "provisional": False, "reason": "В записи нет букв"}
    return None


def study_priority(
    facts: WordFacts, now: datetime, *, mode: str, token: str, assessed: Ranking | None = None
) -> dict[str, int | float | bool | str]:
    """Describe an analysed token on the 1–10 scale independently of reader decisions."""
    structural = structural_study_priority(token)
    if structural is not None:
        return structural
    if facts.decision is not None:
        assessed = rank(replace(facts, decision=None, decided_at=None), now, mode=mode)
    elif assessed is None or assessed.mode != mode:
        assessed = rank(facts, now, mode=mode)

    level = next(
        (position for position, threshold in enumerate(_STUDY_LEVEL_THRESHOLDS, 1) if assessed.score >= threshold), 9
    )
    strongest = next((reason for reason in assessed.reasons if reason.weight), None)
    text = strongest.text if strongest else "Пока мало признаков полезности"
    if strongest and strongest.code == "junk_unknown_word":
        text = (
            "Словарная проверка неполная" if "wordnet_unavailable" in facts.warnings
            else "Слово не найдено в доступных словарях"
        )
    elif strongest and strongest.code in {"junk_non_word", "junk_non_english"}:
        text = "Форма слова распознана неуверенно"
    elif strongest and strongest.code == "recency":
        text = "Недавний поиск в истории читалки" if strongest.weight > 0 else "Давний поиск в истории читалки"
    return {"level": level, "score": assessed.score, "provisional": False, "reason": text}


def _with_negative_reason(reasons: tuple[Reason, ...], lookups: int) -> tuple[Reason, ...]:
    """A word on «Не стоит учить» always says why.

    Usually a negative contribution does (rare or very common word, old lookup, evidence of junk). A word looked
    up once, in the middle of the frequency band, with a lookup neither fresh nor stale, scores low only because
    of the bias: «not enough signals». That is stated as a reason of weight 0.0, so `score` still decomposes.
    """
    if any(reason.weight < 0 for reason in reasons):
        return reasons
    text = "искали один раз, других признаков нет" if lookups == 1 else "мало признаков, что слово вам нужно"
    return (*reasons, Reason("thin_evidence", text, 0.0))


def _effective_decision(facts: WordFacts) -> str | None:
    """The decision that overrides the model; "знаю" lapses when the word was looked up again after it."""
    if facts.decision == "known" and _looked_up_after(facts, facts.decided_at):
        return None
    return facts.decision


def _looked_up_after(facts: WordFacts, moment: datetime | None) -> bool:
    return moment is not None and any(_aware(when) > _aware(moment) for when, _ in facts.lookups)


def _contributions(facts: WordFacts, now: datetime, weights: Weights, mode: str = "full") -> list[Reason]:
    """Named contributions to the log-odds, in a fixed order (ties keep this order)."""
    lookups = [(_aware(when), book) for when, book in facts.lookups]
    reasons: list[Reason] = []

    personal = mode == "full"
    count = len(lookups)
    if personal and count > 1:
        value = weights.repeat * math.log2(min(count, weights.repeat_cap))
        reasons.append(Reason("repeat_lookups", f"искали {_times(count)}", value))

    exported_at = _aware(facts.exported_at) if facts.exported_at is not None else None
    if personal and exported_at is not None and any(when > exported_at for when, _ in lookups):
        reasons.append(Reason("after_export", "снова искали после экспорта", weights.after_export))
    if facts.decision == "known" and _effective_decision(facts) is None:
        # Not counted twice when the word was also looked up again after an export.
        # In `learning` mode it is only a note: the score does not use repeat signals.
        counted = not personal or any(reason.code == "after_export" for reason in reasons)
        reasons.append(Reason("known_again", "снова искали после «знаю»", 0.0 if counted else weights.after_export))

    books = {book for _, book in lookups}
    if personal and len(books) > 1:
        reasons.append(Reason("several_books", _in_books(len(books)), weights.books * math.log2(len(books))))

    if books & facts.reading_books:
        reasons.append(Reason("reading_now", "Из книги с недавними поисками", weights.reading))

    days = max(0.0, (now - max(when for when, _ in lookups)).total_seconds() / 86400)
    freshness = 2.0 ** (-days / weights.recency_half_life_days) - weights.recency_reference
    value = weights.recency * freshness
    if abs(value) >= MIN_REASON_WEIGHT:
        reasons.append(Reason("recency", _when(days) if value > 0 else "давно не искали", value))

    zipf = _zipf(facts)
    if zipf > 0:
        if zipf >= weights.common_zipf:
            value = weights.common * min(2.0, zipf - weights.common_zipf) + 0.0
            if value <= -MIN_REASON_WEIGHT:
                reasons.append(Reason("frequency_common", "очень частое слово", value))
            else:
                reasons.append(Reason("frequency", "частое", 0.0))
        else:
            # "+ 0.0" turns a negative zero into a plain zero.
            value = weights.rare * min(2.0, max(0.0, weights.rare_zipf - zipf)) + 0.0
            text = "частое" if zipf >= FREQUENT_ZIPF else _frequency_text(zipf)
            reasons.append(Reason("frequency", text, value))

    for name, codes, text in _JUNK_FEATURES:
        # A word no frequency list or WordNet knows is "not in the dictionaries" even without the warning.
        unknown = name == "unknown_word" and zipf <= 0 and facts.synset_count <= 0
        if codes & facts.warnings or unknown:
            reasons.append(Reason(f"junk_{name}", text, getattr(weights, name)))
    if facts.proper_noun:
        reasons.append(Reason("junk_proper_noun", "похоже на имя", weights.proper_noun))
    return reasons


def _zipf(facts: WordFacts) -> float:
    values = [value for value in (facts.lemma_zipf, facts.form_zipf) if math.isfinite(value)]
    return max(values, default=0.0)


def _aware(moment: datetime) -> datetime:
    """A time without a zone is taken as UTC, so mixed inputs still compare."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1.0 + exp)


# Russian wording.

def _plural(number: int, one: str, few: str, many: str) -> str:
    """Russian noun form for a count: 1 книга, 2 книги, 5 книг, 11 книг, 21 книга."""
    tail = abs(number) % 100
    if 11 <= tail <= 14:
        return many
    tail %= 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def _times(count: int) -> str:
    if count == 2:
        return "дважды"
    return f"{count} {_plural(count, 'раз', 'раза', 'раз')}"


_BOOKS_LOCATIVE = {2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти"}


def _in_books(count: int) -> str:
    if count in _BOOKS_LOCATIVE:
        return f"в {_BOOKS_LOCATIVE[count]} ваших книгах"
    # After a number the noun agrees with its last digits: «в 21 вашей книге», «в 22 ваших книгах».
    tail = count % 100
    if tail % 10 == 1 and tail != 11:
        return f"в {count} вашей книге"
    return f"в {count} ваших книгах"


def _when(days: float) -> str:
    whole = int(days)
    if whole == 0:
        return "искали сегодня"
    if whole == 1:
        return "искали вчера"
    return f"искали {whole} {_plural(whole, 'день', 'дня', 'дней')} назад"


def _frequency_text(zipf: float) -> str:
    """'Встречается раз в ~N книг (страниц)' from a Zipf value."""
    words = 10.0 ** (9.0 - zipf)
    books = words / WORDS_PER_BOOK
    if books >= 1.95:
        count = round(books)
        return f"встречается раз в ~{count} {_plural(count, 'книгу', 'книги', 'книг')}"
    if books >= 1.0:
        # A fraction takes the genitive singular: «раз в ~1,5 книги».
        return f"встречается раз в ~{books:.1f}".replace(".", ",") + " книги"
    pages = words / WORDS_PER_PAGE
    count = max(1, round(pages, -1) if pages >= 100 else round(pages))
    count = int(count)
    return f"встречается раз в ~{count} {_plural(count, 'страницу', 'страницы', 'страниц')}"
