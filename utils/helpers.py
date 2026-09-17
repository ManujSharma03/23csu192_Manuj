"""
helpers.py
-----------
Small, dependency-free helper functions used across the agent:
rule-based sentiment detection, entity extraction (PNR / money amounts),
and simple ID generators for references/escalations.

These are deliberately deterministic (not LLM-based) so the app keeps
working even in mock mode with no API key.
"""

import re
import random
import string

# ---------------------------------------------------------------------
# Sentiment / emotion detection (communication-tone only, NOT diagnosis)
# ---------------------------------------------------------------------

_ANGRY_WORDS = [
    "furious", "outrageous", "unacceptable", "ridiculous", "disgusted",
    "angry", "livid", "fed up", "sue", "lawyer", "legal action",
    "worst", "horrible", "terrible service", "scam",
]
_FRUSTRATED_WORDS = [
    "frustrated", "frustrating", "annoyed", "upset", "not happy",
    "unhappy", "disappointed", "missed", "ruined", "fed up", "enough",
    "again", "still waiting",
]
_CONFUSED_WORDS = [
    "confused", "don't understand", "not sure", "what do you mean",
    "unclear", "how does", "what happens", "explain",
]


def detect_sentiment(text: str) -> str:
    """Very lightweight keyword-based tone detector.
    Returns one of: calm, confused, frustrated, angry.
    Used ONLY to adjust communication tone -- never to diagnose the customer.
    """
    if not text:
        return "calm"
    lower = text.lower()

    if any(w in lower for w in _ANGRY_WORDS) or text.count("!") >= 2:
        return "angry"
    if any(w in lower for w in _FRUSTRATED_WORDS):
        return "frustrated"
    if any(w in lower for w in _CONFUSED_WORDS) or "?" in lower and len(lower) < 40:
        return "confused"
    return "calm"


# ---------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------

_PNR_PATTERN = re.compile(r"\b[A-Z]{2}\d{3,5}[A-Z]?\b")
_MONEY_PATTERN = re.compile(r"(?:₹|rs\.?|inr)\s?([\d,]+)", re.IGNORECASE)


def extract_pnr(text: str):
    if not text:
        return None
    match = _PNR_PATTERN.search(text.upper())
    return match.group(0) if match else None


def extract_money_amount(text: str):
    """Extract an INR amount mentioned in free text, e.g. '₹2,000' or 'Rs 2000'."""
    if not text:
        return None
    match = _MONEY_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------
# ID generators (simulated references only -- prototype, not a real
# airline backend)
# ---------------------------------------------------------------------

def generate_reference(prefix: str, seed: str = "") -> str:
    suffix = seed.upper() if seed else "".join(random.choices(string.digits, k=4))
    return f"{prefix}-{suffix}"


def generate_escalation_id(counter: int) -> str:
    return f"ESC-{1000 + counter}"
