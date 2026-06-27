"""Risk evaluation layer for the integrated pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config.settings import KraitosConfig
from core.helpers import pip_size_for_symbol, pip_value_per_lot
from core.portfolio import build_portfolio_state
from execution.paper_trader import PaperTrader
from controls.drawdown_risk import DrawdownRiskController
from controls.strategy_quality_gate import StrategyQualityGate
from typing import TYPE_CHECKING

from risk.models import PortfolioState, RiskDecision, TradeRequest, TradeSide

if TYPE_CHECKING:
    from portfolio.portfolio_construction import PortfolioConstructionEngine, PortfolioConstructionResult
from risk.risk_manager import RiskManager


def catastrophic_gate(
    *,
    portfolio: PortfolioState,
    emergency_stop: bool = False,
    live_safety_ok: bool = True,
    broker_available: bool = True,
    valid_story: bool = True,
) -> str | None:
    """Return block reason only for catastrophic safety violations."""
    if emergency_stop:
        return "Emergency stop active"
    if not live_safety_ok:
        return "Live safety violated"
    if not broker_available:
        return "Broker unavailable"
    if not valid_story:
        return "TraderBrain — no valid story"
    dd_block = RiskManager.catastrophic_gate(portfolio)
    if dd_block is not None:
        return dd_block
    return None


@dataclass(frozen=True)
class RiskEvaluation:
    """Risk inputs and outcome for one symbol."""

    portfolio: PortfolioState
    decision: RiskDecision
    pip_size: float


class RiskController:
    """Apply portfolio-aware risk rules before any simulated execution."""

    def __init__(
        self,
        *,
        config: KraitosConfig,
        risk_manager: RiskManager,
        paper_trader: PaperTrader,
        project_root: Path,
        broker_balance: float | None = None,
        connector: object | None = None,
        portfolio_builder: Callable[[], PortfolioState] | None = None,
        strategy_quality_gate: StrategyQualityGate | None = None,
        drawdown_risk: DrawdownRiskController | None = None,
        portfolio_engine: "PortfolioConstructionEngine | None" = None,
    ) -> None:
        self._config = config
        self._risk_manager = risk_manager
        self._paper_trader = paper_trader
        self._project_root = project_root
        self._broker_balance = broker_balance
        self._connector = connector
        self._portfolio_builder = portfolio_builder
        self._strategy_quality_gate = strategy_quality_gate
        self._drawdown_risk = drawdown_risk or DrawdownRiskController()
        self._portfolio_engine = portfolio_engine
        if self._portfolio_engine is not None:
            self._drawdown_risk.portfolio_scaling_mode = True

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk_manager

    def set_portfolio_builder(
        self,
        portfolio_builder: Callable[[], PortfolioState] | None,
    ) -> None:
        """Override portfolio snapshots (used by backtest validation)."""
        self._portfolio_builder = portfolio_builder

    def set_strategy_quality_gate(self, gate: StrategyQualityGate | None) -> None:
        """Attach adaptive risk / symbol filters from validation analysis."""
        self._strategy_quality_gate = gate

    @property
    def strategy_quality_gate(self) -> StrategyQualityGate | None:
        return self._strategy_quality_gate

    @property
    def drawdown_risk(self) -> DrawdownRiskController:
        return self._drawdown_risk

    @property
    def portfolio_engine(self) -> "PortfolioConstructionEngine | None":
        return self._portfolio_engine

    def set_portfolio_engine(self, engine: "PortfolioConstructionEngine | None") -> None:
        """Attach portfolio construction layer."""
        self._portfolio_engine = engine
        self._drawdown_risk.portfolio_scaling_mode = engine is not None

    def portfolio_snapshot(self) -> PortfolioState:
        """Return current portfolio state for adaptive allocation."""
        if self._portfolio_builder is not None:
            return self._portfolio_builder()
        return build_portfolio_state(
            config=self._config,
            paper_trader=self._paper_trader,
            risk_manager=self._risk_manager,
            project_root=self._project_root,
            broker_balance=self._broker_balance,
            connector=self._connector,  # type: ignore[arg-type]
        )

    def evaluate(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        trace_id: str,
        mode: str = "harvest",
        trend_score: float | None = None,
        trend_quality: str | None = None,
        harvest_score_band: str | None = None,
        harvest_score: float | None = None,
        archetype_risk_multiplier: float | None = None,
        is_addon: bool = False,
        evaluation_moment: object | None = None,
        portfolio_construction: "PortfolioConstructionResult | None" = None,
        spread_pips: float = 1.0,
        target_pips: float = 10.0,
        forecast_confidence: float = 0.0,
        expected_r: float | None = None,
    ) -> RiskEvaluation:
        """Run risk checks and return lot size approval."""
        if self._portfolio_builder is not None:
            portfolio = self._portfolio_builder()
        else:
            portfolio = build_portfolio_state(
                config=self._config,
                paper_trader=self._paper_trader,
                risk_manager=self._risk_manager,
                project_root=self._project_root,
                broker_balance=self._broker_balance,
                connector=self._connector,  # type: ignore[arg-type]
            )
        pip_size = pip_size_for_symbol(symbol)
        pip_value = pip_value_per_lot(
            symbol,
            entry_price,
            contract_size=self._risk_manager.limits.contract_size,
        )
        request = TradeRequest(
            symbol=symbol,
            side=side,  # type: ignore[arg-type]
            entry_price=entry_price,
            stop_loss=stop_loss,
            pip_size=pip_size,
            pip_value_per_lot=pip_value,
        )
        decision = self._risk_manager.evaluate(
            request,
            portfolio,
            trace_id=trace_id,
            harvest_score=harvest_score,
        )
        decision = self._apply_drawdown_risk(
            decision,
            symbol=symbol,
            side=side,  # type: ignore[arg-type]
            mode=mode,
            portfolio=portfolio,
            trend_score=trend_score,
            trend_quality=trend_quality,
            is_addon=is_addon,
            evaluation_moment=evaluation_moment,
        )
        decision = self._apply_harvest_intelligence(
            decision,
            harvest_score_band=harvest_score_band,
            archetype_risk_multiplier=archetype_risk_multiplier,
        )
        decision = self._apply_strategy_quality(decision, symbol=symbol, portfolio=portfolio)
        decision = self._apply_portfolio_construction(
            decision,
            portfolio_construction=portfolio_construction,
        )
        decision = self._apply_r_aware_sizing(
            decision,
            spread_pips=spread_pips,
            target_pips=target_pips,
            stop_pips=abs(entry_price - stop_loss) / pip_size,
            forecast_confidence=forecast_confidence,
            expected_r=expected_r,
        )
        return RiskEvaluation(
            portfolio=portfolio,
            decision=decision,
            pip_size=pip_size,
        )

    def _apply_portfolio_construction(
        self,
        decision: RiskDecision,
        *,
        portfolio_construction: "PortfolioConstructionResult | None",
    ) -> RiskDecision:
        if portfolio_construction is None or self._portfolio_engine is None:
            return decision
        return self._portfolio_engine.apply_to_risk_decision(
            decision,
            portfolio_construction,
            default_risk_pct=float(self._config.risk.per_trade_pct),
        )

    def _apply_drawdown_risk(
        self,
        decision: RiskDecision,
        *,
        symbol: str,
        side: TradeSide,
        mode: str,
        portfolio: PortfolioState,
        trend_score: float | None,
        trend_quality: str | None,
        is_addon: bool,
        evaluation_moment: object | None,
    ) -> RiskDecision:
        if not decision.approved:
            return decision

        allowed, reason, multiplier = self._drawdown_risk.evaluate_entry(
            symbol=symbol,
            side=side,
            mode=mode,
            portfolio=portfolio,
            trend_score=trend_score,
            trend_quality=trend_quality,
            is_addon=is_addon,
            evaluation_moment=evaluation_moment,  # type: ignore[arg-type]
        )
        if not allowed:
            return RiskDecision(approved=False, reason=reason, lot_size=0.0)

        min_lot = self._risk_manager.limits.min_lot_size
        if multiplier >= 0.999:
            if reason and reason != "Trade approved":
                return RiskDecision(
                    approved=True,
                    reason=f"{decision.reason}; {reason}",
                    lot_size=max(min_lot, decision.lot_size),
                )
            return decision

        scaled = round(max(min_lot, decision.lot_size * multiplier), 2)
        return RiskDecision(
            approved=True,
            reason=f"{decision.reason} ({reason})",
            lot_size=scaled,
        )

    def _apply_harvest_intelligence(
        self,
        decision: RiskDecision,
        *,
        harvest_score_band: str | None,
        archetype_risk_multiplier: float | None,
    ) -> RiskDecision:
        if not decision.approved:
            return decision
        multiplier = 1.0
        if harvest_score_band == "conditional":
            multiplier = min(multiplier, 0.8)
        elif harvest_score_band == "no_harvest":
            multiplier = min(multiplier, 0.65)
        if archetype_risk_multiplier is not None:
            multiplier = min(multiplier, archetype_risk_multiplier)
        if multiplier >= 0.999:
            return decision
        min_lot = self._risk_manager.limits.min_lot_size
        scaled = round(max(min_lot, decision.lot_size * multiplier), 2)
        return RiskDecision(
            approved=True,
            reason=f"{decision.reason} (harvest intel {multiplier:.0%})",
            lot_size=scaled,
        )

    def _apply_r_aware_sizing(
        self,
        decision: RiskDecision,
        *,
        spread_pips: float,
        target_pips: float,
        stop_pips: float,
        forecast_confidence: float,
        expected_r: float | None,
    ) -> RiskDecision:
        """Spread-aware sizing — reduce weak R setups, boost high-confidence narratives."""
        if not decision.approved or decision.lot_size <= 0:
            return decision

        net_target = max(0.5, target_pips - spread_pips)
        stop_eff = max(1.0, stop_pips)
        r_after_cost = expected_r if expected_r is not None else net_target / stop_eff

        multiplier = 1.0
        if r_after_cost < 0.08:
            multiplier = max(0.55, r_after_cost / 0.08)
        elif r_after_cost > 0.20 and forecast_confidence >= 70.0:
            multiplier = min(1.12, 1.0 + (r_after_cost - 0.20) * 0.35)

        if 0.999 <= multiplier <= 1.001:
            return decision

        min_lot = 0.01
        risk_manager = getattr(self, "_risk_manager", None)
        if risk_manager is not None:
            min_lot = risk_manager.limits.min_lot_size
        scaled = round(max(min_lot, decision.lot_size * multiplier), 2)
        if scaled == decision.lot_size and multiplier > 1.0:
            scaled = round(decision.lot_size + 0.01, 2)
        return RiskDecision(
            approved=True,
            reason=f"{decision.reason} (R-aware {multiplier:.0%}, expR {r_after_cost:.2f})",
            lot_size=scaled,
        )

    def _apply_strategy_quality(
        self,
        decision: RiskDecision,
        *,
        symbol: str,
        portfolio: PortfolioState,
    ) -> RiskDecision:
        gate = self._strategy_quality_gate
        if gate is None or not gate.enabled or not decision.approved:
            return decision

        multiplier = gate.risk_multiplier(symbol)
        if multiplier <= 0:
            multiplier = 0.15

        allowed, reason = gate.symbol_allowed(symbol)
        if not allowed:
            multiplier = min(multiplier, 0.15)

        if multiplier >= 0.999:
            if not allowed:
                min_lot = self._risk_manager.limits.min_lot_size
                scaled = round(max(min_lot, decision.lot_size * 0.15), 2)
                return RiskDecision(
                    approved=True,
                    reason=f"{decision.reason} ({reason}; adaptive micro 15%)",
                    lot_size=scaled,
                )
            return decision

        min_lot = self._risk_manager.limits.min_lot_size
        scaled = round(max(min_lot, decision.lot_size * multiplier), 2)
        note = f"adaptive risk {multiplier:.0%}"
        if not allowed:
            note = f"{reason}; {note}"
        return RiskDecision(
            approved=True,
            reason=f"{decision.reason} ({note})",
            lot_size=scaled,
        )
