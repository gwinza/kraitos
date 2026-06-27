"""Indicator Interpretation Engine — psychological evidence, never trade signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from core.helpers import pip_size_for_symbol
from intelligence.asset_trend_analyzer import AssetTrendAnalyzer, AssetTrendFeatures
from intelligence.evidence_synthesis_engine import EvidencePiece

if TYPE_CHECKING:
    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

FORBIDDEN_OUTPUT = (
    "buy",
    "sell",
    "no_trade",
    "veto",
    "reject",
    "block",
)

INDICATOR_INTERPRETATION_DNA = """
Indicators do not create trades.
Indicators do not veto trades.
Indicators interpret market psychology and support the TraderBrain.

Kraitos reads moving averages, momentum, volatility, volume, and price action as
evidence of who is in control, whether conviction is strengthening or fading, and
what participants are feeling — fear, greed, uncertainty, euphoria, panic,
accumulation, or distribution.

Understanding indicators helps Kraitos recognise more opportunities.
They never filter, trigger, or refuse a trade on their own.
""".strip()

PRIMARY_TIMEFRAME = "H1"
INTERPRETATION_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")

VALID_OPPORTUNITY_HINTS = frozenset({
    "mean_reversion_snapback",
    "compression_breakout",
    "pullback_continuation",
    "liquidity_sweep",
    "liquidity_sweep_snapback",
    "trend_pause_resume",
    "failed_breakout",
})

INDICATOR_NAMES = (
    "Moving averages",
    "ADX",
    "RSI",
    "MACD",
    "Bollinger Bands",
    "ATR",
    "OBV",
    "Accumulation/Distribution",
    "Sentiment",
    "Volume",
    "Price Action",
    "Candlesticks",
)


@dataclass(frozen=True)
class PsychologicalReading:
    """Single indicator psychology slice — evidence, not a command."""

    indicator: str
    reading: str
    psychology: str
    direction: str = "neutral"
    strength: float = 50.0

    def to_dict(self) -> dict:
        return {
            "indicator": self.indicator,
            "reading": self.reading,
            "psychology": self.psychology,
            "direction": self.direction,
            "strength": round(self.strength, 1),
        }


@dataclass(frozen=True)
class IndicatorInterpretation:
    """Full indicator psychology read for one symbol."""

    symbol: str
    psychological_readings: tuple[PsychologicalReading, ...]
    market_explanation_contribution: str
    observations: tuple[str, ...]
    forecast_implications: tuple[str, ...]
    opportunity_hints: tuple[str, ...]
    insight_score: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "psychological_readings": [r.to_dict() for r in self.psychological_readings],
            "market_explanation_contribution": self.market_explanation_contribution,
            "observations": list(self.observations),
            "forecast_implications": list(self.forecast_implications),
            "opportunity_hints": list(self.opportunity_hints),
            "insight_score": round(self.insight_score, 2),
        }

    def to_evidence_pieces(self) -> list[EvidencePiece]:
        pieces: list[EvidencePiece] = []
        for reading in self.psychological_readings:
            signal = reading.indicator.lower().replace(" ", "_").replace("/", "_")
            pieces.append(EvidencePiece(
                category="indicator_psychology",
                timeframe=PRIMARY_TIMEFRAME,
                signal=signal,
                description=f"{reading.indicator}: {reading.reading}",
                direction=reading.direction,
                strength=reading.strength,
            ))
        return pieces


@dataclass
class InterpretationStats:
    """Accumulated interpretation metrics for validation reporting."""

    interpreted: int = 0
    opportunity_hints_emitted: int = 0
    evidence_pieces_added: int = 0


@dataclass
class _IndicatorMetrics:
    ma_slope: float
    ma_control: str
    adx: float
    rsi: float
    macd_hist: float
    macd_accel: float
    bb_width_ratio: float
    bb_position: float
    atr_ratio: float
    obv_slope: float
    ad_line_slope: float
    volume_ratio: float
    momentum_pips: float
    range_ratio: float
    wick_rejection: bool
    inside_bar: bool
    outside_bar: bool
    pin_bar: bool
    engulfing: str
    trend_flattening: bool
    liquidity_rejection: bool


class IndicatorInterpretationEngine:
    """
    Interpret indicators as market psychology.

    Indicators enrich understanding — they never create trades or refuse them.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._analyzer = AssetTrendAnalyzer()
        self._latest: dict[str, IndicatorInterpretation] = {}
        self.stats = InterpretationStats()

    def interpret(
        self,
        *,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult | None = None,
        narrative_direction: str = "neutral",
        features: AssetTrendFeatures | None = None,
        spread_pips: float = 1.0,
        spread_limit: float = 3.0,
    ) -> IndicatorInterpretation:
        symbol = symbol.strip().upper()
        frame = self._primary_frame(candles)
        metrics = self._compute_metrics(symbol, frame, structure, candles)

        if features is None and regime is not None and frame is not None and len(frame) >= 5:
            features = self._analyzer._compute_features(
                candles=candles,
                bias=bias,
                structure=structure,
                regime=regime,
                spread_pips=spread_pips,
                spread_limit=spread_limit,
                target_pips=10.0,
                in_active_session=True,
            )

        readings = self._build_readings(
            metrics,
            structure=structure,
            bias=bias,
            narrative_direction=narrative_direction,
            features=features,
        )
        hints = self._derive_opportunity_hints(metrics, readings, structure)
        observations = self._build_observations(metrics, readings)
        forecast = self._build_forecast_implications(metrics, hints)
        contribution = self._build_contribution(readings, hints)
        insight = self._compute_insight_score(readings, hints, features)

        result = IndicatorInterpretation(
            symbol=symbol,
            psychological_readings=tuple(readings),
            market_explanation_contribution=contribution,
            observations=tuple(observations),
            forecast_implications=tuple(forecast),
            opportunity_hints=tuple(hints),
            insight_score=insight,
        )
        self._latest[symbol] = result
        self.stats.interpreted += 1
        self.stats.opportunity_hints_emitted += len(hints)
        self.stats.evidence_pieces_added += len(result.to_evidence_pieces())
        return result

    @staticmethod
    def _primary_frame(candles: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
        for tf in (PRIMARY_TIMEFRAME, "H4", "M15", "M5", "M1"):
            frame = candles.get(tf)
            if frame is not None and len(frame) >= 5:
                return frame
        return None

    def _compute_metrics(
        self,
        symbol: str,
        frame: pd.DataFrame | None,
        structure: MarketContext,
        candles: dict[str, pd.DataFrame],
    ) -> _IndicatorMetrics:
        if frame is None or len(frame) < 10:
            return _IndicatorMetrics(
                ma_slope=0.0,
                ma_control="contested",
                adx=15.0,
                rsi=50.0,
                macd_hist=0.0,
                macd_accel=0.0,
                bb_width_ratio=1.0,
                bb_position=0.5,
                atr_ratio=1.0,
                obv_slope=0.0,
                ad_line_slope=0.0,
                volume_ratio=1.0,
                momentum_pips=0.0,
                range_ratio=1.0,
                wick_rejection=False,
                inside_bar=False,
                outside_bar=False,
                pin_bar=False,
                engulfing="none",
                trend_flattening=False,
                liquidity_rejection=bool(structure.liquidity_zones),
            )

        closes = frame["close"].astype(float).values
        highs = frame["high"].astype(float).values
        lows = frame["low"].astype(float).values
        opens = frame["open"].astype(float).values
        volumes = (
            frame["tick_volume"].astype(float).values
            if "tick_volume" in frame.columns
            else np.ones(len(closes))
        )
        pip = pip_size_for_symbol(symbol)

        ma = _sma(closes, 20)
        ma_slope = (ma[-1] - ma[-5]) / pip if len(ma) >= 5 else 0.0
        if ma_slope > 1.5:
            ma_control = "bulls"
        elif ma_slope < -1.5:
            ma_control = "bears"
        else:
            ma_control = "contested"

        adx = _adx(highs, lows, closes)
        rsi = _rsi(closes)
        macd_line, signal_line = _macd(closes)
        macd_hist = macd_line[-1] - signal_line[-1] if len(macd_line) else 0.0
        prior_hist = macd_line[-2] - signal_line[-2] if len(macd_line) >= 2 else 0.0
        macd_accel = macd_hist - prior_hist

        upper, middle, lower = _bollinger(closes)
        bb_width = (upper[-1] - lower[-1]) / max(middle[-1], pip)
        prior_width = (upper[-10] - lower[-10]) / max(middle[-10], pip) if len(upper) >= 10 else bb_width
        bb_width_ratio = bb_width / max(prior_width, pip * 0.1)
        bb_position = (closes[-1] - lower[-1]) / max(upper[-1] - lower[-1], pip * 0.1)

        atr = _atr(highs, lows, closes)
        atr_recent = atr[-5:].mean() if len(atr) >= 5 else atr[-1]
        atr_prior = atr[-20:-5].mean() if len(atr) >= 20 else atr_recent
        atr_ratio = atr_recent / max(atr_prior, pip * 0.1)

        obv = _obv(closes, volumes)
        obv_slope = (obv[-1] - obv[-8]) / max(abs(obv[-8]), 1.0) if len(obv) >= 8 else 0.0

        ad_line = _accumulation_distribution(highs, lows, closes, volumes)
        ad_slope = (ad_line[-1] - ad_line[-8]) / max(abs(ad_line[-8]), 1.0) if len(ad_line) >= 8 else 0.0

        vol_recent = volumes[-5:].mean()
        vol_prior = volumes[-15:-5].mean() if len(volumes) >= 15 else vol_recent
        volume_ratio = vol_recent / max(vol_prior, 1.0)

        momentum_pips = (closes[-1] - closes[-8]) / pip if len(closes) >= 8 else 0.0
        recent_range = (highs[-8:].max() - lows[-8:].min()) / pip
        prior_range = (
            (highs[-20:-8].max() - lows[-20:-8].min()) / pip
            if len(closes) >= 20
            else recent_range
        )
        range_ratio = recent_range / max(prior_range, 0.1)

        body = abs(closes[-1] - opens[-1])
        full_range = max(highs[-1] - lows[-1], pip * 0.1)
        wick_upper = highs[-1] - max(closes[-1], opens[-1])
        wick_lower = min(closes[-1], opens[-1]) - lows[-1]
        wick_rejection = wick_upper > body * 1.5 or wick_lower > body * 1.5
        pin_bar = body < full_range * 0.35 and (wick_upper > body * 2 or wick_lower > body * 2)
        inside_bar = len(closes) >= 2 and highs[-1] <= highs[-2] and lows[-1] >= lows[-2]
        outside_bar = len(closes) >= 2 and highs[-1] > highs[-2] and lows[-1] < lows[-2]

        engulfing = "none"
        if len(closes) >= 2:
            prev_body = abs(closes[-2] - opens[-2])
            if closes[-1] > opens[-1] and closes[-2] < opens[-2] and body > prev_body * 1.1:
                engulfing = "bullish"
            elif closes[-1] < opens[-1] and closes[-2] > opens[-2] and body > prev_body * 1.1:
                engulfing = "bearish"

        trend_flattening = False
        if len(closes) >= 20:
            early = (closes[-20] - closes[-15]) / pip
            late = (closes[-5] - closes[-1]) / pip
            if abs(early) > 3.0 and abs(late) < abs(early) * 0.35:
                trend_flattening = True

        liquidity_rejection = wick_rejection and bool(structure.liquidity_zones)

        m15 = candles.get("M15")
        if m15 is not None and len(m15) >= 3 and structure.liquidity_zones:
            m15_highs = m15["high"].astype(float).values
            m15_lows = m15["low"].astype(float).values
            m15_closes = m15["close"].astype(float).values
            m15_opens = m15["open"].astype(float).values
            m15_body = abs(m15_closes[-1] - m15_opens[-1])
            m15_range = max(m15_highs[-1] - m15_lows[-1], pip * 0.1)
            m15_wick_u = m15_highs[-1] - max(m15_closes[-1], m15_opens[-1])
            m15_wick_l = min(m15_closes[-1], m15_opens[-1]) - m15_lows[-1]
            if m15_wick_u > m15_body * 1.5 or m15_wick_l > m15_body * 1.5:
                liquidity_rejection = True

        return _IndicatorMetrics(
            ma_slope=ma_slope,
            ma_control=ma_control,
            adx=adx,
            rsi=rsi,
            macd_hist=macd_hist,
            macd_accel=macd_accel,
            bb_width_ratio=bb_width_ratio,
            bb_position=bb_position,
            atr_ratio=atr_ratio,
            obv_slope=obv_slope,
            ad_line_slope=ad_slope,
            volume_ratio=volume_ratio,
            momentum_pips=momentum_pips,
            range_ratio=range_ratio,
            wick_rejection=wick_rejection,
            inside_bar=inside_bar,
            outside_bar=outside_bar,
            pin_bar=pin_bar,
            engulfing=engulfing,
            trend_flattening=trend_flattening,
            liquidity_rejection=liquidity_rejection,
        )

    def _build_readings(
        self,
        metrics: _IndicatorMetrics,
        *,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        narrative_direction: str,
        features: AssetTrendFeatures | None,
    ) -> list[PsychologicalReading]:
        readings: list[PsychologicalReading] = []

        if metrics.ma_control == "bulls":
            ma_reading = "Buy-side participants steering price higher"
            ma_psych = "Bulls appear in control — buyers absorbing supply"
            ma_dir = "bullish"
        elif metrics.ma_control == "bears":
            ma_reading = "Sell-side participants steering price lower"
            ma_psych = "Bears appear in control — sellers pressing supply"
            ma_dir = "bearish"
        else:
            ma_reading = "Neither side holds clear directional control"
            ma_psych = "Participants undecided — range behaviour likely"
            ma_dir = "neutral"
        readings.append(PsychologicalReading(
            "Moving averages", ma_reading, ma_psych, ma_dir, 55.0 + min(25.0, abs(metrics.ma_slope) * 3),
        ))

        if metrics.adx >= 25:
            adx_reading = "Strong directional conviction — one side dominates"
            adx_psych = "Conviction strengthening — trend participants committed"
            adx_strength = 72.0
        elif metrics.adx >= 18:
            adx_reading = "Moderate directional conviction building"
            adx_psych = "Control emerging but not yet overwhelming"
            adx_strength = 58.0
        else:
            adx_reading = "Weak directional conviction — control contested"
            adx_psych = "Uncertainty — neither side dominates"
            adx_strength = 45.0
        adx_dir = structure.trend if structure.trend != "neutral" else (
            "bullish" if metrics.ma_slope > 0 else "bearish" if metrics.ma_slope < 0 else "neutral"
        )
        readings.append(PsychologicalReading(
            "ADX", adx_reading, adx_psych, adx_dir, adx_strength,
        ))

        if metrics.rsi >= 72:
            rsi_reading = "Momentum stretched — euphoria in the move"
            rsi_psych = "Greed and euphoria — late participants chasing"
            rsi_dir = "bullish"
        elif metrics.rsi >= 60:
            rsi_reading = "Momentum elevated — stretch building"
            rsi_psych = "Optimism building — conviction on the upside"
            rsi_dir = "bullish"
        elif metrics.rsi <= 28:
            rsi_reading = "Momentum stretched lower — panic selling"
            rsi_psych = "Fear and panic — capitulation mood possible"
            rsi_dir = "bearish"
        elif metrics.rsi <= 40:
            rsi_reading = "Momentum depressed — stretch on downside"
            rsi_psych = "Fear dominant — sellers exhausted or pressing"
            rsi_dir = "bearish"
        else:
            rsi_reading = "Momentum balanced — no stretch signal"
            rsi_psych = "Participants neutral; room to move either way"
            rsi_dir = "neutral"
        readings.append(PsychologicalReading(
            "RSI", rsi_reading, rsi_psych, rsi_dir, 50.0 + abs(metrics.rsi - 50) * 0.6,
        ))

        if metrics.macd_accel > 0 and metrics.macd_hist > 0:
            macd_reading = "Momentum accelerating in the bullish direction"
            macd_psych = "Participants increasing commitment to the upside"
            macd_dir = "bullish"
        elif metrics.macd_accel < 0 and metrics.macd_hist < 0:
            macd_reading = "Momentum accelerating in the bearish direction"
            macd_psych = "Participants increasing commitment to the downside"
            macd_dir = "bearish"
        elif metrics.macd_hist > 0:
            macd_reading = "Momentum positive but fading"
            macd_psych = "Conviction weakening — upside momentum losing steam"
            macd_dir = "bullish"
        elif metrics.macd_hist < 0:
            macd_reading = "Momentum negative but stabilising"
            macd_psych = "Selling pressure easing — downside momentum fading"
            macd_dir = "bearish"
        else:
            macd_reading = "Momentum flat — participants waiting"
            macd_psych = "Uncertainty — no directional commitment"
            macd_dir = "neutral"
        readings.append(PsychologicalReading(
            "MACD", macd_reading, macd_psych, macd_dir, 52.0 + abs(metrics.macd_hist) * 500,
        ))

        if metrics.bb_width_ratio < 0.75:
            bb_reading = "Price compressed — tension building in the range"
            bb_psych = "Participants coiled; energy accumulating for release"
            bb_dir = "neutral"
        elif metrics.bb_position > 0.85:
            bb_reading = "Price riding upper band — stretch and greed"
            bb_psych = "Euphoria — participants pressing the upper boundary"
            bb_dir = "bullish"
        elif metrics.bb_position < 0.15:
            bb_reading = "Price riding lower band — fear and stretch"
            bb_psych = "Fear — participants pressing the lower boundary"
            bb_dir = "bearish"
        else:
            bb_reading = "Price mid-range — balanced volatility"
            bb_psych = "Equilibrium — no extreme positioning"
            bb_dir = "neutral"
        readings.append(PsychologicalReading(
            "Bollinger Bands", bb_reading, bb_psych, bb_dir, 50.0 + (1.0 - metrics.bb_width_ratio) * 20,
        ))

        if metrics.atr_ratio > 1.25:
            atr_reading = "Volatility expanding — energy releasing"
            atr_psych = "Participation intensifying — moves carry more conviction"
            atr_dir = structure.trend if structure.trend != "neutral" else "neutral"
        elif metrics.atr_ratio < 0.8:
            atr_reading = "Volatility compressing — energy storing"
            atr_psych = "Patience — market coiling before next impulse"
            atr_dir = "neutral"
        else:
            atr_reading = "Normal energy — typical participation level"
            atr_psych = "Market operating at average volatility"
            atr_dir = "neutral"
        readings.append(PsychologicalReading(
            "ATR", atr_reading, atr_psych, atr_dir, 48.0 + metrics.atr_ratio * 12,
        ))

        if metrics.obv_slope > 0.05:
            obv_reading = "Volume flow supports the upward move"
            obv_psych = "Accumulation — participants backing rise with volume"
            obv_dir = "bullish"
        elif metrics.obv_slope < -0.05:
            obv_reading = "Volume flow supports the downward move"
            obv_psych = "Distribution — participants backing decline with conviction"
            obv_dir = "bearish"
        else:
            obv_reading = "Volume flow mixed — no clear sponsorship"
            obv_psych = "Uncertainty — participation does not confirm direction"
            obv_dir = "neutral"
        readings.append(PsychologicalReading(
            "OBV", obv_reading, obv_psych, obv_dir, 50.0 + abs(metrics.obv_slope) * 80,
        ))

        if metrics.ad_line_slope > 0.05:
            ad_reading = "Large players appear to be accumulating"
            ad_psych = "Institutional accumulation — smart money absorbing"
            ad_dir = "bullish"
        elif metrics.ad_line_slope < -0.05:
            ad_reading = "Large players appear to be distributing"
            ad_psych = "Institutional distribution — smart money offloading"
            ad_dir = "bearish"
        else:
            ad_reading = "Institutional flow balanced"
            ad_psych = "No dominant accumulation or distribution signal"
            ad_dir = "neutral"
        readings.append(PsychologicalReading(
            "Accumulation/Distribution", ad_reading, ad_psych, ad_dir,
            50.0 + abs(metrics.ad_line_slope) * 80,
        ))

        if metrics.rsi >= 65 and metrics.volume_ratio > 1.2:
            sent_reading = "Market sentiment: optimistic crowd"
            sent_psych = "Greed — crowd leaning bullish with participation"
            sent_dir = "bullish"
        elif metrics.rsi <= 35 and metrics.volume_ratio > 1.2:
            sent_reading = "Market sentiment: fearful crowd"
            sent_psych = "Fear — crowd leaning bearish with participation"
            sent_dir = "bearish"
        elif metrics.rsi >= 60:
            sent_reading = "Market sentiment: mildly optimistic"
            sent_psych = "Optimism without full euphoria"
            sent_dir = "bullish"
        elif metrics.rsi <= 40:
            sent_reading = "Market sentiment: mildly fearful"
            sent_psych = "Caution — defensive positioning"
            sent_dir = "bearish"
        else:
            sent_reading = "Market sentiment: balanced"
            sent_psych = "Emotional equilibrium — no dominant mood"
            sent_dir = "neutral"
        readings.append(PsychologicalReading(
            "Sentiment", sent_reading, sent_psych, sent_dir, 50.0,
        ))

        if metrics.volume_ratio > 1.3:
            vol_reading = "Participation spike — conviction behind the move"
            vol_psych = "Strong belief — volume confirms interest"
            vol_dir = "bullish" if metrics.momentum_pips > 0 else "bearish" if metrics.momentum_pips < 0 else "neutral"
        elif metrics.volume_ratio < 0.75:
            vol_reading = "Quiet volume — accumulation or apathy"
            vol_psych = "Low participation — uncertainty or stealth accumulation"
            vol_dir = "neutral"
        else:
            vol_reading = "Average volume — normal belief level"
            vol_psych = "Typical participation for current conditions"
            vol_dir = "neutral"
        readings.append(PsychologicalReading(
            "Volume", vol_reading, vol_psych, vol_dir, 45.0 + metrics.volume_ratio * 15,
        ))

        if metrics.liquidity_rejection and structure.liquidity_zones:
            pa_reading = "Price action: wick rejection at liquidity"
            pa_psych = "Defenders active — sweep met with absorption"
            pa_dir = "neutral"
        elif metrics.wick_rejection:
            pa_reading = "Price action: rejection at support"
            pa_psych = "Buyers defending — demand visible at level"
            pa_dir = "bullish" if metrics.wick_rejection and metrics.momentum_pips >= 0 else "bearish"
        elif abs(metrics.momentum_pips) > 5:
            pa_reading = f"Price action: directional impulse ({metrics.momentum_pips:+.1f} pips)"
            pa_psych = "Conviction visible in recent price delivery"
            pa_dir = "bullish" if metrics.momentum_pips > 0 else "bearish"
        else:
            pa_reading = "Price action: range-bound delivery"
            pa_psych = "Neither side delivering decisive control"
            pa_dir = "neutral"
        readings.append(PsychologicalReading(
            "Price Action", pa_reading, pa_psych, pa_dir, 55.0 + min(20.0, abs(metrics.momentum_pips) * 2),
        ))

        if metrics.pin_bar:
            candle_reading = "Recent candle pattern: pin bar"
            candle_psych = "Sharp rejection — one side rejected aggressively"
            candle_dir = "bearish" if metrics.momentum_pips < 0 else "bullish"
        elif metrics.engulfing == "bullish":
            candle_reading = "Recent candle pattern: bullish engulfing"
            candle_psych = "Aggressive demand — buyers took control of the bar"
            candle_dir = "bullish"
        elif metrics.engulfing == "bearish":
            candle_reading = "Recent candle pattern: bearish engulfing"
            candle_psych = "Aggressive supply — sellers took control of the bar"
            candle_dir = "bearish"
        elif metrics.inside_bar:
            candle_reading = "Recent candle pattern: inside bar"
            candle_psych = "Compression — participants waiting for release"
            candle_dir = "neutral"
        elif metrics.outside_bar:
            candle_reading = "Recent candle pattern: outside bar"
            candle_psych = "Expansion — volatility returning to the market"
            candle_dir = "neutral"
        else:
            candle_reading = "Recent candle pattern: continuation bar"
            candle_psych = "Steady delivery — no dramatic shift in mood"
            candle_dir = narrative_direction if narrative_direction != "neutral" else "neutral"
        readings.append(PsychologicalReading(
            "Candlesticks", candle_reading, candle_psych, candle_dir, 52.0,
        ))

        if features is not None and bias.bias != "neutral":
            if features.layer_agreement > 0.7:
                readings[-1] = PsychologicalReading(
                    readings[-1].indicator,
                    readings[-1].reading,
                    readings[-1].psychology + " — multi-timeframe alignment supports narrative",
                    readings[-1].direction,
                    readings[-1].strength + 5,
                )

        return readings

    @staticmethod
    def _derive_opportunity_hints(
        metrics: _IndicatorMetrics,
        readings: list[PsychologicalReading],
        structure: MarketContext,
    ) -> list[str]:
        hints: list[str] = []
        rsi = next((r for r in readings if r.indicator == "RSI"), None)
        bb = next((r for r in readings if r.indicator == "Bollinger Bands"), None)

        if rsi and ("stretch" in rsi.reading.lower() or "euphoria" in rsi.reading.lower()):
            hints.append("mean_reversion_snapback")
        if bb and ("compressed" in bb.reading.lower() or "coiled" in bb.psychology.lower()):
            hints.append("compression_breakout")
        if metrics.trend_flattening:
            hints.append("trend_pause_resume")
        if metrics.liquidity_rejection and structure.liquidity_zones:
            hints.append("liquidity_sweep")
            hints.append("liquidity_sweep_snapback")
        if metrics.inside_bar or metrics.bb_width_ratio < 0.8:
            if "compression_breakout" not in hints:
                hints.append("compression_breakout")
        if metrics.outside_bar and metrics.range_ratio > 1.1:
            hints.append("failed_breakout")
        if structure.trend in {"bullish", "bearish"} and metrics.trend_flattening:
            hints.append("pullback_continuation")
        if metrics.rsi >= 70 and metrics.momentum_pips > 0:
            if "mean_reversion_snapback" not in hints:
                hints.append("mean_reversion_snapback")

        deduped: list[str] = []
        for hint in hints:
            if hint in VALID_OPPORTUNITY_HINTS and hint not in deduped:
                deduped.append(hint)
        if not deduped:
            deduped = ["compression_breakout", "trend_pause_resume"]
        return deduped

    @staticmethod
    def _build_observations(
        metrics: _IndicatorMetrics,
        readings: list[PsychologicalReading],
    ) -> list[str]:
        obs: list[str] = []
        if metrics.adx >= 20:
            obs.append("Directional control visible across participants")
        if metrics.atr_ratio > 1.2:
            obs.append("Volatility expanding — moves carry more energy")
        elif metrics.atr_ratio < 0.85:
            obs.append("Volatility compressing — coil building")
        if metrics.volume_ratio > 1.2:
            obs.append("Participation supports recent price delivery")
        for reading in readings[:4]:
            obs.append(f"{reading.indicator}: {reading.reading}")
        return obs[:6]

    @staticmethod
    def _build_forecast_implications(
        metrics: _IndicatorMetrics,
        hints: list[str],
    ) -> list[str]:
        forecast: list[str] = []
        if "compression_breakout" in hints or metrics.bb_width_ratio < 0.8:
            forecast.append(
                "Compression often precedes expansion — watch for breakout or failed breakout"
            )
        if "mean_reversion_snapback" in hints:
            forecast.append("Stretch readings suggest pause or snapback before continuation")
        if "liquidity_sweep" in hints:
            forecast.append("Liquidity grab may precede reversal or continuation after absorption")
        if metrics.adx >= 22 and metrics.momentum_pips > 3:
            forecast.append("Strong trend psychology — continuation likely after any pause")
        if not forecast:
            forecast.append("Mixed psychology — story develops as participation clarifies")
        return forecast

    @staticmethod
    def _build_contribution(
        readings: list[PsychologicalReading],
        hints: list[str],
    ) -> str:
        psych_bits = []
        for reading in readings[:3]:
            psych_bits.append(reading.psychology)
        hint_text = ", ".join(hints) if hints else "none"
        return (
            "Participant psychology: "
            + "; ".join(psych_bits)
            + f". Opportunity recognition expanded: {hint_text}"
        )

    @staticmethod
    def _compute_insight_score(
        readings: list[PsychologicalReading],
        hints: list[str],
        features: AssetTrendFeatures | None,
    ) -> float:
        base = 4.0 + len(readings) * 0.4 + len(hints) * 0.8
        alignment = sum(1 for r in readings if r.direction != "neutral")
        base += alignment * 0.3
        if features is not None:
            if features.adx >= 18:
                base += 1.5
            if 0.75 <= features.atr_ratio <= 1.45:
                base += 1.0
        return min(12.0, max(0.0, base))

    def write_indicator_interpretation_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "indicator_interpretation_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Indicator Interpretation Report",
            "",
            f"**Generated:** {now}",
            "",
            "Indicators as psychological evidence — never signals or vetoes.",
            "",
            f"- Interpreted: **{self.stats.interpreted}**",
            f"- Opportunity hints emitted: **{self.stats.opportunity_hints_emitted}**",
            f"- Evidence pieces added: **{self.stats.evidence_pieces_added}**",
            "",
        ]
        for symbol in sorted(self._latest):
            interp = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Insight score:** {interp.insight_score:.0f} (enrichment only)",
                "",
                f"**Contribution:** {interp.market_explanation_contribution}",
                "",
            ])
            for reading in interp.psychological_readings:
                lines.append(f"- **{reading.indicator}:** {reading.reading}")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_indicator_story_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "indicator_story_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Indicator Story Report",
            "",
            f"**Generated:** {now}",
            "",
            "How indicator psychology contributes to the market story.",
            "",
        ]
        for symbol in sorted(self._latest):
            interp = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Contribution:** {interp.market_explanation_contribution}",
                "",
                "**Forecast implications:**",
                "",
            ])
            for item in interp.forecast_implications:
                lines.append(f"- {item}")
            lines.extend(["", "**Opportunity hints:**", ""])
            for hint in interp.opportunity_hints:
                lines.append(f"- {hint}")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_market_psychology_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "market_psychology_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Psychology Report",
            "",
            f"**Generated:** {now}",
            "",
            "What participants behind the price are doing and feeling.",
            "",
        ]
        for symbol in sorted(self._latest):
            interp = self._latest[symbol]
            lines.extend([f"## {symbol}", ""])
            for reading in interp.psychological_readings:
                lines.append(f"- **{reading.indicator}** — {reading.psychology}")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_all_reports(self) -> tuple[Path | None, Path | None, Path | None]:
        return (
            self.write_indicator_interpretation_report(),
            self.write_indicator_story_report(),
            self.write_market_psychology_report(),
        )


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) < period:
        return np.full(len(values), values[-1] if len(values) else 0.0)
    return pd.Series(values).rolling(period).mean().bfill().values


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) == 0:
        return values
    return pd.Series(values).ewm(span=period, adjust=False).mean().values


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = pd.Series(gains).rolling(period).mean().iloc[-1]
    avg_loss = pd.Series(losses).rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _macd(closes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(closes) < 26:
        zeros = np.zeros(len(closes))
        return zeros, zeros
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    signal = _ema(macd_line, 9)
    return macd_line, signal


def _bollinger(closes: np.ndarray, period: int = 20, num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    middle = _sma(closes, period)
    std = pd.Series(closes).rolling(period).std().bfill().values
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    if len(closes) < 2:
        return np.array([0.0])
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(abs(highs - prev_close), abs(lows - prev_close)))
    return pd.Series(tr).rolling(period).mean().bfill().values


def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 2:
        return 15.0
    up = highs[1:] - highs[:-1]
    down = lows[:-1] - lows[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev_close = closes[:-1]
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(abs(highs[1:] - prev_close), abs(lows[1:] - prev_close)),
    )
    atr = pd.Series(tr).rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.rolling(period).mean().iloc[-1]
    return float(adx_val) if not np.isnan(adx_val) else 15.0


def _obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def _accumulation_distribution(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> np.ndarray:
    ad = np.zeros(len(closes))
    for i in range(len(closes)):
        hl = highs[i] - lows[i]
        if hl == 0:
            mfm = 0.0
        else:
            mfm = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / hl
        ad[i] = ad[i - 1] + mfm * volumes[i] if i > 0 else mfm * volumes[i]
    return ad
