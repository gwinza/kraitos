"""Opportunity Allocation Score (OAS) — Edge × Diversification × Stability × Capacity."""



from __future__ import annotations



import math

from dataclasses import dataclass

from typing import TYPE_CHECKING



from risk.models import DEFAULT_CORRELATION_GROUPS, PortfolioState, TradeSide



if TYPE_CHECKING:

    from intelligence.harvest_archetype_memory import ArchetypeCheckResult

    from intelligence.harvest_opportunity_score import HarvestOpportunityScore

    from intelligence.opportunity_allocator import OpportunityAllocation

    from intelligence.strategy_marketplace import MarketplaceSelection

    from intelligence.trend_strength_engine import TrendStrengthResult

else:

    OpportunityAllocation = object  # runtime duck-typed





@dataclass(frozen=True)

class OpportunityAllocationScore:

    """Composite OAS with four normalized pillars (0–100 each)."""



    symbol: str

    oas: float

    edge: float

    diversification: float

    stability: float

    capacity: float

    tier: str

    risk_multiplier: float

    allow_trade: bool

    reason: str



    def to_dict(self) -> dict:

        return {

            "symbol": self.symbol,

            "oas": round(self.oas, 2),

            "edge": round(self.edge, 2),

            "diversification": round(self.diversification, 2),

            "stability": round(self.stability, 2),

            "capacity": round(self.capacity, 2),

            "tier": self.tier,

            "risk_multiplier": round(self.risk_multiplier, 3),

            "allow_trade": self.allow_trade,

            "reason": self.reason,

        }





def _tier_for_oas(oas: float) -> tuple[str, float, bool]:

    """Map OAS to tier and sizing multiplier — watchlist defers, never denies."""

    if oas < 50.0:

        return "defer", 0.15, True

    if oas < 65.0:

        return "watchlist", 0.25, True

    if oas < 75.0:

        return "reduced", 0.50, True

    if oas < 85.0:

        return "standard", 0.75, True

    return "premium", 1.0, True





def _geometric_mean(*values: float) -> float:

    clamped = [max(0.01, min(100.0, v)) for v in values]

    product = 1.0

    for v in clamped:

        product *= v

    return product ** (1.0 / len(clamped))





class OpportunityScoreEngine:

    """Compute OAS from intelligence outputs and portfolio context."""



    def __init__(self) -> None:

        self._latest: dict[str, OpportunityAllocationScore] = {}



    def score(

        self,

        *,

        symbol: str,

        allocation: OpportunityAllocation,

        portfolio: PortfolioState,

        side: TradeSide | None = None,

        spread_pips: float = 1.0,

        target_pips: float = 10.0,

        rolling_pf: float | None = None,

        rolling_avg_r: float | None = None,

        loss_streak: int = 0,

        mode: str = "harvest",

    ) -> OpportunityAllocationScore:

        edge = self._edge_score(allocation)

        diversification = self._diversification_score(

            symbol=symbol,

            portfolio=portfolio,

            side=side,

            allocation=allocation,

            mode=mode,

        )

        stability = self._stability_score(

            portfolio=portfolio,

            rolling_pf=rolling_pf,

            rolling_avg_r=rolling_avg_r,

            loss_streak=loss_streak,

            archetype=allocation.archetype_check,

        )

        capacity = self._capacity_score(

            allocation=allocation,

            spread_pips=spread_pips,

            target_pips=target_pips,

        )



        oas = _geometric_mean(edge, diversification, stability, capacity)

        tier, risk_mult, allow = _tier_for_oas(oas)



        result = OpportunityAllocationScore(

            symbol=symbol,

            oas=oas,

            edge=edge,

            diversification=diversification,

            stability=stability,

            capacity=capacity,

            tier=tier,

            risk_multiplier=risk_mult,

            allow_trade=allow,

            reason=f"OAS {oas:.0f} ({tier}) E={edge:.0f} D={diversification:.0f} "

            f"S={stability:.0f} C={capacity:.0f}",

        )

        self._latest[symbol] = result

        return result



    def latest(self, symbol: str) -> OpportunityAllocationScore | None:

        return self._latest.get(symbol.strip().upper())



    def all_scores(self) -> dict[str, OpportunityAllocationScore]:

        return dict(self._latest)



    @staticmethod

    def _edge_score(allocation: OpportunityAllocation) -> float:

        components: list[float] = []



        trend: TrendStrengthResult = allocation.trend_strength

        components.append(min(100.0, trend.score))



        market: MarketplaceSelection = allocation.marketplace

        components.append(min(100.0, market.fitness_score * 100.0))



        harvest: HarvestOpportunityScore | None = allocation.harvest_score

        if harvest is not None:

            components.append(min(100.0, harvest.score))



        council = getattr(allocation, "council_consensus", None)

        if council is not None:

            components.append(min(100.0, council.consensus_confidence))



        forecast = getattr(allocation, "narrative_forecast", None)

        if forecast is not None:

            components.append(min(100.0, forecast.confidence))



        archetype: ArchetypeCheckResult | None = allocation.archetype_check

        if archetype is not None:

            fitness = 70.0 if archetype.allowed else 35.0

            fitness += (archetype.risk_multiplier - 0.5) * 40.0

            components.append(min(100.0, max(0.0, fitness)))



        if allocation.harvest_boost:

            components.append(90.0)



        maximiser = allocation.maximiser

        if maximiser.allow_primary_entry:

            components.append(75.0 + maximiser.risk_multiplier * 25.0)



        if not components:

            return 50.0

        return sum(components) / len(components)



    @staticmethod

    def _diversification_score(

        *,

        symbol: str,

        portfolio: PortfolioState,

        side: TradeSide | None,

        allocation: OpportunityAllocation,

        mode: str,

    ) -> float:

        normalized = symbol.strip().upper()

        open_positions = portfolio.open_positions

        score = 100.0



        same_symbol = sum(1 for p in open_positions if p.symbol == normalized)

        score -= same_symbol * 20.0



        if side is not None:

            same_dir = sum(

                1 for p in open_positions

                if p.symbol == normalized and p.side == side

            )

            score -= same_dir * 15.0



        cluster_members: set[str] = set()

        for members in DEFAULT_CORRELATION_GROUPS.values():

            if normalized in members:

                cluster_members = set(members)

                break

        if cluster_members:

            cluster_open = sum(

                1 for p in open_positions if p.symbol in cluster_members

            )

            score -= cluster_open * 12.0



        strategy = allocation.marketplace.strategy

        same_strategy = sum(

            1 for p in open_positions

            if getattr(p, "mode", mode) == mode

        )

        score -= min(30.0, same_strategy * 8.0)



        currencies = {normalized[:3], normalized[3:6]}

        currency_exposure: dict[str, int] = {}

        for pos in open_positions:

            for c in {pos.symbol[:3], pos.symbol[3:6]}:

                currency_exposure[c] = currency_exposure.get(c, 0) + 1

        for c in currencies:

            score -= currency_exposure.get(c, 0) * 5.0



        return max(0.0, min(100.0, score))



    @staticmethod

    def _stability_score(

        *,

        portfolio: PortfolioState,

        rolling_pf: float | None,

        rolling_avg_r: float | None,

        loss_streak: int,

        archetype: ArchetypeCheckResult | None,

    ) -> float:

        score = 80.0



        if rolling_pf is not None:

            if rolling_pf >= 2.0:

                score += 10.0

            elif rolling_pf >= 1.5:

                score += 5.0

            elif rolling_pf < 1.0:

                score -= 20.0



        if rolling_avg_r is not None:

            if rolling_avg_r >= 0.15:

                score += 10.0

            elif rolling_avg_r >= 0.05:

                score += 5.0

            elif rolling_avg_r < 0.0:

                score -= 15.0



        score -= loss_streak * 8.0



        if archetype is not None and not archetype.allowed:

            score -= 25.0



        return max(0.0, min(100.0, score))



    @staticmethod

    def _capacity_score(

        *,

        allocation: OpportunityAllocation,

        spread_pips: float,

        target_pips: float,

    ) -> float:

        score = 70.0

        spread_ratio = spread_pips / max(target_pips, 0.1)

        if spread_ratio <= 0.15:

            score += 20.0

        elif spread_ratio <= 0.25:

            score += 10.0

        elif spread_ratio >= 0.40:

            score -= 25.0

        elif spread_ratio >= 0.30:

            score -= 15.0



        harvest = allocation.harvest_score

        if harvest is not None:

            session = harvest.session

            if session in {"london", "london_ny_overlap", "new_york"}:

                score += 10.0

            elif session == "asia":

                score -= 5.0



        pip_target = allocation.dynamic_pip_target

        if pip_target is not None:

            if pip_target.skip_trade:

                score -= 30.0

            elif pip_target.target_pips >= 8.0:

                score += 5.0



        trend = allocation.trend_strength

        if trend.quality == "institutional_trend":

            score += 10.0

        elif trend.quality == "range_or_noise":

            score -= 10.0



        return max(0.0, min(100.0, score))


