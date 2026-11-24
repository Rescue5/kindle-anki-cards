from collections import Counter

import pytest

from scripts.research.expand_novel_coverage import add_authors, load_supplement


def training_book(key, title, first, last, lemmas):
    return {
        "id": key,
        "title": title,
        "author_first": first,
        "author_last": last,
        "lemmas": lemmas,
        "publication_year": 2021,
        "license": "CC BY",
        "source_url": "https://example.org/novels",
        "word_count": 50000,
        "split": "train",
    }


def load_test_books(tmp_path, books):
    metadata = tmp_path / "metadata.csv"
    metadata.write_text(
        "ID,Author_Last,Author_First,Work_Title\nold,Test,Ali,Old\n", encoding="utf-8"
    )
    return load_supplement({"schema_version": 1, "books": books}, metadata)


def test_author_with_two_external_novels_receives_one_vote(tmp_path):
    books = [
        training_book("a1", "Book One", "A", "Reader", ["cloud", "harbor"]),
        training_book("a2", "Book Two", "A", "Reader", ["cloud"]),
        training_book("b1", "Book Three", "B", "Writer", ["cloud", "harbor"]),
    ]
    mass = Counter()
    add_authors(None, load_test_books(tmp_path, books), mass)
    assert mass == {"cloud": 2.0, "harbor": 1.5}


@pytest.mark.parametrize("first,last", [("Anne", "Currie"), ("Ali", "Test")])
def test_known_author_alias_cannot_enter_training(tmp_path, first, last):
    book = training_book("b", "New Book", "", "Pseudonym", ["cloud"])
    book["author_aliases"] = [{"author_first": first, "author_last": last}]
    with pytest.raises(ValueError, match="overlap"):
        load_test_books(tmp_path, [book])
