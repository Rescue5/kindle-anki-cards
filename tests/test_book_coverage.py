import gzip
import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

import pytest

from kindle_vocab_app import book_coverage
from scripts import import_openresearch_coverage as importer


@pytest.fixture
def source(tmp_path, monkeypatch):
    model = {
        "columns": ["conditional", "coverage"],
        "rows": {
            "walk": [0.8, 0.75],
            "walking": [0.8, 0.5],
            "unmeasured": [0.8, None],
            "absent": [0.8, 0.0],
            "rare": [0.8, 0.000001],
            "o'clock": [0.8, 0.1],
            "dose-response": [0.8, 0.2],
            **{word: [None, score] for word, score in zip(
                ("one", "two", "three", "four", "five", "six", "seven", "eight"),
                (0.75, 0.5, 1 / 3, 0.2, 0.1, 0.05, 0.02, 0.005),
                strict=True,
            )},
        },
        "aliases": {
            "walks": "walk",
            "walking": "walk",
            "unmeasured": "walk",
            "dangling": "unavailable",
        },
    }
    compressed = gzip.compress(json.dumps(model).encode())
    digest = hashlib.sha256(compressed).hexdigest()
    monkeypatch.setattr(book_coverage, "SOURCE_SHA256", digest)
    source = tmp_path / "ranker.json.gz"
    source.write_bytes(compressed)
    return source


def test_priority_uses_coverage_and_exact_lookup(source, tmp_path):
    importer.import_model(source, tmp_path)
    with book_coverage.open_model(tmp_path) as model:
        assert model.priority("WALKING")["score"] == 0.5
        assert model.priority("   ｗａｌｋｓ   ")["score"] == 0.75
        assert model.priority("walks", lemma="walk")["score"] == 0.75
        assert model.priority("walking", lemma="walk")["score"] == 0.75
        assert model.priority("walks", lemma="walks")["provisional"]
        assert model.priority("dangling")["provisional"]
        assert model.priority("o’clock")["score"] == 0.1
        assert model.priority("dose‑response")["score"] == 0.2


def test_coverage_bands_and_unresolved_cases(source, tmp_path):
    importer.import_model(source, tmp_path)
    with book_coverage.open_model(tmp_path) as model:
        words = ("one", "two", "three", "four", "five", "six", "seven", "eight")
        assert [model.priority(word)["level"] for word in words] == list(range(1, 9))
        zero = model.priority("absent")
        assert (zero["level"], zero["score"], zero["provisional"]) == (9, 0.0, False)
        assert "0%" in zero["reason"]
        assert "при равном весе авторов" in zero["reason"]
        rare = model.priority("rare")
        assert rare["score"] == 0.000001
        assert "менее чем в 0,01%" in rare["reason"]
        priorities = [
            model.priority("unmeasured"),
            model.priority("unknown"),
            model.priority("walk\taway", lemma="walk"),
            model.priority("walk", lemma="walk away"),
            model.priority("walk!", lemma="walk"),
            model.priority("walk", lemma=""),
        ]
        assert all(
            (item["level"], item["score"], item["provisional"]) == (6, 0.0, True)
            for item in priorities
        )
        assert len({item["reason"] for item in priorities}) == 5


def test_personalized_priority_preserves_a_single_search_and_filters_unreliable_episodes(source, tmp_path):
    importer.import_model(source, tmp_path)
    now = datetime(2026, 11, 24, 19, tzinfo=UTC)
    with book_coverage.open_model(tmp_path) as model:
        base = model.priority("dose-response")
        history = [
            (now, "novel"),
            (now.astimezone(timezone(timedelta(hours=9))), " novel "),
            (now.replace(tzinfo=None) + timedelta(hours=1), "novel"),
            (now, " "),
            (now, "koreader:other"),
            (now, "kobo:other"),
            (None, "unreliable"),
            ("bad date", "unreliable"),
            (datetime.min.replace(tzinfo=timezone(timedelta(hours=1))), "unreliable"),
        ]
        expected = {**base, "coverage_score": 0.2}
        original = base.copy()
        assert book_coverage.personalized_priority(base, []) == expected
        assert book_coverage.personalized_priority(base, iter(history)) == expected
        assert base == original


def test_personalized_priority_counts_only_repeated_days_beyond_each_first_book_episode(source, tmp_path):
    importer.import_model(source, tmp_path)
    today = datetime(2026, 11, 24, tzinfo=UTC)
    yesterday = today - timedelta(days=1)
    with book_coverage.open_model(tmp_path) as model:
        base = model.priority("dose-response")
        repeated = book_coverage.personalized_priority(base, [(today, "a"), (yesterday, "a")])
        crossed = book_coverage.personalized_priority(base, [(today, "a"), (yesterday, "b")])
        mixed = book_coverage.personalized_priority(base, [(today, "a"), (yesterday, "a"), (yesterday, "b")])
        assert repeated["score"] == pytest.approx(0.2 * 1.25 / (0.8 + 0.2 * 1.25))
        assert crossed["score"] == pytest.approx(0.2 * 1.50 / (0.8 + 0.2 * 1.50))
        assert mixed["score"] == pytest.approx(0.2 * 1.75 / (0.8 + 0.2 * 1.75))
        assert all(item["coverage_score"] == 0.2 and item["reason"].startswith(base["reason"])
                   for item in (repeated, crossed, mixed))
        assert "разные дни" in repeated["reason"] and "разных книгах" not in repeated["reason"]
        assert "разных книгах" in crossed["reason"] and "разные дни" not in crossed["reason"]
        assert "разные дни" in mixed["reason"] and "разных книгах" in mixed["reason"]
        assert repeated["personal_reason"] == "Вы искали это слово в одной книге в разные дни."
        assert crossed["personal_reason"] == "Вы искали в разных книгах."
        assert mixed["personal_reason"] == "Вы искали в разных книгах и возвращались к слову в одной из них в разные дни."


def test_personalized_priority_caps_odds_and_keeps_unmeasured_items_provisional(source, tmp_path):
    importer.import_model(source, tmp_path)
    now = datetime(2026, 11, 24, tzinfo=UTC)
    lookups = [(now - timedelta(days=day), "novel") for day in range(20)]
    with book_coverage.open_model(tmp_path) as model:
        base = model.priority("unmeasured")
        unknown = book_coverage.personalized_priority(base, lookups)
        assert unknown == {
            "level": 6,
            "score": 1.0,
            "provisional": True,
            "coverage_score": None,
            "personal_reason": "Вы искали это слово в одной книге в разные дни.",
            "reason": base["reason"] + " Порядок среди предварительных оценок учитывает поиски в разные дни в одной книге.",
        }
        measured = book_coverage.personalized_priority(model.priority("dose-response"), lookups)
        assert measured["score"] == pytest.approx(1 / 3)
        assert measured["level"] == 3
        zero = model.priority("absent")
        assert book_coverage.personalized_priority(zero, lookups) == {**zero, "coverage_score": 0.0}
        full = {"level": 1, "score": 1.0, "provisional": False, "reason": "Книжный охват 100%"}
        assert book_coverage.personalized_priority(full, lookups) == {**full, "coverage_score": 1.0}
        structural = {"level": 10, "score": 0.0, "provisional": False, "reason": "В записи нет букв"}
        assert book_coverage.personalized_priority(structural, lookups) == {**structural, "coverage_score": None}


@pytest.mark.parametrize("before_level,threshold", enumerate(book_coverage.THRESHOLDS, 2))
def test_personalized_priority_does_not_cross_two_level_boundaries(before_level, threshold):
    score = math.nextafter(threshold, 0)
    base = {"level": before_level, "score": score, "provisional": False, "reason": "Книжный охват"}
    lookups = [(datetime(2026, 11, 24, tzinfo=UTC), book) for book in ("a", "b", "c")]
    result = book_coverage.personalized_priority(base, lookups)
    assert before_level - 1 <= result["level"] <= before_level
    assert result["coverage_score"] == score


def test_personalized_priority_distinguishes_exact_threshold_from_next_lower_input():
    base = {"level": 2, "score": 0.60, "provisional": False, "reason": "Книжный охват"}
    lookups = [(datetime(2026, 11, 24, tzinfo=UTC), book) for book in ("a", "b", "c")]
    exact = book_coverage.personalized_priority(base, lookups)
    assert (exact["level"], exact["score"], exact["coverage_score"]) == (1, 0.75, 0.60)
    lower = math.nextafter(0.60, 0)
    below = book_coverage.personalized_priority({**base, "score": lower}, lookups)
    assert below["level"] == 2
    assert below["score"] < 0.75
    assert below["coverage_score"] == lower


def test_zip_import_matches_direct_and_bad_hash_preserves_model(source, tmp_path):
    destination = importer.import_model(source, tmp_path)
    expected = destination.read_bytes()
    archive = tmp_path / "research-kit-v2.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(source, "models/ranker.json.gz")
    assert importer.import_model(archive, tmp_path) == destination
    assert destination.read_bytes() == expected
    source.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="SHA-256"):
        importer.import_model(source, tmp_path)
    assert destination.read_bytes() == expected
    assert list(destination.parent.iterdir()) == [destination]


def test_workspace_precedence_and_portable_fallback(source, tmp_path, monkeypatch):
    portable = tmp_path / "portable"
    portable_model = portable / "models" / book_coverage.MODEL_FILENAME
    portable_model.parent.mkdir(parents=True)
    destination = importer.import_model(source, tmp_path)
    portable_model.write_bytes(destination.read_bytes())
    with sqlite3.connect(portable_model) as connection:
        connection.execute("UPDATE coverage SET share = 0.8 WHERE headword = 'walk'")
    connection.close()
    missing_workspace = tmp_path / "other"
    monkeypatch.setattr(book_coverage.sys, "executable", str(portable / "kindle-bridge.exe"))
    with book_coverage.open_model(missing_workspace) as model:
        assert model is None
    assert not Path(missing_workspace).exists()
    monkeypatch.setattr(book_coverage.sys, "frozen", True, raising=False)
    with book_coverage.open_model(missing_workspace) as model:
        assert model.priority("walk")["score"] == 0.8
    with book_coverage.open_model(tmp_path) as model:
        assert model.priority("walk")["score"] == 0.75
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            model._connection.execute("DELETE FROM coverage")
    destination.write_bytes(b"incomplete")
    with book_coverage.open_model(tmp_path) as model:
        assert model.priority("walk")["score"] == 0.8


def test_expanded_model_is_preferred_without_overwriting_the_original(source, tmp_path, monkeypatch):
    original = importer.import_model(source, tmp_path)
    data = json.loads(gzip.decompress(source.read_bytes()))
    data["rows"]["walk"][1] = 0.81
    expanded = gzip.compress(json.dumps(data).encode(), mtime=0)
    monkeypatch.setattr(book_coverage, "EXPANDED_SOURCE_SHA256", {hashlib.sha256(expanded).hexdigest()})
    source.write_bytes(expanded)
    installed = importer.import_model(source, tmp_path)
    assert installed.name == book_coverage.EXPANDED_MODEL_FILENAME
    assert original.is_file()
    with book_coverage.open_model(tmp_path) as model:
        assert model.priority("walk")["score"] == 0.81
    installed.write_bytes(b"incomplete")
    with book_coverage.open_model(tmp_path) as model:
        assert model.priority("walk")["score"] == 0.75


def test_bundled_expanded_model_wins_on_clean_and_upgraded_profiles(source, tmp_path, monkeypatch):
    upgraded = tmp_path / "upgraded"
    original = importer.import_model(source, upgraded)
    data = json.loads(gzip.decompress(source.read_bytes()))
    data["rows"]["walk"][1] = 0.61
    previous = gzip.compress(json.dumps(data).encode(), mtime=0)
    data["rows"]["walk"][1] = 0.81
    bundled = gzip.compress(json.dumps(data).encode(), mtime=0)
    monkeypatch.setattr(book_coverage, "EXPANDED_SOURCE_SHA256", {
        hashlib.sha256(previous).hexdigest(), hashlib.sha256(bundled).hexdigest(),
    })
    source.write_bytes(previous)
    previous_path = importer.import_model(source, upgraded)
    previous_bytes = previous_path.read_bytes()
    source.write_bytes(bundled)
    bridge_models = tmp_path / "bridge" / "models"
    bridge_models.mkdir(parents=True)
    bundled_path = bridge_models / book_coverage.EXPANDED_MODEL_FILENAME
    bundled_path.write_bytes(importer.import_model(source, tmp_path).read_bytes())
    monkeypatch.setattr(book_coverage.sys, "executable", str(bridge_models.parent / "kindle-bridge.exe"))
    monkeypatch.setattr(book_coverage.sys, "frozen", True, raising=False)

    for workspace in (tmp_path / "clean", upgraded):
        with book_coverage.open_model(workspace) as model:
            assert model is not None
            database = model._connection.execute("PRAGMA database_list").fetchone()
            assert Path(database[2]).samefile(bundled_path)
            assert model.priority("walk")["score"] == 0.81
            assert model.priority("walk")["level"] == 1

    assert previous_path.read_bytes() == previous_bytes
    assert original.is_file()
    bundled_path.write_bytes(b"incomplete")
    with book_coverage.open_model(upgraded) as model:
        assert model is not None
        assert model.priority("walk")["score"] == 0.61
