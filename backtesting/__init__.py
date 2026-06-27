"""Historical simulation and strategy performance replay."""

from backtesting.candle_resampler import build_multitimeframe_candles, build_symbol_candles
from backtesting.backtester import BacktestError, Backtester
from backtesting.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    Trade,
    TradeSignal,
)
from backtesting.performance_report import PerformanceMetrics, PerformanceReport

_LAZY_EXPORTS = {
    "BacktestEngine",
    "BacktestEngineConfig",
    "BacktestRunResult",
    "BacktestSkipStats",
    "SkipAnalyzer",
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        from backtesting.backtest_engine import (
            BacktestEngine,
            BacktestEngineConfig,
            BacktestRunResult,
            BacktestSkipStats,
        )

        exports = {
            "BacktestEngine": BacktestEngine,
            "BacktestEngineConfig": BacktestEngineConfig,
            "BacktestRunResult": BacktestRunResult,
            "BacktestSkipStats": BacktestSkipStats,
        }
        return exports[name]
    if name == "SkipAnalyzer":
        from backtesting.skip_analyzer import SkipAnalyzer

        return SkipAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestEngineConfig",
    "BacktestError",
    "BacktestMetrics",
    "BacktestResult",
    "BacktestRunResult",
    "BacktestSkipStats",
    "SkipAnalyzer",
    "build_multitimeframe_candles",
    "build_symbol_candles",
    "Backtester",
    "PerformanceMetrics",
    "PerformanceReport",
    "Trade",
    "TradeSignal",
]
