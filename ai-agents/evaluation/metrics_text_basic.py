"""
Basic text metrics computation using NLP.
Analyzes vocabulary, sentence structure, questions, and emotion words.
"""

import re
from typing import List, Dict, Set
from collections import Counter
from .video_preprocess import TranscriptSegment
from .config import EMOTION_WORDS, MENTAL_STATE_WORDS, TIER1_VOCAB


def flatten_transcript(transcript_segments: List[TranscriptSegment]) -> str:
    """
    Join all transcript segments into a single text.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        
    Returns:
        Combined text
    """
    return " ".join([seg.text for seg in transcript_segments])


def tokenize_words(text: str) -> List[str]:
    """
    Simple word tokenization.
    
    Args:
        text: Input text
        
    Returns:
        List of word tokens (lowercase, alphanumeric only)
    """
    # Convert to lowercase and extract alphanumeric tokens
    words = re.findall(r'\b[a-z]+\b', text.lower())
    return words


def split_sentences(text: str) -> List[str]:
    """
    Simple sentence splitting.
    
    Args:
        text: Input text
        
    Returns:
        List of sentences
    """
    # Split on sentence terminators
    sentences = re.split(r'[.!?]+', text)
    # Filter empty and strip whitespace
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def compute_type_token_ratio(tokens: List[str]) -> float:
    """
    Compute type-token ratio (vocabulary diversity).
    
    Args:
        tokens: List of word tokens
        
    Returns:
        Ratio of unique words to total words
    """
    if not tokens:
        return 0.0
    
    types = len(set(tokens))
    tokens_count = len(tokens)
    
    return types / tokens_count


def compute_mean_utterance_length(sentences: List[str]) -> float:
    """
    Compute mean utterance length in words.
    
    Args:
        sentences: List of sentences
        
    Returns:
        Average number of words per sentence
    """
    if not sentences:
        return 0.0
    
    word_counts = [len(tokenize_words(s)) for s in sentences]
    return sum(word_counts) / len(word_counts)


def is_question(sentence: str) -> bool:
    """
    Determine if a sentence is a question.
    
    Args:
        sentence: Input sentence
        
    Returns:
        True if it's a question
    """
    sentence = sentence.strip().lower()
    
    # Check for question mark
    if sentence.endswith('?'):
        return True
    
    # Check for question words at start
    question_words = ['who', 'what', 'where', 'when', 'why', 'how', 'can', 'could', 
                     'would', 'should', 'is', 'are', 'do', 'does', 'did', 'will']
    
    first_word = sentence.split()[0] if sentence.split() else ''
    if first_word in question_words:
        return True
    
    # Check for "let's" or similar interactive prompts
    if sentence.startswith("let's") or sentence.startswith("lets"):
        return True
    
    return False


def count_emotion_words(tokens: List[str], emotion_lexicon: Set[str] = EMOTION_WORDS) -> int:
    """
    Count emotion words in token list.
    
    Args:
        tokens: List of word tokens
        emotion_lexicon: Set of emotion words
        
    Returns:
        Count of emotion words
    """
    return sum(1 for token in tokens if token in emotion_lexicon)


def count_mental_state_words(tokens: List[str], 
                             mental_state_lexicon: Set[str] = MENTAL_STATE_WORDS) -> int:
    """
    Count mental state words in token list.
    
    Args:
        tokens: List of word tokens
        mental_state_lexicon: Set of mental state words
        
    Returns:
        Count of mental state words
    """
    return sum(1 for token in tokens if token in mental_state_lexicon)


def compute_tier2_vocab_fraction(tokens: List[str], 
                                 tier1_lexicon: Set[str] = TIER1_VOCAB) -> float:
    """
    Compute fraction of words that are Tier 2 (beyond basic vocabulary).
    
    Args:
        tokens: List of word tokens
        tier1_lexicon: Set of basic (Tier 1) vocabulary
        
    Returns:
        Fraction of non-Tier 1 words
    """
    if not tokens:
        return 0.0
    
    # Count tokens not in Tier 1
    tier2_count = sum(1 for token in tokens if token not in tier1_lexicon)
    
    return tier2_count / len(tokens)


def compute_basic_text_metrics(transcript_segments: List[TranscriptSegment]) -> Dict[str, float]:
    """
    Compute all basic text metrics from transcript.
    
    Args:
        transcript_segments: List of TranscriptSegment objects
        
    Returns:
        Dictionary with text metrics:
        - type_token_ratio: Vocabulary diversity
        - mean_utterance_length: Average sentence length in words
        - tier2_vocab_frac: Fraction of advanced vocabulary
        - question_rate: Questions per minute
        - emotion_word_rate: Emotion words per minute
        - mental_state_word_rate: Mental state words per minute
    """
    if not transcript_segments:
        return {
            "type_token_ratio": 0.0,
            "mean_utterance_length": 0.0,
            "tier2_vocab_frac": 0.0,
            "question_rate": 0.0,
            "emotion_word_rate": 0.0,
            "mental_state_word_rate": 0.0
        }
    
    # Get duration in minutes
    duration_sec = max([seg.end for seg in transcript_segments]) if transcript_segments else 0
    duration_min = duration_sec / 60.0 if duration_sec > 0 else 1.0
    
    # Flatten transcript
    full_text = flatten_transcript(transcript_segments)
    
    # Tokenize
    tokens = tokenize_words(full_text)
    
    # Split sentences
    sentences = split_sentences(full_text)
    
    # Compute metrics
    ttr = compute_type_token_ratio(tokens)
    mul = compute_mean_utterance_length(sentences)
    tier2_frac = compute_tier2_vocab_fraction(tokens)
    
    # Count questions
    num_questions = sum(1 for sent in sentences if is_question(sent))
    question_rate = num_questions / duration_min
    
    # Count emotion and mental state words
    emotion_count = count_emotion_words(tokens)
    mental_state_count = count_mental_state_words(tokens)
    
    emotion_rate = emotion_count / duration_min
    mental_state_rate = mental_state_count / duration_min
    
    return {
        "type_token_ratio": ttr,
        "mean_utterance_length": mul,
        "tier2_vocab_frac": tier2_frac,
        "question_rate": question_rate,
        "emotion_word_rate": emotion_rate,
        "mental_state_word_rate": mental_state_rate
    }


def analyze_vocabulary_depth(tokens: List[str]) -> Dict[str, any]:
    """
    Additional vocabulary analysis (optional, for debugging/insights).
    
    Args:
        tokens: List of word tokens
        
    Returns:
        Dictionary with vocabulary statistics
    """
    if not tokens:
        return {
            "total_tokens": 0,
            "unique_tokens": 0,
            "most_common": []
        }
    
    counter = Counter(tokens)
    
    return {
        "total_tokens": len(tokens),
        "unique_tokens": len(counter),
        "most_common": counter.most_common(20)
    }

