"""
Market structure analysis for Kraitos.

Detects swing points, trend structure (HH/HL/LH/LL), breaks of structure,
changes of character, and support/resistance/liquidity zones.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from loguru import logger

from strategies.models import (
    MarketContext,
    PriceZone,
    StructureEvent,
    StructureEventKind,
    StructureTrend,
    SwingPoint,
)

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class MarketStructureConfig:
    """Configuration for swing and zone detection."""

    swing_left: int = 2
    swing_right: int = 2
    min_candles: int = 40
    zone_tolerance_pct: float = 0.0006
    liquidity_tolerance_pct: float = 0.0003
    min_zone_touches: int = 2
    max_zones: int = 5


class MarketStructureError(Exception):
    """Raised when candle input is invalid for structure analysis."""


class MarketStructureAnalyzer:
    """Analyze price action and return a structured market context."""

    def __init__(self, config: MarketStructureConfig | None = None) -> None:
        self.config = config or MarketStructureConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "EURUSD",
        timeframe: str = "H1",
    ) -> MarketContext:
        """
        Build a market context object from OHLCV candles.

        Args:
            candles: Historical candle DataFrame.
            symbol: Instrument label.
            timeframe: Timeframe label.

        Returns:
            MarketContext with swings, events, zones, and trend state.
        """
        frame = self._prepare_candles(candles)
        swing_highs, swing_lows = self._find_swings(frame)

        hh, hl, lh, ll = self._classify_structure(swing_highs, swing_lows)
        trend = self._determine_trend(hh, hl, lh, ll)
        if trend == "ranging":
            inferred = self._infer_trend_from_price(frame)
            if inferred != "ranging":
                trend = inferred
                if inferred == "bullish":
                    hh = hh or True
                    hl = hl or True
                elif inferred == "bearish":
                    lh = lh or True
                    ll = ll or True
        events = self._detect_structure_events(frame, swing_highs, swing_lows, hh, hl, lh, ll)

        support_zones = self._build_zones(
            [(swing.time, swing.price) for swing in swing_lows],
            kind="support",
        )
        resistance_zones = self._build_zones(
            [(swing.time, swing.price) for swing in swing_highs],
            kind="resistance",
        )
        liquidity_zones = self._detect_liquidity_zones(swing_highs, swing_lows)

        last_bos = self._last_event(events, ("bos_bullish", "bos_bearish"))
        last_choch = self._last_event(events, ("choch_bullish", "choch_bearish"))

        context = MarketContext(
            symbol=symbol.strip().upper(),
            timeframe=timeframe.strip().upper(),
            trend=trend,
            higher_highs=hh,
            higher_lows=hl,
            lower_highs=lh,
            lower_lows=ll,
            swing_highs=tuple(swing_highs),
            swing_lows=tuple(swing_lows),
            structure_events=tuple(events),
            support_zones=tuple(support_zones),
            resistance_zones=tuple(resistance_zones),
            liquidity_zones=tuple(liquidity_zones),
            last_bos=last_bos,
            last_choch=last_choch,
        )

        logger.debug(
            f"Market structure {context.symbol} {context.timeframe}: "
            f"trend={context.trend}, events={len(context.structure_events)}, "
            f"zones={len(context.support_zones) + len(context.resistance_zones) + len(context.liquidity_zones)}"
        )
        return context

    def _prepare_candles(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise MarketStructureError("Candle data is empty")

        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise MarketStructureError(f"Missing columns: {', '.join(missing)}")

        frame = candles.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame.sort_values("time").reset_index(drop=True)

        if len(frame) < self.config.min_candles:
            raise MarketStructureError(
                f"At least {self.config.min_candles} candles required, got {len(frame)}"
            )
        return frame

    def _find_swings(self, frame: pd.DataFrame) -> tuple[list[SwingPoint], list[SwingPoint]]:
        left = self.config.swing_left
        right = self.config.swing_right
        highs: list[SwingPoint] = []
        lows: list[SwingPoint] = []

        for index in range(left, len(frame) - right):
            window = frame.iloc[index - left : index + right + 1]
            bar = frame.iloc[index]
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])

            if bar_high == float(window["high"].max()) and bar_high > float(
                frame.iloc[index - 1]["high"]
            ):
                highs.append(
                    SwingPoint(
                        bar_index=index,
                        time=bar["time"],
                        price=bar_high,
                        kind="high",
                    )
                )

            if bar_low == float(window["low"].min()) and bar_low < float(
                frame.iloc[index - 1]["low"]
            ):
                lows.append(
                    SwingPoint(
                        bar_index=index,
                        time=bar["time"],
                        price=bar_low,
                        kind="low",
                    )
                )

        return highs, lows

    def _classify_structure(
        self,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
    ) -> tuple[bool, bool, bool, bool]:
        hh = self._compare_swings(swing_highs, direction="higher")
        lh = self._compare_swings(swing_highs, direction="lower")
        hl = self._compare_swings(swing_lows, direction="higher")
        ll = self._compare_swings(swing_lows, direction="lower")
        return hh, hl, lh, ll

    def _compare_swings(self, swings: list[SwingPoint], *, direction: str) -> bool:
        if len(swings) < 2:
            return False
        latest = swings[-1].price
        previous = swings[-2].price
        if direction == "higher":
            return latest > previous
        return latest < previous

    def _detect_structure_events(
        self,
        frame: pd.DataFrame,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        hh: bool,
        hl: bool,
        lh: bool,
        ll: bool,
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []

        if hh and swing_highs:
            events.append(
                self._make_pattern_event(
                    "higher_high",
                    swing_highs[-1],
                    swing_highs[-2].price,
                    "Higher high formed above prior swing high",
                )
            )
        if lh and swing_highs:
            events.append(
                self._make_pattern_event(
                    "lower_high",
                    swing_highs[-1],
                    swing_highs[-2].price,
                    "Lower high formed below prior swing high",
                )
            )
        if hl and swing_lows:
            events.append(
                self._make_pattern_event(
                    "higher_low",
                    swing_lows[-1],
                    swing_lows[-2].price,
                    "Higher low formed above prior swing low",
                )
            )
        if ll and swing_lows:
            events.append(
                self._make_pattern_event(
                    "lower_low",
                    swing_lows[-1],
                    swing_lows[-2].price,
                    "Lower low formed below prior swing low",
                )
            )

        events.extend(self._detect_bos_and_choch(frame, swing_highs, swing_lows, hh, hl, lh, ll))
        return events

    def _detect_bos_and_choch(
        self,
        frame: pd.DataFrame,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        hh: bool,
        hl: bool,
        lh: bool,
        ll: bool,
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if not swing_highs or not swing_lows:
            return events

        last_close = float(frame.iloc[-1]["close"])
        last_time = frame.iloc[-1]["time"]
        last_index = len(frame) - 1
        recent_high = swing_highs[-1]
        recent_low = swing_lows[-1]

        bullish_trend = hh and hl
        bearish_trend = lh and ll

        if last_close > recent_high.price:
            if bullish_trend:
                events.append(
                    StructureEvent(
                        kind="bos_bullish",
                        bar_index=last_index,
                        time=last_time,
                        price=last_close,
                        reference_price=recent_high.price,
                        description="Bullish break of structure above recent swing high",
                    )
                )
            elif bearish_trend or lh or ll:
                events.append(
                    StructureEvent(
                        kind="choch_bullish",
                        bar_index=last_index,
                        time=last_time,
                        price=last_close,
                        reference_price=recent_high.price,
                        description="Bullish change of character above recent swing high",
                    )
                )

        if last_close < recent_low.price:
            if bearish_trend:
                events.append(
                    StructureEvent(
                        kind="bos_bearish",
                        bar_index=last_index,
                        time=last_time,
                        price=last_close,
                        reference_price=recent_low.price,
                        description="Bearish break of structure below recent swing low",
                    )
                )
            elif bullish_trend or hh or hl:
                events.append(
                    StructureEvent(
                        kind="choch_bearish",
                        bar_index=last_index,
                        time=last_time,
                        price=last_close,
                        reference_price=recent_low.price,
                        description="Bearish change of character below recent swing low",
                    )
                )

        return events

    def _build_zones(
        self,
        points: list[tuple[object, float]],
        *,
        kind: str,
    ) -> list[PriceZone]:
        if not points:
            return []

        tolerance = self.config.zone_tolerance_pct
        clusters: list[list[tuple[object, float]]] = []

        for time_, price in sorted(points, key=lambda item: item[1]):
            placed = False
            for cluster in clusters:
                mid = sum(item[1] for item in cluster) / len(cluster)
                if abs(price - mid) / mid <= tolerance:
                    cluster.append((time_, price))
                    placed = True
                    break
            if not placed:
                clusters.append([(time_, price)])

        zones: list[PriceZone] = []
        for cluster in clusters:
            if len(cluster) < self.config.min_zone_touches:
                continue
            prices = [price for _, price in cluster]
            lower = min(prices)
            upper = max(prices)
            mid = sum(prices) / len(prices)
            zones.append(
                PriceZone(
                    kind=kind,  # type: ignore[arg-type]
                    lower=lower,
                    upper=upper,
                    mid=mid,
                    touches=len(cluster),
                    times=tuple(time_ for time_, _ in cluster),
                )
            )

        zones.sort(key=lambda zone: zone.touches, reverse=True)
        return zones[: self.config.max_zones]

    def _detect_liquidity_zones(
        self,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
    ) -> list[PriceZone]:
        equal_highs = self._equal_level_clusters(
            [(swing.time, swing.price) for swing in swing_highs]
        )
        equal_lows = self._equal_level_clusters(
            [(swing.time, swing.price) for swing in swing_lows]
        )

        zones: list[PriceZone] = []
        for cluster in equal_highs:
            prices = [price for _, price in cluster]
            zones.append(
                PriceZone(
                    kind="liquidity",
                    lower=min(prices),
                    upper=max(prices),
                    mid=sum(prices) / len(prices),
                    touches=len(cluster),
                    times=tuple(time_ for time_, _ in cluster),
                )
            )
        for cluster in equal_lows:
            prices = [price for _, price in cluster]
            zones.append(
                PriceZone(
                    kind="liquidity",
                    lower=min(prices),
                    upper=max(prices),
                    mid=sum(prices) / len(prices),
                    touches=len(cluster),
                    times=tuple(time_ for time_, _ in cluster),
                )
            )

        zones.sort(key=lambda zone: zone.touches, reverse=True)
        return zones[: self.config.max_zones]

    def _equal_level_clusters(
        self,
        points: list[tuple[object, float]],
    ) -> list[list[tuple[object, float]]]:
        if not points:
            return []

        tolerance = self.config.liquidity_tolerance_pct
        clusters: list[list[tuple[object, float]]] = []

        for time_, price in sorted(points, key=lambda item: item[1]):
            placed = False
            for cluster in clusters:
                mid = sum(item[1] for item in cluster) / len(cluster)
                if abs(price - mid) / mid <= tolerance:
                    cluster.append((time_, price))
                    placed = True
                    break
            if not placed:
                clusters.append([(time_, price)])

        return [cluster for cluster in clusters if len(cluster) >= self.config.min_zone_touches]

    @staticmethod
    def _make_pattern_event(
        kind: StructureEventKind,
        swing: SwingPoint,
        reference_price: float,
        description: str,
    ) -> StructureEvent:
        return StructureEvent(
            kind=kind,
            bar_index=swing.bar_index,
            time=swing.time,
            price=swing.price,
            reference_price=reference_price,
            description=description,
        )

    @staticmethod
    def _determine_trend(hh: bool, hl: bool, lh: bool, ll: bool) -> StructureTrend:
        if hh and hl:
            return "bullish"
        if lh and ll:
            return "bearish"
        return "ranging"

    @staticmethod
    def _infer_trend_from_price(frame: pd.DataFrame) -> StructureTrend:
        """Fallback trend inference when swing points are sparse."""
        if len(frame) < 20:
            return "ranging"

        midpoint = len(frame) // 2
        prior = frame.iloc[:midpoint]
        recent = frame.iloc[midpoint:]
        prior_high = float(prior["high"].max())
        recent_high = float(recent["high"].max())
        prior_low = float(prior["low"].min())
        recent_low = float(recent["low"].min())

        if recent_high > prior_high and recent_low > prior_low:
            return "bullish"
        if recent_high < prior_high and recent_low < prior_low:
            return "bearish"
        return "ranging"

    @staticmethod
    def _last_event(
        events: list[StructureEvent],
        kinds: tuple[str, ...],
    ) -> StructureEvent | None:
        for event in reversed(events):
            if event.kind in kinds:
                return event
        return None
