"""Synthetic checks for the two plain-text study formats."""

from pathlib import Path

import pytest

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
