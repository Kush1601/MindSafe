"""
YouTube video downloading functionality using yt-dlp.
"""

from pathlib import Path
from yt_dlp import YoutubeDL


def download_youtube_video(url: str, out_dir: Path) -> Path:
    """
    Download a YouTube video (best video+audio merged as mp4) using yt-dlp.
    
    Args:
        url: YouTube video URL
        out_dir: Output directory for the downloaded video
    
    Returns:
        Path to the downloaded mp4 file
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target_template = str(out_dir / "video.%(ext)s")

    ydl_opts = {
        # Use best available quality with fallbacks
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": target_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
        # Use browser cookies to bypass bot detection (optional)
        # "cookiesfrombrowser": ("chrome",),  # Change to "firefox" or "safari" if Chrome doesn't work
        # Avoid JS runtime deprecation warning by forcing a simple player client
        "extractor_args": {"youtube": {"player_client": ["default"]}},
    }

    before_files = set(out_dir.glob("*"))

    with YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    after_files = set(out_dir.glob("*"))
    new_files = list(after_files - before_files)

    # Pick the mp4 we just created
    mp4_candidates = [p for p in new_files if p.suffix.lower() == ".mp4"]
    if not mp4_candidates:
        raise RuntimeError("Could not find downloaded mp4 video.")

    return mp4_candidates[0]

