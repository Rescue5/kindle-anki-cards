"""Reproduce a local, held-out modern novel check. Never include source books in a release."""

import argparse
import gzip
import hashlib
import json
import posixpath
import random
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from statistics import mean, quantiles
from urllib.request import Request, urlopen
from zipfile import ZipFile

DEFAULT_ROOT = Path(".app-data/novel-supplement")
RPV2 = Path(".app-data/openresearch/rp-v2")
TOKEN = re.compile(r"(?<!\w)[a-z]+(?:['-][a-z]+)*(?!\w)")
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-", "\u00ad": None})
# Fixed function-word filter from the RP-V2 external assessment.
CLOSED_CLASS = frozenset({
    "a", "an", "the", "this", "that", "these", "those", "i", "me", "my", "mine", "we",
    "us", "our", "ours", "you", "your", "yours", "he", "him", "his", "she", "her",
    "hers", "it", "its", "they", "them", "their", "theirs", "who", "whom", "whose",
    "which", "what", "some", "any", "every", "each", "both", "either", "neither",
    "no", "and", "or", "but", "nor", "if", "then", "than", "though", "although",
    "because", "while", "as", "at", "by", "for", "from", "in", "into", "of", "on",
    "onto", "over", "to", "under", "with", "without", "is", "am", "are", "was",
    "were", "be", "been", "being", "do", "does", "did", "have", "has", "had",
    "can", "could", "may", "might", "shall", "should", "will", "would", "must", "not", "so",
})


@dataclass(frozen=True)
class Novel:
    book_key: str
    title: str
    author: str
    publication_year: int
    genre: str
    license: str
    url: str
    file: str
    download_url: str
    sha256: str
    sections: tuple[int, int]


NOVELS = (
    Novel(
        "runtime", "Runtime", "Barbara Fister", 2023, "technology mystery", "CC BY-NC 4.0",
        "https://mlpp.pressbooks.pub/runtime/", "runtime.epub", "https://barbarafister.net/Runtime.epub",
        "9f30c51500597d711e519cdc4c94c52ac4e83633684b71e39f686f38cfe91906", (1, 24),
    ),
    Novel(
        "in-the-dark", "In the Dark", "Barbara Fister", 2020, "private-investigator mystery",
        "CC BY-NC 4.0", "https://mlpp.pressbooks.pub/inthedark/", "in-the-dark.epub",
        "https://barbarafister.net/In-the-Dark.epub",
        "ba6d5820c7a11547e080a77151316c95c31cae821bb309e9ac94c6a87d5b194d", (1, 28),
    ),
    Novel(
        "the-plainsrunner", "The Plainsrunner", "Jim Bowering", 2018, "science-fiction adventure",
        "CC BY-SA, version unspecified in the book; relicensed 2025",
        "https://greencomet.org/2025/03/04/creative-commons-the-plainsrunner-chapter-one/",
        "the-plainsrunner.epub", "https://greencomet.org/download/the-plainsrunner/?wpdmdl=28352",
        "795c7c79bc8b2afc253ed435dfdb47d582cf8de0ea21c777b7c64e658e1b1fd0", (5, 58),
    ),
    Novel(
        "vumani", "Vumani: A Novel", "Nume Mashinini", 2025, "historical and political fiction",
        "CC BY 4.0", "https://ujonlinepress.uj.ac.za/index.php/ujp/catalog/book/293", "vumani.xml",
        "https://ujonlinepress.uj.ac.za/index.php/ujp/catalog/download/293/1142/4723",
        "fc1ea35b5167e158005428ba8186beee6ef8564168997318f7a1677167ded356", (5, 1864),
    ),
    Novel(
        "utopia-five", "Utopia Five", "Anne Currie", 2019, "dystopian thriller",
        "CC BY-NC 4.0, with explicit non-commercial machine-learning use",
        "https://www.annecurrie.com/book-downloads", "utopia-five.pdf",
        "https://drive.google.com/uc?export=download&id=1hUJ4WPBv4wP3VVa-PKgN8I3qNb1b-G26",
        "e84df418fb65670151aa5dcceeb9890ecfb106d4d42fc66026a383588863d1a2", (7, 216),
    ),
    Novel(
        "view-across-the-bay", "The View across the Bay", "Daniel Meyer-Dinkgräfe", 2018,
        "family and psychological fiction", "CC BY-NC-ND 4.0",
        "https://dmd27.org/DMD%20View.pdf", "view-across-the-bay.pdf",
        "https://dmd27.org/DMD%20View.pdf",
        "8bba46dfd3f49b3eb63156597c230aaa9432e07dd5f0759f3d016595cea7c8ea", (1, 192),
    ),
)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def fetch(novel, root):
    source = root / novel.file
    if source.exists():
        raw = source.read_bytes()
    else:
        request = Request(novel.download_url, headers={"User-Agent": "NovelCoverageResearch/1.0"})
        with urlopen(request, timeout=30) as response:
            raw = response.read(16_000_001)
    if sha256(raw) != novel.sha256:
        raise ValueError(f"Source checksum changed for {novel.title}: {sha256(raw)}")
    if not source.exists():
        source.write_bytes(raw)
    return source


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).translate(TYPOGRAPHY).lower().split())


def local_name(element):
    return element.tag.rpartition("}")[2]


def epub_paragraphs(path, sections):
    first, last = sections
    pattern = re.compile(r"(?:chapter-|content)([0-9]+)(?:-.*)?\.xhtml")
    with ZipFile(path) as source:
        container = ET.fromstring(source.read("META-INF/container.xml"))
        opf = next(e.attrib["full-path"] for e in container.iter() if local_name(e) == "rootfile")
        package = ET.fromstring(source.read(opf))
        manifest = {e.attrib["id"]: e.attrib["href"] for e in package.iter() if local_name(e) == "item"}
        seen = []
        for entry in package.iter():
            if local_name(entry) != "itemref":
                continue
            href = manifest[entry.attrib["idref"]]
            match = pattern.fullmatch(posixpath.basename(href))
            if not match or not first <= int(match[1]) <= last:
                continue
            seen.append(int(match[1]))
            member = posixpath.normpath(posixpath.join(posixpath.dirname(opf), href))
            chapter = ET.fromstring(source.read(member))
            for para in chapter.iter():
                if local_name(para) in {"p", "li"}:
                    yield "".join(para.itertext())
        if seen != list(range(first, last + 1)):
            raise ValueError(f"Unexpected chapters in {path.name}: {seen}")


def vumani_paragraphs(path, sections):
    first, last = sections
    stories = ET.parse(path).findall(".//Document//Story")
    novel = list(stories[-1])
    if len(novel) != last or novel[first - 2].text.strip() != "Prologue":
        raise ValueError("Unexpected structure in Vumani publisher XML")
    for node in novel[first:last]:
        if node.tag in {"Body_Text", "First_Paragraph", "Quote_2", "Quote"}:
            yield "".join(node.itertext())


def pdf_blocks(path, pages):
    # Only PDF extraction needs the local research PyMuPDF installation.
    import pymupdf

    first, last = pages
    with pymupdf.open(path) as source:
        if len(source) < last:
            raise ValueError(f"Unexpected page count in {path.name}")
        for page in range(first, last):
            for *_, body, _, block_type in source[page].get_text(
                "blocks", flags=pymupdf.TEXTFLAGS_BLOCKS | pymupdf.TEXT_DEHYPHENATE, sort=True
            ):
                if block_type != 0:
                    continue
                lines = [line.strip() for line in body.splitlines()]
                yield " ".join(line for line in lines if line not in {"UTOPIA FIVE", "AE Currie"}
                               and not line.isdecimal())


def prose(novel, path):
    if path.suffix == ".epub":
        paragraphs = epub_paragraphs(path, novel.sections)
    elif path.suffix == ".xml":
        paragraphs = vumani_paragraphs(path, novel.sections)
    else:
        paragraphs = pdf_blocks(path, novel.sections)
    return [text for para in paragraphs if (text := " ".join(para.replace("\u200b", "").split()))]


def acquire(root):
    docs = []
    root.mkdir(parents=True, exist_ok=True)
    for novel in NOVELS:
        paragraphs = prose(novel, fetch(novel, root))
        isolated = ("\n\n".join(paragraphs) + "\n").encode()
        tokens = sum(len(TOKEN.findall(normalize(para))) for para in paragraphs)
        if tokens < 40_000:
            raise ValueError(f"Too few English word tokens in {novel.title}: {tokens}")
        name = f"{novel.book_key}.txt"
        (root / name).write_bytes(isolated)
        docs.append({
            **asdict(novel), "text": name, "text_sha256": sha256(isolated),
            "tokens": tokens, "blocks": len(paragraphs), "split": "external_heldout",
        })
    dump_json(root / "manifest.json", {
        "scope": "Local non-commercial research. Keep prose and downloads private.",
        "books": docs,
    })
    return docs


def load_model(path):
    raw = path.read_bytes()
    model = json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)
    return model, sha256(raw)


def fixed_key(model):
    rows, aliases = model["rows"], model["aliases"]

    @lru_cache(maxsize=150_000)
    def key(token):
        return token if token in rows else aliases.get(token, token)

    return key


def shortlist(keys, rows, column):
    groups = defaultdict(list)
    for key in keys:
        score = rows[key][column] if key in rows else None
        groups[float("-inf") if score is None else score].append(key)
    remaining = 5
    weights = {}
    for score in sorted(groups, reverse=True):
        tied = groups[score]
        weight = min(1, remaining / len(tied))
        weights.update(dict.fromkeys(tied, weight))
        remaining -= min(remaining, len(tied))
        if not remaining:
            break
    return weights


def index_panels(panel, key):
    authors = [item["author"] for item in panel["origins"]]
    if len(authors) != 24 or len(set(authors)) != 24:
        raise ValueError("Expected 24 distinct panel source authors")
    for mode in ("rare", "all"):
        lists = panel["lists"][mode]
        if len(lists) != 240 or any(len(terms) != 20 for terms in lists):
            raise ValueError(f"Expected 240 lists of 20 keys in {mode}")
        result = defaultdict(list)
        for i, terms in enumerate(lists):
            keys = list(dict.fromkeys(key(normalize(term)) for term in terms))
            keys = [term for term in keys if term not in CLOSED_CLASS and TOKEN.fullmatch(term)]
            if len(keys) >= 5:
                result[authors[i // 10]].append(keys)
        if len(result) != 24:
            raise ValueError(f"Source book lost all usable panels in {mode}")
        yield mode, result


def paired_interval(cells):
    rng = random.Random(82517)
    authors, sources = len(cells), len(cells[0])
    samples = []
    for _ in range(3000):
        out = rng.choices(range(authors), k=authors)
        origin = rng.choices(range(sources), k=sources)
        samples.append(mean(cells[a][b] for a in out for b in origin))
    cut = quantiles(samples, n=40, method="inclusive")
    return [cut[0], cut[-1]]


def benchmark(root, docs, config):
    original, original_sha = load_model(config.original)
    expanded, expanded_sha = load_model(config.expanded)
    candidates = config.panels.read_bytes()
    key = fixed_key(original)
    models = {"original": (original, "coverage"), "expanded": (expanded, "coverage"),
              "general": (original, "general_rate")}
    model_hashes = {"original": original_sha, "expanded": expanded_sha}
    if config.additional_model:
        additional, digest = load_model(config.additional_model)
        models["additional_only"] = additional, "coverage"
        model_hashes["additional_only"] = digest

    presence = {}
    for doc in docs:
        body = (root / doc["text"]).read_bytes()
        if sha256(body) != doc["text_sha256"]:
            raise ValueError(f"Isolated text changed: {doc['book_key']}")
        presence[doc["book_key"]] = {key(token) for token in TOKEN.findall(normalize(body.decode()))}
    packed = {book: sorted(keys) for book, keys in presence.items()}
    presence_bytes = json.dumps(packed, separators=(",", ":")).encode()
    (root / "presence.json.gz").write_bytes(gzip.compress(presence_bytes, mtime=0))
    modes = {}
    for mode, panels in index_panels(json.loads(candidates), key):
        orders = {
            name: [[shortlist(terms, model["rows"], model["columns"].index(column)) for terms in lists]
                   for lists in panels.values()]
            for name, (model, column) in models.items()
        }
        values = defaultdict(list)
        books = []
        for doc in docs:
            terms = presence[doc["book_key"]]
            cells = {
                name: [mean(sum(weight for term, weight in choices.items() if term in terms) / 5
                            for choices in group) for group in groups]
                for name, groups in orders.items()
            }
            values[doc["author"]].append(cells)
            books.append({"book_key": doc["book_key"], "author": doc["author"],
                          "p_at_5": {model: mean(scores) for model, scores in cells.items()}})
        authors = [
            {"author": author, "p_at_5": {
                model: mean(mean(book[model]) for book in group) for model in models
            }} for author, group in values.items()
        ]
        deltas = [
            [mean(book["expanded"][i] - book["original"][i] for book in group) for i in range(len(panels))]
            for group in values.values()
        ]
        modes[mode] = {
            "books": books, "authors": authors,
            "source_books": len(panels), "kept_lists": sum(map(len, panels.values())),
            "mean_p_at_5": {model: mean(item["p_at_5"][model] for item in authors) for model in models},
            "expanded_minus_original_95_ci": paired_interval(deltas),
        }
    dump_json(root / config.report, {
        "target": "Presence of the fixed key in the isolated full novel",
        "matching": "RP-V2 typography and tokenizer, original exact keys and frozen aliases only",
        "panel_sha256": sha256(candidates), "model_sha256": model_hashes,
        "presence_sha256": sha256(presence_bytes), "modes": modes,
    })
    return modes


def dump_json(path, content):
    path.write_bytes((json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode())


def phrase_report(root, docs, phrases):
    patterns = {phrase: re.compile(r"(?<![\w'-])" + re.escape(phrase) + r"(?![\w'-])")
                for phrase in phrases}
    books = {}
    for doc in docs:
        if doc["file"].endswith(".pdf"):
            books[doc["book_key"]] = None
            continue
        paragraphs = [normalize(para) for para in (root / doc["text"]).read_text(encoding="utf-8").split("\n\n")]
        books[doc["book_key"]] = {
            phrase: sum(len(pattern.findall(para)) for para in paragraphs)
            for phrase, pattern in patterns.items()
        }
    dump_json(root / "exact-phrases.json", {
        "matching": "Exact contiguous spelling within one structural paragraph. No morphological or sense matching.",
        "excluded": "PDF line wrapping does not preserve a reliable paragraph boundary.",
        "books": books,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--original", type=Path, default=RPV2 / "models/ranker.json.gz")
    parser.add_argument("--panels", type=Path, default=RPV2 / "reference/candidate-lists.json")
    parser.add_argument("--expanded", type=Path, help="Run the frozen external benchmark after acquisition.")
    parser.add_argument("--additional-model", type=Path, help="Optional table trained on new sources only.")
    parser.add_argument("--report", default="evaluation.json", help="Report filename inside --out.")
    parser.add_argument("--phrase", action="append", default=[], help="Count an exact phrase in EPUB/XML novels.")
    args = parser.parse_args()
    if args.report != Path(args.report).name or not args.report.endswith(".json"):
        parser.error("--report must be a JSON filename")
    phrases = sorted({normalize(phrase) for phrase in args.phrase})
    if any(len(phrase.split()) < 2 or any(not TOKEN.fullmatch(word) for word in phrase.split())
           for phrase in phrases):
        parser.error("--phrase must contain at least two space-separated English words")
    docs = acquire(args.out)
    for doc in docs:
        print(doc["book_key"], doc["tokens"], doc["text_sha256"])
    if args.expanded:
        modes = benchmark(args.out, docs, args)
        for mode, row in modes.items():
            print(mode, row["mean_p_at_5"], row["expanded_minus_original_95_ci"])
    if phrases:
        phrase_report(args.out, docs, phrases)


if __name__ == "__main__":
    main()
