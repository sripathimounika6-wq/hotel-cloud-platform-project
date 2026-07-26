"""
Unit tests for the BookingRulesEngine library.
Run with: python -m pytest tests/ -v
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from booking_rules_engine import (
    get_policy, PricingEngine, BlendedPricing,
    OverbookingResolver, BookingRecord, GuestTier,
)


def test_flexible_policy_full_refund():
    policy = get_policy("FLEXIBLE")
    checkin = datetime.utcnow() + timedelta(hours=48)
    refund = policy.compute_refund(100.0, checkin)
    assert refund == 100.0


def test_flexible_policy_no_refund_last_minute():
    policy = get_policy("FLEXIBLE")
    checkin = datetime.utcnow() + timedelta(hours=2)
    refund = policy.compute_refund(100.0, checkin)
    assert refund == 0.0


def test_strict_policy_requires_two_weeks():
    policy = get_policy("STRICT")
    checkin = datetime.utcnow() + timedelta(days=20)
    refund = policy.compute_refund(200.0, checkin)
    assert refund == 100.0  # 50%


def test_unknown_policy_raises():
    try:
        get_policy("MADE_UP")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_pricing_high_occupancy_premium():
    engine = PricingEngine(BlendedPricing())
    price = engine.price_for(base_rate=100.0, occupancy_pct=0.95,
                              days_until_checkin=10, is_weekend=False)
    assert price == 140.0


def test_pricing_last_minute_discount():
    engine = PricingEngine(BlendedPricing())
    price = engine.price_for(base_rate=100.0, occupancy_pct=0.2,
                              days_until_checkin=1, is_weekend=False)
    assert price == 80.0


def test_overbooking_protects_higher_tier():
    resolver = OverbookingResolver()
    bookings = [
        BookingRecord("b1", GuestTier.STANDARD, "2026-08-01", "2026-07-01T10:00:00", "Deluxe"),
        BookingRecord("b2", GuestTier.PLATINUM, "2026-08-01", "2026-07-05T10:00:00", "Deluxe"),
        BookingRecord("b3", GuestTier.SILVER, "2026-08-01", "2026-07-02T10:00:00", "Deluxe"),
    ]
    plan = resolver.resolve(bookings, rooms_available=2)

    protected_ids = {b.booking_id for b in plan.protected_bookings}
    assert protected_ids == {"b2", "b3"}
    assert plan.relocation_candidates[0].booking_id == "b1"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
