"""Offline RP-V2 coverage lookup for a local or internal portable workspace."""

from __future__ import annotations

import logging
import re
import sqlite3
import sys
import unicodedata
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from .contracts import StudyPriority

MODEL_FILENAME = "rp-v2-coverage.sqlite"
EXPANDED_MODEL_FILENAME = "rp-v2-expanded.sqlite"
SCHEMA_VERSION = 1
SOURCE_SHA256 = "d75e5ba0b3cd3a21f449955b627e48f9344b95a9ad1694f2d2c7c4956f24e686"
EXPANDED_SOURCE_SHA256 = frozenset({
    "952f50b48899fa4e8fc34a85c8997a16f8e623ae97d589ca0a6ce180f307b842",  # 1,022 CONLIT novels
    "60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db",  # plus Bury the Survivors
})
_EXACT_THRESHOLDS = tuple(map(Fraction, ("0.75", "0.50", "1/3", "0.20", "0.10", "0.05", "0.02", "0.005")))
THRESHOLDS = tuple(map(float, _EXACT_THRESHOLDS))
_TOKEN = re.compile(r"[a-z]+(?:['-][a-z]+)*")
_TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-"})
_LOGGER = logging.getLogger(__name__)


def model_path(workspace: Path, filename: str = MODEL_FILENAME) -> Path:
    return workspace / ".app-data" / "models" / filename


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(_TYPOGRAPHY).lower()
    return " ".join(normalized.split())


def _pending(reason: str) -> StudyPriority:
    return {"level": 6, "score": 0.0, "provisional": True, "reason": reason}


def _coverage_level(score: float | Fraction) -> int:
    thresholds = _EXACT_THRESHOLDS if isinstance(score, Fraction) else THRESHOLDS
    return next((level for level, threshold in enumerate(thresholds, 1) if score >= threshold), 9)


def personalized_priority(base: StudyPriority, lookups: Iterable[tuple[datetime, str]]) -> StudyPriority:
    """Use distinct dated Kindle book observations to adjust a fresh RP-V2 result."""
    coverage = None if base["provisional"] or base["level"] == 10 else base["score"]
    result: StudyPriority = {**base, "coverage_score": coverage}
    if base["level"] == 10 or coverage in (0.0, 1.0):
        return result

    episodes = set()
    for moment, key in lookups:
        book = key.strip()
        if not book or book.startswith(("koreader:", "kobo:")) or not isinstance(moment, datetime):
            continue
        try:
            utc = moment.replace(tzinfo=UTC) if moment.utcoffset() is None else moment.astimezone(UTC)
        except (OverflowError, ValueError):
            continue
        episodes.add((utc.date(), book))

    books = len({book for _, book in episodes})
    same = len(episodes) - books
    cross = max(books - 1, 0)
    bonus = min(1.0, 0.25 * same + 0.50 * cross)
    if bonus == 0:
        return result

    if coverage is None:
        result["score"] = bonus
        prefix = "Порядок среди предварительных оценок учитывает "
    else:
        # The stored float's shortest decimal preserves adjacent inputs while making 0.60 exact.
        original = Fraction(str(coverage))
        multiplier = Fraction(1.0 + bonus)
        adjusted = original * multiplier / (1 - original + original * multiplier)
        score = float(adjusted)
        if score <= coverage:
            return result
        result.update(score=score, level=max(base["level"] - 1, _coverage_level(adjusted)))
        prefix = "В оценке также учитываются "

    if same and cross:
        evidence = "поиски в разные дни в одной книге и поиски в разных книгах"
        personal_reason = "Вы искали в разных книгах и возвращались к слову в одной из них в разные дни."
    elif same:
        evidence = "поиски в разные дни в одной книге"
        personal_reason = "Вы искали это слово в одной книге в разные дни."
    else:
        evidence = "поиски в разных книгах"
        personal_reason = "Вы искали в разных книгах."
    result["personal_reason"] = personal_reason
    result["reason"] = f"{base['reason'].rstrip().rstrip('.')}. {prefix}{evidence}."
    return result


class BookCoverage:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def priority(self, spelling: str, lemma: str | None = None) -> StudyPriority:
        form = _normalize(spelling)
        key = _normalize(lemma) if lemma is not None else form
        if not form or not key:
            return _pending("Для книжной оценки нужно непустое написание.")
        if " " in form or " " in key:
            return _pending("Для целого выражения книжный охват не рассчитан.")
        if not _TOKEN.fullmatch(form) or not _TOKEN.fullmatch(key):
            return _pending("Для такого написания книжный охват не рассчитан.")

        row = self._connection.execute(
            "SELECT share FROM coverage WHERE headword = ?", (key,)
        ).fetchone()
        if row is None and lemma is None:
            row = self._connection.execute(
                "SELECT coverage.share FROM aliases JOIN coverage USING (headword) "
                "WHERE aliases.spelling = ?",
                (key,),
            ).fetchone()
        if row is None:
            return _pending("Слова нет в таблице книжного охвата.")
        if row[0] is None:
            return _pending("Слово есть в таблице, но его книжный охват не рассчитан.")

        score = float(row[0])
        percent = f"{score * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        share = "менее чем в 0,01%" if 0 < score < 0.0001 else f"в {percent}%"
        return {
            "level": _coverage_level(score),
            "score": score,
            "provisional": False,
            "reason": f"Слово встречается {share} современных романов выборки "
            "при равном весе авторов.",
        }


@contextmanager
def open_model(workspace: Path) -> Iterator[BookCoverage | None]:
    directories = [model_path(workspace).parent]
    if getattr(sys, "frozen", False):
        directories.append(Path(sys.executable).parent / "models")

    # The bundled expanded table defines the ranking on both fresh and upgraded installations.
    candidates = [
        *((folder / EXPANDED_MODEL_FILENAME, EXPANDED_SOURCE_SHA256) for folder in reversed(directories)),
        *((folder / MODEL_FILENAME, {SOURCE_SHA256}) for folder in directories),
    ]
    for candidate, accepted in candidates:
        if not candidate.is_file():
            continue
        connection = None
        try:
            connection = sqlite3.connect(f"{candidate.resolve().as_uri()}?mode=ro", uri=True)
            connection.execute("BEGIN")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            source = connection.execute("SELECT source_sha256 FROM provenance").fetchone()
            if version != SCHEMA_VERSION or source is None or source[0] not in accepted:
                raise sqlite3.DatabaseError("Unexpected RP-V2 coverage projection")
            connection.execute("SELECT share FROM coverage WHERE 0")
            connection.execute("SELECT spelling, headword FROM aliases WHERE 0")
        except (OSError, sqlite3.Error):
            if connection is not None:
                connection.close()
            _LOGGER.warning("Could not open the RP-V2 book coverage model", exc_info=True)
            continue
        with closing(connection):
            yield BookCoverage(connection)
        return

    yield None
