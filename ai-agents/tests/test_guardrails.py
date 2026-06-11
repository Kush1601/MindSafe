"""Unit tests for evaluation/guardrails.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evaluation.guardrails import (
    _trips,
    is_too_sparse,
    safety_floor_check,
    trip_counts,
    validate_coherence,
    validate_language_metrics,
    validate_segment_events,
)

VALID_EVENTS = {
    "prosocial_events": ["sharing", "helping"],
    "aggressive_events": [],
    "fantasy_level": "low",
    "sel_strategies": ["deep breathing"],
    "direct_address": True,
    "fear_intense": False,
    "impossible_events": [],
}


class TestSegmentEventsValidator:
    def test_valid_passes(self):
        ok, reason = validate_segment_events(VALID_EVENTS)
        assert ok
        assert reason == ""

    def test_missing_key_fails(self):
        bad = {k: v for k, v in VALID_EVENTS.items() if k != "fantasy_level"}
        ok, reason = validate_segment_events(bad)
        assert not ok
        assert "missing key" in reason

    def test_invalid_fantasy_enum(self):
        bad = {**VALID_EVENTS, "fantasy_level": "extreme"}
        ok, reason = validate_segment_events(bad)
        assert not ok
        assert "fantasy_level" in reason

    def test_non_bool_direct_address(self):
        bad = {**VALID_EVENTS, "direct_address": "yes"}
        ok, reason = validate_segment_events(bad)
        assert not ok

    def test_non_list_field(self):
        bad = {**VALID_EVENTS, "prosocial_events": "sharing"}
        ok, reason = validate_segment_events(bad)
        assert not ok


class TestCoherenceValidator:
    def test_valid(self):
        ok, _ = validate_coherence({"adjacent_similarity_mean": 0.7, "topic_jumps": 0.2})
        assert ok

    def test_out_of_range(self):
        ok, reason = validate_coherence({"adjacent_similarity_mean": 1.5, "topic_jumps": 0.2})
        assert not ok
        assert "adjacent_similarity_mean" in reason

    def test_missing_key(self):
        ok, _ = validate_coherence({"adjacent_similarity_mean": 0.5})
        assert not ok

    def test_boundary_values(self):
        ok, _ = validate_coherence({"adjacent_similarity_mean": 0.0, "topic_jumps": 1.0})
        assert ok


class TestLanguageMetricsValidator:
    def test_valid(self):
        ok, _ = validate_language_metrics({
            "vocabulary_richness": 0.6,
            "sentence_complexity": 0.4,
            "advanced_vocabulary_fraction": 0.2,
            "question_frequency": 0.3,
        })
        assert ok

    def test_negative_value(self):
        ok, _ = validate_language_metrics({
            "vocabulary_richness": -0.1,
            "sentence_complexity": 0.4,
            "advanced_vocabulary_fraction": 0.2,
            "question_frequency": 0.3,
        })
        assert not ok


class TestSafetyFloor:
    def test_high_aggression_overrides_recommended(self):
        result = safety_floor_check("Recommended", {"aggression_rate": 5.0})
        assert result == "Not recommended"

    def test_low_aggression_keeps_recommended(self):
        result = safety_floor_check("Recommended", {"aggression_rate": 1.0})
        assert result == "Recommended"

    def test_non_recommended_not_affected(self):
        result = safety_floor_check("Acceptable with supervision", {"aggression_rate": 10.0})
        assert result == "Acceptable with supervision"

    def test_fear_fraction_overrides(self):
        labels = [{"fear_intense": True}] * 5 + [{"fear_intense": False}] * 5
        result = safety_floor_check("Recommended", {"aggression_rate": 0.0}, segment_labels=labels)
        assert result == "Not recommended"

    def test_low_fear_fraction_keeps_recommended(self):
        labels = [{"fear_intense": True}] + [{"fear_intense": False}] * 9
        result = safety_floor_check("Recommended", {"aggression_rate": 0.0}, segment_labels=labels)
        assert result == "Recommended"


class TestAbstention:
    def test_sparse_transcript(self):
        assert is_too_sparse("hi") is True
        assert is_too_sparse("hello world") is True

    def test_sufficient_transcript(self):
        text = " ".join(["word"] * 30)
        assert is_too_sparse(text) is False
