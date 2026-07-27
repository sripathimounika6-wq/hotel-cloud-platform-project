"""
Unit tests for the VehicleServiceRulesEngine library.
Run with: python -m pytest tests/ -v
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from vehicle_service_engine import (
    get_policy, LaborPricingEngine, BlendedPricing,
    BayAllocationResolver, AppointmentRecord, CustomerTier,
)


def test_flexible_policy_full_refund():
    policy = get_policy("FLEXIBLE")
    appointment = datetime.utcnow() + timedelta(hours=48)
    refund = policy.compute_refund(100.0, appointment)
    assert refund == 100.0


def test_flexible_policy_no_refund_last_minute():
    policy = get_policy("FLEXIBLE")
    appointment = datetime.utcnow() + timedelta(hours=2)
    refund = policy.compute_refund(100.0, appointment)
    assert refund == 0.0


def test_no_show_strict_requires_five_days():
    policy = get_policy("NO_SHOW_STRICT")
    appointment = datetime.utcnow() + timedelta(days=7)
    refund = policy.compute_refund(200.0, appointment)
    assert refund == 100.0  # 50%


def test_unknown_policy_raises():
    try:
        get_policy("MADE_UP")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_pricing_high_occupancy_premium():
    engine = LaborPricingEngine(BlendedPricing())
    price = engine.price_for(base_rate=100.0, bay_occupancy_pct=0.95,
                              days_until_appointment=10, is_peak_day=False)
    assert price == 135.0


def test_pricing_last_minute_discount():
    engine = LaborPricingEngine(BlendedPricing())
    price = engine.price_for(base_rate=100.0, bay_occupancy_pct=0.2,
                              days_until_appointment=1, is_peak_day=False)
    assert price == 80.0


def test_bay_overbooking_protects_fleet_accounts():
    resolver = BayAllocationResolver()
    appointments = [
        AppointmentRecord("a1", CustomerTier.STANDARD, "2026-08-01", "2026-07-01T10:00:00", "Full Service"),
        AppointmentRecord("a2", CustomerTier.FLEET_ACCOUNT, "2026-08-01", "2026-07-05T10:00:00", "Full Service"),
        AppointmentRecord("a3", CustomerTier.SILVER, "2026-08-01", "2026-07-02T10:00:00", "Full Service"),
    ]
    plan = resolver.resolve(appointments, bays_available=2)

    protected_ids = {a.appointment_id for a in plan.protected_appointments}
    assert protected_ids == {"a2", "a3"}
    assert plan.reschedule_candidates[0].appointment_id == "a1"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
