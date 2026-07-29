# vehicle-service-engine-nci

A small, dependency-free, object-oriented Python library implementing the
business-rule logic for a vehicle service booking platform. Built for a
cloud computing coursework project (NCI) and used inside AWS Lambda
handlers, but has no AWS dependency itself, so it is fully unit-testable
in isolation and reusable elsewhere.

## What it does

- **`cancellation_policy`** — Strategy pattern. `FlexiblePolicy`,
  `StandardPolicy`, and `NoShowStrictPolicy` each compute a deposit
  refund percentage based on how many hours before the appointment a
  customer cancels. `get_policy()` is a small factory that resolves a
  policy name (e.g. from a database record) to an instance.
- **`labor_pricing`** — Strategy pattern. `OccupancyBasedPricing` raises
  price as service bays fill up; `LastMinuteDiscountPricing` discounts
  slots that are still empty close to the appointment date;
  `BlendedPricing` combines both. `LaborPricingEngine` is the façade
  callers use, with the strategy swappable at construction time.
- **`bay_allocation_resolver`** — Resolves overbooking: given a list of
  competing appointments and the number of bays actually available,
  decides which appointments keep their slot (highest customer tier
  first, then earliest booking time) and suggests compensation for the
  rest.

## Install

```bash
pip install vehicle-service-engine-nci
```

## Quick example

```python
from vehicle_service_engine import LaborPricingEngine, BlendedPricing, get_policy

# Dynamic labor pricing
engine = LaborPricingEngine(BlendedPricing())
price = engine.price_for(
    base_rate=119.80,
    bay_occupancy_pct=0.8,
    days_until_appointment=1,
    is_peak_day=True,
)

# Cancellation refund calculation
policy = get_policy("STANDARD")
refund = policy.compute_refund(
    deposit_amount=50.0,
    appointment_time=some_datetime,
)
```

## Why a separate library

Both the appointment-booking Lambda and (potentially) an admin/rescheduling
tool need the same pricing and allocation rules. Keeping this logic in one
importable, AWS-agnostic package means it is unit tested once, versioned
independently of the Lambda deployment packages, and can be reused outside
the serverless backend if needed.

## License

MIT
