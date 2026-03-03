"""
agents/key_manager.py

Round-robin Groq API key rotation across 3 keys.
Each call to next_key() returns the next key in sequence.
"""

import os
import itertools
import logging

logger = logging.getLogger(__name__)

# Load all 3 keys from environment
_KEYS = [
    k for k in [
        os.environ.get("GROQ_API_KEY_1"),
        os.environ.get("GROQ_API_KEY_2"),
        os.environ.get("GROQ_API_KEY_3"),
    ]
    if k  # skip missing/empty
]

# Fallback: also accept legacy single key
if not _KEYS:
    single = os.environ.get("GROQ_API_KEY")
    if single:
        _KEYS = [single]

if not _KEYS:
    logger.warning("No GROQ_API_KEY found in environment. AI agents will use fallback defaults.")

_cycle = itertools.cycle(_KEYS) if _KEYS else itertools.cycle([""])


def next_key() -> str:
    """Return next Groq API key in round-robin rotation."""
    key = next(_cycle)
    if key:
        logger.debug(f"Using Groq key: ...{key[-6:]}")
    return key


def has_keys() -> bool:
    return bool(_KEYS)


def key_count() -> int:
    return len(_KEYS)
