"""
bay_allocation_resolver.py

Part of the VehicleServiceRulesEngine library.

Service centers commonly overbook bay slots slightly, betting that some
customers will cancel or no-show, since an idle bay/technician is lost
revenue. This module decides, when a bay slot is oversold for a given
day, which existing appointments should be offered a reschedule, and in
what priority order.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class CustomerTier(Enum):
    STANDARD = 0
    SILVER = 1
    GOLD = 2
    FLEET_ACCOUNT = 3   # commercial fleet customers - highest priority


@dataclass
class AppointmentRecord:
    appointment_id: str
    customer_tier: CustomerTier
    appointment_date: str
    booked_at: str          # ISO timestamp - used as a tiebreaker
    service_type: str


@dataclass
class ResolutionPlan:
    """Result of resolving an overbooking situation for one day/service type."""
    protected_appointments: List[AppointmentRecord] = field(default_factory=list)
    reschedule_candidates: List[AppointmentRecord] = field(default_factory=list)


class BayAllocationResolver:
    """
    Given a list of appointments competing for the same service
    type/day, and the number of bays actually available, determines
    which appointments keep their slot and which should be offered a
    reschedule.

    Priority order (highest protection first):
      1. Higher customer tier (fleet accounts protected first)
      2. Earlier booking time (first-come, first-served within a tier)
    """

    def resolve(self, appointments: List[AppointmentRecord],
                bays_available: int) -> ResolutionPlan:
        if bays_available < 0:
            raise ValueError("bays_available cannot be negative")

        ordered = sorted(
            appointments,
            key=lambda a: (-a.customer_tier.value, a.booked_at),
        )

        protected = ordered[:bays_available]
        candidates = ordered[bays_available:]

        return ResolutionPlan(
            protected_appointments=protected,
            reschedule_candidates=candidates,
        )

    def suggest_compensation(self, candidate: AppointmentRecord) -> str:
        """
        Simple compensation policy based on customer tier - used to
        populate the message sent to affected customers via the
        notification pipeline.
        """
        if candidate.customer_tier in (CustomerTier.GOLD, CustomerTier.FLEET_ACCOUNT):
            return "priority reschedule + free courtesy vehicle"
        if candidate.customer_tier == CustomerTier.SILVER:
            return "priority reschedule"
        return "next available slot + 15% discount on labor"
