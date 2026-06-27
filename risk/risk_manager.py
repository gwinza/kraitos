"""

Risk manager for Kraitos.



Evaluates every trade before execution and returns an approval decision with

calculated lot size. Delegates sizing to AllocationFirewallEngine — scale, don't deny.

"""



from __future__ import annotations



import math



from loguru import logger



from config.settings import KraitosConfig

from logs.event_logger import KraitosEventLogger

from risk.allocation_firewall import (

    ALLOCATION_FIREWALL_DNA,

    AllocationFirewallConfig,

    AllocationFirewallEngine,

    AllocationOpportunity,

)

from risk.models import (

    DEFAULT_CORRELATION_GROUPS,

    OpenPosition,

    PortfolioState,

    RiskDecision,

    RiskLimits,

    TradeRequest,

)



PIP_SIZE_BY_SYMBOL: dict[str, float] = {

    "USDJPY": 0.01,

    "EURJPY": 0.01,

    "GBPJPY": 0.01,

    "AUDJPY": 0.01,

    "NZDJPY": 0.01,

    "CHFJPY": 0.01,

    "XAUUSD": 0.01,

}





class RiskManager:

    """Size trades via allocation firewall — maximise participation, control exposure."""



    def __init__(

        self,

        limits: RiskLimits,

        correlation_groups: dict[str, tuple[str, ...]] | None = None,

        event_logger: KraitosEventLogger | None = None,

        allocation_firewall: AllocationFirewallEngine | None = None,

    ) -> None:

        self.limits = limits

        self.correlation_groups = correlation_groups or DEFAULT_CORRELATION_GROUPS

        self._event_logger = event_logger

        self._firewall = allocation_firewall or AllocationFirewallEngine(

            config=AllocationFirewallConfig(

                minimum_risk_percent=0.05,

                max_daily_loss_pct=limits.max_daily_loss_pct,

                max_risk_per_symbol_pct=limits.max_risk_per_symbol_pct,

                max_correlated_exposure_pct=limits.max_correlated_exposure_pct,

            ),

            correlation_groups=self.correlation_groups,

        )



    @classmethod

    def from_config(cls, config: KraitosConfig) -> RiskManager:

        """Build a risk manager from validated Kraitos configuration."""

        limits = RiskLimits(

            per_trade_pct=config.risk.per_trade_pct,

            max_daily_loss_pct=config.risk.max_daily_drawdown_pct,

            max_open_trades=config.risk.max_open_trades,

            max_risk_per_symbol_pct=config.risk.max_risk_per_symbol_pct,

            max_correlated_exposure_pct=config.risk.max_correlated_exposure_pct,

        )

        return cls(limits)



    @property

    def allocation_firewall(self) -> AllocationFirewallEngine:

        return self._firewall



    def evaluate(

        self,

        request: TradeRequest,

        portfolio: PortfolioState,

        *,

        trace_id: str | None = None,

        harvest_score: float | None = None,

        margin_utilization_pct: float | None = None,

    ) -> RiskDecision:

        """

        Evaluate a trade request and return sized allocation.



        Returns:

            RiskDecision with approved, reason, and calculated lot_size.

        """

        symbol = self._normalize_symbol(request.symbol)

        pip_size = request.pip_size or self._pip_size_for_symbol(symbol)

        pip_value = request.pip_value_per_lot or self._pip_value_per_lot(

            pip_size,

            entry_price=request.entry_price,

            symbol=symbol,

        )



        trace = trace_id or (

            self._event_logger.new_trace_id() if self._event_logger is not None else None

        )



        validation_error = self._validate_request(request, portfolio, pip_size)

        if validation_error:

            decision = RiskDecision(approved=False, reason=validation_error, lot_size=0.0)

            self._log_risk_decision(request.symbol, trace, decision)

            return decision



        base_lot = self.calculate_lot_size(

            balance=portfolio.balance,

            risk_pct=self.limits.per_trade_pct,

            entry_price=request.entry_price,

            stop_loss=request.stop_loss,

            pip_size=pip_size,

            pip_value_per_lot=pip_value,

        )

        if base_lot <= 0:

            base_lot = self.limits.min_lot_size



        trade_risk = self._risk_amount_for_trade(

            volume=base_lot,

            entry_price=request.entry_price,

            stop_loss=request.stop_loss,

            pip_size=pip_size,

            pip_value_per_lot=pip_value,

        )



        opportunity = AllocationOpportunity(

            symbol=symbol,

            side=request.side,

            base_risk_percent=self.limits.per_trade_pct,

            harvest_score=harvest_score,

            estimated_trade_risk=trade_risk,

            margin_utilization_pct=margin_utilization_pct,

        )

        allocation = self._firewall.determine_allocation(opportunity, portfolio)



        if not allocation.execute:

            decision = RiskDecision(

                approved=False,

                reason=allocation.explanation,

                lot_size=0.0,

            )

            self._log_risk_decision(symbol, trace, decision)

            return decision



        scaled_lot = self.calculate_lot_size(

            balance=portfolio.balance,

            risk_pct=allocation.risk_percent,

            entry_price=request.entry_price,

            stop_loss=request.stop_loss,

            pip_size=pip_size,

            pip_value_per_lot=pip_value,

        )

        if scaled_lot <= 0:

            scaled_lot = self.limits.min_lot_size

        scaled_lot = max(self.limits.min_lot_size, min(scaled_lot, self.limits.max_lot_size))

        scaled_lot = self._round_lot_size(scaled_lot)

        scaled_lot, cap_note = self._cap_lot_to_exposure_limits(
            scaled_lot,
            symbol=symbol,
            request=request,
            portfolio=portfolio,
            pip_size=pip_size,
            pip_value_per_lot=pip_value,
        )

        if scaled_lot < self.limits.min_lot_size:
            min_lot_risk = self._risk_amount_for_trade(
                volume=self.limits.min_lot_size,
                entry_price=request.entry_price,
                stop_loss=request.stop_loss,
                pip_size=pip_size,
                pip_value_per_lot=pip_value,
            )
            danger = self._exposure_dangerously_high(
                symbol=symbol,
                portfolio=portfolio,
                additional_risk=min_lot_risk,
            )
            if danger:
                decision = RiskDecision(
                    approved=False,
                    reason=(
                        f"Exposure limit — even minimum lot exceeds safe symbol budget "
                        f"({danger})"
                    ),
                    lot_size=0.0,
                )
                self._log_risk_decision(symbol, trace, decision)
                return decision
            scaled_lot = self.limits.min_lot_size

        trade_risk_scaled = self._risk_amount_for_trade(

            volume=scaled_lot,

            entry_price=request.entry_price,

            stop_loss=request.stop_loss,

            pip_size=pip_size,

            pip_value_per_lot=pip_value,

        )



        reason = f"Allocation approved: {allocation.explanation}"
        if cap_note:
            reason = f"{reason} {cap_note}"

        logger.info(

            f"Trade approved: {symbol} {request.side} "

            f"lot_size={scaled_lot:.2f} risk=${trade_risk_scaled:,.2f} "

            f"(allocation {allocation.allocation_multiplier:.0%}, "

            f"risk {allocation.risk_percent:.2f}%)"

        )

        result = RiskDecision(

            approved=True,

            reason=reason,

            lot_size=scaled_lot,

        )

        self._log_risk_decision(symbol, trace, result, trade_risk=trade_risk_scaled)

        return result



    @staticmethod

    def catastrophic_gate(portfolio: PortfolioState) -> str | None:

        """Block only at catastrophic portfolio drawdown (≥50%)."""

        if portfolio.drawdown_pct >= 50.0:

            return (

                f"Catastrophic drawdown ({portfolio.drawdown_pct:.1f}% ≥ 50%) — "

                "new entries blocked"

            )

        return None



    def _log_risk_decision(

        self,

        symbol: str,

        trace_id: str | None,

        decision: RiskDecision,

        *,

        trade_risk: float | None = None,

    ) -> None:

        if self._event_logger is None or trace_id is None:

            return

        data = {"trade_risk": trade_risk} if trade_risk is not None else {}

        if decision.approved:

            self._event_logger.risk_approval(

                decision.reason,

                symbol=symbol,

                trace_id=trace_id,

                lot_size=decision.lot_size,

                data=data,

            )

        else:

            self._event_logger.risk_rejection(

                decision.reason,

                symbol=symbol,

                trace_id=trace_id,

                reason=decision.reason,

                data={**data, "lot_size": decision.lot_size},

            )



    def calculate_lot_size(

        self,

        *,

        balance: float,

        risk_pct: float,

        entry_price: float,

        stop_loss: float,

        pip_size: float,

        pip_value_per_lot: float,

    ) -> float:

        """

        Calculate position size from balance, risk percentage, and stop distance.



        Formula:

            risk_amount = balance * (risk_pct / 100)

            lots = risk_amount / (stop_pips * pip_value_per_lot)

        """

        stop_distance = abs(entry_price - stop_loss)

        if balance <= 0 or risk_pct <= 0 or stop_distance <= 0:

            return 0.0



        stop_pips = stop_distance / pip_size

        if stop_pips <= 0:

            return 0.0



        risk_amount = balance * (risk_pct / 100.0)

        risk_per_lot = stop_pips * pip_value_per_lot

        if risk_per_lot <= 0:

            return 0.0



        raw_lots = risk_amount / risk_per_lot

        lots = self._round_lot_size(raw_lots)

        lots = min(lots, self.limits.max_lot_size)



        if lots < self.limits.min_lot_size:

            return 0.0

        return lots



    def _round_lot_size(self, lots: float) -> float:

        step = self.limits.lot_step

        if step <= 0:

            return round(lots, 2)

        rounded = math.floor((lots + step * 1e-9) / step) * step

        return round(rounded, 2)



    def _pip_size_for_symbol(self, symbol: str) -> float:

        return PIP_SIZE_BY_SYMBOL.get(symbol, self.limits.pip_size)



    def _pip_value_per_lot(

        self,

        pip_size: float,

        *,

        entry_price: float | None = None,

        symbol: str | None = None,

    ) -> float:

        pip_value = self.limits.contract_size * pip_size

        if entry_price and entry_price > 0 and symbol and symbol.endswith("JPY"):

            return pip_value / entry_price

        return pip_value



    def _validate_request(

        self,

        request: TradeRequest,

        portfolio: PortfolioState,

        pip_size: float,

    ) -> str | None:

        if portfolio.balance <= 0:

            return "Portfolio balance must be greater than zero"



        symbol = self._normalize_symbol(request.symbol)

        if not symbol:

            return "Symbol is required"



        if request.entry_price <= 0:

            return "Entry price must be greater than zero"



        if request.stop_loss <= 0:

            return "Stop loss must be greater than zero"



        if abs(request.entry_price - request.stop_loss) < pip_size:

            return "Stop loss distance is too small"



        if request.side == "buy" and request.stop_loss >= request.entry_price:

            return "Buy stop loss must be below entry price"



        if request.side == "sell" and request.stop_loss <= request.entry_price:

            return "Sell stop loss must be above entry price"



        return None



    def _risk_amount_for_trade(

        self,

        *,

        volume: float,

        entry_price: float,

        stop_loss: float,

        pip_size: float,

        pip_value_per_lot: float,

    ) -> float:

        stop_pips = abs(entry_price - stop_loss) / pip_size

        return stop_pips * pip_value_per_lot * volume

    def _cap_lot_to_exposure_limits(
        self,
        lot_size: float,
        *,
        symbol: str,
        request: TradeRequest,
        portfolio: PortfolioState,
        pip_size: float,
        pip_value_per_lot: float,
    ) -> tuple[float, str]:
        """Reduce lot to fit symbol and correlation budgets before blocking."""
        notes: list[str] = []
        capped = lot_size

        symbol_risk = sum(
            pos.risk_amount for pos in portfolio.open_positions if pos.symbol == symbol
        )
        max_symbol = portfolio.balance * (self.limits.max_risk_per_symbol_pct / 100.0)
        if max_symbol > 0:
            trade_risk = self._risk_amount_for_trade(
                volume=capped,
                entry_price=request.entry_price,
                stop_loss=request.stop_loss,
                pip_size=pip_size,
                pip_value_per_lot=pip_value_per_lot,
            )
            headroom = max(0.0, max_symbol - symbol_risk)
            if trade_risk > headroom and headroom > 0:
                ratio = headroom / trade_risk
                capped = self._round_lot_size(max(self.limits.min_lot_size, capped * ratio))
                notes.append(f"Symbol budget scaled to ${headroom:,.0f} headroom")

        for group_name, members in self.correlation_groups.items():
            if symbol not in members:
                continue
            member_set = set(members)
            group_risk = sum(
                pos.risk_amount
                for pos in portfolio.open_positions
                if pos.symbol in member_set
            )
            max_group = portfolio.balance * (
                self.limits.max_correlated_exposure_pct / 100.0
            )
            if max_group <= 0:
                continue
            trade_risk = self._risk_amount_for_trade(
                volume=capped,
                entry_price=request.entry_price,
                stop_loss=request.stop_loss,
                pip_size=pip_size,
                pip_value_per_lot=pip_value_per_lot,
            )
            headroom = max(0.0, max_group - group_risk)
            if trade_risk > headroom and headroom > 0:
                ratio = headroom / trade_risk
                capped = self._round_lot_size(max(self.limits.min_lot_size, capped * ratio))
                notes.append(f"{group_name} correlation budget scaled")

        note = "; ".join(notes)
        return capped, note

    def _exposure_dangerously_high(
        self,
        *,
        symbol: str,
        portfolio: PortfolioState,
        additional_risk: float,
    ) -> str | None:
        """Return reason only when exposure is genuinely dangerous (>125% of cap)."""
        max_symbol = portfolio.balance * (self.limits.max_risk_per_symbol_pct / 100.0)
        if max_symbol <= 0:
            return None
        symbol_risk = sum(
            pos.risk_amount for pos in portfolio.open_positions if pos.symbol == symbol
        )
        usage = (symbol_risk + additional_risk) / max_symbol
        if usage > 1.25:
            return f"symbol exposure {usage:.0%} of cap"
        return None

    @staticmethod

    def _normalize_symbol(symbol: str) -> str:

        return symbol.strip().upper()



    @staticmethod

    def position_risk_amount(

        *,

        volume: float,

        entry_price: float,

        stop_loss: float,

        pip_size: float,

        pip_value_per_lot: float,

    ) -> float:

        """Helper to compute risk amount for an open position."""

        stop_pips = abs(entry_price - stop_loss) / pip_size

        return stop_pips * pip_value_per_lot * volume





__all__ = ["RiskManager", "ALLOCATION_FIREWALL_DNA"]


