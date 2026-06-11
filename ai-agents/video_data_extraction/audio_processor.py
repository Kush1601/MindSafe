"""
Audio extraction and transcription functionality.
Includes chunked processing to avoid token limits.

All transcription is now done locally using the Whisper model (no OpenAI API).
"""

import subprocess
from pathlib import Path
from typing import List

try:
    import whisper  # Local Whisper model
except ImportError:
    whisper = None


def extract_audio_and_muted_video(video_path: Path, out_dir: Path) -> dict:
    """
    From a full video, produce:
      - audio_only.m4a  (audio track only)
      - video_no_audio.mp4 (muted video)
    
    Returns dict with paths to both files.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_path = out_dir / "audio_only.m4a"
    muted_video_path = out_dir / "video_no_audio.mp4"

    # Extract audio only - with better error handling
    print(f"Extracting audio from {video_path}...")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",  # no video
            "-acodec", "copy",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"⚠️  Warning: Audio extraction failed. Error output:")
        print(result.stderr)
        # Try with re-encoding instead of copying
        print("Retrying with audio re-encoding...")
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vn",
                "-acodec", "aac",
                "-b:a", "192k",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to extract audio: {result.stderr}")

    # Extract video only (no audio)
    print(f"Extracting video without audio...")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-an",  # no audio
            "-c:v", "copy",
            str(muted_video_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    return {
        "audio": audio_path,
        "muted_video": muted_video_path,
    }


def split_audio_into_chunks(
    audio_path: Path, 
    out_dir: Path, 
    chunk_duration: float = 60.0
) -> List[Path]:
    """
    Split audio file into smaller chunks to avoid token/size limits.
    
    Args:
        audio_path: Path to the full audio file
        out_dir: Output directory for audio chunks
        chunk_duration: Duration of each chunk in seconds (default 60s)
    
    Returns:
        List of paths to audio chunk files
    """
    chunks_dir = out_dir / "audio_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    
    # Get total audio duration
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    total_duration = float(result.stdout.strip())
    
    num_chunks = int(total_duration / chunk_duration) + (1 if total_duration % chunk_duration > 0 else 0)
    print(f"  Splitting audio into {num_chunks} chunks of ~{chunk_duration}s each...")
    
    chunk_paths = []
    for i in range(num_chunks):
        start_time = i * chunk_duration
        chunk_path = chunks_dir / f"audio_chunk_{i+1:03d}.m4a"
        
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start_time),
            "-i", str(audio_path),
            "-t", str(chunk_duration),
            "-c", "copy",
            str(chunk_path),
        ]
        
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        
        chunk_paths.append(chunk_path)
    
    print(f"  ✓ Created {len(chunk_paths)} audio chunks")
    return chunk_paths


def transcribe_audio_chunk(audio_chunk_path: Path, chunk_num: int) -> str:
    """
    Transcribe a single audio chunk using the local Whisper model.
    """
    if whisper is None:
        print(
            "  [ERROR] Local whisper not installed. Install with: `pip install openai-whisper`"
        )
        return f"[CHUNK {chunk_num} FAILED - whisper not installed]"

    try:
        # For chunked processing we can use a small model for speed.
        model = whisper.load_model("base")
        # Explicitly disable fp16 to avoid CPU warnings
        result = model.transcribe(
            str(audio_chunk_path), word_timestamps=False, fp16=False
        )
        text = result.get("text", "").strip()
        return text or f"[CHUNK {chunk_num} EMPTY]"
    except Exception as e:
        print(f"  [ERROR] Transcription of chunk {chunk_num} failed: {e}")
        return f"[CHUNK {chunk_num} FAILED]"


def transcribe_audio_in_chunks(
    audio_path: Path, 
    tmp_dir: Path,
    chunk_duration: float = 60.0
) -> str:
    """
    Transcribe audio by splitting it into chunks first, then combining results.
    This avoids token/file size limits for long audio files.
    
    Args:
        audio_path: Path to the full audio file
        tmp_dir: Temporary directory for audio chunks
        chunk_duration: Duration of each chunk in seconds
    
    Returns:
        Complete transcription of all audio combined
    """
    print("  Using chunked audio transcription to avoid token limits...")
    
    # Split audio into chunks
    chunk_paths = split_audio_into_chunks(audio_path, tmp_dir, chunk_duration)
    
    # Transcribe each chunk
    transcriptions = []
    for i, chunk_path in enumerate(chunk_paths, 1):
        print(f"  Transcribing audio chunk {i}/{len(chunk_paths)}...", end=" ")
        chunk_text = transcribe_audio_chunk(chunk_path, i)
        transcriptions.append(chunk_text)
        print(f"✓ ({len(chunk_text)} chars)")
    
    # Combine all transcriptions with spaces
    full_transcript = " ".join(transcriptions)
    
    print(f"  ✓ Combined all chunks: {len(full_transcript)} total characters")
    
    return full_transcript

