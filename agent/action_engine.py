"""
action_engine.py
------------------
Simulated execution of allowed actions. This is a PROTOTYPE: nothing
here connects to a real airline backend, payment system, or hotel
booking system. Every function returns a structured record describing
what "would" happen, for demo purposes only.
"""

from typing import Dict, Any
from utils.helpers import generate_reference


def process_refund(customer: Dict[str, Any]) -> Dict[str, Any]:
    ref = generate_reference("REF", customer["booking_reference"])
    return {
        "action": "process_refund",
        "label": "Refund request initiated (simulated)",
        "reference": ref,
        "details": {
            "processing_time": "Within 7 business days",
            "method": "Original payment method",
        },
        "display": (
            f"\u2713 Refund request initiated\n"
            f"Reference: {ref}\n"
            f"Processing: Within 7 business days\n"
            f"Method: Original payment method"
        ),
    }


def offer_rebooking(customer: Dict[str, Any], flight: Dict[str, Any]) -> Dict[str, Any]:
    ref = generate_reference("RBK", customer["booking_reference"])
    return {
        "action": "offer_rebooking",
        "label": "Free rebooking offered (simulated)",
        "reference": ref,
        "details": {
            "window": "Next available flight within 24 hours",
            "charge": "No charge",
        },
        "display": (
            f"\u2713 Rebooking offer generated\n"
            f"Reference: {ref}\n"
            f"Window: Next available flight within 24 hours\n"
            f"Charge: None"
        ),
    }


def issue_meal_voucher(customer: Dict[str, Any], amount_inr: int = 500) -> Dict[str, Any]:
    ref = generate_reference("MV", customer["booking_reference"])
    return {
        "action": "issue_meal_voucher",
        "label": "Meal voucher issued (simulated)",
        "reference": ref,
        "details": {"amount_inr": amount_inr},
        "display": f"\u2713 Meal voucher issued\nReference: {ref}\nAmount: \u20b9{amount_inr}",
    }


def provide_lounge_access(customer: Dict[str, Any]) -> Dict[str, Any]:
    ref = generate_reference("LNG", customer["booking_reference"])
    return {
        "action": "provide_lounge_access",
        "label": "Lounge access granted (simulated)",
        "reference": ref,
        "details": {},
        "display": f"\u2713 Lounge access granted\nReference: {ref}",
    }


def arrange_hotel(customer: Dict[str, Any], delay_hours: int) -> Dict[str, Any]:
    ref = generate_reference("HTL", customer["booking_reference"])
    return {
        "action": "arrange_hotel",
        "label": "Hotel accommodation arranged (simulated)",
        "reference": ref,
        "details": {
            "coverage": f"Delayed-hours portion only (~{delay_hours}h), not a full night's stay",
        },
        "display": (
            f"\u2713 Hotel accommodation arranged\n"
            f"Reference: {ref}\n"
            f"Coverage: Delayed-hours portion only (~{delay_hours}h) -- not a full night's stay"
        ),
    }


def apply_fare_difference(customer: Dict[str, Any], amount_inr: int) -> Dict[str, Any]:
    ref = generate_reference("FD", customer["booking_reference"])
    return {
        "action": "apply_fare_difference",
        "label": "Fare difference charged (simulated)",
        "reference": ref,
        "details": {"amount_inr": amount_inr},
        "display": f"\u2713 Fare difference of \u20b9{amount_inr} applied within agent authority\nReference: {ref}",
    }


def provide_booking_info(customer: Dict[str, Any], flight: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "action": "provide_booking_info",
        "label": "Booking information provided",
        "reference": customer["booking_reference"],
        "details": {
            "flight": flight.get("flight_number") if flight else None,
            "status": flight.get("status") if flight else None,
        },
        "display": "\u2713 Booking and flight status information provided",
    }
