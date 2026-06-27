"""Currency strength and macro-theme analysis for FX portfolio management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

TrackedCurrency = Literal["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]
MarketRegime = Literal["risk_on", "risk_off", "trend", "range", "unclear"]

TRACKED_CURRENCIES: tuple[TrackedCurrency, ...] = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "NZD",
    "CAD",
    "CHF",
)
STRENGTH_TIMEFRAMES: tuple[str, ...] = ("H8", "H4", "H1", "M15")
TIMEFRAME_WEIGHTS: dict[str, float] = {
    "H8": 0.35,
    "H4": 0.25,
    "H1": 0.25,
    "M15": 0.15,
}


@dataclass(frozen=True)
class TimeframeStrengthEvidence:
    """Directional evidence for a pair on one timeframe."""

    timeframe: str
    pair_score: float
    trend: float
    structure: float
    participation: float
    volatility_quality: float
    regime: MarketRegime
    reason: str

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "pair_score": round(self.pair_score, 3),
            "trend": round(self.trend, 3),
            "structure": round(self.structure, 3),
            "participation": round(self.participation, 3),
            "volatility_quality": round(self.volatility_quality, 3),
            "regime": self.regime,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PairStrengthAnalysis:
    """Relative strength result for a tradable FX pair."""

    symbol: str
    base_currency: str
    quote_currency: str
    base_strength: float
    quote_strength: float
    pair_strength: float
    preferred_side: Literal["buy", "sell", "neutral"]
    trade_theme: str
    theme_confidence: float
    market_regime: MarketRegime
    evidence: tuple[TimeframeStrengthEvidence, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "base_strength": round(self.base_strength, 2),
            "quote_strength": round(self.quote_strength, 2),
            "pair_strength": round(self.pair_strength, 2),
            "preferred_side": self.preferred_side,
            "trade_theme": self.trade_theme,
            "theme_confidence": round(self.theme_confidence, 2),
            "market_regime": self.market_regime,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class CurrencyStrengthSnapshot:
    """Full currency-strength state used by portfolio construction."""

    scores: dict[str, float]
    pair_analyses: dict[str, PairStrengthAnalysis]
    dominant_themes: tuple[str, ...]
    market_regime: MarketRegime

    def to_dict(self) -> dict:
        return {
            "scores": {k: round(v, 2) for k, v in self.scores.items()},
            "pair_analyses": {
                symbol: analysis.to_dict()
                for symbol, analysis in self.pair_analyses.items()
            },
            "dominant_themes": list(self.dominant_themes),
            "market_regime": self.market_regime,
        }


class CurrencyStrengthEngine:
    """
    Aggregate pair-level OHLCV evidence into independent currency scores.

    Each pair contributes positive strength to its base currency and negative
    strength to its quote currency when the pair is bullish, and vice versa.
    """

    def __init__(self) -> None:
        self._pair_candles: dict[str, dict[str, pd.DataFrame]] = {}
        self._latest_snapshot = CurrencyStrengthSnapshot(
            scores={currency: 0.0 for currency in TRACKED_CURRENCIES},
            pair_analyses={},
            dominant_themes=(),
            market_regime="unclear",
        )

    def update_symbol(
        self,
        symbol: str,
        candles_by_timeframe: dict[str, pd.DataFrame],
    ) -> CurrencyStrengthSnapshot:
        normalized = _normalize_symbol(symbol)
        if _pair_currencies(normalized) is not None:
            self._pair_candles[normalized] = dict(candles_by_timeframe)
        self._latest_snapshot = self.evaluate(self._pair_candles)
        return self._latest_snapshot

    def evaluate(
        self,
        candles_by_symbol: dict[str, dict[str, pd.DataFrame]],
    ) -> CurrencyStrengthSnapshot:
        contributions: dict[str, list[float]] = {
            currency: [] for currency in TRACKED_CURRENCIES
        }
        pair_evidence: dict[str, tuple[TimeframeStrengthEvidence, ...]] = {}
        pair_raw_scores: dict[str, float] = {}
        regime_votes: list[MarketRegime] = []

        for symbol, candles_by_timeframe in candles_by_symbol.items():
            normalized = _normalize_symbol(symbol)
            currencies = _pair_currencies(normalized)
            if currencies is None:
                continue
            base, quote = currencies
            evidence = self._score_pair_timeframes(candles_by_timeframe)
            if not evidence:
                continue

            pair_score = sum(
                item.pair_score * TIMEFRAME_WEIGHTS.get(item.timeframe, 0.0)
                for item in evidence
            )
            pair_score = _clamp(pair_score * 10.0, -10.0, 10.0)
            pair_raw_scores[normalized] = pair_score
            pair_evidence[normalized] = tuple(evidence)
            contributions[base].append(pair_score)
            contributions[quote].append(-pair_score)
            regime_votes.extend(item.regime for item in evidence)

        scores = {
            currency: round(_clamp(_mean(values), -10.0, 10.0), 2)
            for currency, values in contributions.items()
        }
        portfolio_regime = _dominant_regime(regime_votes)
        pair_analyses: dict[str, PairStrengthAnalysis] = {}
        for symbol, evidence in pair_evidence.items():
            base, quote = _pair_currencies(symbol) or ("", "")
            pair_strength = scores.get(base, 0.0) - scores.get(quote, 0.0)
            preferred_side: Literal["buy", "sell", "neutral"]
            if pair_strength >= 2.0:
                preferred_side = "buy"
            elif pair_strength <= -2.0:
                preferred_side = "sell"
            else:
                preferred_side = "neutral"
            theme, theme_confidence = _theme_for_pair(
                base=base,
                quote=quote,
                pair_strength=pair_strength,
                market_regime=portfolio_regime,
            )
            pair_analyses[symbol] = PairStrengthAnalysis(
                symbol=symbol,
                base_currency=base,
                quote_currency=quote,
                base_strength=scores.get(base, 0.0),
                quote_strength=scores.get(quote, 0.0),
                pair_strength=round(pair_strength, 2),
                preferred_side=preferred_side,
                trade_theme=theme,
                theme_confidence=theme_confidence,
                market_regime=portfolio_regime,
                evidence=evidence,
            )

        return CurrencyStrengthSnapshot(
            scores=scores,
            pair_analyses=pair_analyses,
            dominant_themes=_dominant_themes(pair_analyses.values()),
            market_regime=portfolio_regime,
        )

    def latest_scores(self) -> dict[str, float]:
        return dict(self._latest_snapshot.scores)

    def latest_snapshot(self) -> CurrencyStrengthSnapshot:
        return self._latest_snapshot

    def pair_analysis(self, symbol: str) -> PairStrengthAnalysis | None:
        return self._latest_snapshot.pair_analyses.get(_normalize_symbol(symbol))

    def _score_pair_timeframes(
        self,
        candles_by_timeframe: dict[str, pd.DataFrame],
    ) -> tuple[TimeframeStrengthEvidence, ...]:
        evidence: list[TimeframeStrengthEvidence] = []
        for timeframe in STRENGTH_TIMEFRAMES:
            frame = candles_by_timeframe.get(timeframe)
            item = _score_timeframe(timeframe, frame)
            if item is not None:
                evidence.append(item)
        return tuple(evidence)


@dataclass
class ThemePerformance:
    """Memory bucket for one macro theme."""

    trades: int = 0
    wins: int = 0
    gross_profit_r: float = 0.0
    gross_loss_r: float = 0.0
    expectancy_r: float = 0.0

    @property
    def win_rate(self) -> float:
        if self.trades <= 0:
            return 0.0
        return self.wins / self.trades

    @property
    def profit_factor(self) -> float:
        if self.gross_loss_r <= 0:
            return float("inf") if self.gross_profit_r > 0 else 0.0
        return self.gross_profit_r / self.gross_loss_r

    def to_dict(self) -> dict:
        pf = self.profit_factor
        return {
            "trades": self.trades,
            "wr": round(self.win_rate, 3),
            "pf": round(pf, 3) if pf != float("inf") else "inf",
            "expectancy": round(self.expectancy_r, 3),
        }


@dataclass
class CurrencyPerformance:
    """Memory bucket for long and short performance of one currency."""

    long_trades: int = 0
    long_wins: int = 0
    short_trades: int = 0
    short_wins: int = 0

    def to_dict(self) -> dict:
        return {
            "longs_wr": round(self.long_wins / self.long_trades, 3)
            if self.long_trades
            else 0.0,
            "shorts_wr": round(self.short_wins / self.short_trades, 3)
            if self.short_trades
            else 0.0,
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
        }


@dataclass
class CurrencyThemeMemory:
    """In-memory learning for theme and currency-level recalibration."""

    theme_performance: dict[str, ThemePerformance] = field(default_factory=dict)
    currency_performance: dict[str, CurrencyPerformance] = field(default_factory=dict)

    def record_trade(
        self,
        *,
        symbol: str,
        side: str,
        trade_theme: str,
        r_multiple: float,
    ) -> None:
        theme = self.theme_performance.setdefault(trade_theme, ThemePerformance())
        theme.trades += 1
        if r_multiple > 0:
            theme.wins += 1
            theme.gross_profit_r += r_multiple
        else:
            theme.gross_loss_r += abs(r_multiple)
        total_r = theme.gross_profit_r - theme.gross_loss_r
        theme.expectancy_r = total_r / max(theme.trades, 1)

        currencies = _pair_currencies(_normalize_symbol(symbol))
        if currencies is None:
            return
        base, quote = currencies
        base_perf = self.currency_performance.setdefault(base, CurrencyPerformance())
        quote_perf = self.currency_performance.setdefault(quote, CurrencyPerformance())
        won = r_multiple > 0
        if side == "buy":
            base_perf.long_trades += 1
            quote_perf.short_trades += 1
            base_perf.long_wins += int(won)
            quote_perf.short_wins += int(won)
        else:
            base_perf.short_trades += 1
            quote_perf.long_trades += 1
            base_perf.short_wins += int(won)
            quote_perf.long_wins += int(won)

    def confidence_adjustment(self, trade_theme: str) -> float:
        perf = self.theme_performance.get(trade_theme)
        if perf is None or perf.trades < 5:
            return 0.0
        if perf.expectancy_r > 0.15 and perf.profit_factor >= 1.4:
            return 0.1
        if perf.expectancy_r < 0.0 or perf.profit_factor < 1.0:
            return -0.15
        return 0.0


def _score_timeframe(
    timeframe: str,
    frame: pd.DataFrame | None,
) -> TimeframeStrengthEvidence | None:
    if frame is None or frame.empty or len(frame) < 24:
        return None
    required = {"open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        return None

    data = frame.copy().dropna(subset=list(required))
    if "time" in data.columns:
        data["time"] = pd.to_datetime(data["time"], utc=True, errors="coerce")
        data = data.sort_values("time")
    if len(data) < 24:
        return None

    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    open_ = data["open"].astype(float)
    volume = (
        data["tick_volume"].astype(float)
        if "tick_volume" in data.columns
        else pd.Series([1.0] * len(data), index=data.index)
    )

    returns = close.pct_change().dropna()
    lookback = min(20, len(close) - 1)
    fast = close.rolling(min(12, lookback)).mean()
    slow = close.rolling(max(20, lookback)).mean()
    price_vs_ma = (close.iloc[-1] - slow.iloc[-1]) / max(abs(slow.iloc[-1]), 1e-9)
    slope = (fast.iloc[-1] - fast.iloc[-1 - min(5, lookback - 1)]) / max(
        abs(fast.iloc[-1 - min(5, lookback - 1)]),
        1e-9,
    )
    persistence = _signed_persistence(returns.tail(lookback))
    trend = _clamp(price_vs_ma * 80.0 + slope * 120.0 + persistence * 0.35)

    recent_high = float(high.iloc[-lookback:].max())
    prior_high = float(high.iloc[-lookback * 2 : -lookback].max())
    recent_low = float(low.iloc[-lookback:].min())
    prior_low = float(low.iloc[-lookback * 2 : -lookback].min())
    structure = 0.0
    if recent_high > prior_high and recent_low > prior_low:
        structure = 1.0
    elif recent_high < prior_high and recent_low < prior_low:
        structure = -1.0

    vol_mean = float(volume.tail(lookback).mean())
    vol_prior = float(volume.iloc[-lookback * 2 : -lookback].mean()) if len(volume) >= lookback * 2 else vol_mean
    participation = _clamp(persistence * 0.55 + ((vol_mean / max(vol_prior, 1.0)) - 1.0) * 0.6)

    candle_range = (high - low).astype(float)
    candle_range = candle_range.mask(candle_range == 0)
    body = (close - open_).abs()
    directional_efficiency = abs(float(close.iloc[-1] - close.iloc[-lookback])) / max(
        float(candle_range.tail(lookback).sum()),
        1e-9,
    )
    range_cv = float(candle_range.tail(lookback).std() / max(candle_range.tail(lookback).mean(), 1e-9))
    volatility_quality = _clamp(directional_efficiency * 2.0 - range_cv * 0.7)
    if body.tail(lookback).mean() > candle_range.tail(lookback).mean() * 0.55:
        volatility_quality = _clamp(volatility_quality + 0.2)

    regime = _classify_timeframe_regime(
        trend=trend,
        volatility_quality=volatility_quality,
        structure=structure,
        persistence=persistence,
    )
    pair_score = _clamp(
        trend * 0.35
        + structure * 0.25
        + participation * 0.20
        + volatility_quality * 0.20
    )
    reason = (
        f"{timeframe}: trend={trend:.2f}, structure={structure:.2f}, "
        f"participation={participation:.2f}, vol_quality={volatility_quality:.2f}"
    )
    return TimeframeStrengthEvidence(
        timeframe=timeframe,
        pair_score=pair_score,
        trend=trend,
        structure=structure,
        participation=participation,
        volatility_quality=volatility_quality,
        regime=regime,
        reason=reason,
    )


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalpha())[:6]


def _pair_currencies(symbol: str) -> tuple[str, str] | None:
    if len(symbol) < 6:
        return None
    base = symbol[:3]
    quote = symbol[3:6]
    if base in TRACKED_CURRENCIES and quote in TRACKED_CURRENCIES:
        return base, quote
    return None


def _signed_persistence(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    up = int((returns > 0).sum())
    down = int((returns < 0).sum())
    return (up - down) / max(up + down, 1)


def _classify_timeframe_regime(
    *,
    trend: float,
    volatility_quality: float,
    structure: float,
    persistence: float,
) -> MarketRegime:
    if abs(trend) >= 0.45 and volatility_quality > 0.05:
        return "trend"
    if abs(structure) < 0.2 and abs(persistence) < 0.15:
        return "range"
    if trend < -0.35 and volatility_quality > 0.0:
        return "risk_off"
    if trend > 0.35 and volatility_quality > 0.0:
        return "risk_on"
    return "unclear"


def _dominant_regime(votes: list[MarketRegime]) -> MarketRegime:
    if not votes:
        return "unclear"
    counts = {regime: votes.count(regime) for regime in set(votes)}
    return max(counts, key=counts.get)


def _theme_for_pair(
    *,
    base: str,
    quote: str,
    pair_strength: float,
    market_regime: MarketRegime,
) -> tuple[str, float]:
    magnitude = min(1.0, abs(pair_strength) / 10.0)
    stronger = base if pair_strength >= 0 else quote
    weaker = quote if pair_strength >= 0 else base
    confidence = round(0.45 + magnitude * 0.5, 2)

    if weaker == "USD":
        return "USD weakness", confidence
    if stronger == "USD":
        return "USD strength", confidence
    if stronger == "JPY" and market_regime in {"risk_off", "trend"}:
        return "JPY risk-off", confidence
    if stronger == "CHF":
        return "CHF defensive demand", confidence
    if stronger in {"AUD", "CAD", "NZD"}:
        return "Commodity rotation", confidence
    if stronger in {"EUR", "GBP"}:
        return "European strength", confidence
    return f"{stronger} over {weaker}", confidence


def _dominant_themes(analyses: object) -> tuple[str, ...]:
    counts: dict[str, float] = {}
    for analysis in analyses:
        counts[analysis.trade_theme] = counts.get(analysis.trade_theme, 0.0) + analysis.theme_confidence
    return tuple(
        theme for theme, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


__all__ = [
    "CurrencyStrengthEngine",
    "CurrencyStrengthSnapshot",
    "CurrencyThemeMemory",
    "PairStrengthAnalysis",
    "TRACKED_CURRENCIES",
    "TimeframeStrengthEvidence",
]
