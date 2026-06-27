"""Realistic execution simulation — variable spread, slippage, partial fills."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backtesting.execution_model import ExecutionCostConfig, pip_size_for_symbol


@dataclass(frozen=True)
class RealisticExecutionConfig(ExecutionCostConfig):
    """Extends conservative costs with session/news liquidity modelling."""

    base_spread_pips: float = 1.2
    spread_volatility_factor: float = 0.35
    news_spread_multiplier: float = 3.5
    news_hours_utc: tuple[int, ...] = (12, 13, 14, 15)
    slippage_volatility_factor: float = 0.5
    fill_delay_bars: int = 0
    partial_fill_probability: float = 0.05
    partial_fill_fraction: float = 0.70
    overnight_spread_multiplier: float = 1.8
    low_liquidity_hours_utc: tuple[int, ...] = (21, 22, 23, 0, 1, 2, 3, 4, 5)


@dataclass
class ExecutionRealismResult:
    label: str
    total_trades: int
    win_rate: float
    profit_factor: float
    average_r: float
    max_drawdown_pct: float
    gross_profit: float
    gross_loss: float


def spread_for_bar(
    *,
    symbol: str,
    bar_time: datetime,
    bar_high: float,
    bar_low: float,
    config: RealisticExecutionConfig,
) -> float:
    """Variable spread from session, volatility proxy, and news windows."""
    hour = bar_time.hour
    spread = config.base_spread_pips

    if hour in config.low_liquidity_hours_utc:
        spread *= config.overnight_spread_multiplier

    if hour in config.news_hours_utc and bar_time.weekday() < 5:
        spread *= config.news_spread_multiplier

    pip = pip_size_for_symbol(symbol)
    if pip > 0 and bar_high > bar_low:
        range_pips = (bar_high - bar_low) / pip
        spread += range_pips * config.spread_volatility_factor * 0.01

    return max(spread, config.base_spread_pips * 0.5)


def slippage_for_bar(
    *,
    symbol: str,
    bar_high: float,
    bar_low: float,
    config: RealisticExecutionConfig,
) -> float:
    pip = pip_size_for_symbol(symbol)
    base = config.slippage_pips
    if pip > 0:
        range_pips = (bar_high - bar_low) / pip
        return base + range_pips * config.slippage_volatility_factor * 0.02
    return base


def apply_realistic_entry_fill(
    *,
    direction: str,
    raw_price: float,
    symbol: str,
    bar_time: datetime,
    bar_high: float,
    bar_low: float,
    config: RealisticExecutionConfig,
) -> float:
    pip = pip_size_for_symbol(symbol)
    spread = spread_for_bar(
        symbol=symbol,
        bar_time=bar_time,
        bar_high=bar_high,
        bar_low=bar_low,
        config=config,
    )
    slip = slippage_for_bar(symbol=symbol, bar_high=bar_high, bar_low=bar_low, config=config)
    half = spread * pip / 2.0
    slip_dist = slip * pip
    if direction == "buy":
        return raw_price + half + slip_dist
    return raw_price - half - slip_dist


def execution_cost_from_realistic(config: RealisticExecutionConfig) -> ExecutionCostConfig:
    """Map realistic config to conservative ExecutionCostConfig baseline."""
    return ExecutionCostConfig(
        spread_pips=config.base_spread_pips,
        commission_per_lot_round_turn=config.commission_per_lot_round_turn,
        slippage_pips=config.slippage_pips + config.slippage_volatility_factor,
        sl_first_on_ambiguity=config.sl_first_on_ambiguity,
        entry_on_next_bar=config.entry_on_next_bar,
        closed_candles_only=config.closed_candles_only,
        mark_open_at_backtest_end=config.mark_open_at_backtest_end,
    )
