"""
Kraitos — integrated forex trading system.

Runs the unified analysis pipeline with command center monitoring:
market data, bias, structure, setup quality, precision entry, risk control,
signal routing, and simulated execution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from loguru import logger

from broker.exceptions import MT5ConnectionError, MT5DataError
from config import ConfigError
from controls.trading_gate import TradingGate
from core.bootstrap import initialize_runtime
from core.engine import KraitosEngine
from dashboard.cli_dashboard import CommandCenter
from monitoring.error_reporter import ErrorReporter

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


@click.command()
@click.option(
    "--symbols",
    multiple=True,
    help="Symbols to evaluate (defaults to config trading.symbols).",
)
@click.option(
    "--execute/--no-execute",
    default=None,
    help="Simulate paper execution for TRADE signals.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Print pipeline signals as JSON to stdout.",
)
@click.option(
    "--no-dashboard",
    is_flag=True,
    default=False,
    help="Skip launching the command center dashboard.",
)
@click.option(
    "--pause",
    is_flag=True,
    default=False,
    help="Pause strategy execution before running.",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume paused strategy execution.",
)
@click.option(
    "--emergency-stop",
    is_flag=True,
    default=False,
    help="Activate emergency stop (disables all trading).",
)
@click.option(
    "--clear-emergency",
    is_flag=True,
    default=False,
    help="Clear an active emergency stop.",
)
def cli(
    symbols: tuple[str, ...],
    execute: bool | None,
    output_json: bool,
    no_dashboard: bool,
    pause: bool,
    resume: bool,
    emergency_stop: bool,
    clear_emergency: bool,
) -> None:
    """Run the integrated Kraitos pipeline with command center."""
    raise SystemExit(
        main(
            symbols=symbols,
            execute=execute,
            output_json=output_json,
            show_dashboard=not no_dashboard,
            pause=pause,
            resume=resume,
            emergency_stop=emergency_stop,
            clear_emergency=clear_emergency,
        )
    )


def main(
    *,
    symbols: tuple[str, ...] = (),
    execute: bool | None = None,
    output_json: bool = False,
    show_dashboard: bool = True,
    pause: bool = False,
    resume: bool = False,
    emergency_stop: bool = False,
    clear_emergency: bool = False,
) -> int:
    """Application entry point for the integrated pipeline."""
    logger.info("Starting Kraitos integrated pipeline")

    try:
        config, event_logger, _log_dir = initialize_runtime(PROJECT_ROOT)
    except ConfigError:
        return 1

    if config.trading.live_enabled and config.pipeline.execution_mode == "simulation":
        logger.warning(
            "Config has live_enabled=true but pipeline.execution_mode=simulation; "
            "using simulated execution only"
        )

    app_name = config.raw.get("app", {}).get("name", "Kraitos")
    mode = "simulation" if config.simulation_only else "live"
    logger.info(f"Loaded configuration for {app_name} ({mode} pipeline)")
    logger.info(
        f"Account balance: {config.account.balance:,.2f} | "
        f"Risk/trade: {config.risk.per_trade_pct}% | "
        f"Symbols: {', '.join(config.trading.symbols)}"
    )

    error_reporter = ErrorReporter(
        project_root=PROJECT_ROOT,
        event_logger=event_logger,
    )
    trading_gate = TradingGate(
        project_root=PROJECT_ROOT,
        config=config,
        critical_errors=error_reporter.critical_errors,
    )
    engine = KraitosEngine.build(
        project_root=PROJECT_ROOT,
        config=config,
        event_logger=event_logger,
        trading_gate=trading_gate,
    )

    command_center = CommandCenter(
        project_root=PROJECT_ROOT,
        config=config,
        event_logger=event_logger,
        paper_trader=engine._runtime.paper_trader,  # type: ignore[attr-defined]
        trading_gate=trading_gate,
        error_reporter=error_reporter,
    )

    if emergency_stop:
        command_center.activate_emergency_stop()
    if clear_emergency:
        command_center.clear_emergency_stop()
    if pause:
        command_center.pause_strategies()
    if resume:
        command_center.resume_strategies()

    if show_dashboard:
        command_center.launch()

    selected = symbols or None
    should_execute = execute if execute is not None else config.pipeline.execute_trades
    permitted, block_reason = command_center.trading_permitted()
    if not permitted and should_execute:
        logger.warning(f"Trade execution blocked: {block_reason}")
        should_execute = False

    try:
        signals = engine.run(symbols=selected, execute=should_execute)
        command_center.update_signals(signals)
    except MT5ConnectionError as exc:
        logger.error(f"MetaTrader 5 connection failed: {exc}")
        command_center.error_reporter.report(
            "MT5 connection failed",
            exc=exc,
            critical=True,
        )
        if show_dashboard:
            print(command_center.render())
        return 1
    except MT5DataError as exc:
        logger.error(f"Market data error: {exc}")
        command_center.error_reporter.report(
            "Market data error",
            exc=exc,
            critical=True,
        )
        if show_dashboard:
            print(command_center.render())
        return 1
    except Exception as exc:
        logger.exception(f"Pipeline failed: {exc}")
        command_center.error_reporter.report(
            "Pipeline run failed",
            exc=exc,
            critical=True,
        )
        if show_dashboard:
            print(command_center.render())
        return 1

    if output_json or config.pipeline.output_json:
        print(json.dumps([signal.to_dict() for signal in signals], indent=2))

    trades = sum(1 for signal in signals if signal.decision == "TRADE")
    executed = sum(1 for signal in signals if signal.executed)
    logger.info(
        f"Pipeline complete: {len(signals)} symbol(s), "
        f"{trades} TRADE signal(s), {executed} simulated execution(s)"
    )

    if show_dashboard:
        print(command_center.render())

    return 0


if __name__ == "__main__":
    cli()
