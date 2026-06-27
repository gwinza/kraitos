from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from strategies.scalping_intelligence_engine import ScalpingIntelligenceEngine


def _frame(
    closes: list[float],
    *,
    volume: float = 120.0,
    spread: float = 1.0,
) -> pd.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    prev = closes[0]
    for idx, close in enumerate(closes):
        open_ = prev
        high = max(open_, close) + 0.00008
        low = min(open_, close) - 0.00008
        rows.append(
            {
                "time": start + timedelta(minutes=idx),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": volume + idx % 8,
                "spread": spread,
            }
        )
        prev = close
    return pd.DataFrame(rows)


def test_scalping_intelligence_extracts_strong_micro_context() -> None:
    closes = [1.1000 + i * 0.00005 for i in range(55)]
    closes.extend([closes[-1] - 0.00003 * i for i in range(1, 8)])
    closes.extend([closes[-1] + 0.00006 * i for i in range(1, 14)])
    frame = _frame(closes, volume=160.0, spread=0.8)

    result = ScalpingIntelligenceEngine().analyze(
        frame,
        symbol="EURUSD",
        spread_pips=0.8,
        spread_limit=2.0,
        market_phase="healthy_pullback",
        reversal_pressure=0.18,
    )

    assert result.micro_trend_state in {"strengthening_bullish", "bullish_but_fading"}
    assert result.scalp_quality_score >= 55
    assert result.scalp_expectancy_score >= 40
    assert result.suggested_action in {"scalp", "harvest"}
    assert "VWAP" in " ".join(result.evidence)
    assert result.thesis_questions is not None
    assert result.thesis_questions["why_move_immediately"]


def test_scalping_intelligence_warns_on_stretched_mean_reversion() -> None:
    closes = [1.1000 + i * 0.00003 for i in range(62)]
    closes.extend([closes[-1] + i * 0.00035 for i in range(1, 14)])
    frame = _frame(closes, volume=95.0, spread=1.8)

    result = ScalpingIntelligenceEngine().analyze(
        frame,
        symbol="EURUSD",
        spread_pips=1.8,
        spread_limit=2.0,
        market_phase="distribution",
        reversal_pressure=0.68,
    )

    assert result.mean_reversion_probability > 0.35
    assert result.micro_reversion_state in {
        "extension_warning",
        "overextended_mean_reversion_likely",
    }
    assert result.suggested_action in {"harvest", "avoid"}
