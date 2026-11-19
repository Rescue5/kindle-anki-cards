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
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from wordfreq import zipf_frequency

from kindle_vocab_app.library_repository import DATABASE_FILENAME
from kindle_vocab_app.logging_config import configure_logging, get_logger
from kindle_vocab_app.ranking import WordFacts, rank
from kindle_vocab_app.vocab_optimizer import (
    SPECIALIZED_LEXNAMES,
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
        lookups = []
        for row in connection.execute("SELECT lexeme_id, book_key, looked_up_at FROM occurrences"):
            at = parse_timestamp(row["looked_up_at"])
            if at is not None:
                lookups.append(Lookup(str(row["lexeme_id"]), str(row["book_key"] or ""), at))
        # Rejected analyses keep their payload too; their warnings are what got them rejected.
        payloads = {
            str(row["lexeme_id"]): row["payload_json"]
            for row in connection.execute(
                "SELECT lexeme_id, payload_json FROM analyses WHERE payload_json IS NOT NULL AND payload_json != ''"
            )
        }
        lexical = {
            str(row["id"]): _lexical(str(row["display_form"] or ""), payloads.get(str(row["id"])))
            for row in connection.execute("SELECT id, display_form FROM lexemes")
        }
    logger.info("Loaded ranking evaluation data lookups=%d lexemes=%d", len(lookups), len(lexical))
    return Library(lookups=lookups, lexical=lexical)


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
) -> list[Example]:
    """One example per lexeme looked up before the cutoff; nothing after it leaks in.

    Words the optimizer rejected are left out by default, as the app never ranks them.
    """
    before: dict[str, list[Lookup]] = defaultdict(list)
    needed: set[str] = set()
    reading: set[str] = set()
    for item in library.lookups:
        if item.at < cutoff:
            before[item.lexeme_id].append(item)
            if item.at >= cutoff - timedelta(days=READING_DAYS):
                reading.add(item.book_key)
        elif item.at < cutoff + horizon:
            needed.add(item.lexeme_id)
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
    """Ranking v2 with its shipped default weights; nothing is fitted per cutoff."""
    return rank(word_facts(example), _moment(example)).score


def word_facts(example: Example) -> WordFacts:
    """What the app would know about the word at the cutoff.

    Exports and the reader's decisions are not part of the history yet, and
    proper nouns are not stored in analyses, so they stay empty here.
    """
    lexical = example.lexical
    return WordFacts(
        lemma_zipf=lexical.lemma_zipf,
        form_zipf=lexical.form_zipf,
        synset_count=lexical.synset_count,
        pos_count=lexical.pos_count,
        warnings=lexical.warnings,
        proper_noun=False,
        lookups=example.history or _synthetic_history(example),
        reading_books=example.reading_books,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path(".app-data") / DATABASE_FILENAME)
    parser.add_argument("--horizon", type=_positive, default=DEFAULT_HORIZON_DAYS, help="days after a cutoff")
    parser.add_argument("--top", type=_positive, nargs="+", default=list(DEFAULT_TOP_K))
    parser.add_argument("--out", type=Path, default=Path(".app-data") / "ranking_eval")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"Library not found: {args.db}", file=sys.stderr)
        return 2
    # Skipped cutoffs and timings go to the run's log; stdout keeps only the report.
    configure_logging(args.out / "logs", console=True)
    library = load_library(args.db)
    if not library.lookups:
        print("The library has no lookups to evaluate.", file=sys.stderr)
        return 2
    horizon = timedelta(days=args.horizon)
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
