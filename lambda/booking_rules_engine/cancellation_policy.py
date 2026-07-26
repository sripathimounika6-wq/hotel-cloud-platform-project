"""
cancellation_policy.py

Part of the BookingRulesEngine library.

Implements a family of cancellation policies using the Strategy pattern.
Each policy encapsulates a different business rule for how much of a
guest's payment is refundable, based on how far in advance they cancel.

This is used by the booking Lambda handler to compute refund amounts
without the Lambda itself needing to know the business rules.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class CancellationPolicy(ABC):
    """
    Abstract base class for all cancellation policies.

    Subclasses must implement `refund_percentage`, which returns a value
    between 0.0 (no refund) and 1.0 (full refund) based on how many hours
    remain before check-in at the time of cancellation.
    """

    @abstractmethod
    def refund_percentage(self, hours_before_checkin: float) -> float:
        """Return the fraction of the booking cost that is refundable."""
        raise NotImplementedError

    def compute_refund(self, booking_amount: float, checkin_time: datetime,
                        cancellation_time: Optional[datetime] = None) -> float:
        """
        Compute the actual refund amount in currency units.

        :param booking_amount: total amount paid for the booking
        :param checkin_time: the scheduled check-in datetime
        :param cancellation_time: when the cancellation is requested
                                   (defaults to now if not provided)
        """
        if cancellation_time is None:
            cancellation_time = datetime.utcnow()

        delta = checkin_time - cancellation_time
        hours_before = max(delta.total_seconds() / 3600.0, 0.0)

        pct = self.refund_percentage(hours_before)
        # Defensive clamp - a policy should never return outside [0, 1],
        # but we guard against implementation bugs here.
        pct = min(max(pct, 0.0), 1.0)

        return round(booking_amount * pct, 2)


class FlexiblePolicy(CancellationPolicy):
    """Full refund if cancelled at least 24 hours before check-in."""

    def refund_percentage(self, hours_before_checkin: float) -> float:
        if hours_before_checkin >= 24:
            return 1.0
        if hours_before_checkin >= 6:
            return 0.5
        return 0.0


class ModeratePolicy(CancellationPolicy):
    """Full refund at 5+ days out, 50% at 2-5 days, none inside 48 hours."""

    def refund_percentage(self, hours_before_checkin: float) -> float:
        days_before = hours_before_checkin / 24.0
        if days_before >= 5:
            return 1.0
        if days_before >= 2:
            return 0.5
        return 0.0


class StrictPolicy(CancellationPolicy):
    """Only a partial refund, and only well in advance of check-in."""

    def refund_percentage(self, hours_before_checkin: float) -> float:
        days_before = hours_before_checkin / 24.0
        if days_before >= 14:
            return 0.5
        return 0.0


def get_policy(policy_name: str) -> CancellationPolicy:
    """
    Factory function that maps a policy name (as stored against a room
    or rate plan in DynamoDB) to a CancellationPolicy instance.
    """
    policies = {
        "FLEXIBLE": FlexiblePolicy,
        "MODERATE": ModeratePolicy,
        "STRICT": StrictPolicy,
    }
    try:
        return policies[policy_name.upper()]()
    except KeyError:
        raise ValueError(f"Unknown cancellation policy: {policy_name}")
