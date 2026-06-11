"""Unit tests for evaluation/evals/metrics.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evaluation.evals.metrics import (
    _bool_accuracy,
    _enum_accuracy,
    _list_overlap_f1,
    _mae,
    aggregate_metrics,
    cohens_kappa,
    score_language_metrics,
    score_segment_events,
)


class TestListOverlapF1:
    def test_perfect_match(self):
        p, r, f1 = _list_overlap_f1(["sharing"], ["sharing"])
        assert p == 1.0 and r == 1.0 and f1 == 1.0

    def test_both_empty(self):
        p, r, f1 = _list_overlap_f1([], [])
        assert f1 == 1.0

    def test_no_predicted(self):
        p, r, f1 = _list_overlap_f1([], ["sharing"])
        assert r == 0.0 and f1 == 0.0

    def test_no_gold(self):
        p, r, f1 = _list_overlap_f1(["sharing"], [])
        assert p == 0.0 and f1 == 0.0

    def test_partial_match_substring(self):
        p, r, f1 = _list_overlap_f1(
            ["cooperative play", "helping"],
            ["cooperative cooking", "helping with task", "sharing"],
        )
        assert r > 0, "should match cooperative and helping"
        assert 0 < f1 < 1.0

    def test_case_insensitive(self):
        p, r, f1 = _list_overlap_f1(["SHARING"], ["sharing"])
        assert f1 == 1.0


class TestScoreSegmentEvents:
    def test_perfect_prediction(self):
        gold = {
            "prosocial_events": ["sharing"],
            "aggressive_events": [],
            "sel_strategies": [],
            "impossible_events": [],
            "fear_intense": False,
            "direct_address": True,
            "fantasy_level": "low",
        }
        scores = score_segment_events(gold, gold)
        assert scores["prosocial_events_f1"] == 1.0
        assert scores["fear_intense_accuracy"] == 1.0
        assert scores["direct_address_accuracy"] == 1.0
        assert scores["fantasy_level_accuracy"] == 1.0

    def test_wrong_fear_intense(self):
        gold = {"prosocial_events": [], "aggressive_events": [], "sel_strategies": [],
                "impossible_events": [], "fear_intense": True, "direct_address": False,
                "fantasy_level": "none"}
        pred = {**gold, "fear_intense": False}
        scores = score_segment_events(pred, gold)
        assert scores["fear_intense_accuracy"] == 0.0


class TestAggregateMetrics:
    def test_basic_average(self):
        per_ex = [
            {"f1": 0.8, "acc": 1.0},
            {"f1": 0.6, "acc": 0.0},
        ]
        agg = aggregate_metrics(per_ex)
        assert abs(agg["mean_f1"] - 0.7) < 0.001
        assert abs(agg["mean_acc"] - 0.5) < 0.001

    def test_empty(self):
        assert aggregate_metrics([]) == {}


class TestCohensKappa:
    def test_perfect_agreement(self):
        labels = [True, False, True, True]
        kappa = cohens_kappa(labels, labels)
        assert abs(kappa - 1.0) < 0.001

    def test_zero_agreement_beyond_chance(self):
        # All A disagree with all B → kappa ≤ 0 (perfect disagreement or 0 when p_e=0)
        a = [True, True, True, True]
        b = [False, False, False, False]
        kappa = cohens_kappa(a, b)
        assert kappa <= 0

    def test_multiclass(self):
        a = ["none", "low", "medium", "high"]
        b = ["none", "low", "medium", "none"]
        kappa = cohens_kappa(a, b, categories=["none", "low", "medium", "high"])
        assert -1.0 <= kappa <= 1.0
