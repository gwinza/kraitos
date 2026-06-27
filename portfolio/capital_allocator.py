"""Capital allocator — combine OAS, risk budget, correlation, heat, rotation."""



from __future__ import annotations



from dataclasses import dataclass



from portfolio.capital_rotation import CapitalRotationEngine

from portfolio.correlation_allocator import CorrelationAllocator, CorrelationScale
from portfolio.exposure_engine import ExposureDecision

from portfolio.opportunity_classifier import OpportunityClassification

from portfolio.opportunity_score import OpportunityAllocationScore

from portfolio.portfolio_heat import HeatAssessment, PortfolioHeatMonitor

from portfolio.risk_budget import RiskBudgetAllocator, RiskBudgetDecision

from risk.models import PortfolioState, TradeSide





@dataclass(frozen=True)

class CapitalAllocation:

    """Final capital allocation for one trade."""



    symbol: str

    side: TradeSide

    oas: float

    oas_multiplier: float

    risk_budget_multiplier: float

    correlation_multiplier: float

    heat_multiplier: float

    rotation_multiplier: float

    open_position_multiplier: float

    exposure_multiplier: float

    combined_multiplier: float

    allocated_risk_pct: float

    allow_trade: bool

    watchlist: bool

    reason: str



    def to_dict(self) -> dict:

        return {

            "symbol": self.symbol,

            "side": self.side,

            "oas": round(self.oas, 2),

            "oas_multiplier": round(self.oas_multiplier, 3),

            "risk_budget_multiplier": round(self.risk_budget_multiplier, 3),

            "correlation_multiplier": round(self.correlation_multiplier, 3),

            "heat_multiplier": round(self.heat_multiplier, 3),

            "rotation_multiplier": round(self.rotation_multiplier, 3),

            "open_position_multiplier": round(self.open_position_multiplier, 3),

            "exposure_multiplier": round(self.exposure_multiplier, 3),

            "combined_multiplier": round(self.combined_multiplier, 3),

            "allocated_risk_pct": round(self.allocated_risk_pct, 3),

            "allow_trade": self.allow_trade,

            "watchlist": self.watchlist,

            "reason": self.reason,

        }





class CapitalAllocator:

    """Merge all portfolio scaling factors into one allocation."""



    WATCHLIST_THRESHOLD = 0.15

    MIN_ALLOCATED_RISK_PCT = 0.01



    def __init__(

        self,

        risk_budget: RiskBudgetAllocator,

        correlation: CorrelationAllocator,

        heat_monitor: PortfolioHeatMonitor,

        rotation: CapitalRotationEngine,

    ) -> None:

        self._risk_budget = risk_budget

        self._correlation = correlation

        self._heat = heat_monitor

        self._rotation = rotation

        self._latest: dict[str, CapitalAllocation] = {}

        self._total_allocated_risk_pct = 0.0



    @property

    def total_allocated_risk_pct(self) -> float:

        return self._total_allocated_risk_pct



    def allocate(

        self,

        *,

        oas: OpportunityAllocationScore,

        portfolio: PortfolioState,

        side: TradeSide,

        mode: str = "harvest",

        base_risk_pct: float = 1.0,

        classification: OpportunityClassification | None = None,

        open_position_multiplier: float = 1.0,

        exposure_decision: ExposureDecision | None = None,

    ) -> CapitalAllocation:

        if classification is not None and classification.no_trade:

            result = CapitalAllocation(

                symbol=oas.symbol,

                side=side,

                oas=oas.oas,

                oas_multiplier=oas.risk_multiplier,

                risk_budget_multiplier=0.0,

                correlation_multiplier=0.0,

                heat_multiplier=0.0,

                rotation_multiplier=0.0,

                open_position_multiplier=0.0,

                exposure_multiplier=0.0,

                combined_multiplier=0.0,

                allocated_risk_pct=0.0,

                allow_trade=False,

                watchlist=False,

                reason=classification.reason,

            )

            self._latest[oas.symbol] = result

            return result



        heat = self._heat.assess(portfolio)

        budget: RiskBudgetDecision = self._risk_budget.allocate(

            oas=oas,

            portfolio=portfolio,

            base_risk_pct=base_risk_pct,

        )

        corr: CorrelationScale = self._correlation.scale(

            symbol=oas.symbol,

            side=side,

            portfolio=portfolio,

        )

        rotation_mult = self._rotation.risk_multiplier(oas.symbol, mode)

        exposure_mult = (
            exposure_decision.scale_multiplier
            if exposure_decision is not None and exposure_decision.allow_trade
            else (0.0 if exposure_decision is not None else 1.0)
        )



        combined = (

            budget.combined_multiplier

            * corr.scale_multiplier

            * heat.scale_multiplier

            * rotation_mult

            * open_position_multiplier

            * exposure_mult

        )

        allow = exposure_decision is None or exposure_decision.allow_trade
        combined = max(0.05, min(1.0, combined)) if allow else 0.0



        watchlist = (

            oas.tier in {"watchlist", "defer"}

            or combined < self.WATCHLIST_THRESHOLD

            or budget.heat_zone == "over_limit"

        )



        allocated = max(self.MIN_ALLOCATED_RISK_PCT, base_risk_pct * combined)

        reasons = [

            budget.reason,

            corr.reason,

            f"Heat {heat.band} {heat.scale_multiplier:.0%}",

            f"Rotation {rotation_mult:.0%}",

            f"Open-pos budget {open_position_multiplier:.0%}",

            f"Currency exposure {exposure_mult:.0%}",

        ]
        if exposure_decision is not None:
            reasons.append(exposure_decision.reason)



        result = CapitalAllocation(

            symbol=oas.symbol,

            side=side,

            oas=oas.oas,

            oas_multiplier=oas.risk_multiplier,

            risk_budget_multiplier=budget.combined_multiplier,

            correlation_multiplier=corr.scale_multiplier,

            heat_multiplier=heat.scale_multiplier,

            rotation_multiplier=rotation_mult,

            open_position_multiplier=open_position_multiplier,

            exposure_multiplier=exposure_mult,

            combined_multiplier=combined,

            allocated_risk_pct=allocated,

            allow_trade=allow,

            watchlist=watchlist and allow,

            reason="; ".join(reasons),

        )

        self._latest[oas.symbol] = result

        if allow:

            self._total_allocated_risk_pct += allocated

        return result



    def latest(self, symbol: str) -> CapitalAllocation | None:

        return self._latest.get(symbol.strip().upper())


