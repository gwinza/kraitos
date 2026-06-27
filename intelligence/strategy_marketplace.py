"""Strategy marketplace — competing strategies per asset and trend state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from intelligence.rolling_fitness import RollingFitnessMemory, SymbolFitnessProfile, WindowFitness
from intelligence.trend_strength_engine import TrendQuality, TrendStrengthResult

MarketplaceStrategy = Literal[
    "harvest",
    "normal_trend",
    "breakout_continuation",
    "mean_reversion",
    "range_scalper",
    "micro_scalp",
    "no_trade",
]

ALL_STRATEGIES: tuple[MarketplaceStrategy, ...] = (
    "harvest",
    "normal_trend",
    "breakout_continuation",
    "mean_reversion",
    "range_scalper",
    "micro_scalp",
    "no_trade",
)

TREND_PREFERENCES: dict[TrendQuality, list[MarketplaceStrategy]] = {
    "institutional_trend": ["harvest", "normal_trend", "breakout_continuation"],
    "developing_trend": ["normal_trend", "harvest", "breakout_continuation"],
    "weak_trend": ["range_scalper", "mean_reversion", "micro_scalp"],
    "range_or_noise": ["range_scalper", "mean_reversion", "micro_scalp"],
}

REGIME_BOOSTS: dict[str, dict[str, float]] = {
    "trending": {"harvest": 1.1, "normal_trend": 1.05, "breakout_continuation": 1.0},
    "ranging": {"range_scalper": 1.15, "mean_reversion": 1.1},
    "volatile": {"breakout_continuation": 1.1, "micro_scalp": 1.05},
    "compression": {"breakout_continuation": 1.12, "harvest": 0.95},
    "low_liquidity": {"no_trade": 1.2},
}

SESSION_BOOSTS: dict[str, dict[str, float]] = {
    "london": {"harvest": 1.08, "normal_trend": 1.05},
    "london_ny_overlap": {"harvest": 1.1, "breakout_continuation": 1.05},
    "new_york": {"harvest": 1.05, "mean_reversion": 1.05},
    "asia": {"range_scalper": 1.1, "mean_reversion": 1.08},
}


@dataclass(frozen=True)
class MarketplaceSelection:
    """Winning strategy from marketplace competition."""

    symbol: str
    strategy: MarketplaceStrategy
    fitness_score: float
    expected_value: float
    trend_score: float
    trend_quality: TrendQuality
    regime: str
    session: str
    competitors: dict[str, float]
    reason: str
    recommended_action: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "fitness_score": round(self.fitness_score, 4),
            "expected_value": round(self.expected_value, 4),
            "trend_score": round(self.trend_score, 2),
            "trend_quality": self.trend_quality,
            "regime": self.regime,
            "session": self.session,
            "competitors": {k: round(v, 4) for k, v in self.competitors.items()},
            "reason": self.reason,
            "recommended_action": self.recommended_action,
        }


class StrategyMarketplace:
    """Select best strategy using trend strength and rolling fitness."""

    def __init__(self, fitness_memory: RollingFitnessMemory) -> None:
        self._fitness = fitness_memory

    def compete(
        self,
        *,
        trend: TrendStrengthResult,
        regime: str = "trending",
        session: str = "any",
        spread_to_target: float = 0.2,
        structure_clean: bool = True,
    ) -> MarketplaceSelection:
        profile = self._fitness.get(trend.symbol)
        action = profile.recommended_action if profile else "APPROVED"

        if action == "DISABLED":
            return self._selection(
                trend, "no_trade", 0.0, 0.0, regime, session, {}, action,
                "Asset disabled — all strategy modes failed across regimes",
            )

        if action == "QUARANTINED":
            return self._selection(
                trend, "no_trade", 0.0, 0.0, regime, session, {}, action,
                "Asset quarantined — no strategy shows positive rolling fitness",
            )

        candidates = list(TREND_PREFERENCES.get(trend.quality, ["no_trade"]))
        if (
            trend.quality == "range_or_noise"
            and spread_to_target <= 0.25
            and structure_clean
        ):
            candidates = ["range_scalper", "mean_reversion", "micro_scalp", "no_trade"]

        scores: dict[str, float] = {}
        expected_values: dict[str, float] = {}
        for strategy in ALL_STRATEGIES:
            if strategy not in candidates and strategy != "no_trade":
                scores[strategy] = -1.0
                expected_values[strategy] = -1.0
                continue
            base = self._fitness.fitness_for(trend.symbol, strategy)
            trend_boost = self._trend_boost(strategy, trend.quality)
            regime_boost = REGIME_BOOSTS.get(regime, {}).get(strategy, 1.0)
            session_boost = SESSION_BOOSTS.get(session, {}).get(strategy, 1.0)
            spread_penalty = self._spread_sensitivity(strategy, spread_to_target)

            fitness = base * 0.55 + trend_boost * 0.45
            fitness *= regime_boost * session_boost
            fitness *= spread_penalty

            ev = self._expected_value(profile, strategy, fitness)
            scores[strategy] = fitness
            expected_values[strategy] = ev

        if profile and profile.worst_strategy in scores:
            scores[profile.worst_strategy] *= 0.5
            expected_values[profile.worst_strategy] *= 0.5

        ranked = sorted(
            ((s, expected_values[s]) for s in candidates if s in expected_values),
            key=lambda x: x[1],
            reverse=True,
        )
        if not ranked or ranked[0][1] <= 0:
            if spread_to_target <= 0.45 and structure_clean:
                fallback = "micro_scalp" if spread_to_target <= 0.32 else "range_scalper"
                return self._selection(
                    trend,
                    fallback,  # type: ignore[arg-type]
                    scores.get(fallback, 0.3),
                    0.25,
                    regime,
                    session,
                    scores,
                    action,
                    f"Low EV — micro scalp fallback for {trend.quality}",
                )
            return self._selection(
                trend, "no_trade", 0.0, 0.0, regime, session, scores, action,
                "No competitive strategy for current trend quality",
            )

        winner, win_ev = ranked[0]
        win_fitness = scores.get(winner, 0.0)
        if action in {"REDUCED_RISK", "CONDITIONAL"} and winner != "no_trade":
            win_ev *= 0.85
            win_fitness *= 0.85

        return self._selection(
            trend,
            winner,  # type: ignore[arg-type]
            win_fitness,
            win_ev,
            regime,
            session,
            scores,
            action,
            f"Marketplace EV winner {winner} for {trend.quality}/{regime}/{session} "
            f"(EV {win_ev:.2f}, trend {trend.score:.0f})",
        )

    def _expected_value(
        self,
        profile: SymbolFitnessProfile | None,
        strategy: str,
        fitness: float,
    ) -> float:
        if profile is None:
            return fitness
        record = profile.strategy_records.get(strategy)
        if record is None:
            return fitness
        w50 = record.windows.get("50")
        w100 = record.windows.get("100")
        w250 = record.windows.get("250")
        expectancy = self._weighted_expectancy(w50, w100, w250)
        pf_bonus = 0.0
        if w50 is not None and w50.profit_factor >= 1.5:
            pf_bonus = 0.1
        wr_bonus = 0.0
        if w50 is not None and w50.win_rate >= 0.6:
            wr_bonus = 0.08
        dd_penalty = 0.0
        if w50 is not None and w50.max_drawdown_pct > 12:
            dd_penalty = 0.15
        det_penalty = 0.12 if record.deterioration else 0.0
        return max(
            0.0,
            fitness * 0.5 + expectancy * 0.5 + pf_bonus + wr_bonus - dd_penalty - det_penalty,
        )

    @staticmethod
    def _weighted_expectancy(
        w50: WindowFitness | None,
        w100: WindowFitness | None,
        w250: WindowFitness | None,
    ) -> float:
        parts: list[tuple[float, float]] = []
        if w50 is not None and w50.trades >= 3:
            parts.append((w50.average_r, 0.5))
        if w100 is not None and w100.trades >= 5:
            parts.append((w100.average_r, 0.3))
        if w250 is not None and w250.trades >= 10:
            parts.append((w250.average_r, 0.2))
        if not parts:
            return 0.3
        total_w = sum(w for _, w in parts)
        return sum(r * w for r, w in parts) / total_w

    @staticmethod
    def _spread_sensitivity(strategy: str, spread_to_target: float) -> float:
        if strategy in {"micro_scalp", "range_scalper", "mean_reversion"}:
            if spread_to_target > 0.3:
                return max(0.2, 1.0 - spread_to_target)
            if spread_to_target > 0.2:
                return 0.85
        if spread_to_target > 0.4:
            return 0.6
        return 1.0

    @staticmethod
    def _trend_boost(strategy: str, quality: TrendQuality) -> float:
        prefs = TREND_PREFERENCES.get(quality, [])
        if strategy in prefs:
            idx = prefs.index(strategy)
            return max(0.3, 1.0 - idx * 0.15)
        if strategy == "no_trade":
            return 0.05 if quality == "range_or_noise" else 0.02
        return 0.15

    @staticmethod
    def _selection(
        trend: TrendStrengthResult,
        strategy: MarketplaceStrategy,
        fitness: float,
        expected_value: float,
        regime: str,
        session: str,
        competitors: dict[str, float],
        action: str,
        reason: str,
    ) -> MarketplaceSelection:
        return MarketplaceSelection(
            symbol=trend.symbol,
            strategy=strategy,
            fitness_score=fitness,
            expected_value=expected_value,
            trend_score=trend.score,
            trend_quality=trend.quality,
            regime=regime,
            session=session,
            competitors=competitors,
            reason=reason,
            recommended_action=action,
        )
