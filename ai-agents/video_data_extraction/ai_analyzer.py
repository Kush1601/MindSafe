"""
AI-powered analysis for generating richer textual descriptions of video segments.

Generates textual descriptions of video segments using Claude (see evaluation.llm_client),
combining time-aligned speech with per-segment prompts.
"""

from pathlib import Path
from typing import List

from evaluation.llm_client import LLMClient


def extract_dialogue_for_timerange(
    full_transcript: str,
    start_time: float,
    end_time: float,
    total_duration: float
) -> str:
    """
    Extract approximate dialogue for a specific time range.
    Uses proportional text extraction based on time ratios.
    """
    if not full_transcript or total_duration <= 0:
        return "[No dialogue available]"
    
    # Calculate proportional position in the transcript
    start_ratio = start_time / total_duration
    end_ratio = end_time / total_duration
    
    # Extract the corresponding portion of text
    transcript_length = len(full_transcript)
    start_pos = int(start_ratio * transcript_length)
    end_pos = int(end_ratio * transcript_length)
    
    segment_dialogue = full_transcript[start_pos:end_pos].strip()
    
    if not segment_dialogue:
        return "[No dialogue in this segment]"
    
    return segment_dialogue


def generate_segment_transcript(
    frame_paths: List[Path],
    segment_num: int,
    total_segments: int,
    start_time: float,
    end_time: float,
    full_speech_transcript: str,
    total_duration: float,
) -> str:
    """
    Generate transcript for a single video segment with relevant dialogue.
    """
    # Extract dialogue specific to this time segment
    segment_dialogue = extract_dialogue_for_timerange(
        full_speech_transcript,
        start_time,
        end_time,
        total_duration
    )
    
    # We no longer send frames directly to the model; instead we describe
    # what should be captured using the time range and dialogue.
    print(
        f"  Processing segment {segment_num}/{total_segments} "
        f"({start_time:.1f}s - {end_time:.1f}s) with text-only Gemini analysis..."
    )

    llm = LLMClient()

    system_prompt = (
        "You are analyzing a short segment from a children's video. "
        "You will be given the approximate time range and the dialogue that occurs "
        "in this segment. Your job is to reconstruct a detailed scene description "
        "that would help another expert understand what is happening on screen."
    )

    user_prompt = f"""
SEGMENT {segment_num} OF {total_segments}
TIME RANGE: {start_time:.1f}s to {end_time:.1f}s

DIALOGUE IN THIS SEGMENT:
\"\"\"{segment_dialogue}\"\"\"

Write 2–3 vivid paragraphs describing:
1. The setting and environment.
2. What the characters are likely doing, feeling, and how they are interacting.
3. How the dialogue fits into the unfolding action.

Do NOT summarize the whole video—focus only on this time window.
"""

    description = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=800,
    )

    return (
        f"[SEGMENT {segment_num}/{total_segments}: {start_time:.1f}s - {end_time:.1f}s]\n"
        f"{description.strip()}\n"
    )


def generate_dialogue_transcript(speech_transcript: str) -> str:
    """
    Turn raw ASR text into a dialogue-style transcript with speaker labels.
    """
    if not speech_transcript:
        return "[DIALOGUE TRANSCRIPT UNAVAILABLE – empty transcription]"

    if speech_transcript.startswith("[TRANSCRIPTION FAILED]"):
        return (
            "DIALOGUE TRANSCRIPT\n"
            "===================\n"
            "Speaker diarization unavailable because transcription failed.\n\n"
            "Raw content:\n"
            f"{speech_transcript}\n"
        )

    llm = LLMClient()

    system_prompt = (
        "You are given a raw automatic speech recognition transcript of a children's video.\n"
        "Your job is to turn it into a clean DIALOGUE transcript that labels who speaks."
    )

    user_prompt = f"""
REQUIREMENTS:
1. Do NOT summarize or omit content. Keep ALL lines and information.
2. Split the text into natural utterances.
3. Assign speaker labels like SPEAKER 1, SPEAKER 2, NARRATOR, CHILD 1, etc.
   - Be consistent: the same person must always keep the same label.
   - Infer speaker changes from the text structure and cues.
4. If you are unsure who is speaking, still assign a consistent label.
5. Keep the original chronological order of everything said.
6. Use this format:
   SPEAKER 1: "…"
   SPEAKER 2: "…"
   NARRATOR: "…"
7. DO NOT drop jokes, asides, or filler words; preserve the full content.

Now convert this raw transcript into a fully labeled dialogue transcript:

RAW TRANSCRIPT:
\"\"\"{speech_transcript}\"\"\"
"""

    labeled = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2000,
    )

    return labeled.strip()


def generate_scene_summary(vllm_transcript: str) -> str:
    """
    Take the long, detailed multimodal analysis and turn it into:
      - scene-by-scene breakdown (in order, covering entire video)
      - plus a final 'Global Evaluation' section.
    """
    if not vllm_transcript:
        return "[SCENE SUMMARY UNAVAILABLE – no analysis text]"

    llm = LLMClient()

    system_prompt = (
        "You are given a detailed, segment-by-segment analysis of a children's video "
        "that already includes both visual descriptions and dialogue."
    )

    user_prompt = f"""
YOUR JOB:
1. Infer the SCENE structure of the video (changes in location, time, or activity).
2. Produce a scene-by-scene breakdown that covers the ENTIRE video in order.
3. Include ALL important events mentioned in the analysis; do NOT skip segments.
4. For each scene, include:
   - SCENE number
   - Approximate time range (if possible, based on the text; otherwise, 'approx.')
   - Brief title (one line)
   - 1–3 paragraphs describing exactly what happens: actions, dialogue, emotions.
5. At the end, add a 'GLOBAL EVALUATION' section that:
   - Summarizes the overall story
   - Comments on pacing, tone, and structure
   - Notes any recurring themes or patterns
   - Evaluates the video as a complete unit.

FORMATTING:
Use this structure exactly:

SCENE 1 [00:00–00:35] – Short scene title
Detailed description...

SCENE 2 [00:35–01:10] – Short scene title
Detailed description...

...

GLOBAL EVALUATION
-----------------
Your global comments here.

Now, here is the full analysis to rewrite into that format:

FULL SEGMENT ANALYSIS:
\"\"\"{vllm_transcript}\"\"\"
"""

    summary = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2500,
    )

    return summary.strip()

