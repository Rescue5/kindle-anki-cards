import json
import subprocess
import sys

import pytest

from scripts.research.reading_priority import EvidenceIndex, Model
from scripts.research.study_value import (
    Reference,
    UtilityModel,
    load_utilities,
    priority_order,
    score_form,
)


@pytest.fixture
def setup_models():
    index = EvidenceIndex(books={"borrow": 200, "lend": 100}, cefr={})
    reading = Model("books", 0, (0, 0))
    frequency = Model("frequency", 2, (0, 0))
    utility = UtilityModel("combined_cefr", (0,) * 11, 0.5, 0.2, 0.1, 0.5)
    return index, reading, frequency, utility


def test_utilities_drop_all_duplicate_rows_controls_and_missing(tmp_path):
    path = tmp_path / "utilities.tsv"
    path.write_text(
        "Word\tUtility\nborrow\t0.6\nＬＥＮＤ\t0.3\nlend\t\n"
        "happy\t0.97\nhelp me\t0.9\n\t0.4\nset off\t\n"
        "  NO THANK YOU  \t0.7\nzero\t0\n",
        encoding="utf-8-sig",
    )
    assert load_utilities(path) == {"borrow": 0.6, "no thank you": 0.7, "zero": 0.0}
    assert "happy" in load_utilities(path, controls=())


@pytest.mark.parametrize(
    ("observed", "expected_adjustment"),
    [(0.99, 0.05), (0.51, 0.005), (0.49, -0.005), (0.0, -0.05)],
)
def test_residual_is_signed_and_bounded(setup_models, observed, expected_adjustment):
    index, reading, frequency, utility_model = setup_models
    row = score_form(index, "borrow", reading, frequency, {"borrow": observed}, utility_model)
    assert row.method == "books"
    assert row.expected_utility == 0.5
    assert row.reading_score == 0.5
    assert row.adjustment == pytest.approx(expected_adjustment)
    assert row.score == pytest.approx(0.5 + expected_adjustment)


def test_zero_strength_and_missing_ratings_preserve_reading_score(setup_models):
    index, reading, frequency, active = setup_models
    disabled = UtilityModel("combined_cefr", active.weights, 0.5, 0.2, 0.1, 0)
    row = score_form(index, "borrow", reading, frequency, {"borrow": 0.99}, disabled)
    assert row.score == row.reading_score and row.adjustment == 0
    row = score_form(index, "lend", reading, frequency, {"borrow": 0.99}, active)
    assert row.score == row.reading_score and row.adjustment is None


def test_frequency_fallback_and_retained_provisional_entries(setup_models):
    index, reading, frequency, utility_model = setup_models
    utilities = {"know": 0.0, "no thank you": 0.8, "take off": 0.4}
    fallback = score_form(index, "know", reading, frequency, utilities, utility_model)
    assert fallback.method == "frequency" and fallback.evidence.books is None
    assert fallback.reading_score == frequency.predict(fallback.evidence)
    assert fallback.adjustment == pytest.approx(-0.05)
    rows = [
        score_form(index, form, reading, frequency, utilities, utility_model)
        for form in ("take off", "no thank you", "zqvrel", "00:17")
    ]
    assert [row.form for row in sorted(rows, key=priority_order)] == [
        "no thank you", "take off", "zqvrel", "00:17"
    ]
    assert [(row.tier, row.provisional, row.method) for row in rows] == [
        (6, True, "human_only"), (6, True, "human_only"), (6, True, "insufficient"),
        (10, False, "structural"),
    ]
    assert rows[0].human_utility == 0.4 and rows[1].human_utility == 0.8
    assert rows[0].score is None and rows[1].score is None


def test_reference_exact_hits_and_preliminary_class(setup_models):
    index, reading, frequency, utility_model = setup_models
    reference = Reference(42, {"take off": 12, "zqvrel": 1, "borrow": 40}, 0.012, "42 training books")
    utilities = {"take off": 0.9, "no thank you": 0.8, "qabzrel": 0.9}

    def score(form):
        return score_form(index, form, reading, frequency, utilities, utility_model, reference=reference)

    for form, books in (("TAKE OFF", 12), ("zqvrel", 1)):
        result = score(form)
        assert result.method == "reference_books" and not result.provisional
        assert result.reading_score == pytest.approx((books + 0.5) / 43)
        assert result.adjustment is None
        assert any("42 training books" in reason for reason in result.reasons)
    assert score("borrow").method == "books"
    assert score("know").method == "frequency"
    unseen = score("qabzrel")
    assert (unseen.method, unseen.provisional, unseen.tier, unseen.score) == (
        "reference_unseen_single", True, 8, 0.012
    )
    assert unseen.human_utility == 0.9 and unseen.adjustment is None
    assert score("no thank you").method == "human_only"
    assert score("qab zrel").method == "insufficient"
    assert score("qäbzrel").method == "insufficient"
    assert score("123").tier == 10


@pytest.mark.parametrize("resources_mode", [False, True])
def test_cli_artifact_round_trip(tmp_path, resources_mode):
    cyp = tmp_path / "main_cyplex13.csv"
    cyp.write_text("Word,CD_book_count_raw\nborrow,200\n", encoding="utf-8")
    ratings = tmp_path / "utility.tsv"
    ratings.write_text("Word\tUtility\nborrow\t0.9\nno thank you\t0.8\n", encoding="utf-8")
    reading = tmp_path / "reading-model.json"
    base_model = {"variant": "books", "weights": [0, 0], "intercept": 0}
    reading.write_text(json.dumps(base_model), encoding="utf-8")
    transfer = tmp_path / "transfer-models.json"
    transfer.write_text(
        json.dumps({"frequency": {**base_model, "variant": "frequency"}}), encoding="utf-8",
    )
    utility = tmp_path / "utility-model.json"
    utility.write_text(
        json.dumps(
            {"feature_variant": "combined_cefr", "weights": [0] * 11, "intercept": 0.5,
             "residual_scale": 0.2, "residual_cap": 0.1, "strength": 0}
        ),
        encoding="utf-8",
    )
    for name in ("cefr15.csv", "octanove.csv"):
        (tmp_path / name).write_text("headword,pos,CEFR\n", encoding="utf-8")
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps({"books": 42, "counts": {"take off": 12}, "unseen_single_rate": 0.01,
                    "scope": "42 training books"}),
        encoding="utf-8",
    )
    input_args = [
        "--cyp", str(cyp), "--utilities", str(ratings), "--reading-model", str(reading),
        "--transfer-models", str(transfer), "--utility-model", str(utility),
        "--reference", str(reference),
    ]
    if resources_mode:
        input_args = ["--resources", str(tmp_path)]
    output = subprocess.run(
        [
            sys.executable, "-X", "utf8", "-m", "scripts.research.study_value",
            *input_args, "--strength", "0.5", "borrow", "no thank you", "take off", "00:17",
        ],
        check=True, capture_output=True, encoding="utf-8",
    )
    rows = json.loads(output.stdout)
    assert rows[0]["score"] == pytest.approx(0.55)
    assert rows[1]["method"] == "reference_books"
    assert rows[2]["method"] == "human_only" and rows[2]["human_utility"] == 0.8
    assert rows[3]["tier"] == 10
