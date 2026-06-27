"""Patience engine — wait for professional entry locations, never chase price.

After a valid market story is detected, Kraitos waits for price to offer a
logical entry. Timing is driven by structure, volatility, and price behaviour —
never fixed clock delays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from brain.market_story_engine import MarketStory
from core.helpers import pip_size_for_symbol
from execution.atr_timing_engine import compute_atr
from learning.early_entry_detector import EarlyEntryDetector, get_early_entry_detector
from risk.stop_placement import place_structural_stop
from strategies.liquidity_sweep_engine import LiquiditySweepEngine, LiquiditySweepEngineError
from strategies.market_reading_utils import validate_candles
from strategies.models import MarketContext

EntryType = Literal[
    "pullback_into_value",
    "retest_broken_structure",
    "liquidity_sweep_rejection",
    "compression_before_expansion",
]

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class EntryOpportunity:
    """A patient, professional entry location aligned with the market story."""

    entry_price: float
    entry_type: EntryType
    confidence: float
    stop_loss: float
    explanation: str
    side: Side = "buy"

    def to_dict(self) -> dict:
        return {
            "entry_price": round(self.entry_price, 5),
            "entry_type": self.entry_type,
            "confidence": round(self.confidence, 2),
            "stop_loss": round(self.stop_loss, 5),
            "explanation": self.explanation,
            "side": self.side,
        }


@dataclass(frozen=True)
class PatienceDecision:
    """Whether a professional entry is available now."""

    ready: bool
    opportunity: EntryOpportunity | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "opportunity": self.opportunity.to_dict() if self.opportunity else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PatienceEngineConfig:
    """Volatility-normalised patience thresholds — not time-based."""

    min_story_confidence: float = 38.0
    max_stop_atr: float = 4.50
    min_stop_atr: float = 0.35
    max_stop_pips: float = 120.0
    min_confirmation_strength: float = 55.0
    max_structure_distance_atr: float = 1.85
    late_entry_progress: float = 0.72
    vertical_momentum_atr: float = 1.55
    extended_candle_atr: float = 1.35
    pullback_retrace_min: float = 0.25
    pullback_retrace_max: float = 0.62
    compression_range_atr: float = 0.85
    retest_tolerance_atr: float = 0.45
    min_candles: int = 25


class PatienceEngine:
    """Wait for structure-backed entries instead of chasing momentum."""

    def __init__(
        self,
        config: PatienceEngineConfig | None = None,
        *,
        early_entry_detector: EarlyEntryDetector | None = None,
        project_root: object | None = None,
    ) -> None:
        self.config = config or PatienceEngineConfig()
        self._sweep = LiquiditySweepEngine()
        self._early_entry = early_entry_detector
        if self._early_entry is None and project_root is not None:
            from pathlib import Path

            root = project_root if isinstance(project_root, Path) else Path(str(project_root))
            self._early_entry = get_early_entry_detector(root)

    def evaluate(
        self,
        *,
        story: MarketStory,
        candles: pd.DataFrame,
        structure: MarketContext,
        bid: float,
        ask: float,
        symbol: str,
        timeframe: str = "M5",
    ) -> PatienceDecision:
        """
        Return an EntryOpportunity when price offers a professional location.

        When the story is valid but price has not yet set up, returns ready=False
        with a behavioural wait reason (never a timer).
        """
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().upper()

        story_wait = self._story_gate(story)
        if story_wait is not None:
            return story_wait

        side: Side = "buy" if story.direction == "bullish" else "sell"
        entry_price = ask if side == "buy" else bid

        try:
            frame = validate_candles(
                candles, min_candles=self.config.min_candles, engine="PatienceEngine"
            )
        except ValueError as exc:
            return PatienceDecision(False, None, str(exc))

        atr = compute_atr(frame)
        if atr <= 0:
            return PatienceDecision(False, None, "ATR unavailable — cannot size entry patience")

        reject = self._reject_chase(
            side=side,
            frame=frame,
            story=story,
            structure=structure,
            entry_price=entry_price,
            atr=atr,
            symbol=symbol,
        )
        if reject is not None:
            return reject

        candidates = self._scan_entry_types(
            side=side,
            frame=frame,
            story=story,
            structure=structure,
            entry_price=entry_price,
            atr=atr,
            symbol=symbol,
            timeframe=timeframe,
        )
        confirmed = [
            opp
            for opp in candidates
            if self._confirmation_strength(
                opp.entry_type,
                side=side,
                frame=frame,
                story=story,
                structure=structure,
                atr=atr,
                symbol=symbol,
                timeframe=timeframe,
            )
            >= self.config.min_confirmation_strength
        ]
        if not confirmed:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason=(
                    f"Story valid ({story.direction}, {story.confidence:.0f}%) — "
                    "setup detected but confirmation missing "
                    "(need rejection wick, failed continuation, sweep reclaim, "
                    "retest with reduced momentum, or compression)"
                ),
            )

        best = max(confirmed, key=lambda item: item.confidence)

        if self._early_entry is not None:
            strength = self._confirmation_strength(
                best.entry_type,
                side=side,
                frame=frame,
                story=story,
                structure=structure,
                atr=atr,
                symbol=symbol,
                timeframe=timeframe,
            )
            delay = self._early_entry.evaluate_delay(
                symbol=symbol,
                side=side,
                entry_type=best.entry_type,
                confirmation_strength=strength,
            )
            if delay.delay:
                return PatienceDecision(
                    ready=False,
                    opportunity=None,
                    reason=delay.reason,
                )
            if delay.confidence_penalty > 0:
                best = EntryOpportunity(
                    entry_price=best.entry_price,
                    entry_type=best.entry_type,
                    confidence=max(50.0, best.confidence - delay.confidence_penalty),
                    stop_loss=best.stop_loss,
                    explanation=best.explanation,
                    side=best.side,
                )

        stop_loss = place_structural_stop(
            side=side,
            entry_price=entry_price,
            structure=structure,
            symbol=symbol,
            atr=atr,
            story=story,
            entry_type=best.entry_type,
            frame=frame,
        )
        stop_issue = self._stop_quality(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            atr=atr,
            symbol=symbol,
        )
        if stop_issue is not None:
            return stop_issue

        opportunity = EntryOpportunity(
            entry_price=entry_price,
            entry_type=best.entry_type,
            confidence=best.confidence,
            stop_loss=stop_loss,
            explanation=best.explanation,
            side=side,
        )
        return PatienceDecision(
            ready=True,
            opportunity=opportunity,
            reason=opportunity.explanation,
        )

    def _story_gate(self, story: MarketStory) -> PatienceDecision | None:
        if story.direction == "neutral":
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="No directional story — patience engine idle",
            )
        if story.confidence < self.config.min_story_confidence:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason=(
                    f"Story confidence {story.confidence:.0f}% below "
                    f"{self.config.min_story_confidence:.0f}% — wait for clarity"
                ),
            )
        return None

    def _reject_chase(
        self,
        *,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        structure: MarketContext,
        entry_price: float,
        atr: float,
        symbol: str,
    ) -> PatienceDecision | None:
        if self._is_late_entry(side, entry_price, story):
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: late entry — price already extended toward objective",
            )

        if self._vertical_momentum(side, frame, atr):
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: vertical momentum — do not chase impulse candles",
            )

        if self._extended_candle(frame, atr):
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: entry after extended candle — wait for digestion",
            )

        if self._far_from_structure(side, entry_price, structure, story, atr):
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: price too far from structure — wait for retest or value",
            )

        return None

    def _is_late_entry(self, side: Side, price: float, story: MarketStory) -> bool:
        origin = story.invalidation_level
        target = story.next_objective
        span = abs(target - origin)
        if span <= 0:
            return False
        if side == "buy":
            progress = (price - origin) / span
        else:
            progress = (origin - price) / span
        return progress >= self.config.late_entry_progress

    @staticmethod
    def _vertical_momentum(side: Side, frame: pd.DataFrame, atr: float) -> bool:
        tail = frame.tail(3)
        ranges = (tail["high"].astype(float) - tail["low"].astype(float)).values
        if len(ranges) < 3:
            return False
        if float(ranges[-1]) >= 1.55 * atr:
            opens = tail["open"].astype(float).values
            closes = tail["close"].astype(float).values
            bodies = abs(closes - opens)
            if float(bodies[-1]) >= 0.65 * float(ranges[-1]):
                bullish = closes[-1] > opens[-1]
                bearish = closes[-1] < opens[-1]
                if side == "buy" and bullish:
                    return True
                if side == "sell" and bearish:
                    return True
        directional = 0
        for i in range(-3, 0):
            o = float(tail["open"].iloc[i])
            c = float(tail["close"].iloc[i])
            r = float(tail["high"].iloc[i]) - float(tail["low"].iloc[i])
            if r < 0.9 * atr:
                continue
            if side == "buy" and c > o:
                directional += 1
            elif side == "sell" and c < o:
                directional += 1
        return directional >= 2 and float(ranges[-1]) > 1.1 * atr

    @staticmethod
    def _extended_candle(frame: pd.DataFrame, atr: float) -> bool:
        bar = frame.iloc[-1]
        high = float(bar["high"])
        low = float(bar["low"])
        open_ = float(bar["open"])
        close = float(bar["close"])
        full_range = high - low
        body = abs(close - open_)
        if full_range < 1.35 * atr:
            return False
        return body >= 0.60 * full_range

    def _far_from_structure(
        self,
        side: Side,
        price: float,
        structure: MarketContext,
        story: MarketStory,
        atr: float,
    ) -> bool:
        anchors: list[float] = []
        if side == "buy":
            anchors.extend(z.mid for z in structure.support_zones)
            anchors.extend(s.price for s in structure.swing_lows[-3:])
            anchors.append(story.invalidation_level)
        else:
            anchors.extend(z.mid for z in structure.resistance_zones)
            anchors.extend(s.price for s in structure.swing_highs[-3:])
            anchors.append(story.invalidation_level)

        if structure.last_bos is not None:
            anchors.append(structure.last_bos.price)
            anchors.append(structure.last_bos.reference_price)

        if not anchors:
            return False

        nearest = min(anchors, key=lambda level: abs(level - price))
        return abs(price - nearest) > self.config.max_structure_distance_atr * atr

    def _stop_quality(
        self,
        *,
        side: Side,
        entry_price: float,
        stop_loss: float,
        atr: float,
        symbol: str,
    ) -> PatienceDecision | None:
        pip = pip_size_for_symbol(symbol)
        distance = abs(entry_price - stop_loss)
        if distance <= 0:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: illogical stop — zero risk distance",
            )

        if side == "buy" and stop_loss >= entry_price:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: illogical stop — buy stop must sit below entry",
            )
        if side == "sell" and stop_loss <= entry_price:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: illogical stop — sell stop must sit above entry",
            )

        stop_atr = distance / atr
        if stop_atr > self.config.max_stop_atr:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason=(
                    f"Reject: stop too wide ({stop_atr:.1f} ATR > "
                    f"{self.config.max_stop_atr:.1f} ATR) — wait for tighter structure"
                ),
            )
        if stop_atr < self.config.min_stop_atr:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason="Reject: stop too tight — structure invalidation unclear",
            )

        stop_pips = distance / pip
        if stop_pips > self.config.max_stop_pips:
            return PatienceDecision(
                ready=False,
                opportunity=None,
                reason=(
                    f"Reject: stop {stop_pips:.0f} pips > "
                    f"{self.config.max_stop_pips:.0f} pip cap — wait for closer structure"
                ),
            )
        return None

    def _scan_entry_types(
        self,
        *,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        structure: MarketContext,
        entry_price: float,
        atr: float,
        symbol: str,
        timeframe: str,
    ) -> list[EntryOpportunity]:
        found: list[EntryOpportunity] = []

        sweep = self._detect_sweep_rejection(side, frame, story, atr, symbol, timeframe)
        if sweep is not None:
            found.append(sweep)

        retest = self._detect_structure_retest(side, frame, structure, atr)
        if retest is not None:
            found.append(retest)

        pullback = self._detect_pullback_into_value(side, frame, atr)
        if pullback is not None:
            found.append(pullback)

        compression = self._detect_compression_setup(side, frame, story, atr)
        if compression is not None:
            found.append(compression)

        return found

    def _entry_confirmed(
        self,
        opp: EntryOpportunity,
        *,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        structure: MarketContext,
        atr: float,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Require explicit price confirmation — not generic pullback alone."""
        et = opp.entry_type
        if et == "liquidity_sweep_rejection":
            return self._confirm_sweep_reclaim(side, frame, story, atr, symbol, timeframe)
        if et == "retest_broken_structure":
            return self._confirm_retest_reduced_momentum(side, frame, structure, atr)
        if et == "pullback_into_value":
            return self._confirm_rejection_wick_at_value(side, frame, atr) or self._confirm_failed_continuation(
                side, frame, atr
            )
        if et == "compression_before_expansion":
            return self._confirm_compression_expansion(side, frame, story, atr)
        return False

    def _confirmation_strength(
        self,
        entry_type: EntryType,
        *,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        structure: MarketContext,
        atr: float,
        symbol: str,
        timeframe: str,
    ) -> float:
        """Score how strongly price confirmed the entry pattern."""
        if entry_type == "liquidity_sweep_rejection" and self._confirm_sweep_reclaim(
            side, frame, story, atr, symbol, timeframe
        ):
            return 88.0
        if entry_type == "retest_broken_structure" and self._confirm_retest_reduced_momentum(
            side, frame, structure, atr
        ):
            return 82.0
        if entry_type == "pullback_into_value":
            if self._confirm_rejection_wick_at_value(side, frame, atr):
                return 80.0
            if self._confirm_failed_continuation(side, frame, atr):
                return 74.0
            last_range = float(frame["high"].iloc[-1]) - float(frame["low"].iloc[-1])
            if last_range <= 0.85 * atr:
                return 62.0
        if entry_type == "compression_before_expansion" and self._confirm_compression_expansion(
            side, frame, story, atr
        ):
            return 76.0
        return 55.0

    def _confirm_rejection_wick_at_value(self, side: Side, frame: pd.DataFrame, atr: float) -> bool:
        bar = frame.iloc[-1]
        open_ = float(bar["open"])
        close = float(bar["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        body = abs(close - open_) + 1e-12
        full = high - low
        if full < 0.25 * atr:
            return False

        if side == "buy":
            wick = min(close, open_) - low
            return wick >= body * 1.15 and close > open_ and close >= low + 0.45 * full
        wick = high - max(close, open_)
        return wick >= body * 1.15 and close < open_ and close <= high - 0.45 * full

    def _confirm_failed_continuation(self, side: Side, frame: pd.DataFrame, atr: float) -> bool:
        if len(frame) < 4:
            return False
        prev = frame.iloc[-2]
        last = frame.iloc[-1]
        prev_range = float(prev["high"]) - float(prev["low"])
        last_range = float(last["high"]) - float(last["low"])
        if prev_range < 0.5 * atr:
            return False

        if side == "buy":
            extended = float(prev["close"]) > float(prev["open"]) and prev_range >= 0.85 * atr
            failed = float(last["close"]) < float(last["open"]) or last_range < 0.65 * prev_range
            return extended and failed
        extended = float(prev["close"]) < float(prev["open"]) and prev_range >= 0.85 * atr
        failed = float(last["close"]) > float(last["open"]) or last_range < 0.65 * prev_range
        return extended and failed

    def _confirm_sweep_reclaim(
        self,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        atr: float,
        symbol: str,
        timeframe: str,
    ) -> bool:
        try:
            sweep = self._sweep.analyze(frame, symbol=symbol, timeframe=timeframe)
        except LiquiditySweepEngineError:
            sweep = None

        if sweep is not None and sweep.reclaimed and sweep.liquidity_sweep_probability >= 0.55:
            if side == "buy" and sweep.sell_side_swept:
                return True
            if side == "sell" and sweep.buy_side_swept:
                return True

        bar = frame.iloc[-1]
        close = float(bar["close"])
        open_ = float(bar["open"])
        low = float(bar["low"])
        high = float(bar["high"])
        body = abs(close - open_) + 1e-12

        if side == "buy":
            wick = min(close, open_) - low
            prior_low = float(frame["low"].iloc[-4:-1].min())
            swept = low < prior_low - 0.08 * atr
            reclaimed = close > prior_low and close > open_
            return swept and reclaimed and wick >= body * 1.2
        wick = high - max(close, open_)
        prior_high = float(frame["high"].iloc[-4:-1].max())
        swept = high > prior_high + 0.08 * atr
        reclaimed = close < prior_high and close < open_
        return swept and reclaimed and wick >= body * 1.2

    def _confirm_retest_reduced_momentum(
        self,
        side: Side,
        frame: pd.DataFrame,
        structure: MarketContext,
        atr: float,
    ) -> bool:
        if structure.last_bos is None or len(frame) < 5:
            return False
        retest_bars = frame.iloc[-3:]
        ranges = (retest_bars["high"].astype(float) - retest_bars["low"].astype(float)).values
        if len(ranges) < 2:
            return False
        impulse_range = float(frame.iloc[-6:-3]["high"].max() - frame.iloc[-6:-3]["low"].min())
        if impulse_range <= 0:
            return False
        reduced = float(ranges[-1]) <= 0.72 * impulse_range and float(ranges[-1]) <= 0.85 * atr
        close = float(frame["close"].iloc[-1])
        event = structure.last_bos
        level = event.reference_price or event.price
        tolerance = self.config.retest_tolerance_atr * atr
        if side == "buy":
            return reduced and close >= level - tolerance
        return reduced and close <= level + tolerance

    def _confirm_compression_expansion(
        self,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        atr: float,
    ) -> bool:
        coil_bars = 4
        if len(frame) < coil_bars + 2:
            return False
        coil = frame.tail(coil_bars + 1).iloc[:-1]
        last = frame.iloc[-1]
        coil_range = float(coil["high"].max()) - float(coil["low"].min())
        last_range = float(last["high"]) - float(last["low"])
        if coil_range > self.config.compression_range_atr * atr:
            return False
        expanding = last_range >= 0.85 * atr or last_range >= coil_range * 1.35
        close = float(last["close"])
        coil_high = float(coil["high"].max())
        coil_low = float(coil["low"].min())
        if side == "buy":
            return expanding and close > coil_high - 0.1 * atr
        return expanding and close < coil_low + 0.1 * atr

    def _detect_sweep_rejection(
        self,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        atr: float,
        symbol: str,
        timeframe: str,
    ) -> EntryOpportunity | None:
        try:
            sweep = self._sweep.analyze(frame, symbol=symbol, timeframe=timeframe)
        except LiquiditySweepEngineError:
            sweep = None

        bar = frame.iloc[-1]
        open_ = float(bar["open"])
        close = float(bar["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        body = abs(close - open_)
        wick_lower = min(close, open_) - low
        wick_upper = high - max(close, open_)

        if sweep is not None and sweep.reclaimed and sweep.liquidity_sweep_probability >= 0.55:
            if side == "buy" and sweep.sell_side_swept:
                conf = min(92.0, 68.0 + sweep.liquidity_sweep_probability * 24.0)
                return EntryOpportunity(
                    entry_price=0.0,
                    entry_type="liquidity_sweep_rejection",
                    confidence=conf,
                    stop_loss=0.0,
                    explanation=(
                        "Sell-side liquidity swept and reclaimed — rejection entry "
                        "with trapped shorts as fuel"
                    ),
                    side=side,
                )
            if side == "sell" and sweep.buy_side_swept:
                conf = min(92.0, 68.0 + sweep.liquidity_sweep_probability * 24.0)
                return EntryOpportunity(
                    entry_price=0.0,
                    entry_type="liquidity_sweep_rejection",
                    confidence=conf,
                    stop_loss=0.0,
                    explanation=(
                        "Buy-side liquidity swept and rejected — fade with trapped longs "
                        "above the highs"
                    ),
                    side=side,
                )

        if side == "buy" and wick_lower > body * 1.6 and close > open_ and close > (high + low) / 2:
            if "sweep" in story.structure_state.lower() or story.trapped_traders:
                return EntryOpportunity(
                    entry_price=0.0,
                    entry_type="liquidity_sweep_rejection",
                    confidence=74.0,
                    stop_loss=0.0,
                    explanation="Wick rejection below liquidity — buy the reclaim",
                    side=side,
                )
        if side == "sell" and wick_upper > body * 1.6 and close < open_ and close < (high + low) / 2:
            if "sweep" in story.structure_state.lower() or story.trapped_traders:
                return EntryOpportunity(
                    entry_price=0.0,
                    entry_type="liquidity_sweep_rejection",
                    confidence=74.0,
                    stop_loss=0.0,
                    explanation="Wick rejection above liquidity — sell the failure",
                    side=side,
                )
        return None

    def _detect_structure_retest(
        self,
        side: Side,
        frame: pd.DataFrame,
        structure: MarketContext,
        atr: float,
    ) -> EntryOpportunity | None:
        if structure.last_bos is None:
            return None

        event = structure.last_bos
        close = float(frame["close"].iloc[-1])
        tolerance = self.config.retest_tolerance_atr * atr

        if side == "buy" and "bullish" in event.kind:
            retest_level = event.reference_price or event.price
            touched = float(frame["low"].iloc[-3:].min()) <= retest_level + tolerance
            holding = close >= retest_level - tolerance * 0.5
            if touched and holding and self._confirm_retest_reduced_momentum(
                side, frame, structure, atr
            ):
                return EntryOpportunity(
                    entry_price=0.0,
                    entry_type="retest_broken_structure",
                    confidence=78.0,
                    stop_loss=0.0,
                    explanation="Retest of broken bullish structure — prior resistance now support",
                    side=side,
                )

        if side == "sell" and "bearish" in event.kind:
            retest_level = event.reference_price or event.price
            touched = float(frame["high"].iloc[-3:].max()) >= retest_level - tolerance
            holding = close <= retest_level + tolerance * 0.5
            if touched and holding and self._confirm_retest_reduced_momentum(
                side, frame, structure, atr
            ):
                return EntryOpportunity(
                    entry_price=0.0,
                    entry_type="retest_broken_structure",
                    confidence=78.0,
                    stop_loss=0.0,
                    explanation="Retest of broken bearish structure — prior support now resistance",
                    side=side,
                )
        return None

    def _detect_pullback_into_value(
        self,
        side: Side,
        frame: pd.DataFrame,
        atr: float,
    ) -> EntryOpportunity | None:
        impulse_bars = 6
        if len(frame) < impulse_bars + 2:
            return None

        window = frame.tail(impulse_bars + 1)
        impulse = window.iloc[:-1]
        current_close = float(window.iloc[-1]["close"])

        impulse_high = float(impulse["high"].max())
        impulse_low = float(impulse["low"].min())
        move = impulse_high - impulse_low
        if move < 0.4 * atr:
            return None

        if side == "buy":
            if float(impulse.iloc[-1]["close"]) <= float(impulse.iloc[0]["open"]):
                return None
            retrace = (impulse_high - current_close) / move
            value_level = impulse_high - move * 0.50
        else:
            if float(impulse.iloc[-1]["close"]) >= float(impulse.iloc[0]["open"]):
                return None
            retrace = (current_close - impulse_low) / move
            value_level = impulse_low + move * 0.50

        if not (self.config.pullback_retrace_min <= retrace <= self.config.pullback_retrace_max):
            return None

        if abs(current_close - value_level) > 0.65 * atr:
            return None

        last_range = float(frame["high"].iloc[-1]) - float(frame["low"].iloc[-1])
        if last_range > 1.35 * atr:
            return None

        has_wick = self._confirm_rejection_wick_at_value(side, frame, atr)
        has_failed = self._confirm_failed_continuation(side, frame, atr)
        has_slow = last_range <= 0.85 * atr and (
            (side == "buy" and float(frame["close"].iloc[-1]) >= float(frame["open"].iloc[-1]))
            or (side == "sell" and float(frame["close"].iloc[-1]) <= float(frame["open"].iloc[-1]))
        )
        if not (has_wick or has_failed or has_slow):
            return None

        conf = 70.0 + min(12.0, (self.config.pullback_retrace_max - abs(retrace - 0.45)) * 40.0)
        if has_wick:
            conf += 6.0
        return EntryOpportunity(
            entry_price=0.0,
            entry_type="pullback_into_value",
            confidence=conf,
            stop_loss=0.0,
            explanation=(
                f"Pullback into value ({retrace:.0%} of impulse) — "
                "enter on discount, not extension"
            ),
            side=side,
        )

    def _detect_compression_setup(
        self,
        side: Side,
        frame: pd.DataFrame,
        story: MarketStory,
        atr: float,
    ) -> EntryOpportunity | None:
        coil_bars = 4
        if len(frame) < coil_bars + 8:
            return None

        coil = frame.tail(coil_bars)
        coil_range = float(coil["high"].max()) - float(coil["low"].min())
        prior = frame.iloc[-(coil_bars + 8) : -coil_bars]
        prior_range = float(prior["high"].max()) - float(prior["low"].min())
        if prior_range <= 0:
            return None

        if coil_range > self.config.compression_range_atr * atr:
            return None
        if coil_range / prior_range > 0.72:
            return None

        last = frame.iloc[-1]
        last_range = float(last["high"]) - float(last["low"])
        if last_range > 1.15 * atr:
            return None

        close = float(last["close"])
        coil_mid = (float(coil["high"].max()) + float(coil["low"].min())) / 2
        if side == "buy" and close < coil_mid - 0.15 * atr:
            return None
        if side == "sell" and close > coil_mid + 0.15 * atr:
            return None

        if "compression" not in story.structure_state.lower() and story.trend_strength < 40:
            return None

        if not self._confirm_compression_expansion(side, frame, story, atr):
            return None

        return EntryOpportunity(
            entry_price=0.0,
            entry_type="compression_before_expansion",
            confidence=66.0,
            stop_loss=0.0,
            explanation=(
                "Compression coil aligned with story — enter before expansion, "
                "stop beyond coil extreme"
            ),
            side=side,
        )


__all__ = [
    "EntryOpportunity",
    "EntryType",
    "PatienceDecision",
    "PatienceEngine",
    "PatienceEngineConfig",
]
