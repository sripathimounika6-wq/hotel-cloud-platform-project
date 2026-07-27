"""
cancellation_policy.py

Part of the VehicleServiceRulesEngine library.

Implements a family of cancellation policies for vehicle service
appointments using the Strategy pattern. Each policy encapsulates a
different business rule for how much of a customer's deposit is
refundable, based on how far in advance they cancel a booked service
bay slot.

Service centers hold deposits on appointments (especially for longer
jobs like full services or diagnostics) because a cancelled slot with
no notice means a technician and bay sit idle. This module is used by
the appointment booking Lambda to compute refund amounts.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class CancellationPolicy(ABC):
    """
    Abstract base class for all service-appointment cancellation policies.

    Subclasses must implement `refund_percentage`, which returns a value
    between 0.0 (no refund) and 1.0 (full refund) based on how many hours
    remain before the scheduled appointment at the time of cancellation.
    """

    @abstractmethod
    def refund_percentage(self, hours_before_appointment: float) -> float:
        """Return the fraction of the deposit that is refundable."""
        raise NotImplementedError

    def compute_refund(self, deposit_amount: float, appointment_time: datetime,
                        cancellation_time: Optional[datetime] = None) -> float:
        """
        Compute the actual refund amount in currency units.

        :param deposit_amount: deposit paid to hold the service bay slot
        :param appointment_time: the scheduled appointment datetime
        :param cancellation_time: when the cancellation is requested
                                   (defaults to now if not provided)
        """
        if cancellation_time is None:
            cancellation_time = datetime.utcnow()

        delta = appointment_time - cancellation_time
        hours_before = max(delta.total_seconds() / 3600.0, 0.0)

        pct = self.refund_percentage(hours_before)
        # Defensive clamp - a policy should never return outside [0, 1],
        # but we guard against implementation bugs here.
        pct = min(max(pct, 0.0), 1.0)

        return round(deposit_amount * pct, 2)


class FlexiblePolicy(CancellationPolicy):
    """Full refund if cancelled at least 24 hours before the appointment."""

    def refund_percentage(self, hours_before_appointment: float) -> float:
        if hours_before_appointment >= 24:
            return 1.0
        if hours_before_appointment >= 6:
            return 0.5
        return 0.0


class StandardPolicy(CancellationPolicy):
    """Full refund at 2+ days out, 50% at 1-2 days, none inside 24 hours."""

    def refund_percentage(self, hours_before_appointment: float) -> float:
        days_before = hours_before_appointment / 24.0
        if days_before >= 2:
            return 1.0
        if days_before >= 1:
            return 0.5
        return 0.0


class NoShowStrictPolicy(CancellationPolicy):
    """
    Used for major jobs (engine work, bodywork) where a bay is blocked
    out for a full day or more - only a partial refund, and only well
    in advance of the appointment.
    """

    def refund_percentage(self, hours_before_appointment: float) -> float:
        days_before = hours_before_appointment / 24.0
        if days_before >= 5:
            return 0.5
        return 0.0


def get_policy(policy_name: str) -> CancellationPolicy:
    """
    Factory function that maps a policy name (as stored against a
    service type in DynamoDB) to a CancellationPolicy instance.
    """
    policies = {
        "FLEXIBLE": FlexiblePolicy,
        "STANDARD": StandardPolicy,
        "NO_SHOW_STRICT": NoShowStrictPolicy,
    }
    try:
        return policies[policy_name.upper()]()
    except KeyError:
        raise ValueError(f"Unknown cancellation policy: {policy_name}")
