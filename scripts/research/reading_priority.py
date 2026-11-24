"""Offline, form-level reading-priority experiment using explicitly supplied CSVs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from wordfreq import tokenize, zipf_frequency

BOOK_COUNT = 400
CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
FEATURE_COUNTS = {"frequency": 2, "books": 2, "combined": 4, "combined_cefr": 11}
# Inclusive bounds from tier 1 through tier 8, followed by tier 9.
# These bands are exploratory, shared by the model and descriptive baselines.
TIER_THRESHOLDS = (0.75, 0.50, 1 / 3, 0.20, 0.10, 0.05, 0.02, 0.005)


def _key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


@dataclass(frozen=True)
class Evidence:
    form: str
    books: int | None
    zipf: float
    cefr: str | None


@dataclass(frozen=True)
class EvidenceIndex:
    books: dict[str, int]
    cefr: dict[str, set[tuple[str, str]]]

    def lookup(self, form: str, pos: str | None = None) -> Evidence:
        key = _key(form)
        readings = self.cefr.get(key, set())
        if pos is not None:
            readings = {reading for reading in readings if reading[0] == _key(pos)}
        # Multiple parts of speech or conflicting levels cannot identify a reading.
        level = next(iter(readings))[1] if len(readings) == 1 else None
        # wordfreq otherwise estimates some multi-token strings from their components.
        zipf = zipf_frequency(key, "en") if tokenize(key, "en") == [key] else 0.0
        return Evidence(form=key, books=self.books.get(key), zipf=zipf, cefr=level)


def load_evidence(
    cyp_path: str | Path | None,
    cefr_paths: tuple[str | Path, ...] | list[str | Path] = (),
) -> EvidenceIndex:
    books: dict[str, int] = {}
    if cyp_path is not None:
        with Path(cyp_path).open(encoding="utf-8-sig", newline="") as file:
            rows = csv.DictReader(file)
            if not {"Word", "CD_book_count_raw"} <= set(rows.fieldnames or []):
                raise ValueError("В CYP-LEX нужны колонки Word и CD_book_count_raw.")
            for row in rows:
                form = _key(row["Word"] or "")
                if not form:
                    continue
                count = int(row["CD_book_count_raw"])
                if not 0 <= count <= BOOK_COUNT:
                    raise ValueError(f"Некорректный книжный охват CYP-LEX: {row['Word']!r}.")
                if form in books and books[form] != count:
                    raise ValueError(f"Несовпадающий книжный охват одной формы: {form!r}.")
                books[form] = count

    cefr: dict[str, set[tuple[str, str]]] = {}
    for path in cefr_paths:
        with Path(path).open(encoding="utf-8-sig", newline="") as file:
            rows = csv.DictReader(file)
            if not {"headword", "pos", "CEFR"} <= set(rows.fieldnames or []):
                raise ValueError("В CEFR CSV нужны колонки headword, pos и CEFR.")
            for row in rows:
                form = _key(row["headword"] or "")
                pos = _key(row["pos"] or "")
                level = (row["CEFR"] or "").strip().upper()
                if form and pos and level in CEFR_LEVELS:
                    cefr.setdefault(form, set()).add((pos, level))
    return EvidenceIndex(books=books, cefr=cefr)


def features(evidence: Evidence, variant: str) -> tuple[float, ...]:
    """Fixed feature order. Transforms and sentinels use no fitted statistics."""
    frequency = (evidence.zipf, float(evidence.zipf == 0))
    count = evidence.books
    if count is None:
        books = (0.0, 1.0)
    else:
        books = (math.log((count + 0.5) / (BOOK_COUNT - count + 0.5)), 0.0)
    if variant == "frequency":
        return frequency
    if variant == "books":
        return books
    if variant == "combined":
        return frequency + books
    if variant == "combined_cefr":
        levels = tuple(float(evidence.cefr == level) for level in CEFR_LEVELS)
        return frequency + books + levels + (float(evidence.cefr is None),)
    raise ValueError(f"Неизвестный вариант модели: {variant!r}.")


@dataclass(frozen=True)
class Model:
    variant: str
    intercept: float
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.weights) != FEATURE_COUNTS.get(self.variant):
            raise ValueError("Вариант модели или число весов не совпадает с контрактом признаков.")
        coefficients = (self.intercept, *self.weights)
        if not all(type(value) in {int, float} and math.isfinite(value) for value in coefficients):
            raise ValueError("Все коэффициенты модели должны быть конечными числами.")

    def predict(self, evidence: Evidence) -> float:
        total = math.fsum(
            [self.intercept, *(x * w for x, w in zip(features(evidence, self.variant), self.weights))]
        )
        if total >= 0:
            return 1 / (1 + math.exp(-total))
        exp_total = math.exp(total)
        return exp_total / (1 + exp_total)


def load_model(path: str | Path) -> Model:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return Model(data["variant"], data["intercept"], tuple(data["weights"]))


@dataclass(frozen=True)
class Priority:
    form: str
    pos: str | None
    tier: int
    score: float | None
    provisional: bool
    method: str
    evidence: Evidence
    reasons: tuple[str, ...]


def rank_form(
    index: EvidenceIndex, form: str, pos: str | None = None, model: Model | None = None
) -> Priority:
    # Reject blank input rather than treating it as a captured vocabulary record.
    evidence = index.lookup(form, pos)
    if not evidence.form:
        raise ValueError("Укажите непустую форму.")
    if not any(letter.isalpha() for letter in evidence.form):
        return Priority(form, pos, 10, 0.0, False, "structural", evidence, ("В записи нет букв.",))

    reasons = []
    if evidence.books is None:
        reasons.append("Совпадение формы в CYP-LEX 13+ отсутствует. Охват неизвестен.")
    else:
        reasons.append(
            f"Форма встречается в {evidence.books} из {BOOK_COUNT} книг CYP-LEX 13+."
        )
    if evidence.zipf:
        reasons.append(f"Общая частотность формы по wordfreq: Zipf {evidence.zipf:.2f}.")
    elif len(evidence.form.split()) > 1 or len(tokenize(evidence.form, "en")) > 1:
        reasons.append("Для выражения частотность не оценивалась по отдельным словам.")
    else:
        reasons.append("Общая частотность этой формы в wordfreq неизвестна.")
    if evidence.cefr:
        reasons.append(
            f"В словаре CEFR для формы найден уровень {evidence.cefr}. "
            "Уровень может различаться по значениям."
        )
    else:
        reasons.append("Однозначный уровень CEFR для формы и указанной части речи не найден.")

    usable = {
        "books": evidence.books is not None,
        "frequency": bool(evidence.zipf),
        "combined": evidence.books is not None or bool(evidence.zipf),
        "combined_cefr": evidence.books is not None or bool(evidence.zipf) or bool(evidence.cefr),
    }
    method = "insufficient"
    score = None
    if model is not None and usable[model.variant]:
        method = model.variant
        score = model.predict(evidence)
        reasons.append("Баллы рассчитаны моделью из файла. Границы уровней экспериментальные.")
    elif model is None and evidence.books is not None:
        method = "book_reach"
        score = evidence.books / BOOK_COUNT
        reasons.append("Балл равен доле книг с этой формой. Границы уровней экспериментальные.")
    elif model is None and evidence.zipf:
        method = "general_frequency"
        score = min(evidence.zipf / 9, 1.0)
        reasons.append("Балл равен Zipf, делённому на 9. Границы уровней экспериментальные.")
    if score is None:
        reasons.append("Для выбранного метода недостаточно данных. Приоритет предварительный.")
        return Priority(form, pos, 6, None, True, method, evidence, tuple(reasons))

    reasons.append("Источники описывают форму. Значение в контексте и польза для читателя не измерены.")
    tier = next((tier for tier, threshold in enumerate(TIER_THRESHOLDS, 1) if score >= threshold), 9)
    return Priority(form, pos, tier, score, False, method, evidence, tuple(reasons))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forms", nargs="*", help="Формы слов или выражений.")
    parser.add_argument("--entry", nargs=2, action="append", default=[], metavar=("FORM", "POS"),
                        help="Форма и часть речи из CEFR-J, например present verb.")
    parser.add_argument("--cyp", type=Path, help="CSV CYP-LEX 13+.")
    parser.add_argument("--cefr", type=Path, action="append", default=[], help="CSV CEFR.")
    parser.add_argument("--model", type=Path, help="JSON с variant, intercept и weights.")
    args = parser.parse_args()
    if not args.forms and not args.entry:
        parser.error("Укажите хотя бы одну форму.")

    try:
        index = load_evidence(args.cyp, args.cefr)
        model = load_model(args.model) if args.model is not None else None
        priorities = [rank_form(index, form, model=model) for form in args.forms]
        priorities.extend(rank_form(index, form, pos, model) for form, pos in args.entry)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))

    # Without a model, prioritize book evidence and keep frequency-only fallbacks
    # together. The two descriptive scores have different units.
    method_order = {"general_frequency": 1, "insufficient": 2, "structural": 3}
    priorities.sort(
        key=lambda row: (
            method_order.get(row.method, 0),
            row.tier,
            -(row.score or 0.0),
            row.evidence.form,
            row.pos or "",
        )
    )
    print(json.dumps([asdict(row) for row in priorities], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
