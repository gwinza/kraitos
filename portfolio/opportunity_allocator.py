"""Portfolio opportunity allocator — rank setups by OAS, don't starve."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from typing import TYPE_CHECKING

from portfolio.capital_allocator import CapitalAllocation, CapitalAllocator
from portfolio.capital_rotation import CapitalRotationEngine
from portfolio.correlation_allocator import CorrelationAllocator
from portfolio.opportunity_classifier import OpportunityClassification
from portfolio.opportunity_score import OpportunityAllocationScore, OpportunityScoreEngine
from portfolio.opportunity_watchlist import OpportunityWatchlist
from portfolio.portfolio_heat import PortfolioHeatMonitor
from portfolio.risk_budget import RiskBudgetAllocator
from risk.models import PortfolioState, TradeSide

if TYPE_CHECKING:
    from intelligence.opportunity_allocator import OpportunityAllocation
    from portfolio.exposure_engine import ExposureDecision

REPORT_MIN_INTERVAL_SEC = 120.0


@dataclass(frozen=True)
class RankedOpportunity:
    """One ranked opportunity with full portfolio context."""

    symbol: str
    side: TradeSide
    oas: OpportunityAllocationScore
    capital: CapitalAllocation
    rank: int
    intelligence: OpportunityAllocation | None = None

    def to_dict(self) -> dict:
        payload = {
            "symbol": self.symbol,
            "side": self.side,
            "rank": self.rank,
            "oas": self.oas.to_dict(),
            "capital": self.capital.to_dict(),
        }
        if self.intelligence is not None:
            payload["intelligence"] = self.intelligence.to_dict()
        return payload


class PortfolioOpportunityAllocator:
    """Rank and allocate capital across scanned opportunities."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.score_engine = OpportunityScoreEngine()
        self.risk_budget = RiskBudgetAllocator(project_root)
        self.correlation = CorrelationAllocator(project_root)
        self.heat_monitor = PortfolioHeatMonitor(project_root)
        self.rotation = CapitalRotationEngine(project_root=project_root)
        self.watchlist = OpportunityWatchlist(project_root)
        self.capital_allocator = CapitalAllocator(
            self.risk_budget,
            self.correlation,
            self.heat_monitor,
            self.rotation,
        )
        self._ranked: list[RankedOpportunity] = []
        self._symbol_pf: dict[str, float] = {}
        self._last_report_write: float = 0.0

    def set_symbol_pf(self, symbol_pf: dict[str, float]) -> None:
        self._symbol_pf = dict(symbol_pf)
        self.correlation.set_symbol_pf(symbol_pf)

    def evaluate(
        self,
        *,
        symbol: str,
        side: TradeSide,
        allocation: OpportunityAllocation,
        portfolio: PortfolioState,
        spread_pips: float = 1.0,
        target_pips: float = 10.0,
        mode: str = "harvest",
        loss_streak: int = 0,
        trace_id: str = "",
        evaluation_moment: datetime | None = None,
        base_risk_pct: float = 1.0,
        classification: OpportunityClassification | None = None,
        open_position_multiplier: float = 1.0,
        exposure_decision: "ExposureDecision | None" = None,
    ) -> RankedOpportunity:
        rolling_pf = self._symbol_pf.get(symbol.strip().upper())
        oas = self.score_engine.score(
            symbol=symbol,
            allocation=allocation,
            portfolio=portfolio,
            side=side,
            spread_pips=spread_pips,
            target_pips=target_pips,
            rolling_pf=rolling_pf,
            loss_streak=loss_streak,
            mode=mode,
        )
        capital = self.capital_allocator.allocate(
            oas=oas,
            portfolio=portfolio,
            side=side,
            mode=mode,
            base_risk_pct=base_risk_pct,
            classification=classification,
            open_position_multiplier=open_position_multiplier,
            exposure_decision=exposure_decision,
        )

        if capital.watchlist:
            state = self.watchlist.classify_deferral(
                heat_over_limit=capital.risk_budget_multiplier < 0.3,
                correlation_blocked=capital.correlation_multiplier < 0.5,
                spread_too_wide=oas.capacity < 40.0,
                needs_confirmation=oas.edge < 60.0,
            )
            self.watchlist.add(
                symbol=symbol,
                side=side,
                oas=oas,
                state=state,
                reason=capital.reason,
                trace_id=trace_id,
                evaluation_moment=evaluation_moment,
            )
        elif capital.allow_trade:
            self.watchlist.promote(symbol, side, evaluation_moment=evaluation_moment)

        self.watchlist.expire_stale(evaluation_moment)

        ranked = RankedOpportunity(
            symbol=symbol.strip().upper(),
            side=side,
            oas=oas,
            capital=capital,
            rank=0,
            intelligence=allocation,
        )
        self._update_rankings(ranked)
        return ranked

    def rank_all(self, opportunities: list[RankedOpportunity]) -> list[RankedOpportunity]:
        """Sort opportunities by OAS × combined multiplier descending."""
        sorted_opps = sorted(
            opportunities,
            key=lambda o: o.oas.oas * o.capital.combined_multiplier,
            reverse=True,
        )
        ranked = []
        for i, opp in enumerate(sorted_opps, start=1):
            ranked.append(
                RankedOpportunity(
                    symbol=opp.symbol,
                    side=opp.side,
                    oas=opp.oas,
                    capital=opp.capital,
                    rank=i,
                    intelligence=opp.intelligence,
                )
            )
        self._ranked = ranked
        return ranked

    def _update_rankings(self, new: RankedOpportunity) -> None:
        existing = [o for o in self._ranked if o.symbol != new.symbol]
        existing.append(new)
        self.rank_all(existing)

    @property
    def rankings(self) -> list[RankedOpportunity]:
        return list(self._ranked)

    def record_trade_result(
        self,
        *,
        symbol: str,
        mode: str,
        result: str,
        r_multiple: float,
        drawdown_pct: float,
    ) -> None:
        self.rotation.record_trade(
            symbol=symbol,
            mode=mode,
            result=result,
            r_multiple=r_multiple,
            drawdown_pct=drawdown_pct,
        )

    def maybe_write_reports(self, *, force: bool = False) -> tuple[Path, ...] | None:
        now = time.monotonic()
        if not force and (now - self._last_report_write) < REPORT_MIN_INTERVAL_SEC:
            return None
        self._last_report_write = now
        return self.write_reports()

    def write_reports(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        logs = self.project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()

        alloc_path = logs / "portfolio_allocation_report.md"
        lines = [
            "# Portfolio Allocation Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Rank | Symbol | Side | OAS | Tier | Combined | Alloc % | Trade | Watch |",
            "|------|--------|------|-----|------|----------|---------|-------|-------|",
        ]
        for opp in self._ranked:
            c = opp.capital
            lines.append(
                f"| {opp.rank} | {opp.symbol} | {opp.side} | {opp.oas.oas:.0f} | "
                f"{opp.oas.tier} | {c.combined_multiplier:.0%} | "
                f"{c.allocated_risk_pct:.2f}% | {'Y' if c.allow_trade else 'N'} | "
                f"{'Y' if c.watchlist else 'N'} |"
            )
        alloc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append(alloc_path)

        for writer in (
            self.risk_budget.write_report,
            self.correlation.write_report,
            self.watchlist.write_report,
            self.heat_monitor.write_report,
            self.rotation.write_report,
        ):
            p = writer()
            if p is not None:
                paths.append(p)

        return tuple(paths)
