"""
Configuration file for all thresholds, age bands, metric definitions, and weights.
"""

# Age band definitions (in years)
AGE_BANDS = {
    "G1_0_2": {"min_age": 0, "max_age": 2, "label": "Infant/Toddler"},
    "G2_2_3": {"min_age": 2, "max_age": 3, "label": "Early Preschool"},
    "G3_3_5": {"min_age": 3, "max_age": 5, "label": "Preschool"},
    "G4_5_8": {"min_age": 5, "max_age": 8, "label": "Early Elementary"},
}

# Metric configurations with ideal ranges and hard limits per age band
# Direction: "lower_better", "higher_better", "mid" (target middle range)
METRIC_CONFIG = {
    "cuts_per_minute": {
        "G1_0_2": {"ideal_low": 0, "ideal_high": 6, "hard_max": 20, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0, "ideal_high": 8, "hard_max": 25, "direction": "lower_better"},
        "G3_3_5": {"ideal_low": 4, "ideal_high": 12, "hard_max": 30, "direction": "mid"},
        "G4_5_8": {"ideal_low": 4, "ideal_high": 15, "hard_max": 35, "direction": "mid"},
    },
    "avg_shot_length": {
        "G1_0_2": {"ideal_low": 8, "ideal_high": 100, "hard_min": 2, "direction": "higher_better"},
        "G2_2_3": {"ideal_low": 6, "ideal_high": 100, "hard_min": 2, "direction": "higher_better"},
        "G3_3_5": {"ideal_low": 4, "ideal_high": 20, "hard_min": 1, "direction": "mid"},
        "G4_5_8": {"ideal_low": 3, "ideal_high": 15, "hard_min": 1, "direction": "mid"},
    },
    "motion_high_frac": {
        "G1_0_2": {"ideal_low": 0.0, "ideal_high": 0.2, "hard_max": 0.6, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0.0, "ideal_high": 0.3, "hard_max": 0.7, "direction": "lower_better"},
        "G3_3_5": {"ideal_low": 0.1, "ideal_high": 0.4, "hard_max": 0.8, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0.1, "ideal_high": 0.5, "hard_max": 0.9, "direction": "mid"},
    },
    "loudness_mean": {
        "G1_0_2": {"ideal_low": -20, "ideal_high": -10, "hard_max": -5, "direction": "mid"},
        "G2_2_3": {"ideal_low": -20, "ideal_high": -8, "hard_max": -3, "direction": "mid"},
        "G3_3_5": {"ideal_low": -18, "ideal_high": -6, "hard_max": -2, "direction": "mid"},
        "G4_5_8": {"ideal_low": -18, "ideal_high": -5, "hard_max": 0, "direction": "mid"},
    },
    "music_ratio": {
        "G1_0_2": {"ideal_low": 0.3, "ideal_high": 0.7, "hard_max": 1.0, "direction": "mid"},
        "G2_2_3": {"ideal_low": 0.25, "ideal_high": 0.65, "hard_max": 1.0, "direction": "mid"},
        "G3_3_5": {"ideal_low": 0.2, "ideal_high": 0.6, "hard_max": 1.0, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0.15, "ideal_high": 0.5, "hard_max": 1.0, "direction": "mid"},
    },
    "sfx_rate": {
        "G1_0_2": {"ideal_low": 0, "ideal_high": 2, "hard_max": 8, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0, "ideal_high": 3, "hard_max": 10, "direction": "lower_better"},
        "G3_3_5": {"ideal_low": 1, "ideal_high": 5, "hard_max": 15, "direction": "mid"},
        "G4_5_8": {"ideal_low": 1, "ideal_high": 6, "hard_max": 20, "direction": "mid"},
    },
    "adjacent_similarity_mean": {
        "G1_0_2": {"ideal_low": 0.7, "ideal_high": 1.0, "hard_min": 0.4, "direction": "higher_better"},
        "G2_2_3": {"ideal_low": 0.65, "ideal_high": 1.0, "hard_min": 0.35, "direction": "higher_better"},
        "G3_3_5": {"ideal_low": 0.6, "ideal_high": 0.9, "hard_min": 0.3, "direction": "higher_better"},
        "G4_5_8": {"ideal_low": 0.55, "ideal_high": 0.85, "hard_min": 0.25, "direction": "higher_better"},
    },
    "topic_jumps": {
        "G1_0_2": {"ideal_low": 0.0, "ideal_high": 0.1, "hard_max": 0.3, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0.0, "ideal_high": 0.15, "hard_max": 0.4, "direction": "lower_better"},
        "G3_3_5": {"ideal_low": 0.0, "ideal_high": 0.2, "hard_max": 0.5, "direction": "lower_better"},
        "G4_5_8": {"ideal_low": 0.0, "ideal_high": 0.25, "hard_max": 0.6, "direction": "lower_better"},
    },
    "type_token_ratio": {
        "G1_0_2": {"ideal_low": 0.3, "ideal_high": 0.5, "hard_min": 0.1, "direction": "mid"},
        "G2_2_3": {"ideal_low": 0.35, "ideal_high": 0.55, "hard_min": 0.15, "direction": "mid"},
        "G3_3_5": {"ideal_low": 0.4, "ideal_high": 0.65, "hard_min": 0.2, "direction": "higher_better"},
        "G4_5_8": {"ideal_low": 0.45, "ideal_high": 0.75, "hard_min": 0.25, "direction": "higher_better"},
    },
    "mean_utterance_length": {
        "G1_0_2": {"ideal_low": 3, "ideal_high": 6, "hard_max": 12, "direction": "mid"},
        "G2_2_3": {"ideal_low": 4, "ideal_high": 8, "hard_max": 15, "direction": "mid"},
        "G3_3_5": {"ideal_low": 5, "ideal_high": 10, "hard_max": 20, "direction": "mid"},
        "G4_5_8": {"ideal_low": 6, "ideal_high": 12, "hard_max": 25, "direction": "mid"},
    },
    "tier2_vocab_frac": {
        "G1_0_2": {"ideal_low": 0.0, "ideal_high": 0.1, "hard_max": 0.3, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0.05, "ideal_high": 0.15, "hard_max": 0.4, "direction": "mid"},
        "G3_3_5": {"ideal_low": 0.1, "ideal_high": 0.25, "hard_max": 0.5, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0.15, "ideal_high": 0.35, "hard_max": 0.6, "direction": "higher_better"},
    },
    "question_rate": {
        "G1_0_2": {"ideal_low": 1, "ideal_high": 4, "hard_max": 10, "direction": "mid"},
        "G2_2_3": {"ideal_low": 2, "ideal_high": 5, "hard_max": 12, "direction": "mid"},
        "G3_3_5": {"ideal_low": 2, "ideal_high": 6, "hard_max": 15, "direction": "mid"},
        "G4_5_8": {"ideal_low": 2, "ideal_high": 7, "hard_max": 18, "direction": "mid"},
    },
    "prosocial_ratio": {
        "G1_0_2": {"ideal_low": 0.7, "ideal_high": 1.0, "hard_min": 0.3, "direction": "higher_better"},
        "G2_2_3": {"ideal_low": 0.65, "ideal_high": 1.0, "hard_min": 0.3, "direction": "higher_better"},
        "G3_3_5": {"ideal_low": 0.6, "ideal_high": 1.0, "hard_min": 0.25, "direction": "higher_better"},
        "G4_5_8": {"ideal_low": 0.55, "ideal_high": 1.0, "hard_min": 0.2, "direction": "higher_better"},
    },
    "aggression_rate": {
        "G1_0_2": {"ideal_low": 0, "ideal_high": 0.5, "hard_max": 3, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0, "ideal_high": 1, "hard_max": 4, "direction": "lower_better"},
        "G3_3_5": {"ideal_low": 0, "ideal_high": 1.5, "hard_max": 5, "direction": "lower_better"},
        "G4_5_8": {"ideal_low": 0, "ideal_high": 2, "hard_max": 6, "direction": "lower_better"},
    },
    "sel_strategy_rate": {
        "G1_0_2": {"ideal_low": 0.5, "ideal_high": 3, "hard_max": 10, "direction": "higher_better"},
        "G2_2_3": {"ideal_low": 1, "ideal_high": 4, "hard_max": 12, "direction": "higher_better"},
        "G3_3_5": {"ideal_low": 1.5, "ideal_high": 5, "hard_max": 15, "direction": "higher_better"},
        "G4_5_8": {"ideal_low": 2, "ideal_high": 6, "hard_max": 18, "direction": "higher_better"},
    },
    "emotion_word_rate": {
        "G1_0_2": {"ideal_low": 1, "ideal_high": 4, "hard_max": 10, "direction": "mid"},
        "G2_2_3": {"ideal_low": 1.5, "ideal_high": 5, "hard_max": 12, "direction": "mid"},
        "G3_3_5": {"ideal_low": 2, "ideal_high": 6, "hard_max": 15, "direction": "higher_better"},
        "G4_5_8": {"ideal_low": 2.5, "ideal_high": 7, "hard_max": 18, "direction": "higher_better"},
    },
    "mental_state_word_rate": {
        "G1_0_2": {"ideal_low": 0.5, "ideal_high": 2, "hard_max": 6, "direction": "mid"},
        "G2_2_3": {"ideal_low": 1, "ideal_high": 3, "hard_max": 8, "direction": "mid"},
        "G3_3_5": {"ideal_low": 1.5, "ideal_high": 4, "hard_max": 10, "direction": "higher_better"},
        "G4_5_8": {"ideal_low": 2, "ideal_high": 5, "hard_max": 12, "direction": "higher_better"},
    },
    "fantasy_rate": {
        "G1_0_2": {"ideal_low": 0.2, "ideal_high": 0.6, "hard_max": 0.9, "direction": "mid"},
        "G2_2_3": {"ideal_low": 0.3, "ideal_high": 0.7, "hard_max": 0.95, "direction": "mid"},
        "G3_3_5": {"ideal_low": 0.3, "ideal_high": 0.8, "hard_max": 1.0, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0.2, "ideal_high": 0.7, "hard_max": 1.0, "direction": "mid"},
    },
    "impossible_event_rate": {
        "G1_0_2": {"ideal_low": 0, "ideal_high": 2, "hard_max": 8, "direction": "lower_better"},
        "G2_2_3": {"ideal_low": 0, "ideal_high": 3, "hard_max": 10, "direction": "lower_better"},
        "G3_3_5": {"ideal_low": 0, "ideal_high": 4, "hard_max": 12, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0, "ideal_high": 5, "hard_max": 15, "direction": "mid"},
    },
    "direct_address_rate": {
        "G1_0_2": {"ideal_low": 3, "ideal_high": 8, "hard_max": 20, "direction": "higher_better"},
        "G2_2_3": {"ideal_low": 2, "ideal_high": 6, "hard_max": 15, "direction": "higher_better"},
        "G3_3_5": {"ideal_low": 1, "ideal_high": 5, "hard_max": 12, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0.5, "ideal_high": 3, "hard_max": 10, "direction": "mid"},
    },
    "interactive_block_count": {
        "G1_0_2": {"ideal_low": 3, "ideal_high": 10, "hard_max": 30, "direction": "higher_better"},
        "G2_2_3": {"ideal_low": 2, "ideal_high": 8, "hard_max": 25, "direction": "higher_better"},
        "G3_3_5": {"ideal_low": 1, "ideal_high": 6, "hard_max": 20, "direction": "mid"},
        "G4_5_8": {"ideal_low": 0, "ideal_high": 4, "hard_max": 15, "direction": "mid"},
    },
}

# Dimension definitions - which metrics belong to which dimension
DIMENSIONS = {
    "Pacing": [
        "cuts_per_minute",
        "avg_shot_length",
        "motion_high_frac",
        "loudness_mean",
        "music_ratio",
        "sfx_rate",
    ],
    "Story": [
        "adjacent_similarity_mean",
        "topic_jumps",
    ],
    "Language": [
        "type_token_ratio",
        "mean_utterance_length",
        "tier2_vocab_frac",
        "question_rate",
    ],
    "SEL": [
        "prosocial_ratio",
        "aggression_rate",
        "sel_strategy_rate",
        "emotion_word_rate",
        "mental_state_word_rate",
    ],
    "Fantasy": [
        "fantasy_rate",
        "impossible_event_rate",
    ],
    "Interactivity": [
        "direct_address_rate",
        "interactive_block_count",
    ],
}

# Developmental Score Weights per dimension per age band
# Higher values mean better development
DEV_WEIGHTS = {
    "G1_0_2": {
        "Pacing": 0.20,      # Very important - sensory regulation
        "Story": 0.15,       # Simple coherence matters
        "Language": 0.20,    # Critical for language acquisition
        "SEL": 0.25,         # Most important - emotional foundation
        "Fantasy": 0.05,     # Less relevant at this age
        "Interactivity": 0.15,  # Important for engagement
    },
    "G2_2_3": {
        "Pacing": 0.18,
        "Story": 0.18,
        "Language": 0.22,
        "SEL": 0.25,
        "Fantasy": 0.07,
        "Interactivity": 0.10,
    },
    "G3_3_5": {
        "Pacing": 0.15,
        "Story": 0.20,
        "Language": 0.25,
        "SEL": 0.25,
        "Fantasy": 0.05,
        "Interactivity": 0.10,
    },
    "G4_5_8": {
        "Pacing": 0.12,
        "Story": 0.23,
        "Language": 0.25,
        "SEL": 0.23,
        "Fantasy": 0.07,
        "Interactivity": 0.10,
    },
}

# Brainrot Index Weights per dimension per age band
# Higher values mean MORE brainrot risk
# Note: Some dimensions contribute more to brainrot risk than dev score
BRAINROT_WEIGHTS = {
    "G1_0_2": {
        "Pacing": 0.40,      # Hyperstimulation is THE risk
        "Story": 0.10,       # Incoherence contributes
        "Language": 0.05,    # Less direct brainrot factor
        "SEL": 0.30,         # Aggression/fear are big risks
        "Fantasy": 0.10,     # Confusing reality
        "Interactivity": 0.05,  # Not a major brainrot factor
    },
    "G2_2_3": {
        "Pacing": 0.38,
        "Story": 0.12,
        "Language": 0.05,
        "SEL": 0.28,
        "Fantasy": 0.12,
        "Interactivity": 0.05,
    },
    "G3_3_5": {
        "Pacing": 0.35,
        "Story": 0.15,
        "Language": 0.10,
        "SEL": 0.25,
        "Fantasy": 0.15,
        "Interactivity": 0.00,
    },
    "G4_5_8": {
        "Pacing": 0.30,
        "Story": 0.18,
        "Language": 0.12,
        "SEL": 0.22,
        "Fantasy": 0.13,
        "Interactivity": 0.05,
    },
}

# Lexicons for text analysis
EMOTION_WORDS = {
    "happy", "sad", "angry", "scared", "excited", "worried", "surprised", "proud",
    "frustrated", "disappointed", "joyful", "afraid", "nervous", "calm", "upset",
    "cheerful", "mad", "frightened", "delighted", "anxious", "content", "grumpy",
    "terrified", "thrilled", "annoyed", "peaceful", "furious", "ecstatic"
}

MENTAL_STATE_WORDS = {
    "think", "thought", "know", "knew", "believe", "believed", "remember",
    "remembered", "forget", "forgot", "understand", "understood", "wonder",
    "wondered", "imagine", "imagined", "realize", "realized", "guess", "guessed",
    "suppose", "supposed", "feel", "felt", "wish", "wished", "hope", "hoped",
    "want", "wanted", "need", "needed", "decide", "decided"
}

# Basic vocabulary (Tier 1) - common words for young children
# For simplicity, we'll check against a larger list but here's a sample
TIER1_VOCAB = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "I", "you", "he", "she", "it", "we", "they",
    "me", "him", "her", "us", "them", "my", "your", "his", "her", "its", "our",
    "their", "this", "that", "these", "those", "what", "which", "who", "when",
    "where", "why", "how", "all", "some", "any", "many", "much", "more", "most",
    "good", "bad", "big", "small", "long", "short", "hot", "cold", "old", "new",
    "yes", "no", "not", "very", "too", "so", "here", "there", "up", "down", "in",
    "out", "on", "off", "over", "under", "again", "time", "day", "year", "way",
    "work", "back", "use", "make", "go", "come", "get", "give", "take", "see",
    "look", "want", "like", "help", "tell", "call", "try", "ask", "need", "feel",
    "become", "leave", "put", "mean", "keep", "let", "begin", "seem", "play",
    "run", "move", "live", "eat", "say", "talk", "mom", "dad", "mama", "papa",
    "baby", "boy", "girl", "man", "woman", "child", "friend", "home", "house",
    "car", "dog", "cat", "bird", "tree", "food", "water", "milk", "red", "blue",
    "green", "yellow", "black", "white", "happy", "sad", "fun", "love", "ok", "okay"
}

# LLM Configuration (Claude via the Anthropic API)
LLM_CONFIG = {
    # Default Claude model; can be overridden with ANTHROPIC_MODEL.
    "model": None,  # None -> LLMClient resolves ANTHROPIC_MODEL or its default
    "temperature": None,  # unused; kept for back-compat
    "max_tokens": 2000,
    "segment_duration": 30,  # seconds per segment for LLM analysis
}

