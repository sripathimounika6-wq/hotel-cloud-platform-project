"""
booking_rules_engine.py

A small, self-contained library that encapsulates the *business rules*
for the hotel platform, kept deliberately separate from any AWS SDK code.

Why this is a "library" and not just app code:
- It has no dependency on boto3, Lambda, or any AWS service.
- It can be unit-tested in isolation (see tests below).
- It is imported by multiple Lambda functions (create_booking, get_bookings)
  so the pricing/cancellation logic lives in exactly one place.

Design patterns used:
- Strategy pattern for pricing (PricingStrategy subclasses can be swapped
  at runtime without changing calling code).
- Simple state/rules objects for cancellation and overbooking, so new
  policies can be added by subclassing rather than editing existing logic
  (Open/Closed Principle).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

class PricingStrategy(ABC):
    """Base class for a pricing algorithm. Subclass this to add new
    pricing models (e.g. seasonal, loyalty-tier) without touching
    the booking Lambda."""

    @abstractmethod
    def calculate_price(self, base_rate: float, occupancy_ratio: float) -> float:
        ...


class OccupancyBasedPricing(PricingStrategy):
    """Simple demand-based dynamic pricing:
    - Below 50% occupancy: 10% discount
    - 50-80% occupancy: base rate
    - Above 80% occupancy: surge pricing, up to +40%
    """

    def calculate_price(self, base_rate: float, occupancy_ratio: float) -> float:
        if occupancy_ratio < 0.5:
            return round(base_rate * 0.9, 2)
        if occupancy_ratio <= 0.8:
            return round(base_rate, 2)
        # linear surge between 80% -> 100% occupancy, capped at +40%
        surge_fraction = min((occupancy_ratio - 0.8) / 0.2, 1.0)
        multiplier = 1.0 + (0.4 * surge_fraction)
        return round(base_rate * multiplier, 2)


class PricingEngine:
    """Wraps a PricingStrategy so calling code depends only on this class."""

    def __init__(self, strategy: PricingStrategy = None):
        self.strategy = strategy or OccupancyBasedPricing()

    def price_for_room(self, base_rate: float, rooms_total: int, rooms_booked: int) -> float:
        occupancy_ratio = rooms_booked / rooms_total if rooms_total else 0
        return self.strategy.calculate_price(base_rate, occupancy_ratio)


# ---------------------------------------------------------------------------
# Cancellation policy
# ---------------------------------------------------------------------------

@dataclass
class CancellationResult:
    allowed: bool
    refund_percentage: int
    reason: str


class CancellationPolicy:
    """Standard hotel cancellation tiers based on days-before-checkin."""

    # (days_before_checkin_threshold, refund_percentage)
    TIERS = [
        (7, 100),   # 7+ days out: full refund
        (3, 50),    # 3-6 days out: half refund
        (1, 20),    # 1-2 days out: small refund
    ]

    def evaluate(self, checkin_date: date, today: date) -> CancellationResult:
        days_before = (checkin_date - today).days

        if days_before < 0:
            return CancellationResult(False, 0, "Check-in date already passed.")

        for threshold, refund in self.TIERS:
            if days_before >= threshold:
                return CancellationResult(
                    True, refund,
                    f"{days_before} days before check-in: {refund}% refund."
                )

        return CancellationResult(
            True, 0,
            "Cancelling within 24 hours of check-in: no refund."
        )


# ---------------------------------------------------------------------------
# Overbooking resolution
# ---------------------------------------------------------------------------

class OverbookingResolver:
    """Resolves conflicts when more bookings exist for a room/date than
    physical inventory allows. Uses a simple, explainable strategy:
    walk the newest booking to the next available similar room type,
    or flag for manual staff review if none exists.
    """

    def __init__(self, available_rooms_by_type: dict[str, list[str]]):
        # e.g. {"double": ["101", "102"], "suite": ["201"]}
        self.available_rooms_by_type = available_rooms_by_type

    def resolve(self, room_type: str, conflicting_booking_ids: list[str]) -> dict:
        candidates = self.available_rooms_by_type.get(room_type, [])

        if len(candidates) >= len(conflicting_booking_ids):
            reassignment = {
                booking_id: candidates[i]
                for i, booking_id in enumerate(conflicting_booking_ids)
            }
            return {"status": "resolved", "reassignments": reassignment}

        return {
            "status": "manual_review_required",
            "reason": f"Not enough '{room_type}' rooms to reassign all conflicts.",
            "unresolved_count": len(conflicting_booking_ids) - len(candidates),
        }
