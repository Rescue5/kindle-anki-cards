"""Offline ranking with separately measured reading reach and human usefulness."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from collections.abc import Collection
from dataclasses import asdict, dataclass
from pathlib import Path

from wordfreq import tokenize

from .reading_priority import (
    FEATURE_COUNTS,
    TIER_THRESHOLDS,
    Evidence,
    EvidenceIndex,
    Model,
    _key,
    features,
    load_evidence,
    load_model,
    rank_form,
)

# The 30 items in Wang et al.'s published catch_trials.txt.
DEFAULT_CONTROLS = frozenset(
    (
        "because", "monetary system", "eightfold", "herring", "entrancingly", "stotinka",
        "i am", "utterance", "philosophic", "affront", "gamble on", "witenagemot",
        "happy", "anecdotic", "crystallization", "boating", "fairground ride", "savo finnish",
        "ask a question", "check mark", "unclouded", "multimedia system", "top edge", "yataghan",
        "help me", "tinkling", "curb", "bamboo shoot", "make hay", "crissal thrasher",
    )
)


def load_utilities(
    tsv: str | Path, controls: Collection[str] = DEFAULT_CONTROLS
) -> dict[str, float]:
    """Read unique form-level human ratings from the Word and Utility columns."""
    excluded = {_key(word) for word in controls}
    counts: Counter[str] = Counter()
    values: dict[str, float] = {}
    with Path(tsv).open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        if not {"Word", "Utility"} <= set(rows.fieldnames or []):
            raise ValueError("В TSV оценок нужны колонки Word и Utility.")
        for row in rows:
            key = _key(row["Word"] or "")
            if not key or key in excluded:
                continue
            counts[key] += 1
            value = (row["Utility"] or "").strip()
            if not value:
                continue
            utility = float(value)
            if not math.isfinite(utility) or not 0 <= utility <= 1:
                raise ValueError(f"Оценка Utility вне диапазона [0, 1]: {key!r}.")
            values[key] = utility
    return {key: value for key, value in values.items() if counts[key] == 1}


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


@dataclass(frozen=True)
class UtilityModel:
    feature_variant: str
    weights: tuple[float, ...]
    intercept: float
    residual_scale: float
    residual_cap: float
    strength: float

    def __post_init__(self) -> None:
        if self.feature_variant != "combined_cefr" or len(self.weights) != FEATURE_COUNTS[
            "combined_cefr"
        ]:
            raise ValueError("Артефакт Utility должен использовать combined_cefr.")
        coefficients = (
            self.intercept, self.residual_scale, self.residual_cap, self.strength, *self.weights
        )
        if not all(type(value) in {int, float} and math.isfinite(value) for value in coefficients):
            raise ValueError("Все параметры Utility должны быть конечными числами.")
        if (
            self.residual_scale < 0
            or not 0 <= self.residual_cap <= 0.10
            or not 0 <= self.strength <= 0.50
        ):
            raise ValueError("Допустимы residual_scale ≥ 0, cap от 0 до 0,10 и strength от 0 до 0,50.")

    def predict(self, evidence: Evidence) -> float:
        values = features(evidence, self.feature_variant)
        return _clip(self.intercept + math.fsum(value * weight for value, weight in zip(values, self.weights)))

    def adjustment(self, observed: float, expected: float) -> float:
        # Scale is an artifact diagnostic. It does not rescale the bounded residual.
        return self.strength * _clip(observed - expected, -self.residual_cap, self.residual_cap)


def load_utility_model(path: str | Path, strength: float | None = None) -> UtilityModel:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return UtilityModel(
        data["feature_variant"], tuple(data["weights"]), data["intercept"],
        data["residual_scale"], data["residual_cap"],
        data["strength"] if strength is None else strength,
    )


@dataclass(frozen=True)
class Reference:
    books: int
    counts: dict[str, int]
    unseen_single_rate: float
    scope: str

    def __post_init__(self) -> None:
        if type(self.books) is not int or self.books < 1:
            raise ValueError("В reference books должно быть положительным целым числом.")
        if type(self.unseen_single_rate) not in {float, int} or not 0 <= self.unseen_single_rate <= 1:
            raise ValueError("В reference unseen_single_rate должна быть долей от 0 до 1.")
        if not isinstance(self.scope, str) or not self.scope.strip():
            raise ValueError("В reference укажите книги и объём обрабатываемых текстов в scope.")
        if not isinstance(self.counts, dict) or any(
            not form or form != _key(form) or type(count) is not int or not 0 <= count <= self.books
            for form, count in self.counts.items()
        ):
            raise ValueError("В reference нужны нормализованные формы и целые числа книг.")


def load_reference(path: str | Path) -> Reference:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return Reference(data["books"], data["counts"], data["unseen_single_rate"], data["scope"])


@dataclass(frozen=True)
class StudyValue:
    form: str
    pos: str | None
    tier: int
    score: float | None
    provisional: bool
    method: str
    evidence: Evidence
    reading_score: float | None
    human_utility: float | None
    expected_utility: float | None
    adjustment: float | None
    reasons: tuple[str, ...]


def score_form(
    index: EvidenceIndex,
    form: str,
    reading_model: Model,
    frequency_model: Model,
    utilities: dict[str, float],
    utility_model: UtilityModel | None = None,
    pos: str | None = None,
    *,
    reference: Reference | None = None,
) -> StudyValue:
    if frequency_model.variant != "frequency":
        raise ValueError("Резервная модель должна использовать признаки frequency.")
    evidence = index.lookup(form, pos)
    model = reading_model if evidence.books is not None else frequency_model
    base = rank_form(index, form, pos, model)
    if base.tier == 10:
        return StudyValue(
            form, pos, 10, base.score, False, base.method, evidence, None, None, None, None,
            base.reasons,
        )

    reading_score = base.score
    method = base.method
    provisional = base.provisional
    utility = utilities.get(evidence.form)
    reasons = list(base.reasons)
    if reading_score is not None and evidence.books is None:
        reasons.append("Книжный охват формы неизвестен. Применена отдельная частотная модель.")
    if reading_score is None and reference is not None:
        count = reference.counts.get(evidence.form, 0)
        if count > 0:
            reading_score = (count + 0.5) / (reference.books + 1)
            method = "reference_books"
            provisional = False
            reasons[-1] = (
                f"Точная форма или последовательность встретилась в {count} из {reference.books} "
                f"книг ({reference.scope}). Балл использует сглаженную долю книг."
            )
        elif evidence.books is None and evidence.zipf == 0 and re.fullmatch(r"[a-z]+", evidence.form):
            reading_score = reference.unseen_single_rate
            method = "reference_unseen_single"
            reasons[-1] = (
                f"Временный балл {reading_score:.5f} получен на проверочных фрагментах ELTeC "
                "для одиночных форм без словарного покрытия и без совпадений в обучающих книгах. "
                "Для самой формы данных недостаточно."
            )
    if utility is not None:
        reasons.append(
            f"Человеческая оценка полезности формы в Wang et al.: {utility:.3f}. "
            "Оценка относится к предъявленной форме и основана на ответах носителей английского."
        )

    if reading_score is None:
        method = "human_only" if utility is not None else "insufficient"
        if utility is not None:
            reasons.append("Есть оценка людей. Книжный приоритет предварительный.")
        return StudyValue(
            form, pos, 6, None, True, method, evidence, None, utility, None, None, tuple(reasons),
        )

    score = reading_score
    expected = adjustment = None
    if (
        not provisional
        and utility_model is not None
        and utility is not None
        and tokenize(evidence.form, "en") == [evidence.form]
    ):
        expected = utility_model.predict(evidence)
        # Keep ordering information near both ends of the scale, including rare forms.
        move = utility_model.adjustment(utility, expected)
        score = reading_score + _clip(move, -reading_score / 2, (1 - reading_score) / 2)
        adjustment = score - reading_score
        if utility_model.strength > 0:
            reasons.append(
                f"Поправка к книжному баллу {adjustment:+.3f}. "
                "Она учитывает отклонение оценки людей от обычной для слов такой частоты."
            )
    tier = next((i for i, boundary in enumerate(TIER_THRESHOLDS, 1) if score >= boundary), 9)
    return StudyValue(
        form, pos, tier, score, provisional, method, evidence, reading_score, utility,
        expected, adjustment, tuple(reasons),
    )


def priority_order(row: StudyValue) -> tuple[int, bool, bool, float, str, str]:
    # Rating is a tie-break only inside the preliminary category with human evidence.
    within_group = row.human_utility if row.method == "human_only" else row.score
    return (
        row.tier, row.provisional, row.method == "insufficient", -(within_group or 0.0),
        row.evidence.form, row.pos or "",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forms", nargs="*")
    parser.add_argument("--entry", nargs=2, action="append", default=[], metavar=("FORM", "POS"))
    parser.add_argument("--resources", type=Path, help="Локальный каталог набора исследования.")
    parser.add_argument("--cyp", type=Path)
    parser.add_argument("--cefr", type=Path, action="append", default=[])
    parser.add_argument("--utilities", type=Path)
    parser.add_argument("--reading-model", type=Path)
    parser.add_argument("--transfer-models", type=Path)
    parser.add_argument("--utility-model", type=Path)
    parser.add_argument("--reference", type=Path, help="JSON с охватом форм в справочных книгах.")
    parser.add_argument("--strength", type=float, help="Переопределить strength из артефакта Utility.")
    args = parser.parse_args()
    if not args.forms and not args.entry:
        parser.error("Укажите хотя бы одну форму.")
    if args.resources is not None:
        args.cyp = args.cyp or args.resources / "main_cyplex13.csv"
        args.cefr = args.cefr or [args.resources / name for name in ("cefr15.csv", "octanove.csv")]
        args.utilities = args.utilities or args.resources / "utility.tsv"
        args.reading_model = args.reading_model or args.resources / "reading-model.json"
        args.transfer_models = args.transfer_models or args.resources / "transfer-models.json"
        args.utility_model = args.utility_model or args.resources / "utility-model.json"
        args.reference = args.reference or args.resources / "reference.json"
    if not all((args.utilities, args.reading_model, args.transfer_models)):
        parser.error("Укажите --resources или передайте --utilities, --reading-model и --transfer-models.")
    if args.strength is not None and args.utility_model is None:
        parser.error("--strength требует файл --utility-model.")
    try:
        index = load_evidence(args.cyp, args.cefr)
        utilities = load_utilities(args.utilities)
        reading_model = load_model(args.reading_model)
        transfer = json.loads(args.transfer_models.read_text(encoding="utf-8-sig"))
        frequency = transfer.get("frequency_if_missing_books", transfer["frequency"])
        frequency_model = Model(frequency["variant"], frequency["intercept"], tuple(frequency["weights"]))
        utility_model = None
        if args.utility_model is not None:
            utility_model = load_utility_model(args.utility_model, args.strength)
        reference = load_reference(args.reference) if args.reference is not None else None
        entries = [(form, None) for form in args.forms] + args.entry
        rows = [
            score_form(
                index, form, reading_model, frequency_model, utilities, utility_model, pos,
                reference=reference,
            )
            for form, pos in entries
        ]
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps([asdict(row) for row in sorted(rows, key=priority_order)], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
