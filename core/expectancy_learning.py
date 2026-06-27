"""Post-trade learning loop — steps 5–7 of the expectancy doctrine."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from brain.market_story_engine import MarketStoryEngine
from core.helpers import pip_size_for_symbol, trade_pnl
from execution.models import ExitDecision as LegacyExitDecision, OpenTrade
from learning.early_entry_detector import get_early_entry_detector
from learning.trade_review_brain import ClosedTradeContext, TradeReviewBrain
from management.adaptive_exit_engine import ExitDecision as AdaptiveExitDecision, OpenTradeSnapshot
from management.stop_loss_forensics import StopForensicsInput, StopLossForensics
from execution.atr_timing_engine import compute_atr

if TYPE_CHECKING:
    from core.expectancy_doctrine import ExpectancyDoctrine
    from execution.models import PaperTrade
    from strategies.market_structure import MarketStructureAnalyzer
    from strategies.models import MarketContext


def _current_r(trade: OpenTrade, current_price: float) -> float:
    pip_size = pip_size_for_symbol(trade.symbol)
    if pip_size <= 0:
        return 0.0
    stop_pips = abs(trade.entry_price - trade.stop_loss) / pip_size
    if stop_pips <= 0:
        return 0.0
    if trade.side == "buy":
        move = (current_price - trade.entry_price) / pip_size
    else:
        move = (trade.entry_price - current_price) / pip_size
    return move / stop_pips


def map_adaptive_exit(
    adaptive: AdaptiveExitDecision,
    *,
    trade: OpenTrade,
    current_price: float,
) -> LegacyExitDecision:
    """Translate adaptive exit actions into legacy execution exit decisions."""
    action = adaptive.action
    reason = adaptive.reasoning

    if action == "HOLD":
        return LegacyExitDecision(action="hold_trade", reason=reason)

    if action == "TRAIL" and adaptive.stop_level is not None:
        return LegacyExitDecision(
            action="trail_stop",
            reason=reason,
            new_stop_loss=adaptive.stop_level,
        )

    if action == "SCALE_OUT":
        fraction = adaptive.scale_fraction or 0.5
        return LegacyExitDecision(
            action="scale_out",
            reason=reason,
            scale_fraction=fraction,
        )

    if action == "EXIT":
        r_val = _current_r(trade, current_price)
        if r_val <= -0.35:
            legacy = "cut_loss"
        elif r_val >= 0.8:
            legacy = "take_profit"
        else:
            legacy = "close_early"
        return LegacyExitDecision(action=legacy, reason=reason)

    return LegacyExitDecision(action="hold_trade", reason=reason or "Adaptive exit — hold")


class ExpectancyLearningLoop:
    """Adaptive exits plus personality memory and trade review on close."""

    def __init__(self, doctrine: ExpectancyDoctrine) -> None:
        self._doctrine = doctrine
        self._brain_story = MarketStoryEngine()
        self._stop_forensics = StopLossForensics()
        root = getattr(doctrine, "_project_root", None)
        self._early_entry = get_early_entry_detector(root)

    @property
    def doctrine(self) -> ExpectancyDoctrine:
        return self._doctrine

    def evaluate_adaptive_exit(
        self,
        *,
        trade: OpenTrade,
        current_price: float,
        candles: pd.DataFrame,
        structure: MarketContext | None,
        structure_analyzer: MarketStructureAnalyzer | None = None,
        symbol: str | None = None,
    ) -> LegacyExitDecision:
        """Step 5 — dynamic exit from live behaviour."""
        sym = symbol or trade.symbol
        story = None
        if structure is None and structure_analyzer is not None and len(candles) >= 30:
            structure = structure_analyzer.analyze(candles, symbol=sym, timeframe="M5")

        if len(candles) >= 30:
            story = self._brain_story.read(
                symbol=sym,
                timeframe="M5",
                candles=candles,
            )

        liquidity = ()
        invalidation = trade.invalidation_level
        if story is not None:
            liquidity = tuple(target.price for target in story.liquidity_targets)
            if invalidation is None:
                invalidation = story.invalidation_level

        snapshot = OpenTradeSnapshot(
            symbol=sym,
            side=trade.side,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            current_price=current_price,
            best_price=trade.best_price,
            invalidation_level=invalidation,
            liquidity_targets=liquidity,
            partial_taken=trade.partial_taken,
            bars_since_entry=trade.bars_since_entry,
        )
        adaptive = self._doctrine.adaptive_exit_engine.evaluate(
            trade=snapshot,
            candles=candles,
            structure=structure,
            story=story,
        )
        return map_adaptive_exit(adaptive, trade=trade, current_price=current_price)

    def on_trade_closed(
        self,
        trade: PaperTrade,
        *,
        exit_action: str = "unknown",
        project_root: Path | None = None,
        candles: pd.DataFrame | None = None,
        structure: MarketContext | None = None,
    ) -> None:
        """Steps 6–7 — personality memory update and mentor trade review."""
        if trade.exit_price is None or trade.status != "closed":
            return

        pip_size = pip_size_for_symbol(trade.symbol)
        stop_pips = abs(trade.entry_price - trade.stop_loss) / pip_size if pip_size > 0 else 0.0
        pnl = trade_pnl(
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            lot_size=trade.lot_size,
        )
        r_multiple = 0.0
        if stop_pips > 0:
            if trade.side == "buy":
                pips = (trade.exit_price - trade.entry_price) / pip_size
            else:
                pips = (trade.entry_price - trade.exit_price) / pip_size
            r_multiple = pips / stop_pips

        won = pnl > 0
        entry_type = getattr(trade, "entry_type", "unknown") or "unknown"
        story_direction = getattr(trade, "story_direction", "neutral") or "neutral"
        story_confidence = float(getattr(trade, "story_confidence", 0.0) or 0.0)
        story_narrative = getattr(trade, "story_narrative", "") or ""
        trace_id = getattr(trade, "trace_id", trade.trade_id) or trade.trade_id
        loss_class = getattr(trade, "loss_classification", "") or ""

        atr = 0.0
        story = None
        if candles is not None and len(candles) >= 14:
            atr = compute_atr(candles)
            story = self._brain_story.read(
                symbol=trade.symbol,
                timeframe="M5",
                candles=candles,
            )

        forensics = self._stop_forensics.classify(
            StopForensicsInput(
                symbol=trade.symbol,
                side=trade.side,  # type: ignore[arg-type]
                entry_price=trade.entry_price,
                stop_loss=trade.stop_loss,
                exit_price=trade.exit_price,
                exit_action=exit_action,
                r_multiple=r_multiple,
                atr=atr or pip_size * 12,
                structure=structure,
                story=story,
                candles_after_entry=candles,
            )
        )
        if forensics is not None and not loss_class:
            loss_class = forensics.classification

        had_confirmation = bool(getattr(trade, "patience_ready", False))
        if not loss_class and not won:
            loss_class = self._early_entry.classify_early_entry(
                side=trade.side,  # type: ignore[arg-type]
                story_direction=story_direction,
                entry_type=entry_type,
                had_confirmation=had_confirmation,
                r_multiple=r_multiple,
                bars_to_favourable=None,
            )

        self._early_entry.record_outcome(
            symbol=trade.symbol,
            side=trade.side,  # type: ignore[arg-type]
            entry_type=entry_type,
            loss_class=loss_class,
            r_multiple=r_multiple,
            won=won,
            had_confirmation=had_confirmation,
        )

        personality = self._doctrine.personality_memory
        if personality is not None:
            personality.record_outcome(
                trade_id=trace_id,
                symbol=trade.symbol,
                won=won,
                r_multiple=r_multiple,
                net_pl=pnl,
                entry_type=entry_type,
                exit_style=exit_action,
            )

        review = self._doctrine.trade_review
        if review is None:
            return

        target_pips = None
        if trade.take_profit is not None and pip_size > 0:
            target_pips = abs(trade.take_profit - trade.entry_price) / pip_size

        context = ClosedTradeContext(
            trade_id=trace_id,
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            stop_loss=trade.stop_loss,
            r_multiple=r_multiple,
            net_pl=pnl,
            won=won,
            take_profit=trade.take_profit,
            entry_type=entry_type,
            exit_action=exit_action,
            bars_held=trade.bars_since_entry,
            story_direction=story_direction,
            story_confidence=story_confidence,
            story_narrative=story_narrative,
            invalidation_level=trade.invalidation_level,
            stop_pips=stop_pips or None,
            target_pips=target_pips,
            loss_classification=loss_class,
            stop_forensics=forensics.to_dict() if forensics else None,
        )
        review.review(context)

        if project_root is not None:
            from council.cognitive_brain import CognitiveBrain
            from council.cognitive_learning import CognitiveLearningLoop
            from council.cognitive_models import CIODecision

            snapshot = getattr(trade, "cognitive_snapshot", "") or ""
            decision = CIODecision.from_snapshot_json(snapshot, symbol=trade.symbol)
            if decision is None:
                decision = CognitiveBrain(project_root).latest(trade.symbol)
            if decision is not None:
                CognitiveLearningLoop(CognitiveBrain(project_root).memory).review_trade(
                    decision=decision,
                    won=won,
                    r_multiple=r_multiple,
                    side=trade.side,
                )

            from learning.picture_review import PictureReviewEngine

            st_snapshot = (
                getattr(trade, "market_mind_snapshot", "")
                or getattr(trade, "storyteller_snapshot", "")
                or ""
            )
            st_decision = PictureReviewEngine.decision_from_snapshot(
                st_snapshot,
                symbol=trade.symbol,
            )
            if st_decision is not None:
                PictureReviewEngine(project_root).review_trade(
                    decision=st_decision,
                    won=won,
                    r_multiple=r_multiple,
                    side=trade.side,
                    exit_reason=exit_action,
                )
        _ = project_root


def get_expectancy_learning(runtime: object) -> ExpectancyLearningLoop:
    """Build or return cached learning loop for exit and post-trade updates."""
    cached = getattr(runtime, "expectancy_learning", None)
    if cached is not None:
        return cached

    from core.expectancy_doctrine import build_expectancy_doctrine
    from core.risk_controller import RiskController

    project_root = getattr(runtime, "project_root")
    config = getattr(runtime, "config")
    risk_controller = RiskController(
        config=config,
        risk_manager=getattr(runtime, "risk_manager"),
        paper_trader=getattr(runtime, "paper_trader"),
        project_root=project_root,
        connector=getattr(runtime, "connector", None),
    )
    doctrine = build_expectancy_doctrine(
        project_root=project_root,
        config=config,
        risk_controller=risk_controller,
    )
    loop = ExpectancyLearningLoop(doctrine)
    setattr(runtime, "expectancy_learning", loop)
    return loop
