"""
Run an optimistic research/demo backtest (NOT used for live readiness).

Live readiness uses validation.conservative_validation only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from backtesting.backtest_engine import BacktestEngine, BacktestEngineConfig
from backtesting.skip_analyzer import SkipAnalyzer
from backtesting.synthetic_market import generate_symbol_universe
from config import load_config
from controls.drawdown_risk import DrawdownRiskController
from core.pipeline import TradingPipeline
from core.risk_controller import RiskController
from core.runtime import KraitosRuntime
from logs.event_logger import KraitosEventLogger
from paper_trading.virtual_account import ValidationConfig


def build_backtest_stack(
    project_root: Path,
    *,
    apply_strategy_quality: bool = False,
) -> tuple[object, TradingPipeline, RiskController]:
    """Construct pipeline and risk controller for historical replay.

    Trader path (apply_strategy_quality=False): no validation gates on discovery.
    Strategy quality filters are auditor-only (diagnostic reporting).
    """
    from intelligence.opportunity_allocator import OpportunityAllocator
    from portfolio.portfolio_construction import PortfolioConstructionEngine

    config_path = project_root / "config" / "config.yaml"
    config = load_config(config_path)
    event_logger = KraitosEventLogger(project_root / "logs")
    runtime = KraitosRuntime.build(
        project_root=project_root,
        config=config,
        event_logger=event_logger,
    )
    gate = None
    opportunity_allocator = OpportunityAllocator(project_root)
    portfolio_engine = PortfolioConstructionEngine(project_root)
    drawdown_risk = DrawdownRiskController(portfolio_scaling_mode=portfolio_engine is not None)
    risk_controller = RiskController(
        config=config,
        risk_manager=runtime.risk_manager,
        paper_trader=runtime.paper_trader,
        project_root=project_root,
        strategy_quality_gate=gate,
        drawdown_risk=drawdown_risk,
        portfolio_engine=portfolio_engine,
    )
    pipeline = TradingPipeline(
        config=config,
        regime_detector=runtime.regime_detector,
        bias_analyzer=runtime.bias_analyzer,
        structure_analyzer=runtime.structure_analyzer,
        harvest_engine=runtime.harvest_engine,
        micro_scalper=runtime.micro_scalper,
        entry_engine=runtime.entry_engine,
        risk_controller=risk_controller,
        news_filter=runtime.news_filter,
        pair_analyzer=runtime.pair_analyzer,
        project_root=project_root,
        opportunity_allocator=opportunity_allocator,
        portfolio_engine=portfolio_engine,
    )
    return config, pipeline, risk_controller


def run_validation_backtest(
    project_root: Path,
    *,
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY"),
    m1_bars: int = 50_000,
    min_closed_trades: int = 100,
) -> tuple[object, SkipAnalyzer]:
    """Execute backtest replay and write skip/debug reports."""
    project_root = project_root.resolve()
    (project_root / "logs").mkdir(parents=True, exist_ok=True)
    journal_path = project_root / "logs" / "trade_journal.csv"

    config, pipeline, risk_controller = build_backtest_stack(project_root)
    candles = generate_symbol_universe(symbols, bars=m1_bars)

    engine_config = BacktestEngineConfig(
        driver_timeframe="M5",
        step=2,
        min_warmup_bars=0,
        validation=ValidationConfig(
            initial_balance=float(config.account.balance),
            risk_per_trade_pct=float(config.risk.per_trade_pct),
            spread_pips=0.5,
        ),
    )

    engine = BacktestEngine(
        config=config,
        pipeline=pipeline,
        risk_controller=risk_controller,
        engine_config=engine_config,
        journal_path=journal_path,
    )
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )

    result = engine.run(candles, symbols=symbols)
    closed = len(result.account.closed_entries) if result.account else 0
    logger.info(f"Backtest finished with {closed} closed trades")

    analyzer = SkipAnalyzer(
        stats=result.skip_stats,
        result=result,
        symbols=symbols,
        config_summary={
            "driver_timeframe": engine_config.driver_timeframe,
            "step": engine_config.step,
            "min_warmup_bars": engine_config.min_warmup_bars,
            "m1_bars_per_symbol": m1_bars,
            "symbols": ", ".join(symbols),
            "timeframe_note": "M1 base resampled to M5/M15/H1/H4/H8",
            "live_trading": False,
            "min_closed_trades_target": min_closed_trades,
        },
    )
    skip_path, debug_path = analyzer.write_reports(project_root)
    logger.info(f"Wrote {skip_path}")
    logger.info(f"Wrote {debug_path}")
    return result, analyzer


def main() -> int:
    import sys

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    parser = argparse.ArgumentParser(description="Run Kraitos validation backtest")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--bars", type=int, default=50_000)
    parser.add_argument("--min-closed", type=int, default=100)
    args = parser.parse_args()

    result, _analyzer = run_validation_backtest(
        args.root,
        m1_bars=args.bars,
        min_closed_trades=args.min_closed,
    )
    closed = len(result.account.closed_entries) if result.account else 0
    if closed < args.min_closed:
        logger.warning(
            f"Closed trades {closed} below target {args.min_closed}; "
            "see logs/skip_analysis.md for blockers"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
