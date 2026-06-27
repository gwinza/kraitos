"""
Micro scalper strategy for Kraitos.

Targets 1-3 pip opportunities using M1 entries with M5 confirmation and
spread, momentum, liquidity, and volatility filters.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from loguru import logger

from strategies.models import MicroScalpAction, MicroScalpSignal

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread")

TARGET_PIPS_RANGE = (1.0, 3.0)


@dataclass(frozen=True)
class MicroScalperConfig:
    """Thresholds for micro scalping filters."""

    min_m1_candles: int = 60
    min_m5_candles: int = 40
    momentum_lookback: int = 5
    m5_momentum_lookback: int = 4
    atr_period: int = 14
    atr_long_period: int = 40
    momentum_threshold: float = 0.00008
    chaotic_atr_ratio: float = 1.45
    chaotic_candle_expansion: float = 1.6
    low_volume_ratio: float = 0.55
    spread_buffer_ratio: float = 0.9
    pip_size: float = 0.0001


class MicroScalperError(Exception):
    """Raised when micro scalper input is invalid."""


class MicroScalper:
    """Scan M1/M5 candles for short pip scalp opportunities."""

    def __init__(self, config: MicroScalperConfig | None = None) -> None:
        self.config = config or MicroScalperConfig()

    def scan(
        self,
        m1_candles: pd.DataFrame,
        m5_candles: pd.DataFrame,
        *,
        symbol: str = "EURUSD",
        spread_limit: float = 2.0,
        current_spread: float | None = None,
    ) -> MicroScalpSignal:
        """
        Evaluate micro scalp opportunity on M1 with M5 confirmation.

        Returns:
            MicroScalpSignal with action buy, sell, or no_trade and reason.
        """
        m1 = self._prepare_candles(m1_candles, self.config.min_m1_candles, "M1")
        m5 = self._prepare_candles(m5_candles, self.config.min_m5_candles, "M5")

        spread = (
            current_spread
            if current_spread is not None
            else float(m1["spread"].iloc[-1])
        )
        features_m1 = self._compute_features(m1)
        features_m5 = self._compute_features(m5)

        rejection = self._check_rejections(
            spread=spread,
            spread_limit=spread_limit,
            features_m1=features_m1,
            features_m5=features_m5,
        )
        if rejection is not None:
            logger.debug(f"Micro scalper {symbol}: no_trade - {rejection}")
            return MicroScalpSignal(action="no_trade", reason=rejection)

        direction = self._resolve_direction(features_m1, features_m5)
        if direction == "unclear":
            reason = (
                "Direction is unclear; M1/M5 momentum or moving-average alignment failed"
            )
            logger.debug(f"Micro scalper {symbol}: no_trade - {reason}")
            return MicroScalpSignal(action="no_trade", reason=reason)

        action: MicroScalpAction = "buy" if direction == "bullish" else "sell"
        target_pips = self._calculate_target_pips(features_m1, features_m5, spread, spread_limit)
        reason = (
            f"{action.upper()} scalp approved: M1 momentum {features_m1['momentum']:.6f} "
            f"confirmed by M5 {features_m5['momentum']:.6f}, "
            f"spread {spread:.2f}, target {target_pips:.1f} pips"
        )
        logger.info(f"Micro scalper {symbol}: {reason}")
        return MicroScalpSignal(action=action, reason=reason, target_pips=target_pips)

    def _prepare_candles(
        self,
        candles: pd.DataFrame,
        min_candles: int,
        timeframe: str,
    ) -> pd.DataFrame:
        if candles is None or candles.empty:
            raise MicroScalperError(f"{timeframe} candle data is empty")

        missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
        if missing:
            raise MicroScalperError(f"{timeframe} missing columns: {', '.join(missing)}")

        frame = candles.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame.sort_values("time").reset_index(drop=True)

        if len(frame) < min_candles:
            raise MicroScalperError(
                f"{timeframe} requires at least {min_candles} candles, got {len(frame)}"
            )
        return frame

    def _compute_features(self, frame: pd.DataFrame) -> dict[str, float]:
        cfg = self.config
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        open_ = frame["open"].astype(float)

        lookback = min(cfg.momentum_lookback, len(close) - 1)
        momentum = (close.iloc[-1] - close.iloc[-1 - lookback]) / close.iloc[-1 - lookback]

        prev_close = close.shift(1)
        true_range = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(cfg.atr_period).mean()
        atr_long = true_range.rolling(cfg.atr_long_period).mean()

        current_atr = float(atr.iloc[-1])
        baseline_atr = float(atr_long.iloc[-1])
        atr_ratio = current_atr / baseline_atr if baseline_atr > 0 else 1.0

        candle_range = high - low
        avg_range = candle_range.rolling(cfg.atr_period).mean()
        current_range = float(candle_range.iloc[-1])
        mean_range = float(avg_range.iloc[-1])
        candle_expansion = current_range / mean_range if mean_range > 0 else 1.0

        current_volume = float(frame["tick_volume"].iloc[-1])
        mean_volume = float(frame["tick_volume"].rolling(cfg.atr_period).mean().iloc[-1])
        volume_ratio = current_volume / mean_volume if mean_volume > 0 else 1.0

        current_spread = float(frame["spread"].iloc[-1])
        mean_spread = float(frame["spread"].rolling(cfg.atr_period).mean().iloc[-1])
        spread_to_average = current_spread / mean_spread if mean_spread > 0 else 1.0

        ma = close.rolling(cfg.atr_period).mean()
        price_vs_ma = (close.iloc[-1] - ma.iloc[-1]) / ma.iloc[-1] if ma.iloc[-1] else 0.0

        body = (close - open_).abs()
        bullish_bars = int((close > open_).iloc[-lookback:].sum())
        bearish_bars = int((close < open_).iloc[-lookback:].sum())

        return {
            "momentum": float(momentum),
            "atr_ratio": float(atr_ratio),
            "candle_expansion": float(candle_expansion),
            "volume_ratio": float(volume_ratio),
            "spread_to_average": float(spread_to_average),
            "current_spread": current_spread,
            "price_vs_ma": float(price_vs_ma),
            "bullish_bars": float(bullish_bars),
            "bearish_bars": float(bearish_bars),
            "body_momentum": float(body.iloc[-1] / (avg_range.iloc[-1] or 1.0)),
        }

    def _check_rejections(
        self,
        *,
        spread: float,
        spread_limit: float,
        features_m1: dict[str, float],
        features_m5: dict[str, float],
    ) -> str | None:
        effective_limit = spread_limit * self.config.spread_buffer_ratio
        if spread > effective_limit:
            return (
                f"Spread is too high ({spread:.2f} > {effective_limit:.2f} limit)"
            )

        if self._volatility_chaotic(features_m1):
            return (
                f"Volatility is chaotic on M1 (ATR ratio {features_m1['atr_ratio']:.2f}, "
                f"candle expansion {features_m1['candle_expansion']:.2f})"
            )

        if self._liquidity_poor(features_m1, spread, spread_limit):
            return (
                f"Liquidity is poor (volume ratio {features_m1['volume_ratio']:.2f}, "
                f"spread {spread:.2f})"
            )

        if self._direction_unclear(features_m1, features_m5):
            return (
                f"Direction is unclear (M1 momentum {features_m1['momentum']:.6f}, "
                f"M5 momentum {features_m5['momentum']:.6f})"
            )

        return None

    def _volatility_chaotic(self, features: dict[str, float]) -> bool:
        return (
            features["atr_ratio"] >= self.config.chaotic_atr_ratio
            or features["candle_expansion"] >= self.config.chaotic_candle_expansion
        )

    def _liquidity_poor(
        self,
        features: dict[str, float],
        spread: float,
        spread_limit: float,
    ) -> bool:
        return (
            features["volume_ratio"] <= self.config.low_volume_ratio
            or spread > spread_limit * 0.75
            or features["spread_to_average"] >= 1.35
        )

    def _direction_unclear(
        self,
        features_m1: dict[str, float],
        features_m5: dict[str, float],
    ) -> bool:
        m1_dir = self._momentum_direction(features_m1["momentum"])
        m5_dir = self._momentum_direction(features_m5["momentum"])

        if m1_dir == "neutral" or m5_dir == "neutral":
            return True
        return m1_dir != m5_dir

    def _resolve_direction(
        self,
        features_m1: dict[str, float],
        features_m5: dict[str, float],
    ) -> str:
        m1_dir = self._momentum_direction(features_m1["momentum"])
        m5_dir = self._momentum_direction(features_m5["momentum"])

        if m1_dir == "bullish" and m5_dir == "bullish":
            if features_m1["price_vs_ma"] >= 0 or features_m5["price_vs_ma"] >= 0:
                return "bullish"
        if m1_dir == "bearish" and m5_dir == "bearish":
            if features_m1["price_vs_ma"] <= 0 or features_m5["price_vs_ma"] <= 0:
                return "bearish"
        return "unclear"

    def _momentum_direction(self, momentum: float) -> str:
        threshold = self.config.momentum_threshold
        if momentum >= threshold:
            return "bullish"
        if momentum <= -threshold:
            return "bearish"
        return "neutral"

    def _calculate_target_pips(
        self,
        features_m1: dict[str, float],
        features_m5: dict[str, float],
        spread: float,
        spread_limit: float,
    ) -> float:
        low, high = TARGET_PIPS_RANGE
        spread_quality = 1.0 - min(1.0, spread / max(spread_limit, 0.01))
        momentum_strength = min(
            1.0,
            (abs(features_m1["momentum"]) + abs(features_m5["momentum"]))
            / (self.config.momentum_threshold * 4),
        )
        liquidity_strength = min(1.0, features_m1["volume_ratio"])
        volatility_penalty = min(1.0, features_m1["atr_ratio"] / self.config.chaotic_atr_ratio)

        score = (
            0.35 * momentum_strength
            + 0.25 * spread_quality
            + 0.25 * liquidity_strength
            + 0.15 * (1.0 - volatility_penalty * 0.5)
        )
        score = max(0.0, min(1.0, score))
        return round(low + (high - low) * score, 1)
