"""
agent.py
---------
The orchestrator. Implements the flow described in the assignment brief:

    Customer -> Chat -> Intent Detection -> Customer/Booking Identification
    -> Retrieve Data -> Policy Engine -> Decision -> Allowed Action | Escalation
    -> Response Generator -> Customer Response -> Audit Log

The LLM (via LLMClient) is used ONLY for:
  - assisting intent/sentiment extraction (intent.py already has a robust
    rule-based detector that always runs; the LLM can only add on top)
  - phrasing the final customer-facing response, strictly grounded in the
    decisions already produced by the deterministic policy engine

The LLM NEVER decides eligibility, compensation, or escalation.
"""

import os
import re
import json
from typing import Dict, Any, List, Optional

from utils.data_loader import get_data_store
from utils.audit_logger import log_event
from agent import intent as intent_module
from agent import policy_engine as pe
from agent import action_engine as ae
from agent import escalation as esc
from agent.prompts import (
    INTENT_EXTRACTION_SYSTEM_PROMPT,
    RESPONSE_SYSTEM_PROMPT,
    build_response_user_prompt,
)

FLIGHT_NUMBER_PATTERN = re.compile(r"\b([A-Z]{2})-?(\d{2,4})\b")


# ---------------------------------------------------------------------
# Optional LLM client (Anthropic API). The whole app must work without
# this -- if no API key or the anthropic package / network is
# unavailable, we silently fall back to deterministic templates.
# ---------------------------------------------------------------------

class LLMClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        self.available = False
        self._client = None
        if self.api_key:
            try:
                import anthropic  # imported lazily so app still runs without the package
                self._client = anthropic.Anthropic(api_key=self.api_key)
                self.available = True
            except Exception:
                self.available = False

    def extract_intent(self, text: str) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=200,
                system=INTENT_EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            raw = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
            raw = raw.strip().strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
            return json.loads(raw)
        except Exception:
            return None

    def generate_response(self, customer_message: str, sentiment: str, decisions: List[Dict[str, Any]],
                           actions: List[Dict[str, Any]], escalations: List[Dict[str, Any]]) -> Optional[str]:
        if not self.available:
            return None
        try:
            user_prompt = build_response_user_prompt(customer_message, sentiment, decisions, actions, escalations)
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=500,
                system=RESPONSE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
        except Exception:
            return None


# ---------------------------------------------------------------------
# Fallback (mock-mode) response generation -- deterministic templates
# ---------------------------------------------------------------------

_SENTIMENT_OPENERS = {
    "angry": "I understand how frustrating this is, and I want to sort it out for you right now.",
    "frustrated": "I understand this has been frustrating -- let's get it sorted.",
    "confused": "No problem, let me walk you through it clearly.",
    "calm": "Thanks for reaching out.",
}


def _flight_fact_line(flight: Optional[Dict[str, Any]]) -> str:
    if not flight:
        return ""
    if flight.get("status") == "Cancelled":
        return (f"I've confirmed that flight {flight['flight_number']} ({flight['route']}, "
                f"{flight['date']}) was cancelled due to {flight.get('cause', 'operational reasons').lower()}.")
    if flight.get("delay_hours"):
        return (f"I've confirmed that flight {flight['flight_number']} ({flight['route']}, "
                f"{flight['date']}) is delayed by {flight['delay_hours']} hours "
                f"(new departure {flight.get('new_departure', 'TBC')}).")
    return f"I've confirmed flight {flight['flight_number']} ({flight['route']}, {flight['date']}) -- status: {flight.get('status')}."


def _decision_paragraph(decision: Dict[str, Any]) -> str:
    intent_name = decision.get("intent", "")
    reason = decision.get("reason", "")
    lines = []

    if intent_name == "cancellation":
        if decision["eligible"]:
            lines.append(f"{reason} Under our cancellation policy you can either:")
            lines.append("\u2022 Rebook on the next available flight within 24 hours at no charge, OR")
            lines.append("\u2022 Request a full refund.")
            lines.append("Which would you prefer?")
        else:
            lines.append(reason)
    elif intent_name == "refund":
        lines.append(reason)
    elif intent_name == "delay_compensation":
        lines.append(reason)
    elif intent_name == "hotel_request":
        lines.append(reason)
    elif intent_name == "fare_difference_waiver":
        lines.append(reason)
    elif intent_name == "upgrade_request":
        lines.append(reason)
    elif intent_name == "compensation_request":
        lines.append(reason)
    elif intent_name == "legal_threat":
        lines.append("I hear you, and I'm sorry this has been such a frustrating experience.")
        lines.append(reason)
    elif intent_name == "formal_complaint":
        lines.append(reason)
    elif intent_name == "loyalty_status":
        lines.append(reason)
    elif intent_name == "status_check":
        lines.append(reason)
    elif intent_name == "ungrounded_request":
        lines.append(reason)
    else:
        lines.append(reason)

    if decision.get("requires_escalation"):
        esc_reason = decision.get("escalation_reason", "")
        lines.append(f"This part is outside my authority, so I'm escalating it to a specialist / supervisor team ({esc_reason}).")

    return " ".join(lines)


def build_fallback_response(customer_message: str, sentiment: str, decisions: List[Dict[str, Any]],
                             actions: List[Dict[str, Any]], flight: Optional[Dict[str, Any]],
                             identification_prompt: Optional[str] = None) -> str:
    if identification_prompt:
        return identification_prompt

    parts = [_SENTIMENT_OPENERS.get(sentiment, _SENTIMENT_OPENERS["calm"])]

    fact_line = _flight_fact_line(flight)
    if fact_line:
        parts.append(fact_line)

    if not decisions:
        parts.append("I couldn't find a specific policy or action that matches this request in the information available to me. "
                      "Could you tell me a bit more, or would you like me to check your booking/flight status instead?")
    else:
        for d in decisions:
            para = _decision_paragraph(d)
            if para:
                parts.append(para)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------
# Helpers for this module
# ---------------------------------------------------------------------

def _extract_flight_number(text: str) -> Optional[str]:
    if not text:
        return None
    match = FLIGHT_NUMBER_PATTERN.search(text.upper())
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def _wants_full_night(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"full[\s-]?night", lower)) or "entire night" in lower or "whole night" in lower


def _wants_different_payment_method(text: str) -> bool:
    lower = text.lower()
    return "different" in lower and any(k in lower for k in ["payment method", "account", "card", "bank"])


def _mentions_loyalty_tier(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in ["gold", "platinum", "silver", "tier", "loyalty"])


BASELINE_CANCEL_INTENTS = {"CANCELLATION", "REFUND", "REBOOKING", "FLIGHT_STATUS"}
BASELINE_DELAY_INTENTS = {"MEAL_VOUCHER", "LOUNGE_ACCESS", "HOTEL", "FLIGHT_STATUS"}

ACTION_DISPATCH = {
    "offer_rebooking": lambda customer, flight, amount: ae.offer_rebooking(customer, flight),
    "process_refund": lambda customer, flight, amount: ae.process_refund(customer),
    "meal_voucher": lambda customer, flight, amount: ae.issue_meal_voucher(customer),
    "lounge_access": lambda customer, flight, amount: ae.provide_lounge_access(customer),
    "hotel_accommodation": lambda customer, flight, amount: ae.arrange_hotel(customer, (flight or {}).get("delay_hours", 0)),
    "arrange_hotel": lambda customer, flight, amount: ae.arrange_hotel(customer, (flight or {}).get("delay_hours", 0)),
    "apply_fare_difference": lambda customer, flight, amount: ae.apply_fare_difference(customer, amount),
    "provide_booking_info": lambda customer, flight, amount: ae.provide_booking_info(customer, flight),
}


class Agent:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.store = get_data_store()
        self.llm_client = llm_client

    # ---------------- Identification ----------------

    def identify_customer(self, text: str):
        customer = self.store.find_customer(text)
        if customer:
            return customer
        flight_no = _extract_flight_number(text)
        if flight_no:
            flight_no_norm = flight_no.replace("-", "")
            for booking in self.store.bookings:
                for f in booking["flights"]:
                    if f["flight_number"].replace("-", "").startswith(flight_no_norm):
                        return self.store.get_customer_by_id(booking["customer_id"])
        return None

    # ---------------- Main entry point ----------------

    def handle_message(self, user_text: str, current_customer: Optional[Dict[str, Any]],
                        audit_log: List[Dict[str, Any]], escalation_counter: int,
                        granted_actions: set) -> Dict[str, Any]:
        """
        Returns a dict:
            {
              "response_text": str,
              "customer": dict or None,
              "decisions": [...],
              "actions": [...],
              "escalations": [...],
              "sentiment": str,
              "intents": [...],
              "escalation_counter": int (updated),
              "granted_actions": set (updated),
            }
        """
        decisions: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []
        escalations: List[Dict[str, Any]] = []
        identification_prompt = None

        # ---- Step 1: NLU (rule-based, optionally LLM-assisted) ----
        analysis = intent_module.analyze_message(user_text, llm_client=self.llm_client if (self.llm_client and self.llm_client.available) else None)
        intents = analysis["intents"]
        sentiment = analysis["sentiment"]
        entities = analysis["entities"]

        # ---- Step 2: Customer / booking identification ----
        customer = current_customer
        if customer is None:
            customer = self.identify_customer(user_text)
            if customer:
                log_event(audit_log, "identify", f"Customer identified: {customer['name']}")
                log_event(audit_log, "retrieve", f"Booking retrieved: {customer['booking_reference']}")
            else:
                log_event(audit_log, "info", "Customer not yet identified from message.")
                identification_prompt = (
                    "I can help with that. Could you please share your name or booking reference (PNR) "
                    "so I can pull up your booking?"
                )
                return {
                    "response_text": identification_prompt,
                    "customer": None,
                    "decisions": [],
                    "actions": [],
                    "escalations": [],
                    "sentiment": sentiment,
                    "intents": intents,
                    "escalation_counter": escalation_counter,
                    "granted_actions": granted_actions,
                }

        booking = self.store.get_booking_for_customer(customer)
        # `flight` is always the primary/disrupted (outbound) flight -- cancellation,
        # refund, delay and hotel policy decisions are always evaluated against it.
        flight = self.store.get_flight(customer["booking_reference"], leg="outbound")
        # `queried_flight` is what the customer is literally asking the status of
        # (e.g. "what about my return flight?") -- used only for status lookups.
        queried_flight = flight
        if "return" in user_text.lower():
            queried_flight = self.store.get_flight(customer["booking_reference"], leg="return") or flight
        if flight:
            log_event(audit_log, "retrieve", f"Flight status: {flight.get('status', 'UNKNOWN').upper()} ({flight['flight_number']})")

        # ---- Step 3: Policy engine dispatch ----
        booking_ref = customer["booking_reference"]

        # Cancellation / refund / rebooking baseline
        if flight and flight.get("status") == "Cancelled" and (set(intents) & BASELINE_CANCEL_INTENTS or intents == ["OTHER"]):
            d = pe.cancellation_decision(customer, flight)
            decisions.append(d)
            log_event(audit_log, "policy", "Cancellation policy matched", {"policy": d.get("policy_used")})

        if "REFUND" in intents:
            requested_method = "different" if _wants_different_payment_method(user_text) else None
            d = pe.refund_decision(customer, flight, requested_payment_method=requested_method)
            decisions.append(d)
            log_event(audit_log, "policy", "Refund policy checked", {"policy": d.get("policy_used")})
            if d["requires_escalation"]:
                escalation_counter += 1
                e = esc.escalate_to_human(
                    escalation_counter, customer,
                    requested_action="Refund to a different payment method",
                    policy_constraint="Refunds go to the original payment method only",
                    reason=d["escalation_reason"],
                )
                escalations.append(e)
                log_event(audit_log, "escalation", f"Escalation created: {e['escalation_id']}")

        if "REBOOKING" in intents and "FARE_DIFFERENCE" not in intents:
            d = pe.rebooking_decision(customer, flight)
            decisions.append(d)
            log_event(audit_log, "policy", "Rebooking policy checked", {"policy": d.get("policy_used")})

        # Delay compensation baseline (meal voucher / lounge / hotel)
        if flight and flight.get("delay_hours") and (set(intents) & BASELINE_DELAY_INTENTS or intents == ["OTHER"]):
            d = pe.delay_decision(customer, flight)
            decisions.append(d)
            log_event(audit_log, "policy", "Delay compensation policy matched", {"policy": d.get("policy_used")})

        # Explicit "full night" hotel request -> extra clarifying decision
        if "HOTEL" in intents and _wants_full_night(user_text) and flight:
            d = pe.hotel_request_decision(customer, flight, wants_full_night=True)
            decisions.append(d)
            log_event(audit_log, "policy", "Hotel coverage policy checked (full-night request)", {"policy": "Delay Compensation Rule"})

        # Fare difference waiver
        if "FARE_DIFFERENCE" in intents:
            amount = entities.get("money_amount_inr")
            d = pe.fare_difference_decision(customer, amount)
            decisions.append(d)
            log_event(audit_log, "policy", "Fare difference policy checked", {"policy": d.get("policy_used")})
            if d["requires_escalation"]:
                escalation_counter += 1
                e = esc.escalate_to_human(
                    escalation_counter, customer,
                    requested_action=f"Waive \u20b9{amount} fare difference" if amount else "Waive fare difference",
                    policy_constraint="Agent authority limited to \u20b91,500",
                    reason=d["escalation_reason"],
                )
                escalations.append(e)
                log_event(audit_log, "escalation", f"Escalation created: {e['escalation_id']}")

        # Upgrade request -> always escalate, no policy authority
        if "UPGRADE" in intents:
            d = pe.upgrade_decision(customer)
            decisions.append(d)
            log_event(audit_log, "policy", "Customer requested upgrade")
            log_event(audit_log, "policy", "No policy authority found for complimentary upgrade")
            escalation_counter += 1
            e = esc.escalate_to_human(
                escalation_counter, customer,
                requested_action="Complimentary class upgrade",
                policy_constraint="No policy provision for complimentary upgrades",
                reason=d["escalation_reason"],
            )
            escalations.append(e)
            log_event(audit_log, "escalation", f"Escalation created: {e['escalation_id']}")

            if _mentions_loyalty_tier(user_text):
                decisions.append(pe.loyalty_decision(customer))

        # Compensation beyond policy (only if not already covered by an upgrade ask)
        elif "COMPENSATION" in intents:
            d = pe.compensation_beyond_policy_decision(customer)
            decisions.append(d)
            escalation_counter += 1
            e = esc.escalate_to_human(
                escalation_counter, customer,
                requested_action="Compensation beyond stated policy",
                policy_constraint="No policy provision for additional compensation",
                reason=d["escalation_reason"],
            )
            escalations.append(e)
            log_event(audit_log, "escalation", f"Escalation created: {e['escalation_id']}")

        # Legal threat -> immediate escalation
        if "LEGAL_THREAT" in intents:
            d = pe.legal_threat_decision(customer)
            decisions.append(d)
            escalation_counter += 1
            e = esc.escalate_to_human(
                escalation_counter, customer,
                requested_action="Customer referenced legal action",
                policy_constraint="Mandatory immediate escalation",
                reason=d["escalation_reason"],
            )
            escalations.append(e)
            log_event(audit_log, "escalation", f"Escalation created (legal threat): {e['escalation_id']}")

        # Formal complaint -> immediate escalation
        if "FORMAL_COMPLAINT" in intents:
            d = pe.formal_complaint_decision(customer)
            decisions.append(d)
            escalation_counter += 1
            e = esc.escalate_to_human(
                escalation_counter, customer,
                requested_action="Customer intends to file a formal complaint",
                policy_constraint="Mandatory immediate escalation",
                reason=d["escalation_reason"],
            )
            escalations.append(e)
            log_event(audit_log, "escalation", f"Escalation created (formal complaint): {e['escalation_id']}")

        # Flight status / booking info (uses queried_flight, e.g. the return leg if asked about)
        if "FLIGHT_STATUS" in intents and queried_flight:
            info_action = ae.provide_booking_info(customer, queried_flight)
            actions.append(info_action)
            log_event(audit_log, "action", info_action["label"])
            decisions.append({
                "intent": "status_check",
                "customer": customer["name"],
                "booking_reference": booking_ref,
                "flight": queried_flight["flight_number"],
                "eligible": True,
                "allowed_action": "provide_booking_info",
                # left empty deliberately: the info action above is already executed
                # directly (using queried_flight), so Step 4 must not re-dispatch it.
                "allowed_actions": [],
                "reason": f"Current status for {queried_flight['flight_number']} ({queried_flight['route']}): {queried_flight.get('status')}.",
                "requires_escalation": False,
                "escalation_reason": None,
                "policy_used": None,
            })

        # ---- Step 4: Execute allowed actions from eligible decisions (deduped) ----
        for d in decisions:
            if not d.get("eligible") or d.get("requires_escalation"):
                continue
            allowed_actions = d.get("allowed_actions") or []
            for action_key in allowed_actions:
                dedup_key = (booking_ref, action_key)
                if dedup_key in granted_actions:
                    continue  # already granted earlier this session
                dispatcher = ACTION_DISPATCH.get(action_key)
                if not dispatcher:
                    continue
                amount = None
                if action_key == "apply_fare_difference":
                    amount = next((dd.get("fare_difference") for dd in decisions if dd.get("intent") == "fare_difference_waiver"), None)
                result = dispatcher(customer, flight, amount)
                actions.append(result)
                granted_actions.add(dedup_key)
                log_event(audit_log, "action", result["label"], {"reference": result.get("reference")})

        # ---- Step 5: Fallback "ungrounded" note if nothing matched ----
        if not decisions and not actions:
            d = {
                "intent": "ungrounded_request",
                "customer": customer["name"],
                "booking_reference": booking_ref,
                "flight": flight["flight_number"] if flight else None,
                "eligible": False,
                "allowed_action": None,
                "allowed_actions": [],
                "reason": "This specific request isn't covered by the customer, booking, or policy information available to me.",
                "requires_escalation": False,
                "escalation_reason": None,
                "policy_used": None,
            }
            decisions.append(d)
            log_event(audit_log, "info", "No matching policy found for this request")

        # ---- Step 6: Response generation ----
        llm_text = None
        if self.llm_client and self.llm_client.available:
            llm_text = self.llm_client.generate_response(user_text, sentiment, decisions, actions, escalations)

        response_text = llm_text or build_fallback_response(user_text, sentiment, decisions, actions, flight)

        return {
            "response_text": response_text,
            "customer": customer,
            "decisions": decisions,
            "actions": actions,
            "escalations": escalations,
            "sentiment": sentiment,
            "intents": intents,
            "escalation_counter": escalation_counter,
            "granted_actions": granted_actions,
        }
