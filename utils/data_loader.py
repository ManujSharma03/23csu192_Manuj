"""
data_loader.py
----------------
Loads the grounded source-of-truth data (customers, bookings, policies)
from the /data JSON files. This is the ONLY place the application reads
customer/flight/policy facts from. Nothing here is invented at runtime.
"""

import json
import os
from typing import Optional, Dict, Any, List

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load_json(filename: str) -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class DataStore:
    """In-memory, read-only view over the grounded data files."""

    def __init__(self):
        self.customers = _load_json("customers.json")["customers"]
        self.bookings = _load_json("bookings.json")["bookings"]
        self.policies = _load_json("policies.json")

    # ---------- Customer lookups ----------

    def all_customers(self) -> List[Dict[str, Any]]:
        return self.customers

    def get_customer_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        name_norm = name.strip().lower()
        for c in self.customers:
            if c["name"].lower() == name_norm:
                return c
            # allow first-name-only matches (e.g. "Priya")
            first = c["name"].split()[0].lower()
            if name_norm == first:
                return c
        return None

    def get_customer_by_id(self, customer_id: str) -> Optional[Dict[str, Any]]:
        for c in self.customers:
            if c["id"] == customer_id:
                return c
        return None

    def get_customer_by_pnr(self, pnr: str) -> Optional[Dict[str, Any]]:
        if not pnr:
            return None
        pnr_norm = pnr.strip().upper()
        for c in self.customers:
            if c["booking_reference"].upper() == pnr_norm:
                return c
        return None

    def find_customer(self, text: str) -> Optional[Dict[str, Any]]:
        """Try to identify a customer from free text: PNR first, then name."""
        if not text:
            return None
        # Try each known PNR / booking ref as a substring match (case-insensitive)
        upper_text = text.upper()
        for c in self.customers:
            if c["booking_reference"].upper() in upper_text:
                return c
        # Try full name / first name substring match
        lower_text = text.lower()
        for c in self.customers:
            if c["name"].lower() in lower_text:
                return c
            first = c["name"].split()[0].lower()
            if first in lower_text.split():
                return c
        return None

    # ---------- Booking / flight lookups ----------

    def get_booking(self, booking_reference: str) -> Optional[Dict[str, Any]]:
        if not booking_reference:
            return None
        ref_norm = booking_reference.strip().upper()
        for b in self.bookings:
            if b["booking_reference"].upper() == ref_norm:
                return b
        return None

    def get_booking_for_customer(self, customer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not customer:
            return None
        return self.get_booking(customer["booking_reference"])

    def get_flight(self, booking_reference: str, leg: str = "outbound") -> Optional[Dict[str, Any]]:
        booking = self.get_booking(booking_reference)
        if not booking:
            return None
        for flight in booking["flights"]:
            if flight["leg"] == leg:
                return flight
        # fall back to first flight
        return booking["flights"][0] if booking["flights"] else None

    # ---------- Policy lookups ----------

    def get_policy(self, key: str) -> Optional[Dict[str, Any]]:
        return self.policies.get(key)


_store: Optional[DataStore] = None


def get_data_store() -> DataStore:
    """Singleton accessor so data is only parsed from disk once per process."""
    global _store
    if _store is None:
        _store = DataStore()
    return _store
