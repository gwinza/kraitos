"""Risk management data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class RiskLimits:
    """Risk limits used to size trades via allocation firewall."""

    per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_open_trades: int = 5
    max_risk_per_symbol_pct: float = 2.0
    max_correlated_exposure_pct: float = 3.0
    min_lot_size: float = 0.01
    max_lot_size: float = 10.0
    pip_size: float = 0.0001
    contract_size: float = 100_000.0
    lot_step: float = 0.01


@dataclass(frozen=True)
class OpenPosition:
    """An open position used for portfolio risk checks."""

    symbol: str
    side: TradeSide
    volume: float
    entry_price: float
    stop_loss: float
    risk_amount: float


@dataclass(frozen=True)
class TradeRequest:
    """Trade awaiting capital allocation."""

    symbol: str
    side: TradeSide
    entry_price: float
    stop_loss: float
    pip_size: float | None = None
    pip_value_per_lot: float | None = None


@dataclass(frozen=True)
class PortfolioState:
    """Current account and exposure snapshot."""

    balance: float
    open_positions: tuple[OpenPosition, ...] = ()
    daily_realized_pnl: float = 0.0
    day_start_balance: float | None = None
    peak_balance: float | None = None
    margin_utilization_pct: float = 0.0

    @property
    def drawdown_pct(self) -> float:
        peak = self.peak_balance or self.balance
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - self.balance) / peak * 100.0)


@dataclass(frozen=True)
class RiskDecision:
    """Outcome of a risk evaluation."""

    approved: bool
    reason: str
    lot_size: float


# Symbols that share a currency exposure are considered correlated.
DEFAULT_CORRELATION_GROUPS: dict[str, tuple[str, ...]] = {
    "usd_majors": ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF", "USDCAD"),
    "eur_block": ("EURUSD", "EURGBP", "EURJPY", "EURCHF", "EURAUD"),
    "gbp_block": ("GBPUSD", "EURGBP", "GBPJPY", "GBPCHF", "GBPAUD"),
    "jpy_crosses": ("USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY"),
}
