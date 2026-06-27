"""Integration tests for live intelligence wiring."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.offline

from analytics.journal_bridge import get_learning_loop, journal_entry_to_enriched_record
from brains.intelligence_integration import IntelligenceIntegrator
from brains.models import TradeCandidate
from paper_trading.virtual_account import TradeJournalEntry
from strategies.decision_architecture import DecisionArchitecture
from strategies.models import (
    HarvestDecision,
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    RegimeResult,
    SwingPoint,
    TimeframeBiasDetail,
)


def _candles() -> dict[str, pd.DataFrame]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    price = 1.1000
    for idx in range(80):
        close = price + idx * 0.00012
        rows.append(
            {
                "time": start.replace(hour=idx % 24),
                "open": close - 0.00005,
                "high": close + 0.00020,
                "low": close - 0.00020,
                "close": close,
                "tick_volume": 100 + idx,
                "spread": 1.0,
            }
        )
    frame = pd.DataFrame(rows)
    return {"H1": frame, "M5": frame.tail(40), "M1": frame.tail(20)}


def _bias() -> MultiTimeframeBiasResult:
    layers = (
        TimeframeBiasDetail("H4", "bullish", 0.55, "macro"),
        TimeframeBiasDetail("H1", "bullish", 0.50, "macro"),
    )
    return MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.72,
        explanation="test",
        layers=layers,
    )


def _structure() -> MarketContext:
    swing = SwingPoint(
        bar_index=1,
        time=pd.Timestamp("2025-01-10", tz="UTC"),
        price=1.10,
        kind="low",
    )
    return MarketContext(
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


def _candidate() -> TradeCandidate:
    return TradeCandidate(
        symbol="EURUSD",
        trace_id="trace-1",
        bid=1.1050,
        ask=1.1052,
        spread_pips=1.2,
        spread_limit=3.0,
        candles=_candles(),
        regime=RegimeResult(regime="trending", confidence=0.7, reason="test"),
        bias=_bias(),
        structure=_structure(),
        harvest=HarvestDecision(allowed=True, reason="ok", mode="full", target_pips=24.0),
        micro_scalp=MicroScalpSignal(action="no_trade", reason="none", target_pips=8.0),
    )


class TestIntelligenceIntegrator:
    def test_enrich_market_reading_populates_candidate(self) -> None:
        integrator = IntelligenceIntegrator()
        candidate = _candidate()
        bundle = integrator.enrich_market_reading(
            candidate,
            evaluation_moment=datetime(2025, 1, 1, 14, tzinfo=timezone.utc),
        )
        assert candidate.session_intelligence is not None
        assert candidate.news_context is not None
        assert bundle.session_intelligence is not None

    def test_participation_decision_attached(self) -> None:
        integrator = IntelligenceIntegrator()
        candidate = _candidate()
        integrator.enrich_market_reading(candidate)
        decision = integrator.evaluate_participation(
            symbol="EURUSD",
            side="buy",
            candidate=candidate,
            market_story="bullish continuation",
            story_clear=True,
            opportunity_type="continuation",
            reward_risk=1.8,
            invalidation_level=1.1020,
            is_tradeable=True,
        )
        assert candidate.conviction_assessment is not None
        assert candidate.opportunity_assessment is not None
        assert candidate.decision_result is decision
        assert decision.participation_mode in {
            "avoid",
            "watchlist",
            "probe",
            "normal",
            "aggressive",
        }

    def test_entry_execution_quality_attached(self) -> None:
        integrator = IntelligenceIntegrator()
        candidate = _candidate()
        integrator.enrich_market_reading(candidate)
        result = integrator.evaluate_entry_execution(
            symbol="EURUSD",
            side="buy",
            spread_pips=1.2,
            spread_limit=3.0,
            stop_pips=12.0,
            target_pips=24.0,
            candidate=candidate,
        )
        assert candidate.execution_quality is result
        assert 0 <= result.execution_score <= 100


class TestDecisionArchitectureParticipation:
    def test_evaluate_participation_without_thesis(self) -> None:
        candidate = _candidate()
        arch = DecisionArchitecture()
        decision = arch.evaluate_participation(
            symbol="EURUSD",
            side="buy",
            bias=candidate.bias,
            structure=candidate.structure,
            market_story="trend continuation",
            story_clear=True,
            reward_risk=2.0,
            is_tradeable=True,
        )
        assert decision.should_participate or decision.participation_mode == "avoid"
        assert decision.effective_size_multiplier > 0


class TestJournalBridge:
    def test_journal_entry_to_enriched_record(self) -> None:
        snapshot = (
            '{"thesis_confidence":0.72,'
            '"intelligence":{"conviction":{"conviction_score":68,'
            '"conviction_class":"moderate","participation_mode":"normal"},'
            '"primary_regime":"trending","session":"overlap"}}'
        )
        entry = TradeJournalEntry(
            trade_id="t-1",
            event_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            symbol="EURUSD",
            timeframe="H1",
            direction="buy",
            entry=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            confidence=0.72,
            mode="harvest",
            result="win",
            profit_loss=120.0,
            reason="take_profit",
            balance=10120.0,
            equity=10120.0,
            lot_size=0.10,
            r_multiple=1.5,
            thesis_snapshot=snapshot,
        )
        enriched = journal_entry_to_enriched_record(entry)
        assert enriched.conviction_score == 68.0
        assert enriched.participation_mode == "normal"
        assert enriched.primary_regime == "trend"

        loop = get_learning_loop()
        before = len(loop.enriched_trades())
        loop.record_closed_trade(entry)
        assert len(loop.enriched_trades()) == before + 1
