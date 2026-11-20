"""A synthetic newcomer library for testing the ranking without anybody's real vocabulary.

A reader with one or two books, a few hundred lookups over about three months. Words are invented
pseudo-words (pronounceable, never English) plus a short list of common English words and a few
capitalised names; their frequency and dictionary facts are set here, so nothing depends on the
`wordfreq` data or on WordNet. A planted "needed again" process decides which words come back: a
share of the pseudo-words is sticky and is looked up again a few times, mostly within weeks, across
the two books when their reading overlaps; the rest is looked up once, with a rare accidental
repeat. The same seed always gives the same library.

`write_koreader` and `write_kobo` save it as `vocabulary_builder.sqlite3` and `KoboReader.sqlite` in
the shapes `reader_sources` reads. This is a regression fixture for the evaluation path, not
evidence that the ranking generalises: the planted process was written to match the model's own
assumptions.
"""

from __future__ import annotations

import random
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kindle_vocab_app.ranking_eval import Lexical

SEED = 20261119
START = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
DAYS = 90
BOOKS = ("Synthetic Book A", "Synthetic Book B")
# Book B is picked up around day 45; both are read for a while after that.
SECOND_BOOK_FROM = 45
OVERLAP_UNTIL = 65

# Common English words with an approximate Zipf frequency (fixed here, not read from wordfreq).
COMMON_WORDS = (
    ("remember", 5.3), ("window", 5.2), ("whisper", 4.7), ("journey", 5.0), ("promise", 5.2),
    ("silence", 5.0), ("wander", 4.2), ("tremble", 4.0), ("ordinary", 4.9), ("gesture", 4.6),
    ("anxious", 4.5), ("hesitate", 4.3), ("shadow", 5.0), ("measure", 5.1), ("distant", 4.8),
    ("reluctant", 4.2), ("glance", 4.6), ("pretend", 4.9), ("sudden", 5.0), ("careful", 5.1),
    ("mention", 5.0), ("remark", 4.5), ("settle", 4.9), ("slight", 4.7), ("weary", 4.1),
    ("honest", 5.1), ("breathe", 4.9), ("borrow", 4.6), ("faint", 4.4), ("neighbour", 4.6),
)
NAMES = ("Marlenta", "Orvik", "Selwen", "Dravin", "Tolmar", "Ysanne", "Brecht", "Halvar")
GLUED = ("nevertheless", "whatsoever")

_ONSETS = ("b", "br", "c", "ch", "d", "dr", "f", "fl", "g", "gr", "k", "l", "m", "n", "p", "pl", "r", "s", "sk", "st", "t", "tr", "v", "z")
_VOWELS = ("a", "e", "i", "o", "u", "ai", "ou")
_CODAS = ("", "l", "m", "n", "r", "s", "th", "nd", "rt")


@dataclass(frozen=True)
class SyntheticLookup:
    word: str
    book: int
    at: datetime
    prev_context: str
    next_context: str


@dataclass
class SyntheticLibrary:
    lookups: list[SyntheticLookup]
    # Facts of each word by lowercased word, in the shape `ranking_eval` wants.
    lexical: dict[str, Lexical]


def generate(seed: int = SEED, pseudo_words: int = 320) -> SyntheticLibrary:
    """The same seed always gives the same library (about 500-600 lookups with the defaults)."""
    rng = random.Random(seed)
    lexical: dict[str, Lexical] = {}
    lookups: list[SyntheticLookup] = []

    def add(word: str, zipf: float, first_day: float, extra: int, **facts: object) -> None:
        lexical[word.casefold()] = _lexical(word, zipf, **facts)
        day = first_day
        for index in range(1 + extra):
            if day >= DAYS:
                break
            lookups.append(_lookup(rng, word, day))
            # Repeats come within a few weeks of the previous lookup.
            day += rng.expovariate(1 / 9.0) + 0.3
            if index > 8:
                break

    for word in _pseudo_words(rng, pseudo_words, {w for w, _ in COMMON_WORDS}):
        zipf = rng.uniform(2.2, 4.4)
        # Words in the usual band stick more often than the very rare ones.
        sticky = rng.random() < (0.3 if zipf >= 3.0 else 0.15)
        extra = 1 + _geometric(rng, 0.45) if sticky else int(rng.random() < 0.08)
        add(word, zipf, rng.uniform(0, DAYS - 1), extra, synsets=rng.randint(1, 6))
    for word, zipf in COMMON_WORDS:
        add(word, zipf, rng.uniform(0, DAYS - 1), int(rng.random() < 0.1), synsets=rng.randint(2, 8))
    for word in NAMES:
        add(word, 0.0, rng.uniform(0, DAYS - 1), 0, synsets=0, warnings={"unknown_to_local_lexicons"}, accepted=False)
    for word in GLUED:
        add(word, 3.4, rng.uniform(0, DAYS - 1), 0, synsets=0, warnings={"possibly_glued_words"}, accepted=False)

    lookups.sort(key=lambda item: (item.at, item.word))
    return SyntheticLibrary(lookups, lexical)


def write_koreader(library: SyntheticLibrary, path: Path, repeats: bool = True) -> None:
    """`vocabulary_builder.sqlite3`. With `repeats=False` each word keeps only its first lookup."""
    lookups = library.lookups if repeats else _first_of(library.lookups, per_book=False)
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE title (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, filter INTEGER NOT NULL DEFAULT 1)")
        connection.execute(
            "CREATE TABLE vocabulary (word TEXT NOT NULL, in_context TEXT, create_time INTEGER NOT NULL, "
            "review_time INTEGER, due_time INTEGER NOT NULL DEFAULT 0, review_count INTEGER NOT NULL DEFAULT 0, "
            "prev_context TEXT, next_context TEXT, title_id INTEGER, streak_count INTEGER NOT NULL DEFAULT 0)"
        )
        connection.executemany("INSERT INTO title (id, name) VALUES (?, ?)", list(enumerate(BOOKS, start=1)))
        connection.executemany(
            "INSERT INTO vocabulary (word, create_time, prev_context, next_context, title_id) VALUES (?, ?, ?, ?, ?)",
            [(item.word, int(item.at.timestamp()), item.prev_context, item.next_context, item.book + 1) for item in lookups],
        )
        connection.commit()


def write_kobo(library: SyntheticLibrary, path: Path, repeats: bool = True) -> None:
    """`KoboReader.sqlite`. With `repeats=False` each word keeps its first lookup per book."""
    lookups = library.lookups if repeats else _first_of(library.lookups, per_book=True)
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE content (ContentID TEXT PRIMARY KEY, Title TEXT, Attribution TEXT)")
        connection.execute(
            "CREATE TABLE WordList (Text TEXT, VolumeId TEXT, DictSuffix TEXT, DateCreated TEXT)"
        )
        connection.executemany(
            "INSERT INTO content VALUES (?, ?, ?)",
            [(f"synthetic-volume-{index}", title, "Synthetic Author") for index, title in enumerate(BOOKS)],
        )
        connection.executemany(
            "INSERT INTO WordList VALUES (?, ?, ?, ?)",
            [
                (item.word, f"synthetic-volume-{item.book}", "-en", item.at.replace(tzinfo=None).isoformat(timespec="seconds"))
                for item in lookups
            ],
        )
        connection.commit()


def _first_of(lookups: list[SyntheticLookup], per_book: bool) -> list[SyntheticLookup]:
    seen: set[tuple[str, int]] = set()
    kept = []
    for item in sorted(lookups, key=lambda looked: looked.at):
        key = (item.word.casefold(), item.book if per_book else 0)
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept


def _lexical(
    word: str,
    zipf: float,
    synsets: int = 1,
    warnings: set[str] | None = None,
    accepted: bool = True,
) -> Lexical:
    return Lexical(
        display_form=word,
        base_form=word.casefold(),
        lemma_zipf=zipf,
        form_zipf=zipf,
        synset_count=synsets,
        pos_count=1,
        warnings=frozenset(warnings or ()),
        accepted=accepted,
    )


def _lookup(rng: random.Random, word: str, day: float) -> SyntheticLookup:
    at = START + timedelta(days=int(day), hours=rng.uniform(0, 14), minutes=rng.randint(0, 59))
    if int(day) < SECOND_BOOK_FROM:
        book = 0
    elif int(day) < OVERLAP_UNTIL:
        book = rng.randint(0, 1)
    else:
        book = 1
    return SyntheticLookup(word, book, at.replace(microsecond=0, second=0), "She said it was", "and nothing more. Then it was quiet.")


def _geometric(rng: random.Random, p: float) -> int:
    count = 0
    while rng.random() > p and count < 6:
        count += 1
    return count


def _pseudo_words(rng: random.Random, count: int, taken: set[str]) -> list[str]:
    words: list[str] = []
    seen = set(taken)
    while len(words) < count:
        syllables = rng.randint(2, 3)
        word = "".join(rng.choice(_ONSETS) + rng.choice(_VOWELS) + rng.choice(_CODAS) for _ in range(syllables))
        if word not in seen and 5 <= len(word) <= 10:
            seen.add(word)
            words.append(word)
    return words
