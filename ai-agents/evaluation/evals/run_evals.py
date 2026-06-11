"""
MindSafe Clinical Eval Harness

Runs LLM labeling against gold_set.jsonl and emits:
  - eval_report.json  (machine-readable, for CI gate)
  - eval_report.md    (human-readable, for portfolio/resume)

Usage:
    python -m evaluation.evals.run_evals [--gold PATH] [--out-dir DIR] [--fail-below F1_THRESHOLD]

The eval runner measures:
  1. Segment-event classification accuracy (precision/recall/F1 per event type)
  2. Boolean accuracy (direct_address, fear_intense)
  3. Enum accuracy (fantasy_level)
  4. Language-metric MAE vs hand-labeled estimates
  5. Guardrail trip counts (validation failures, repairs, abstentions, safety floor)

CI gate: exits non-zero if mean_prosocial_events_f1 < --fail-below (default 0.35).
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure package root is on path when run as __main__
_HERE = Path(__file__).resolve()
_AGENTS_ROOT = _HERE.parent.parent.parent
if str(_AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENTS_ROOT))

from dotenv import load_dotenv

load_dotenv()

from evaluation.evals.metrics import (
    aggregate_metrics,
    cohens_kappa,
    score_language_metrics,
    score_segment_events,
)
from evaluation.guardrails import trip_counts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("mindsafe.evals")

GOLD_PATH_DEFAULT = _HERE.parent / "gold_set.jsonl"
OUT_DIR_DEFAULT   = _HERE.parent
CI_F1_THRESHOLD   = 0.70  # fail CI if mean prosocial F1 drops below this


# ---------- Loader ----------

def load_gold_set(path: Path) -> list[dict[str, Any]]:
    examples = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    logger.info("Loaded %d gold examples from %s", len(examples), path)
    return examples


# ---------- Runner ----------

def run_evals(
    gold_path: Path = GOLD_PATH_DEFAULT,
    out_dir: Path = OUT_DIR_DEFAULT,
    fail_below: float = CI_F1_THRESHOLD,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Run the full eval suite. Returns the report dict.
    Raises SystemExit(1) if CI threshold not met.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — evals require LLM access")
        sys.exit(1)

    from evaluation.llm_client import LLMClient
    client = LLMClient(api_key=api_key, model=model)
    logger.info("LLM eval using model: %s", client.model)

    gold_examples = load_gold_set(gold_path)

    event_results: list[dict[str, Any]] = []
    lang_results:  list[dict[str, Any]] = []
    per_example_detail: list[dict[str, Any]] = []

    # For kappa: collect parallel lists
    gold_fear_labels: list[bool] = []
    pred_fear_labels: list[bool] = []
    gold_fantasy_labels: list[str] = []
    pred_fantasy_labels: list[str] = []

    total_latency_ms = 0.0

    for ex in gold_examples:
        eid = ex["id"]
        transcript = ex["transcript"]
        gold_events = ex["expected_events"]
        gold_lang = ex.get("expected_language")

        logger.info("Evaluating example %s: %s", eid, ex.get("description", ""))

        # --- Segment events ---
        t0 = time.perf_counter()
        pred_events = client.classify_segment_events(transcript)
        latency_ms = (time.perf_counter() - t0) * 1000
        total_latency_ms += latency_ms

        event_score = score_segment_events(pred_events, gold_events)
        event_results.append(event_score)

        # Kappa tracking
        gold_fear_labels.append(bool(gold_events.get("fear_intense", False)))
        pred_fear_labels.append(bool(pred_events.get("fear_intense", False)))
        gold_fantasy_labels.append(str(gold_events.get("fantasy_level", "none")))
        pred_fantasy_labels.append(str(pred_events.get("fantasy_level", "none")))

        # --- Language metrics (if gold available) ---
        lang_score: dict[str, float] = {}
        if gold_lang:
            pred_lang = client.estimate_language_metrics_llm(transcript)
            lang_score = score_language_metrics(pred_lang, gold_lang)
            lang_results.append(lang_score)

        per_example_detail.append({
            "id": eid,
            "description": ex.get("description", ""),
            "latency_ms": round(latency_ms, 1),
            "uncertain": pred_events.get("uncertain", False),
            "event_scores": event_score,
            "language_scores": lang_score,
            "predicted_events": {k: v for k, v in pred_events.items() if k != "uncertain"},
            "gold_events": gold_events,
        })

    # --- Aggregate ---
    agg_events = aggregate_metrics(event_results)
    agg_lang   = aggregate_metrics(lang_results) if lang_results else {}

    kappa_fear    = cohens_kappa(pred_fear_labels, gold_fear_labels)
    kappa_fantasy = cohens_kappa(pred_fantasy_labels, gold_fantasy_labels,
                                 categories=["none", "low", "medium", "high"])

    guardrail_trips = trip_counts()

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "model": client.model,
        "n_examples": len(gold_examples),
        "total_latency_ms": round(total_latency_ms, 1),
        "mean_latency_ms_per_example": round(total_latency_ms / max(len(gold_examples), 1), 1),
        "aggregate_event_metrics": agg_events,
        "aggregate_language_metrics": agg_lang,
        "kappa_fear_intense": round(kappa_fear, 4),
        "kappa_fantasy_level": round(kappa_fantasy, 4),
        "guardrail_trips": guardrail_trips,
        "ci_threshold": fail_below,
        "ci_metric": "mean_prosocial_events_f1",
        "ci_value": round(agg_events.get("mean_prosocial_events_f1", 0.0), 4),
        "ci_passed": agg_events.get("mean_prosocial_events_f1", 0.0) >= fail_below,
        "examples": per_example_detail,
    }

    # --- Write outputs ---
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "eval_report.json"
    with open(json_path, "w") as fh:
        json.dump(report, fh, indent=2)
    logger.info("Report saved → %s", json_path)

    md_path = out_dir / "eval_report.md"
    _write_markdown_report(report, md_path)
    logger.info("Markdown report → %s", md_path)

    # --- CI gate ---
    if not report["ci_passed"]:
        logger.error(
            "CI GATE FAILED: %s=%.4f < threshold=%.2f",
            report["ci_metric"], report["ci_value"], fail_below,
        )
        sys.exit(1)

    logger.info(
        "CI GATE PASSED: %s=%.4f >= %.2f",
        report["ci_metric"], report["ci_value"], fail_below,
    )
    return report


# ---------- Markdown report ----------

def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    agg_ev  = report["aggregate_event_metrics"]
    agg_lng = report["aggregate_language_metrics"]
    trips   = report["guardrail_trips"]

    lines = [
        "# MindSafe Eval Report",
        "",
        f"Generated: `{report['generated_at']}`  |  Model: `{report['model']}`  |  N: {report['n_examples']}",
        "",
        "## CI Gate",
        "",
        "| Metric | Value | Threshold | Passed |",
        "|--------|-------|-----------|--------|",
        f"| `{report['ci_metric']}` | {report['ci_value']:.4f} | {report['ci_threshold']:.2f} "
        f"| {'✅' if report['ci_passed'] else '❌'} |",
        "",
        "## Event Classification (LLM vs Gold)",
        "",
        "| Field | Precision | Recall | F1 |",
        "|-------|-----------|--------|----|",
    ]

    for field in ("prosocial_events", "aggressive_events", "sel_strategies", "impossible_events"):
        p = agg_ev.get(f"mean_{field}_precision", 0)
        r = agg_ev.get(f"mean_{field}_recall", 0)
        f = agg_ev.get(f"mean_{field}_f1", 0)
        lines.append(f"| {field} | {p:.3f} | {r:.3f} | {f:.3f} |")

    lines += [
        "",
        "## Boolean & Enum Accuracy",
        "",
        "| Field | Accuracy | Cohen's κ |",
        "|-------|----------|-----------|",
        f"| fear_intense | {agg_ev.get('mean_fear_intense_accuracy', 0):.3f} | {report['kappa_fear_intense']:.3f} |",
        f"| direct_address | {agg_ev.get('mean_direct_address_accuracy', 0):.3f} | — |",
        f"| fantasy_level | {agg_ev.get('mean_fantasy_level_accuracy', 0):.3f} | {report['kappa_fantasy_level']:.3f} |",
        "",
    ]

    if agg_lng:
        lines += [
            "## Language Metric MAE (vs hand-labeled estimates)",
            "",
            "| Metric | MAE (lower = better) |",
            "|--------|----------------------|",
        ]
        for field in ("vocabulary_richness", "sentence_complexity",
                      "advanced_vocabulary_fraction", "question_frequency"):
            mae = agg_lng.get(f"mean_{field}_mae", None)
            if mae is not None:
                lines.append(f"| {field} | {mae:.3f} |")
        lines.append("")

    lines += [
        "## Guardrail Trips",
        "",
        "| Type | Count |",
        "|------|-------|",
        f"| validation_fail | {trips.get('validation_fail', 0)} |",
        f"| repair_success | {trips.get('repair_success', 0)} |",
        f"| repair_fail | {trips.get('repair_fail', 0)} |",
        f"| abstention | {trips.get('abstention', 0)} |",
        f"| safety_floor | {trips.get('safety_floor', 0)} |",
        "",
        "## Latency",
        "",
        f"- Total: {report['total_latency_ms']:.0f} ms",
        f"- Mean per example: {report['mean_latency_ms_per_example']:.0f} ms",
        "",
        "## Per-Example Detail",
        "",
    ]

    for ex in report["examples"]:
        ev = ex["event_scores"]
        status = "⚠️ uncertain" if ex["uncertain"] else "✅"
        lines += [
            f"### `{ex['id']}` {status} — {ex['description']}",
            "",
            f"Latency: {ex['latency_ms']:.0f} ms",
            "",
            "| | P | R | F1 |",
            "|--|---|---|----|",
        ]
        for field in ("prosocial_events", "aggressive_events", "sel_strategies"):
            p = ev.get(f"{field}_precision", 0)
            r = ev.get(f"{field}_recall", 0)
            f1 = ev.get(f"{field}_f1", 0)
            lines.append(f"| {field} | {p:.2f} | {r:.2f} | {f1:.2f} |")
        lines.append(
            f"| fear_intense | — | — | {ev.get('fear_intense_accuracy', 0):.2f} |"
        )
        lines.append(
            f"| fantasy_level | — | — | {ev.get('fantasy_level_accuracy', 0):.2f} |"
        )
        lines.append("")

    with open(path, "w") as fh:
        fh.write("\n".join(lines))


# ---------- CLI ----------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MindSafe LLM eval harness")
    parser.add_argument("--gold", type=Path, default=GOLD_PATH_DEFAULT,
                        help="Path to gold_set.jsonl")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR_DEFAULT,
                        help="Directory to write eval_report.json and .md")
    parser.add_argument("--fail-below", type=float, default=CI_F1_THRESHOLD,
                        help="CI fails if mean prosocial F1 < this value")
    parser.add_argument("--model", type=str, default=None,
                        help="Override Anthropic model (default: ANTHROPIC_MODEL env or claude-opus-4-8)")
    args = parser.parse_args()

    run_evals(
        gold_path=args.gold,
        out_dir=args.out_dir,
        fail_below=args.fail_below,
        model=args.model,
    )
