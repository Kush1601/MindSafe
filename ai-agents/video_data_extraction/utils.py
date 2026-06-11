"""
Utility functions for video data extraction.
"""

import subprocess
from pathlib import Path
from datetime import datetime


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def create_logger():
    """Create a simple logger function with timestamps."""
    log_entries = []
    
    def log(message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entries.append(f"[{timestamp}] {message}")
        print(f"[{timestamp}] {message}")
    
    return log, log_entries


def safe_responses_create(client, *args, **kwargs) -> str:
    """
    Legacy helper for LLM calls that should never crash the pipeline.
    Kept for backward compatibility but no longer used with OpenAI.
    """
    try:
        resp = client.responses.create(*args, **kwargs)
        if hasattr(resp, "output_text"):
            return resp.output_text
        if hasattr(resp, "output") and resp.output and resp.output[0].content:
            part = resp.output[0].content[0]
            if hasattr(part, "text"):
                return part.text
        return None
    except Exception as e:
        print(f"[ERROR] LLM responses.create failed: {e}")
        return None

