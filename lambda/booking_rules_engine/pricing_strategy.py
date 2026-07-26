"""
pricing_strategy.py

Part of the BookingRulesEngine library.

Implements dynamic pricing using the Strategy pattern: given a base rate,
current occupancy, and how far out the booking is, compute the actual
nightly price to charge.

This is the core "meaningful functionality" the library provides -
the booking Lambda calls into this instead of embedding pricing math
directly in the handler.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PricingContext:
    """All the inputs a pricing strategy needs to compute a nightly rate."""
    base_rate: float
    occupancy_pct: float       # 0.0 - 1.0, how full the hotel is for that night
    days_until_checkin: int    # how far in advance the booking is being made
    is_weekend: bool = False


class PricingStrategy(ABC):
    """Abstract base for pricing strategies."""

    @abstractmethod
    def compute_price(self, ctx: PricingContext) -> float:
        raise NotImplementedError


class OccupancyBasedPricing(PricingStrategy):
    """
    Raises price as occupancy increases (classic revenue-management logic),
    and applies a small weekend premium.
    """

    def compute_price(self, ctx: PricingContext) -> float:
        price = ctx.base_rate

        if ctx.occupancy_pct >= 0.9:
            price *= 1.40
        elif ctx.occupancy_pct >= 0.75:
            price *= 1.20
        elif ctx.occupancy_pct >= 0.5:
            price *= 1.05

        if ctx.is_weekend:
            price *= 1.10

        return round(price, 2)


class LastMinuteDiscountPricing(PricingStrategy):
    """
    Discounts unsold rooms as check-in approaches, but only if occupancy
    is still low - avoids discounting rooms that would sell anyway.
    """

    def compute_price(self, ctx: PricingContext) -> float:
        price = ctx.base_rate

        if ctx.occupancy_pct < 0.5 and ctx.days_until_checkin <= 2:
            price *= 0.80
        elif ctx.occupancy_pct < 0.3 and ctx.days_until_checkin <= 5:
            price *= 0.90

        if ctx.is_weekend:
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
        if ctx.occupancy_pct >= 0.5:
            return self._occupancy.compute_price(ctx)
        return self._last_minute.compute_price(ctx)


class PricingEngine:
    """
    Thin wrapper the Lambda handler talks to. Decouples callers from
    knowing which concrete strategy is active, and allows the strategy
    to be swapped (e.g. via config/env var) without touching handler code.
    """

    def __init__(self, strategy: PricingStrategy = None):
        self._strategy = strategy or BlendedPricing()

    def price_for(self, base_rate: float, occupancy_pct: float,
                  days_until_checkin: int, is_weekend: bool = False) -> float:
        ctx = PricingContext(
            base_rate=base_rate,
            occupancy_pct=occupancy_pct,
            days_until_checkin=days_until_checkin,
            is_weekend=is_weekend,
        )
        return self._strategy.compute_price(ctx)
