"""
escalation.py
---------------
Creates structured escalation records when the policy engine determines
a request is outside the agent's authority. These are simulated hand-offs
to a human agent -- no real ticketing system is connected.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from utils.helpers import generate_escalation_id


def escalate_to_human(
    escalation_counter: int,
    customer: Optional[Dict[str, Any]],
    requested_action: str,
    policy_constraint: str,
    reason: str,
) -> Dict[str, Any]:
    escalation_id = generate_escalation_id(escalation_counter)
    return {
        "escalation_id": escalation_id,
        "customer": customer["name"] if customer else "Unknown",
        "pnr": customer["booking_reference"] if customer else None,
        "requested_action": requested_action,
        "policy_constraint": policy_constraint,
        "reason": reason,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "status": "Escalated",
    }


def format_escalation(escalation: Dict[str, Any]) -> str:
    return (
        f"{escalation['escalation_id']}\n\n"
        f"Customer: {escalation['customer']}\n"
        f"PNR: {escalation['pnr']}\n"
        f"Request: {escalation['requested_action']}\n"
        f"Policy Constraint: {escalation['policy_constraint']}\n"
        f"Reason: {escalation['reason']}\n"
        f"Status: {escalation['status']}"
    )
