"""
policy_engine.py
------------------
Deterministic, rule-based policy decisions. This module is the ONLY
place that decides eligibility, compensation, refunds, hotel coverage,
fare-difference thresholds, and escalation. The LLM is never allowed
to make or override these decisions (see assignment brief, section 25:
"Never allow the LLM to override the policy engine").

Every public function returns a "decision object" (plain dict) that is
used to both drive the UI (Policy Decision Card) and to feed the
action / escalation engines.
"""

from typing import Dict, Any, Optional
from utils.data_loader import get_data_store

FARE_WAIVER_THRESHOLD_INR = 1500


def _base_decision(intent: str, customer: Dict[str, Any], booking_reference: str, flight: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "intent": intent,
        "customer": customer["name"] if customer else None,
        "booking_reference": booking_reference,
        "flight": flight["flight_number"] if flight else None,
        "eligible": False,
        "allowed_action": None,
        "allowed_actions": [],
        "reason": "",
        "requires_escalation": False,
        "escalation_reason": None,
        "policy_used": None,
    }


# ---------------------------------------------------------------------
# Cancellation / rebooking / refund
# ---------------------------------------------------------------------

def cancellation_decision(customer: Dict[str, Any], flight: Dict[str, Any]) -> Dict[str, Any]:
    store = get_data_store()
    policy = store.get_policy("cancellation_rebooking_rule")
    decision = _base_decision("cancellation", customer, customer["booking_reference"], flight)
    decision["policy_used"] = policy["name"]

    if flight and flight.get("status") == "Cancelled":
        decision["eligible"] = True
        # NOTE: allowed_actions is intentionally left empty here -- this decision
        # presents a CHOICE to the customer (rebook OR refund). Nothing is
        # auto-executed until the customer states which option they want
        # (handled separately by rebooking_decision / refund_decision).
        decision["allowed_actions"] = []
        decision["allowed_action"] = "Customer's choice: free rebooking within 24 hours OR full refund"
        decision["reason"] = f"Flight {flight['flight_number']} was cancelled by the airline ({flight.get('cause', 'operational reasons')})."
    else:
        decision["eligible"] = False
        decision["reason"] = "No cancellation is recorded for this flight in the booking data."
    return decision


def rebooking_decision(customer: Dict[str, Any], flight: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates an explicit customer request to be rebooked (free, within 24h)
    following an airline-caused cancellation."""
    store = get_data_store()
    policy = store.get_policy("cancellation_rebooking_rule")
    decision = _base_decision("rebooking", customer, customer["booking_reference"], flight)
    decision["policy_used"] = policy["name"]

    if flight and flight.get("status") == "Cancelled":
        decision["eligible"] = True
        decision["allowed_action"] = "offer_rebooking"
        decision["allowed_actions"] = ["offer_rebooking"]
        decision["reason"] = (
            f"Flight {flight['flight_number']} was cancelled by the airline, so a free rebooking on the "
            f"next available flight within 24 hours applies."
        )
    else:
        decision["eligible"] = False
        decision["reason"] = (
            "Free rebooking under this policy applies only to airline-caused cancellations. "
            "A voluntary flight change is subject to the fare difference rule instead."
        )
    return decision


def refund_decision(customer: Dict[str, Any], flight: Dict[str, Any], requested_payment_method: Optional[str] = None) -> Dict[str, Any]:
    store = get_data_store()
    policy = store.get_policy("refund_rule")
    decision = _base_decision("refund", customer, customer["booking_reference"], flight)
    decision["policy_used"] = policy["name"]

    if requested_payment_method and requested_payment_method.lower() not in ("original", "same", "original_payment_method"):
        decision["eligible"] = False
        decision["requires_escalation"] = True
        decision["escalation_reason"] = "Refund requested to a different payment method than the original."
        decision["reason"] = "Refunds can only be processed to the original payment method without supervisor approval."
        return decision

    if flight and flight.get("status") == "Cancelled":
        decision["eligible"] = True
        decision["allowed_action"] = "process_refund"
        decision["allowed_actions"] = ["process_refund"]
        decision["reason"] = (
            f"Flight {flight['flight_number']} was cancelled by the airline, so a full refund is due "
            f"within {policy['processing_days']} business days to the original payment method."
        )
    else:
        decision["eligible"] = False
        decision["reason"] = "Refund policy applies only to airline-caused cancellations; no cancellation found."
    return decision


# ---------------------------------------------------------------------
# Delay compensation (meal voucher / lounge / hotel)
# ---------------------------------------------------------------------

def delay_decision(customer: Dict[str, Any], flight: Dict[str, Any]) -> Dict[str, Any]:
    store = get_data_store()
    policy = store.get_policy("delay_compensation_rule")
    decision = _base_decision("delay_compensation", customer, customer["booking_reference"], flight)
    decision["policy_used"] = policy["name"]

    delay_hours = (flight or {}).get("delay_hours")
    if delay_hours is None:
        decision["eligible"] = False
        decision["reason"] = "No recorded delay for this flight."
        return decision

    benefits = ["meal_voucher"]
    if delay_hours > 3:
        benefits.append("lounge_access")
    if delay_hours > 5:
        benefits.append("hotel_accommodation")

    decision["eligible"] = True
    decision["allowed_actions"] = benefits
    decision["allowed_action"] = " + ".join(b.replace("_", " ") for b in benefits)
    decision["delay_hours"] = delay_hours

    if delay_hours > 5:
        decision["reason"] = (
            f"Delay of {delay_hours} hours exceeds 5 hours: meal voucher, lounge access, and hotel "
            f"accommodation (covering only the {delay_hours} delayed hours, not a full night) apply."
        )
    elif delay_hours > 3:
        decision["reason"] = (
            f"Delay of {delay_hours} hours is more than 3 hours but not more than 5: meal voucher and "
            f"lounge access apply. Hotel accommodation applies only when delay is more than 5 hours."
        )
    else:
        decision["reason"] = f"Delay of {delay_hours} hours is under 3 hours: a meal voucher applies."
    return decision


def hotel_request_decision(customer: Dict[str, Any], flight: Dict[str, Any], wants_full_night: bool = False) -> Dict[str, Any]:
    """Specifically evaluates a customer's HOTEL request (used when the customer
    explicitly asks for a hotel / a full night's stay)."""
    decision = delay_decision(customer, flight)
    decision["intent"] = "hotel_request"
    delay_hours = decision.get("delay_hours")

    hotel_eligible = "hotel_accommodation" in decision.get("allowed_actions", [])
    decision["eligible"] = hotel_eligible
    decision["allowed_action"] = "hotel_accommodation" if hotel_eligible else None
    decision["allowed_actions"] = ["hotel_accommodation"] if hotel_eligible else []

    if not hotel_eligible:
        decision["reason"] = "Hotel accommodation applies only when delay is more than 5 hours."
        decision["requires_escalation"] = False
    else:
        if wants_full_night:
            decision["reason"] = (
                f"Delay of {delay_hours} hours qualifies for hotel accommodation, but coverage is limited "
                f"to the delayed hours only -- not a full night's stay."
            )
        else:
            decision["reason"] = f"Delay of {delay_hours} hours qualifies for hotel accommodation for the delayed hours."
    return decision


# ---------------------------------------------------------------------
# Fare difference waiver
# ---------------------------------------------------------------------

def fare_difference_decision(customer: Dict[str, Any], amount_inr: Optional[int]) -> Dict[str, Any]:
    store = get_data_store()
    policy = store.get_policy("fare_difference_rule")
    decision = _base_decision("fare_difference_waiver", customer, customer["booking_reference"] if customer else None)
    decision["policy_used"] = policy["name"]
    decision["fare_difference"] = amount_inr
    threshold = policy.get("agent_waiver_threshold_inr", FARE_WAIVER_THRESHOLD_INR)

    if amount_inr is None:
        decision["eligible"] = False
        decision["requires_escalation"] = True
        decision["escalation_reason"] = "Fare difference amount was not confirmed."
        decision["reason"] = "The fare difference amount is needed to apply this policy."
        return decision

    if amount_inr <= threshold:
        decision["eligible"] = True
        decision["allowed_action"] = "apply_fare_difference"
        decision["allowed_actions"] = ["apply_fare_difference"]
        decision["reason"] = f"Fare difference of \u20b9{amount_inr} is within the agent's \u20b9{threshold} authority."
    else:
        decision["eligible"] = False
        decision["requires_escalation"] = True
        decision["escalation_reason"] = "Supervisor approval required."
        decision["reason"] = f"Fare difference of \u20b9{amount_inr} exceeds the agent's \u20b9{threshold} authority."
    return decision


# ---------------------------------------------------------------------
# Loyalty tier (informational -- never grants extra compensation)
# ---------------------------------------------------------------------

def loyalty_decision(customer: Dict[str, Any]) -> Dict[str, Any]:
    store = get_data_store()
    policy = store.get_policy("loyalty_tier_rule")
    decision = _base_decision("loyalty_status", customer, customer["booking_reference"] if customer else None)
    decision["policy_used"] = policy["name"]
    tier = customer.get("loyalty_tier") if customer else None
    priority = tier in policy.get("priority_tiers", [])
    decision["eligible"] = priority
    decision["allowed_action"] = "priority_rebooking" if priority else None
    decision["allowed_actions"] = ["priority_rebooking"] if priority else []
    decision["reason"] = (
        f"{tier} tier receives priority rebooking, but no additional compensation beyond standard policy."
        if priority else f"{tier} tier has no special rebooking priority under current policy."
    )
    return decision


# ---------------------------------------------------------------------
# Requests with NO policy authority -> always escalate
# ---------------------------------------------------------------------

def upgrade_decision(customer: Dict[str, Any]) -> Dict[str, Any]:
    decision = _base_decision("upgrade_request", customer, customer["booking_reference"] if customer else None)
    decision["policy_used"] = None
    decision["eligible"] = False
    decision["requires_escalation"] = True
    decision["escalation_reason"] = "No policy authority for complimentary upgrades."
    decision["reason"] = (
        "There is no policy provision for a complimentary class upgrade, including for Gold/Platinum tiers. "
        "Loyalty tier provides priority rebooking only, not additional compensation."
    )
    return decision


def compensation_beyond_policy_decision(customer: Dict[str, Any], detail: str = "") -> Dict[str, Any]:
    decision = _base_decision("compensation_request", customer, customer["booking_reference"] if customer else None)
    decision["eligible"] = False
    decision["requires_escalation"] = True
    decision["escalation_reason"] = "Requested compensation is beyond stated policy amounts."
    decision["reason"] = "This request goes beyond the meal voucher / lounge / hotel / refund benefits defined in policy."
    return decision


def legal_threat_decision(customer: Dict[str, Any]) -> Dict[str, Any]:
    decision = _base_decision("legal_threat", customer, customer["booking_reference"] if customer else None)
    decision["eligible"] = False
    decision["requires_escalation"] = True
    decision["escalation_reason"] = "Customer indicated intent to pursue legal action -- must be escalated immediately."
    decision["reason"] = "Threats of legal action require immediate escalation to a human agent."
    return decision


def formal_complaint_decision(customer: Dict[str, Any]) -> Dict[str, Any]:
    decision = _base_decision("formal_complaint", customer, customer["booking_reference"] if customer else None)
    decision["eligible"] = False
    decision["requires_escalation"] = True
    decision["escalation_reason"] = "Customer indicated intent to file a formal complaint -- must be escalated immediately."
    decision["reason"] = "Formal complaint intent requires immediate escalation to a human agent."
    return decision


def non_airline_disruption_decision(customer: Dict[str, Any], detail: str = "") -> Dict[str, Any]:
    decision = _base_decision("non_airline_caused_exception", customer, customer["booking_reference"] if customer else None)
    decision["eligible"] = False
    decision["requires_escalation"] = True
    decision["escalation_reason"] = "Exception requested for a disruption not caused by the airline."
    decision["reason"] = "Policy benefits in this data pack apply to airline-caused disruptions only."
    return decision
