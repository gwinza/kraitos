"""Institutional structure engine — BOS, MSB, OB, FVG, liquidity, premium/discount, OTE."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, swing_points, validate_candles

StructureBias = Literal["bullish", "bearish", "range"]
EventType = Literal["bos", "msb", "none"]


@dataclass(frozen=True)
class OrderBlock:
    """Institutional order block zone."""

    side: Literal["bullish", "bearish"]
    high: float
    low: float
    bar_index: int
    mitigated: bool

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0


@dataclass(frozen=True)
class FairValueGap:
    """Three-candle imbalance zone."""

    side: Literal["bullish", "bearish"]
    high: float
    low: float
    bar_index: int
    filled: bool


@dataclass(frozen=True)
class LiquidityPool:
    """Resting liquidity above/below structure."""

    side: Literal["buy_side", "sell_side"]
    level: float
    strength: float
    swept: bool


@dataclass(frozen=True)
class InstitutionalStructureResult:
    """Full institutional market structure assessment."""

    symbol: str
    timeframe: str
    structure_bias: StructureBias
    bullish_structure_score: int
    bearish_structure_score: int
    range_structure_score: int
    last_event: EventType
    event_direction: Literal["bullish", "bearish", "neutral"]
    order_blocks: tuple[OrderBlock, ...]
    fair_value_gaps: tuple[FairValueGap, ...]
    liquidity_pools: tuple[LiquidityPool, ...]
    premium_zone_high: float
    premium_zone_low: float
    discount_zone_high: float
    discount_zone_low: float
    ote_zone_high: float
    ote_zone_low: float
    equilibrium: float
    in_premium: bool
    in_discount: bool
    in_ote: bool
    explanation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    trade_opportunity: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "structure_bias": self.structure_bias,
            "bullish_structure_score": self.bullish_structure_score,
            "bearish_structure_score": self.bearish_structure_score,
            "range_structure_score": self.range_structure_score,
            "last_event": self.last_event,
            "event_direction": self.event_direction,
            "order_blocks": len(self.order_blocks),
            "fair_value_gaps": len(self.fair_value_gaps),
            "liquidity_pools": len(self.liquidity_pools),
            "premium_zone": [self.premium_zone_low, self.premium_zone_high],
            "discount_zone": [self.discount_zone_low, self.discount_zone_high],
            "ote_zone": [self.ote_zone_low, self.ote_zone_high],
            "equilibrium": self.equilibrium,
            "in_premium": self.in_premium,
            "in_discount": self.in_discount,
            "in_ote": self.in_ote,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "trade_opportunity": self.trade_opportunity,
        }


@dataclass(frozen=True)
class InstitutionalStructureConfig:
    min_candles: int = 50
    lookback: int = 100
    swing_window: int = 2
    ob_lookback: int = 20


class InstitutionalStructureEngineError(Exception):
    pass


class InstitutionalStructureEngine:
    """Map institutional concepts — BOS, MSB, OB, FVG, liquidity, premium/discount, OTE."""

    def __init__(self, config: InstitutionalStructureConfig | None = None) -> None:
        self.config = config or InstitutionalStructureConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "H1",
    ) -> InstitutionalStructureResult:
        try:
            frame = validate_candles(
                candles,
                min_candles=self.config.min_candles,
                engine="InstitutionalStructureEngine",
            ).tail(self.config.lookback)
        except ValueError as exc:
            raise InstitutionalStructureEngineError(str(exc)) from exc

        atr = atr_series(frame)
        atr_value = float(atr.iloc[-1]) or float((frame["high"] - frame["low"]).median()) or 1.0
        highs, lows = swing_points(frame, window=self.config.swing_window)
        current = float(frame["close"].iloc[-1])

        range_high = float(frame["high"].max())
        range_low = float(frame["low"].min())
        equilibrium = (range_high + range_low) / 2.0
        premium_low = equilibrium
        premium_high = range_high
        discount_low = range_low
        discount_high = equilibrium

        swing_range = range_high - range_low
        ote_low = range_high - swing_range * 0.79 if swing_range > 0 else equilibrium
        ote_high = range_high - swing_range * 0.62 if swing_range > 0 else equilibrium
        ote_low_bear = range_low + swing_range * 0.62 if swing_range > 0 else equilibrium
        ote_high_bear = range_low + swing_range * 0.79 if swing_range > 0 else equilibrium

        event, event_dir, event_ev = self._detect_bos_msb(highs, lows, frame, atr_value)
        order_blocks = self._order_blocks(frame, atr_value)
        fvgs = self._fair_value_gaps(frame)
        pools = self._liquidity_pools(highs, lows, frame, atr_value)

        bullish_score = self._bullish_score(highs, lows, event, event_dir, order_blocks, fvgs, current)
        bearish_score = self._bearish_score(highs, lows, event, event_dir, order_blocks, fvgs, current)
        range_score = self._range_score(highs, lows, frame, atr_value)

        if bullish_score >= bearish_score + 12 and bullish_score >= range_score:
            bias: StructureBias = "bullish"
        elif bearish_score >= bullish_score + 12 and bearish_score >= range_score:
            bias = "bearish"
        else:
            bias = "range"

        in_premium = current >= premium_low
        in_discount = current <= discount_high
        in_ote = (
            (ote_low <= current <= ote_high and bias == "bullish")
            or (ote_low_bear <= current <= ote_high_bear and bias == "bearish")
        )

        evidence = list(event_ev)
        if order_blocks:
            evidence.append(f"{len(order_blocks)} active order blocks")
        if fvgs:
            evidence.append(f"{len(fvgs)} open fair value gaps")
        if pools:
            evidence.append(f"{len(pools)} liquidity pools mapped")
        if in_discount and bias == "bullish":
            evidence.append("price in discount — favourable for longs")
        if in_premium and bias == "bearish":
            evidence.append("price in premium — favourable for shorts")
        if in_ote:
            evidence.append("price in OTE zone")

        opportunity = self._trade_opportunity(bias, event, event_dir, in_premium, in_discount, in_ote)

        return InstitutionalStructureResult(
            symbol=symbol,
            timeframe=timeframe,
            structure_bias=bias,
            bullish_structure_score=bullish_score,
            bearish_structure_score=bearish_score,
            range_structure_score=range_score,
            last_event=event,
            event_direction=event_dir,
            order_blocks=tuple(order_blocks),
            fair_value_gaps=tuple(fvgs),
            liquidity_pools=tuple(pools),
            premium_zone_high=premium_high,
            premium_zone_low=premium_low,
            discount_zone_high=discount_high,
            discount_zone_low=discount_low,
            ote_zone_high=ote_high if bias != "bearish" else ote_high_bear,
            ote_zone_low=ote_low if bias != "bearish" else ote_low_bear,
            equilibrium=equilibrium,
            in_premium=in_premium,
            in_discount=in_discount,
            in_ote=in_ote,
            explanation=(
                f"{bias} structure — bullish {bullish_score}/100, bearish {bearish_score}/100, "
                f"range {range_score}/100 | last event: {event}"
            ),
            evidence=tuple(evidence),
            trade_opportunity=opportunity,
        )

    @staticmethod
    def _detect_bos_msb(
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        frame: pd.DataFrame,
        atr_value: float,
    ) -> tuple[EventType, Literal["bullish", "bearish", "neutral"], list[str]]:
        evidence: list[str] = []
        if len(highs) < 2 or len(lows) < 2:
            return "none", "neutral", evidence
        last_close = float(frame["close"].iloc[-1])
        prev_high = highs[-2][1]
        prev_low = lows[-2][1]

        if last_close > prev_high + atr_value * 0.05:
            evidence.append(f"BOS bullish — closed above {prev_high:.5f}")
            return "bos", "bullish", evidence
        if last_close < prev_low - atr_value * 0.05:
            evidence.append(f"BOS bearish — closed below {prev_low:.5f}")
            return "bos", "bearish", evidence

        if highs[-1][1] < highs[-2][1] and last_close < lows[-2][1]:
            evidence.append("MSB bearish — structure shift")
            return "msb", "bearish", evidence
        if lows[-1][1] > lows[-2][1] and last_close > highs[-2][1]:
            evidence.append("MSB bullish — structure shift")
            return "msb", "bullish", evidence
        return "none", "neutral", evidence

    def _order_blocks(self, frame: pd.DataFrame, atr_value: float) -> list[OrderBlock]:
        blocks: list[OrderBlock] = []
        lookback = min(self.config.ob_lookback, len(frame) - 3)
        for i in range(len(frame) - lookback, len(frame) - 1):
            bar = frame.iloc[i]
            nxt = frame.iloc[i + 1]
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            body = abs(c - o)
            range_ = h - l
            if range_ <= 0:
                continue
            impulse = float(nxt["close"]) - c
            if c < o and impulse > atr_value * 0.4 and body / range_ > 0.45:
                blocks.append(OrderBlock("bullish", h, l, i, mitigated=float(frame["low"].iloc[-1]) < l))
            elif c > o and impulse < -atr_value * 0.4 and body / range_ > 0.45:
                blocks.append(OrderBlock("bearish", h, l, i, mitigated=float(frame["high"].iloc[-1]) > h))
        return blocks[-5:]

    @staticmethod
    def _fair_value_gaps(frame: pd.DataFrame) -> list[FairValueGap]:
        gaps: list[FairValueGap] = []
        for i in range(2, len(frame)):
            c0 = frame.iloc[i - 2]
            c2 = frame.iloc[i]
            if float(c2["low"]) > float(c0["high"]):
                gaps.append(
                    FairValueGap(
                        "bullish",
                        float(c2["low"]),
                        float(c0["high"]),
                        i,
                        filled=float(frame["low"].iloc[-1]) <= float(c0["high"]),
                    )
                )
            elif float(c2["high"]) < float(c0["low"]):
                gaps.append(
                    FairValueGap(
                        "bearish",
                        float(c0["low"]),
                        float(c2["high"]),
                        i,
                        filled=float(frame["high"].iloc[-1]) >= float(c0["low"]),
                    )
                )
        return [g for g in gaps if not g.filled][-5:]

    @staticmethod
    def _liquidity_pools(
        highs: list[tuple[int, float]],
        lows: list[tuple[int, float]],
        frame: pd.DataFrame,
        atr_value: float,
    ) -> list[LiquidityPool]:
        pools: list[LiquidityPool] = []
        current = float(frame["close"].iloc[-1])
        if highs:
            buy_level = max(h for _, h in highs[-3:])
            pools.append(
                LiquidityPool(
                    "buy_side",
                    buy_level,
                    0.75,
                    swept=current > buy_level + atr_value * 0.05,
                )
            )
        if lows:
            sell_level = min(l for _, l in lows[-3:])
            pools.append(
                LiquidityPool(
                    "sell_side",
                    sell_level,
                    0.75,
                    swept=current < sell_level - atr_value * 0.05,
                )
            )
        return pools

    @staticmethod
    def _bullish_score(
        highs, lows, event, event_dir, order_blocks, fvgs, current
    ) -> int:
        score = 40.0
        if len(highs) >= 2 and highs[-1][1] > highs[-2][1]:
            score += 15
        if len(lows) >= 2 and lows[-1][1] > lows[-2][1]:
            score += 15
        if event == "bos" and event_dir == "bullish":
            score += 20
        if event == "msb" and event_dir == "bullish":
            score += 12
        score += min(10, sum(1 for ob in order_blocks if ob.side == "bullish" and not ob.mitigated) * 4)
        score += min(8, sum(1 for g in fvgs if g.side == "bullish") * 3)
        return int(max(0, min(100, round(score))))

    @staticmethod
    def _bearish_score(
        highs, lows, event, event_dir, order_blocks, fvgs, current
    ) -> int:
        score = 40.0
        if len(highs) >= 2 and highs[-1][1] < highs[-2][1]:
            score += 15
        if len(lows) >= 2 and lows[-1][1] < lows[-2][1]:
            score += 15
        if event == "bos" and event_dir == "bearish":
            score += 20
        if event == "msb" and event_dir == "bearish":
            score += 12
        score += min(10, sum(1 for ob in order_blocks if ob.side == "bearish" and not ob.mitigated) * 4)
        score += min(8, sum(1 for g in fvgs if g.side == "bearish") * 3)
        return int(max(0, min(100, round(score))))

    @staticmethod
    def _range_score(highs, lows, frame, atr_value) -> int:
        if len(highs) < 2 or len(lows) < 2:
            return 50
        high_flat = abs(highs[-1][1] - highs[-2][1]) < atr_value * 0.3
        low_flat = abs(lows[-1][1] - lows[-2][1]) < atr_value * 0.3
        score = 35.0
        if high_flat:
            score += 20
        if low_flat:
            score += 20
        width = float(frame["high"].max()) - float(frame["low"].min())
        if width < atr_value * 8:
            score += 15
        return int(max(0, min(100, round(score))))

    @staticmethod
    def _trade_opportunity(
        bias: StructureBias,
        event: EventType,
        event_dir: str,
        in_premium: bool,
        in_discount: bool,
        in_ote: bool,
    ) -> str:
        if bias == "bullish":
            if in_discount or in_ote:
                return "Long from discount/OTE after bullish BOS or OB mitigation"
            return "Long continuations on pullbacks to bullish OB or FVG"
        if bias == "bearish":
            if in_premium or in_ote:
                return "Short from premium/OTE after bearish BOS or OB mitigation"
            return "Short continuations on rallies to bearish OB or FVG"
        return "Range trade extremes — scout breakout above buy-side or below sell-side liquidity"


__all__ = [
    "EventType",
    "FairValueGap",
    "InstitutionalStructureConfig",
    "InstitutionalStructureEngine",
    "InstitutionalStructureEngineError",
    "InstitutionalStructureResult",
    "LiquidityPool",
    "OrderBlock",
    "StructureBias",
]
