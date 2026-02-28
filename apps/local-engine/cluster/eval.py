"""cluster/eval.py — Clustering evaluation harness.

Computes precision, recall, and F1 against a set of human-labeled
item pairs. Used to compare Jaccard (v1) vs embeddings (v2).

Labeled pairs format (JSON list):
  [
    {"item_key_a": "key1", "item_key_b": "key2", "same_story": true},
    ...
  ]

Usage:
    from cluster.eval import evaluate_clustering, EvalResult
    result = evaluate_from_file(
        pairs_path="tests/fixtures/cluster_eval_pairs.json",
        predict_fn=my_predict_fn,
    )
    print(result)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class EvalPair:
    item_key_a: str
    item_key_b: str
    same_story: bool  # human label


@dataclass
class EvalResult:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    total: int

    def __str__(self) -> str:
        return (
            f"Precision={self.precision:.3f}  "
            f"Recall={self.recall:.3f}  "
            f"F1={self.f1:.3f}  "
            f"(TP={self.true_positives} FP={self.false_positives} "
            f"FN={self.false_negatives} TN={self.true_negatives})"
        )


def _safe_div(num: float, denom: float) -> float:
    return num / denom if denom > 0 else 0.0


def evaluate_clustering(
    pairs: list[EvalPair],
    predict_fn: Callable[[str, str], bool],
) -> EvalResult:
    """Evaluate clustering predictions against labeled pairs.

    Args:
        pairs:      List of labeled EvalPair objects.
        predict_fn: Function that takes (item_key_a, item_key_b) and returns
                    True if the model predicts they belong to the same story.

    Returns:
        EvalResult with precision, recall, F1, and confusion matrix counts.
    """
    tp = fp = fn = tn = 0

    for pair in pairs:
        predicted = predict_fn(pair.item_key_a, pair.item_key_b)
        if predicted and pair.same_story:
            tp += 1
        elif predicted and not pair.same_story:
            fp += 1
        elif not predicted and pair.same_story:
            fn += 1
        else:
            tn += 1

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)

    return EvalResult(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        total=len(pairs),
    )


def load_pairs(path: str | Path) -> list[EvalPair]:
    """Load labeled pairs from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EvalPair(
            item_key_a=entry["item_key_a"],
            item_key_b=entry["item_key_b"],
            same_story=bool(entry["same_story"]),
        )
        for entry in data
    ]


def evaluate_from_file(
    pairs_path: str | Path,
    predict_fn: Callable[[str, str], bool],
) -> EvalResult:
    """Convenience wrapper: load pairs from JSON file, evaluate, return result."""
    pairs = load_pairs(pairs_path)
    return evaluate_clustering(pairs, predict_fn)


# ─────────────────────────────────────────────────────────────────────────────
# Jaccard-based predict function (for baseline evaluation)
# ─────────────────────────────────────────────────────────────────────────────


def make_jaccard_predictor(
    title_map: dict[str, str],
    threshold: float = 0.25,
) -> Callable[[str, str], bool]:
    """Return a Jaccard-based predict_fn that uses item_key → title mapping.

    Args:
        title_map: dict mapping item_key → Hebrew title string.
        threshold: Jaccard threshold (> means same story).
    """
    from cluster.tokens import jaccard_similarity, tokenize

    def predict(key_a: str, key_b: str) -> bool:
        title_a = title_map.get(key_a, "")
        title_b = title_map.get(key_b, "")
        tokens_a = tokenize(title_a)
        tokens_b = tokenize(title_b)
        return jaccard_similarity(tokens_a, tokens_b) > threshold

    return predict


def make_cosine_predictor(
    embedding_map: dict[str, "np.ndarray"],
    threshold: float = 0.75,
) -> Callable[[str, str], bool]:
    """Return a cosine-based predict_fn using item_key → embedding mapping.

    Args:
        embedding_map: dict mapping item_key → numpy float32 array.
        threshold: Cosine similarity threshold (> means same story).
    """
    from cluster.embeddings import cosine_similarity

    def predict(key_a: str, key_b: str) -> bool:
        vec_a = embedding_map.get(key_a)
        vec_b = embedding_map.get(key_b)
        if vec_a is None or vec_b is None:
            return False
        return cosine_similarity(vec_a, vec_b) > threshold

    return predict
