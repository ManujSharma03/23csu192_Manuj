"""
audit_logger.py
-----------------
Structured audit trail. Every meaningful event in the conversation
(identification, retrieval, policy match, action, escalation) is
appended here so the evaluator can inspect exactly why the agent
did what it did.
"""

from datetime import datetime
from typing import Dict, Any, List

EVENT_ICONS = {
    "identify": "\U0001F464",      # bust in silhouette
    "retrieve": "\U0001F4C2",      # open file folder
    "policy": "\U0001F4D8",        # blue book
    "action": "\u2705",            # check mark
    "escalation": "\u26A0\uFE0F",  # warning
    "info": "\u2139\uFE0F",        # info
    "error": "\u274C",             # cross mark
}


def new_log() -> List[Dict[str, Any]]:
    return []


def log_event(log: List[Dict[str, Any]], category: str, message: str, detail: Dict[str, Any] = None) -> Dict[str, Any]:
    """Append a structured event to the given log list (mutates + returns entry)."""
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "category": category,
        "icon": EVENT_ICONS.get(category, "\u2022"),
        "message": message,
        "detail": detail or {},
    }
    log.append(entry)
    return entry


def format_log_line(entry: Dict[str, Any]) -> str:
    return f"{entry['timestamp']}  {entry['icon']}  {entry['message']}"
