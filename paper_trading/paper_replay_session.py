"""Historical replay session that populates paper_trades.csv without live orders."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtesting.conservative_backtest_engine import ConservativeBacktestConfig, ConservativeBacktestEngine
from backtesting.backtest_engine import BacktestEngineConfig
from backtesting.execution_model import ExecutionCostConfig
from backtesting.performance_report import PerformanceReport
from backtesting.run_validation_backtest import build_backtest_stack
from paper_trading.virtual_account import ValidationConfig
from validation.data_universe import WALK_FORWARD_SYMBOLS, WALK_FORWARD_YEARS, build_walk_forward_universe
from validation.r_metrics import CLOSED_RESULTS

PAPER_TRADES_COLUMNS = [
    "trade_id",
    "event_time",
    "event_type",
    "symbol",
    "side",
    "status",
    "entry_price",
    "exit_price",
    "lot_size",
    "stop_loss",
    "take_profit",
    "floating_pl",
    "closed_pl",
    "balance",
    "reason",
]


@dataclass(frozen=True)
class PaperReplayConfig:
    """Scope for a safe paper replay run."""

    years: tuple[int, ...] = WALK_FORWARD_YEARS
    symbols: tuple[str, ...] = WALK_FORWARD_SYMBOLS
    m1_bars_per_year: int = 8_000
    step: int = 4
    min_closed_trades: int = 30


def run_paper_replay_session(
    project_root: Path,
    *,
    config: PaperReplayConfig | None = None,
    paper_path: Path | None = None,
    overwrite: bool = True,
) -> int:
    """
    Replay historical candles into paper_trades.csv using conservative execution rules.

    Returns the number of closed trades written.
    """
    project_root = project_root.resolve()
    cfg = config or PaperReplayConfig()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    journal_path = logs / "paper_replay_journal.csv"
    target_paper = paper_path or (logs / "paper_trades.csv")
    if journal_path.exists():
        journal_path.unlink()
    if overwrite and target_paper.exists():
        target_paper.unlink()

    stack_config, pipeline, risk_controller = build_backtest_stack(project_root)
    candles, _source = build_walk_forward_universe(
        project_root,
        years=cfg.years,
        symbols=cfg.symbols,
        m1_bars_per_year=cfg.m1_bars_per_year,
    )

    validation = ValidationConfig(
        initial_balance=float(stack_config.account.balance),
        risk_per_trade_pct=float(stack_config.risk.per_trade_pct),
        spread_pips=0.5,
    )

    engine = ConservativeBacktestEngine(
        config=stack_config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        conservative_config=ConservativeBacktestConfig(
            engine=BacktestEngineConfig(
                driver_timeframe="M5",
                step=cfg.step,
                min_warmup_bars=0,
                validation=validation,
            ),
            costs=ExecutionCostConfig(
                spread_pips=1.2,
                commission_per_lot_round_turn=7.0,
                slippage_pips=0.3,
            ),
        ),
        journal_path=journal_path,
    )
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )
    engine.run(candles, symbols=cfg.symbols)

    closed_count = _journal_to_paper_trades(
        journal_path,
        target_paper,
        overwrite=overwrite,
    )
    return closed_count


def _journal_to_paper_trades(
    journal_path: Path,
    paper_path: Path,
    *,
    overwrite: bool,
) -> int:
    if not journal_path.exists():
        return 0

    frame = pd.read_csv(journal_path)
    if frame.empty:
        return 0

    closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
    if closed.empty:
        return 0

    paper_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "a"
    write_header = overwrite or not paper_path.exists() or paper_path.stat().st_size == 0

    rows_written = 0
    with paper_path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAPER_TRADES_COLUMNS)
        if write_header:
            writer.writeheader()

        for trade_id, group in frame.groupby("trade_id"):
            group = group.sort_values("event_time")
            close_rows = group[group["result"].astype(str).str.lower().isin(CLOSED_RESULTS)]
            if close_rows.empty:
                continue
            open_rows = group[group["result"].astype(str).str.lower() == "open"]
            open_row = open_rows.iloc[0] if not open_rows.empty else close_rows.iloc[0]
            close_row = close_rows.iloc[-1]

            direction = str(open_row.get("direction", "buy")).lower()
            side = direction if direction in {"buy", "sell"} else "buy"
            entry = float(open_row.get("entry", 0.0) or 0.0)
            result = str(close_row.get("result", "")).lower()
            tp = close_row.get("take_profit")
            sl = close_row.get("stop_loss")
            if result == "win" and tp not in (None, ""):
                exit_price = float(tp)
            elif result == "loss" and sl not in (None, ""):
                exit_price = float(sl)
            else:
                exit_price = entry
            pnl = float(close_row.get("profit_loss", 0.0) or 0.0)
            balance = float(close_row.get("balance", 0.0) or 0.0)

            writer.writerow(
                {
                    "trade_id": trade_id,
                    "event_time": open_row.get("event_time"),
                    "event_type": "open",
                    "symbol": open_row.get("symbol"),
                    "side": side,
                    "status": "open",
                    "entry_price": entry,
                    "exit_price": "",
                    "lot_size": open_row.get("lot_size"),
                    "stop_loss": open_row.get("stop_loss"),
                    "take_profit": open_row.get("take_profit"),
                    "floating_pl": "0.0",
                    "closed_pl": "0.0",
                    "balance": balance - pnl,
                    "reason": "paper_replay_open",
                }
            )
            writer.writerow(
                {
                    "trade_id": trade_id,
                    "event_time": close_row.get("event_time"),
                    "event_type": "close",
                    "symbol": close_row.get("symbol"),
                    "side": side,
                    "status": "closed",
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "lot_size": close_row.get("lot_size"),
                    "stop_loss": close_row.get("stop_loss"),
                    "take_profit": close_row.get("take_profit"),
                    "floating_pl": "0.0",
                    "closed_pl": pnl,
                    "balance": balance,
                    "reason": str(close_row.get("reason", "paper_replay_close")),
                }
            )
            rows_written += 1

    return rows_written


def paper_closed_trade_count(paper_path: Path) -> int:
    """Count realized paper closes in paper_trades.csv."""
    if not paper_path.exists():
        return 0
    frame = pd.read_csv(paper_path)
    if frame.empty or "event_type" not in frame.columns:
        return 0
    realized = frame[frame["event_type"].astype(str).str.lower().isin({"close", "scale_out"})]
    if "closed_pl" in realized.columns:
        realized = realized[pd.to_numeric(realized["closed_pl"], errors="coerce").fillna(0.0) != 0.0]
    return len(realized)
