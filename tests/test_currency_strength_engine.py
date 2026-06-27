"""Tests for FX currency strength and relative-theme analysis."""

from __future__ import annotations

import pandas as pd

from portfolio.currency_strength_engine import CurrencyStrengthEngine, TRACKED_CURRENCIES
from portfolio.portfolio_construction import PortfolioConstructionEngine


def _candles(start: float, step: float, rows: int = 80) -> pd.DataFrame:
    closes = [start + step * i for i in range(rows)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="h"),
            "open": [price - step * 0.3 for price in closes],
            "high": [price + abs(step) * 0.8 + 0.0002 for price in closes],
            "low": [price - abs(step) * 0.8 - 0.0002 for price in closes],
            "close": closes,
            "tick_volume": [100 + i for i in range(rows)],
            "spread": [1.0] * rows,
        }
    )


def _multi_tf(start: float, step: float) -> dict[str, pd.DataFrame]:
    return {
        "H8": _candles(start, step),
        "H4": _candles(start, step * 0.8),
        "H1": _candles(start, step * 0.6),
        "M15": _candles(start, step * 0.4),
    }


def test_currency_strength_returns_all_tracked_currencies() -> None:
    engine = CurrencyStrengthEngine()
    snapshot = engine.evaluate(
        {
            "GBPUSD": _multi_tf(1.20, 0.0010),
            "USDJPY": _multi_tf(150.0, -0.05),
        }
    )

    assert set(snapshot.scores) == set(TRACKED_CURRENCIES)
    assert all(-10.0 <= score <= 10.0 for score in snapshot.scores.values())


def test_relative_strength_prefers_strong_base_over_weak_quote() -> None:
    engine = CurrencyStrengthEngine()
    snapshot = engine.evaluate({"GBPUSD": _multi_tf(1.20, 0.0010)})
    analysis = snapshot.pair_analyses["GBPUSD"]

    assert snapshot.scores["GBP"] > 0
    assert snapshot.scores["USD"] < 0
    assert analysis.pair_strength > 0
    assert analysis.preferred_side == "buy"
    assert analysis.trade_theme == "USD weakness"
    assert analysis.theme_confidence > 0.5


def test_jpy_strength_warns_against_buying_gbpjpy() -> None:
    engine = CurrencyStrengthEngine()
    snapshot = engine.evaluate(
        {
            "GBPUSD": _multi_tf(1.20, 0.0004),
            "GBPJPY": _multi_tf(190.0, -0.08),
        }
    )
    analysis = snapshot.pair_analyses["GBPJPY"]

    assert snapshot.scores["JPY"] > snapshot.scores["GBP"]
    assert analysis.pair_strength < 0
    assert analysis.preferred_side == "sell"


def test_portfolio_engine_records_theme_and_currency_memory(tmp_path) -> None:
    engine = PortfolioConstructionEngine(tmp_path)
    engine.currency_strength.update_symbol("GBPJPY", _multi_tf(190.0, -0.08))

    for _ in range(5):
        engine.record_trade_result(
            symbol="GBPJPY",
            mode="harvest",
            result="loss",
            r_multiple=-0.5,
            drawdown_pct=0.0,
            side="buy",
            trade_theme="JPY risk-off",
        )

    summary = engine.theme_memory.theme_performance["JPY risk-off"].to_dict()
    gbp = engine.theme_memory.currency_performance["GBP"].to_dict()
    jpy = engine.theme_memory.currency_performance["JPY"].to_dict()

    assert summary["trades"] == 5
    assert summary["expectancy"] < 0
    assert gbp["long_trades"] == 5
    assert jpy["short_trades"] == 5
    assert engine.theme_memory.confidence_adjustment("JPY risk-off") < 0
