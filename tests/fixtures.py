"""Shared synthetic data and config builders for offline pytest runs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from config.validator import validate_config
from config.settings import KraitosConfig


def write_config(tmp_path: Path, data: dict) -> Path:
    """Write a YAML config file and return its path."""
    path = tmp_path / "config.yaml"
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle)
    return path


def valid_config_data() -> dict:
    """Minimal valid Kraitos configuration dictionary."""
    return {
        "account": {"balance": 10000.0},
        "risk": {
            "per_trade_pct": 1.0,
            "max_daily_drawdown_pct": 3.0,
            "max_open_trades": 5,
        },
        "trading": {
            "symbols": ["EURUSD", "GBPUSD"],
            "timeframes": ["M5", "H1"],
            "spread_limits": {"default": 2.0, "EURUSD": 1.5},
            "sessions": [
                {
                    "name": "london",
                    "start": "08:00",
                    "end": "17:00",
                    "timezone": "UTC",
                    "days": ["mon", "tue", "wed", "thu", "fri"],
                }
            ],
            "live_enabled": False,
            "paper_enabled": True,
            "news_filter_enabled": True,
        },
    }


def load_validated_config(data: dict | None = None) -> KraitosConfig:
    """Return a typed config object without touching the filesystem."""
    return validate_config(data or valid_config_data())


def ohlcv_from_closes(
    closes: np.ndarray,
    *,
    freq: str = "h",
    spread: float = 1.5,
    volume: float = 200.0,
    noise: float = 0.0002,
) -> pd.DataFrame:
    """Build a normalized OHLCV DataFrame from close prices."""
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, close in enumerate(closes):
        open_ = close - noise / 2
        moment = start + (timedelta(hours=index) if freq == "h" else timedelta(minutes=index))
        rows.append(
            {
                "time": moment,
                "open": open_,
                "high": close + noise,
                "low": close - noise,
                "close": close,
                "tick_volume": volume,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def trending_closes(length: int = 80, step: float = 0.0008) -> np.ndarray:
    """Synthetic uptrend close prices."""
    return np.linspace(1.10, 1.10 + step * length, length)


def ranging_closes(length: int = 80) -> np.ndarray:
    """Synthetic range-bound close prices."""
    base = np.full(length, 1.10)
    oscillation = np.sin(np.linspace(0, 12, length)) * 0.0001
    return base + oscillation


def bullish_structure_closes(length: int = 60) -> np.ndarray:
    """Synthetic closes that form higher highs and higher lows."""
    steps = np.arange(length)
    return 1.10 + steps * 0.0005 + np.sin(steps * 0.8) * 0.002
