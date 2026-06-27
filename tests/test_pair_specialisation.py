"""Tests for pair specialisation analytics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analytics import PairSpecialisationAnalyzer
from analytics.models import ClosedTradeRecord


def _trade(symbol: str, pnl: float, trade_id: str) -> ClosedTradeRecord:
    return ClosedTradeRecord(
        trade_id=trade_id,
        symbol=symbol,
        side="buy",
        exit_time=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        pnl=pnl,
        session="london",
    )


def _strong_trades(symbol: str = "EURUSD") -> list[ClosedTradeRecord]:
    return [
        _trade(symbol, 20.0, f"{symbol}-1"),
        _trade(symbol, 15.0, f"{symbol}-2"),
        _trade(symbol, 10.0, f"{symbol}-3"),
        _trade(symbol, -5.0, f"{symbol}-4"),
    ]


def _weak_trades(symbol: str = "GBPUSD") -> list[ClosedTradeRecord]:
    return [
        _trade(symbol, 10.0, f"{symbol}-1"),
        _trade(symbol, -20.0, f"{symbol}-2"),
        _trade(symbol, -15.0, f"{symbol}-3"),
        _trade(symbol, -10.0, f"{symbol}-4"),
    ]


def _quarantine_trades(symbol: str = "USDJPY") -> list[ClosedTradeRecord]:
    return [
        _trade(symbol, -20.0, f"{symbol}-1"),
        _trade(symbol, -25.0, f"{symbol}-2"),
        _trade(symbol, 5.0, f"{symbol}-3"),
        _trade(symbol, -30.0, f"{symbol}-4"),
        _trade(symbol, -15.0, f"{symbol}-5"),
    ]


def test_classifies_strong_pair():
    result = PairSpecialisationAnalyzer().analyze(_strong_trades())

    entry = result.pairs[0]
    assert entry.classification == "strong"
    assert entry.risk_multiplier == 1.0
    assert entry.trading_allowed is True


def test_classifies_weak_pair():
    result = PairSpecialisationAnalyzer().analyze(_weak_trades())

    entry = result.pairs[0]
    assert entry.classification == "weak"
    assert entry.risk_multiplier == 0.5
    assert entry.trading_allowed is True


def test_classifies_quarantined_pair():
    result = PairSpecialisationAnalyzer().analyze(_quarantine_trades())

    entry = result.pairs[0]
    assert entry.classification == "quarantined"
    assert entry.risk_multiplier == 0.0
    assert entry.trading_allowed is False


def test_unknown_symbol_defaults_to_normal():
    result = PairSpecialisationAnalyzer().analyze(
        _strong_trades(),
        symbols=["EURUSD", "AUDUSD"],
    )

    by_symbol = {entry.symbol: entry for entry in result.pairs}
    assert by_symbol["EURUSD"].classification == "strong"
    assert by_symbol["AUDUSD"].classification == "normal"
    assert "Insufficient" in by_symbol["AUDUSD"].reason


def test_saves_and_loads_json(tmp_path: Path):
    output = tmp_path / "pair_specialisation.json"
    analyzer = PairSpecialisationAnalyzer()
    result = analyzer.analyze(
        _strong_trades() + _weak_trades() + _quarantine_trades(),
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
    )
    analyzer.save(result, output)

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "symbols" in payload
    assert payload["symbols"]["USDJPY"]["classification"] == "quarantined"

    loaded = analyzer.load(output)
    assert len(loaded.pairs) == 3
