"""
Semantic content metrics using LLM analysis.
Analyzes prosocial behavior, aggression, SEL strategies, fantasy, interactivity.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from .video_preprocess import TranscriptSegment
from .llm_client import LLMClient


@dataclass
class SegmentLabels:
    """Labels for a transcript segment from LLM analysis."""
    start_time: float
    end_time: float
    prosocial_events: List[str]
    aggressive_events: List[str]
    fantasy_level: str  # "none", "low", "medium", "high"
    sel_strategies: List[str]
    direct_address: bool
    fear_intense: bool
    impossible_events: List[str]


def chunk_transcript_by_time(transcript_segments: List[TranscriptSegment], 
                             chunk_duration: float = 30.0) -> List[Tuple[float, float, str]]:
    """
    Chunk transcript into time-based segments for LLM analysis.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        chunk_duration: Target duration for each chunk in seconds
        
    Returns:
        List of (start_time, end_time, text) tuples
    """
    if not transcript_segments:
        return []
    
    chunks = []
    current_chunk_text = []
    current_start = transcript_segments[0].start
    current_end = current_start
    
    for segment in transcript_segments:
        # Check if adding this segment would exceed chunk duration
        if segment.end - current_start > chunk_duration and current_chunk_text:
            # Save current chunk
            chunks.append((current_start, current_end, " ".join(current_chunk_text)))
            # Start new chunk
            current_chunk_text = [segment.text]
            current_start = segment.start
            current_end = segment.end
        else:
            # Add to current chunk
            current_chunk_text.append(segment.text)
            current_end = segment.end
    
    # Add final chunk
    if current_chunk_text:
        chunks.append((current_start, current_end, " ".join(current_chunk_text)))
    
    return chunks


def llm_label_segments(transcript_segments: List[TranscriptSegment], 
                       llm_client: LLMClient,
                       chunk_duration: float = 30.0) -> List[SegmentLabels]:
    """
    Use LLM to label semantic content in transcript segments.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        llm_client: LLMClient instance
        chunk_duration: Duration of chunks to analyze
        
    Returns:
        List of SegmentLabels
    """
    # Chunk transcript
    chunks = chunk_transcript_by_time(transcript_segments, chunk_duration)
    
    labels = []
    for start_time, end_time, text in chunks:
        if not text.strip():
            continue
        
        try:
            # Get LLM classification
            result = llm_client.classify_segment_events(text, end_time - start_time)
            
            labels.append(SegmentLabels(
                start_time=start_time,
                end_time=end_time,
                prosocial_events=result.get("prosocial_events", []),
                aggressive_events=result.get("aggressive_events", []),
                fantasy_level=result.get("fantasy_level", "none"),
                sel_strategies=result.get("sel_strategies", []),
                direct_address=result.get("direct_address", False),
                fear_intense=result.get("fear_intense", False),
                impossible_events=result.get("impossible_events", [])
            ))
        except Exception as e:
            print(f"Error labeling segment {start_time}-{end_time}: {e}")
            # Add empty label on error
            labels.append(SegmentLabels(
                start_time=start_time,
                end_time=end_time,
                prosocial_events=[],
                aggressive_events=[],
                fantasy_level="none",
                sel_strategies=[],
                direct_address=False,
                fear_intense=False,
                impossible_events=[]
            ))
    
    return labels


def compute_event_metrics_from_labels(segment_labels: List[SegmentLabels], 
                                      duration_minutes: float) -> Dict[str, float]:
    """
    Compute per-minute event rates from LLM labels.
    
    Args:
        segment_labels: List of SegmentLabels
        duration_minutes: Total video duration in minutes
        
    Returns:
        Dictionary with event-based metrics
    """
    if not segment_labels or duration_minutes <= 0:
        return {
            "prosocial_rate": 0.0,
            "aggression_rate": 0.0,
            "prosocial_ratio": 0.5,
            "sel_strategy_rate": 0.0,
            "direct_address_rate": 0.0,
            "interactive_block_count": 0,
            "fantasy_rate": 0.0,
            "impossible_event_rate": 0.0,
            "fear_intense_rate": 0.0
        }
    
    # Count events across all segments
    total_prosocial = sum(len(label.prosocial_events) for label in segment_labels)
    total_aggressive = sum(len(label.aggressive_events) for label in segment_labels)
    total_sel = sum(len(label.sel_strategies) for label in segment_labels)
    total_impossible = sum(len(label.impossible_events) for label in segment_labels)
    
    # Count segments with specific features
    direct_address_segments = sum(1 for label in segment_labels if label.direct_address)
    fear_intense_segments = sum(1 for label in segment_labels if label.fear_intense)
    
    # Count fantasy levels
    fantasy_mapping = {"none": 0, "low": 0.33, "medium": 0.67, "high": 1.0}
    fantasy_scores = [fantasy_mapping.get(label.fantasy_level, 0) for label in segment_labels]
    fantasy_rate = sum(fantasy_scores) / len(fantasy_scores) if fantasy_scores else 0.0
    
    # Compute rates
    prosocial_rate = total_prosocial / duration_minutes
    aggression_rate = total_aggressive / duration_minutes
    sel_strategy_rate = total_sel / duration_minutes
    impossible_event_rate = total_impossible / duration_minutes
    direct_address_rate = direct_address_segments / duration_minutes
    fear_intense_rate = fear_intense_segments / duration_minutes
    
    # Compute prosocial ratio
    total_social_events = total_prosocial + total_aggressive
    if total_social_events > 0:
        prosocial_ratio = total_prosocial / total_social_events
    else:
        prosocial_ratio = 0.5  # Neutral if no social events
    
    # Interactive block count (same as direct address segments for now)
    interactive_block_count = direct_address_segments
    
    return {
        "prosocial_rate": prosocial_rate,
        "aggression_rate": aggression_rate,
        "prosocial_ratio": prosocial_ratio,
        "sel_strategy_rate": sel_strategy_rate,
        "direct_address_rate": direct_address_rate,
        "interactive_block_count": interactive_block_count,
        "fantasy_rate": fantasy_rate,
        "impossible_event_rate": impossible_event_rate,
        "fear_intense_rate": fear_intense_rate
    }


def compute_event_metrics_heuristic(
    transcript_segments: List[TranscriptSegment],
    duration_minutes: float,
) -> Dict[str, float]:
    """
    FAST heuristic semantic metrics (no LLM).

    We scan the full transcript for simple keyword lists to approximate
    prosocial / aggression / SEL / fantasy / interactivity. This is much
    faster than LLM labeling while still giving more signal than flat defaults.
    """
    if not transcript_segments or duration_minutes <= 0:
        return {
            "prosocial_rate": 0.0,
            "aggression_rate": 0.0,
            "prosocial_ratio": 0.5,
            "sel_strategy_rate": 0.0,
            "direct_address_rate": 0.0,
            "interactive_block_count": 0,
            "fantasy_rate": 0.0,
            "impossible_event_rate": 0.0,
            "fear_intense_rate": 0.0,
        }

    full_text = " ".join(seg.text for seg in transcript_segments).lower()

    prosocial_words = [
        "share",
        "sharing",
        "kind",
        "kindness",
        "help",
        "helping",
        "sorry",
        "apologize",
        "apology",
        "please",
        "thank you",
        "friend",
        "friends",
        "teamwork",
        "together",
        "cooperate",
        "cooperation",
    ]
    aggression_words = [
        "hit",
        "hitting",
        "kick",
        "kicking",
        "fight",
        "fighting",
        "punch",
        "angry",
        "mad",
        "mean",
        "yell",
        "shout",
    ]
    sel_words = [
        "calm down",
        "deep breath",
        "breathe",
        "feelings",
        "how do you feel",
        "use your words",
        "take a break",
        "count to",
    ]
    direct_address_phrases = [
        "can you",
        "will you",
        "let's",
        "let us",
        "do you want to",
        "join us",
        "come on",
    ]
    fantasy_words = [
        "magic",
        "fairy",
        "dragon",
        "wizard",
        "superhero",
        "castle",
        "princess",
        "unicorn",
    ]
    impossible_words = [
        "fly",
        "flying",
        "invisible",
        "time travel",
        "teleport",
    ]
    fear_words = [
        "scary",
        "afraid",
        "monster",
        "ghost",
        "danger",
        "creepy",
    ]

    def count_occurrences(words):
        return sum(full_text.count(w) for w in words)

    total_prosocial = count_occurrences(prosocial_words)
    total_aggressive = count_occurrences(aggression_words)
    total_sel = count_occurrences(sel_words)
    total_impossible = count_occurrences(impossible_words)
    total_fantasy_markers = count_occurrences(fantasy_words)
    total_fear = count_occurrences(fear_words)
    direct_address_segments = count_occurrences(direct_address_phrases)

    prosocial_rate = total_prosocial / duration_minutes
    aggression_rate = total_aggressive / duration_minutes
    sel_strategy_rate = total_sel / duration_minutes
    impossible_event_rate = total_impossible / duration_minutes
    fantasy_rate = total_fantasy_markers / duration_minutes
    fear_intense_rate = total_fear / duration_minutes
    direct_address_rate = direct_address_segments / duration_minutes

    total_social_events = total_prosocial + total_aggressive
    if total_social_events > 0:
        prosocial_ratio = total_prosocial / total_social_events
    else:
        prosocial_ratio = 0.5

    interactive_block_count = direct_address_segments

    return {
        "prosocial_rate": float(prosocial_rate),
        "aggression_rate": float(aggression_rate),
        "prosocial_ratio": float(prosocial_ratio),
        "sel_strategy_rate": float(sel_strategy_rate),
        "direct_address_rate": float(direct_address_rate),
        "interactive_block_count": int(interactive_block_count),
        "fantasy_rate": float(fantasy_rate),
        "impossible_event_rate": float(impossible_event_rate),
        "fear_intense_rate": float(fear_intense_rate),
    }


def compute_narrative_metrics_embeddings(transcript_segments: List[TranscriptSegment],
                                        chunk_duration: float = 30.0) -> Dict[str, float]:
    """
    Compute narrative coherence using sentence embeddings.
    Alternative to LLM-based coherence analysis.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        chunk_duration: Duration of chunks to compare
        
    Returns:
        Dictionary with:
        - adjacent_similarity_mean: Average similarity between adjacent chunks
        - topic_jumps: Fraction of transitions with low similarity
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        
        # Load model
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Chunk transcript
        chunks = chunk_transcript_by_time(transcript_segments, chunk_duration)
        
        if len(chunks) < 2:
            return {"adjacent_similarity_mean": 1.0, "topic_jumps": 0.0}
        
        # Get embeddings for each chunk
        chunk_texts = [text for _, _, text in chunks]
        embeddings = model.encode(chunk_texts)
        
        # Compute cosine similarity between adjacent chunks
        similarities = []
        for i in range(len(embeddings) - 1):
            emb1 = embeddings[i]
            emb2 = embeddings[i + 1]
            # Cosine similarity
            similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
            similarities.append(similarity)
        
        adjacent_similarity_mean = float(np.mean(similarities))
        
        # Define "topic jump" as similarity < 0.4
        topic_jump_threshold = 0.4
        topic_jumps = sum(1 for s in similarities if s < topic_jump_threshold) / len(similarities)
        
        return {
            "adjacent_similarity_mean": adjacent_similarity_mean,
            "topic_jumps": float(topic_jumps)
        }
    
    except ImportError:
        print("sentence-transformers not installed. Install with: pip install sentence-transformers")
        # Fallback to LLM-based analysis
        return {"adjacent_similarity_mean": 0.7, "topic_jumps": 0.2}
    except Exception as e:
        print(f"Error computing narrative metrics with embeddings: {e}")
        return {"adjacent_similarity_mean": 0.7, "topic_jumps": 0.2}


def compute_narrative_metrics_llm(transcript_segments: List[TranscriptSegment],
                                  llm_client: LLMClient,
                                  chunk_duration: float = 30.0) -> Dict[str, float]:
    """
    Compute narrative coherence using LLM analysis.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        llm_client: LLMClient instance
        chunk_duration: Duration of chunks to summarize
        
    Returns:
        Dictionary with:
        - adjacent_similarity_mean: Average coherence rating
        - topic_jumps: Fraction of abrupt topic changes
    """
    # Chunk transcript
    chunks = chunk_transcript_by_time(transcript_segments, chunk_duration)
    
    if len(chunks) < 2:
        return {"adjacent_similarity_mean": 1.0, "topic_jumps": 0.0}
    
    # Generate summaries for each chunk
    summaries = []
    for start_time, end_time, text in chunks:
        if not text.strip():
            summaries.append("(silence)")
            continue
        
        try:
            summary = llm_client.generate_segment_summary(text)
            summaries.append(summary)
        except Exception as e:
            print(f"Error generating summary for chunk {start_time}-{end_time}: {e}")
            summaries.append(text[:100])  # Fallback to truncated text
    
    # Use LLM to rate coherence
    try:
        result = llm_client.rate_narrative_coherence(summaries)
        return result
    except Exception as e:
        print(f"Error rating narrative coherence: {e}")
        return {"adjacent_similarity_mean": 0.7, "topic_jumps": 0.2}


def compute_narrative_metrics(transcript_segments: List[TranscriptSegment],
                              llm_client: Optional[LLMClient] = None,
                              use_embeddings: bool = True,
                              chunk_duration: float = 30.0) -> Dict[str, float]:
    """
    Compute narrative coherence metrics.
    Tries embedding-based approach first, falls back to LLM if needed.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        llm_client: Optional LLMClient for LLM-based analysis
        use_embeddings: Whether to try embedding-based approach first
        chunk_duration: Duration of chunks to analyze
        
    Returns:
        Dictionary with narrative metrics
    """
    if use_embeddings:
        result = compute_narrative_metrics_embeddings(transcript_segments, chunk_duration)
        # Check if embeddings worked (will return default values on failure)
        if result["adjacent_similarity_mean"] != 0.7:  # Not the fallback value
            return result
    
    # Fallback to LLM if embeddings failed or not requested
    if llm_client:
        return compute_narrative_metrics_llm(transcript_segments, llm_client, chunk_duration)
    else:
        print("No LLM client provided for narrative analysis, using defaults")
        return {"adjacent_similarity_mean": 0.7, "topic_jumps": 0.2}

