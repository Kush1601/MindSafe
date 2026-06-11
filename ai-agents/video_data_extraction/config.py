"""
Configuration module for video data extraction.
Handles environment variables and processing defaults.

Note: All language modeling is done via the Claude (Anthropic API) client
in `evaluation.llm_client`. This module no longer initializes any
provider-specific clients.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Anthropic configuration (used indirectly by evaluation.llm_client)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")


# Processing Configuration
DEFAULT_SEGMENT_DURATION = 30.0  # seconds
DEFAULT_FRAMES_PER_SEGMENT = 20
DEFAULT_AUDIO_CHUNK_DURATION = 60.0  # seconds

