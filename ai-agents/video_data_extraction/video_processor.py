"""
Video frame extraction functionality.
"""

import subprocess
from pathlib import Path
from typing import List


def extract_frames(video_path: Path, out_dir: Path, max_frames: int = 16) -> List[Path]:
    """
    Sample up to `max_frames` frames from the video using ffmpeg.
    (1 frame per second, capped at max_frames.)
    
    Returns list of frame paths.
    """
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_pattern = frames_dir / "frame_%03d.jpg"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vf", "fps=1",
        "-vframes", str(max_frames),
        str(frame_pattern),
    ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    return frames


def extract_frames_from_segment(
    video_path: Path,
    out_dir: Path,
    start_time: float,
    duration: float,
    segment_num: int,
    frames_per_segment: int = 20,
) -> List[Path]:
    """
    Extract frames from a specific time segment of the video.
    
    Args:
        video_path: Path to the video file
        out_dir: Output directory for frames
        start_time: Start time in seconds
        duration: Duration of segment in seconds
        segment_num: Segment number for file naming
        frames_per_segment: Number of frames to extract from this segment
    
    Returns:
        List of paths to extracted frame images
    """
    frames_dir = out_dir / f"segment_{segment_num:03d}"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_pattern = frames_dir / "frame_%04d.jpg"

    fps = frames_per_segment / duration if duration > 0 else 1

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", f"fps={fps}",
        "-vframes", str(frames_per_segment),
        str(frame_pattern),
    ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    return frames

