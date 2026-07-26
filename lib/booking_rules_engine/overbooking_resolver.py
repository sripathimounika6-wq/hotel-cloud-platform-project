"""
overbooking_resolver.py

Part of the BookingRulesEngine library.

Hotels commonly oversell rooms slightly, betting that some guests won't
show or will cancel. This module decides, when a room type is oversold
for a given night, which existing bookings should be offered a room
upgrade/relocation, and in what priority order.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class GuestTier(Enum):
    STANDARD = 0
    SILVER = 1
    GOLD = 2
    PLATINUM = 3


@dataclass
class BookingRecord:
    booking_id: str
    guest_tier: GuestTier
    checkin_date: str
    booked_at: str          # ISO timestamp - used as a tiebreaker
    room_type: str


@dataclass
class ResolutionPlan:
    """Result of resolving an overbooking situation for one night/room type."""
    protected_bookings: List[BookingRecord] = field(default_factory=list)
    relocation_candidates: List[BookingRecord] = field(default_factory=list)


class OverbookingResolver:
    """
    Given a list of bookings competing for the same room type/night, and
    the number of rooms actually available, determines which bookings
    keep their room and which should be offered a relocation/upgrade.

    Priority order (highest protection first):
      1. Higher guest loyalty tier
      2. Earlier booking time (first-come, first-served within a tier)
    """

    def resolve(self, bookings: List[BookingRecord],
                rooms_available: int) -> ResolutionPlan:
        if rooms_available < 0:
            raise ValueError("rooms_available cannot be negative")

        ordered = sorted(
            bookings,
            key=lambda b: (-b.guest_tier.value, b.booked_at),
        )

        protected = ordered[:rooms_available]
        candidates = ordered[rooms_available:]

        return ResolutionPlan(
            protected_bookings=protected,
            relocation_candidates=candidates,
        )

    def suggest_compensation(self, candidate: BookingRecord) -> str:
        """
        Simple compensation policy based on guest tier - used to populate
        the message sent to affected guests via the notification pipeline.
        """
        if candidate.guest_tier in (GuestTier.GOLD, GuestTier.PLATINUM):
            return "complimentary upgrade + one night refund"
        if candidate.guest_tier == GuestTier.SILVER:
            return "complimentary upgrade"
        return "alternative room + 20% discount on stay"
