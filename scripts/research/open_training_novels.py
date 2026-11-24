"""Build private novel-level lemma-presence records from licensed source snapshots."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import platform
import re
import unicodedata
from collections import Counter
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

import nltk
from bs4 import BeautifulSoup
from bs4 import __version__ as bs4_version
from nltk.corpus import wordnet
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import TreebankWordTokenizer

SCP = "https://scpwiki.com"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"
WORD = re.compile(r"[a-z]+(?:['-][a-z]+)*")
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-"})
POS = {"J": "a", "N": "n", "R": "r", "V": "v"}
HOLDOUT_AUTHORS = {
    "barbarafister", "jimbowering", "kathywollenberg", "numemashinini",
    "annecurrie", "danielmeyerdinkgrafe",
}
PINNED = {
    "CONLIT_META.csv": "61de1b342d4a7cb6e7388512a1d03b808f940019b51be8d491d0a4793e30da46",
    "CONLIT_WORDCOUNTS.zip": "776c9638d773f0316e361f145248aa3817698584a4b74898574c7cb243ccf6c1",
    "split.json": "414390c844ec498d993330db848d8b35cce402201dad99ce718c764e42890fc0",
    "ranker.json.gz": "d75e5ba0b3cd3a21f449955b627e48f9344b95a9ad1694f2d2c7c4956f24e686",
}


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def pinned(path: Path) -> Path:
    if sha256(path) != PINNED[path.name]:
        raise ValueError(f"Unexpected SHA-256 for {path.name}")
    return path


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(TYPOGRAPHY)


def identity(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def pages(directory: Path) -> tuple[dict, list[list[str]], dict]:
    hub_file = directory / "bury-hub-official.html"
    hub = BeautifulSoup(hub_file.read_bytes(), "html.parser").select_one("#page-content")
    if hub is None or "Storyline complete as of 10/10/2022!" not in hub.get_text():
        raise ValueError("Publication evidence for Bury the Survivors unavailable")
    links = {}
    for link in hub.select("h2 a[href]"):
        match = re.fullmatch(r"/(\d+)-[a-z-]+", link["href"])
        if match:
            number = int(match[1])
            if number in links:
                raise ValueError(f"Duplicate chapter number {number}")
            links[number] = link["href"]
    if sorted(links) != list(range(18)):
        raise ValueError("Expected the complete 18-chapter Bury the Survivors serial")

    chapters, evidence = [], []
    for number, slug in sorted(links.items()):
        source = directory / f"bury-{number:02}.html"
        page = BeautifulSoup(source.read_bytes(), "html.parser")
        body = page.select_one("#page-content")
        credit = body.select_one(f'.licensebox a[href="{LICENSE_URL}"]')
        if page.html.get("lang") != "en" or not credit or "by HarryBlank" not in credit.parent.get_text():
            raise ValueError(f"Missing English or CC authorship evidence: {slug}")
        first_heading = body.find("h1")
        navigation = body.select_one(".earthworm")
        heading_container = first_heading
        while heading_container.parent is not body:
            heading_container = heading_container.parent
        siblings = body.find_all(recursive=False)
        narrative = siblings[siblings.index(heading_container) + 1 : siblings.index(navigation)]
        paragraphs = []
        for tag in narrative:
            for removed in tag.select("script, style, sup, .image-container, .footnotes-footer"):
                removed.decompose()
            for linebreak in tag.find_all("br"):
                linebreak.replace_with(" ")
            for paragraph in ([tag] if tag.name == "p" else tag.find_all("p")):
                text = " ".join(paragraph.get_text().split())
                if text:
                    paragraphs.append(text)
        chapters.append(paragraphs)
        evidence.append({
            "url": f"{SCP}{slug}", "source_file": source.name, "source_sha256": sha256(source),
            "chapter": number, "paragraphs": len(paragraphs),
        })
    book = {
        "id": "scp-harryblank-bury-the-survivors-2022",
        "title": "Bury the Survivors", "title_aliases": ["The Breach Goes On: Bury the Survivors"],
        "author": "Harry Blank", "author_first": "Harry", "author_last": "Blank",
        "author_aliases": [{"author_first": "", "author_last": "HarryBlank"}],
        "publication_year": 2022, "split": "train", "license": "CC BY-SA 3.0",
        "source_url": f"{SCP}/bury-the-survivors-hub",
    }
    return book, chapters, {
        "edition": "Complete SCP Wiki web serial, completed 2022-10-10",
        "license_url": LICENSE_URL, "license_guide": f"{SCP}/licensing-guide",
        "source_hub_file": hub_file.name, "source_hub_sha256": sha256(hub_file),
        "extraction": "Chapter paragraphs after first heading and before navigator; "
                      "preserve narrative including in-world documents; omit headings, "
                      "image content, footnote markers, introductory labels and page chrome.",
        "chapters": evidence,
    }


def training_vocabulary(archive_path: Path, split: dict) -> set[str]:
    words = set()
    with ZipFile(archive_path, metadata_encoding="utf-8") as archive:
        for book in [*split["train"], *split["valid"]]:
            member = f"CONLIT_WORDCOUNTS/{book['id']}_unigrams.csv"
            with archive.open(member) as raw, TextIOWrapper(raw, encoding="utf-8-sig") as stream:
                rows = csv.reader(stream)
                if next(rows) != ["Lemma", "Count"]:
                    raise ValueError(f"Unexpected CONLIT columns in {member}")
                for lemma, count in rows:
                    key = normalized(lemma).lower()
                    if WORD.fullmatch(key) and int(count) > 0:
                        words.add(key)
    return words


def verify_independence(book: dict, metadata: list[dict], split: dict) -> list[str]:
    author_aliases = [
        identity(f"{names['author_first']} {names['author_last']}")
        for names in [book, *book["author_aliases"]]
    ]
    titles = {identity(title) for title in [book["title"], *book["title_aliases"]]}
    if set(author_aliases) & HOLDOUT_AUTHORS:
        raise ValueError("External holdout author would enter training")
    for row in metadata:
        author = identity(f"{row['Author_First']} {row['Author_Last']}")
        title = identity(row["Work_Title"])
        if author in author_aliases or title in titles:
            raise ValueError(f"New novel overlaps CONLIT metadata: {row['ID']}")
    for group, members in split.items():
        if not isinstance(members, list):
            continue
        for row in members:
            if not isinstance(row, dict) or "author" not in row:
                continue
            surname_first = row["author"].split("|", 1)
            if identity(" ".join(reversed(surname_first))) in author_aliases:
                raise ValueError(f"New novel overlaps frozen author in {group}")
    return ["full CONLIT metadata", "frozen split (all groups)", "external holdout authors"]


def measure(chapters: list[list[str]], vocabulary: set[str], aliases: dict) -> tuple[list[str], dict]:
    words = set()
    chapter_hashes = set()
    stats = Counter()
    tokenizer = TreebankWordTokenizer()
    lemmatizer = WordNetLemmatizer()
    word_counts = []
    for chapter in chapters:
        body = "\n".join(chapter)
        digest = hashlib.sha256(body.encode()).hexdigest()
        if digest in chapter_hashes:
            raise ValueError("Identical extracted chapters")
        chapter_hashes.add(digest)
        chapter_words = 0
        for paragraph in chapter:
            for token, tag in nltk.pos_tag(tokenizer.tokenize(normalized(paragraph))):
                surface = token.lower()
                if not WORD.fullmatch(surface):
                    continue
                chapter_words += 1
                if tag in {"NNP", "NNPS"} or (len(token) > 1 and token.isupper()):
                    stats["proper_or_acronym_tokens"] += 1
                    continue
                candidate = lemmatizer.lemmatize(surface, POS[tag[0]]) if tag[0] in POS else surface
                candidate = aliases.get(candidate, candidate)
                if candidate in vocabulary:
                    words.add(candidate)
                    stats["matched_tokens"] += 1
                else:
                    stats["unmatched_tokens"] += 1
        if chapter_words < 200:
            raise ValueError("Chapter too short to be a complete source snapshot")
        word_counts.append(chapter_words)
    if sum(word_counts) < 40_000:
        raise ValueError("Extracted text does not reach 40,000 prose word tokens")
    language_probes = {"the", "and", "i", "you", "she", "had", "was", "with"}
    if not words.intersection(language_probes) >= {"the", "and", "i", "you", "with"}:
        raise ValueError("Missing basic English function-word evidence")
    return sorted(words), {"chapter_word_counts": word_counts, "word_count": sum(word_counts),
                           "unique_lemmas": len(words), "tokens": dict(stats)}


def resources() -> dict:
    tagger = Path(str(nltk.data.find("taggers/averaged_perceptron_tagger_eng/")))
    wordnet_archive = Path(str(nltk.data.find("corpora/wordnet.zip")))
    return {
        "python": platform.python_version(), "beautifulsoup4": bs4_version, "nltk": nltk.__version__,
        "wordnet": wordnet.get_version(), "wordnet_sha256": sha256(wordnet_archive),
        "pos_model": {f.name: sha256(f) for f in sorted(tagger.glob("*.json"))},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieved", required=True, help="Date of the local source snapshots")
    args = parser.parse_args()
    meta_path = pinned(args.cache / "CONLIT_META.csv")
    archive = pinned(args.cache / "CONLIT_WORDCOUNTS.zip")
    split = json.loads(pinned(args.kit / "reference/split.json").read_bytes())
    with gzip.open(pinned(args.kit / "models/ranker.json.gz"), "rb") as compressed:
        aliases = json.load(compressed)["aliases"]
    with meta_path.open(encoding="utf-8-sig", newline="") as source:
        metadata = list(csv.DictReader(source))
    book, chapters, evidence = pages(args.out / "source")
    evidence["independence_verified_against"] = verify_independence(book, metadata, split)
    vocabulary = training_vocabulary(archive, split)
    book["lemmas"], stats = measure(chapters, vocabulary, aliases)
    book["word_count"] = stats["word_count"]
    evidence.update({**book, **stats, "lemmas": None, "retrieved": args.retrieved})
    del evidence["lemmas"]
    manifest = {
        "schema_version": 1, "input_sha256": PINNED, "software": resources(),
        "normalization": "Treebank tokenizer and Perceptron POS tagger on prose paragraphs, "
                         "WordNet POS lemmatization, suppress proper names and upper-case acronyms, "
                         "apply frozen RP-V2 aliases, restrict to positive CONLIT train+validation lemmas.",
        "vocabulary_lemmas": len(vocabulary), "books": [evidence],
    }
    write_json(args.out / "training-presence.json", {"schema_version": 1, "books": [book]})
    write_json(args.out / "source-manifest.json", manifest)
    print(book["title"], stats)


if __name__ == "__main__":
    main()
