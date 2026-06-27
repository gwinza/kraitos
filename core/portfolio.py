"""Portfolio state builders for risk evaluation."""

from __future__ import annotations

from pathlib import Path

from typing import TYPE_CHECKING

from config.settings import KraitosConfig
from core.daily_tracker import DailyPnLTracker
from core.helpers import pip_size_for_symbol, pip_value_per_lot
from execution.paper_trader import PaperTrader
from risk.models import OpenPosition, PortfolioState
from risk.risk_manager import RiskManager

if TYPE_CHECKING:
    from broker.mt5_connector import MT5Connector


def _position_from_trade(
    *,
    symbol: str,
    side: str,
    volume: float,
    entry_price: float,
    stop_loss: float,
    risk_manager: RiskManager,
) -> OpenPosition:
    pip_size = pip_size_for_symbol(symbol)
    pip_value = pip_value_per_lot(
        symbol,
        entry_price,
        contract_size=risk_manager.limits.contract_size,
    )
    risk_amount = RiskManager.position_risk_amount(
        volume=volume,
        entry_price=entry_price,
        stop_loss=stop_loss,
        pip_size=pip_size,
        pip_value_per_lot=pip_value,
    )
    return OpenPosition(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        volume=volume,
        entry_price=entry_price,
        stop_loss=stop_loss,
        risk_amount=risk_amount,
    )


def build_portfolio_state(
    *,
    config: KraitosConfig,
    paper_trader: PaperTrader,
    risk_manager: RiskManager,
    project_root: Path | None = None,
    broker_balance: float | None = None,
    connector: MT5Connector | None = None,
) -> PortfolioState:
    """Build a portfolio snapshot from paper or live account state."""
    positions: list[OpenPosition] = []

    if config.trading.live_enabled and connector is not None and connector.is_connected:
        for position in connector.get_open_positions():
            positions.append(
                _position_from_trade(
                    symbol=position.symbol,
                    side=position.side,
                    volume=position.volume,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    risk_manager=risk_manager,
                )
            )
        balance = (
            broker_balance
            if broker_balance is not None and broker_balance > 0
            else config.account.balance
        )
    else:
        snapshot = paper_trader.snapshot()
        for trade in snapshot.open_trades:
            positions.append(
                _position_from_trade(
                    symbol=trade.symbol,
                    side=trade.side,
                    volume=trade.lot_size,
                    entry_price=trade.entry_price,
                    stop_loss=trade.stop_loss,
                    risk_manager=risk_manager,
                )
            )
        balance = (
            snapshot.balance if snapshot.balance > 0 else config.account.balance
        )

    tracker_path = (project_root or Path.cwd()) / "logs" / "daily_pnl_state.json"
    daily = DailyPnLTracker(tracker_path).snapshot(balance)

    return PortfolioState(
        balance=balance,
        open_positions=tuple(positions),
        daily_realized_pnl=daily.daily_realized_pnl,
        day_start_balance=daily.day_start_balance,
        peak_balance=balance,
    )
