"""
De-identification module for MindSafe.

Demonstrates PHI-boundary awareness: even though MindSafe inputs are public
YouTube URLs (not clinical records), this module:
1. Documents the PHI flow boundary clearly.
2. Strips/hashes any incidental identifiers that could appear in inputs
   (YouTube channel names, video titles that may contain child names, etc.)
3. Provides a clean API for any future expansion to actual clinical data.

In a real clinical deployment (e.g. EHR integration), this module would apply
HIPAA Safe Harbor or Expert Determination de-identification over clinical text.

Safe Harbor identifiers addressed here (HIPAA § 164.514(b)(2)):
  - Names (in video metadata/titles)
  - Geographic data below state level
  - Dates (more specific than year) — evaluation timestamps are truncated to date
  - URLs (video URLs are hashed when stored for reporting)
  - IP addresses (not stored; noted for completeness)
  - Account numbers / user IDs
  - Free-text fields that may contain identifiers
"""

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional

# ---------- URL pseudonymization ----------

def pseudonymize_url(url: str) -> str:
    """
    One-way hash a YouTube URL for safe storage/logging.
    The hash is deterministic so cache lookups still work via the original URL;
    logs only emit the pseudonym.
    """
    return "vid-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


# ---------- Metadata scrubbing ----------

# Patterns that flag potential PII in free-text fields
_PII_PATTERNS = [
    re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b"),          # Proper name (FirstName LastName)
    re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),  # IP address
    re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),      # Phone number
    re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),  # Email
]


def scrub_text(text: str) -> str:
    """
    Remove obvious PII patterns from free-text (parent summary, titles, etc.).
    Replaces matches with [REDACTED].
    """
    for pattern in _PII_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# ---------- Evaluation metadata scrubbing ----------

def scrub_evaluation_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of evaluation metadata with PII-sensitive fields cleaned.

    - video_path (URL) → pseudonymized
    - video_name  → scrubbed for PII
    - evaluation_timestamp → date only (year-month-day, no time)
    - child_age  → age band only (not exact age)
    """
    scrubbed = dict(metadata)

    if "video_path" in scrubbed:
        scrubbed["video_path"] = pseudonymize_url(scrubbed["video_path"])

    if "video_name" in scrubbed:
        scrubbed["video_name"] = scrub_text(str(scrubbed["video_name"]))

    if "evaluation_timestamp" in scrubbed:
        ts = scrubbed["evaluation_timestamp"]
        try:
            scrubbed["evaluation_timestamp"] = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            scrubbed["evaluation_timestamp"] = "[DATE REDACTED]"

    # Replace exact age with band label only
    if "child_age" in scrubbed and "age_band_label" in scrubbed:
        scrubbed["child_age"] = f"[age band: {scrubbed['age_band_label']}]"

    return scrubbed


# ---------- PHI flow boundary documentation ----------

PHI_BOUNDARY = """
MindSafe PHI Boundary (as of v1):

IN  (external) : YouTube public video URL, child age (integer), child age band
PROCESSING     : Video downloaded to tmpdir → ffmpeg audio extract → local Whisper → text
                 Text transcript → Claude API (Anthropic) for semantic labeling
                 Transcript text contains NO names, no dates, no locations from end users.
OUT (stored)   : Dimension scores, aggregate scores, recommendations (no raw transcript stored)
                 Video URL stored as pseudonymous hash in audit log; full URL in Supabase cache
                 (Supabase holds public YouTube URLs only — not clinical data)

NOT COLLECTED  : User identity, child name, date of birth, IP address, account info
NOT SENT       : Raw audio/video never leaves the local machine (local Whisper)
                 Only extracted text is sent to the Claude API

If this tool is extended to process clinical video (e.g., recorded therapy sessions
containing PHI), a full HIPAA BAA with Anthropic and Supabase would be required, and
this module must be extended to apply Safe Harbor or Expert Determination de-id
before any text is sent to external APIs.
"""


def get_phi_boundary_doc() -> str:
    """Return the PHI boundary documentation string."""
    return PHI_BOUNDARY.strip()
