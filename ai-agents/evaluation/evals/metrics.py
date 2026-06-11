"""
Evaluation metrics for MindSafe LLM labeling accuracy.

Metrics computed:
- Precision, recall, F1 per event type (prosocial, aggressive, SEL, impossible)
- Boolean accuracy (direct_address, fear_intense)
- Enum accuracy (fantasy_level)
- MAE for language metrics (vocabulary_richness, etc.)
- Cohen's kappa for LLM-vs-heuristic agreement (called externally)
"""

import math
from typing import Any, Dict, List, Optional, Tuple

# ---------- Helpers ----------

def _safe_div(num: float, denom: float, default: float = 0.0) -> float:
    return num / denom if denom > 0 else default


def _list_overlap_f1(predicted: list[str], gold: list[str]) -> tuple[float, float, float]:
    """
    Soft overlap F1 for event lists.
    A predicted event "matches" a gold event if the gold string appears as a
    substring of the predicted string or vice versa (case-insensitive).
    Returns (precision, recall, f1).
    """
    if not gold and not predicted:
        return 1.0, 1.0, 1.0
    if not gold:
        return 0.0, 1.0, 0.0  # predicted something that shouldn't be there
    if not predicted:
        return 1.0, 0.0, 0.0  # missed everything

    def matches(a: str, b: str) -> bool:
        a, b = a.lower().strip(), b.lower().strip()
        return a in b or b in a

    tp_pred = sum(1 for p in predicted if any(matches(p, g) for g in gold))
    tp_gold = sum(1 for g in gold if any(matches(p, g) for p in predicted))

    precision = _safe_div(tp_pred, len(predicted))
    recall = _safe_div(tp_gold, len(gold))
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return precision, recall, f1


def _bool_accuracy(predicted: bool, gold: bool) -> float:
    return 1.0 if predicted == gold else 0.0


def _enum_accuracy(predicted: str, gold: str) -> float:
    return 1.0 if str(predicted).lower().strip() == str(gold).lower().strip() else 0.0


def _mae(predicted: float, gold: float) -> float:
    return abs(float(predicted) - float(gold))


# ---------- Per-example scoring ----------

def score_segment_events(
    predicted: dict[str, Any],
    gold: dict[str, Any],
) -> dict[str, Any]:
    """
    Score a single classify_segment_events prediction against gold.

    Returns a dict of per-field metrics.
    """
    result: dict[str, Any] = {}

    for field in ("prosocial_events", "aggressive_events", "sel_strategies", "impossible_events"):
        p_list = predicted.get(field, []) or []
        g_list = gold.get(field, []) or []
        prec, rec, f1 = _list_overlap_f1(p_list, g_list)
        result[f"{field}_precision"] = prec
        result[f"{field}_recall"] = rec
        result[f"{field}_f1"] = f1

    result["direct_address_accuracy"] = _bool_accuracy(
        predicted.get("direct_address", False), gold.get("direct_address", False)
    )
    result["fear_intense_accuracy"] = _bool_accuracy(
        predicted.get("fear_intense", False), gold.get("fear_intense", False)
    )
    result["fantasy_level_accuracy"] = _enum_accuracy(
        predicted.get("fantasy_level", "none"), gold.get("fantasy_level", "none")
    )

    return result


def score_language_metrics(
    predicted: dict[str, float],
    gold: dict[str, float],
) -> dict[str, float]:
    """MAE per language metric field."""
    fields = ["vocabulary_richness", "sentence_complexity",
              "advanced_vocabulary_fraction", "question_frequency"]
    result: dict[str, float] = {}
    for f in fields:
        if f in gold and gold[f] is not None:
            result[f"{f}_mae"] = _mae(predicted.get(f, 0.5), gold[f])
    return result


# ---------- Aggregate across examples ----------

def aggregate_metrics(per_example: list[dict[str, Any]]) -> dict[str, float]:
    """
    Average all numeric metrics across examples.
    Returns a flat dict of mean values.
    """
    if not per_example:
        return {}

    keys = per_example[0].keys()
    agg: dict[str, float] = {}
    for k in keys:
        values = [ex[k] for ex in per_example if isinstance(ex.get(k), (int, float)) and not math.isnan(ex[k])]
        if values:
            agg[f"mean_{k}"] = sum(values) / len(values)

    return agg


# ---------- Cohen's kappa ----------

def cohens_kappa(
    labels_a: list[Any],
    labels_b: list[Any],
    categories: list[Any] | None = None,
) -> float:
    """
    Cohen's kappa for two raters over a flat list of categorical labels.
    Used to measure LLM-vs-heuristic agreement on fantasy_level or fear_intense.
    """
    assert len(labels_a) == len(labels_b), "label lists must be same length"
    if not labels_a:
        return 0.0

    if categories is None:
        categories = list(set(labels_a) | set(labels_b))

    n = len(labels_a)
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    # Observed agreement
    p_o = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n

    # Expected agreement
    count_a = [sum(1 for x in labels_a if x == c) for c in categories]
    count_b = [sum(1 for x in labels_b if x == c) for c in categories]
    p_e = sum((count_a[i] / n) * (count_b[i] / n) for i in range(k))

    if abs(1.0 - p_e) < 1e-9:
        return 1.0 if abs(p_o - 1.0) < 1e-9 else 0.0

    return (p_o - p_e) / (1.0 - p_e)
