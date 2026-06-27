"""Opportunity allocation — trend strength + marketplace + maximiser."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.settings import TradeMode
from typing import TYPE_CHECKING

from intelligence.dynamic_pip_targets import DynamicPipTargetDecision, DynamicPipTargetEngine

if TYPE_CHECKING:
    from council.opportunity_hunter_council import CouncilConsensus
    from intelligence.market_narrative_engine import MarketNarrativeResult
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.narrative_forecast_engine import NarrativeForecastResult
    from intelligence.story_evolution_engine import NestedStoryState
    from intelligence.story_forecast_engine import StoryForecastResult
from intelligence.dynamic_strategy_selector import (
    DynamicStrategySelector,
    StrategySelection,
)
from intelligence.harvest_archetype_memory import ArchetypeCheckResult, HarvestArchetypeMemory
from intelligence.harvest_opportunity_score import HarvestOpportunityScore, HarvestOpportunityScorer
from intelligence.rolling_fitness import RollingFitnessMemory
from intelligence.strategy_marketplace import MarketplaceSelection, StrategyMarketplace
from intelligence.trend_maximiser import TrendMaximiser, TrendMaximiserDecision
from intelligence.trend_strength_engine import TrendStrengthEngine, TrendStrengthResult
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

REPORT_MIN_INTERVAL_SEC = 120.0


@dataclass(frozen=True)
class AdaptiveConfirmation:
    """Drawdown-adaptive confirmation requirements."""

    min_bias_confidence: float
    min_structure_swings: int
    risk_multiplier: float
    defensive_mode: bool
    tier: str

    def to_dict(self) -> dict:
        return {
            "min_bias_confidence": round(self.min_bias_confidence, 4),
            "min_structure_swings": self.min_structure_swings,
            "risk_multiplier": round(self.risk_multiplier, 2),
            "defensive_mode": self.defensive_mode,
            "tier": self.tier,
        }


@dataclass(frozen=True)
class OpportunityAllocation:
    """Full opportunity allocation decision."""

    symbol: str
    trend_strength: TrendStrengthResult
    marketplace: MarketplaceSelection
    maximiser: TrendMaximiserDecision
    confirmation: AdaptiveConfirmation
    strategy_selection: StrategySelection
    harvest_boost: bool
    harvest_score: HarvestOpportunityScore | None = None
    archetype_check: ArchetypeCheckResult | None = None
    dynamic_pip_target: DynamicPipTargetDecision | None = None
    council_consensus: CouncilConsensus | None = None
    narrative_forecast: NarrativeForecastResult | None = None

    def to_dict(self) -> dict:
        payload = {
            "symbol": self.symbol,
            "trend_strength": self.trend_strength.to_dict(),
            "marketplace": self.marketplace.to_dict(),
            "maximiser": self.maximiser.to_dict(),
            "confirmation": self.confirmation.to_dict(),
            "strategy_selection": self.strategy_selection.to_dict(),
            "harvest_boost": self.harvest_boost,
        }
        if self.harvest_score is not None:
            payload["harvest_score"] = self.harvest_score.to_dict()
        if self.archetype_check is not None:
            payload["archetype_check"] = self.archetype_check.to_dict()
        if self.dynamic_pip_target is not None:
            payload["dynamic_pip_target"] = self.dynamic_pip_target.to_dict()
        if self.council_consensus is not None:
            payload["council_consensus"] = self.council_consensus.to_dict()
        if self.narrative_forecast is not None:
            payload["narrative_forecast"] = self.narrative_forecast.to_dict()
        return payload


class OpportunityAllocator:
    """Coordinate trend scoring, strategy competition, and maximisation."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.trend_engine = TrendStrengthEngine()
        self.fitness_memory = RollingFitnessMemory(project_root)
        self.marketplace = StrategyMarketplace(self.fitness_memory)
        self.maximiser = TrendMaximiser()
        self.selector = DynamicStrategySelector(project_root)
        self.harvest_scorer = HarvestOpportunityScorer(project_root)
        self.archetype_memory = HarvestArchetypeMemory(project_root)
        self.pip_target_engine = DynamicPipTargetEngine(project_root)
        self._trend_snapshots: dict[str, object] = {}
        self._allocations: dict[str, OpportunityAllocation] = {}
        self._last_report_write: float = 0.0

    def refresh_fitness(self, journal_path: Path | None = None) -> None:
        self.fitness_memory.refresh_from_journal(journal_path)
        self.archetype_memory.refresh_from_journal(journal_path)

    def allocate(
        self,
        *,
        symbol: str,
        candles: dict,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
        spread_pips: float,
        spread_limit: float,
        drawdown_pct: float = 0.0,
        open_positions_on_symbol: int = 0,
        evaluation_moment: datetime | None = None,
        base_min_bias: float = 0.45,
        base_min_swings: int = 2,
        narrative: MarketNarrativeResult | None = None,
        market_story: MarketStoryResult | None = None,
        forecast: NarrativeForecastResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        story_evolution: NestedStoryState | None = None,
        council: CouncilConsensus | None = None,
        indicator_insight: float = 0.0,
    ) -> OpportunityAllocation:
        snapshot, trend = self.trend_engine.evaluate(
            symbol=symbol,
            candles=candles,
            bias=bias,
            structure=structure,
            regime=regime,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            in_active_session=True,
            evaluation_time=(
                evaluation_moment.isoformat() if evaluation_moment else None
            ),
        )
        self._trend_snapshots[symbol] = snapshot

        from intelligence.harvest_opportunity_score import infer_session
        from intelligence.indicator_interpretation_engine import IndicatorInterpretationEngine

        narrative_direction = "neutral"
        if story_forecast is not None:
            narrative_direction = story_forecast.direction
        elif forecast is not None:
            narrative_direction = forecast.direction
        elif bias.bias != "neutral":
            narrative_direction = bias.bias
        interp_engine = IndicatorInterpretationEngine(self.project_root)
        interpretation = interp_engine.interpret(
            symbol=symbol,
            candles=candles,
            structure=structure,
            bias=bias,
            regime=regime,
            narrative_direction=narrative_direction,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
        )
        if indicator_insight == 0.0:
            indicator_insight = interpretation.insight_score

        target_pips = 10.0
        spread_to_target = spread_pips / max(target_pips, 0.1)
        structure_clean = len(structure.swing_highs) >= 2 and len(structure.swing_lows) >= 2
        session_hour = evaluation_moment.hour if evaluation_moment else None
        session = infer_session(session_hour) if session_hour is not None else "any"

        harvest_score = self.harvest_scorer.score(
            symbol=symbol,
            trend=trend,
            snapshot=snapshot,
            bias=bias,
            structure=structure,
            regime=regime,
            spread_pips=spread_pips,
            target_pips=target_pips,
            in_active_session=True,
            evaluation_moment=evaluation_moment,
            narrative=narrative,
            market_story=market_story,
            forecast=forecast,
            story_forecast=story_forecast,
            story_evolution=story_evolution,
            council=council,
            indicator_insight=indicator_insight,
        )
        archetype_check = self.archetype_memory.check(
            symbol=symbol,
            session=harvest_score.session,
            regime=regime.regime,
            trend_quality=trend.quality,
            asset_state=snapshot.state,
        )

        market = self.marketplace.compete(
            trend=trend,
            regime=regime.regime,
            session=harvest_score.session,
            spread_to_target=spread_to_target,
            structure_clean=structure_clean,
        )
        atr_ratio = getattr(snapshot, "features", None)
        atr_value = getattr(atr_ratio, "atr_ratio", None) if atr_ratio else None
        exit_profile = None
        if market_story is not None:
            narrative_for_exit = market_story.to_narrative_result()
            from intelligence.narrative_forecast_engine import NarrativeForecastEngine

            exit_profile = NarrativeForecastEngine.exit_profile_for(
                narrative_for_exit.micro_narrative_class,
                phase=narrative_for_exit.primary_phase,
            )
        elif narrative is not None:
            from intelligence.narrative_forecast_engine import NarrativeForecastEngine

            exit_profile = NarrativeForecastEngine.exit_profile_for(
                narrative.micro_narrative_class,
                phase=narrative.primary_phase,
            )
        maximiser = self.maximiser.evaluate(
            trend=trend,
            structure=structure,
            drawdown_pct=drawdown_pct,
            open_positions_on_symbol=open_positions_on_symbol,
            spread_to_target=spread_to_target,
            atr_ratio=atr_value,
            harvest_score=harvest_score,
            archetype_check=archetype_check,
            council=council,
            forecast=forecast,
            exit_profile=exit_profile,
        )
        atr_pips = snapshot.features.swing_range_pips if snapshot else 5.0
        council_micro = (
            council is not None
            and getattr(council, "micro_harvest", False)
        )
        forecast_conf = (
            story_forecast.confidence
            if story_forecast is not None
            else (forecast.confidence if forecast is not None else 0.0)
        )
        pa_vol_agree = any(
            r.indicator == "OBV" and "supports" in r.reading
            for r in interpretation.psychological_readings
        ) and any(
            r.indicator in {"ADX", "Moving averages"} and "control" in r.reading.lower()
            for r in interpretation.psychological_readings
        )
        dynamic_pip = self.pip_target_engine.evaluate(
            symbol=symbol,
            atr_ratio=atr_value or snapshot.features.atr_ratio,
            atr_pips=atr_pips,
            spread_pips=spread_pips,
            trend=trend,
            harvest_score=harvest_score,
            choppiness=snapshot.features.choppiness,
            allow_pyramiding=maximiser.allow_continuation_addon,
            micro_harvest=council_micro,
            forecast_confidence=forecast_conf,
            price_action_volume_agree=pa_vol_agree,
            narrative_target_multiplier=exit_profile.target_multiplier if exit_profile else 1.0,
            expected_pip_range=(
                story_forecast.expected_pip_range
                if story_forecast
                else (forecast.expected_pip_range if forecast else None)
            ),
            allow_runner=exit_profile.allow_runner if exit_profile else False,
            partial_fraction=exit_profile.partial_fraction if exit_profile else 0.5,
            move_stop_to_breakeven=exit_profile.move_stop_to_breakeven if exit_profile else False,
            exit_speed=exit_profile.exit_speed if exit_profile else 1.0,
        )
        confirmation = self._adaptive_confirmation(
            drawdown_pct=drawdown_pct,
            trend=trend,
            base_min_bias=base_min_bias,
            base_min_swings=base_min_swings,
        )

        if trend.score >= 80:
            confirmation = AdaptiveConfirmation(
                min_bias_confidence=max(0.4, base_min_bias - 0.05),
                min_structure_swings=base_min_swings,
                risk_multiplier=confirmation.risk_multiplier,
                defensive_mode=False,
                tier=confirmation.tier,
            )

        selection = self._build_selection(
            snapshot=snapshot,
            trend=trend,
            market=market,
            maximiser=maximiser,
            confirmation=confirmation,
            evaluation_moment=evaluation_moment,
            council=council,
            forecast=forecast,
            market_story=market_story,
            story_forecast=story_forecast,
        )

        harvest_boost = (
            trend.quality == "institutional_trend"
            and maximiser.allow_primary_entry
            and market.strategy in {"harvest", "normal_trend", "breakout_continuation"}
        ) or (
            market_story is not None
            and market_story.story_clear
            and market_story.opportunity_type is not None
        )

        allocation = OpportunityAllocation(
            symbol=symbol,
            trend_strength=trend,
            marketplace=market,
            maximiser=maximiser,
            confirmation=confirmation,
            strategy_selection=selection,
            harvest_boost=harvest_boost,
            harvest_score=harvest_score,
            archetype_check=archetype_check,
            dynamic_pip_target=dynamic_pip,
            council_consensus=council,
            narrative_forecast=forecast,
        )
        self._allocations[symbol] = allocation
        return allocation

    def _adaptive_confirmation(
        self,
        *,
        drawdown_pct: float,
        trend: TrendStrengthResult,
        base_min_bias: float,
        base_min_swings: int,
    ) -> AdaptiveConfirmation:
        """Drawdown does not tighten confirmation — diagnostic tier only."""
        tier = "defensive" if drawdown_pct >= 20.0 else "normal"
        return AdaptiveConfirmation(
            min_bias_confidence=base_min_bias,
            min_structure_swings=base_min_swings,
            risk_multiplier=1.0,
            defensive_mode=False,
            tier=tier,  # type: ignore[arg-type]
        )

    def _build_selection(
        self,
        *,
        snapshot: object,
        trend: TrendStrengthResult,
        market: MarketplaceSelection,
        maximiser: TrendMaximiserDecision,
        confirmation: AdaptiveConfirmation,
        evaluation_moment: datetime | None,
        council: CouncilConsensus | None = None,
        forecast: NarrativeForecastResult | None = None,
        market_story: MarketStoryResult | None = None,
        story_forecast: StoryForecastResult | None = None,
    ) -> StrategySelection:
        from intelligence.asset_trend_analyzer import AssetTrendSnapshot

        assert isinstance(snapshot, AssetTrendSnapshot)
        base = self.selector.select(
            snapshot,
            evaluation_moment=evaluation_moment,
        )
        base = self.selector.apply_story_forecast(
            base,
            market_story=market_story,
            story_forecast=story_forecast,
            council=council,
            forecast=forecast,
        )

        strategy_map = {
            "harvest": "harvest",
            "normal_trend": "normal_trend",
            "breakout_continuation": "breakout_continuation",
            "mean_reversion": "mean_reversion",
            "range_scalper": "range_scalper",
            "micro_scalp": "micro_scalp_reduced",
            "no_trade": "no_trade",
        }
        mapped = strategy_map.get(market.strategy, "no_trade")

        allow_harvest = mapped in {
            "harvest", "normal_trend", "breakout_continuation",
            "reduced_risk_harvest", "confirmation_heavy_trend", "breakout",
            "momentum_continuation",
        } and maximiser.allow_primary_entry and not confirmation.defensive_mode

        allow_scalp = mapped in {"mean_reversion", "range_scalper", "micro_scalp_reduced"} and (
            maximiser.allow_primary_entry or trend.quality == "range_or_noise"
        )

        story_unlock = (
            market_story is not None
            and market_story.story_clear
            and market_story.opportunity_type is not None
        )
        if market.strategy == "no_trade" and story_unlock:
            micro_types = {
                "liquidity_sweep",
                "mean_reversion_snapback",
                "failed_breakout",
                "session_transition",
            }
            if market_story.opportunity_type in micro_types:
                mapped = "micro_scalp_reduced"
                allow_scalp = True
                allow_harvest = False
            else:
                mapped = "harvest"
                allow_harvest = True
                allow_scalp = False
            trade_mode = "scalp" if allow_scalp else "harvest"
        if confirmation.defensive_mode:
            allow_harvest = allow_harvest or story_unlock
            allow_scalp = allow_scalp or (
                story_unlock and market_story.opportunity_type in {
                    "liquidity_sweep",
                    "mean_reversion_snapback",
                    "failed_breakout",
                    "session_transition",
                }
            )

        trade_mode: TradeMode = "harvest" if allow_harvest else ("scalp" if allow_scalp else "normal")
        risk_mult = min(
            base.risk_multiplier,
            confirmation.risk_multiplier,
            maximiser.risk_multiplier,
        )
        if market.recommended_action == "REDUCED_RISK":
            risk_mult = min(risk_mult, 0.5)
        elif market.recommended_action == "CONDITIONAL":
            risk_mult = min(risk_mult, 0.75)

        heavy = base.require_heavy_confirmation or confirmation.tier in {"cautious", "defensive"}

        return StrategySelection(
            symbol=base.symbol,
            asset_state=snapshot.state,
            selected_strategy=mapped,  # type: ignore[arg-type]
            trade_mode=trade_mode,
            allow_harvest=allow_harvest,
            allow_micro_scalp=allow_scalp,
            risk_multiplier=risk_mult,
            require_heavy_confirmation=heavy,
            reason=f"{market.reason}; {maximiser.reason}",
            switched=base.switched,
            asset_status=market.recommended_action,
        )

    def maybe_write_reports(self, *, force: bool = False) -> tuple[Path, Path, Path] | None:
        now = time.monotonic()
        if not force and (now - self._last_report_write) < REPORT_MIN_INTERVAL_SEC:
            return None
        self._last_report_write = now
        return self.write_reports()

    def write_reports(self) -> tuple[Path, Path, Path]:
        logs = self.project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()

        trend_path = logs / "trend_strength_report.md"
        trend_lines = [
            "# Trend Strength Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Score | Quality | Direction | Reason |",
            "|--------|-------|---------|-----------|--------|",
        ]
        for symbol, alloc in sorted(self._allocations.items()):
            t = alloc.trend_strength
            trend_lines.append(
                f"| {symbol} | {t.score:.0f} | {t.quality} | {t.direction} | {t.reason[:50]} |"
            )
        trend_path.write_text("\n".join(trend_lines) + "\n", encoding="utf-8")

        market_path = logs / "strategy_marketplace_report.md"
        market_lines = [
            "# Strategy Marketplace Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Winner | Fitness | Trend | Action | Reason |",
            "|--------|--------|---------|-------|--------|--------|",
        ]
        for symbol, alloc in sorted(self._allocations.items()):
            m = alloc.marketplace
            market_lines.append(
                f"| {symbol} | {m.strategy} | {m.fitness_score:.2f} | "
                f"{m.trend_score:.0f} | {m.recommended_action} | {m.reason[:40]} |"
            )
        for symbol, profile in sorted(self.fitness_memory.all_profiles().items()):
            market_lines.append(
                f"\n**{symbol}** best={profile.best_strategy_overall} "
                f"worst={profile.worst_strategy} action={profile.recommended_action}"
            )
        market_path.write_text("\n".join(market_lines) + "\n", encoding="utf-8")

        max_path = logs / "trend_maximiser_report.md"
        max_lines = [
            "# Trend Maximiser Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Primary | Pullback | Retest | Add-on | 1R partial | Trail | Risk |",
            "|--------|---------|----------|--------|--------|------------|-------|------|",
        ]
        for symbol, alloc in sorted(self._allocations.items()):
            mx = alloc.maximiser
            max_lines.append(
                f"| {symbol} | {'Y' if mx.allow_primary_entry else 'N'} | "
                f"{'Y' if mx.allow_pullback_reentry else 'N'} | "
                f"{'Y' if mx.allow_breakout_retest else 'N'} | "
                f"{'Y' if mx.allow_continuation_addon else 'N'} | "
                f"{'Y' if mx.partial_take_profit_at_1r else 'N'} | "
                f"{mx.trail_timeframe} | {mx.risk_multiplier:.0%} |"
            )
        max_path.write_text("\n".join(max_lines) + "\n", encoding="utf-8")

        if self._allocations:
            snapshots = {s: self._trend_snapshots[s] for s in self._allocations}
            selections = {s: a.strategy_selection for s, a in self._allocations.items()}
            self.selector.write_dynamic_strategy_report(snapshots, selections)  # type: ignore[arg-type]
            self.harvest_scorer.write_report()
            self.pip_target_engine.write_report()
            self.archetype_memory.write_report()

        return trend_path, market_path, max_path
