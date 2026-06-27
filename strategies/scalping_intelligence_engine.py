"""
Scalping intelligence for Kraitos.

This is not a scalping signal system. It extracts the market-reading concepts
professional scalpers use and returns evidence for story, lifecycle, thesis,
entry timing, sizing, and management.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd

ScalpAction = Literal["scalp", "harvest", "avoid"]

REQUIRED_COLUMNS = ("open", "high", "low", "close", "tick_volume", "spread")


@dataclass(frozen=True)
class ScalpingIntelligenceResult:
    """Microstructure evidence extracted from scalping concepts."""

    symbol: str
    timeframe: str
    micro_trend_state: str
    micro_momentum_state: str
    micro_liquidity_state: str
    micro_structure_state: str
    micro_breakout_state: str
    micro_reversion_state: str
    scalp_quality_score: int
    scalp_expectancy_score: int
    momentum_quality_score: int
    microstructure_quality: int
    breakout_quality_score: int
    mean_reversion_probability: float
    suggested_action: ScalpAction
    explanation: str
    evidence: tuple[str, ...] = ()
    thesis_questions: dict[str, str] | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence"] = tuple(self.evidence)
        return data


@dataclass(frozen=True)
class ScalpingIntelligenceConfig:
    """Relative, data-adaptive parameters for micro evidence extraction."""

    min_candles: int = 60
    fast_ema: int = 8
    mid_ema: int = 21
    slow_ema: int = 34
    vwap_window: int = 40
    structure_lookback: int = 18
    breakout_lookback: int = 20
    momentum_lookback: int = 5
    atr_period: int = 14


class ScalpingIntelligenceEngineError(Exception):
    """Raised when scalping intelligence input is invalid."""


class ScalpingIntelligenceEngine:
    """Convert scalping tools into market intelligence, not trade triggers."""

    def __init__(self, config: ScalpingIntelligenceConfig | None = None) -> None:
        self.config = config or ScalpingIntelligenceConfig()

    def analyze(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str,
        timeframe: str = "M1",
        spread_pips: float | None = None,
        spread_limit: float = 2.0,
        market_phase: str = "unknown",
        reversal_pressure: float = 0.0,
    ) -> ScalpingIntelligenceResult:
        frame = self._prepare(candles)
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        open_ = frame["open"].astype(float)
        volume = frame["tick_volume"].astype(float)
        spread = float(spread_pips if spread_pips is not None else frame["spread"].iloc[-1])

        atr = self._atr(frame)
        atr_now = float(atr.iloc[-1]) or float((high - low).tail(20).median()) or 1.0
        ema_fast = close.ewm(span=self.config.fast_ema, adjust=False).mean()
        ema_mid = close.ewm(span=self.config.mid_ema, adjust=False).mean()
        ema_slow = close.ewm(span=self.config.slow_ema, adjust=False).mean()
        vwap = self._rolling_vwap(frame)

        micro_trend_state, trend_score, trend_evidence = self._micro_trend(
            close, ema_fast, ema_mid, ema_slow, atr_now
        )
        micro_momentum_state, momentum_score, momentum_evidence = self._momentum(
            close, high, low, atr_now
        )
        micro_liquidity_state, liquidity_score, liquidity_evidence = self._liquidity(
            frame, vwap, spread=spread, spread_limit=spread_limit
        )
        micro_structure_state, structure_score, structure_evidence = self._microstructure(
            frame, atr_now
        )
        micro_breakout_state, breakout_score, breakout_evidence = self._breakout(
            frame, volume, atr_now
        )
        micro_reversion_state, reversion_probability, reversion_evidence = self._reversion(
            close, high, low, ema_mid, atr, atr_now
        )

        spread_quality = max(0.0, min(1.0, 1.0 - spread / max(spread_limit, 0.01)))
        lifecycle_quality = max(0.0, min(1.0, 1.0 - reversal_pressure))
        if market_phase in {"distribution", "reversal_warning", "confirmed_reversal"}:
            lifecycle_quality *= 0.65
        quality = (
            0.18 * trend_score
            + 0.18 * momentum_score
            + 0.18 * liquidity_score
            + 0.18 * structure_score
            + 0.12 * breakout_score
            + 0.10 * lifecycle_quality
            + 0.06 * spread_quality
        )
        expectancy = quality * (1.0 - 0.28 * reversion_probability)
        if micro_reversion_state.startswith("overextended"):
            expectancy *= 0.85
        scalp_quality_score = self._score(quality)
        scalp_expectancy_score = self._score(expectancy)
        action = self._suggest_action(scalp_quality_score, scalp_expectancy_score)

        evidence = tuple(
            item
            for group in (
                trend_evidence,
                momentum_evidence,
                liquidity_evidence,
                structure_evidence,
                breakout_evidence,
                reversion_evidence,
            )
            for item in group
        )
        thesis_questions = self._thesis_questions(
            action=action,
            liquidity=micro_liquidity_state,
            structure=micro_structure_state,
            breakout=micro_breakout_state,
            reversion=micro_reversion_state,
            expectancy=scalp_expectancy_score,
        )
        explanation = (
            f"Scalping intelligence {action}: quality {scalp_quality_score}/100, "
            f"expectancy {scalp_expectancy_score}/100. Trend={micro_trend_state}; "
            f"momentum={micro_momentum_state}; liquidity={micro_liquidity_state}; "
            f"structure={micro_structure_state}; breakout={micro_breakout_state}; "
            f"reversion={micro_reversion_state}."
        )
        return ScalpingIntelligenceResult(
            symbol=symbol,
            timeframe=timeframe,
            micro_trend_state=micro_trend_state,
            micro_momentum_state=micro_momentum_state,
            micro_liquidity_state=micro_liquidity_state,
            micro_structure_state=micro_structure_state,
            micro_breakout_state=micro_breakout_state,
            micro_reversion_state=micro_reversion_state,
            scalp_quality_score=scalp_quality_score,
            scalp_expectancy_score=scalp_expectancy_score,
            momentum_quality_score=self._score(momentum_score),
            microstructure_quality=self._score(structure_score),
            breakout_quality_score=self._score(breakout_score),
            mean_reversion_probability=round(reversion_probability, 4),
            suggested_action=action,
            explanation=explanation,
            evidence=evidence,
            thesis_questions=thesis_questions,
        )

    def _prepare(self, candles: pd.DataFrame) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise ScalpingIntelligenceEngineError("candle data is empty")
        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise ScalpingIntelligenceEngineError(f"missing columns: {', '.join(missing)}")
        frame = candles.copy()
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            frame = frame.sort_values("time")
        frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if len(frame) < self.config.min_candles:
            raise ScalpingIntelligenceEngineError(
                f"need at least {self.config.min_candles} candles"
            )
        return frame

    def _atr(self, frame: pd.DataFrame) -> pd.Series:
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(self.config.atr_period, min_periods=3).mean().bfill()

    def _rolling_vwap(self, frame: pd.DataFrame) -> pd.Series:
        typical = (frame["high"].astype(float) + frame["low"].astype(float) + frame["close"].astype(float)) / 3.0
        volume = frame["tick_volume"].astype(float).clip(lower=1.0)
        num = (typical * volume).rolling(self.config.vwap_window, min_periods=5).sum()
        den = volume.rolling(self.config.vwap_window, min_periods=5).sum()
        return (num / den).bfill()

    def _micro_trend(
        self,
        close: pd.Series,
        ema_fast: pd.Series,
        ema_mid: pd.Series,
        ema_slow: pd.Series,
        atr_now: float,
    ) -> tuple[str, float, tuple[str, ...]]:
        stacked_bull = ema_fast.iloc[-1] > ema_mid.iloc[-1] > ema_slow.iloc[-1]
        stacked_bear = ema_fast.iloc[-1] < ema_mid.iloc[-1] < ema_slow.iloc[-1]
        slope_fast = (ema_fast.iloc[-1] - ema_fast.iloc[-6]) / atr_now
        slope_mid = (ema_mid.iloc[-1] - ema_mid.iloc[-8]) / atr_now
        price_respects = abs(close.iloc[-1] - ema_fast.iloc[-1]) <= atr_now * 1.2
        accelerating = abs(slope_fast) > abs(slope_mid)
        evidence: list[str] = []
        if stacked_bull:
            evidence.append("EMA ribbon bullish")
            state = "strengthening_bullish" if slope_fast > 0 and accelerating else "bullish_but_fading"
            score = 0.78 if state == "strengthening_bullish" else 0.62
        elif stacked_bear:
            evidence.append("EMA ribbon bearish")
            state = "strengthening_bearish" if slope_fast < 0 and accelerating else "bearish_but_fading"
            score = 0.78 if state == "strengthening_bearish" else 0.62
        else:
            state = "mixed_or_transitioning"
            score = 0.48
            evidence.append("EMA ribbon mixed")
        if price_respects:
            evidence.append("price respecting micro trend structure")
            score += 0.08
        return state, min(score, 1.0), tuple(evidence)

    def _momentum(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        atr_now: float,
    ) -> tuple[str, float, tuple[str, ...]]:
        lookback = self.config.momentum_lookback
        impulse_now = (close.iloc[-1] - close.iloc[-1 - lookback]) / atr_now
        impulse_prev = (close.iloc[-1 - lookback] - close.iloc[-1 - 2 * lookback]) / atr_now
        range_now = (high.iloc[-lookback:].max() - low.iloc[-lookback:].min()) / atr_now
        making_high = close.iloc[-1] >= close.iloc[-lookback:].max()
        making_low = close.iloc[-1] <= close.iloc[-lookback:].min()
        divergence = (making_high and impulse_now < impulse_prev) or (
            making_low and impulse_now > impulse_prev
        )
        evidence: list[str] = []
        if divergence:
            evidence.append("momentum diverging from price")
            return "diverging", 0.38, tuple(evidence)
        if abs(impulse_now) > abs(impulse_prev):
            evidence.append("momentum accelerating")
            return "accelerating", min(1.0, 0.58 + min(abs(impulse_now), 2.0) * 0.16), tuple(evidence)
        if range_now < 0.8:
            evidence.append("momentum compressed")
            return "compressed", 0.46, tuple(evidence)
        evidence.append("momentum slowing")
        return "slowing", 0.52, tuple(evidence)

    def _liquidity(
        self,
        frame: pd.DataFrame,
        vwap: pd.Series,
        *,
        spread: float,
        spread_limit: float,
    ) -> tuple[str, float, tuple[str, ...]]:
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        volume = frame["tick_volume"].astype(float)
        tail = frame.tail(12)
        accepted_above = int((tail["close"].astype(float) > vwap.tail(12)).sum()) >= 8
        accepted_below = int((tail["close"].astype(float) < vwap.tail(12)).sum()) >= 8
        vwap_rejections = int(
            ((low.tail(12) <= vwap.tail(12)) & (close.tail(12) > vwap.tail(12))).sum()
            + ((high.tail(12) >= vwap.tail(12)) & (close.tail(12) < vwap.tail(12))).sum()
        )
        volume_ratio = float(volume.iloc[-1] / max(volume.rolling(20, min_periods=5).mean().iloc[-1], 1.0))
        spread_drag = spread / max(spread_limit, 0.01)
        evidence: list[str] = []
        score = 0.50 + min(volume_ratio, 1.8) * 0.18 - min(spread_drag, 1.5) * 0.25
        if accepted_above:
            evidence.append("price accepted above VWAP")
            state = "bullish_control_above_vwap"
            score += 0.15
        elif accepted_below:
            evidence.append("price accepted below VWAP")
            state = "bearish_control_below_vwap"
            score += 0.15
        elif vwap_rejections >= 3:
            evidence.append("repeated VWAP rejection")
            state = "directional_vwap_rejection"
            score += 0.10
        else:
            state = "balanced_around_vwap"
        if volume_ratio >= 1.0:
            evidence.append("volume supports participation")
        if spread_drag >= 0.80:
            evidence.append("spread drag elevated")
        return state, max(0.0, min(1.0, score)), tuple(evidence)

    def _microstructure(self, frame: pd.DataFrame, atr_now: float) -> tuple[str, float, tuple[str, ...]]:
        tail = frame.tail(self.config.structure_lookback)
        highs = tail["high"].astype(float)
        lows = tail["low"].astype(float)
        closes = tail["close"].astype(float)
        higher_highs = highs.iloc[-1] > highs.iloc[: len(highs) // 2].max()
        higher_lows = lows.iloc[-1] > lows.iloc[: len(lows) // 2].min()
        lower_highs = highs.iloc[-1] < highs.iloc[: len(highs) // 2].max()
        lower_lows = lows.iloc[-1] < lows.iloc[: len(lows) // 2].min()
        body = (tail["close"].astype(float) - tail["open"].astype(float)).abs()
        wick = (tail["high"].astype(float) - tail["low"].astype(float)) - body
        rejection = float(wick.tail(3).mean()) > float(body.tail(3).mean()) * 1.4
        evidence: list[str] = []
        if higher_highs and higher_lows:
            evidence.append("short-term higher highs and higher lows")
            state = "bullish_micro_control"
            score = 0.74
        elif lower_highs and lower_lows:
            evidence.append("short-term lower highs and lower lows")
            state = "bearish_micro_control"
            score = 0.74
        elif rejection:
            evidence.append("recent rejection candles")
            state = "rejection_or_absorption"
            score = 0.56
        elif (closes.iloc[-1] - closes.iloc[0]) / atr_now > 0.8:
            state = "bullish_pullback_holding"
            score = 0.62
        elif (closes.iloc[0] - closes.iloc[-1]) / atr_now > 0.8:
            state = "bearish_pullback_holding"
            score = 0.62
        else:
            state = "choppy_microstructure"
            score = 0.42
        return state, score, tuple(evidence)

    def _breakout(
        self,
        frame: pd.DataFrame,
        volume: pd.Series,
        atr_now: float,
    ) -> tuple[str, float, tuple[str, ...]]:
        lookback = self.config.breakout_lookback
        prior = frame.iloc[-lookback - 1 : -1]
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        upper = float(prior["high"].max())
        lower = float(prior["low"].min())
        broke_up = close.iloc[-1] > upper
        broke_down = close.iloc[-1] < lower
        volume_ratio = float(volume.iloc[-1] / max(volume.rolling(20, min_periods=5).mean().iloc[-1], 1.0))
        follow = abs(close.iloc[-1] - close.iloc[-3]) / atr_now
        evidence: list[str] = []
        if broke_up or broke_down:
            if volume_ratio >= 1.0:
                evidence.append("breakout volume supportive")
            if follow >= 0.8:
                evidence.append("breakout follow-through present")
            held = low.iloc[-1] > upper if broke_up else high.iloc[-1] < lower
            if held:
                evidence.append("breakout held without immediate rejection")
                return "breakout_holding", min(1.0, 0.58 + 0.18 * volume_ratio + 0.12 * follow), tuple(evidence)
            evidence.append("immediate breakout rejection")
            return "failed_breakout_or_breakdown", 0.36, tuple(evidence)
        if high.iloc[-1] >= upper and close.iloc[-1] < upper:
            evidence.append("failed upside continuation")
            return "failed_upside_breakout", 0.42, tuple(evidence)
        if low.iloc[-1] <= lower and close.iloc[-1] > lower:
            evidence.append("failed downside continuation")
            return "failed_downside_breakdown", 0.42, tuple(evidence)
        return "no_active_breakout", 0.50, tuple(evidence)

    def _reversion(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        ema_mid: pd.Series,
        atr: pd.Series,
        atr_now: float,
    ) -> tuple[str, float, tuple[str, ...]]:
        distance = abs(close.iloc[-1] - ema_mid.iloc[-1]) / atr_now
        atr_ratio = float(atr.iloc[-1] / max(atr.rolling(40, min_periods=10).mean().iloc[-1], atr_now))
        move = abs(close.iloc[-1] - close.iloc[-10]) / atr_now
        wick_ratio = float(((high - low) - (close - close.shift(1)).abs()).tail(5).mean() / max(atr_now, 1e-9))
        probability = min(1.0, 0.18 * distance + 0.20 * max(0.0, atr_ratio - 1.0) + 0.16 * move + 0.08 * wick_ratio)
        evidence: list[str] = []
        if distance >= 1.6 or move >= 2.4:
            evidence.append("move stretched from micro value")
        if atr_ratio > 1.25:
            evidence.append("volatility expansion")
        if wick_ratio > 0.6:
            evidence.append("wick behaviour suggests absorption")
        if probability >= 0.62:
            return "overextended_mean_reversion_likely", round(probability, 4), tuple(evidence)
        if probability >= 0.42:
            return "extension_warning", round(probability, 4), tuple(evidence)
        return "continuation_not_stretched", round(probability, 4), tuple(evidence)

    @staticmethod
    def _score(value: float) -> int:
        return int(round(max(0.0, min(1.0, value)) * 100))

    @staticmethod
    def _suggest_action(quality: int, expectancy: int) -> ScalpAction:
        if quality >= 68 and expectancy >= 58:
            return "scalp"
        if quality >= 48 and expectancy >= 42:
            return "harvest"
        return "avoid"

    @staticmethod
    def _thesis_questions(
        *,
        action: ScalpAction,
        liquidity: str,
        structure: str,
        breakout: str,
        reversion: str,
        expectancy: int,
    ) -> dict[str, str]:
        return {
            "why_move_immediately": f"{structure}; {breakout}; expectancy {expectancy}/100",
            "where_is_liquidity": liquidity,
            "who_is_trapped": "breakout traders" if "failed" in breakout else "late counter-trend participants",
            "expected_move": action,
            "what_invalidates": f"loss of {structure} or {reversion} becoming dominant",
        }


__all__ = [
    "ScalpingIntelligenceConfig",
    "ScalpingIntelligenceEngine",
    "ScalpingIntelligenceEngineError",
    "ScalpingIntelligenceResult",
]
