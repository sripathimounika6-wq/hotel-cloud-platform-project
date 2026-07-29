"""
labor_pricing.py

Part of the VehicleServiceRulesEngine library.

Implements dynamic labor pricing using the Strategy pattern: given a
base labor rate, current bay/technician occupancy for that day, and how
far out the appointment is being booked, compute the actual price to
charge for the service slot.

Service centers commonly raise prices during high-demand periods
(e.g. Monday mornings, pre-holiday rushes) and offer last-minute
discounts to fill otherwise-idle bays. This is the core "meaningful
functionality" the library provides - the appointment Lambda calls into
this instead of embedding pricing math directly in the handler.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PricingContext:
    """All the inputs a pricing strategy needs to compute a service price."""
    base_rate: float
    bay_occupancy_pct: float   # 0.0 - 1.0, how full the service bays are that day
    days_until_appointment: int
    is_peak_day: bool = False  # e.g. Monday, or day before a public holiday


class PricingStrategy(ABC):
    """Abstract base for labor pricing strategies."""

    @abstractmethod
    def compute_price(self, ctx: PricingContext) -> float:
        raise NotImplementedError


class OccupancyBasedPricing(PricingStrategy):
    """
    Raises price as bay occupancy increases (classic capacity-based
    pricing), and applies a small peak-day premium.
    """

    def compute_price(self, ctx: PricingContext) -> float:
        price = ctx.base_rate

        if ctx.bay_occupancy_pct >= 0.9:
            price *= 1.35
        elif ctx.bay_occupancy_pct >= 0.75:
            price *= 1.15
        elif ctx.bay_occupancy_pct >= 0.5:
            price *= 1.05

        if ctx.is_peak_day:
            price *= 1.10

        return round(price, 2)


class LastMinuteDiscountPricing(PricingStrategy):
    """
    Discounts unfilled bay slots as the appointment date approaches, but
    only if occupancy is still low - avoids discounting slots that
    would fill anyway.
    """

    def compute_price(self, ctx: PricingContext) -> float:
        price = ctx.base_rate

        if ctx.bay_occupancy_pct < 0.5 and ctx.days_until_appointment <= 1:
            price *= 0.80
        elif ctx.bay_occupancy_pct < 0.3 and ctx.days_until_appointment <= 3:
            price *= 0.90

        if ctx.is_peak_day:
            price *= 1.10

        return round(price, 2)


class BlendedPricing(PricingStrategy):
    """
    Combines both signals: rewards high occupancy with a premium, but
    still offers last-minute discounts when occupancy is genuinely low.
    Used as the default strategy in production.
    """

    def __init__(self):
        self._occupancy = OccupancyBasedPricing()
        self._last_minute = LastMinuteDiscountPricing()

    def compute_price(self, ctx: PricingContext) -> float:
        if ctx.bay_occupancy_pct >= 0.5:
            return self._occupancy.compute_price(ctx)
        return self._last_minute.compute_price(ctx)


class LaborPricingEngine:
    """
    Thin wrapper the Lambda handler talks to. Decouples callers from
    knowing which concrete strategy is active, and allows the strategy
    to be swapped (e.g. via config/env var) without touching handler code.
    """

    def __init__(self, strategy: PricingStrategy = None):
        self._strategy = strategy or BlendedPricing()

    def price_for(self, base_rate: float, bay_occupancy_pct: float,
                  days_until_appointment: int, is_peak_day: bool = False) -> float:
        ctx = PricingContext(
            base_rate=base_rate,
            bay_occupancy_pct=bay_occupancy_pct,
            days_until_appointment=days_until_appointment,
            is_peak_day=is_peak_day,
        )
        return self._strategy.compute_price(ctx)
