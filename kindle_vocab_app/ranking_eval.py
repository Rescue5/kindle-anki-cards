"""Offline evaluation of word-ranking strategies on the local library.

A ranking has to answer "which of the words looked up so far will the reader
need again?". There are no outside labels, so the library's own history is the
ground truth: at a cutoff date every feature uses only lookups before it, and a
word counts as needed again when it is looked up again within the following
window. Several cutoffs are evaluated so that one month does not decide.

Run it on the local library:

    python -m kindle_vocab_app.ranking_eval

The report is printed and saved under `.app-data/ranking_eval/`. Only
aggregate numbers are written; no words or contexts leave the database.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable, Collection, Sequence
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from wordfreq import zipf_frequency

from kindle_vocab_app.library_repository import DATABASE_FILENAME
from kindle_vocab_app.logging_config import configure_logging, get_logger
from kindle_vocab_app.ranking import DEFAULT_WEIGHTS, SHELVES, Weights, WordFacts, rank
from kindle_vocab_app.vocab_optimizer import (
    SPECIALIZED_LEXNAMES,
    is_probable_proper_noun,
    score_importance,
    wordnet_features,
)

logger = get_logger(__name__)

DEFAULT_HORIZON_DAYS = 42
DEFAULT_TOP_K = (50, 100)
BOOTSTRAP_ROUNDS = 200
MIN_POSITIVES = 10
# Middle of the frequency band a reader of English fiction tends to look up.
FREQUENCY_SWEET_SPOT = 3.6
# A book with a lookup this recently counts as being read at the cutoff.
READING_DAYS = 14


@dataclass(frozen=True)
class Lookup:
    lexeme_id: str
    book_key: str
    at: datetime
    # Capitalised away from the start of its sentence and unknown to WordNet (see `WordFacts.proper_noun`).
    proper: bool = False


@dataclass(frozen=True)
class Lexical:
    """Facts about a lexeme that do not depend on when it was looked up."""

    display_form: str
    base_form: str
    lemma_zipf: float
    form_zipf: float
    synset_count: int
    pos_count: int
    warnings: frozenset[str]
    pos: str = ""
    # False when the optimizer rejected the word; the app never ranks those.
    accepted: bool = True
    # WordNet places it in a specialised domain; the app scores such words half a point lower.
    specialized: bool = False
    # When the word was last put into a destination (the library's `destinations` rows); None when never.
    exported_at: datetime | None = None


@dataclass(frozen=True)
class Example:
    lexeme_id: str
    lexical: Lexical
    lookups_before: int
    books_before: int
    days_since_last: float
    days_since_first: float
    needed_again: bool
    # (when, book_key) of every lookup before the cutoff, oldest first.
    history: tuple[tuple[datetime, str], ...] = ()
    # Books with any lookup in the READING_DAYS before the cutoff: "the book being read".
    reading_books: frozenset[str] = frozenset()
    cutoff: datetime | None = None
    # Every lookup before the cutoff looks like a name; export time only if it was before the cutoff.
    proper_noun: bool = False
    exported_at: datetime | None = None


Ranker = Callable[[Example], float]


@dataclass
class Library:
    lookups: list[Lookup]
    lexical: dict[str, Lexical]

    @property
    def first_lookup(self) -> datetime:
        return min(item.at for item in self.lookups)

    @property
    def last_lookup(self) -> datetime:
        return max(item.at for item in self.lookups)


@dataclass
class RankerResult:
    auc: float
    precision: dict[int, float]
    auc_interval: tuple[float, float]
    precision_interval: dict[int, tuple[float, float]] = field(default_factory=dict)


def parse_timestamp(value: str) -> datetime | None:
    """Read a stored lookup time; a bare date is taken as midnight UTC."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def load_library(db_path: Path) -> Library:
    # A connection used as a context manager only ends the transaction; closing() releases the file.
    with closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        have = {str(row["name"]) for row in connection.execute("PRAGMA table_info(occurrences)")}
        # `word` and `context` only feed the proper-noun check; a library without them still evaluates.
        text = ", ".join(column if column in have else f"'' AS {column}" for column in ("word", "context"))
        occurrences = connection.execute(
            f"SELECT lexeme_id, book_key, looked_up_at, {text} FROM occurrences"
        ).fetchall()
        # Rejected analyses keep their payload too; their warnings are what got them rejected.
        payloads = {
            str(row["lexeme_id"]): row["payload_json"]
            for row in connection.execute(
                "SELECT lexeme_id, payload_json FROM analyses WHERE payload_json IS NOT NULL AND payload_json != ''"
            )
        }
        exported = _exported_at(connection)
        lexical = {
            str(row["id"]): replace(
                _lexical(str(row["display_form"] or ""), payloads.get(str(row["id"]))),
                exported_at=exported.get(str(row["id"])),
            )
            for row in connection.execute("SELECT id, display_form FROM lexemes")
        }
    lookups = []
    for row in occurrences:
        at = parse_timestamp(row["looked_up_at"])
        if at is None:
            continue
        lexeme_id = str(row["lexeme_id"])
        known = lexical.get(lexeme_id)
        proper = known is not None and is_probable_proper_noun(
            str(row["word"] or ""), str(row["context"] or ""), {"synset_count": known.synset_count}
        )
        lookups.append(Lookup(lexeme_id, str(row["book_key"] or ""), at, proper))
    logger.info("Loaded ranking evaluation data lookups=%d lexemes=%d", len(lookups), len(lexical))
    return Library(lookups=lookups, lexical=lexical)


def _exported_at(connection: sqlite3.Connection) -> dict[str, datetime]:
    """Latest time each lexeme was put into a destination; empty while the library has no such rows."""
    try:
        rows = connection.execute(
            "SELECT lexeme_id, last_exported_at, last_synced_at FROM destinations "
            "WHERE state IN ('synced', 'exported')"
        ).fetchall()
    except sqlite3.Error:
        return {}
    result: dict[str, datetime] = {}
    for row in rows:
        moments = [parse_timestamp(str(row[name] or "")) for name in ("last_exported_at", "last_synced_at")]
        when = max((moment for moment in moments if moment is not None), default=None)
        if when is not None:
            key = str(row["lexeme_id"])
            result[key] = max(when, result.get(key, when))
    return result


def _lexical(display_form: str, payload_json: str | None) -> Lexical:
    payload: dict[str, Any] = {}
    if payload_json:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {}
    word = display_form.lower()
    base_form = str(payload.get("base_form") or word)
    pos = str(payload.get("pos") or "")
    # Lexnames depend on the word alone, so recomputing them cannot leak later lookups.
    lexnames = set(wordnet_features(base_form, pos, "").get("lexnames") or [])
    return Lexical(
        display_form=display_form,
        base_form=base_form,
        lemma_zipf=_float(payload.get("lemma_zipf"), lambda: zipf_frequency(base_form, "en")),
        form_zipf=_float(payload.get("form_zipf"), lambda: zipf_frequency(word, "en")),
        synset_count=int(payload.get("wordnet_synset_count") or 0),
        pos_count=int(payload.get("wordnet_pos_count") or 0),
        warnings=frozenset(str(item) for item in payload.get("warnings") or []),
        pos=pos,
        accepted=payload.get("accepted") is not False,
        specialized=bool(lexnames & SPECIALIZED_LEXNAMES),
    )


def _float(value: Any, fallback: Callable[[], float]) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback())


def build_examples(
    library: Library,
    cutoff: datetime,
    horizon: timedelta,
    include_rejected: bool = False,
    outcome: Library | None = None,
) -> list[Example]:
    """One example per lexeme looked up before the cutoff; nothing after it leaks in.

    Words the optimizer rejected are left out by default, as the app never ranks them. The "needed again" label
    is read from `outcome` when given (the same library with its repeat lookups, while `library` has them
    collapsed), else from `library`.
    """
    before: dict[str, list[Lookup]] = defaultdict(list)
    needed: set[str] = set()
    reading: set[str] = set()
    for item in library.lookups:
        if item.at < cutoff:
            before[item.lexeme_id].append(item)
            if item.at >= cutoff - timedelta(days=READING_DAYS):
                reading.add(item.book_key)
        elif item.at < cutoff + horizon and outcome is None:
            needed.add(item.lexeme_id)
    if outcome is not None:
        needed = {
            item.lexeme_id for item in outcome.lookups if cutoff <= item.at < cutoff + horizon
        }
    reading_books = frozenset(reading)
    examples = []
    for lexeme_id, items in before.items():
        lexical = library.lexical.get(lexeme_id)
        if lexical is None or not (lexical.accepted or include_rejected):
            continue
        times = [item.at for item in items]
        examples.append(Example(
            lexeme_id=lexeme_id,
            lexical=lexical,
            lookups_before=len(items),
            books_before=len({item.book_key for item in items}),
            days_since_last=(cutoff - max(times)).total_seconds() / 86400,
            days_since_first=(cutoff - min(times)).total_seconds() / 86400,
            needed_again=lexeme_id in needed,
            history=tuple(sorted((item.at, item.book_key) for item in items)),
            reading_books=reading_books,
            cutoff=cutoff,
            proper_noun=all(item.proper for item in items),
            exported_at=lexical.exported_at if lexical.exported_at and lexical.exported_at < cutoff else None,
        ))
    examples.sort(key=lambda example: example.lexeme_id)
    return examples


# Rankers. Higher means "show earlier".

def frequency(example: Example) -> float:
    return max(example.lexical.lemma_zipf, example.lexical.form_zipf)


def current_score(example: Example) -> float:
    """The app's importance score, recomputed with only the lookups before the cutoff."""
    lexical = example.lexical
    score, _ = score_importance(
        word=lexical.display_form.lower(),
        base_form=lexical.base_form,
        frequencies={"lemma_zipf": lexical.lemma_zipf, "form_zipf": lexical.form_zipf},
        wordnet={"synset_count": lexical.synset_count, "pos_count": lexical.pos_count},
        warnings=dict.fromkeys(lexical.warnings, True),
        # Not stored in analyses; it only caps names, which are rare among looked-up words.
        proper_noun=False,
        genre={"specialized": lexical.specialized, "preferred_match": False},
        occurrence_count=example.lookups_before,
    )
    return float(score)


def ranking_v2(example: Example) -> float:
    """Ranking v2 with its shipped default weights; nothing is fitted per cutoff.

    Exports and proper nouns are left out, as in the first measurement; `v2_variant` switches them on.
    """
    return rank(word_facts(example), _moment(example)).score


def ranking_learning(example: Example) -> float:
    """Ranking v2 in `learning` mode: no repeat lookups, books or exports, only the band, the book read and recency."""
    return rank(word_facts(example), _moment(example), mode="learning").score


def v2_variant(
    weights: Weights = DEFAULT_WEIGHTS,
    exports: bool = False,
    proper_nouns: bool = False,
    mode: str = "full",
) -> Ranker:
    """Ranking v2 with other weights and/or the optional inputs the library may know."""

    def ranker(example: Example) -> float:
        facts = word_facts(example, exports=exports, proper_nouns=proper_nouns)
        return rank(facts, _moment(example), weights, mode).score

    return ranker


def word_facts(example: Example, exports: bool = False, proper_nouns: bool = False) -> WordFacts:
    """What the app would know about the word at the cutoff.

    The reader's decisions are not part of the history. Exports (from the
    library's destination rows) and proper nouns (a capitalisation heuristic;
    analyses do not store it) are only passed when asked for.
    """
    lexical = example.lexical
    return WordFacts(
        lemma_zipf=lexical.lemma_zipf,
        form_zipf=lexical.form_zipf,
        synset_count=lexical.synset_count,
        pos_count=lexical.pos_count,
        warnings=lexical.warnings,
        proper_noun=example.proper_noun if proper_nouns else False,
        lookups=example.history or _synthetic_history(example),
        reading_books=example.reading_books,
        exported_at=example.exported_at if exports else None,
    )


def _moment(example: Example) -> datetime:
    return example.cutoff or _SYNTHETIC_CUTOFF


_SYNTHETIC_CUTOFF = datetime(2000, 1, 1, tzinfo=UTC)


def _synthetic_history(example: Example) -> tuple[tuple[datetime, str], ...]:
    """Lookups matching the counts of an example built by hand (tests), oldest first."""
    now = _moment(example)
    count = max(1, example.lookups_before)
    books = max(1, example.books_before)
    first = now - timedelta(days=example.days_since_first)
    last = now - timedelta(days=example.days_since_last)
    times = [first + (last - first) * (i / (count - 1)) if count > 1 else last for i in range(count)]
    return tuple((when, f"book-{i % books}") for i, when in enumerate(times))


def lookups(example: Example) -> float:
    return float(example.lookups_before)


def recency(example: Example) -> float:
    return -example.days_since_last


def features(example: Example) -> list[float]:
    """Inputs of the learned ranker; keep in step with FEATURE_NAMES."""
    zipf = frequency(example)
    return [
        zipf,
        -abs(zipf - FREQUENCY_SWEET_SPOT),
        math.log1p(example.lookups_before - 1),
        float(example.books_before > 1),
        -math.log1p(example.days_since_last),
        math.log1p(example.lexical.synset_count),
        float(bool(example.lexical.warnings)),
    ]


FEATURE_NAMES = (
    "frequency",
    "closeness to the usual band",
    "repeat lookups",
    "several books",
    "recency",
    "senses",
    "warnings",
)

BASELINES: dict[str, Ranker] = {
    "frequency": frequency,
    "current_score": current_score,
    "lookups": lookups,
    "recency": recency,
    "ranking_v2": ranking_v2,
    "ranking_learning": ranking_learning,
}


@dataclass
class LogisticModel:
    """A small L2-regularised logistic regression, deterministic and explainable."""

    weights: list[float]
    bias: float
    means: list[float]
    scales: list[float]

    def score(self, example: Example) -> float:
        row = self._standardise(features(example))
        return self.bias + sum(w * x for w, x in zip(self.weights, row, strict=True))

    def _standardise(self, row: Sequence[float]) -> list[float]:
        return [(x - m) / s for x, m, s in zip(row, self.means, self.scales, strict=True)]

    @classmethod
    def fit(cls, examples: Sequence[Example], l2: float = 1.0, epochs: int = 400, rate: float = 0.2) -> LogisticModel:
        rows = [features(example) for example in examples]
        labels = [1.0 if example.needed_again else 0.0 for example in examples]
        width = len(rows[0])
        means = [sum(row[i] for row in rows) / len(rows) for i in range(width)]
        scales = [
            math.sqrt(sum((row[i] - means[i]) ** 2 for row in rows) / len(rows)) or 1.0
            for i in range(width)
        ]
        model = cls([0.0] * width, 0.0, means, scales)
        data = [model._standardise(row) for row in rows]
        count = len(data)
        for _ in range(epochs):
            grad_w = [l2 * w / count for w in model.weights]
            grad_b = 0.0
            for row, label in zip(data, labels, strict=True):
                error = _sigmoid(model.bias + sum(w * x for w, x in zip(model.weights, row, strict=True))) - label
                for i in range(width):
                    grad_w[i] += error * row[i] / count
                grad_b += error / count
            model.weights = [w - rate * g for w, g in zip(model.weights, grad_w, strict=True)]
            model.bias -= rate * grad_b
        return model


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1.0 + exp)


# Metrics.

def auc(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Probability that a needed word outranks a not-needed one; ties count half."""
    positives = sum(1 for label in labels if label)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return float("nan")
    ordered = sorted(zip(scores, labels, strict=True), key=lambda pair: pair[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2
        rank_sum += average_rank * sum(1 for _, label in ordered[index:end] if label)
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def precision_at(scores: Sequence[float], labels: Sequence[bool], k: int) -> float:
    """Share of needed words among the top k; a tie at the boundary is shared out evenly."""
    if not scores:
        return float("nan")
    k = min(k, len(scores))
    ordered = sorted(zip(scores, labels, strict=True), key=lambda pair: -pair[0])
    threshold = ordered[k - 1][0]
    above = [label for score, label in ordered if score > threshold]
    tied = [label for score, label in ordered if score == threshold]
    slots = k - len(above)
    hits = sum(above) + (sum(tied) * slots / len(tied) if tied else 0.0)
    return hits / k


def bootstrap_interval(
    scores: Sequence[float],
    labels: Sequence[bool],
    metric: Callable[[Sequence[float], Sequence[bool]], float],
    rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = 7,
) -> tuple[float, float]:
    """95% percentile interval of a metric over resampled words."""
    generator = random.Random(seed)
    size = len(scores)
    values = []
    for _ in range(rounds):
        picks = [generator.randrange(size) for _ in range(size)]
        value = metric([scores[i] for i in picks], [labels[i] for i in picks])
        if not math.isnan(value):
            values.append(value)
    if not values:
        return (float("nan"), float("nan"))
    values.sort()
    return (values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))])


def score_ranker(examples: Sequence[Example], ranker: Ranker, top_k: Sequence[int]) -> RankerResult:
    scores = [ranker(example) for example in examples]
    labels = [example.needed_again for example in examples]
    return RankerResult(
        auc=auc(scores, labels),
        precision={k: precision_at(scores, labels, k) for k in top_k},
        auc_interval=bootstrap_interval(scores, labels, auc),
        precision_interval={
            k: bootstrap_interval(scores, labels, lambda s, y, k=k: precision_at(s, y, k)) for k in top_k
        },
    )


def default_cutoffs(library: Library, horizon: timedelta) -> list[datetime]:
    """Month starts that leave a full window of later lookups to judge by."""
    first, last = library.first_lookup, library.last_lookup
    cutoff = _next_month(datetime(first.year, first.month, 1, tzinfo=UTC))
    cutoffs = []
    while cutoff + horizon <= last:
        cutoffs.append(cutoff)
        cutoff = _next_month(cutoff)
    return cutoffs


def _next_month(moment: datetime) -> datetime:
    return datetime(moment.year + moment.month // 12, moment.month % 12 + 1, 1, tzinfo=UTC)


# Other libraries, newcomers, ablations.

def library_from_entries(
    entries: Sequence[dict[str, Any]],
    lexical: dict[str, Lexical] | None = None,
) -> Library:
    """A library from reader entries (`reader_sources.fetch_entries`); lexemes are the lowercased words.

    `lexical` gives the facts of words by lexeme id; the others are looked up in WordNet and the frequency list.
    """
    lookups = []
    facts: dict[str, Lexical] = dict(lexical or {})
    for entry in entries:
        word = str(entry.get("word") or "").strip()
        at = parse_timestamp(str(entry.get("looked_up_at") or ""))
        if not word or at is None:
            continue
        lexeme_id = word.casefold()
        if lexeme_id not in facts:
            facts[lexeme_id] = _lexical(word, None)
        names = {"synset_count": facts[lexeme_id].synset_count}
        proper = is_probable_proper_noun(word, str(entry.get("context") or ""), names)
        lookups.append(Lookup(lexeme_id, str(entry.get("book_key") or ""), at, proper))
    return Library(lookups=lookups, lexical=facts)


def load_reader_library(path: Path, lexical: dict[str, Lexical] | None = None) -> Library:
    """Evaluate on a KOReader, Kobo or Kindle words file instead of the app's library."""
    from kindle_vocab_app.reader_sources import fetch_entries

    return library_from_entries(fetch_entries(path), lexical)


def restrict_library(
    library: Library,
    first_books: int | None = None,
    first_days: float | None = None,
    only_books: Collection[str] | None = None,
) -> Library:
    """What a newcomer would have: only some books and/or the first days of lookups.

    `first_books` keeps the books started first (by their first lookup), `only_books` keeps named ones; days count
    from the first remaining lookup. Labels are cut the same way, so a window never reaches into a book or a time
    the newcomer has not got to.
    """
    lookups = library.lookups
    if only_books is not None:
        lookups = [item for item in lookups if item.book_key in only_books]
    if first_books is not None:
        started: dict[str, datetime] = {}
        for item in lookups:
            started[item.book_key] = min(item.at, started.get(item.book_key, item.at))
        keep = set(sorted(started, key=lambda book: (started[book], book))[:first_books])
        lookups = [item for item in lookups if item.book_key in keep]
    if first_days is not None and lookups:
        end = min(item.at for item in lookups) + timedelta(days=first_days)
        lookups = [item for item in lookups if item.at < end]
    return Library(lookups=list(lookups), lexical=library.lexical)


def step_cutoffs(library: Library, horizon: timedelta, step_days: float, start_days: float) -> list[datetime]:
    """Cutoffs `start_days` after the first lookup and then every `step_days`, each with a full window after it."""
    if not library.lookups:
        return []
    last = library.last_lookup
    cutoff = library.first_lookup + timedelta(days=start_days)
    cutoffs = []
    while cutoff + horizon <= last:
        cutoffs.append(cutoff)
        cutoff += timedelta(days=step_days)
    return cutoffs


# Metrics over several cutoffs at once: each cutoff is a group, a metric is the mean over groups, and the
# bootstrap resamples words inside every group (the same words for every ranker, so differences are paired).

Scores = dict[str, list[float]]
GroupMetric = Callable[[Scores, Sequence[bool]], float]


@dataclass
class Group:
    scores: Scores
    labels: list[bool]


def score_groups(
    library: Library,
    cutoffs: Sequence[datetime],
    horizon: timedelta,
    rankers: dict[str, Ranker],
    min_positives: int = 3,
    include_rejected: bool = False,
    outcome: Library | None = None,
) -> list[Group]:
    groups = []
    for cutoff in cutoffs:
        examples = build_examples(library, cutoff, horizon, include_rejected, outcome)
        labels = [example.needed_again for example in examples]
        if sum(labels) < min_positives or sum(labels) == len(labels):
            continue
        scores = {name: [ranker(example) for example in examples] for name, ranker in rankers.items()}
        groups.append(Group(scores, labels))
    return groups


def lift_at(scores: Sequence[float], labels: Sequence[bool], k: int) -> float:
    """Precision@k over the share of words needed again; nan when nobody was needed again."""
    if not labels or not any(labels):
        return float("nan")
    return precision_at(scores, labels, k) / (sum(labels) / len(labels))


def metric_auc(name: str) -> GroupMetric:
    return lambda scores, labels: auc(scores[name], labels)


def metric_lift(name: str, k: int) -> GroupMetric:
    return lambda scores, labels: lift_at(scores[name], labels, k)


def metric_delta(metric: Callable[[str], GroupMetric], new: str, old: str) -> GroupMetric:
    return lambda scores, labels: metric(new)(scores, labels) - metric(old)(scores, labels)


def group_value(groups: Sequence[Group], metric: GroupMetric) -> float:
    return _mean(metric(group.scores, group.labels) for group in groups)


def group_interval(
    groups: Sequence[Group],
    metric: GroupMetric,
    rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = 7,
) -> tuple[float, float]:
    """95% percentile interval of the mean metric over words resampled inside every cutoff."""
    generator = random.Random(seed)
    values = []
    for _ in range(rounds):
        parts = []
        for group in groups:
            size = len(group.labels)
            picks = [generator.randrange(size) for _ in range(size)]
            sample = {name: [column[i] for i in picks] for name, column in group.scores.items()}
            parts.append(metric(sample, [group.labels[i] for i in picks]))
        value = _mean(parts)
        if not math.isnan(value):
            values.append(value)
    if not values:
        return (float("nan"), float("nan"))
    values.sort()
    return (values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))])


def _estimate(groups: Sequence[Group], metric: GroupMetric) -> dict[str, float]:
    low, high = group_interval(groups, metric)
    return {"value": group_value(groups, metric), "low": low, "high": high}


def compare_rankers(groups: Sequence[Group], names: Sequence[str], top_k: Sequence[int]) -> dict[str, Any]:
    """AUC and lift@k with intervals for each ranker, averaged over the cutoffs."""
    return {
        name: {
            "auc": _estimate(groups, metric_auc(name)),
            "lift": {str(k): _estimate(groups, metric_lift(name, k)) for k in top_k},
        }
        for name in names
    }


def compare_to(groups: Sequence[Group], new: str, old: str, top_k: Sequence[int]) -> dict[str, Any]:
    """Paired difference new - old in AUC and lift@k, with intervals."""
    return {
        "auc": _estimate(groups, metric_delta(metric_auc, new, old)),
        "lift": {str(k): _estimate(groups, metric_delta(lambda n, k=k: metric_lift(n, k), new, old)) for k in top_k},
    }


def shelf_counts(
    library: Library,
    at: datetime | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
    mode: str = "full",
) -> dict[str, Any]:
    """How the words looked up so far fall on the shelves at `at` (default: just after the last lookup)."""
    at = at or library.last_lookup + timedelta(seconds=1)
    examples = build_examples(library, at, timedelta(0), include_rejected=True)
    counts = dict.fromkeys(SHELVES, 0)
    for example in examples:
        counts[rank(word_facts(example), at, weights, mode).shelf] += 1
    total = len(examples)
    return {"words": total, "shelves": counts, "disputed_share": counts["disputed"] / total if total else 0.0}


def too_basic_recall(library: Library, cutoffs: Sequence[datetime], horizon: timedelta) -> dict[str, Any]:
    """Do words flagged `too_basic` that v2 puts on «Не стоит учить» come back more often than other words?

    Counted over all cutoffs together (a word at two cutoffs counts twice): every flagged word, those v2 sends to
    not_worth, how many were looked up again within the window, against the base rate of the other words.
    """
    flagged = flagged_back = hidden = hidden_back = rest = rest_back = 0
    shelves = dict.fromkeys(SHELVES, 0)
    for cutoff in cutoffs:
        for example in build_examples(library, cutoff, horizon, include_rejected=True):
            if "too_basic" in example.lexical.warnings:
                flagged += 1
                flagged_back += example.needed_again
                shelf = rank(word_facts(example), cutoff).shelf
                shelves[shelf] += 1
                if shelf == "not_worth":
                    hidden += 1
                    hidden_back += example.needed_again
            else:
                rest += 1
                rest_back += example.needed_again
    return {
        "flagged": flagged,
        "flagged_back": flagged_back,
        "flagged_shelves": shelves,
        "not_worth": hidden,
        "not_worth_back": hidden_back,
        "not_worth_rate": _rate(hidden_back, hidden),
        "other_words": rest,
        "other_back": rest_back,
        "other_rate": _rate(rest_back, rest),
    }


def _rate(hits: int, total: int) -> dict[str, float]:
    """A share with its 95% Wilson interval."""
    if not total:
        return {"value": float("nan"), "low": float("nan"), "high": float("nan")}
    p = hits / total
    z = 1.96
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return {"value": p, "low": centre - half, "high": centre + half}


def ablation_report(
    library: Library,
    cutoffs: Sequence[datetime],
    horizon: timedelta,
    top_k: Sequence[int],
    include_rejected: bool = False,
) -> dict[str, Any]:
    """Switch the optional inputs and the weights of the two unmeasured features on and off.

    `off` is v2 without exports and proper nouns. Each variant is compared with `off` on the same words.
    Names are mostly words the optimizer rejected, so `include_rejected` matters for the proper-noun result.
    Exports come from the library's destination rows; for the author's library that is the one Obsidian
    reconcile, a proxy for "the word had a card".
    """
    base = DEFAULT_WEIGHTS
    rankers: dict[str, Ranker] = {
        "off": v2_variant(),
        "exports": v2_variant(exports=True),
        "proper": v2_variant(proper_nouns=True),
        "both": v2_variant(exports=True, proper_nouns=True),
        # Other absolute weights (the default is `after_export` +1.0 and `proper_noun` -1.5).
        "exports_w0.5": v2_variant(replace(base, after_export=0.5), exports=True),
        "exports_w2": v2_variant(replace(base, after_export=2.0), exports=True),
        "exports_w3": v2_variant(replace(base, after_export=3.0), exports=True),
        "proper_w-0.75": v2_variant(replace(base, proper_noun=-0.75), proper_nouns=True),
        "proper_w-3": v2_variant(replace(base, proper_noun=-3.0), proper_nouns=True),
    }
    groups = score_groups(library, cutoffs, horizon, rankers, min_positives=MIN_POSITIVES, include_rejected=include_rejected)
    present = dict.fromkeys(
        ("words", "back", "exported", "looked_up_after_export", "after_export_back", "proper_noun", "proper_noun_back"), 0
    )
    for cutoff in cutoffs:
        for example in build_examples(library, cutoff, horizon, include_rejected):
            present["words"] += 1
            present["back"] += example.needed_again
            present["exported"] += example.exported_at is not None
            again = example.exported_at is not None and any(when > example.exported_at for when, _ in example.history)
            present["looked_up_after_export"] += again
            present["after_export_back"] += again and example.needed_again
            present["proper_noun"] += example.proper_noun
            present["proper_noun_back"] += example.proper_noun and example.needed_again
    return {
        "cutoffs": len(groups),
        "inputs_present": present,
        "levels": compare_rankers(groups, list(rankers), top_k),
        "versus_off": {name: compare_to(groups, name, "off", top_k) for name in rankers if name != "off"},
    }


def newcomer_report(
    library: Library,
    horizon: timedelta,
    top_k: Sequence[int],
    first_books: int | None = None,
    first_days: float | None = None,
    step_days: float = 7.0,
    start_days: float = 14.0,
    only_books: Collection[str] | None = None,
) -> dict[str, Any]:
    """The ranking for a reader who has only some books or the first weeks of the library."""
    cut = restrict_library(library, first_books, first_days, only_books)
    if not cut.lookups:
        return {"lookups": 0, "cutoffs": 0}
    cutoffs = step_cutoffs(cut, horizon, step_days, start_days)
    rankers = {name: BASELINES[name] for name in ("ranking_v2", "current_score", "lookups", "recency", "frequency")}
    groups = score_groups(cut, cutoffs, horizon, rankers)
    names = list(rankers)
    return {
        "lookups": len(cut.lookups),
        "books": len({item.book_key for item in cut.lookups}),
        "days": (cut.last_lookup - cut.first_lookup).days,
        "cutoffs": len(groups),
        "words_per_cutoff": [len(group.labels) for group in groups],
        "positives_per_cutoff": [sum(group.labels) for group in groups],
        "levels": compare_rankers(groups, names, top_k) if groups else {},
        "v2_minus_current": compare_to(groups, "ranking_v2", "current_score", top_k) if groups else {},
        # The first sync: what the newcomer sees once everything in the window is looked up.
        "shelves": shelf_counts(cut),
    }


def collapse_repeats(library: Library) -> Library:
    """The library as a source without repeat lookups would have kept it: one lookup per word, the first."""
    seen: set[str] = set()
    kept = []
    for item in sorted(library.lookups, key=lambda looked: (looked.at, looked.lexeme_id)):
        if item.lexeme_id not in seen:
            seen.add(item.lexeme_id)
            kept.append(item)
    return Library(lookups=kept, lexical=library.lexical)


BLIND_RANKERS = ("ranking_learning", "ranking_v2", "current_score", "lookups", "recency", "frequency")


def blind_report(
    features: Library,
    outcome: Library | None,
    horizon: timedelta,
    top_k: Sequence[int],
    first_days: float | None = None,
    step_days: float = 7.0,
    start_days: float = 14.0,
    rankers: Sequence[str] = BLIND_RANKERS,
    minimum_positives: int = 3,
) -> dict[str, Any]:
    """Rankings that see only the first lookup of each word, judged by the repeats the full library does have.

    A reader whose source keeps no repeat lookups has no "came back" label, so there is nothing to measure on
    their own history. This is the proxy: `features` is the library collapsed to first lookups (what such a source
    would hold), `outcome` is the same library with its repeats (None means `features` itself, so the repeats
    are the ones the source really kept). The label is then "looked up again within the window", as everywhere
    else. It is weak evidence: the reader who repeated words is the same reader, and a source without repeats
    would simply never tell the product that a word came back.
    """
    view = restrict_library(features, first_days=first_days)
    if not view.lookups:
        return {"lookups": 0, "cutoffs": 0}
    truth = restrict_library(outcome, first_days=first_days) if outcome is not None else None
    cutoffs = step_cutoffs(truth or view, horizon, step_days, start_days)
    groups = score_groups(
        view, cutoffs, horizon, {name: BASELINES[name] for name in rankers}, min_positives=minimum_positives, outcome=truth
    )
    names = list(rankers)
    return {
        "lookups": len(view.lookups),
        "days": (view.last_lookup - view.first_lookup).days,
        "cutoffs": len(groups),
        "words_per_cutoff": [len(group.labels) for group in groups],
        "positives_per_cutoff": [sum(group.labels) for group in groups],
        "levels": compare_rankers(groups, names, top_k) if groups else {},
        "learning_minus": {
            name: compare_to(groups, "ranking_learning", name, top_k) for name in names if name != "ranking_learning"
        }
        if groups
        else {},
    }


def evaluate(
    library: Library,
    cutoffs: Sequence[datetime],
    horizon: timedelta = timedelta(days=DEFAULT_HORIZON_DAYS),
    top_k: Sequence[int] = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Score every ranker at every cutoff.

    The learned ranker at a cutoff is trained on the examples one window
    earlier, whose outcome was already known on the cutoff date.
    """
    rounds = []
    for cutoff in cutoffs:
        examples = build_examples(library, cutoff, horizon)
        positives = sum(1 for example in examples if example.needed_again)
        if positives < MIN_POSITIVES:
            logger.info("Skipping cutoff %s: %d positives", cutoff.date(), positives)
            continue
        rankers: dict[str, Ranker] = dict(BASELINES)
        model = None
        training = build_examples(library, cutoff - horizon, horizon)
        if sum(1 for example in training if example.needed_again) >= MIN_POSITIVES:
            model = LogisticModel.fit(training)
            rankers["learned"] = model.score
        rounds.append({
            "cutoff": cutoff.date().isoformat(),
            "words": len(examples),
            "needed_again": positives,
            "base_rate": positives / len(examples),
            "results": {name: _as_dict(score_ranker(examples, ranker, top_k)) for name, ranker in rankers.items()},
            "learned_weights": dict(zip(FEATURE_NAMES, model.weights, strict=True)) if model else None,
        })
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "horizon_days": horizon.days,
        "top_k": list(top_k),
        "rounds": rounds,
        "summary": _summary(rounds, top_k),
    }


def _as_dict(result: RankerResult) -> dict[str, Any]:
    return {
        "auc": result.auc,
        "auc_interval": list(result.auc_interval),
        "precision": {str(k): value for k, value in result.precision.items()},
        "precision_interval": {str(k): list(value) for k, value in result.precision_interval.items()},
    }


def _summary(rounds: Sequence[dict[str, Any]], top_k: Sequence[int]) -> dict[str, Any]:
    """Mean of each metric over the rounds where every ranker ran, so rankers compare fairly."""
    names = sorted({name for item in rounds for name in item["results"]})
    common = [item for item in rounds if all(name in item["results"] for name in names)]
    summary: dict[str, Any] = {}
    for name in names:
        used = common or [item for item in rounds if name in item["results"]]
        runs = [item["results"][name] for item in used]
        summary[name] = {
            "rounds": len(runs),
            "auc": _mean(run["auc"] for run in runs),
            "precision": {str(k): _mean(run["precision"][str(k)] for run in runs) for k in top_k},
            "lift": {
                str(k): _mean(item["results"][name]["precision"][str(k)] / item["base_rate"] for item in used)
                for k in top_k
            },
        }
    return summary


def _mean(values: Any) -> float:
    items = [value for value in values if not math.isnan(value)]
    return sum(items) / len(items) if items else float("nan")


def format_report(report: dict[str, Any]) -> str:
    top_k = report["top_k"]
    lines = [f"Window after each cutoff: {report['horizon_days']} days"]
    for item in report["rounds"]:
        lines.append(
            f"  {item['cutoff']}: {item['words']} words, {item['needed_again']} needed again "
            f"({item['base_rate']:.0%})"
        )
    header = f"{'ranker':15} {'rounds':>6} {'AUC':>6}" + "".join(f" {'P@' + str(k):>6} {'lift':>5}" for k in top_k)
    lines += ["", header]
    for name, row in sorted(report["summary"].items(), key=lambda pair: -pair[1]["auc"]):
        cells = "".join(f" {row['precision'][str(k)]:6.2f} {row['lift'][str(k)]:5.1f}" for k in top_k)
        lines.append(f"{name:15} {row['rounds']:6d} {row['auc']:6.3f}{cells}")
    k = top_k[0]
    lines += ["", f"Per cutoff: AUC [95% interval], P@{k} [interval], lift"]
    for item in report["rounds"]:
        lines.append(f"  {item['cutoff']}")
        for name, result in sorted(item["results"].items(), key=lambda pair: -pair[1]["auc"]):
            low, high = result["auc_interval"]
            p_low, p_high = result["precision_interval"][str(k)]
            precision = result["precision"][str(k)]
            lines.append(
                f"    {name:15} {result['auc']:.3f} [{low:.3f}-{high:.3f}]  "
                f"{precision:.2f} [{p_low:.2f}-{p_high:.2f}]  {precision / item['base_rate']:.1f}"
            )
    lines.append("")
    lines.append("AUC 0.5 is random order; lift is precision divided by the share of words needed again.")
    lines.append(
        "ranking_v2 is in-sample: its default weights were derived from these same cutoffs, "
        "so its numbers are optimistic."
    )
    return "\n".join(lines)


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _json_safe(value: Any) -> Any:
    """Strict JSON has no NaN; an undefined metric (one class only) becomes null."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def format_extras(extras: dict[str, Any], top_k: Sequence[int]) -> str:
    """Plain-text tables for the newcomer, ablation and too_basic sections."""
    lines: list[str] = []
    for title, key in (("Newcomer replay", "newcomer"),):
        section = extras.get(key)
        if not section:
            continue
        lines.append(
            f"{title}: {section['lookups']} lookups, {section['books']} books, {section['days']} days, "
            f"{section['cutoffs']} cutoffs"
        )
        if not section["cutoffs"]:
            lines.append("  no cutoff has enough words looked up again")
            continue
        lines.append(f"  words per cutoff {section['words_per_cutoff']}, needed again {section['positives_per_cutoff']}")
        lines += _level_table(section["levels"], top_k)
        delta = section["v2_minus_current"]
        lines.append(f"  v2 - current_score: AUC {_fmt(delta['auc'], signed=True)}"
                     + "".join(f", lift@{k} {_fmt(delta['lift'][str(k)], signed=True)}" for k in top_k))
        shelves = section["shelves"]
        lines.append(f"  first sync: {shelves['words']} words, shelves {shelves['shelves']}, "
                     f"disputed {shelves['disputed_share']:.1%}")
    blind = extras.get("no_repeats")
    if blind:
        lines.append(
            f"First lookups only (proxy, weak evidence): {blind['lookups']} lookups, {blind['days']} days, "
            f"{blind['cutoffs']} cutoffs"
        )
        if not blind["cutoffs"]:
            lines.append("  no cutoff has enough words looked up again")
        else:
            lines.append(f"  words per cutoff {blind['words_per_cutoff']}, came back {blind['positives_per_cutoff']}")
            lines += _level_table(blind["levels"], top_k)
            for name, delta in blind["learning_minus"].items():
                lines.append(f"  learning - {name:13} AUC {_fmt(delta['auc'], signed=True)}"
                             + "".join(f"  lift@{k} {_fmt(delta['lift'][str(k)], signed=True)}" for k in top_k))
    ablation = extras.get("ablation")
    if ablation:
        lines += ["", f"Ablation over {ablation['cutoffs']} cutoffs; inputs present: {ablation['inputs_present']}"]
        lines += _level_table(ablation["levels"], top_k)
        lines.append("  difference against 'off' (paired, 95% interval)")
        for name, delta in ablation["versus_off"].items():
            lines.append(f"    {name:13} AUC {_fmt(delta['auc'], signed=True)}"
                         + "".join(f"  lift@{k} {_fmt(delta['lift'][str(k)], signed=True)}" for k in top_k))
    basic = extras.get("too_basic")
    if basic:
        hidden, rest = basic["not_worth_rate"], basic["other_rate"]
        lines.append("")
        lines.append(
            f"too_basic: {basic['flagged']} word-cutoffs flagged, {basic['not_worth']} on not_worth, "
            f"{basic['not_worth_back']} looked up again; shelves {basic['flagged_shelves']}"
        )
        lines.append(
            f"  back within the window: {_pct(hidden)} on not_worth vs {_pct(rest)} for the other "
            f"{basic['other_words']} words"
        )
    return "\n".join(lines)


def _level_table(levels: dict[str, Any], top_k: Sequence[int]) -> list[str]:
    lines = []
    for name, row in levels.items():
        lines.append(
            f"  {name:14} AUC {_fmt(row['auc'])}"
            + "".join(f"  lift@{k} {_fmt(row['lift'][str(k)])}" for k in top_k)
        )
    return lines


def _fmt(estimate: dict[str, float], signed: bool = False) -> str:
    sign = "+" if signed else ""
    return f"{estimate['value']:{sign}.3f} [{estimate['low']:{sign}.3f}..{estimate['high']:{sign}.3f}]"


def _pct(rate: dict[str, float]) -> str:
    return f"{rate['value']:.1%} [{rate['low']:.1%}..{rate['high']:.1%}]"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path(".app-data") / DATABASE_FILENAME)
    parser.add_argument("--reader-file", type=Path, help="evaluate a KOReader, Kobo or Kindle words file instead")
    parser.add_argument("--horizon", type=_positive, default=DEFAULT_HORIZON_DAYS, help="days after a cutoff")
    parser.add_argument("--top", type=_positive, nargs="+", default=list(DEFAULT_TOP_K))
    parser.add_argument("--out", type=Path, default=Path(".app-data") / "ranking_eval")
    parser.add_argument("--newcomer", action="store_true", help="evaluate with only the first books / days of history")
    parser.add_argument("--first-books", type=_positive, help="with --newcomer: keep the first N books")
    parser.add_argument("--first-days", type=_positive, help="with --newcomer: keep the first N days of lookups")
    parser.add_argument("--step-days", type=_positive, default=7, help="with --newcomer: days between cutoffs")
    parser.add_argument("--start-days", type=_positive, default=14, help="with --newcomer: first cutoff, in days")
    parser.add_argument("--ablation", action="store_true", help="switch exports and proper nouns on and off")
    parser.add_argument("--include-rejected", action="store_true", help="with --ablation: also rank rejected words")
    parser.add_argument(
        "--no-repeats",
        action="store_true",
        help="rank as a source without repeat lookups would see the library; judge by the repeats it really has",
    )
    parser.add_argument("--too-basic", action="store_true", help="how often too_basic words are looked up again")
    args = parser.parse_args(argv)
    source = args.reader_file or args.db
    if not source.exists():
        print(f"Library not found: {source}", file=sys.stderr)
        return 2
    # Skipped cutoffs and timings go to the run's log; stdout keeps only the report.
    configure_logging(args.out / "logs", console=True)
    library = load_reader_library(source) if args.reader_file else load_library(source)
    if not library.lookups:
        print("The library has no lookups to evaluate.", file=sys.stderr)
        return 2
    horizon = timedelta(days=args.horizon)
    if args.newcomer or args.ablation or args.too_basic or args.no_repeats:
        extras: dict[str, Any] = {}
        if args.no_repeats:
            extras["no_repeats"] = blind_report(
                collapse_repeats(library), library, horizon, args.top, args.first_days, args.step_days, args.start_days
            )
        if args.newcomer:
            extras["newcomer"] = newcomer_report(
                library, horizon, args.top, args.first_books, args.first_days, args.step_days, args.start_days
            )
        cutoffs = default_cutoffs(library, horizon)
        if args.ablation:
            extras["ablation"] = ablation_report(library, cutoffs, horizon, args.top, args.include_rejected)
        if args.too_basic:
            extras["too_basic"] = too_basic_recall(library, cutoffs, horizon)
        print(format_extras(extras, args.top))
        path = args.out / f"extras-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(_json_safe(extras), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"\nSaved {path}")
        return 0
    cutoffs = default_cutoffs(library, horizon)
    if not cutoffs:
        print("Not enough history yet: no cutoff has a full window of later lookups.", file=sys.stderr)
        return 1
    report = evaluate(library, cutoffs, horizon, args.top)
    if not report["rounds"]:
        print(
            f"Every cutoff had fewer than {MIN_POSITIVES} words looked up again; read more and try later.",
            file=sys.stderr,
        )
        return 1
    print(format_report(report))
    path = args.out / f"report-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"\nSaved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
