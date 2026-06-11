"""Unit tests for evaluation/fhir_export.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json

import pytest

from evaluation.fhir_export import _b64, _extract_risk_label, evaluation_to_fhir_bundle

MOCK_RESULTS = {
    "metadata": {"age_band": "G3_3_5", "age_band_label": "Preschool"},
    "overall_scores": {"development_score": 72.3, "brainrot_index": 28.1},
    "dimension_scores": {
        "pacing": 68.0, "story": 75.2, "language": 80.1,
        "sel": 71.5, "fantasy": 65.0, "interactivity": 77.3,
    },
    "interpretations": {
        "developmental": "Good - Generally appropriate",
        "brainrot": "Low Risk - Minor concerns, generally safe",
        "overall": "Acceptable with supervision",
    },
    "parent_summary": "Good language variety and interactive moments.",
}


class TestFhirBundleStructure:
    def test_bundle_type(self):
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        assert bundle.type == "collection"

    def test_entry_count(self):
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        assert len(bundle.entry) == 11  # 1 Patient + 8 Obs + 1 RA + 1 DocRef

    def test_resource_types_present(self):
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        json_str = bundle.model_dump_json()
        parsed = json.loads(json_str)
        types = [e.get("resource", {}).get("resourceType", "?") for e in parsed.get("entry", [])]
        assert "Patient" in types
        assert types.count("Observation") == 8
        assert "RiskAssessment" in types
        assert "DocumentReference" in types

    def test_no_parent_summary_skips_docref(self):
        results_no_summary = {**MOCK_RESULTS, "parent_summary": ""}
        bundle = evaluation_to_fhir_bundle(results_no_summary, child_age=4)
        json_str = bundle.model_dump_json()
        parsed = json.loads(json_str)
        types = [e.get("resource", {}).get("resourceType", "?") for e in parsed.get("entry", [])]
        assert "DocumentReference" not in types

    def test_json_round_trip(self):
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        json_str = bundle.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["resourceType"] == "Bundle"

    def test_disclaimer_in_patient(self):
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        json_str = bundle.model_dump_json()
        assert "research" in json_str.lower() or "disclaimer" in json_str.lower() or "screening" in json_str.lower()

    def test_no_pii_in_patient_name(self):
        """Patient resource must not contain a name field."""
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        json_str = bundle.model_dump_json()
        parsed = json.loads(json_str)
        patient_entries = [e for e in parsed["entry"] if e.get("resource", {}).get("resourceType") == "Patient"]
        assert patient_entries, "Patient entry missing"
        patient = patient_entries[0]["resource"]
        assert "name" not in patient, "Patient must not have a name field"

    def test_risk_score_in_0_1_range(self):
        bundle = evaluation_to_fhir_bundle(MOCK_RESULTS, child_age=4)
        json_str = bundle.model_dump_json()
        parsed = json.loads(json_str)
        ra_entries = [e for e in parsed["entry"] if e.get("resource", {}).get("resourceType") == "RiskAssessment"]
        assert ra_entries
        prob = ra_entries[0]["resource"]["prediction"][0]["probabilityDecimal"]
        assert 0.0 <= prob <= 1.0


class TestHelpers:
    def test_extract_risk_label_low(self):
        assert _extract_risk_label("Low Risk - Minor concerns") == "Low Risk"

    def test_extract_risk_label_very_high(self):
        assert _extract_risk_label("Very High Risk - Strongly discourage") == "Very High Risk"

    def test_extract_risk_label_moderate(self):
        assert _extract_risk_label("Moderate Risk - Some concerns") == "Moderate Risk"

    def test_b64_round_trip(self):
        import base64
        text = "Hello parent summary"
        assert base64.b64decode(_b64(text)).decode() == text
