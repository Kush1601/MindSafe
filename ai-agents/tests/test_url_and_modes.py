"""
Tests for URL canonicalization and the transcript / metadata evaluation modes
added for the browser-side analysis pipeline.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evaluation.utils import canonical_youtube_url

# evaluate_video pulls in heavy ML deps (numpy/librosa/opencv) that aren't
# installed in the lightweight CI environment. Skip those tests when absent.
try:
    from evaluation.evaluate_video import evaluate_metadata, evaluate_transcript
    from evaluation.video_preprocess import TranscriptSegment
    _PIPELINE_AVAILABLE = True
except ImportError:
    _PIPELINE_AVAILABLE = False

requires_pipeline = pytest.mark.skipif(
    not _PIPELINE_AVAILABLE,
    reason="evaluation pipeline deps (numpy/librosa/opencv) not installed",
)


class TestCanonicalUrl:
    def test_strips_timestamp(self):
        assert (
            canonical_youtube_url("https://www.youtube.com/watch?v=HNiFC1aVBa0&t=1s")
            == "https://www.youtube.com/watch?v=HNiFC1aVBa0"
        )

    def test_strips_playlist(self):
        assert (
            canonical_youtube_url("https://www.youtube.com/watch?v=21_KQbzw6K4&list=PLx")
            == "https://www.youtube.com/watch?v=21_KQbzw6K4"
        )

    def test_short_link(self):
        assert (
            canonical_youtube_url("https://youtu.be/HNiFC1aVBa0")
            == "https://www.youtube.com/watch?v=HNiFC1aVBa0"
        )

    def test_shorts(self):
        assert (
            canonical_youtube_url("https://www.youtube.com/shorts/abcdefghijk")
            == "https://www.youtube.com/watch?v=abcdefghijk"
        )

    def test_already_canonical_unchanged(self):
        url = "https://www.youtube.com/watch?v=HNiFC1aVBa0"
        assert canonical_youtube_url(url) == url

    def test_none_passthrough(self):
        assert canonical_youtube_url(None) is None

    def test_non_youtube_passthrough(self):
        assert canonical_youtube_url("https://example.com/x") == "https://example.com/x"


@requires_pipeline
class TestEvaluateTranscript:
    """Heuristics-only path (no LLM) — deterministic, no network."""

    def _segments(self):
        return [
            TranscriptSegment(start=0.0, end=3.0, text="we share our toys and help our friends"),
            TranscriptSegment(start=3.0, end=6.0, text="being kind makes everyone happy today"),
        ]

    def test_returns_expected_shape(self):
        result = evaluate_transcript(self._segments(), child_age=6, llm_client=None)
        assert result["metadata"]["analysis_mode"] == "transcript_only"
        assert "development_score" in result["overall_scores"]
        assert "brainrot_index" in result["overall_scores"]
        assert isinstance(result["dimension_scores"], dict)

    def test_duration_from_segments(self):
        result = evaluate_transcript(self._segments(), child_age=6, llm_client=None)
        assert result["metadata"]["duration_seconds"] == 6.0

    def test_scores_in_range(self):
        result = evaluate_transcript(self._segments(), child_age=6, llm_client=None)
        dev = result["overall_scores"]["development_score"]
        br = result["overall_scores"]["brainrot_index"]
        assert 0 <= dev <= 100
        assert 0 <= br <= 100


@requires_pipeline
class TestEvaluateMetadata:
    """Metadata fallback with no LLM returns a clearly-marked neutral result."""

    def test_no_llm_returns_neutral_marked(self):
        result = evaluate_metadata("Some Kids Show", child_age=6, channel="Kids", llm_client=None)
        assert result["metadata"]["analysis_mode"] == "metadata_only"
        assert result["overall_scores"]["development_score"] == 50.0
        assert "note" in result["metadata"]
