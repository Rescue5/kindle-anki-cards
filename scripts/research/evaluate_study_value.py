"""Fit a human-utility baseline and audit the optional correction on held-out books."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from nltk.stem import SnowballStemmer

from .evaluate_reading_priority import (
    SEED,
    author_means,
    author_split,
    mean_interval,
    measure,
    read_targets,
    source_panels,
)
from .reading_priority import Model, features, load_evidence
from .study_value import Reference, UtilityModel, load_utilities, priority_order, score_form


def midranks(values):
    """Average ranks for ties, as required for Spearman correlation."""
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    ranks = np.cumsum(counts) - (counts - 1) / 2
    return ranks[inverse]


def spearman(actual, estimated):
    return float(np.corrcoef(midranks(actual), midranks(estimated))[0, 1])


def lexical_training(index, utilities):
    stemmer = SnowballStemmer("english")
    words = sorted(w for w in utilities if re.fullmatch("[a-z]+", w))
    def bucket(word):
        stem = stemmer.stem(word)
        digest = hashlib.sha256(f"{SEED}/{stem}".encode()).digest()
        return int.from_bytes(digest[:4], "big") % 5

    held = np.array([bucket(w) == 0 for w in words])
    y = np.asarray([utilities[w] for w in words])
    evidence = [index.lookup(w) for w in words]
    variants = {}
    selected = None
    for variant in ("frequency", "books", "combined", "combined_cefr"):
        x = np.asarray([features(e, variant) for e in evidence])
        x = np.column_stack([np.ones(len(x)), x])
        train_x = x[~held]
        penalty = np.diag([0.] + [.001] * (x.shape[1] - 1))
        weights = np.linalg.solve(train_x.T @ train_x / len(train_x) + penalty,
                                  train_x.T @ y[~held] / len(train_x))
        prediction = np.clip(x @ weights, 0, 1)
        variants[variant] = {
            "spearman": spearman(y[held], prediction[held]),
            "mae": float(np.abs(prediction[held] - y[held]).mean()),
        }
        if variant == "combined_cefr":
            selected = {
                "feature_variant": variant, "weights": weights[1:].tolist(),
                "intercept": float(weights[0]),
                "residual_scale": float(np.std((y - prediction)[~held])),
                # The internal study candidate and the unadjusted reading baseline
                # serve different objectives. Both remain callable on the same data.
                "residual_cap": .10, "strength": .5,
            }
    return selected, {
        "source": "Wang et al., human Value Learning only",
        "table_unique_clean": len(utilities), "training_single_forms": int((~held).sum()),
        "held_single_forms": int(held.sum()), "masked_evaluation": variants,
    }


def exact_phrases(tokens, trie):
    found = set()
    for start, token in enumerate(tokens):
        if token not in trie:
            continue
        node = trie[token]
        end = start + 1
        while end < len(tokens) and tokens[end] in node:
            node = node[tokens[end]]
            if "" in node:
                found.add(node[""])
            end += 1
    return found


def build_reference(books, train, valid, forms, index, utilities):
    trie = {}
    for phrase in utilities.keys() | index.cefr.keys():
        if not re.fullmatch(r"[a-z]+(?:'[a-z]+)?(?: [a-z]+(?:'[a-z]+)?)+", phrase):
            continue
        node = trie
        for token in phrase.split():
            node = node.setdefault(token, {})
        node[""] = phrase
    counts = Counter()
    phrase_sets = [exact_phrases(tokens, trie) for _, _, tokens in books]
    for i in train:
        counts.update((set(books[i][2]) - {"|"}) | phrase_sets[i])
    # Estimate the prior for unobserved, uncovered forms on different authors.
    missing = [w for w in forms if re.fullmatch("[a-z]+", w) and w not in counts
               and w not in index.books and index.lookup(w).zipf == 0]
    target_sets = [set(tokens) for _, _, tokens in books]
    outcomes = np.asarray([sum(w in seen for w in missing) / len(missing) for seen in target_sets])
    rate = float(author_means(outcomes, valid, books).mean())
    return {"books": len(train), "scope": "ELTeC, обучающие романы, первые 20 000 токенов",
            "unseen_single_rate": rate, "counts": dict(sorted(counts.items()))}, phrase_sets, len(missing)


def transfer_audit(args, index, utilities, auxiliary):
    models = json.loads((args.transfer / "transfer-models.json").read_text(encoding="utf-8"))
    primary = json.loads((args.transfer / "reading-model.json").read_text(encoding="utf-8"))
    primary = Model(**primary)
    fallback = Model(**models.get("frequency_if_missing_books", models["frequency"]))
    forms = source_panels(args.source_zip)
    books = read_targets(args.eltec_dir, args.metadata, ordered=True)
    train, valid, test = author_split(books)
    ref, phrase_sets, missing = build_reference(books, train, valid, forms, index, utilities)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "reference.json").write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
    ref = Reference(**ref)
    target = [set(tokens) for _, _, tokens in books]
    y = np.asarray([[w in body for w in forms] for body in target], dtype=int)
    def rank_scores(rows):
        # Use the actual CLI ordering, including its tie-breaks and provisional groups.
        order = sorted(range(len(rows)), key=lambda i: priority_order(rows[i]))
        scores = np.empty(len(rows))
        scores[order] = -np.arange(len(rows))
        return scores

    all_runs = {}
    for name, reference, strength in (("preliminary_6", None, 0), ("reference", ref, 0),
                                      ("reference_plus_human", ref, .5)):
        model = UtilityModel(**{**auxiliary, "strength": strength})
        rows = [score_form(index, w, primary, fallback, utilities, model, reference=reference)
                for w in forms]
        metrics = author_means(measure(y, rank_scores(rows)), test, books)
        if name == "reference":
            main = metrics
        all_runs[name] = {"nDCG@5": float(metrics[:, 0].mean()),
                          "precision@5": float(metrics[:, 1].mean())}
        if name == "reference_plus_human":
            all_runs[name]["paired_ndcg_delta_vs_reference"] = mean_interval(metrics[:, 0] - main[:, 0])
    phrases = sorted(w for w in ref.counts if " " in w)
    phrase_prob = np.array([(ref.counts[w] + .5) / (ref.books + 1) for w in phrases])
    per_book = np.asarray([[int(w in seen) for w in phrases] for seen in phrase_sets])
    teacher = None
    if args.teachers:
        teacher = teacher_check(args.teachers, index, primary, fallback, utilities, model, ref)
    return {"forms_with_adjustment": sum(r.adjustment is not None for r in rows),
            "source_forms": len(forms), "uncovered_forms_for_validation_prior": missing,
            "unseen_single_rate": ref.unseen_single_rate, "measured_phrases": len(phrases),
            "spearman_phrase_reach_on_test": spearman(
                author_means(per_book, test, books).mean(axis=0), phrase_prob),
            "diagnostic_repeat_on_same_held_books": all_runs, "teachers": teacher}


def teacher_check(path, index, primary, fallback, utilities, model, ref):
    import csv
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            entry = score_form(index, r["Word"], primary, fallback, utilities, model, reference=ref)
            if None not in (entry.score, entry.reading_score, entry.human_utility) and entry.evidence.zipf:
                rows.append([float(r["Utility_All"]), entry.evidence.zipf, entry.reading_score,
                             entry.human_utility, entry.score])
    columns = np.asarray(rows).T
    rng = np.random.default_rng(SEED)
    delta = []
    for _ in range(2000):
        truth, _, reading, _, combined = columns[:, rng.integers(len(rows), size=len(rows))]
        delta.append(spearman(truth, combined) - spearman(truth, reading))
    return {"complete_cases": len(rows), "range": [min(columns[0]), max(columns[0])],
            "paired_item_bootstrap_95_delta_combined_minus_reading":
                np.quantile(delta, [.025, .975]).tolist(),
            "spearman": {k: spearman(columns[0], col) for k, col in zip(
                ("wordfreq", "book_model", "direct_native_utility", "combined_study"), columns[1:])}}


def run(args):
    index = load_evidence(args.cyp, args.cefr)
    utilities = load_utilities(args.utilities)
    model, report = lexical_training(index, utilities)
    report["transfer_sensitivity"] = transfer_audit(args, index, utilities, model)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("utility-model", model), ("utility-results", report)):
        (args.output / f"{name}.json").write_text(json.dumps(content, indent=2) + "\n",
                                                  encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("cyp", "source-zip", "eltec-dir", "metadata", "utilities", "transfer", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--cefr", type=Path, action="append", default=[])
    parser.add_argument("--teachers", type=Path, help="Dang et al., Appendix 10, extracted TSV.")
    run(parser.parse_args())
