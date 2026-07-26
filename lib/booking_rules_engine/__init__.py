"""
BookingRulesEngine
==================

A small object-oriented library providing the business-rule logic for
a hotel booking platform:

- Cancellation policies and refund calculation (cancellation_policy.py)
- Dynamic, occupancy-aware pricing (pricing_strategy.py)
- Overbooking resolution and guest prioritisation (overbooking_resolver.py)

This library is intentionally decoupled from AWS - it has no dependency
on boto3 or any AWS SDK. Lambda handlers import it and pass in plain
Python data, which keeps the business logic unit-testable in isolation
and reusable outside of AWS if needed (e.g. in a local admin tool).
"""

from .cancellation_policy import (
    CancellationPolicy,
    FlexiblePolicy,
    ModeratePolicy,
    StrictPolicy,
    get_policy,
)
from .pricing_strategy import (
    PricingContext,
    PricingStrategy,
    OccupancyBasedPricing,
    LastMinuteDiscountPricing,
    BlendedPricing,
    PricingEngine,
)
from .overbooking_resolver import (
    GuestTier,
    BookingRecord,
    ResolutionPlan,
    OverbookingResolver,
)

__all__ = [
    "CancellationPolicy", "FlexiblePolicy", "ModeratePolicy", "StrictPolicy", "get_policy",
    "PricingContext", "PricingStrategy", "OccupancyBasedPricing",
    "LastMinuteDiscountPricing", "BlendedPricing", "PricingEngine",
    "GuestTier", "BookingRecord", "ResolutionPlan", "OverbookingResolver",
]

__version__ = "1.0.0"
