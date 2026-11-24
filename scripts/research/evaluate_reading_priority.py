"""Measure cross-book transfer of exact forms on public texts, with authors kept together."""

import argparse
import csv
import hashlib
import json
import random
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from kindle_vocab_app.ranking import WordFacts, rank

from .reading_priority import features, load_evidence

BOOKS = (
    "austen-emma", "austen-persuasion", "austen-sense", "carroll-alice",
    "chesterton-ball", "chesterton-brown", "chesterton-thursday",
    "edgeworth-parents", "melville-moby_dick",
)
# Authors also present in the CYP-LEX bibliography (all ages) or the source shelf.
EXCLUDED = {
    "ENG18471", "ENG18570", "ENG18481", "ENG18530", "ENG18540", "ENG18610",
    "ENG18660", "ENG18721", "ENG18760", "ENG18900", "ENG18952", "ENG19090",
    "ENG19120", "ENG18652", "ENG18890", "ENG19020", "ENG19060", "ENG19080",
}
TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?")
TEI = "{http://www.tei-c.org/ns/1.0}"
VARIANTS = ("frequency", "books", "combined", "combined_cefr")
SEED = 20261124


def tokenize(text):
    return TOKEN.findall(text.casefold().replace("’", "'"))


def source_panels(archive):
    """Choose word types from different books before observing any target outcome."""
    with zipfile.ZipFile(archive) as z:
        words = set()
        for name in BOOKS:
            data = z.read(f"gutenberg/{name}.txt").decode("latin1")
            # Omit the short NLTK title/author line.
            words.update(tokenize(data.partition("\n")[2]))
    words = sorted(words)
    random.Random(SEED).shuffle(words)
    return words[: min(8000, len(words)) // 20 * 20]


def read_targets(root, metadata, *, ordered=False):
    with metadata.open(encoding="utf-8-sig", newline="") as f:
        author = {r["xmlid"]: r["author-name"] for r in csv.DictReader(f, delimiter="\t")}
    books = []
    for path in sorted(root.glob("*.xml")):
        xml = ET.parse(path).getroot()
        book_id = xml.attrib["{http://www.w3.org/XML/1998/namespace}id"]
        if book_id in EXCLUDED:
            continue
        body = xml.find(f"{TEI}text/{TEI}body")
        if body is None:
            raise ValueError(f"Missing book body: {book_id}")
        tokens = []
        token_count = 0
        for paragraph in body.iter(f"{TEI}p"):
            content = "".join(paragraph.itertext()).casefold().replace("’", "'")
            last = 0
            if ordered:
                tokens.append("|")
            for match in TOKEN.finditer(content):
                if ordered and last and not content[last:match.start()].isspace():
                    tokens.append("|")
                tokens.append(match[0])
                token_count += 1
                last = match.end()
                if token_count == 20000:
                    break
            if token_count == 20000:
                break
        if token_count == 20000:
            books.append((book_id, author[book_id], tokens if ordered else set(tokens)))
    if len(books) < 30:
        raise ValueError("Too few complete 20,000-token targets; verify the ELTeC directory.")
    return books


def author_split(books):
    authors = sorted({a for _, a, _ in books}, key=lambda a: hashlib.sha256(
        f"{SEED}/{a}".encode()
    ).digest())
    cut1, cut2 = len(authors) // 2, len(authors) * 3 // 4
    groups = [set(authors[:cut1]), set(authors[cut1:cut2]), set(authors[cut2:])]
    return [[i for i, (_, a, _) in enumerate(books) if a in group] for group in groups]


def fit_logistic(x, outcome):
    """Ridge logistic on soft labels (mean binary outcome per training author)."""
    x = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(x.shape[1])
    penalty = np.diag([0.] + [0.001] * (x.shape[1] - 1))
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(x @ beta, -40, 40)))
        grad = x.T @ (p - outcome) / len(x) + penalty @ beta
        hessian = (x.T * (p * (1 - p))) @ x / len(x) + penalty
        update = np.linalg.solve(hessian, grad)
        beta -= update
        if np.max(np.abs(update)) < 1e-8:
            break
    return beta


def author_means(values, ids, books):
    groups = defaultdict(list)
    for i in ids:
        groups[books[i][1]].append(values[i])
    return np.asarray([np.mean(groups[a], axis=0) for a in sorted(groups)])


def measure(outcomes, scores):
    panels = outcomes.reshape(len(outcomes), -1, 20)
    # Ties use the same seed-fixed source order for every variant.
    order = np.argsort(-scores.reshape(-1, 20), axis=1, kind="stable")[:, :5]
    hits = np.take_along_axis(panels, order[None, :, :], axis=2)
    discount = 1 / np.log2(np.arange(2, 7))
    ideal = np.r_[0, np.cumsum(discount)][np.minimum(5, panels.sum(axis=2))]
    valid = ideal > 0
    dcg = (hits * discount).sum(axis=2)
    ndcg = np.divide(dcg, ideal, out=np.zeros_like(dcg), where=valid)
    return np.column_stack([ndcg.sum(axis=1) / valid.sum(axis=1), hits.mean(axis=(1, 2)),
                            ((outcomes - scores) ** 2).mean(axis=1), valid.mean(axis=1)])


def mean_interval(differences):
    rng = np.random.default_rng(SEED)
    draws = rng.choice(differences, size=(4000, len(differences)), replace=True).mean(axis=1)
    return [float(differences.mean()), *map(float, np.quantile(draws, [.025, .975]))]


def run(args):
    index = load_evidence(args.cyp, args.cefr)
    forms = source_panels(args.source_zip)
    evidence = [index.lookup(form) for form in forms]
    books = read_targets(args.eltec_dir, args.metadata)
    y = np.asarray([[w in tokens for w in forms] for _, _, tokens in books], dtype=int)
    train, valid, test = author_split(books)
    training_mean = author_means(y, train, books).mean(axis=0)
    report = {
        "seed": SEED, "panel_size": 20, "forms": len(forms),
        "covered": {"books": sum(e.books is not None for e in evidence),
                    "frequency": sum(e.zipf > 0 for e in evidence),
                    "cefr": sum(e.cefr is not None for e in evidence)},
        "splits": {name: {"authors": len({books[i][1] for i in ids}),
                          "book_ids": [books[i][0] for i in ids]}
                   for name, ids in zip(("train", "validation", "test"), (train, valid, test))},
        "metrics": ["nDCG@5 among panels with hits", "precision@5", "Brier", "panels with hits"],
        "variants": {},
    }
    models, test_metrics = {}, {}
    snapshot = datetime(2026, 11, 24, tzinfo=UTC)
    common_context = {"synset_count": 1, "pos_count": 1, "warnings": frozenset(),
                      "proper_noun": False, "lookups": ((snapshot, "synthetic-book"),),
                      "reading_books": frozenset({"synthetic-book"})}
    old_scores = np.array([rank(WordFacts(lemma_zipf=e.zipf, form_zipf=e.zipf, **common_context),
                                snapshot, mode="learning").score for e in evidence])
    old_metrics = measure(y, old_scores)
    report["controlled_current_rank_one_lookup"] = {
        "nDCG@5": float(author_means(old_metrics, test, books).mean(axis=0)[0]),
        "precision@5": float(author_means(old_metrics, test, books).mean(axis=0)[1]),
        "control": "one synthetic lookup, same active book/date and lexical flags; rank() only",
    }
    for variant in VARIANTS:
        x = np.asarray([features(e, variant) for e in evidence], dtype=float)
        beta = fit_logistic(x, training_mean)
        models[variant] = {"variant": variant, "intercept": beta[0], "weights": beta[1:].tolist()}
        scores = 1 / (1 + np.exp(-np.clip(x @ beta[1:] + beta[0], -40, 40)))
        metrics = measure(y, scores)
        test_metrics[variant] = author_means(metrics, test, books)
        report["variants"][variant] = {
            "validation": author_means(metrics, valid, books).mean(axis=0).tolist(),
            "test": test_metrics[variant].mean(axis=0).tolist(),
        }
    def validation(name):
        return report["variants"][name]["validation"][0]
    single = max(VARIANTS[:2], key=validation)
    full = max(VARIANTS[2:], key=validation)
    delta = mean_interval(test_metrics[full][:, 0] - test_metrics[single][:, 0])
    report.update({"validation_single": single, "validation_combination": full,
                   "test_delta_ndcg_and_author_bootstrap_95": delta})
    # The paired test adjudicates a pre-declared promotion rule. Raw results remain available.
    selected = full if delta[0] >= .03 and delta[1] > 0 else single
    report["selected_transfer_model"] = selected
    # A missing book-table row is informative as a cohort. The frequency fallback
    # will run precisely in that cohort; calibrate it on the corresponding cases.
    missing_books = np.array([e.books is None and e.zipf > 0 for e in evidence])
    freq_x = np.array([features(e, "frequency") for e in evidence])[missing_books]
    conditional = fit_logistic(freq_x, training_mean[missing_books])
    default = models["frequency"]
    def brier(coefficients, group):
        pred = 1 / (1 + np.exp(-(freq_x @ coefficients[1:] + coefficients[0])))
        losses = ((y[:, missing_books] - pred) ** 2).mean(axis=1)
        return float(author_means(losses, group, books).mean())
    general = np.array([default["intercept"], *default["weights"]])
    losses = {name: [brier(coef, valid), brier(coef, test)]
              for name, coef in (("general", general), ("conditional", conditional))}
    if losses["conditional"][0] < losses["general"][0]:
        models["frequency_if_missing_books"] = {
            "variant": "frequency", "intercept": conditional[0], "weights": conditional[1:].tolist()}
    report["fallback"] = {"complete_frequency_only_forms": int(missing_books.sum()),
                          "brier_validation_then_test": losses,
                          "use_conditional": "frequency_if_missing_books" in models}
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, data in {"transfer-results": report, "reading-model": models[selected],
                           "transfer-models": models}.items():
        (args.output / f"{filename}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("cyp", "source-zip", "eltec-dir", "metadata", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--cefr", type=Path, action="append", default=[])
    run(parser.parse_args())
