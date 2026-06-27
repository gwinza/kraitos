"""Demo forward test — candle replay with thesis snapshot recording."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from backtesting.conservative_backtest_engine import ConservativeBacktestConfig, ConservativeBacktestEngine
from backtesting.execution_model import ExecutionCostConfig
from backtesting.run_validation_backtest import build_backtest_stack
from intelligence.kraitos_thesis_doctrine import reset_thesis_tracker
from paper_trading.virtual_account import ValidationConfig
from validation.data_universe import build_walk_forward_universe


@dataclass
class ForwardTestSnapshot:
    moment: str
    symbol: str
    decision: str
    thesis_tradeable: bool | None
    thesis_direction: str | None
    thesis_rr: float | None
    entry_action: str | None
    risk_approved: bool | None
    story_clear: bool | None
    rejection_reason: str = ""


@dataclass
class DemoForwardTestResult:
    snapshots: list[ForwardTestSnapshot] = field(default_factory=list)
    entries: int = 0
    exits: int = 0
    overrides: int = 0


def run_demo_forward_test(
    project_root: Path,
    *,
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD"),
    years: tuple[int, ...] = (2023,),
    m1_bars_per_year: int = 4_000,
    step: int = 8,
    max_snapshots: int = 500,
) -> DemoForwardTestResult:
    """Replay walk-forward data and record thesis/decision snapshots."""
    from backtesting.backtest_engine import BacktestEngineConfig

    project_root = project_root.resolve()
    reset_thesis_tracker()
    universe, _source = build_walk_forward_universe(
        project_root,
        years=years,
        symbols=symbols,
        m1_bars_per_year=m1_bars_per_year,
    )
    stack_config, pipeline, risk_controller = build_backtest_stack(project_root)
    journal_before = project_root / "logs" / "demo_forward_journal.csv"
    if journal_before.exists():
        journal_before.unlink()

    validation = ValidationConfig(
        initial_balance=float(stack_config.account.balance),
        risk_per_trade_pct=float(stack_config.risk.per_trade_pct),
    )
    engine = ConservativeBacktestEngine(
        config=stack_config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        conservative_config=ConservativeBacktestConfig(
            engine=BacktestEngineConfig(
                driver_timeframe="M5",
                step=step,
                min_warmup_bars=0,
                validation=validation,
            ),
            costs=ExecutionCostConfig(),
        ),
        journal_path=journal_before,
    )
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )
    run = engine.run(universe, symbols=symbols)
    result = DemoForwardTestResult()

    if run.account is not None and run.account.closed_entries:
        result.exits = len(run.account.closed_entries)
    result.entries = run.skip_stats.positions_opened

    # Build snapshots from journal open rows
    if journal_before.exists():
        frame = pd.read_csv(journal_before)
        opens = frame[frame["result"] == "open"].head(max_snapshots)
        for _, row in opens.iterrows():
            reason = str(row.get("reason", ""))
            result.snapshots.append(
                ForwardTestSnapshot(
                    moment=str(row.get("event_time", "")),
                    symbol=str(row.get("symbol", "")),
                    decision="TRADE",
                    thesis_tradeable="Thesis:" in reason or "TP1 at" in reason,
                    thesis_direction="bullish" if row.get("direction") == "buy" else "bearish",
                    thesis_rr=None,
                    entry_action="enter",
                    risk_approved=True,
                    story_clear="story" in reason.lower() or "liquidity_sweep" in reason.lower(),
                )
            )

    return result


def write_demo_forward_test_report(
    project_root: Path,
    result: DemoForwardTestResult,
) -> Path:
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    jsonl_path = logs / "demo_forward_test_snapshots.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for snap in result.snapshots:
            handle.write(json.dumps(asdict(snap)) + "\n")

    lines = [
        "# Demo Forward Test Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Replay summary",
        "",
        f"- Snapshots recorded: **{len(result.snapshots)}**",
        f"- Entries: **{result.entries}**",
        f"- Exit events: **{result.exits}**",
        f"- Story overrides: **{result.overrides}**",
        "",
        "## Snapshot file",
        "",
        f"`{jsonl_path}`",
        "",
        "## Sample decisions",
        "",
    ]
    for snap in result.snapshots[:10]:
        lines.append(
            f"- `{snap.moment}` **{snap.symbol}** — thesis_ok={snap.thesis_tradeable}, "
            f"story_clear={snap.story_clear}, direction={snap.thesis_direction}"
        )

    path = logs / "demo_forward_test_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
