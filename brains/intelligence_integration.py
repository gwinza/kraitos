"""Central intelligence enrichment for live TraderBrain evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from strategies.decision_architecture import DecisionArchitecture, ParticipationDecision
from strategies.execution_quality_engine import ExecutionQualityEngine, ExecutionQualityResult
from strategies.false_breakout_engine import FalseBreakoutEngine
from strategies.institutional_structure_engine import InstitutionalStructureEngine
from strategies.liquidity_sweep_engine import LiquiditySweepEngine
from strategies.market_lifecycle_engine import MarketLifecycleEngine
from strategies.news_context_engine import NewsContextEngine
from strategies.reversal_pressure_engine import ReversalPressureEngine
from strategies.session_intelligence_engine import SessionIntelligenceEngine
from strategies.trade_maturity_engine import TradeMaturityEngine, TradeMaturityResult

if TYPE_CHECKING:
    from brains.models import TradeCandidate


@dataclass(frozen=True)
class MarketReadingBundle:
    """Institutional and contextual market reading outputs."""

    institutional_structure: object | None = None
    liquidity_sweep: object | None = None
    false_breakout: object | None = None
    market_lifecycle: object | None = None
    reversal_pressure: object | None = None
    session_intelligence: object | None = None
    news_context: object | None = None

    def to_dict(self) -> dict:
        payload: dict = {}
        for key in (
            "institutional_structure",
            "liquidity_sweep",
            "false_breakout",
            "market_lifecycle",
            "reversal_pressure",
            "session_intelligence",
            "news_context",
        ):
            value = getattr(self, key)
            if value is not None and hasattr(value, "to_dict"):
                payload[key] = value.to_dict()
        return payload


class IntelligenceIntegrator:
    """Run market-reading, participation, and execution-quality engines."""

    def __init__(
        self,
        *,
        structure_timeframe: str = "H1",
        decision: DecisionArchitecture | None = None,
        execution_quality: ExecutionQualityEngine | None = None,
    ) -> None:
        self._structure_tf = structure_timeframe
        self._decision = decision or DecisionArchitecture()
        self._execution = execution_quality or ExecutionQualityEngine()
        self._institutional = InstitutionalStructureEngine()
        self._liquidity_sweep = LiquiditySweepEngine()
        self._false_breakout = FalseBreakoutEngine()
        self._lifecycle = MarketLifecycleEngine()
        self._reversal = ReversalPressureEngine()
        self._session = SessionIntelligenceEngine()
        self._news = NewsContextEngine()
        self._maturity = TradeMaturityEngine()

    def enrich_market_reading(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment: datetime | None = None,
    ) -> MarketReadingBundle:
        """Attach institutional and contextual intelligence to a candidate."""
        frame = self._structure_frame(candidate.candles)
        symbol = candidate.symbol

        institutional = None
        liquidity = None
        false_break = None
        lifecycle = None
        reversal = None

        if frame is not None and not frame.empty:
            try:
                institutional = self._institutional.analyze(
                    frame, symbol=symbol, timeframe=self._structure_tf
                )
            except Exception:
                institutional = None
            try:
                liquidity = self._liquidity_sweep.analyze(frame, symbol=symbol)
            except Exception:
                liquidity = None
            try:
                false_break = self._false_breakout.analyze(frame, symbol=symbol)
            except Exception:
                false_break = None
            try:
                lifecycle = self._lifecycle.analyze(frame, symbol=symbol)
            except Exception:
                lifecycle = None
            try:
                reversal = self._reversal.analyze(
                    frame, symbol=symbol, timeframe=self._structure_tf
                )
            except Exception:
                reversal = None

        session = self._session.analyze(symbol=symbol, at_time=evaluation_moment)
        news = self._news.analyze(events=None, symbol=symbol, at_time=evaluation_moment)

        candidate.institutional_structure = institutional
        candidate.liquidity_sweep = liquidity
        candidate.false_breakout = false_break
        candidate.market_lifecycle = lifecycle
        candidate.reversal_pressure = reversal
        candidate.session_intelligence = session
        candidate.news_context = news

        return MarketReadingBundle(
            institutional_structure=institutional,
            liquidity_sweep=liquidity,
            false_breakout=false_break,
            market_lifecycle=lifecycle,
            reversal_pressure=reversal,
            session_intelligence=session,
            news_context=news,
        )

    def evaluate_participation(
        self,
        *,
        symbol: str,
        side: str,
        candidate: TradeCandidate,
        market_story: str,
        story_clear: bool,
        opportunity_type: str | None,
        reward_risk: float,
        invalidation_level: float | None,
        is_tradeable: bool,
    ) -> ParticipationDecision:
        trend_quality_score = None
        if candidate.trend_quality is not None:
            trend_quality_score = candidate.trend_quality.trend_quality_score

        decision = self._decision.evaluate_participation(
            symbol=symbol,
            side=side,
            bias=candidate.bias,
            structure=candidate.structure,
            market_story=market_story,
            story_clear=story_clear,
            opportunity_type=opportunity_type,
            candles=candidate.candles,
            momentum=candidate.micro_scalp,
            reward_risk=reward_risk,
            invalidation_level=invalidation_level,
            trend_quality_score=trend_quality_score,
            is_tradeable=is_tradeable,
        )
        candidate.opportunity_assessment = decision.opportunity
        candidate.conviction_assessment = decision.conviction
        candidate.decision_result = decision
        return decision

    def evaluate_entry_execution(
        self,
        *,
        symbol: str,
        side: str,
        spread_pips: float,
        spread_limit: float,
        stop_pips: float,
        target_pips: float,
        candidate: TradeCandidate,
    ) -> ExecutionQualityResult:
        m5 = candidate.candles.get("M5")
        candles = m5 if isinstance(m5, pd.DataFrame) else self._structure_frame(candidate.candles)
        primary_regime = None
        if candidate.market_regime_intelligence is not None:
            primary_regime = getattr(
                candidate.market_regime_intelligence, "primary_regime", None
            ) or getattr(candidate.market_regime_intelligence, "market_regime", None)
        range_location = None
        if candidate.range_intelligence is not None:
            range_location = getattr(candidate.range_intelligence, "price_location", None)

        result = self._execution.evaluate_entry(
            symbol=symbol,
            side=side,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            stop_pips=stop_pips,
            target_pips=target_pips,
            candles=candles,
            structure=candidate.structure,
            momentum=candidate.micro_scalp,
            primary_regime=str(primary_regime) if primary_regime else None,
            range_location=str(range_location) if range_location else None,
        )
        candidate.execution_quality = result
        return result

    def evaluate_trade_maturity(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_price: float | None,
        setup_kind: str,
        candidate: TradeCandidate,
        story_clear: bool = False,
        invalidation_level: float | None = None,
        conviction_score: float | None = None,
        execution_score: int | None = None,
    ) -> TradeMaturityResult:
        from core.helpers import pip_size_for_symbol

        pip_size = pip_size_for_symbol(symbol)
        exec_score = execution_score
        if exec_score is None and candidate.execution_quality is not None:
            exec_score = int(getattr(candidate.execution_quality, "execution_score", 50) or 50)

        market_phase = ""
        trend_quality = 50
        if candidate.trend_quality is not None:
            market_phase = str(getattr(candidate.trend_quality, "trend_phase", "") or "")
            trend_quality = int(getattr(candidate.trend_quality, "trend_quality_score", 50) or 50)

        result = self._maturity.evaluate_entry(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            spread_pips=candidate.spread_pips,
            pip_size=pip_size,
            setup_kind=setup_kind,
            bias=candidate.bias,
            structure=candidate.structure,
            candles=candidate.candles,
            momentum=candidate.micro_scalp,
            invalidation_level=invalidation_level,
            institutional_structure=candidate.institutional_structure,
            range_intelligence=candidate.range_intelligence,
            execution_score=exec_score,
            conviction_score=conviction_score,
            story_clear=story_clear,
            market_phase=market_phase,
            trend_quality=trend_quality,
        )
        candidate.trade_maturity = result
        candidate.location_quality = result.location
        candidate.timing_quality = result.timing
        candidate.market_acceptance = result.acceptance
        return result

    def evaluate_open_maturity(
        self,
        *,
        side: str,
        current_r: float,
        setup_kind: str,
        candidate: TradeCandidate | None = None,
        trend_health: int = 50,
    ) -> TradeMaturityResult:
        timing = getattr(candidate, "timing_quality", None) if candidate else None
        acceptance = getattr(candidate, "market_acceptance", None) if candidate else None
        return self._maturity.evaluate_open(
            side=side,
            current_r=current_r,
            setup_kind=setup_kind,
            acceptance=acceptance,
            timing=timing,
            trend_health=trend_health,
        )

    @staticmethod
    def session_size_multiplier(candidate: TradeCandidate) -> float:
        session = candidate.session_intelligence
        if session is None:
            return 1.0
        quality = int(getattr(session, "session_quality", 50) or 50)
        if quality >= 85:
            return 1.0
        if quality >= 70:
            return 0.95
        if quality >= 55:
            return 0.85
        return 0.75

    @staticmethod
    def news_size_multiplier(candidate: TradeCandidate) -> float:
        news = candidate.news_context
        if news is None:
            return 1.0
        return float(getattr(news, "size_multiplier", 1.0) or 1.0)

    def _structure_frame(self, candles: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
        for key in (self._structure_tf, "H1", "M15", "M5"):
            frame = candles.get(key)
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                return frame
        return None


__all__ = ["IntelligenceIntegrator", "MarketReadingBundle"]
