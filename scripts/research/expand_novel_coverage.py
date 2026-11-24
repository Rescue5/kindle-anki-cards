"""Refit CONLIT coverage on the frozen train + validation books, then replay the test.

Run with --cache pointing at the original CONLIT files and --kit pointing at
the extracted RP-V2 kit. Only local inputs are read. Output is private.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import random
import re
import statistics
import unicodedata
import zlib
from collections import Counter, defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from platform import python_version
from zipfile import ZipFile

REFERENCE = {
    "reference/split.json": "414390c844ec498d993330db848d8b35cce402201dad99ce718c764e42890fc0",
    "reference/candidate-lists.json": "1162448ef626d8a0b3415697823c51afb4e68d1088801720174c4baeeb9677e2",
    "reference/model.json": "51cdb059a4b56a156c9757f6d7bf5d57a9b27e9bd7bc907000cb573b1d2aff04",
    "models/ranker.json.gz": "d75e5ba0b3cd3a21f449955b627e48f9344b95a9ad1694f2d2c7c4956f24e686",
    "prior-study/output/results.json": "fc1425c1429380092be848f134791195428c6ca3234e5b421c7ad2b13827b739",
}
CORPUS = {
    "CONLIT_META.csv": "61de1b342d4a7cb6e7388512a1d03b808f940019b51be8d491d0a4793e30da46",
    "CONLIT_WORDCOUNTS.zip": "776c9638d773f0316e361f145248aa3817698584a4b74898574c7cb243ccf6c1",
}
TOKEN = re.compile(r"[a-z]+(?:['-][a-z]+)*")
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-"})
# Independent external evaluation authors. Protect the entire surname, also for
# sources that omit initials or split a compound family name differently.
HELD_SURNAMES = {
    "fister",
    "bowering",
    "wollenberg",
    "mashinini",
    "currie",
    "meyerdinkgrafe",
}


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_files(directory, expected):
    for name, checksum in expected.items():
        if digest(directory / name) != checksum:
            raise ValueError(f"Input SHA-256 mismatch: {name}")


def read_json(file):
    return json.loads(file.read_bytes())


@lru_cache(maxsize=250_000)
def normalize(lemma):
    text = unicodedata.normalize("NFKC", lemma).translate(TYPOGRAPHY).lower()
    key = " ".join(text.split())
    return key if TOKEN.fullmatch(key) else None


def terms(archive, book):
    present = set()
    with (
        archive.open(f"CONLIT_WORDCOUNTS/{book['id']}_unigrams.csv") as raw,
        io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as source,
    ):
        rows = csv.reader(source)
        if next(rows) != ["Lemma", "Count"]:
            raise ValueError(f"Unexpected column names in {book['id']}")
        for lemma, count in rows:
            key = normalize(lemma)
            if key and int(count) > 0:
                present.add(key)
    return present


def by_author(books):
    grouped = defaultdict(list)
    for book in books:
        grouped[book["author"]].append(book)
    return grouped


def book_summary(books):
    years = [book["year"] for book in books]
    return {
        "books": len(books),
        "authors": len(by_author(books)),
        "years": [min(years), max(years)],
    }


def verify_split(split, origins):
    groups = ["train", "valid", "source", "test", "youth"]
    seen_authors, seen_ids = set(), set()
    for group in groups:
        books = split[group]
        authors, ids = set(by_author(books)), {book["id"] for book in books}
        if len(ids) != len(books) or ids & seen_ids or authors & seen_authors:
            raise ValueError(f"Overlapping book/author split: {group}")
        seen_authors.update(authors)
        seen_ids.update(ids)
    if len(origins) != 24 or any(book not in split["source"] for book in origins):
        raise ValueError("Unexpected panel origins")


def identity(text):
    return "".join(
        char for char in unicodedata.normalize("NFKD", text).casefold() if char.isalnum()
    )


def name_forms(names):
    forms = set()
    for name in names:
        surname, given = identity(name["author_last"]), identity(name["author_first"])
        forms.update((surname + given, given + surname))
    return forms - {""}


def load_supplement(data, metadata):
    if data is None:
        return []
    with metadata.open(encoding="utf-8-sig", newline="") as source:
        records = list(csv.DictReader(source))
    reserved_authors = name_forms(
        {"author_last": r["Author_Last"], "author_first": r["Author_First"]} for r in records
    )
    reserved_titles = {identity(r["Work_Title"]) for r in records}
    reserved_ids = {r["ID"] for r in records}
    author_keys = {}
    if data["schema_version"] != 1 or not data["books"]:
        raise ValueError("Expected nonempty external training presence schema version 1")
    books = []
    for row in data["books"]:
        surname, given = identity(row["author_last"]), identity(row["author_first"])
        title, year, book_id = identity(row["title"]), row["publication_year"], row["id"]
        if row["split"] != "train" or not surname or not title or not book_id:
            raise ValueError("Incomplete training provenance")
        if not 2016 < year <= datetime.now(UTC).year or not all(
            row.get(k) for k in ("license", "source_url", "word_count")
        ):
            raise ValueError(f"Missing modern publication or source provenance: {book_id}")
        variants = [row, *row.get("author_aliases", [])]
        author = f"{surname}|{given}"
        forms = name_forms(variants)
        held_name = any(identity(v["author_last"]) in HELD_SURNAMES for v in variants)
        if (
            held_name
            or forms & reserved_authors
            or title in reserved_titles
            or book_id in reserved_ids
        ):
            raise ValueError(f"Possible author, work or ID overlap: {book_id}")
        if any(name in author_keys and author_keys[name] != author for name in forms):
            raise ValueError(f"An author must use one training key across books: {book_id}")
        author_keys.update(dict.fromkeys(forms, author))
        lemmas = row["lemmas"]
        if not lemmas or sorted(set(lemmas)) != lemmas or any(normalize(w) != w for w in lemmas):
            raise ValueError(f"Expected sorted unique normalized unigram lemmas: {book_id}")
        reserved_ids.add(book_id)
        reserved_titles.add(title)
        books.append({"id": book_id, "author": author, "year": year, "lemmas": lemmas})
    return books


def add_authors(archive, books, mass):
    """Each novel contributes one presence vote divided by this author's book count."""
    for novels in by_author(books).values():
        local = Counter()
        for novel in novels:
            local.update(novel["lemmas"] if "lemmas" in novel else terms(archive, novel))
        for word, n in local.items():
            mass[word] += n / len(novels)


def write_model(path, rows, aliases):
    payload = {"columns": ["coverage"], "rows": rows, "aliases": aliases}
    encoded = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()
    tmp = path.with_suffix(".tmp")
    with (
        tmp.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as output,
    ):
        output.write(encoded)
    tmp.replace(path)
    return hashlib.sha256(encoded).hexdigest()


def fit(archive, split, kit, destination, supplement):
    old = json.loads(gzip.decompress((kit / "models/ranker.json.gz").read_bytes()))
    baseline = {w: row[2] for w, row in read_json(kit / "reference/model.json")["rows"].items()}
    column = old["columns"].index("coverage")
    original = {w: row[column] for w, row in old["rows"].items()}
    old_measured = {w: share for w, share in original.items() if share is not None}
    mass = Counter()
    add_authors(archive, split["train"], mass)
    train_authors = len(by_author(split["train"]))
    if (
        baseline != {w: value / train_authors for w, value in mass.items()}
        or baseline != old_measured
    ):
        raise ValueError("Reconstructed training coverage differs from the frozen baseline")
    add_authors(archive, split["valid"], mass)
    aliases = old["aliases"]
    checkpoint_authors = train_authors + len(by_author(split["valid"]))
    checkpoint = (
        {w: value / checkpoint_authors for w, value in mass.items() if w not in aliases}
        if supplement
        else None
    )
    add_authors(archive, supplement, mass)
    denominator = checkpoint_authors + len(by_author(supplement))
    # An alias uniquely identified a canonical headword in the old release.
    # Do not shadow that mapping with a newly observed surface spelling.
    shadowed = mass.keys() & aliases.keys()
    words = (mass.keys() | original.keys()) - shadowed
    expanded = {w: [mass[w] / denominator if w in mass else original[w]] for w in words}
    json_checksum = write_model(destination, expanded, aliases)
    audit = {
        "sha256": digest(destination),
        "uncompressed_sha256": json_checksum,
        "rows": len(expanded),
        "aliases": len(aliases),
        "original_rows": len(original),
        "baseline_reproduced": len(baseline),
        "new_keys": len(words - original.keys()),
        "reserved_alias_spellings": sorted(shadowed),
        "null_before": sum(x is None for x in original.values()),
        "null_after": sum(x[0] is None for x in expanded.values()),
        "zero_before": sum(x == 0 for x in original.values()),
        "zero_after": sum(x[0] == 0 for x in expanded.values()),
    }
    print(f"MODEL {destination} ({len(expanded)} rows) SHA-256 {audit['sha256']}", flush=True)
    measured = {w: row[0] for w, row in expanded.items() if row[0] is not None}
    return baseline, measured, checkpoint, audit


def compare(archive, test, lists, baseline, expanded):
    # The frozen protocol resolves ties by position in the frozen input list.
    def top_five(panel, scores):
        return tuple(sorted(panel, key=lambda w: -scores.get(w, 0.0))[:5])

    choices = [[top_five(panel, scores) for panel in lists] for scores in (baseline, expanded)]
    authors = by_author(test)
    scores = [[], []]
    raw_hits = [0, 0]
    for novels in authors.values():
        author_hits = [0, 0]
        for novel in novels:
            present = terms(archive, novel)
            for i, tops in enumerate(choices):
                author_hits[i] += sum(w in present for top in tops for w in top)
        for i, hits in enumerate(author_hits):
            raw_hits[i] += hits
            scores[i].append(hits / (len(novels) * len(lists) * 5))
    new_minus_old = [new - old for old, new in zip(*scores)]
    rng = random.Random(24011)
    samples = [statistics.fmean(rng.choices(new_minus_old, k=len(authors))) for _ in range(5000)]
    ci = statistics.quantiles(samples, n=1000, method="inclusive")
    return {
        "p5": [statistics.fmean(values) for values in scores],
        "raw_hits": raw_hits,
        "raw_opportunities": len(test) * len(lists) * 5,
        "delta": statistics.fmean(new_minus_old),
        "paired_author_ci95": [ci[24], ci[974]],
        "bootstrap": {
            "replicates": 5000,
            "seed": 24011,
            "unit": "target author; fixed source lists",
        },
        "changed_top5_sets": sum(set(a) != set(b) for a, b in zip(*choices)),
        "panel_lists": len(lists),
        "keys_per_list": len(lists[0]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, default=Path(".app-data/openresearch/rp-v2"))
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, help="Separate post-2016 training presence JSON")
    parser.add_argument("--output", type=Path, help="Private output directory")
    args = parser.parse_args()
    default_output = Path(".app-data/expanded-corpus")
    output = args.output or (default_output / "extended" if args.supplement else default_output)
    check_files(args.cache, CORPUS)
    check_files(args.kit, REFERENCE)
    split = read_json(args.kit / "reference/split.json")
    candidates = read_json(args.kit / "reference/candidate-lists.json")
    verify_split(split, candidates["origins"])
    # Hash the bytes actually consumed even if another acquisition finishes during the refit.
    supplied = args.supplement.read_bytes() if args.supplement else None
    supplement = load_supplement(
        json.loads(supplied) if supplied is not None else None, args.cache / "CONLIT_META.csv"
    )
    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.cache / "CONLIT_WORDCOUNTS.zip", metadata_encoding="utf8") as archive:
        old, new, checkpoint, audit = fit(
            archive, split, args.kit, output / "ranker.json.gz", supplement
        )
        lists = candidates["lists"]["rare"]
        result = compare(archive, split["test"], lists, old, new)
        incremental = (
            compare(archive, split["test"], lists, checkpoint, new) if checkpoint else None
        )
    reference = read_json(args.kit / "prior-study/output/results.json")
    if abs(result["p5"][0] - reference["test"]["author"]["precision"]) > 1e-12:
        raise ValueError("Could not reproduce the original P@5")
    report = {
        "created_utc": datetime.now(UTC).isoformat(),
        "data_source": "CONLIT v1, doi:10.6084/m9.figshare.21166171.v1",
        "runtime": {"python": python_version(), "zlib": zlib.ZLIB_RUNTIME_VERSION},
        "groups": {k: book_summary(v) for k, v in split.items()},
        "combined": book_summary(split["train"] + split["valid"] + supplement),
        "supplement": (
            {
                "sha256": hashlib.sha256(supplied).hexdigest(),
                **book_summary(supplement),
                "ids": [b["id"] for b in supplement],
            }
            if supplement
            else None
        ),
        "inputs": {**CORPUS, **REFERENCE},
        "model": audit,
        "next_novel": result,
        "supplement_vs_conlit_only": incremental,
    }
    (output / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print("TEST", json.dumps(result))


if __name__ == "__main__":
    main()
