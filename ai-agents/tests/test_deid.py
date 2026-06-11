"""Unit tests for evaluation/deid.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluation.deid import (
    get_phi_boundary_doc,
    pseudonymize_url,
    scrub_evaluation_metadata,
    scrub_text,
)


class TestPseudonymizeUrl:
    def test_deterministic(self):
        url = "https://youtube.com/watch?v=abc123"
        assert pseudonymize_url(url) == pseudonymize_url(url)

    def test_different_urls_produce_different_hashes(self):
        assert pseudonymize_url("https://youtube.com/watch?v=aaa") != pseudonymize_url("https://youtube.com/watch?v=bbb")

    def test_starts_with_vid_prefix(self):
        result = pseudonymize_url("https://youtube.com/watch?v=test")
        assert result.startswith("vid-")

    def test_no_original_url_in_output(self):
        url = "https://youtube.com/watch?v=abc123"
        result = pseudonymize_url(url)
        assert "youtube" not in result
        assert "abc123" not in result


class TestScrubText:
    def test_removes_email(self):
        text = "Contact John at john@example.com for info"
        scrubbed = scrub_text(text)
        assert "john@example.com" not in scrubbed
        assert "[REDACTED]" in scrubbed

    def test_removes_ip_address(self):
        text = "Server at 192.168.1.100"
        scrubbed = scrub_text(text)
        assert "192.168.1.100" not in scrubbed

    def test_clean_text_unchanged(self):
        text = "Bluey watches TV with Bingo."
        scrubbed = scrub_text(text)
        # "Bluey" is a proper noun but single word — pattern requires First Last
        assert "watches TV" in scrubbed


class TestScrubEvaluationMetadata:
    def test_pseudonymizes_video_path(self):
        meta = {"video_path": "https://youtube.com/watch?v=test", "age_band_label": "Preschool"}
        scrubbed = scrub_evaluation_metadata(meta)
        assert "youtube" not in scrubbed["video_path"]
        assert scrubbed["video_path"].startswith("vid-")

    def test_truncates_timestamp_to_date(self):
        meta = {"evaluation_timestamp": "2024-06-10T14:23:45", "age_band_label": "Preschool"}
        scrubbed = scrub_evaluation_metadata(meta)
        assert scrubbed["evaluation_timestamp"] == "2024-06-10"
        assert "14:23:45" not in scrubbed["evaluation_timestamp"]

    def test_replaces_exact_age_with_band(self):
        meta = {"child_age": 4.5, "age_band_label": "Preschool"}
        scrubbed = scrub_evaluation_metadata(meta)
        assert scrubbed["child_age"] == "[age band: Preschool]"


class TestPhiBoundaryDoc:
    def test_returns_non_empty_string(self):
        doc = get_phi_boundary_doc()
        assert isinstance(doc, str)
        assert len(doc) > 100
        assert "PHI" in doc
