"""Trend maximiser — expand opportunity inside high-quality trends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from intelligence.trend_strength_engine import TrendQuality, TrendStrengthResult
from strategies.models import MarketContext

if TYPE_CHECKING:
    from council.opportunity_hunter_council import CouncilConsensus
    from intelligence.harvest_archetype_memory import ArchetypeCheckResult
    from intelligence.harvest_opportunity_score import HarvestOpportunityScore
    from intelligence.narrative_forecast_engine import NarrativeExitProfile, NarrativeForecastResult

TrailTimeframe = Literal["H1", "M15", "none"]


@dataclass(frozen=True)
class TrendMaximiserDecision:
    """Opportunity expansion rules for trending assets."""

    symbol: str
    allow_primary_entry: bool
    allow_pullback_reentry: bool
    allow_breakout_retest: bool
    allow_continuation_addon: bool
    partial_take_profit_at_1r: bool
    early_partial_on_atr_contraction: bool
    trail_timeframe: TrailTimeframe
    risk_multiplier: float
    target_pips_multiplier: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "allow_primary_entry": self.allow_primary_entry,
            "allow_pullback_reentry": self.allow_pullback_reentry,
            "allow_breakout_retest": self.allow_breakout_retest,
            "allow_continuation_addon": self.allow_continuation_addon,
            "partial_take_profit_at_1r": self.partial_take_profit_at_1r,
            "early_partial_on_atr_contraction": self.early_partial_on_atr_contraction,
            "trail_timeframe": self.trail_timeframe,
            "risk_multiplier": round(self.risk_multiplier, 2),
            "target_pips_multiplier": round(self.target_pips_multiplier, 2),
            "reason": self.reason,
        }


class TrendMaximiser:
    """Maximise opportunity in institutional/developing trends."""

    def evaluate(
        self,
        *,
        trend: TrendStrengthResult,
        structure: MarketContext,
        drawdown_pct: float,
        open_positions_on_symbol: int = 0,
        spread_to_target: float = 0.2,
        atr_ratio: float | None = None,
        harvest_score: HarvestOpportunityScore | None = None,
        archetype_check: ArchetypeCheckResult | None = None,
        council: CouncilConsensus | None = None,
        forecast: NarrativeForecastResult | None = None,
        exit_profile: NarrativeExitProfile | None = None,
    ) -> TrendMaximiserDecision:
        symbol = trend.symbol
        archetype_mult = archetype_check.risk_multiplier if archetype_check else 1.0
        harvest_band = harvest_score.band if harvest_score else "standard"
        allow_addons = open_positions_on_symbol < 2
        story_boost = forecast is not None and forecast.confidence >= 42
        council_boost = story_boost or (
            council is not None and council.consensus_confidence >= 45
        )
        hunter_edge = council.opportunity_edge if council_boost and council else None

        if trend.quality == "range_or_noise":
            clean = spread_to_target <= 0.25 and len(structure.swing_highs) >= 2
            return TrendMaximiserDecision(
                symbol=symbol,
                allow_primary_entry=clean,
                allow_pullback_reentry=False,
                allow_breakout_retest=False,
                allow_continuation_addon=False,
                partial_take_profit_at_1r=False,
                early_partial_on_atr_contraction=False,
                trail_timeframe="none",
                risk_multiplier=0.5 if clean else 0.0,
                target_pips_multiplier=1.0,
                reason="Range/noise — limited scalping only if spread clean",
            )

        exit_mult = exit_profile.target_multiplier if exit_profile else 1.0
        partial_at_1r = bool(exit_profile and exit_profile.allow_runner)
        trail_tf: TrailTimeframe = (
            exit_profile.trail_timeframe
            if exit_profile and exit_profile.trail_timeframe != "none"
            else "none"
        )

        if trend.quality == "institutional_trend":
            target_mult = 1.25 if harvest_band == "aggressive" else 1.15
            if council_boost and council and council.consensus_confidence >= 65:
                target_mult = min(1.4, target_mult + 0.1)
            target_mult = min(1.5, target_mult * exit_mult)
            if trail_tf == "none" and exit_profile and exit_profile.allow_runner:
                trail_tf = "H1"
            return TrendMaximiserDecision(
                symbol=symbol,
                allow_primary_entry=True,
                allow_pullback_reentry=True,
                allow_breakout_retest=hunter_edge != "exhaustion_snapback",
                allow_continuation_addon=allow_addons and harvest_band != "conditional",
                partial_take_profit_at_1r=partial_at_1r,
                early_partial_on_atr_contraction=exit_profile is not None and exit_profile.exit_speed > 1.1,
                trail_timeframe=trail_tf if trail_tf != "none" else "H1",
                risk_multiplier=min(1.0, archetype_mult),
                target_pips_multiplier=target_mult,
                reason="Institutional trend — narrative council maximise",
            )

        if trend.quality == "developing_trend":
            target_mult = min(1.35, 1.1 * exit_mult)
            if trail_tf == "none" and exit_profile and exit_profile.allow_runner:
                trail_tf = "M5"
            return TrendMaximiserDecision(
                symbol=symbol,
                allow_primary_entry=True,
                allow_pullback_reentry=True,
                allow_breakout_retest=False,
                allow_continuation_addon=False,
                partial_take_profit_at_1r=partial_at_1r,
                early_partial_on_atr_contraction=False,
                trail_timeframe=trail_tf if trail_tf != "none" else "H1",
                risk_multiplier=1.0,
                target_pips_multiplier=target_mult,
                reason="Developing trend — primary + pullback harvesting",
            )

        allow_weak = (
            trend.score >= 35 and harvest_band != "no_harvest"
        ) or council_boost
        if forecast is not None and forecast.confidence >= 55:
            allow_weak = True
        return TrendMaximiserDecision(
            symbol=symbol,
            allow_primary_entry=allow_weak,
            allow_pullback_reentry=False,
            allow_breakout_retest=False,
            allow_continuation_addon=False,
            partial_take_profit_at_1r=partial_at_1r and allow_weak,
            early_partial_on_atr_contraction=exit_profile is not None and exit_profile.exit_speed > 1.2,
            trail_timeframe=trail_tf,
            risk_multiplier=min(0.6, archetype_mult),
            target_pips_multiplier=min(1.2, exit_mult),
            reason="Weak trend — reduced opportunity",
        )
