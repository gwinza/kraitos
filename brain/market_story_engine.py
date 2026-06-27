"""Market Story Engine — read price as narrative, not indicators.

Structure, liquidity, price behaviour, and risk/reward lead every decision.
Indicators may support the story but never veto it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from core.helpers import pip_size_for_symbol
from strategies.false_breakout_engine import FalseBreakoutEngine, FalseBreakoutEngineError
from strategies.liquidity_sweep_engine import LiquiditySweepEngine, LiquiditySweepEngineError
from strategies.market_reading_utils import atr_series, swing_points, trend_direction_from_swings
from strategies.market_structure import MarketStructureAnalyzer, MarketStructureConfig, MarketStructureError
from strategies.models import MarketContext, PriceZone

STORY_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")

Direction = Literal["bullish", "bearish", "neutral"]
ControllingSide = Literal["buyers", "sellers", "neutral"]


@dataclass(frozen=True)
class LiquidityTarget:
    """Mapped pool of resting orders or equal highs/lows."""

    label: str
    price: float
    side: Literal["buy_side", "sell_side", "equal_highs", "equal_lows", "swing"]

    def to_dict(self) -> dict:
        return {"label": self.label, "price": round(self.price, 5), "side": self.side}


@dataclass(frozen=True)
class TrappedTraderZone:
    """Area where late or wrong-sided participants are likely stuck."""

    description: str
    lower: float
    upper: float
    trapped_side: Literal["longs", "shorts", "breakout_traders", "none"]

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "lower": round(self.lower, 5),
            "upper": round(self.upper, 5),
            "trapped_side": self.trapped_side,
        }


@dataclass(frozen=True)
class MarketStory:
    """Professional trade narrative for one symbol and timeframe."""

    direction: Direction
    confidence: float
    controlling_side: ControllingSide
    structure_state: str
    liquidity_targets: tuple[LiquidityTarget, ...]
    trapped_traders: tuple[TrappedTraderZone, ...]
    next_objective: float
    invalidation_level: float
    narrative: str
    symbol: str = ""
    timeframe: str = ""
    trend_strength: float = 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "controlling_side": self.controlling_side,
            "structure_state": self.structure_state,
            "trend_strength": round(self.trend_strength, 2),
            "liquidity_targets": [t.to_dict() for t in self.liquidity_targets],
            "trapped_traders": [t.to_dict() for t in self.trapped_traders],
            "next_objective": round(self.next_objective, 5),
            "invalidation_level": round(self.invalidation_level, 5),
            "narrative": self.narrative,
        }


@dataclass(frozen=True)
class _PriceRead:
    direction: Direction
    controlling_side: ControllingSide
    trend_strength: float
    structure_state: str
    momentum_atr: float
    range_position: float
    rejection_up: bool
    rejection_down: bool
    participation: float


class MarketStoryEngine:
    """Build market stories from structure, liquidity, and price behaviour."""

    def __init__(self) -> None:
        self._structure = MarketStructureAnalyzer(
            MarketStructureConfig(min_candles=30, swing_left=2, swing_right=2)
        )
        self._sweep = LiquiditySweepEngine()
        self._false_break = FalseBreakoutEngine()
        self._latest: dict[tuple[str, str], MarketStory] = {}

    def read(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: pd.DataFrame,
        indicator_interpretation: object | None = None,
    ) -> MarketStory:
        """Read the market story for one symbol on one timeframe."""
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().upper()
        frame = self._prepare_frame(candles)
        if frame is None or len(frame) < 10:
            return self._empty_story(symbol, timeframe, "Insufficient candle data")

        structure = self._safe_structure(frame, symbol=symbol, timeframe=timeframe)
        price_read = self._read_price(frame, symbol, structure)
        sweep = self._safe_sweep(frame, symbol=symbol, timeframe=timeframe)
        breakout = self._safe_breakout(frame, symbol=symbol, timeframe=timeframe)

        direction, controlling_side = self._resolve_control(
            price_read, structure, sweep, breakout
        )
        trend_strength = self._trend_strength(price_read, structure, sweep)
        structure_state = self._structure_label(price_read, structure, sweep, breakout)

        liquidity_targets = self._liquidity_targets(frame, structure, sweep)
        trapped_traders = self._trapped_zones(frame, sweep, breakout, structure)
        next_objective = self._next_objective(
            frame, direction, structure, liquidity_targets, sweep
        )
        invalidation_level = self._invalidation_level(
            frame, direction, structure, sweep
        )
        confidence = self._confidence(
            price_read, structure, sweep, breakout, liquidity_targets, trapped_traders
        )
        confidence = self._indicator_support_only(
            confidence, direction, indicator_interpretation
        )

        narrative = self._compose_narrative(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            controlling_side=controlling_side,
            structure_state=structure_state,
            trend_strength=trend_strength,
            liquidity_targets=liquidity_targets,
            trapped_traders=trapped_traders,
            sweep=sweep,
            breakout=breakout,
            next_objective=next_objective,
            invalidation_level=invalidation_level,
            indicator_interpretation=indicator_interpretation,
        )

        story = MarketStory(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            controlling_side=controlling_side,
            structure_state=structure_state,
            liquidity_targets=tuple(liquidity_targets),
            trapped_traders=tuple(trapped_traders),
            next_objective=next_objective,
            invalidation_level=invalidation_level,
            narrative=narrative,
            trend_strength=trend_strength,
        )
        self._latest[(symbol, timeframe)] = story
        return story

    def read_all(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        indicator_interpretation: object | None = None,
    ) -> dict[str, MarketStory]:
        """Read stories for every available story timeframe."""
        stories: dict[str, MarketStory] = {}
        for tf in STORY_TIMEFRAMES:
            frame = candles.get(tf)
            if frame is None or len(frame) < 10:
                continue
            stories[tf] = self.read(
                symbol=symbol,
                timeframe=tf,
                candles=frame,
                indicator_interpretation=indicator_interpretation,
            )
        return stories

    def latest(self, symbol: str, timeframe: str) -> MarketStory | None:
        return self._latest.get((symbol.strip().upper(), timeframe.strip().upper()))

    @staticmethod
    def _prepare_frame(candles: pd.DataFrame) -> pd.DataFrame | None:
        if candles is None or candles.empty:
            return None
        frame = candles.copy()
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            frame = frame.sort_values("time")
        return frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    def _safe_structure(
        self, frame: pd.DataFrame, *, symbol: str, timeframe: str
    ) -> MarketContext | None:
        try:
            return self._structure.analyze(frame, symbol=symbol, timeframe=timeframe)
        except MarketStructureError:
            return None

    def _safe_sweep(self, frame: pd.DataFrame, *, symbol: str, timeframe: str):
        try:
            return self._sweep.analyze(frame, symbol=symbol, timeframe=timeframe)
        except LiquiditySweepEngineError:
            return None

    def _safe_breakout(self, frame: pd.DataFrame, *, symbol: str, timeframe: str):
        try:
            return self._false_break.analyze(frame, symbol=symbol, timeframe=timeframe)
        except FalseBreakoutEngineError:
            return None

    def _read_price(
        self,
        frame: pd.DataFrame,
        symbol: str,
        structure: MarketContext | None,
    ) -> _PriceRead:
        pip = pip_size_for_symbol(symbol)
        atr = atr_series(frame)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or pip

        highs, lows = swing_points(frame, window=2)
        direction = trend_direction_from_swings(highs, lows, frame, atr_value)  # type: ignore[assignment]

        lookback = min(24, len(frame) - 1)
        window_high = float(frame["high"].iloc[-lookback:].max())
        window_low = float(frame["low"].iloc[-lookback:].min())
        close = float(frame["close"].iloc[-1])
        span = max(window_high - window_low, pip)
        range_position = (close - window_low) / span

        open_ = float(frame["open"].iloc[-1])
        body = abs(close - open_)
        full_range = max(float(frame["high"].iloc[-1]) - float(frame["low"].iloc[-1]), pip)
        wick_upper = float(frame["high"].iloc[-1]) - max(close, open_)
        wick_lower = min(close, open_) - float(frame["low"].iloc[-1])
        rejection_up = wick_upper > body * 1.5 and body < full_range * 0.45
        rejection_down = wick_lower > body * 1.5 and body < full_range * 0.45

        momentum_atr = (close - float(frame["close"].iloc[-min(8, len(frame) - 1)])) / max(
            atr_value, pip
        )

        if "tick_volume" in frame.columns and len(frame) >= 20:
            vol = frame["tick_volume"].astype(float)
            participation = float(vol.iloc[-5:].mean() / max(vol.iloc[-20:-5].mean(), 1.0))
            participation = max(0.0, min(1.5, participation))
        else:
            participation = 0.8

        controlling_side: ControllingSide = "neutral"
        if range_position >= 0.62 and momentum_atr > 0.15:
            controlling_side = "buyers"
        elif range_position <= 0.38 and momentum_atr < -0.15:
            controlling_side = "sellers"
        elif direction == "bullish" and range_position >= 0.55:
            controlling_side = "buyers"
        elif direction == "bearish" and range_position <= 0.45:
            controlling_side = "sellers"

        if structure is not None:
            if structure.trend == "bullish" and structure.higher_lows:
                controlling_side = "buyers" if controlling_side != "sellers" else controlling_side
            elif structure.trend == "bearish" and structure.lower_highs:
                controlling_side = "sellers" if controlling_side != "buyers" else controlling_side

        trend_strength = self._raw_trend_strength(
            direction=direction,
            structure=structure,
            momentum_atr=momentum_atr,
            participation=participation,
        )
        structure_state = self._structure_label_from_parts(structure, direction, trend_strength)

        return _PriceRead(
            direction=direction,
            controlling_side=controlling_side,
            trend_strength=trend_strength,
            structure_state=structure_state,
            momentum_atr=momentum_atr,
            range_position=range_position,
            rejection_up=rejection_up,
            rejection_down=rejection_down,
            participation=participation,
        )

    @staticmethod
    def _raw_trend_strength(
        *,
        direction: str,
        structure: MarketContext | None,
        momentum_atr: float,
        participation: float,
    ) -> float:
        score = 35.0
        if direction in {"bullish", "bearish"}:
            score += 15.0
        if structure is not None:
            if structure.trend == direction:
                score += 18.0
            if (structure.higher_highs and structure.higher_lows) or (
                structure.lower_highs and structure.lower_lows
            ):
                score += 12.0
            if structure.last_bos is not None:
                score += 8.0
        score += min(15.0, abs(momentum_atr) * 6.0)
        score += min(10.0, max(0.0, (participation - 0.8) * 20.0))
        return max(0.0, min(100.0, score))

    def _resolve_control(
        self,
        price_read: _PriceRead,
        structure: MarketContext | None,
        sweep,
        breakout,
    ) -> tuple[Direction, ControllingSide]:
        direction: Direction = price_read.direction  # type: ignore[assignment]
        controlling: ControllingSide = price_read.controlling_side

        if sweep is not None and sweep.reclaimed:
            if sweep.sell_side_swept and sweep.reclaimed:
                direction = "bullish"
                controlling = "buyers"
            elif sweep.buy_side_swept and sweep.reclaimed:
                direction = "bearish"
                controlling = "sellers"

        if breakout is not None and breakout.breakout_class == "failed":
            if breakout.trapped_traders == "longs":
                direction = "bearish"
                controlling = "sellers"
            elif breakout.trapped_traders == "shorts":
                direction = "bullish"
                controlling = "buyers"

        if structure is not None and structure.last_choch is not None:
            kind = structure.last_choch.kind
            if kind == "choch_bullish":
                direction = "bullish"
                controlling = "buyers"
            elif kind == "choch_bearish":
                direction = "bearish"
                controlling = "sellers"

        if direction == "neutral" and controlling != "neutral":
            direction = "bullish" if controlling == "buyers" else "bearish"
        if controlling == "neutral" and direction != "neutral":
            controlling = "buyers" if direction == "bullish" else "sellers"

        return direction, controlling

    def _trend_strength(
        self,
        price_read: _PriceRead,
        structure: MarketContext | None,
        sweep,
    ) -> float:
        strength = price_read.trend_strength
        if sweep is not None and sweep.reclaimed and sweep.liquidity_sweep_probability >= 0.7:
            strength = min(100.0, strength + 12.0)
        if structure is not None and structure.last_bos is not None:
            bos_dir = "bullish" if "bullish" in structure.last_bos.kind else "bearish"
            if bos_dir == price_read.direction:
                strength = min(100.0, strength + 8.0)
        return round(strength, 2)

    @staticmethod
    def _structure_label_from_parts(
        structure: MarketContext | None,
        direction: str,
        trend_strength: float,
    ) -> str:
        strength_word = (
            "strong" if trend_strength >= 70 else "moderate" if trend_strength >= 45 else "weak"
        )
        if structure is None:
            return f"{direction} {strength_word} — structure forming"
        if structure.last_choch is not None:
            return f"character change ({structure.last_choch.kind.replace('_', ' ')})"
        if structure.last_bos is not None:
            return f"{structure.last_bos.kind.replace('_', ' ')} — {strength_word} {structure.trend}"
        if structure.trend == "ranging":
            return "balanced range — auction between defined extremes"
        return f"{structure.trend} {strength_word} ({'HH/HL' if structure.higher_highs else 'LH/LL' if structure.lower_lows else 'mixed swings'})"

    def _structure_label(self, price_read, structure, sweep, breakout) -> str:
        label = price_read.structure_state
        if sweep is not None and sweep.reclaimed:
            label = f"{label}; sell-side sweep reclaimed" if sweep.sell_side_swept else (
                f"{label}; buy-side sweep reclaimed" if sweep.buy_side_swept else label
            )
        if breakout is not None and breakout.breakout_class == "failed":
            label = f"{label}; failed breakout — {breakout.trapped_traders} trapped"
        return label

    def _liquidity_targets(
        self,
        frame: pd.DataFrame,
        structure: MarketContext | None,
        sweep,
    ) -> list[LiquidityTarget]:
        targets: list[LiquidityTarget] = []
        pip = pip_size_for_symbol(structure.symbol if structure else "EURUSD")
        highs, lows = swing_points(frame, window=2)

        if highs:
            buy_level = max(price for _, price in highs[-3:])
            targets.append(LiquidityTarget("buy-side liquidity above swing highs", buy_level, "buy_side"))
        if lows:
            sell_level = min(price for _, price in lows[-3:])
            targets.append(LiquidityTarget("sell-side liquidity below swing lows", sell_level, "sell_side"))

        if structure is not None:
            for zone in structure.liquidity_zones[:3]:
                side: Literal["buy_side", "sell_side", "equal_highs", "equal_lows", "swing"] = (
                    "equal_highs" if zone.mid >= float(frame["close"].iloc[-1]) else "equal_lows"
                )
                targets.append(
                    LiquidityTarget(
                        f"equal {'highs' if side == 'equal_highs' else 'lows'} pool",
                        zone.mid,
                        side,
                    )
                )
            for zone in structure.resistance_zones[:2]:
                targets.append(
                    LiquidityTarget("overhead resistance liquidity", zone.mid, "buy_side")
                )
            for zone in structure.support_zones[:2]:
                targets.append(
                    LiquidityTarget("underlying support liquidity", zone.mid, "sell_side")
                )

        if sweep is not None and sweep.sweep_level > 0:
            side = "sell_side" if sweep.sell_side_swept else "buy_side"
            targets.append(
                LiquidityTarget(
                    f"recent {sweep.sweep_type.replace('_', ' ')} level",
                    sweep.sweep_level,
                    side,
                )
            )

        # Session / rolling extremes
        lookback = min(len(frame), 48)
        session_high = float(frame["high"].iloc[-lookback:].max())
        session_low = float(frame["low"].iloc[-lookback:].min())
        targets.append(LiquidityTarget("session high liquidity", session_high, "buy_side"))
        targets.append(LiquidityTarget("session low liquidity", session_low, "sell_side"))

        # Deduplicate near-identical levels
        deduped: list[LiquidityTarget] = []
        for target in targets:
            if any(abs(target.price - existing.price) <= pip for existing in deduped):
                continue
            deduped.append(target)
        return deduped[:8]

    def _trapped_zones(self, frame, sweep, breakout, structure) -> list[TrappedTraderZone]:
        zones: list[TrappedTraderZone] = []
        pip = pip_size_for_symbol(structure.symbol if structure else "EURUSD")
        close = float(frame["close"].iloc[-1])

        if breakout is not None and breakout.trapped_traders != "none":
            pad = pip * 8
            if breakout.trapped_traders == "longs":
                zones.append(
                    TrappedTraderZone(
                        "longs caught on failed upside breakout",
                        close - pad * 2,
                        close + pad,
                        "longs",
                    )
                )
            elif breakout.trapped_traders == "shorts":
                zones.append(
                    TrappedTraderZone(
                        "shorts caught on failed downside breakdown",
                        close - pad,
                        close + pad * 2,
                        "shorts",
                    )
                )

        if sweep is not None and sweep.reclaimed:
            pad = pip * 6
            if sweep.sell_side_swept:
                zones.append(
                    TrappedTraderZone(
                        "shorts trapped below sell-side liquidity sweep",
                        sweep.sweep_level - pad,
                        sweep.sweep_level + pad,
                        "shorts",
                    )
                )
            elif sweep.buy_side_swept:
                zones.append(
                    TrappedTraderZone(
                        "longs trapped above buy-side liquidity sweep",
                        sweep.sweep_level - pad,
                        sweep.sweep_level + pad,
                        "longs",
                    )
                )
        elif sweep is not None and sweep.sweep_type == "stop_hunt" and not sweep.reclaimed:
            pad = pip * 5
            side = "shorts" if sweep.sell_side_swept else "longs"
            zones.append(
                TrappedTraderZone(
                    "breakout traders leaning into unconfirmed stop hunt",
                    sweep.sweep_level - pad,
                    sweep.sweep_level + pad,
                    "breakout_traders",
                )
            )

        if structure is not None and structure.last_bos is not None:
            event = structure.last_bos
            pad = pip * 5
            if "bullish" in event.kind:
                zones.append(
                    TrappedTraderZone(
                        "late shorts leaning against fresh bullish structure",
                        event.price - pad * 2,
                        event.price,
                        "shorts",
                    )
                )
            elif "bearish" in event.kind:
                zones.append(
                    TrappedTraderZone(
                        "late longs leaning against fresh bearish structure",
                        event.price,
                        event.price + pad * 2,
                        "longs",
                    )
                )

        return zones[:5]

    def _next_objective(
        self,
        frame: pd.DataFrame,
        direction: Direction,
        structure: MarketContext | None,
        liquidity_targets: list[LiquidityTarget],
        sweep,
    ) -> float:
        close = float(frame["close"].iloc[-1])
        if direction == "bullish":
            above = [t.price for t in liquidity_targets if t.price > close]
            if sweep is not None and sweep.sell_side_swept and sweep.reclaimed and above:
                return min(above)
            if structure is not None and structure.swing_highs:
                swing_target = max(s.price for s in structure.swing_highs[-2:])
                if swing_target > close:
                    return swing_target
            return max(above) if above else close + (close - float(frame["low"].iloc[-20:].min())) * 0.5

        if direction == "bearish":
            below = [t.price for t in liquidity_targets if t.price < close]
            if sweep is not None and sweep.buy_side_swept and sweep.reclaimed and below:
                return max(below)
            if structure is not None and structure.swing_lows:
                swing_target = min(s.price for s in structure.swing_lows[-2:])
                if swing_target < close:
                    return swing_target
            return min(below) if below else close - (float(frame["high"].iloc[-20:].max()) - close) * 0.5

        mid = (float(frame["high"].iloc[-20:].max()) + float(frame["low"].iloc[-20:].min())) / 2
        return mid

    def _invalidation_level(
        self,
        frame: pd.DataFrame,
        direction: Direction,
        structure: MarketContext | None,
        sweep,
    ) -> float:
        pip = pip_size_for_symbol(structure.symbol if structure else "EURUSD")
        if direction == "bullish":
            if sweep is not None and sweep.sell_side_swept and sweep.sweep_level > 0:
                return sweep.sweep_level - pip * 3
            if structure is not None and structure.swing_lows:
                return min(s.price for s in structure.swing_lows[-2:]) - pip * 2
            return float(frame["low"].iloc[-12:].min()) - pip * 2

        if direction == "bearish":
            if sweep is not None and sweep.buy_side_swept and sweep.sweep_level > 0:
                return sweep.sweep_level + pip * 3
            if structure is not None and structure.swing_highs:
                return max(s.price for s in structure.swing_highs[-2:]) + pip * 2
            return float(frame["high"].iloc[-12:].max()) + pip * 2

        return float(frame["close"].iloc[-1])

    @staticmethod
    def _confidence(
        price_read: _PriceRead,
        structure: MarketContext | None,
        sweep,
        breakout,
        liquidity_targets: list[LiquidityTarget],
        trapped_traders: list[TrappedTraderZone],
    ) -> float:
        score = 38.0 + price_read.trend_strength * 0.35
        if structure is not None and structure.trend == price_read.direction:
            score += 10.0
        if sweep is not None and sweep.reclaimed:
            score += 14.0
        if breakout is not None and breakout.breakout_class == "failed":
            score += 8.0
        if liquidity_targets:
            score += 6.0
        if trapped_traders:
            score += 5.0
        if price_read.rejection_up or price_read.rejection_down:
            score += 4.0
        return max(20.0, min(95.0, score))

    @staticmethod
    def _indicator_support_only(
        confidence: float,
        direction: Direction,
        indicator_interpretation: object | None,
    ) -> float:
        """Indicators may nudge confidence but never flip or veto the story."""
        if indicator_interpretation is None:
            return round(confidence, 2)
        contribution = str(
            getattr(indicator_interpretation, "market_explanation_contribution", "") or ""
        ).lower()
        insight = float(getattr(indicator_interpretation, "insight_score", 50.0) or 50.0)
        if not contribution:
            return round(confidence, 2)

        aligned = (
            (direction == "bullish" and any(w in contribution for w in ("bull", "bid", "accumulation")))
            or (direction == "bearish" and any(w in contribution for w in ("bear", "offer", "distribution")))
        )
        if aligned:
            confidence = min(95.0, confidence + min(6.0, insight / 20.0))
        elif direction != "neutral":
            confidence = max(20.0, confidence - 2.0)
        return round(confidence, 2)

    def _compose_narrative(
        self,
        *,
        symbol: str,
        timeframe: str,
        direction: Direction,
        controlling_side: ControllingSide,
        structure_state: str,
        trend_strength: float,
        liquidity_targets: list[LiquidityTarget],
        trapped_traders: list[TrappedTraderZone],
        sweep,
        breakout,
        next_objective: float,
        invalidation_level: float,
        indicator_interpretation: object | None,
    ) -> str:
        control_phrase = {
            "buyers": f"{timeframe} buyers remain in control",
            "sellers": f"{timeframe} sellers remain in control",
            "neutral": f"{timeframe} is balanced — neither side owns the auction",
        }[controlling_side]

        strength_phrase = (
            "with strong trend sponsorship"
            if trend_strength >= 70
            else "with developing trend sponsorship"
            if trend_strength >= 45
            else "but trend sponsorship is still weak"
        )

        parts: list[str] = [f"{control_phrase} {strength_phrase}."]

        if sweep is not None and sweep.reclaimed and sweep.sell_side_swept:
            parts.append(
                "Price swept sell-side liquidity below recent lows and immediately reclaimed structure."
            )
            parts.append("This suggests accumulation rather than genuine distribution.")
        elif sweep is not None and sweep.reclaimed and sweep.buy_side_swept:
            parts.append(
                "Price swept buy-side liquidity above recent highs and rejected back inside range."
            )
            parts.append("This suggests distribution and trapped longs above the highs.")
        elif breakout is not None and breakout.breakout_class == "failed":
            parts.append(
                f"A failed {breakout.direction} breakout left {breakout.trapped_traders} exposed."
            )
        else:
            parts.append(f"Structure reads as {structure_state}.")

        if trapped_traders:
            parts.append(trapped_traders[0].description.capitalize() + ".")

        if direction == "bullish":
            objective_label = self._objective_label(liquidity_targets, next_objective, above=True)
            parts.append(f"The next likely target is {objective_label} at {next_objective:.5f}.")
            parts.append(f"Bullish thesis invalidates below {invalidation_level:.5f}.")
        elif direction == "bearish":
            objective_label = self._objective_label(liquidity_targets, next_objective, above=False)
            parts.append(f"The next likely target is {objective_label} at {next_objective:.5f}.")
            parts.append(f"Bearish thesis invalidates above {invalidation_level:.5f}.")
        else:
            parts.append(
                f"Trade only on confirmation toward {next_objective:.5f} "
                f"or fade back toward range centre; no thesis until control resolves."
            )

        if indicator_interpretation is not None:
            note = str(
                getattr(indicator_interpretation, "market_explanation_contribution", "") or ""
            ).strip()
            if note:
                parts.append(f"Indicator context (supporting only): {note}")

        return " ".join(parts)

    @staticmethod
    def _objective_label(
        targets: list[LiquidityTarget],
        price: float,
        *,
        above: bool,
    ) -> str:
        for target in targets:
            if abs(target.price - price) <= 0.00015:
                return target.label.replace(" liquidity", "")
        if above:
            return "overhead liquidity"
        return "underlying liquidity"

    @staticmethod
    def _empty_story(symbol: str, timeframe: str, reason: str) -> MarketStory:
        return MarketStory(
            symbol=symbol,
            timeframe=timeframe,
            direction="neutral",
            confidence=20.0,
            controlling_side="neutral",
            structure_state="insufficient data",
            liquidity_targets=(),
            trapped_traders=(),
            next_objective=0.0,
            invalidation_level=0.0,
            narrative=f"{timeframe} {symbol}: {reason}. Wait for structure.",
            trend_strength=0.0,
        )


__all__ = [
    "LiquidityTarget",
    "MarketStory",
    "MarketStoryEngine",
    "STORY_TIMEFRAMES",
    "TrappedTraderZone",
]
