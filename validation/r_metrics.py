"""R-multiple helpers for validation metrics."""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.helpers import pip_size_for_symbol, pip_value_per_lot
from risk.risk_manager import RiskManager

CLOSED_RESULTS = frozenset({"win", "loss", "breakeven"})


def initial_risk_amount(
    *,
    symbol: str,
    entry: float,
    stop_loss: float,
    lot_size: float,
) -> float:
    """Dollar risk at entry: stop distance × pip value × lot size."""
    if entry <= 0 or stop_loss <= 0 or lot_size <= 0:
        return 0.0
    pip_size = pip_size_for_symbol(symbol)
    pip_value = pip_value_per_lot(symbol, entry)
    return RiskManager.position_risk_amount(
        volume=lot_size,
        entry_price=entry,
        stop_loss=stop_loss,
        pip_size=pip_size,
        pip_value_per_lot=pip_value,
    )


def trade_r_multiple(row: pd.Series | dict[str, Any]) -> float:
    """Return R for one closed trade; recompute when journal stored 0."""
    if isinstance(row, pd.Series):
        data = row.to_dict()
    else:
        data = row

    stored = float(pd.to_numeric(data.get("r_multiple"), errors="coerce") or 0.0)
    if stored != 0.0:
        return stored

    pnl = float(pd.to_numeric(data.get("profit_loss"), errors="coerce") or 0.0)
    risk = initial_risk_amount(
        symbol=str(data.get("symbol", "EURUSD")),
        entry=float(pd.to_numeric(data.get("entry"), errors="coerce") or 0.0),
        stop_loss=float(pd.to_numeric(data.get("stop_loss"), errors="coerce") or 0.0),
        lot_size=float(pd.to_numeric(data.get("lot_size"), errors="coerce") or 0.0),
    )
    if risk <= 0:
        return 0.0
    return pnl / risk


def average_r_from_closed_frame(frame: pd.DataFrame) -> float:
    """Mean R across closed trades only."""
    if frame.empty:
        return 0.0
    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    if closed.empty:
        return 0.0
    r_values = closed.apply(trade_r_multiple, axis=1)
    return float(r_values.mean()) if len(r_values) else 0.0
