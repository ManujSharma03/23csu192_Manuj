"""
intent.py
----------
Intent detection for customer messages.

Design note (see README / assignment brief, section 9 & 25):
The LLM is used ONLY for natural-language understanding -- extracting
what the customer is asking for and how they feel. It NEVER decides
policy or eligibility. A deterministic, keyword-based detector always
runs first and is what the app relies on for correctness; an optional
LLM pass (when an API key is configured) can add extra recognised
intents on top, but can never remove or override the rule-based ones.
"""

from typing import List, Dict, Any
from utils.helpers import detect_sentiment, extract_pnr, extract_money_amount

INTENT_CATEGORIES = [
    "FLIGHT_STATUS",
    "CANCELLATION",
    "REFUND",
    "REBOOKING",
    "MEAL_VOUCHER",
    "LOUNGE_ACCESS",
    "HOTEL",
    "COMPENSATION",
    "UPGRADE",
    "FARE_DIFFERENCE",
    "LEGAL_THREAT",
    "FORMAL_COMPLAINT",
    "OTHER",
]

_KEYWORDS = {
    "LEGAL_THREAT": ["legal action", "sue ", "sue us", "lawyer", "court", "take you to court"],
    "FORMAL_COMPLAINT": ["formal complaint", "file a complaint", "filing a complaint", "escalate this in writing"],
    "CANCELLATION": ["cancelled", "cancel ", "got cancelled", "was cancelled"],
    "FARE_DIFFERENCE": ["fare difference", "waive the difference", "waive ₹", "more expensive", "higher fare", "pay the difference"],
    "UPGRADE": ["upgrade", "business class", "business-class", "first class"],
    "HOTEL": ["hotel", "accommodation", "full night", "full-night", "room for the night", "place to stay"],
    "LOUNGE_ACCESS": ["lounge"],
    "MEAL_VOUCHER": ["meal voucher", "meal", "food voucher"],
    "REFUND": ["refund", "cash refund", "money back", "reimburse"],
    "REBOOKING": ["rebook", "another flight", "different flight", "put me on", "next available flight", "alternate flight"],
    "COMPENSATION": ["compensation", "compensate", "for the trouble", "make it up to me"],
    "FLIGHT_STATUS": ["status", "what time", "is my flight", "flight update", "on time", "delayed"],
}

# Order matters: more specific / higher-priority intents are checked first
_PRIORITY_ORDER = [
    "LEGAL_THREAT",
    "FORMAL_COMPLAINT",
    "FARE_DIFFERENCE",
    "UPGRADE",
    "HOTEL",
    "LOUNGE_ACCESS",
    "MEAL_VOUCHER",
    "CANCELLATION",
    "REFUND",
    "REBOOKING",
    "COMPENSATION",
    "FLIGHT_STATUS",
]


def detect_intents_rule_based(text: str) -> List[str]:
    """Return every matching intent category found in the message (can be multiple)."""
    if not text:
        return ["OTHER"]
    lower = f" {text.lower()} "
    found = []
    for intent in _PRIORITY_ORDER:
        for kw in _KEYWORDS[intent]:
            if kw in lower:
                found.append(intent)
                break
    if not found:
        found.append("OTHER")
    # de-duplicate, preserve order
    seen = set()
    ordered = []
    for i in found:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered


def extract_entities(text: str) -> Dict[str, Any]:
    return {
        "pnr": extract_pnr(text),
        "money_amount_inr": extract_money_amount(text),
    }


def analyze_message(text: str, llm_client=None) -> Dict[str, Any]:
    """
    Full NLU pass over a single customer message.

    Returns a dict:
        {
          "intents": [...],          # always populated by rule-based detection
          "sentiment": "...",        # calm | confused | frustrated | angry
          "entities": {...},         # pnr, money_amount_inr
          "source": "rule_based" | "llm_assisted"
        }
    """
    result = {
        "intents": detect_intents_rule_based(text),
        "sentiment": detect_sentiment(text),
        "entities": extract_entities(text),
        "source": "rule_based",
    }

    if llm_client is not None:
        try:
            llm_result = llm_client.extract_intent(text)
            if llm_result:
                # Merge: union of intents, but rule-based intents always kept.
                # The LLM can only ADD recognised categories, never remove/override.
                extra_intents = [
                    i for i in llm_result.get("intents", [])
                    if i in INTENT_CATEGORIES and i not in result["intents"]
                ]
                result["intents"].extend(extra_intents)
                if llm_result.get("sentiment") in ("calm", "confused", "frustrated", "angry"):
                    # LLM sentiment can refine tone, rule-based stays as a floor
                    # (e.g. if rule-based already says "angry", keep angry)
                    if result["sentiment"] == "calm":
                        result["sentiment"] = llm_result["sentiment"]
                result["source"] = "llm_assisted"
        except Exception:
            # Any LLM failure silently falls back to rule-based only
            pass

    return result
