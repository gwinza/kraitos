"""Daily realized P/L tracking for risk limits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class DailyPnLSnapshot:
    """Daily drawdown inputs for portfolio risk checks."""

    trading_day: str
    day_start_balance: float
    daily_realized_pnl: float


class DailyPnLTracker:
    """Track per-calendar-day realized P/L using account balance deltas."""

    def __init__(self, state_path: Path) -> None:
        self._path = state_path

    def snapshot(self, current_balance: float) -> DailyPnLSnapshot:
        """
        Return day-start balance and today's realized P/L.

        Realized P/L is computed as balance change since the UTC day open.
        Open-trade floating P/L does not affect the cash balance.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        state = self._load()

        if state.get("trading_day") != today:
            state = {
                "trading_day": today,
                "day_start_balance": current_balance,
            }
            self._save(state)
            return DailyPnLSnapshot(
                trading_day=today,
                day_start_balance=current_balance,
                daily_realized_pnl=0.0,
            )

        day_start = float(state["day_start_balance"])
        if day_start > 0:
            drift = abs(current_balance - day_start) / day_start
            if drift > 0.5:
                logger.info(
                    f"Re-baselining daily P/L: day_start {day_start:,.2f} -> "
                    f"current balance {current_balance:,.2f}"
                )
                state = {
                    "trading_day": today,
                    "day_start_balance": current_balance,
                }
                self._save(state)
                return DailyPnLSnapshot(
                    trading_day=today,
                    day_start_balance=current_balance,
                    daily_realized_pnl=0.0,
                )
        daily_pnl = current_balance - day_start
        return DailyPnLSnapshot(
            trading_day=today,
            day_start_balance=day_start,
            daily_realized_pnl=daily_pnl,
        )

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
