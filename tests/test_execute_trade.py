"""Tests for trade execution safety guards."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from broker.exceptions import LiveTradingDisabledError
from broker.models import MarketOrderResult
from config import load_config
from core.models import SymbolCycleState
from core.runtime import KraitosRuntime
from core.steps.execute_trade import execute_trade
from execution.models import EntryDecision
from logs.event_logger import KraitosEventLogger
from strategies.models import (
    HarvestDecision,
    MarketContext,
    RegimeResult,
    SwingPoint,
)


def _runtime(tmp_path: Path, *, live_enabled: bool, paper_enabled: bool) -> KraitosRuntime:
    config_path = tmp_path / "config" / "config.yaml"
    config_path.parent.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    text = source.read_text(encoding="utf-8")
    text = re.sub(
        r"live_enabled:\s*\w+",
        f"live_enabled: {str(live_enabled).lower()}",
        text,
    )
    text = re.sub(
        r"paper_enabled:\s*\w+",
        f"paper_enabled: {str(paper_enabled).lower()}",
        text,
    )
    config_path.write_text(text, encoding="utf-8")

    config = load_config(config_path)
    event_logger = KraitosEventLogger(tmp_path / "logs")
    runtime = KraitosRuntime.build(
        project_root=tmp_path,
        config=config,
        event_logger=event_logger,
    )
    runtime.connector.require_live_trading = MagicMock()
    return runtime


def _state(*, action: str = "enter_buy") -> SymbolCycleState:
    swing = SwingPoint(
        bar_index=1,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=1.10,
        kind="low",
    )
    structure = MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(swing,),
        swing_lows=(swing,),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )
    state = SymbolCycleState(
        symbol="EURUSD",
        trace_id="test",
        bid=1.1000,
        ask=1.10015,
        spread_pips=1.5,
        spread_limit=2.0,
        structure=structure,
        harvest=HarvestDecision(
            mode="conditional",
            allowed=True,
            target_pips=5.0,
            reason="ok",
        ),
        entry=EntryDecision(
            action=action,  # type: ignore[arg-type]
            explanation="test",
            lot_size=0.1,
        ),
        risk_approved=True,
        risk_lot_size=0.1,
        regime=RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
    )
    return state


def test_paper_execution_when_paper_enabled(tmp_path: Path):
    runtime = _runtime(tmp_path, live_enabled=False, paper_enabled=True)
    state = _state()
    assert execute_trade(runtime, state) is True
    assert state.executed is True
    assert state.execution_mode == "paper"


def test_live_mode_blocks_without_env_gate(tmp_path: Path):
    runtime = _runtime(tmp_path, live_enabled=True, paper_enabled=False)
    runtime.connector.require_live_trading.side_effect = LiveTradingDisabledError("blocked")
    state = _state()
    assert execute_trade(runtime, state) is False
    assert state.executed is False
    assert "blocked" in state.skip_reason.lower()


def test_live_execution_places_mt5_order(tmp_path: Path):
    runtime = _runtime(tmp_path, live_enabled=True, paper_enabled=False)
    runtime.connector.place_market_order = MagicMock(
        return_value=MarketOrderResult(
            ticket=12345,
            symbol="EURUSD",
            side="buy",
            volume=0.1,
            entry_price=1.10015,
            stop_loss=1.0980,
            take_profit=1.1040,
            deal=1,
            order=2,
            retcode=10009,
            comment="done",
        )
    )
    state = _state()
    assert execute_trade(runtime, state) is True
    assert state.executed is True
    assert state.execution_mode == "live"
    assert state.live_ticket == 12345
    runtime.connector.place_market_order.assert_called_once()


def test_live_execution_surfaces_order_errors(tmp_path: Path):
    from broker.exceptions import MT5OrderError

    runtime = _runtime(tmp_path, live_enabled=True, paper_enabled=False)
    runtime.connector.place_market_order = MagicMock(
        side_effect=MT5OrderError("broker rejected order")
    )
    state = _state()
    assert execute_trade(runtime, state) is False
    assert state.executed is False
    assert "rejected" in state.skip_reason.lower()
