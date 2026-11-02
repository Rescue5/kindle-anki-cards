"""Build the bundled English -> Russian dictionary from the Russian Wiktionary.

Input is ``ru-extract.jsonl.gz`` from kaikki.org (Wiktextract's extraction of
ru.wiktionary.org). Only English entries are kept, each with its part of
speech and a few short Russian meanings, and written to a small read-only
SQLite file that the app ships with:

    python packaging/build_dictionary.py path/to/ru-extract.jsonl.gz

The output is derived from Wiktionary and is licensed CC BY-SA 4.0; see
``kindle_vocab_app/data/README.md``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "kindle_vocab_app" / "data" / "en_ru_wiktionary.sqlite"

# Wiktextract part-of-speech names -> WordNet codes used by the optimizer
# ("p" marks phrases such as phrasal verbs and idioms).
POS_CODES = {
    "noun": "n",
    "verb": "v",
    "adj": "a",
    "adv": "r",
    "phrase": "p",
    "prep": "x",
    "pron": "x",
    "conj": "x",
    "intj": "x",
    "interj": "x",
    "num": "x",
    "abbrev": "x",
    "particle": "x",
    "article": "x",
}
MAX_SENSES = 4
MAX_GLOSS = 90
# Grammatical cross-references ("мн. ч. от cat") carry no meaning of their own.
FORM_OF = re.compile(r"^(форма|мн\.|ед\.|прош\.|наст\.|буд\.|3-е|2-е|1-е|причастие|деепричастие|сравн\.|превосх\.|то же, что|см\.)", re.IGNORECASE)
SPACES = re.compile(r"\s+")


def clean_gloss(text: str) -> str:
    gloss = SPACES.sub(" ", text).strip().strip(";,. ")
    if not gloss or FORM_OF.match(gloss):
        return ""
    if len(gloss) > MAX_GLOSS:
        gloss = gloss[:MAX_GLOSS].rsplit(" ", 1)[0].rstrip(";,") + "…"
    return gloss


def english_entries(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if '"lang_code": "en"' not in line:
                continue
            entry = json.loads(line)
            if entry.get("lang_code") == "en":
                yield entry


def build(source: Path, output: Path) -> dict[str, int]:
    merged: dict[tuple[str, str], list[str]] = {}
    skipped = Counter()
    for entry in english_entries(source):
        word = SPACES.sub(" ", str(entry.get("word") or "")).strip().lower()
        pos = POS_CODES.get(str(entry.get("pos") or ""))
        if not word or pos is None:
            skipped["pos"] += 1
            continue
        senses = merged.setdefault((word, pos), [])
        for sense in entry.get("senses") or []:
            for gloss in sense.get("glosses") or []:
                cleaned = clean_gloss(str(gloss))
                if cleaned and cleaned not in senses and len(senses) < MAX_SENSES:
                    senses.append(cleaned)
    rows = [(word, pos, "\n".join(senses)) for (word, pos), senses in merged.items() if senses]
    skipped["empty"] = len(merged) - len(rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    with sqlite3.connect(output) as db:
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("CREATE TABLE entries (word TEXT NOT NULL, pos TEXT NOT NULL, meanings TEXT NOT NULL, PRIMARY KEY (word, pos)) WITHOUT ROWID")
        db.executemany("INSERT INTO entries VALUES (?, ?, ?)", sorted(rows))
        db.executemany("INSERT INTO meta VALUES (?, ?)", [
            ("source", "Russian Wiktionary via Wiktextract (kaikki.org)"),
            ("license", "CC BY-SA 4.0, Wiktionary contributors"),
            ("built_at", datetime.now(UTC).strftime("%Y-%m-%d")),
            ("entries", str(len(rows))),
        ])
    db.close()
    with sqlite3.connect(output) as db:
        db.execute("VACUUM")
    db.close()
    return {"entries": len(rows), "words": len({word for word, _, _ in rows}), **skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="ru-extract.jsonl.gz from kaikki.org")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    stats = build(args.source, args.output)
    size = args.output.stat().st_size / 1_000_000
    print(f"{args.output.name}: {stats['entries']} entries, {stats['words']} words, {size:.1f} MB; skipped {stats.get('pos', 0)} by part of speech, {stats.get('empty', 0)} without meanings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
