"""Synthetic checks for the two plain-text study formats."""

from pathlib import Path

import pytest

from kindle_vocab_app import card_fields
from kindle_vocab_app.study_formats import write_study_file


def test_quizlet_separates_fields_and_uses_the_saved_card(tmp_path: Path) -> None:
    output = tmp_path / "words.tsv"
    output.touch()
    write_study_file(
        output,
        "quizlet",
        [
            {
                "id": "test",
                "display_form": "take",
                "dictionary": {"meaning_ru": "брать"},
                "enrichment": {"status": "ready", "meaning_ru": "взять"},
                "occurrences": [
                    {"id": "longest", "word": "take", "context": "This longer example was not selected."},
                    {"id": "selected", "word": "took\tup", "context": "She took\r\nup\u2028art."},
                ],
            },
            {"id": "no-meaning", "lemma": "untranslated", "occurrences": [
                {"word": "", "context": "A word\x00in a quote."},
            ]},
            {"id": "no-meaning-no-context", "lemma": "bare"},
        ],
        {"test": {"meaning_ru": "занялась; приступила", "example_occurrence_id": "selected"}},
    )
    assert output.read_bytes() == (
        "took up\tзанялась; приступила · Пример: She took up art.\n"
        "untranslated\tПеревод не добавлен · Пример: A word in a quote.\n"
        "bare\tПеревод не добавлен\n"
    ).encode()


def test_remnote_emits_one_forward_card_per_lexeme(tmp_path: Path) -> None:
    output = tmp_path / "words.txt"
    output.touch()
    write_study_file(
        output,
        "remnote",
        [
            {"id": "markers", "display_form": "- term << <> >> >=, {{blank}}, #[[Tag]]\n- more",
             "enrichment": {"status": "ready", "meaning_ru": "A) first == second"},
             "occurrences": [{"context": "x\ny\t:: ;; :> ;< >- :- ;- +++ ~~ <br> &gt;"}]},
            {"id": "number", "display_form": "1. entry", "dictionary": {"meaning_ru": "1. first"}},
            {"id": "missing", "lemma": "untranslated"},
        ],
        {},
    )
    lines = output.read_bytes().decode("utf-8").splitlines()
    assert lines == [
        (
            "－ term ＜＜ ＜＞ ＞＞ ＞=, ｛｛blank｝｝, ＃［［Tag］］ - more"
            " >> A） first ＝＝ second · Пример: x y ：： ；； :＞ ;＜ ＞- ：－ ；－ ＋＋＋ ～～ ＜br＞ ＆gt；"
        ),
        "1． entry >> 1． first",
        "untranslated >> Перевод не добавлен",
    ]
    assert all(line.count(" >> ") == 1 for line in lines)


def test_write_failure_preserves_reservation_and_unrelated_temps(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "words.tsv"
    output.touch()
    unrelated = output.with_suffix(".tsv.tmp")
    unrelated.write_bytes(b"owned by a different writer")

    replace = Path.replace

    def reject_replace(source: Path, target: Path) -> Path:
        if target != output:
            return replace(source, target)
        assert source.parent == output.parent
        assert source != unrelated and source.read_bytes() == "word\tПеревод не добавлен\n".encode()
        assert target.read_bytes() == b""
        raise PermissionError("test: replace failed")

    monkeypatch.setattr(Path, "replace", reject_replace)
    with pytest.raises(PermissionError, match="replace failed"):
        write_study_file(output, "quizlet", [{"id": "test", "lemma": "word"}], {})

    assert output.read_bytes() == b""
    assert unrelated.read_bytes() == b"owned by a different writer"
    assert set(tmp_path.iterdir()) == {output, unrelated}


@pytest.mark.parametrize(("destination", "separator"), [("quizlet", "\t"), ("remnote", " >> ")])
def test_structured_pairs_stay_on_one_card(tmp_path: Path, destination: str, separator: str) -> None:
    output = tmp_path / "cards"
    context = "A bank near the river."
    fingerprint = card_fields.context_fingerprint(context)
    entry = {
        "id": "one", "lemma": "bank", "occurrences": [{"context": context}],
        "processing": {"state": "ready"},
        "enrichment": {
            "status": "ready", "prompt_version": 2, "meaning_ru": "берег",
            "selected_context_sha256": fingerprint, "context_source_sha256": fingerprint,
            "context_quality": "good", "context_truncated": False,
            "context_meaning_ru": "берег реки", "context_ru": "Берег около реки.",
            "example_en": "He climbed up the bank.", "example_ru": "Он поднялся по берегу.",
            "senses": [
                {"meaning_ru": "банк", "example_en": "The bank\nopened.", "example_ru": "Банк\tоткрылся."},
                {"meaning_ru": "вираж", "example_en": "It banked >> sharply.", "example_ru": "Он резко накренился."},
            ],
        },
    }
    baseline = card_fields.resolve(entry, include_enrichment=False)
    entry["enrichment"]["review_fingerprint"] = card_fields.review_fingerprint(entry, baseline)
    write_study_file(output, destination, [entry], {})
    [line] = output.read_text(encoding="utf-8").splitlines()
    assert line.count(separator) == 1
    front, back = line.split(separator, maxsplit=1)
    assert front == "bank" and back.startswith("берег · Пример: A bank near the river.")
    assert "Значение в цитате: берег реки" in back
    assert "Перевод цитаты: Берег около реки." in back
    assert "He climbed up the bank. — Он поднялся по берегу." in back
    assert "банк — The bank opened. — Банк открылся." in back
    assert "Он резко накренился." in back
