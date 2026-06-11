"""
Video preprocessing utilities.
Extracts frames, audio, shots, and generates transcripts from video files.
"""

import os
import subprocess
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import tempfile


@dataclass
class Shot:
    """Represents a detected shot/scene in a video."""
    start_time: float  # seconds
    end_time: float    # seconds
    duration: float    # seconds
    frame_start: int
    frame_end: int


@dataclass
class TranscriptSegment:
    """Represents a segment of transcript with timing."""
    start: float       # seconds
    end: float         # seconds
    text: str


def extract_audio(video_path: str, output_path: Optional[str] = None) -> str:
    """
    Extract audio from video file using ffmpeg.
    
    Args:
        video_path: Path to video file
        output_path: Path for output audio file (if None, creates temp file)
        
    Returns:
        Path to extracted audio file
    """
    if output_path is None:
        temp_dir = tempfile.gettempdir()
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(temp_dir, f"{base_name}_audio.wav")
    
    # Use ffmpeg to extract audio as WAV
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", "16000",  # 16kHz sample rate
        "-ac", "1",  # Mono
        "-y",  # Overwrite
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e.stderr.decode()}")
        raise


def get_video_duration(video_path: str) -> float:
    """
    Get video duration in seconds using ffprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Duration in seconds
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting video duration: {e}")
        return 0.0


def get_video_fps(video_path: str) -> float:
    """
    Get video frame rate using ffprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Frames per second
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        fps_str = result.stdout.strip()
        # Parse fraction like "30/1"
        if "/" in fps_str:
            num, den = fps_str.split("/")
            return float(num) / float(den)
        return float(fps_str)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting video FPS: {e}")
        return 30.0  # Default assumption


def detect_shots(video_path: str, threshold: float = 0.3) -> List[Shot]:
    """
    FAST-MODE shot estimation.

    For speed, we avoid heavy scene detection (PySceneDetect or ffmpeg
    scene filters) and instead approximate shots by splitting the video
    into uniform time intervals.

    Args:
        video_path: Path to video file
        threshold: Unused in fast mode (kept for API compatibility)

    Returns:
        List of Shot objects
    """
    duration = get_video_duration(video_path)
    fps = get_video_fps(video_path)

    if duration <= 0:
        # Fallback: single shot with default 30fps
        fps = fps or 30.0
        return [
            Shot(
                start_time=0.0,
                end_time=0.0,
                duration=0.0,
                frame_start=0,
                frame_end=0,
            )
        ]

    # Choose a coarse shot length to keep pacing reasonable but fast
    approx_shot_len = 5.0  # seconds
    num_shots = max(1, int(duration / approx_shot_len))

    shots: List[Shot] = []
    for i in range(num_shots):
        start_time = i * approx_shot_len
        end_time = min(duration, (i + 1) * approx_shot_len)
        frame_start = int(start_time * fps)
        frame_end = int(end_time * fps)
        shots.append(
            Shot(
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                frame_start=frame_start,
                frame_end=frame_end,
            )
        )

    return shots


def detect_shots_ffmpeg(video_path: str, threshold: float = 0.3) -> List[Shot]:
    """
    Fallback shot detection using ffmpeg's scene filter.
    
    Args:
        video_path: Path to video file
        threshold: Scene detection threshold
        
    Returns:
        List of Shot objects
    """
    # Use ffmpeg scene filter to detect cuts
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + result.stderr
        
        # Parse scene timestamps from showinfo output
        scene_times = []
        for line in output.split('\n'):
            if 'pts_time:' in line:
                try:
                    time_str = line.split('pts_time:')[1].split()[0]
                    scene_times.append(float(time_str))
                except (IndexError, ValueError):
                    continue
        
        # Convert to shots
        duration = get_video_duration(video_path)
        fps = get_video_fps(video_path)
        
        if not scene_times:
            # No cuts detected, return single shot
            return [Shot(
                start_time=0.0,
                end_time=duration,
                duration=duration,
                frame_start=0,
                frame_end=int(duration * fps)
            )]
        
        # Create shots from cut points
        scene_times = [0.0] + sorted(scene_times) + [duration]
        shots = []
        
        for i in range(len(scene_times) - 1):
            start_time = scene_times[i]
            end_time = scene_times[i + 1]
            shots.append(Shot(
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                frame_start=int(start_time * fps),
                frame_end=int(end_time * fps)
            ))
        
        return shots
    
    except subprocess.CalledProcessError as e:
        print(f"Error detecting shots: {e}")
        # Return single shot as fallback
        duration = get_video_duration(video_path)
        fps = get_video_fps(video_path)
        return [Shot(
            start_time=0.0,
            end_time=duration,
            duration=duration,
            frame_start=0,
            frame_end=int(duration * fps)
        )]


def transcribe_audio(audio_path: str, use_api: bool = False) -> List[TranscriptSegment]:
    """
    Transcribe audio file using the local Whisper model.

    Remote OpenAI transcription has been removed; all transcription now happens
    locally to avoid external dependencies.

    Args:
        audio_path: Path to audio file
        use_api: Ignored (kept for backward compatibility)

    Returns:
        List of TranscriptSegment objects
    """
    return transcribe_audio_local(audio_path)


def transcribe_audio_local(audio_path: str) -> List[TranscriptSegment]:
    """
    Transcribe using local Whisper model.
    Requires: a locally installed Whisper implementation (e.g. `pip install openai-whisper`)
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        List of TranscriptSegment objects
    """
    try:
        import whisper
        
        # Load model (use 'base' for speed, 'large' for accuracy)
        model = whisper.load_model("base")

        # Transcribe with timestamps; disable fp16 on CPU to avoid warnings
        result = model.transcribe(audio_path, word_timestamps=False, fp16=False)
        
        # Extract segments
        segments = []
        for seg in result.get('segments', []):
            segments.append(TranscriptSegment(
                start=seg['start'],
                end=seg['end'],
                text=seg['text'].strip()
            ))
        
        return segments
    
    except ImportError:
        print("Local whisper not installed. Install with: `pip install openai-whisper`")
        return []
    except Exception as e:
        print(f"Error transcribing locally: {e}")
        return []


def extract_frames(video_path: str, fps: int = 1, output_dir: Optional[str] = None) -> List[str]:
    """
    Extract frames from video at specified rate.
    
    Args:
        video_path: Path to video file
        fps: Frames per second to extract
        output_dir: Directory for output frames (if None, creates temp dir)
        
    Returns:
        List of paths to extracted frame images
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp()
    
    os.makedirs(output_dir, exist_ok=True)
    
    output_pattern = os.path.join(output_dir, "frame_%04d.jpg")
    
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",  # Quality
        "-y",
        output_pattern
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Get list of extracted frames
        frames = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ])
        
        return frames
    
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frames: {e.stderr.decode()}")
        return []


def load_existing_transcript(transcript_path: str) -> List[TranscriptSegment]:
    """
    Load transcript from existing file (from video_data_extraction output).
    
    Args:
        transcript_path: Path to transcript file
        
    Returns:
        List of TranscriptSegment objects
    """
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse as JSON first (structured format)
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return [TranscriptSegment(**seg) for seg in data]
        except json.JSONDecodeError:
            pass
        
        # Fallback: treat as plain text, create single segment
        return [TranscriptSegment(start=0.0, end=0.0, text=content)]
    
    except Exception as e:
        print(f"Error loading transcript: {e}")
        return []

