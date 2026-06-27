"""Portfolio construction engine — orchestrates full allocation pipeline."""



from __future__ import annotations



from dataclasses import dataclass, replace

from datetime import datetime

from pathlib import Path



from typing import TYPE_CHECKING



import pandas as pd

from portfolio.currency_strength_engine import (
    CurrencyStrengthEngine,
    CurrencyStrengthSnapshot,
    CurrencyThemeMemory,
    PairStrengthAnalysis,
)
from portfolio.exposure_engine import AdaptiveConviction, ExposureDecision, ExposureEngine
from portfolio.opportunity_allocator import PortfolioOpportunityAllocator, RankedOpportunity

from portfolio.opportunity_classifier import OpportunityClassification, OpportunityClassifier



if TYPE_CHECKING:

    from intelligence.market_story_engine import MarketStoryResult

    from intelligence.opportunity_allocator import OpportunityAllocation

    from intelligence.story_forecast_engine import StoryForecastResult

from risk.models import PortfolioState, RiskDecision, TradeSide





@dataclass(frozen=True)

class PortfolioConstructionResult:

    """Outcome of portfolio construction for one symbol."""



    ranked: RankedOpportunity

    classification: OpportunityClassification

    portfolio_multiplier: float

    allow_trade: bool

    watchlist: bool

    reason: str

    currency_strength: CurrencyStrengthSnapshot | None = None

    relative_strength: PairStrengthAnalysis | None = None

    exposure_decision: ExposureDecision | None = None

    adaptive_conviction: AdaptiveConviction | None = None



    def to_dict(self) -> dict:

        return {

            "ranked": self.ranked.to_dict(),

            "classification": self.classification.to_dict(),

            "portfolio_multiplier": round(self.portfolio_multiplier, 3),

            "allow_trade": self.allow_trade,

            "watchlist": self.watchlist,

            "reason": self.reason,

            "currency_strength": (
                self.currency_strength.to_dict()
                if self.currency_strength is not None
                else None
            ),

            "relative_strength": (
                self.relative_strength.to_dict()
                if self.relative_strength is not None
                else None
            ),

            "exposure_decision": (
                self.exposure_decision.to_dict()
                if self.exposure_decision is not None
                else None
            ),

            "adaptive_conviction": (
                self.adaptive_conviction.to_dict()
                if self.adaptive_conviction is not None
                else None
            ),

        }





def _open_position_budget_multiplier(

    classification: OpportunityClassification,

    portfolio: PortfolioState,

) -> float:

    """Capital budgeting by tier — soft scale instead of max-open binary cap."""

    n = len(portfolio.open_positions)

    tier = classification.opportunity_class



    if tier in {"MICRO_HARVEST", "SCOUT"}:

        if n >= 12:

            return 0.20

        if n >= 8:

            return 0.40

        if n >= 5:

            return 0.60

        return 1.0

    if tier == "HARVEST":

        if n >= 10:

            return 0.25

        if n >= 7:

            return 0.50

        if n >= 5:

            return 0.70

        return 1.0

    if tier == "PROPER":

        if n >= 6:

            return 0.40

        if n >= 4:

            return 0.60

        if n >= 3:

            return 0.80

        return 1.0



    if tier == "ELITE":

        if n >= 4:

            return 0.50

        if n >= 3:

            return 0.70

        return 1.0



    return 1.0





class PortfolioConstructionEngine:

    """

    Wire portfolio layer into pipeline flow:



    1. Classify opportunity tier (HARVEST / PROPER / ELITE)

    2. Intelligence scores setup (OpportunityAllocation)

    3. Portfolio ranks (OAS)

    4. Risk budget allocates capital

    5. Correlation scales exposure

    6. Watchlist preserves unfunded setups

    7. Heat monitor controls total risk

    8. Capital rotation updates preferences

    """



    def __init__(self, project_root: Path) -> None:

        self.project_root = project_root.resolve()

        self.allocator = PortfolioOpportunityAllocator(project_root)

        self.classifier = OpportunityClassifier(project_root)

        self.currency_strength = CurrencyStrengthEngine()

        self.exposure = ExposureEngine()

        self.theme_memory = CurrencyThemeMemory()



    def construct(

        self,

        *,

        symbol: str,

        side: TradeSide,

        allocation: "OpportunityAllocation",

        portfolio: PortfolioState,

        spread_pips: float = 1.0,

        target_pips: float = 10.0,

        mode: str = "harvest",

        loss_streak: int = 0,

        trace_id: str = "",

        evaluation_moment: datetime | None = None,

        base_risk_pct: float = 1.0,

        market_story: "MarketStoryResult | None" = None,

        story_forecast: "StoryForecastResult | None" = None,

        valid_story: bool = True,

        setup_kind: str = "harvest",

        emergency_stop: bool = False,

        broker_available: bool = True,

        live_safety_ok: bool = True,

        candles: dict[str, pd.DataFrame] | None = None,

        pair_conviction: float | None = None,

        expected_r: float | None = None,

    ) -> PortfolioConstructionResult:

        if candles:
            strength_snapshot = self.currency_strength.update_symbol(symbol, candles)
        else:
            strength_snapshot = self.currency_strength.latest_snapshot()
        relative_strength = self.currency_strength.pair_analysis(symbol)
        if relative_strength is not None:
            memory_adjustment = self.theme_memory.confidence_adjustment(
                relative_strength.trade_theme
            )
            if memory_adjustment:
                relative_strength = replace(
                    relative_strength,
                    theme_confidence=max(
                        0.0,
                        min(
                            1.0,
                            relative_strength.theme_confidence + memory_adjustment,
                        ),
                    ),
                )

        classification = self.classifier.classify(

            symbol=symbol,

            allocation=allocation,

            market_story=market_story,

            story_forecast=story_forecast,

            mode=mode,

            valid_story=valid_story,

            emergency_stop=emergency_stop,

            broker_available=broker_available,

            live_safety_ok=live_safety_ok,

            drawdown_pct=portfolio.drawdown_pct,

            target_pips=target_pips,

            setup_kind=setup_kind,

        )



        open_mult = _open_position_budget_multiplier(classification, portfolio)

        if open_mult < 0.999 and not classification.no_trade:

            self.classifier.record_scaled_allocation()


        exceptional_conviction = False
        if relative_strength is not None:
            exceptional_conviction = (
                abs(relative_strength.pair_strength) >= 7.0
                and relative_strength.theme_confidence >= 0.75
            )

        proposed_risk_pct = (
            classification.base_risk_pct if not classification.no_trade else 0.0
        )
        exposure_decision = self.exposure.evaluate_trade(
            portfolio=portfolio,
            symbol=symbol,
            side=side,
            proposed_risk_pct=proposed_risk_pct,
            pair_analysis=relative_strength,
            exceptional_conviction=exceptional_conviction,
        )
        adaptive_conviction = self.exposure.adaptive_conviction(
            symbol=symbol,
            side=side,
            pair_conviction=pair_conviction if pair_conviction is not None else 0.0,
            pair_analysis=relative_strength,
            exposure=exposure_decision,
            expected_r=expected_r,
        )


        ranked = self.allocator.evaluate(

            symbol=symbol,

            side=side,

            allocation=allocation,

            portfolio=portfolio,

            spread_pips=spread_pips,

            target_pips=target_pips,

            mode=mode,

            loss_streak=loss_streak,

            trace_id=trace_id,

            evaluation_moment=evaluation_moment,

            base_risk_pct=(

                classification.base_risk_pct if not classification.no_trade else 0.0

            ),

            classification=classification,

            open_position_multiplier=open_mult,

            exposure_decision=exposure_decision,

        )

        mult = ranked.capital.combined_multiplier

        allow = not classification.no_trade and exposure_decision.allow_trade

        self.allocator.maybe_write_reports()



        return PortfolioConstructionResult(

            ranked=ranked,

            classification=classification,

            portfolio_multiplier=mult,

            allow_trade=allow,

            watchlist=ranked.capital.watchlist,

            reason=f"{classification.reason}; {ranked.capital.reason}",

            currency_strength=strength_snapshot,

            relative_strength=relative_strength,

            exposure_decision=exposure_decision,

            adaptive_conviction=adaptive_conviction,

        )



    def apply_to_risk_decision(

        self,

        decision: RiskDecision,

        construction: PortfolioConstructionResult,

        *,

        default_risk_pct: float = 1.0,

    ) -> RiskDecision:

        """Scale lot size via classified risk × portfolio multipliers — min 0.01 lot floor."""

        if not decision.approved:

            return decision



        if construction.classification.no_trade:
            scaled = round(max(0.01, decision.lot_size * 0.10), 2)
            return RiskDecision(
                approved=True,
                reason=(
                    f"Portfolio SCOUT micro-allocation — {construction.classification.reason}; "
                    f"scaled to {scaled:.2f} lots"
                ),
                lot_size=max(0.01, scaled),
            )



        allocated = construction.ranked.capital.allocated_risk_pct
        if allocated <= 0.0:
            allocated = 0.01

        risk_ratio = allocated / max(default_risk_pct, 0.01)

        mult = max(0.05, min(1.0, risk_ratio))



        if construction.watchlist:

            mult = max(0.10, mult * 0.65)



        scaled = round(max(0.01, decision.lot_size * mult), 2)

        return RiskDecision(

            approved=True,

            reason=(

                f"{decision.reason}; portfolio {construction.classification.opportunity_class} "

                f"{mult:.0%} ({allocated:.2f}% risk)"

            ),

            lot_size=scaled,

        )



    def record_trade_result(

        self,

        *,

        symbol: str,

        mode: str,

        result: str,

        r_multiple: float,

        drawdown_pct: float,

        side: str | None = None,

        trade_theme: str | None = None,

    ) -> None:

        self.allocator.record_trade_result(

            symbol=symbol,

            mode=mode,

            result=result,

            r_multiple=r_multiple,

            drawdown_pct=drawdown_pct,

        )

        analysis = self.currency_strength.pair_analysis(symbol)
        resolved_theme = trade_theme or (
            analysis.trade_theme if analysis is not None else "unknown"
        )
        resolved_side = side or (
            analysis.preferred_side if analysis is not None else "buy"
        )
        if resolved_side in {"buy", "sell"}:
            self.theme_memory.record_trade(
                symbol=symbol,
                side=resolved_side,
                trade_theme=resolved_theme,
                r_multiple=r_multiple,
            )



    def write_doctrine_reports(self) -> tuple[Path, ...]:

        from portfolio.doctrine_reports import (

            write_allocation_vs_rejection_report,

            write_portfolio_allocation_doctrine_report,

        )



        paths: list[Path] = []

        classifier_path = self.classifier.write_classification_report()

        if classifier_path is not None:

            paths.append(classifier_path)

        counts = self.classifier.counts

        paths.append(

            write_portfolio_allocation_doctrine_report(

                self.project_root, classifier_counts=counts

            )

        )

        paths.append(

            write_allocation_vs_rejection_report(

                self.project_root,

                scaled_not_rejected=self.classifier.scaled_not_rejected,

                classifier_counts=counts,

                correlation_scaled=self.allocator.correlation.scaled_count,

                heat_scaled=self.allocator.heat_monitor.scaled_count,

                daily_loss_scaled=self.allocator.risk_budget.daily_scaled_count,

                total_allocated_risk_pct=self.allocator.capital_allocator.total_allocated_risk_pct,

            )

        )

        return tuple(paths)


