"""
VehicleServiceRulesEngine
==========================

A small object-oriented library providing the business-rule logic for
a fleet vehicle service booking platform:

- Cancellation policies and deposit refund calculation (cancellation_policy.py)
- Dynamic, occupancy-aware labor pricing (labor_pricing.py)
- Service bay overbooking resolution and customer prioritisation
  (bay_allocation_resolver.py)

This library is intentionally decoupled from AWS - it has no dependency
on boto3 or any AWS SDK. Lambda handlers import it and pass in plain
Python data, which keeps the business logic unit-testable in isolation
and reusable outside of AWS if needed (e.g. in a local admin tool).
"""

from .cancellation_policy import (
    CancellationPolicy,
    FlexiblePolicy,
    StandardPolicy,
    NoShowStrictPolicy,
    get_policy,
)
from .labor_pricing import (
    PricingContext,
    PricingStrategy,
    OccupancyBasedPricing,
    LastMinuteDiscountPricing,
    BlendedPricing,
    LaborPricingEngine,
)
from .bay_allocation_resolver import (
    CustomerTier,
    AppointmentRecord,
    ResolutionPlan,
    BayAllocationResolver,
)

__all__ = [
    "CancellationPolicy", "FlexiblePolicy", "StandardPolicy", "NoShowStrictPolicy", "get_policy",
    "PricingContext", "PricingStrategy", "OccupancyBasedPricing",
    "LastMinuteDiscountPricing", "BlendedPricing", "LaborPricingEngine",
    "CustomerTier", "AppointmentRecord", "ResolutionPlan", "BayAllocationResolver",
]

__version__ = "1.0.0"
