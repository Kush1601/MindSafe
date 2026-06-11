"""
Main orchestrator for video data extraction pipeline.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict

# Support both relative imports (when used as a module) and direct execution
try:
    from .config import DEFAULT_SEGMENT_DURATION, DEFAULT_FRAMES_PER_SEGMENT, DEFAULT_AUDIO_CHUNK_DURATION
    from .utils import get_video_duration, create_logger
    from .video_downloader import download_youtube_video
    from .audio_processor import extract_audio_and_muted_video, transcribe_audio_in_chunks
    from .video_processor import extract_frames_from_segment
    from .ai_analyzer import generate_segment_transcript, generate_dialogue_transcript, generate_scene_summary
    from .file_manager import save_transcripts, save_media_files
except ImportError:
    # Fallback for direct execution
    from config import DEFAULT_SEGMENT_DURATION, DEFAULT_FRAMES_PER_SEGMENT, DEFAULT_AUDIO_CHUNK_DURATION
    from utils import get_video_duration, create_logger
    from video_downloader import download_youtube_video
    from audio_processor import extract_audio_and_muted_video, transcribe_audio_in_chunks
    from video_processor import extract_frames_from_segment
    from ai_analyzer import generate_segment_transcript, generate_dialogue_transcript, generate_scene_summary
    from file_manager import save_transcripts, save_media_files


def process_video_in_chunks(
    video_path: Path,
    speech_transcript: str,
    tmp_dir: Path,
    segment_duration: float = DEFAULT_SEGMENT_DURATION,
    frames_per_segment: int = DEFAULT_FRAMES_PER_SEGMENT,
) -> str:
    """
    Process entire video by splitting into chunks and analyzing each separately.
    Returns combined transcript from all segments.
    """
    total_duration = get_video_duration(video_path)
    print(f"\nVideo duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")

    num_segments = int(total_duration / segment_duration) + (1 if total_duration % segment_duration > 0 else 0)
    print(f"Splitting into {num_segments} segments of ~{segment_duration}s each")
    print(f"Extracting {frames_per_segment} frames per segment")
    print(f"Total frames to analyze: {num_segments * frames_per_segment}\n")

    segment_transcripts = []

    for i in range(num_segments):
        start_time = i * segment_duration
        end_time = min((i + 1) * segment_duration, total_duration)
        duration = end_time - start_time

        print(f"[Segment {i+1}/{num_segments}] Time: {start_time:.1f}s - {end_time:.1f}s")

        frame_paths = extract_frames_from_segment(
            video_path,
            tmp_dir,
            start_time,
            duration,
            i + 1,
            frames_per_segment
        )

        print(f"  Extracted {len(frame_paths)} frames")

        segment_transcript = generate_segment_transcript(
            frame_paths,
            i + 1,
            num_segments,
            start_time,
            end_time,
            speech_transcript,
            total_duration
        )

        segment_transcripts.append({
            "segment_num": i + 1,
            "start_time": start_time,
            "end_time": end_time,
            "transcript": segment_transcript,
        })

        print(f"  ✓ Segment {i+1} analyzed ({len(segment_transcript)} characters)\n")

    print("Combining all segments into final comprehensive transcript...")

    final_transcript = "=" * 80 + "\n"
    final_transcript += "COMPREHENSIVE VIDEO ANALYSIS (SEGMENTED)\n"
    final_transcript += f"Total Duration: {total_duration:.1f}s ({total_duration/60:.1f} minutes)\n"
    final_transcript += f"Analyzed: {num_segments} segments with {num_segments * frames_per_segment} total frames\n"
    final_transcript += "=" * 80 + "\n\n"

    for seg in segment_transcripts:
        final_transcript += f"\n{'=' * 80}\n"
        final_transcript += f"SEGMENT {seg['segment_num']}/{num_segments}: "
        final_transcript += f"{seg['start_time']:.1f}s - {seg['end_time']:.1f}s\n"
        final_transcript += f"{'=' * 80}\n\n"
        final_transcript += seg["transcript"]
        final_transcript += "\n\n"

    return final_transcript


def process_youtube_video(
    url: str,
    output_dir: str = "outputs",
    use_chunked_processing: bool = True,
    segment_duration: float = DEFAULT_SEGMENT_DURATION,
    frames_per_segment: int = DEFAULT_FRAMES_PER_SEGMENT,
    audio_chunk_duration: float = DEFAULT_AUDIO_CHUNK_DURATION,
) -> Dict[str, str]:
    """
    High-level function to process a YouTube video:
      - Download video
      - Extract audio and transcribe (chunked)
      - Extract frames and analyze with AI (chunked)
      - Generate dialogue transcript
      - Generate scene summary
      - Save all outputs
    
    Returns dict with paths and results.
    """
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    log, log_entries = create_logger()

    log("Starting video processing pipeline...")
    log(f"Source URL: {url}")
    log(f"Output directory: {output_root.absolute()}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 1) Download full video
        log("Step 1/6: Downloading YouTube video...")
        full_video_path = download_youtube_video(url, tmp_dir)
        log(f"✓ Video downloaded: {full_video_path.name}")

        # 2) Extract audio & muted video
        log("Step 2/6: Extracting audio and video tracks...")
        av_paths = extract_audio_and_muted_video(full_video_path, tmp_dir)
        audio_path = av_paths["audio"]
        muted_video_path = av_paths["muted_video"]
        log(f"✓ Audio extracted: {audio_path.name}")
        log(f"✓ Muted video extracted: {muted_video_path.name}")

        # 3) Transcribe audio using chunked processing
        log("Step 3/6: Transcribing audio using chunked processing...")
        speech_transcript = transcribe_audio_in_chunks(
            audio_path, 
            tmp_dir,
            chunk_duration=audio_chunk_duration
        )
        log(f"✓ Audio fully transcribed ({len(speech_transcript)} characters)")

        # 4) Generate multimodal analysis (FAST MODE)
        if use_chunked_processing:
            log("Step 4/6: Using CHUNKED processing for comprehensive video analysis...")
            log(f"         Segments: {segment_duration}s each, {frames_per_segment} frames/segment")
            vllm_transcript = process_video_in_chunks(
                full_video_path,
                speech_transcript,
                tmp_dir,
                segment_duration=segment_duration,
                frames_per_segment=frames_per_segment,
            )
            log(f"✓ Comprehensive video analysis complete ({len(vllm_transcript)} characters)")
        else:
            # FAST MODE: skip frame extraction and LLM visual analysis.
            log("Step 4/6: FAST MODE - skipping visual LLM analysis, using speech transcript only...")
            vllm_transcript = f"[FAST MODE] Visual analysis skipped.\n\nSpeech transcript:\n{speech_transcript}"
            log(f"✓ Simple transcript assembled ({len(vllm_transcript)} characters)")
        
        # 5) Generate dialogue transcript (FAST MODE - reuse speech text)
        log("Step 5/6: FAST MODE - generating lightweight dialogue transcript...")
        dialogue_transcript = speech_transcript
        log(f"✓ Dialogue transcript assembled ({len(dialogue_transcript)} characters)")
        
        # 6) Generate scene summary (FAST MODE - placeholder)
        log("Step 6/6: FAST MODE - generating simple scene summary...")
        scene_summary = (
            "[FAST MODE] Detailed scene-by-scene summary disabled for speed.\n\n"
            "Use the developmental scores and brainrot index from the evaluator "
            "for decision making."
        )
        log(f"✓ Scene summary generated ({len(scene_summary)} characters)")

        # Copy media files
        media_files = save_media_files(output_root, full_video_path, audio_path, muted_video_path)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    log(f"Pipeline completed in {duration:.2f} seconds")

    # Save transcripts
    log("Saving transcripts to files...")
    transcript_files = save_transcripts(
        output_root,
        speech_transcript,
        vllm_transcript,
        dialogue_transcript,
        scene_summary
    )

    log(f"✅ All files saved to: {output_root.absolute()}")
    log(f"   - {media_files['video_with_audio'].name}")
    log(f"   - {media_files['audio_only'].name}")
    log(f"   - {media_files['video_only'].name}")
    log(f"   - {transcript_files['speech_transcript_file'].name}")
    log(f"   - {transcript_files['vllm_transcript_file'].name}")
    log(f"   - {transcript_files['dialogue_transcript_file'].name}")
    log(f"   - {transcript_files['scene_summary_file'].name}")

    return {
        **media_files,
        "speech_transcript": speech_transcript,
        **transcript_files,
        "duration": duration,
    }


if __name__ == "__main__":
    test_url = "https://www.youtubekids.com/watch?v=j5MrMsHwNGg"
    
    print("\n" + "=" * 80)
    print("YOUTUBE VIDEO PROCESSOR - COMPREHENSIVE ANALYSIS")
    print("=" * 80)
    print(f"Processing: {test_url}\n")
    
    result = process_youtube_video(
        test_url, 
        output_dir="outputs",
        use_chunked_processing=True,
        segment_duration=30.0,
        frames_per_segment=20,
        audio_chunk_duration=60.0,
    )
    
    print("\n" + "=" * 80)
    print("PROCESSING COMPLETE!")
    print("=" * 80)
    print(f"\n⏱️  Total processing time: {result['duration']:.2f} seconds")
    print(f"\n📂 All outputs saved to: outputs/")
    print("\n📄 Text files:")
    print(f"   • speech_transcript.txt")
    print(f"   • video_llm_transcript.txt")
    print(f"   • dialogue_transcript.txt")
    print(f"   • scene_summary.txt")
    print("\n🎥 Media files:")
    print(f"   • video_with_audio.mp4")
    print(f"   • audio_only.m4a")
    print(f"   • video_no_audio.mp4")
    print("\n" + "=" * 80 + "\n")

