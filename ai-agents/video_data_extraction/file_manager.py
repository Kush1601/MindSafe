"""
File management and output saving functionality.
"""

import shutil
from pathlib import Path


def save_transcripts(
    output_root: Path,
    speech_transcript: str,
    vllm_transcript: str,
    dialogue_transcript: str,
    scene_summary: str
) -> dict:
    """
    Save all transcript files to the output directory.
    
    Returns dict with paths to saved files.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    
    # Define file paths
    speech_transcript_file = output_root / "speech_transcript.txt"
    vllm_transcript_file = output_root / "video_llm_transcript.txt"
    dialogue_transcript_file = output_root / "dialogue_transcript.txt"
    scene_summary_file = output_root / "scene_summary.txt"

    # Save speech transcript
    with open(speech_transcript_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("SPEECH TRANSCRIPT (Raw ASR)\n")
        f.write("=" * 80 + "\n\n")
        f.write(speech_transcript)
        f.write("\n")

    # Save video-LLM transcript
    with open(vllm_transcript_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("VIDEO-LLM TRANSCRIPT (Segmented Audio + Visual Analysis)\n")
        f.write("=" * 80 + "\n\n")
        f.write(vllm_transcript)
        f.write("\n")

    # Save dialogue transcript
    with open(dialogue_transcript_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("DIALOGUE TRANSCRIPT (Labeled)\n")
        f.write("=" * 80 + "\n\n")
        f.write(dialogue_transcript)
        f.write("\n")

    # Save scene summary
    with open(scene_summary_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("SCENE SUMMARY & EVALUATION\n")
        f.write("=" * 80 + "\n\n")
        f.write(scene_summary)
        f.write("\n")

    return {
        "speech_transcript_file": speech_transcript_file,
        "vllm_transcript_file": vllm_transcript_file,
        "dialogue_transcript_file": dialogue_transcript_file,
        "scene_summary_file": scene_summary_file,
    }


def save_media_files(
    output_root: Path,
    full_video_path: Path,
    audio_path: Path,
    muted_video_path: Path
) -> dict:
    """
    Copy media files to the output directory.
    
    Returns dict with paths to copied files.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    
    final_video = output_root / "video_with_audio.mp4"
    final_audio = output_root / "audio_only.m4a"
    final_muted = output_root / "video_no_audio.mp4"

    shutil.copy(full_video_path, final_video)
    shutil.copy(audio_path, final_audio)
    shutil.copy(muted_video_path, final_muted)

    return {
        "video_with_audio": final_video,
        "audio_only": final_audio,
        "video_only": final_muted,
    }

