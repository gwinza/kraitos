"""
Dashboard data aggregation for Kraitos.

Reads configuration, trade logs, analytics, and optional runtime state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from analytics.pair_specialisation import PairSpecialisationAnalyzer
from analytics.performance import PerformanceAnalyzer
from config import ConfigError, load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
PAPER_TRADES_PATH = LOGS_DIR / "paper_trades.csv"
DASHBOARD_STATE_PATH = LOGS_DIR / "dashboard_state.json"
REJECTED_TRADES_PATH = LOGS_DIR / "csv" / "rejected_trades.csv"
TRADE_DECISIONS_PATH = LOGS_DIR / "csv" / "trade_decisions.csv"
TRADE_DECISIONS_JSONL = LOGS_DIR / "json" / "trade_decisions.jsonl"


@dataclass(frozen=True)
class DashboardSnapshot:
    """Aggregated data for the Streamlit dashboard."""

    account_balance: float
    equity: float
    mode: str
    win_rate: float
    max_drawdown: float
    best_pairs: tuple[str, ...]
    worst_pairs: tuple[str, ...]
    regime: str
    regime_confidence: float
    regime_reason: str
    latest_decision: str
    latest_decision_action: str
    open_trades: pd.DataFrame
    recent_trades: pd.DataFrame
    rejected_trades: pd.DataFrame


class DashboardDataService:
    """Load dashboard metrics from Kraitos logs and configuration."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.root = project_root or PROJECT_ROOT
        self.logs_dir = self.root / "logs"
        self._performance = PerformanceAnalyzer()
        self._pair_analyzer = PairSpecialisationAnalyzer()

    def load_snapshot(self) -> DashboardSnapshot:
        """Build a complete dashboard snapshot."""
        config = self._load_config_safe()
        paper_df = self._load_paper_trades()
        trades = self._load_closed_trades()
        metrics = self._performance.analyze(
            trades,
            initial_balance=config.get("initial_balance", 10_000.0),
        )

        balance = self._resolve_balance(paper_df, config)
        equity = balance
        mode = "live" if config.get("live_enabled") else "paper"
        best_pairs, worst_pairs = self._resolve_pair_rankings()
        regime_state = self._load_dashboard_state()
        latest_decision, latest_action = self._load_latest_decision()

        return DashboardSnapshot(
            account_balance=balance,
            equity=equity,
            mode=mode,
            win_rate=metrics.win_rate,
            max_drawdown=metrics.max_drawdown,
            best_pairs=best_pairs,
            worst_pairs=worst_pairs,
            regime=regime_state.get("regime", "unknown"),
            regime_confidence=float(regime_state.get("regime_confidence", 0.0)),
            regime_reason=regime_state.get("regime_reason", "No regime data available"),
            latest_decision=latest_decision,
            latest_decision_action=latest_action,
            open_trades=self._open_trades(paper_df),
            recent_trades=self._recent_trades(paper_df),
            rejected_trades=self._load_rejected_trades(),
        )

    def _load_config_safe(self) -> dict:
        try:
            config = load_config(self.root / "config" / "config.yaml")
            return {
                "initial_balance": config.account.balance,
                "live_enabled": config.trading.live_enabled,
                "paper_enabled": config.trading.paper_enabled,
            }
        except (ConfigError, OSError, ValueError):
            return {
                "initial_balance": 10_000.0,
                "live_enabled": False,
                "paper_enabled": True,
            }

    def _load_paper_trades(self) -> pd.DataFrame:
        path = self.logs_dir / "paper_trades.csv"
        if not path.exists():
            return pd.DataFrame()
        frame = pd.read_csv(path)
        if "event_time" in frame.columns:
            frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
        return frame.sort_values("event_time") if not frame.empty else frame

    def _load_closed_trades(self):
        paths = [
            self.logs_dir / "paper_trades.csv",
            self.logs_dir / "csv" / "executed_trades.csv",
            self.logs_dir / "json" / "executed_trades.jsonl",
        ]
        trades = []
        for path in paths:
            if path.exists():
                try:
                    trades.extend(self._performance.load_trades(path))
                except Exception:
                    continue
        return trades

    def _resolve_balance(self, paper_df: pd.DataFrame, config: dict) -> float:
        if not paper_df.empty and "balance" in paper_df.columns:
            balances = pd.to_numeric(paper_df["balance"], errors="coerce").dropna()
            if not balances.empty:
                return float(balances.iloc[-1])
        return float(config.get("initial_balance", 10_000.0))

    def _resolve_pair_rankings(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        best: tuple[str, ...] = ()
        worst: tuple[str, ...] = ()

        path = self.root / "logs" / "pair_specialisation.json"
        if path.exists():
            try:
                result = self._pair_analyzer.load(path)
                strong = [entry.symbol for entry in result.pairs if entry.classification == "strong"]
                weak = [
                    entry.symbol
                    for entry in result.pairs
                    if entry.classification in {"weak", "quarantined"}
                ]
                if strong:
                    best = tuple(strong)
                if weak:
                    worst = tuple(weak)
                return best, worst
            except Exception:
                pass

        trades = self._load_closed_trades()
        if trades:
            metrics = self._performance.analyze(trades)
            if metrics.best_symbol:
                best = (metrics.best_symbol,)
            if metrics.worst_symbol:
                worst = (metrics.worst_symbol,)
        return best, worst

    def _load_dashboard_state(self) -> dict:
        path = self.logs_dir / "dashboard_state.json"
        if not path.exists():
            return {}
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _load_latest_decision(self) -> tuple[str, str]:
        csv_path = self.logs_dir / "csv" / "trade_decisions.csv"
        if csv_path.exists():
            frame = pd.read_csv(csv_path)
            if not frame.empty:
                row = frame.iloc[-1]
                action = str(row.get("event_type", row.get("message", "unknown")))
                message = str(row.get("message", ""))
                return message, action

        jsonl_path = self.logs_dir / "json" / "trade_decisions.jsonl"
        if jsonl_path.exists():
            last_line = ""
            with jsonl_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        last_line = line.strip()
            if last_line:
                payload = json.loads(last_line)
                return str(payload.get("message", "")), str(payload.get("event_type", "unknown"))

        return "No trade decisions logged yet", "none"

    def _open_trades(self, paper_df: pd.DataFrame) -> pd.DataFrame:
        if paper_df.empty or "trade_id" not in paper_df.columns:
            return pd.DataFrame()

        latest = paper_df.sort_values("event_time").groupby("trade_id", as_index=False).tail(1)
        open_rows = latest[latest["status"].astype(str).str.lower() == "open"]
        columns = [
            col
            for col in [
                "trade_id",
                "symbol",
                "side",
                "entry_price",
                "lot_size",
                "stop_loss",
                "take_profit",
                "floating_pl",
                "event_time",
            ]
            if col in open_rows.columns
        ]
        return open_rows[columns].reset_index(drop=True) if not open_rows.empty else pd.DataFrame()

    def _recent_trades(self, paper_df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
        if paper_df.empty:
            return pd.DataFrame()

        closed = paper_df[
            paper_df["event_type"].astype(str).str.lower().isin(["close", "scale_out"])
        ]
        columns = [
            col
            for col in [
                "event_time",
                "symbol",
                "side",
                "entry_price",
                "exit_price",
                "lot_size",
                "closed_pl",
                "balance",
                "reason",
            ]
            if col in closed.columns
        ]
        if closed.empty:
            return pd.DataFrame()
        return closed[columns].tail(limit).iloc[::-1].reset_index(drop=True)

    def _load_rejected_trades(self, limit: int = 10) -> pd.DataFrame:
        path = self.logs_dir / "csv" / "rejected_trades.csv"
        if not path.exists():
            return pd.DataFrame()

        frame = pd.read_csv(path)
        if frame.empty:
            return frame

        columns = [
            col
            for col in ["timestamp", "symbol", "event_type", "message", "trace_id"]
            if col in frame.columns
        ]
        result = frame[columns].tail(limit).iloc[::-1] if columns else frame.tail(limit)
        return result.reset_index(drop=True)
