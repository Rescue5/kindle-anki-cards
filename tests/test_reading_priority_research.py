import json
import math
import subprocess
import sys

import pytest

from scripts.research.reading_priority import (
    Evidence,
    Model,
    features,
    load_evidence,
    load_model,
    rank_form,
)


@pytest.fixture
def evidence_files(tmp_path):
    cyp = tmp_path / "books.csv"
    cyp.write_text(
        "Word,CD_book_count_raw\n"
        "borrow,360\nborrows,7\npresent,200\nzero,0\nthe,400\n",
        encoding="utf-8-sig",
    )
    cefr = tmp_path / "cefr.csv"
    cefr.write_text(
        "headword,pos,CEFR\n"
        "borrow,verb,B1\npresent,noun,A2\npresent,verb,B2\n"
        "take off,verb,A2\nset,verb,B1\nset,verb,C1\n"
        "light,noun,A1\nlight,adjective,A1\n",
        encoding="utf-8-sig",
    )
    return cyp, cefr


def test_form_and_pos_are_resolved_without_lemmatizing(evidence_files):
    cyp, cefr = evidence_files
    index = load_evidence(cyp, [cefr])

    assert index.lookup("  ＢＯＲＲＯＷ ").form == "borrow"
    assert index.lookup("borrow").books == 360
    assert index.lookup("borrow").cefr == "B1"
    assert index.lookup("borrows").books == 7
    assert index.lookup("borrows").cefr is None
    assert index.lookup("borrowed").books is None
    assert index.lookup("present").cefr is None
    assert index.lookup("present", " VERB ").cefr == "B2"
    assert index.lookup("present", "noun").cefr == "A2"
    assert index.lookup("present", "adverb").cefr is None
    assert index.lookup("set", "verb").cefr is None
    assert index.lookup("light").cefr is None


def test_features_distinguish_zero_from_missing_and_include_cefr_without_intercept():
    known = Evidence("item", 0, 4.1, "B1")
    missing = Evidence("zqwfryz", None, 0, None)
    minimum = math.log(0.5 / 400.5)

    assert features(known, "frequency") == (4.1, 0.0)
    assert features(known, "books") == (minimum, 0.0)
    assert features(known, "combined") == (4.1, 0.0, minimum, 0.0)
    assert features(known, "combined_cefr") == (
        4.1, 0.0, minimum, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0
    )
    assert features(missing, "combined_cefr") == (
        0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0
    )
    maximum = Evidence("the", 400, 7.73, "A1")
    assert features(maximum, "books") == (-minimum, 0.0)
    with pytest.raises(ValueError, match="вариант"):
        features(known, "unknown")


def test_fallback_uses_book_reach_and_no_level_is_forced_by_cefr(evidence_files):
    cyp, cefr = evidence_files
    index = load_evidence(cyp, [cefr])

    assert rank_form(index, "borrow").score == 0.9
    assert rank_form(index, "borrow").tier == 1
    assert rank_form(index, "zero").tier == 9
    fitted_baseline = Model("combined_cefr", 0.0, (0.0,) * 11)
    priority = rank_form(index, "borrow", model=fitted_baseline)
    assert (priority.evidence.cefr, priority.tier, priority.score) == ("B1", 2, 0.5)
    assert any("значениям" in reason for reason in priority.reasons)
    assert any("контексте" in reason for reason in priority.reasons)


def test_unknown_phrase_name_and_structural_input(evidence_files):
    cyp, cefr = evidence_files
    index = load_evidence(cyp, [cefr])
    phrase = rank_form(index, "take off", "verb")
    assert phrase.evidence == Evidence("take off", None, 0.0, "A2")
    assert phrase.provisional and phrase.tier == 6 and phrase.score is None
    assert any("выражения" in reason for reason in phrase.reasons)
    frequency_only = rank_form(index, "take off", model=Model("frequency", 1.0, (1.0, 0.0)))
    assert frequency_only.provisional and frequency_only.score is None
    frequency_fallback = rank_form(index, "context")
    assert frequency_fallback.method == "general_frequency"
    assert frequency_fallback.score == pytest.approx(frequency_fallback.evidence.zipf / 9)
    name = rank_form(index, "Zqvrel")
    assert name.provisional and name.tier == 6
    assert rank_form(index, "über").tier != 10
    for form in ("00:17", "?!", "123"):
        priority = rank_form(index, form)
        assert (priority.tier, priority.score, priority.provisional) == (10, 0.0, False)
    with pytest.raises(ValueError, match="непустую"):
        rank_form(index, " \t")


def test_model_json_and_cli_round_trip(tmp_path, evidence_files):
    cyp, cefr = evidence_files
    model_file = tmp_path / "model.json"
    model_file.write_text(
        json.dumps({"variant": "books", "intercept": -0.5, "weights": [1.0, 0.0]}),
        encoding="utf-8",
    )
    model = load_model(model_file)
    expected = model.predict(load_evidence(cyp, [cefr]).lookup("borrow"))
    output = subprocess.run(
        [
            sys.executable, "-X", "utf8", "-m", "scripts.research.reading_priority",
            "--model", str(model_file), "--cyp", str(cyp), "--cefr", str(cefr),
            "borrow", "00:17", "--entry", "present", "verb",
        ],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    rows = json.loads(output.stdout)
    assert [row["form"] for row in rows] == ["borrow", "present", "00:17"]
    assert rows[0]["score"] == expected
    assert rows[1]["pos"] == "verb" and rows[1]["evidence"]["cefr"] == "B2"
    assert rows[2]["tier"] == 10


@pytest.mark.parametrize(
    ("variant", "intercept", "weights"),
    [("books", 0, (1,)), ("unknown", 0, ()), ("frequency", float("nan"), (1, 2))],
)
def test_invalid_model_is_rejected(variant, intercept, weights):
    with pytest.raises(ValueError):
        Model(variant, intercept, weights)
