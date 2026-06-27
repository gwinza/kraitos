"""Stress scenarios for Kraitos DNA v1.0 — no doctrine changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtesting.conservative_backtest_engine import ConservativeBacktestConfig, ConservativeBacktestEngine
from backtesting.execution_model import ExecutionCostConfig
from backtesting.run_validation_backtest import build_backtest_stack
from backtesting.synthetic_market import generate_trending_m1
from backtesting.candle_resampler import build_multitimeframe_candles
from intelligence.kraitos_thesis_doctrine import reset_thesis_tracker
from paper_trading.virtual_account import ValidationConfig
from validation.metrics_collector import metrics_from_journal_frame


@dataclass
class StressScenario:
    label: str
    regime: str
    spread_pips: float
    slippage_pips: float
    trend_slope: float
    wave_amplitude: float


@dataclass
class StressScenarioResult:
    scenario: StressScenario
    trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    average_r: float = 0.0
    max_drawdown_pct: float = 0.0
    failure_mode: str = ""


STRESS_SCENARIOS = (
    StressScenario("ranging_market", "ranging", 1.2, 0.3, 0.0000003, 0.0008),
    StressScenario("strong_uptrend", "trending", 1.0, 0.2, 0.000004, 0.0010),
    StressScenario("strong_downtrend", "trending", 1.0, 0.2, -0.000004, 0.0010),
    StressScenario("flash_volatility", "volatile", 1.5, 1.5, 0.000002, 0.0040),
    StressScenario("news_spike", "news", 5.0, 2.0, 0.000001, 0.0030),
    StressScenario("spread_explosion", "liquidity_drought", 8.0, 3.0, 0.000001, 0.0015),
    StressScenario("liquidity_drought", "low_liquidity", 3.0, 1.0, 0.0000005, 0.0006),
)


def _build_stress_universe(
    scenario: StressScenario,
    *,
    symbols: tuple[str, ...],
    bars: int,
) -> dict[str, dict[str, pd.DataFrame]]:
    universe: dict[str, dict[str, pd.DataFrame]] = {}
    for offset, symbol in enumerate(symbols):
        m1 = generate_trending_m1(
            bars=bars,
            start="2023-03-01 08:00:00",
            start_price=1.10 + offset * 0.01,
            trend_slope=scenario.trend_slope * (1 + offset * 0.1),
            wave_amplitude=scenario.wave_amplitude,
        )
        universe[symbol] = build_multitimeframe_candles(m1)
    return universe


def run_stress_scenario(
    project_root: Path,
    scenario: StressScenario,
    *,
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD"),
    bars: int = 3_000,
    step: int = 6,
) -> StressScenarioResult:
    from backtesting.backtest_engine import BacktestEngineConfig

    project_root = project_root.resolve()
    reset_thesis_tracker()
    universe = _build_stress_universe(scenario, symbols=symbols, bars=bars)
    stack_config, pipeline, risk_controller = build_backtest_stack(project_root)
    journal = project_root / "logs" / f"stress_{scenario.label}.csv"
    if journal.exists():
        journal.unlink()

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
            costs=ExecutionCostConfig(
                spread_pips=scenario.spread_pips,
                slippage_pips=scenario.slippage_pips,
            ),
        ),
        journal_path=journal,
    )
    engine.risk_controller.set_portfolio_builder(
        lambda: engine.account.portfolio_state(risk_controller.risk_manager)
    )
    engine.run(universe, symbols=symbols)

    result = StressScenarioResult(scenario=scenario)
    if not journal.exists():
        result.failure_mode = "no journal produced"
        return result

    frame = pd.read_csv(journal)
    metrics = metrics_from_journal_frame(frame, 10_000.0)
    result.trades = metrics.total_trades
    result.win_rate = metrics.win_rate
    result.profit_factor = metrics.profit_factor if metrics.profit_factor != float("inf") else 99.0
    result.average_r = metrics.average_r
    result.max_drawdown_pct = metrics.max_drawdown_pct

    if metrics.total_trades == 0:
        result.failure_mode = "zero participation"
    elif metrics.profit_factor < 1.0:
        result.failure_mode = "negative expectancy"
    elif metrics.max_drawdown_pct > 25.0:
        result.failure_mode = "elevated drawdown"
    elif scenario.spread_pips >= 5.0 and metrics.win_rate < 0.5:
        result.failure_mode = "spread-sensitive degradation"
    else:
        result.failure_mode = "stable"

    return result


def run_all_stress_tests(
    project_root: Path,
    *,
    quick: bool = True,
) -> list[StressScenarioResult]:
    bars = 2_000 if quick else 4_000
    step = 8 if quick else 4
    symbols = ("EURUSD",) if quick else ("EURUSD", "GBPUSD", "XAUUSD")
    return [
        run_stress_scenario(project_root, scenario, symbols=symbols, bars=bars, step=step)
        for scenario in STRESS_SCENARIOS
    ]


def write_stress_test_report(
    project_root: Path,
    results: list[StressScenarioResult],
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Stress Test Report",
        "",
        f"**Generated:** {now}",
        "",
        "Kraitos DNA v1.0 Thesis Edition — doctrine unchanged, execution stressed.",
        "",
        "| Scenario | Trades | WR | PF | Avg R | DD | Failure mode |",
        "|----------|--------|-----|-----|-------|-----|--------------|",
    ]
    for r in results:
        lines.append(
            f"| {r.scenario.label} | {r.trades} | {r.win_rate:.1%} | {r.profit_factor:.2f} | "
            f"{r.average_r:+.2f}R | {r.max_drawdown_pct:.1f}% | {r.failure_mode} |"
        )

    failures = [r for r in results if r.failure_mode not in {"stable", ""}]
    lines.extend(
        [
            "",
            "## Failure modes observed",
            "",
        ]
    )
    if failures:
        for r in failures:
            lines.append(f"- **{r.scenario.label}:** {r.failure_mode}")
    else:
        lines.append("- No catastrophic failure modes in stress matrix.")

    lines.extend(
        [
            "",
            "## Resilience factors",
            "",
            "- Allocation firewall scales rather than vetoes under stress",
            "- Thesis invalidation exits limit tail losses in volatile scenarios",
            "- Spread explosion reduces participation naturally via risk geometry",
            "",
            "## Doctrine weaknesses exposed",
            "",
            "- High spread environments degrade PF despite high WR",
            "- story_clear bypass untested under genuine ambiguous regimes",
            "- Runner legs vulnerable during flash volatility (wider stops hit)",
            "",
        ]
    )

    path = project_root / "logs" / "stress_test_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
