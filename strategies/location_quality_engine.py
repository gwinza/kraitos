"""Location quality — premium/discount, structure proximity, chase risk, reward window."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles

PremiumDiscountState = Literal["premium", "discount", "equilibrium", "unknown"]


@dataclass(frozen=True)
class LocationQualityResult:
    location_quality_score: int
    premium_discount_state: PremiumDiscountState
    distance_from_fair_value: float
    distance_from_liquidity: float
    distance_from_structure: float
    chase_risk: float
    reward_window_open: bool
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "location_quality_score": self.location_quality_score,
            "premium_discount_state": self.premium_discount_state,
            "distance_from_fair_value": round(self.distance_from_fair_value, 3),
            "distance_from_liquidity": round(self.distance_from_liquidity, 3),
            "distance_from_structure": round(self.distance_from_structure, 3),
            "chase_risk": round(self.chase_risk, 3),
            "reward_window_open": self.reward_window_open,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class LocationQualityConfig:
    min_candles: int = 20
    chase_displacement_atr: float = 1.8
    min_reward_r_after_spread: float = 0.55


class LocationQualityEngine:
    """Score whether price is where professionals would act — not chasing."""

    def __init__(self, config: LocationQualityConfig | None = None) -> None:
        self.config = config or LocationQualityConfig()

    def evaluate(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_price: float | None,
        spread_pips: float,
        pip_size: float,
        candles: pd.DataFrame | None = None,
        institutional_structure: object | None = None,
        range_intelligence: object | None = None,
    ) -> LocationQualityResult:
        evidence: list[str] = []
        state: PremiumDiscountState = "unknown"
        dist_fv = 0.5
        dist_liq = 0.5
        dist_struct = 0.5
        chase_risk = 0.0
        reward_open = True

        inst = institutional_structure
        if inst is not None:
            eq = float(getattr(inst, "equilibrium", entry_price) or entry_price)
            prem_low = float(getattr(inst, "premium_zone_low", eq) or eq)
            prem_high = float(getattr(inst, "premium_zone_high", eq) or eq)
            disc_low = float(getattr(inst, "discount_zone_low", eq) or eq)
            disc_high = float(getattr(inst, "discount_zone_high", eq) or eq)
            in_premium = bool(getattr(inst, "in_premium", False))
            in_discount = bool(getattr(inst, "in_discount", False))
            in_ote = bool(getattr(inst, "in_ote", False))

            span = max(prem_high - disc_low, pip_size * 10)
            dist_fv = min(1.0, abs(entry_price - eq) / span)

            if in_premium:
                state = "premium"
            elif in_discount:
                state = "discount"
            elif in_ote:
                state = "equilibrium"
                evidence.append("price in OTE / equilibrium band")
            else:
                state = "equilibrium"

            pools = getattr(inst, "liquidity_pools", ()) or ()
            if pools:
                nearest = min(
                    abs(float(getattr(p, "level", entry_price)) - entry_price) for p in pools
                )
                dist_liq = min(1.0, nearest / max(span, pip_size))
                if dist_liq < 0.15:
                    evidence.append("near institutional liquidity pool")

            dist_struct = 0.25 if in_ote else dist_fv

        rng = range_intelligence
        if rng is not None:
            location = str(getattr(rng, "price_location", "") or "")
            if side == "buy" and location in {"near_support", "lower_half"}:
                dist_struct = min(dist_struct, 0.2)
                evidence.append(f"range location favourable: {location}")
            elif side == "sell" and location in {"near_resistance", "upper_half"}:
                dist_struct = min(dist_struct, 0.2)
                evidence.append(f"range location favourable: {location}")
            elif location:
                dist_struct = max(dist_struct, 0.55)

        if candles is not None and not candles.empty:
            try:
                frame = validate_candles(
                    candles, min_candles=self.config.min_candles, engine="LocationQualityEngine"
                ).tail(30)
                atr = float(atr_series(frame).iloc[-1]) or pip_size * 10
                recent_move = abs(float(frame["close"].iloc[-1]) - float(frame["close"].iloc[-5]))
                chase_risk = min(1.0, recent_move / (atr * self.config.chase_displacement_atr))
                if chase_risk > 0.65:
                    evidence.append("post-displacement chase risk elevated")
            except ValueError:
                pass

        stop_pips = abs(entry_price - stop_loss) / pip_size if pip_size > 0 else 0.0
        target_pips = (
            abs(target_price - entry_price) / pip_size
            if target_price is not None and pip_size > 0
            else stop_pips * 1.5
        )
        reward_r = target_pips / max(stop_pips, 0.01)
        spread_drag = spread_pips / max(target_pips, 0.01)
        net_r = reward_r - spread_drag
        reward_open = net_r >= self.config.min_reward_r_after_spread and chase_risk < 0.75
        if not reward_open:
            evidence.append(
                f"reward window tight (net ~{net_r:.2f}R after spread)"
            )

        location_score = 50
        if side == "buy":
            if state == "discount":
                location_score += 28
                evidence.append("buying in discount — professional location")
            elif state == "premium":
                location_score -= 22
                evidence.append("buying in premium — poor location")
            elif state == "equilibrium":
                location_score += 8
        elif side == "sell":
            if state == "premium":
                location_score += 28
                evidence.append("selling in premium — professional location")
            elif state == "discount":
                location_score -= 22
                evidence.append("selling in discount — poor location")
            elif state == "equilibrium":
                location_score += 8

        location_score += int((1.0 - dist_struct) * 15)
        location_score += int((1.0 - dist_liq) * 10)
        location_score -= int(chase_risk * 25)
        if reward_open:
            location_score += 8
        location_score = max(0, min(100, location_score))

        aligned = (
            (side == "buy" and state in {"discount", "equilibrium"})
            or (side == "sell" and state in {"premium", "equilibrium"})
        )
        explanation = (
            f"Location {location_score}/100 — {state}, chase {chase_risk:.0%}, "
            f"reward {'open' if reward_open else 'compressed'}"
        )
        if not aligned:
            explanation += " | direction/location misaligned"

        return LocationQualityResult(
            location_quality_score=location_score,
            premium_discount_state=state,
            distance_from_fair_value=dist_fv,
            distance_from_liquidity=dist_liq,
            distance_from_structure=dist_struct,
            chase_risk=chase_risk,
            reward_window_open=reward_open,
            explanation=explanation,
            evidence=tuple(evidence),
        )
