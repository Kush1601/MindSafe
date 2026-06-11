"""
LLM Client for semantic content analysis using Claude (Anthropic API).

Usage:
    from llm_client import LLMClient

    client = LLMClient()
    text = client.chat([{"role": "user", "content": "Say hi in one sentence"}])
    print(text)

Env vars:
    ANTHROPIC_API_KEY   (required)
    ANTHROPIC_MODEL     (optional, default: claude-opus-4-8)
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional, Any

import anthropic
from dotenv import load_dotenv

logger = logging.getLogger("mindsafe.llm_client")

# Load environment variables from .env if present
load_dotenv()

DEFAULT_MODEL = "claude-opus-4-8"

# JSON Schemas for structured outputs (additionalProperties must be false).
SEGMENT_EVENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "prosocial_events": {"type": "array", "items": {"type": "string"}},
        "aggressive_events": {"type": "array", "items": {"type": "string"}},
        "fantasy_level": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "sel_strategies": {"type": "array", "items": {"type": "string"}},
        "direct_address": {"type": "boolean"},
        "fear_intense": {"type": "boolean"},
        "impossible_events": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "prosocial_events",
        "aggressive_events",
        "fantasy_level",
        "sel_strategies",
        "direct_address",
        "fear_intense",
        "impossible_events",
    ],
    "additionalProperties": False,
}

COHERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "adjacent_similarity_mean": {"type": "number"},
        "topic_jumps": {"type": "number"},
    },
    "required": ["adjacent_similarity_mean", "topic_jumps"],
    "additionalProperties": False,
}

LANGUAGE_METRICS_SCHEMA = {
    "type": "object",
    "properties": {
        "vocabulary_richness": {"type": "number"},
        "sentence_complexity": {"type": "number"},
        "advanced_vocabulary_fraction": {"type": "number"},
        "question_frequency": {"type": "number"},
    },
    "required": [
        "vocabulary_richness",
        "sentence_complexity",
        "advanced_vocabulary_fraction",
        "question_frequency",
    ],
    "additionalProperties": False,
}


class LLMClient:
    """
    Wrapper for the Anthropic Messages API with helpers
    for content analysis and schema-validated JSON responses.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,  # kept for back-compat; unused
    ):
        """
        Initialize the LLM client.

        Args:
            api_key: Anthropic API key (if None, uses ANTHROPIC_API_KEY)
            model: Model name (if None, uses ANTHROPIC_MODEL or default)
            temperature: Ignored — sampling params are not supported on
                current Claude models; determinism comes from the prompts.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key must be provided via ANTHROPIC_API_KEY env var."
            )

        self.model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._client = anthropic.Anthropic(api_key=self.api_key)

    @staticmethod
    def _split_system(messages: List[Dict[str, str]]):
        """Anthropic takes the system prompt as a top-level param, not a message role."""
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        chat_messages = [m for m in messages if m.get("role") != "system"]
        return ("\n\n".join(system_parts) or None), chat_messages

    def _create(self, messages: List[Dict[str, str]], **kwargs) -> Optional[anthropic.types.Message]:
        """
        Low-level call to the Messages API. Returns the Message, or None on error.
        Logs latency and token usage at DEBUG level.
        """
        system, chat_messages = self._split_system(messages)
        params: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": kwargs.pop("max_tokens", 16000),
            "messages": chat_messages,
        }
        if system:
            params["system"] = system
        params.update(kwargs)

        t0 = time.perf_counter()
        try:
            response = self._client.messages.create(**params)
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = getattr(response, "usage", None)
            logger.debug(
                "[llm_client] model=%s latency=%.0fms input_tokens=%s output_tokens=%s",
                self.model,
                latency_ms,
                getattr(usage, "input_tokens", "?"),
                getattr(usage, "output_tokens", "?"),
            )
            return response
        except anthropic.APIStatusError as e:
            logger.error("[llm_client] Anthropic API error (%s): %s", e.status_code, e.message)
            print(f"[LLMClient] Anthropic API error ({e.status_code}): {e.message}")
            return None
        except anthropic.APIConnectionError as e:
            logger.error("[llm_client] Network error: %s", e)
            print(f"[LLMClient] Network error calling Anthropic API: {e}")
            return None
        except Exception as e:
            logger.error("[llm_client] Unexpected error: %s", e)
            print(f"[LLMClient] Unexpected error calling Anthropic API: {e}")
            return None

    @staticmethod
    def _text(response: Optional[anthropic.types.Message]) -> Optional[str]:
        if response is None:
            return None
        return next((b.text for b in response.content if b.type == "text"), None)

    # ---------- Basic Chat ----------

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Basic chat completion.

        Args:
            messages: List of dicts with 'role' and 'content'
            **kwargs: Extra params for the API (e.g., max_tokens)

        Returns:
            The assistant's response text or a safe fallback string.
        """
        text = self._text(self._create(messages, **kwargs))
        if text is None:
            return "[LLM ERROR] Unable to generate response."
        return text

    # ---------- JSON Chat Helper ----------

    def json_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Chat completion that returns parsed JSON.

        When a JSON schema is provided, uses Claude structured outputs
        (output_config.format) so the response is guaranteed to match.

        Returns:
            Parsed JSON dict ({} on failure).
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": schema}
            }
        else:
            messages[0]["content"] += (
                "\nYou MUST return ONLY valid JSON with no additional text or markdown."
            )

        text = self._text(self._create(messages, **kwargs))
        if text is None:
            return {}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: strip markdown fences if the model wrapped the JSON.
            stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as e:
                print(f"[LLMClient] Failed to parse JSON response: {e}")
                print(f"[LLMClient] Raw response: {text[:2000]}")
                return {}

    # ---------- Specialized Helpers ----------

    def classify_segment_events(
        self, text_segment: str, segment_duration: float = 30.0
    ) -> Dict[str, Any]:
        """
        Classify semantic events in a text segment.

        Returns:
            {
              "prosocial_events": [...],
              "aggressive_events": [...],
              "fantasy_level": "none"/"low"/"medium"/"high",
              "sel_strategies": [...],
              "direct_address": bool,
              "fear_intense": bool,
              "impossible_events": [...]
            }
        """
        from .guardrails import guarded_json_call, validate_segment_events, is_too_sparse

        default_result: Dict[str, Any] = {
            "prosocial_events": [],
            "aggressive_events": [],
            "fantasy_level": "none",
            "sel_strategies": [],
            "direct_address": False,
            "fear_intense": False,
            "impossible_events": [],
            "uncertain": False,
        }

        if is_too_sparse(text_segment):
            from .guardrails import _trips
            _trips["abstention"] += 1
            logger.warning("[llm_client] classify_segment_events: transcript too sparse, abstaining")
            return {**default_result, "uncertain": True}

        system_prompt = """You are a child development expert analyzing children's media content.
Your task is to label content for developmental appropriateness and educational value.

Analyze the provided transcript segment and identify:
1. Prosocial events: sharing, helping, cooperating, empathy, kindness, apologizing, etc.
2. Aggressive events: hitting, yelling, meanness, conflicts, violence (even if cartoon/mild)
3. Fantasy level: How fantastical/imaginative is the content?
4. SEL strategies: Explicit social-emotional learning like "take deep breaths", "use your words", emotion labeling
5. Direct address: Does a character speak directly to the viewer (e.g., "Can you help me?", "Let's count together!")
6. Fear/intensity: Is this segment scary, intense, or overwhelming for young children?
7. Impossible events: Things that violate reality/physics in confusing ways for young kids

Be thorough but concise in your descriptions."""

        user_prompt = f"""Analyze this transcript segment from children's media:

TRANSCRIPT:
{text_segment}

Only include events that actually occur in the transcript. Use empty lists if none found."""

        call_kwargs = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": SEGMENT_EVENTS_SCHEMA,
        }

        result = guarded_json_call(
            self, call_kwargs, validate_segment_events, default_result,
            label="classify_segment_events",
        )

        merged = {**default_result, **result}
        merged["uncertain"] = False
        return merged

    def rate_narrative_coherence(self, segment_summaries: List[str]) -> Dict[str, float]:
        """
        Rate narrative coherence across segments using LLM.

        Returns:
            {
              "adjacent_similarity_mean": float,
              "topic_jumps": float
            }
        """
        from .guardrails import guarded_json_call, validate_coherence

        if not segment_summaries or len(segment_summaries) < 2:
            return {"adjacent_similarity_mean": 1.0, "topic_jumps": 0.0}

        default_result = {"adjacent_similarity_mean": 0.5, "topic_jumps": 0.3}

        system_prompt = """You are analyzing narrative coherence in children's media.
Given a sequence of segment summaries, evaluate how well the story flows."""

        summaries_text = "\n".join(
            [f"{i+1}. {s}" for i, s in enumerate(segment_summaries)]
        )

        user_prompt = f"""Analyze the narrative coherence of these consecutive segments from a children's show:

SEGMENTS:
{summaries_text}

Evaluate (both values between 0.0 and 1.0):
1. adjacent_similarity_mean: Average coherence/connection between consecutive segments (0.0 = completely unrelated, 1.0 = perfectly connected)
2. topic_jumps: Fraction of transitions that are abrupt/jarring topic changes with no logical connection"""

        result = guarded_json_call(
            self,
            {"system_prompt": system_prompt, "user_prompt": user_prompt, "schema": COHERENCE_SCHEMA},
            validate_coherence,
            default_result,
            label="rate_narrative_coherence",
        )

        return {
            "adjacent_similarity_mean": float(result.get("adjacent_similarity_mean", 0.5)),
            "topic_jumps": float(result.get("topic_jumps", 0.3)),
        }

    def generate_segment_summary(self, text_segment: str) -> str:
        """
        Generate a short, one-sentence summary of a text segment.
        """
        system_prompt = (
            "You are summarizing children's media content. Create brief, one-sentence summaries."
        )

        user_prompt = f"""Summarize this segment in ONE simple sentence (suitable for a children's show):

{text_segment}

Summary:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return self.chat(messages, max_tokens=256).strip()

    def estimate_language_metrics_llm(self, transcript: str) -> Dict[str, float]:
        """
        Use LLM to estimate language complexity metrics.

        Returns something like:
            {
              "vocabulary_richness": float,
              "sentence_complexity": float,
              "advanced_vocabulary_fraction": float,
              "question_frequency": float
            }
        """
        from .guardrails import guarded_json_call, validate_language_metrics

        default_result = {
            "vocabulary_richness": 0.5,
            "sentence_complexity": 0.5,
            "advanced_vocabulary_fraction": 0.3,
            "question_frequency": 0.3,
        }

        system_prompt = """You are analyzing language complexity in children's media.
Evaluate the transcript and return language metrics."""

        truncated = transcript[:2000]

        user_prompt = f"""Analyze this transcript for language complexity.
All metrics are between 0.0 and 1.0:
- vocabulary_richness: variety of unique words
- sentence_complexity: average sentence length/complexity
- advanced_vocabulary_fraction: fraction of words above basic tier
- question_frequency: relative frequency of questions

TRANSCRIPT:
{truncated}"""

        result = guarded_json_call(
            self,
            {"system_prompt": system_prompt, "user_prompt": user_prompt, "schema": LANGUAGE_METRICS_SCHEMA},
            validate_language_metrics,
            default_result,
            label="estimate_language_metrics_llm",
        )

        return {
            "vocabulary_richness": float(result.get("vocabulary_richness", 0.5)),
            "sentence_complexity": float(result.get("sentence_complexity", 0.5)),
            "advanced_vocabulary_fraction": float(result.get("advanced_vocabulary_fraction", 0.3)),
            "question_frequency": float(result.get("question_frequency", 0.3)),
        }

    def generate_parent_summary(self, scores: Dict[str, Any], age: int) -> str:
        """
        Generate a short, plain-English explanation for parents of why a video
        received its scores for a child of the given age.
        """
        system_prompt = (
            "You are a child development expert helping parents understand a video "
            "evaluation. Write 2-4 plain-English sentences a busy parent can read at "
            "a glance: what the video does well or poorly for this age, and one "
            "practical takeaway. No jargon, no markdown, no preamble."
        )

        user_prompt = (
            f"Child age: {age}\n\nEvaluation scores and findings (JSON):\n"
            f"{json.dumps(scores, indent=2, default=str)[:4000]}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return self.chat(messages, max_tokens=512).strip()


if __name__ == "__main__":
    """
    Tiny smoke test you can run with:
        python llm_client.py
    Make sure your ANTHROPIC_API_KEY is set first.
    """
    try:
        client = LLMClient()
        msg = [{"role": "user", "content": "Say hi in one short friendly sentence."}]
        print("Chat test:", client.chat(msg))
    except Exception as e:
        print("Error running LLMClient smoke test:", e)
