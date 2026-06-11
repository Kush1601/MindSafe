"""
LLM output guardrails for MindSafe evaluation pipeline.

Three layers:
1. Value validation  — range/enum checks per schema field.
2. Repair-retry      — on validation failure, sends a correction prompt (once).
3. Safety floor      — blocks "Recommended" if raw violence/fear metrics exceed thresholds;
                       forces "Not recommended" regardless of dev_score.
4. Abstention        — returns an empty result with uncertain=True when the transcript
                       is too sparse to label reliably.

Usage:
    from evaluation.guardrails import validate_segment_events, safety_floor_check
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("mindsafe.guardrails")

# ---------- Constants ----------

# Minimum word count below which the transcript is too sparse for LLM labeling.
ABSTENTION_WORD_THRESHOLD = 20

# Safety floor: if aggressive_events count OR fear_intense trips exceed these
# fractions across labeled segments, block a "Recommended" verdict.
SAFETY_FLOOR_AGGRESSION_RATE = 3.0   # events per minute
SAFETY_FLOOR_FEAR_FRACTION   = 0.40  # fraction of segments with fear_intense=True

# Guardrail trip log counters — accumulated at module level for metrics reporting.
_trips: dict[str, int] = {
    "validation_fail": 0,
    "repair_success": 0,
    "repair_fail": 0,
    "abstention": 0,
    "safety_floor": 0,
}


def trip_counts() -> dict[str, int]:
    """Return a snapshot of guardrail trip counters since process start."""
    return dict(_trips)


# ---------- Abstention check ----------

def is_too_sparse(transcript: str) -> bool:
    """True when the transcript has too few words for reliable LLM labeling."""
    return len(transcript.split()) < ABSTENTION_WORD_THRESHOLD


# ---------- Validators ----------

def _in_range(value: Any, lo: float, hi: float) -> bool:
    try:
        return lo <= float(value) <= hi
    except (TypeError, ValueError):
        return False


def validate_segment_events(result: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate a classify_segment_events() result.

    Returns (ok: bool, reason: str).
    """
    required = ["prosocial_events", "aggressive_events", "fantasy_level",
                "sel_strategies", "direct_address", "fear_intense", "impossible_events"]
    for key in required:
        if key not in result:
            return False, f"missing key: {key}"

    if result["fantasy_level"] not in ("none", "low", "medium", "high"):
        return False, f"invalid fantasy_level: {result['fantasy_level']!r}"

    if not isinstance(result["direct_address"], bool):
        return False, f"direct_address must be bool, got {type(result['direct_address'])}"

    if not isinstance(result["fear_intense"], bool):
        return False, f"fear_intense must be bool, got {type(result['fear_intense'])}"

    for list_field in ("prosocial_events", "aggressive_events", "sel_strategies", "impossible_events"):
        if not isinstance(result[list_field], list):
            return False, f"{list_field} must be a list"

    return True, ""


def validate_coherence(result: dict[str, Any]) -> tuple[bool, str]:
    """Validate a rate_narrative_coherence() result."""
    for key in ("adjacent_similarity_mean", "topic_jumps"):
        if key not in result:
            return False, f"missing key: {key}"
        if not _in_range(result[key], 0.0, 1.0):
            return False, f"{key}={result[key]!r} outside [0, 1]"
    return True, ""


def validate_language_metrics(result: dict[str, Any]) -> tuple[bool, str]:
    """Validate an estimate_language_metrics_llm() result."""
    for key in ("vocabulary_richness", "sentence_complexity",
                "advanced_vocabulary_fraction", "question_frequency"):
        if key not in result:
            return False, f"missing key: {key}"
        if not _in_range(result[key], 0.0, 1.0):
            return False, f"{key}={result[key]!r} outside [0, 1]"
    return True, ""


# ---------- Repair-retry ----------

_REPAIR_INSTRUCTION = (
    "Your previous response failed validation. Fix ONLY the invalid fields "
    "and return the corrected JSON. Invalid reason: {reason}"
)


def _repair(llm_client: Any, original_call_kwargs: dict, reason: str) -> dict[str, Any]:
    """
    Re-invoke the LLM with a repair instruction appended to the user prompt.
    Returns the new result dict (may still be invalid; caller re-validates).
    """
    import copy
    kwargs = copy.deepcopy(original_call_kwargs)
    # Append repair note to user_prompt
    kwargs["user_prompt"] = kwargs.get("user_prompt", "") + "\n\n" + _REPAIR_INSTRUCTION.format(reason=reason)
    return llm_client.json_chat(**kwargs)


def guarded_json_call(
    llm_client: Any,
    call_kwargs: dict[str, Any],
    validator,
    default: dict[str, Any],
    label: str = "",
) -> dict[str, Any]:
    """
    Call llm_client.json_chat(**call_kwargs), validate with validator,
    attempt one repair if invalid, fall back to default on second failure.

    Args:
        llm_client:   LLMClient instance.
        call_kwargs:  kwargs for json_chat (system_prompt, user_prompt, schema, …).
        validator:    callable(result) → (bool, str).
        default:      safe fallback dict to return if both attempts fail.
        label:        name for log messages.

    Returns:
        Validated result dict, or default on double failure.
    """
    t0 = time.perf_counter()
    result = llm_client.json_chat(**call_kwargs)
    latency_ms = (time.perf_counter() - t0) * 1000

    ok, reason = validator(result)
    logger.debug("[guardrails] %s first-pass ok=%s latency=%.0fms", label, ok, latency_ms)

    if ok:
        return result

    _trips["validation_fail"] += 1
    logger.warning("[guardrails] %s validation failed (%s); attempting repair", label, reason)

    t1 = time.perf_counter()
    repaired = _repair(llm_client, call_kwargs, reason)
    repair_latency_ms = (time.perf_counter() - t1) * 1000

    ok2, reason2 = validator(repaired)
    if ok2:
        _trips["repair_success"] += 1
        logger.info("[guardrails] %s repair succeeded latency=%.0fms", label, repair_latency_ms)
        return repaired

    _trips["repair_fail"] += 1
    logger.error(
        "[guardrails] %s repair still invalid (%s); using default fallback", label, reason2
    )
    return default


# ---------- Safety floor ----------

def safety_floor_check(
    interpretation: str,
    raw_metrics: dict[str, float],
    segment_labels: list | None = None,
) -> str:
    """
    Defense-in-depth: never surface 'Recommended' if hard safety thresholds are exceeded.

    Args:
        interpretation: the current overall interpretation string (e.g. "Recommended").
        raw_metrics:    dict containing at minimum aggression_rate (events/min).
        segment_labels: optional list of per-segment label dicts (from llm_label_segments).

    Returns:
        Possibly overridden interpretation string.
    """
    if interpretation != "Recommended":
        return interpretation

    aggression_rate = raw_metrics.get("aggression_rate", 0.0)
    if aggression_rate >= SAFETY_FLOOR_AGGRESSION_RATE:
        _trips["safety_floor"] += 1
        logger.warning(
            "[guardrails] safety_floor: aggression_rate=%.2f >= %.2f; "
            "overriding 'Recommended' → 'Not recommended'",
            aggression_rate, SAFETY_FLOOR_AGGRESSION_RATE,
        )
        return "Not recommended"

    if segment_labels:
        def _fear(s):
            # segment_labels may be SegmentLabels dataclasses or plain dicts
            return getattr(s, "fear_intense", None) if not isinstance(s, dict) else s.get("fear_intense", False)
        fear_count = sum(1 for s in segment_labels if _fear(s))
        fear_fraction = fear_count / max(len(segment_labels), 1)
        if fear_fraction >= SAFETY_FLOOR_FEAR_FRACTION:
            _trips["safety_floor"] += 1
            logger.warning(
                "[guardrails] safety_floor: fear_fraction=%.2f >= %.2f; "
                "overriding 'Recommended' → 'Not recommended'",
                fear_fraction, SAFETY_FLOOR_FEAR_FRACTION,
            )
            return "Not recommended"

    return interpretation
