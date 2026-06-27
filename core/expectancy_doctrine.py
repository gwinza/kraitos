"""Expectancy doctrine — professional portfolio manager pipeline.

Kraitos optimises for expected value, profit factor, average R, equity growth,
and drawdown control — not win rate, trade count, or indicator agreement.

Pipeline order:
  1. Market Story Engine
  2. Patience Engine
  3. Conviction Position Sizing
  4. Trade Execution (delegated to entry/risk layers)
  5. Adaptive Exit Engine (see expectancy_learning)
  6. Pair Personality Memory update
  7. Trade Review Brain update
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pandas as pd

from brain.market_story_engine import MarketStory, MarketStoryEngine
from config.settings import KraitosConfig
from core.helpers import is_in_trading_session, pip_size_for_symbol
from execution.patience_engine import (
    EntryOpportunity,
    PatienceDecision,
    PatienceEngine,
)
from intelligence.harvest_opportunity_score import infer_session
from learning.pair_personality_memory import PairPersonalityMemory, get_pair_personality_memory
from learning.trade_review_brain import TradeReviewBrain
from management.adaptive_exit_engine import AdaptiveExitEngine
from risk.conviction_position_sizing import ConvictionPositionSizer, ConvictionSizing, SetupExpectancy

if TYPE_CHECKING:
    from core.risk_controller import RiskController
    from intelligence.market_story_engine import MarketStoryResult
    from strategies.models import MarketContext

from core.expectancy_gates import (
    MIN_EXPECTED_R,
    MIN_STORY_CONFIDENCE,
    participation_unlock,
    story_actionable,
)


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class ExpectancyDoctrineConfig:
    """Thresholds for expectancy-first participation."""

    min_story_confidence: float = MIN_STORY_CONFIDENCE
    min_expected_r: float = MIN_EXPECTED_R
    story_timeframe: str = "M5"


class ExpectancyDoctrine:
    """Orchestrates story → patience → conviction sizing and learning services."""

    def __init__(
        self,
        *,
        project_root: Path | None,
        config: KraitosConfig,
        risk_controller: RiskController,
        doctrine_config: ExpectancyDoctrineConfig | None = None,
    ) -> None:
        self._config = config
        self._risk_controller = risk_controller
        self._project_root = project_root
        self._doctrine = doctrine_config or ExpectancyDoctrineConfig()
        self._brain_story = MarketStoryEngine()
        self._patience = PatienceEngine(project_root=project_root)
        limits = risk_controller.risk_manager.limits
        self._sizer = ConvictionPositionSizer(limits=limits)
        self._adaptive_exit = AdaptiveExitEngine()
        self._personality: PairPersonalityMemory | None = get_pair_personality_memory(project_root)
        self._review: TradeReviewBrain | None = (
            TradeReviewBrain(project_root, personality_memory=self._personality)
            if project_root
            else None
        )

    @property
    def personality_memory(self) -> PairPersonalityMemory | None:
        return self._personality

    @property
    def trade_review(self) -> TradeReviewBrain | None:
        return self._review

    @property
    def adaptive_exit_engine(self) -> AdaptiveExitEngine:
        return self._adaptive_exit

    # --- Step 1: Market Story Engine ---

    def read_market_story(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        indicator_interpretation: object | None = None,
    ) -> MarketStory | None:
        """Primary narrative read — structure and liquidity lead; indicators assist only."""
        timeframe = self._resolve_story_timeframe(candles)
        if timeframe is None:
            return None
        frame = candles[timeframe]
        if frame is None or frame.empty:
            return None
        return self._brain_story.read(
            symbol=symbol,
            timeframe=timeframe,
            candles=frame,
            indicator_interpretation=indicator_interpretation,
        )

    # --- Step 2: Patience Engine ---

    def evaluate_patience(
        self,
        *,
        story: MarketStory,
        structure: MarketContext,
        candles: pd.DataFrame | None,
        bid: float,
        ask: float,
        symbol: str,
    ) -> PatienceDecision:
        if candles is None or candles.empty:
            return PatienceDecision(
                False,
                None,
                "No M5 candles — patience engine waiting for price structure",
            )
        return self._patience.evaluate(
            story=story,
            candles=candles,
            structure=structure,
            bid=bid,
            ask=ask,
            symbol=symbol,
            timeframe=self._doctrine.story_timeframe,
        )

    # --- Step 3: Conviction Position Sizing ---

    def size_by_conviction(
        self,
        *,
        symbol: str,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float | None,
        story: MarketStory | None,
        structure: MarketContext | None,
        entry_opportunity: EntryOpportunity | None,
        setup_key: str = "",
        evaluation_moment: datetime | None = None,
    ) -> ConvictionSizing:
        balance = self._risk_controller.portfolio_snapshot().balance
        key = (symbol.strip().upper(), "harvest")
        streak_state = self._risk_controller.drawdown_risk._loss_streaks.get(key)
        loss_streak = streak_state.consecutive_losses if streak_state else 0
        dd_risk = getattr(self._risk_controller, "drawdown_risk", None)
        recovery = bool(getattr(dd_risk, "recovery_mode", False)) if dd_risk else False

        setup_expectancy = self._personality_expectancy(symbol, setup_key, entry_opportunity)
        sizing = self._sizer.size(
            symbol=symbol,
            side=side,
            balance=balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            story=story,
            structure=structure,
            entry_opportunity=entry_opportunity,
            setup_expectancy=setup_expectancy,
            setup_key=setup_key,
            loss_streak=loss_streak,
            recovery_mode=recovery,
        )
        if entry_opportunity is not None and self._personality is not None:
            boost = self._personality.entry_type_boost(symbol, entry_opportunity.entry_type)
            if abs(boost - 1.0) > 0.01:
                adjusted = round(max(0.01, sizing.position_size * boost), 2)
                return ConvictionSizing(
                    score=sizing.score,
                    risk_percent=sizing.risk_percent,
                    position_size=adjusted,
                    explanation=f"{sizing.explanation} | Personality edge ×{boost:.2f}",
                    components=sizing.components,
                )
        _ = evaluation_moment
        return sizing

    # --- Expectancy gates (replace story_clear / indicator vetoes) ---

    @staticmethod
    def story_actionable(
        brain_story: MarketStory | None,
        legacy_story: MarketStoryResult | None,
    ) -> bool:
        return story_actionable(brain_story, legacy_story)

    def harvest_unlock(
        self,
        *,
        harvest_allowed: bool,
        brain_story: MarketStory | None,
        legacy_story: MarketStoryResult | None,
        harvest_score_band: str | None,
        expected_r: float | None = None,
    ) -> bool:
        if harvest_allowed:
            return True
        if self.story_actionable(brain_story, legacy_story):
            return True
        if harvest_score_band not in {None, "no_harvest"}:
            return True
        if expected_r is not None and expected_r >= self._doctrine.min_expected_r:
            return True
        return False

    @staticmethod
    def expected_r_from_levels(
        *,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float | None,
        spread_pips: float,
        symbol: str,
    ) -> float | None:
        pip_size = pip_size_for_symbol(symbol)
        if pip_size <= 0 or take_profit is None:
            return None
        stop_pips = abs(entry_price - stop_loss) / pip_size
        if stop_pips <= 0:
            return None
        target_pips = abs(take_profit - entry_price) / pip_size
        return max(0.0, target_pips - spread_pips) / stop_pips

    def record_pending_entry(
        self,
        *,
        trade_id: str,
        symbol: str,
        entry_type: str,
        evaluation_moment: datetime | None = None,
    ) -> None:
        if self._personality is None:
            return
        session = "any"
        if evaluation_moment is not None:
            session = infer_session(evaluation_moment.hour)
        if not is_in_trading_session(self._config, evaluation_moment):
            session = f"off_session_{session}"
        self._personality.record_pending_entry(
            trade_id=trade_id,
            symbol=symbol,
            entry_type=entry_type,
            session=session,
        )

    def _resolve_story_timeframe(self, candles: dict[str, pd.DataFrame]) -> str | None:
        preferred = self._doctrine.story_timeframe
        order = (preferred, "M15", "H1", "M1")
        for tf in order:
            frame = candles.get(tf)
            if frame is not None and len(frame) >= 30:
                return tf
        return None

    def _personality_expectancy(
        self,
        symbol: str,
        setup_key: str,
        entry_opportunity: EntryOpportunity | None,
    ) -> SetupExpectancy:
        if self._personality is None:
            return SetupExpectancy(setup_label=setup_key)
        profile = self._personality.get_profile(symbol)
        key = setup_key or (
            entry_opportunity.entry_type if entry_opportunity is not None else "unknown"
        )
        stats = profile.setup_stats.get(key) or profile.entry_type_stats.get(key)
        if stats is None or stats.trades < 4:
            return SetupExpectancy(setup_label=key)
        return SetupExpectancy(
            average_r=stats.average_r,
            win_rate=stats.win_rate,
            profit_factor=stats.profit_factor,
            sample_size=stats.trades,
            setup_label=key,
        )


def build_expectancy_doctrine(
    *,
    project_root: Path | None,
    config: KraitosConfig,
    risk_controller: RiskController,
) -> ExpectancyDoctrine:
    """Factory for TraderBrain and runtime wiring."""
    return ExpectancyDoctrine(
        project_root=project_root,
        config=config,
        risk_controller=risk_controller,
    )
