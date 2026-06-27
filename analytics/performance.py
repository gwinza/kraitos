"""
Performance analytics for Kraitos.

Calculates trading statistics from paper trade logs and executed trade logs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger

from analytics.models import ClosedTradeRecord, PerformanceMetrics

DEFAULT_PAPER_LOG = Path(__file__).resolve().parent.parent / "logs" / "paper_trades.csv"
DEFAULT_EXECUTED_CSV = (
    Path(__file__).resolve().parent.parent / "logs" / "csv" / "executed_trades.csv"
)
DEFAULT_EXECUTED_JSONL = (
    Path(__file__).resolve().parent.parent / "logs" / "json" / "executed_trades.jsonl"
)

REALIZED_EVENT_TYPES = frozenset({"close", "scale_out"})


class PerformanceError(Exception):
    """Raised when performance input is invalid."""


class PerformanceAnalyzer:
    """Calculate performance metrics from trade logs."""

    def analyze(
        self,
        trades: list[ClosedTradeRecord],
        *,
        initial_balance: float = 10_000.0,
    ) -> PerformanceMetrics:
        """Compute performance metrics from normalized closed trades."""
        if not trades:
            return self._empty_metrics()

        pnls = [trade.pnl for trade in trades]
        winners = [pnl for pnl in pnls if pnl > 0]
        losers = [pnl for pnl in pnls if pnl < 0]

        total = len(trades)
        win_rate = len(winners) / total
        loss_rate = len(losers) / total
        average_win = sum(winners) / len(winners) if winners else 0.0
        average_loss = abs(sum(losers) / len(losers)) if losers else 0.0
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        net_profit = sum(pnls)

        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        max_drawdown = self._max_drawdown(trades, initial_balance)
        daily_return = self._average_daily_return(trades, initial_balance)
        best_symbol, worst_symbol = self._best_worst_symbol(trades)
        best_session, worst_session = self._best_worst_session(trades)

        return PerformanceMetrics(
            total_trades=total,
            win_rate=round(win_rate, 4),
            loss_rate=round(loss_rate, 4),
            average_win=round(average_win, 2),
            average_loss=round(average_loss, 2),
            profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else profit_factor,
            max_drawdown=round(max_drawdown, 4),
            daily_return=round(daily_return, 4),
            best_symbol=best_symbol,
            worst_symbol=worst_symbol,
            best_session=best_session,
            worst_session=worst_session,
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            net_profit=round(net_profit, 2),
        )

    def from_log_paths(
        self,
        *paths: Path | str,
        initial_balance: float = 10_000.0,
    ) -> PerformanceMetrics:
        """Load and analyze trades from one or more log files."""
        trades: list[ClosedTradeRecord] = []
        for path in paths:
            trades.extend(self.load_trades(path))
        return self.analyze(trades, initial_balance=initial_balance)

    def from_default_logs(self, initial_balance: float = 10_000.0) -> PerformanceMetrics:
        """Analyze trades from default Kraitos log locations."""
        paths = [DEFAULT_PAPER_LOG, DEFAULT_EXECUTED_CSV, DEFAULT_EXECUTED_JSONL]
        existing = [path for path in paths if path.exists()]
        if not existing:
            raise PerformanceError("No trade log files found in logs/")
        return self.from_log_paths(*existing, initial_balance=initial_balance)

    def load_trades(self, path: Path | str) -> list[ClosedTradeRecord]:
        """Load normalized closed trades from a supported log file."""
        file_path = Path(path)
        if not file_path.exists():
            raise PerformanceError(f"Trade log not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            if file_path.name == "paper_trades.csv":
                return self._load_paper_trades_csv(file_path)
            return self._load_executed_trades_csv(file_path)
        if suffix == ".jsonl":
            return self._load_executed_trades_jsonl(file_path)

        raise PerformanceError(f"Unsupported trade log format: {file_path}")

    def _load_paper_trades_csv(self, path: Path) -> list[ClosedTradeRecord]:
        frame = pd.read_csv(path)
        trades: list[ClosedTradeRecord] = []

        for _, row in frame.iterrows():
            event_type = str(row.get("event_type", "")).strip().lower()
            if event_type not in REALIZED_EVENT_TYPES:
                continue

            pnl = self._to_float(row.get("closed_pl"))
            if pnl == 0.0 and event_type == "scale_out":
                continue

            exit_time = self._parse_time(row.get("event_time"))
            trades.append(
                ClosedTradeRecord(
                    trade_id=str(row.get("trade_id", "")),
                    symbol=str(row.get("symbol", "")).upper(),
                    side=str(row.get("side", "")).lower(),
                    exit_time=exit_time,
                    pnl=pnl,
                    balance=self._optional_float(row.get("balance")),
                    session=self._session_for_time(exit_time),
                    event_type=event_type,
                )
            )
        return trades

    def _load_executed_trades_csv(self, path: Path) -> list[ClosedTradeRecord]:
        frame = pd.read_csv(path)
        trades: list[ClosedTradeRecord] = []

        for _, row in frame.iterrows():
            event_type = str(row.get("event_type", "")).strip().lower()
            if event_type not in REALIZED_EVENT_TYPES:
                continue

            data = self._parse_json_field(row.get("data_json", "{}"))
            pnl = self._to_float(data.get("closed_pl", 0))
            if pnl == 0.0:
                continue

            exit_time = self._parse_time(row.get("timestamp") or row.get("event_time"))
            trades.append(
                ClosedTradeRecord(
                    trade_id=str(data.get("trade_id", row.get("event_id", ""))),
                    symbol=str(row.get("symbol", data.get("symbol", ""))).upper(),
                    side=str(data.get("side", "")).lower(),
                    exit_time=exit_time,
                    pnl=pnl,
                    balance=self._optional_float(data.get("balance")),
                    session=self._session_for_time(exit_time),
                    event_type=event_type,
                )
            )
        return trades

    def _load_executed_trades_jsonl(self, path: Path) -> list[ClosedTradeRecord]:
        trades: list[ClosedTradeRecord] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                event_type = str(row.get("event_type", "")).lower()
                if event_type not in REALIZED_EVENT_TYPES:
                    continue

                data = row.get("data", {})
                pnl = self._to_float(data.get("closed_pl", 0))
                if pnl == 0.0:
                    continue

                exit_time = self._parse_time(row.get("timestamp"))
                trades.append(
                    ClosedTradeRecord(
                        trade_id=str(data.get("trade_id", row.get("event_id", ""))),
                        symbol=str(row.get("symbol", "")).upper(),
                        side=str(data.get("side", "")).lower(),
                        exit_time=exit_time,
                        pnl=pnl,
                        balance=self._optional_float(data.get("balance")),
                        session=self._session_for_time(exit_time),
                        event_type=event_type,
                    )
                )
        return trades

    def _max_drawdown(
        self,
        trades: list[ClosedTradeRecord],
        initial_balance: float,
    ) -> float:
        ordered = sorted(trades, key=lambda trade: trade.exit_time)
        balance = initial_balance
        peak = initial_balance
        max_dd = 0.0

        for trade in ordered:
            if trade.balance is not None:
                balance = trade.balance
            else:
                balance += trade.pnl

            peak = max(peak, balance)
            if peak > 0:
                drawdown = (peak - balance) / peak
                max_dd = max(max_dd, drawdown)

        return max_dd

    def _average_daily_return(
        self,
        trades: list[ClosedTradeRecord],
        initial_balance: float,
    ) -> float:
        if not trades:
            return 0.0

        daily_pnl: dict[str, float] = {}
        for trade in trades:
            day = trade.exit_time.date().isoformat()
            daily_pnl[day] = daily_pnl.get(day, 0.0) + trade.pnl

        if not daily_pnl:
            return 0.0

        daily_returns = [
            pnl / initial_balance for pnl in daily_pnl.values()
        ]
        return sum(daily_returns) / len(daily_returns)

    def _best_worst_symbol(
        self,
        trades: list[ClosedTradeRecord],
    ) -> tuple[str | None, str | None]:
        totals: dict[str, float] = {}
        for trade in trades:
            totals[trade.symbol] = totals.get(trade.symbol, 0.0) + trade.pnl

        if not totals:
            return None, None

        best = max(totals, key=totals.get)
        worst = min(totals, key=totals.get)
        return best, worst

    def _best_worst_session(
        self,
        trades: list[ClosedTradeRecord],
    ) -> tuple[str | None, str | None]:
        totals: dict[str, float] = {}
        for trade in trades:
            totals[trade.session] = totals.get(trade.session, 0.0) + trade.pnl

        if not totals:
            return None, None

        best = max(totals, key=totals.get)
        worst = min(totals, key=totals.get)
        return best, worst

    @staticmethod
    def _session_for_time(moment: datetime) -> str:
        hour = moment.astimezone(timezone.utc).hour
        if 0 <= hour < 8:
            return "asia"
        if 8 <= hour < 13:
            return "london"
        if 13 <= hour < 22:
            return "new_york"
        return "off_hours"

    @staticmethod
    def _parse_time(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(parsed):
            return datetime.now(timezone.utc)
        return parsed.to_pydatetime()

    @staticmethod
    def _parse_json_field(value: object) -> dict:
        if isinstance(value, dict):
            return value
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return {}
        try:
            return json.loads(str(value))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _to_float(value: object) -> float:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if str(value).strip() == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _empty_metrics() -> PerformanceMetrics:
        return PerformanceMetrics(
            total_trades=0,
            win_rate=0.0,
            loss_rate=0.0,
            average_win=0.0,
            average_loss=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            daily_return=0.0,
            best_symbol=None,
            worst_symbol=None,
            best_session=None,
            worst_session=None,
            gross_profit=0.0,
            gross_loss=0.0,
            net_profit=0.0,
        )
