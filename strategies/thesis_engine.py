"""
Thesis engine — every trade is a market story with explicit geometry.

Observe the tape, articulate the thesis, define invalidation, then participate.
Momentum and indicators explain behaviour; they do not veto coherent theses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from strategies.models import MarketContext, MultiTimeframeBiasResult

ThesisDirection = Literal["buy", "sell"]
INVALIDATION_BUFFER_PIPS = 3.0
MIN_REWARD_RISK = 0.80


@dataclass(frozen=True)
class TradeThesis:
    """Decision-layer trade thesis — the contract before capital allocation."""

    market_story: str
    direction: ThesisDirection
    entry_reason: str
    invalidation_reason: str
    expected_path: str
    risk: float
    reward: float
    confidence: float
    symbol: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    invalidation_level: float = 0.0
    take_profit: float = 0.0
    reward_risk_ratio: float = 0.0
    is_tradeable: bool = True
    rejection_reason: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "market_story": self.market_story,
            "direction": self.direction,
            "entry_reason": self.entry_reason,
            "invalidation_reason": self.invalidation_reason,
            "expected_path": self.expected_path,
            "risk": round(self.risk, 5),
            "reward": round(self.reward, 5),
            "confidence": round(self.confidence, 3),
            "symbol": self.symbol,
            "entry_price": round(self.entry_price, 5),
            "stop_loss": round(self.stop_loss, 5),
            "invalidation_level": round(self.invalidation_level, 5),
            "take_profit": round(self.take_profit, 5),
            "reward_risk_ratio": round(self.reward_risk_ratio, 3),
            "is_tradeable": self.is_tradeable,
            "rejection_reason": self.rejection_reason,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ThesisEngineConfig:
    """Parameters for thesis construction."""

    default_tp_r: float = 1.25
    min_reward_risk: float = MIN_REWARD_RISK
    invalidation_buffer_pips: float = INVALIDATION_BUFFER_PIPS
    min_confidence: float = 0.35


class ThesisEngineError(Exception):
    """Raised when thesis inputs are invalid."""


class ThesisEngine:
    """Build a complete trade thesis from market context."""

    def __init__(self, config: ThesisEngineConfig | None = None) -> None:
        self.config = config or ThesisEngineConfig()

    def build(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
        market_story: str = "",
        entry_reason: str = "",
        pip_size: float = 0.0001,
        spread_pips: float = 0.0,
        spread_limit: float = 3.0,
        expected_target_pips: float | None = None,
        opportunity_type: str | None = None,
        invalidation_level: float | None = None,
    ) -> TradeThesis:
        if side not in {"buy", "sell"}:
            return self._reject(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                market_story=market_story or "No directional thesis",
                reason="Direction must be buy or sell",
            )

        story = (market_story or "").strip() or self._infer_story(
            side, structure, bias, opportunity_type
        )
        if not story:
            return self._reject(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                market_story="No coherent market story",
                reason="No coherent market story exists",
            )

        stop, invalidation, inv_reason = self._geometry(
            side=side,
            entry_price=entry_price,
            structure=structure,
            pip_size=pip_size,
            invalidation_level=invalidation_level,
        )
        risk = abs(entry_price - stop)
        if risk <= 0:
            return self._reject(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                market_story=story,
                reason="Stop geometry invalid — zero risk distance",
            )

        target_pips = expected_target_pips
        if target_pips is None or target_pips <= 0:
            target_pips = risk / pip_size * self.config.default_tp_r if pip_size > 0 else 0.0

        if side == "buy":
            take_profit = entry_price + target_pips * pip_size
        else:
            take_profit = entry_price - target_pips * pip_size

        reward = abs(take_profit - entry_price)
        rr = reward / risk if risk > 0 else 0.0

        if spread_pips > spread_limit:
            return self._reject(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                market_story=story,
                reason=f"Spread {spread_pips:.1f} pips exceeds limit {spread_limit:.1f}",
            )

        if rr < self.config.min_reward_risk:
            return self._reject(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                market_story=story,
                reason=f"Reward/risk {rr:.2f} below minimum {self.config.min_reward_risk:.2f}",
            )

        confidence = self._confidence(
            bias=bias,
            structure=structure,
            story=story,
            rr=rr,
            opportunity_type=opportunity_type,
        )
        expected_path = self._expected_path(
            side=side,
            opportunity_type=opportunity_type,
            structure=structure,
        )
        reason = entry_reason.strip() or self._entry_reason(
            side=side,
            opportunity_type=opportunity_type,
            structure=structure,
            bias=bias,
        )
        evidence = self._evidence(
            side=side,
            bias=bias,
            structure=structure,
            opportunity_type=opportunity_type,
            rr=rr,
        )

        return TradeThesis(
            market_story=story,
            direction=side,  # type: ignore[arg-type]
            entry_reason=reason,
            invalidation_reason=inv_reason,
            expected_path=expected_path,
            risk=risk,
            reward=reward,
            confidence=confidence,
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop,
            invalidation_level=invalidation,
            take_profit=take_profit,
            reward_risk_ratio=rr,
            is_tradeable=True,
            evidence=tuple(evidence),
        )

    @staticmethod
    def _geometry(
        *,
        side: str,
        entry_price: float,
        structure: MarketContext | None,
        pip_size: float,
        invalidation_level: float | None,
    ) -> tuple[float, float, str]:
        buffer = INVALIDATION_BUFFER_PIPS * pip_size
        if invalidation_level is not None and invalidation_level > 0:
            if side == "buy":
                stop = min(invalidation_level - buffer, entry_price - buffer)
                inv = invalidation_level
                reason = f"Bullish thesis invalid if price closes below {inv:.5f}"
            else:
                stop = max(invalidation_level + buffer, entry_price + buffer)
                inv = invalidation_level
                reason = f"Bearish thesis invalid if price closes above {inv:.5f}"
            return stop, inv, reason

        if structure is not None:
            if side == "buy" and structure.swing_lows:
                swing = min(s.price for s in structure.swing_lows)
                inv = swing
                stop = swing - buffer
                return stop, inv, f"Bullish thesis invalid if H1 swing low {inv:.5f} breaks"
            if side == "sell" and structure.swing_highs:
                swing = max(s.price for s in structure.swing_highs)
                inv = swing
                stop = swing + buffer
                return stop, inv, f"Bearish thesis invalid if H1 swing high {inv:.5f} breaks"

        fallback = entry_price - 20 * pip_size if side == "buy" else entry_price + 20 * pip_size
        if side == "buy":
            stop = fallback
            inv = fallback + buffer
            reason = "Bullish thesis invalid if structure support fails"
        else:
            stop = fallback
            inv = fallback - buffer
            reason = "Bearish thesis invalid if structure resistance fails"
        return stop, inv, reason

    @staticmethod
    def _infer_story(
        side: str,
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
        opportunity_type: str | None,
    ) -> str:
        parts: list[str] = []
        if opportunity_type:
            parts.append(opportunity_type.replace("_", " "))
        if bias is not None and bias.bias != "neutral":
            parts.append(f"{bias.bias} MTF bias")
        if structure is not None and structure.trend != "neutral":
            parts.append(f"{structure.trend} H1 structure")
        if not parts:
            return ""
        action = "long" if side == "buy" else "short"
        return f"{action.capitalize()} {' + '.join(parts)}"

    @staticmethod
    def _confidence(
        *,
        bias: MultiTimeframeBiasResult | None,
        structure: MarketContext | None,
        story: str,
        rr: float,
        opportunity_type: str | None,
    ) -> float:
        score = 0.40
        if bias is not None:
            score += min(bias.confidence, 1.0) * 0.25
            aligned = (
                (bias.bias == "bullish")
                or (bias.bias == "bearish")
            )
            if aligned:
                score += 0.05
        if structure is not None:
            if structure.trend in {"bullish", "bearish"}:
                score += 0.10
        if story:
            score += 0.05
        if opportunity_type:
            score += 0.05
        score += min(rr / 3.0, 0.10)
        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _expected_path(
        *,
        side: str,
        opportunity_type: str | None,
        structure: MarketContext | None,
    ) -> str:
        opp = (opportunity_type or "").lower()
        if "sweep" in opp or "liquidity" in opp:
            return (
                "Sweep reclaim → impulse toward opposing liquidity → "
                "partial at 1R, runner to target liquidity"
            )
        if "pullback" in opp or "continuation" in opp:
            return "Pullback holds structure → continuation toward prior swing extreme"
        if "breakout" in opp or "retest" in opp:
            return "Breakout retest holds → expansion toward measured move"
        if "mean_reversion" in opp or "snapback" in opp:
            return "Stretch fades → snapback toward equilibrium"
        trend = structure.trend if structure else "neutral"
        direction = "higher" if side == "buy" else "lower"
        return f"{trend} structure → price seeks {direction} while thesis holds"

    @staticmethod
    def _entry_reason(
        *,
        side: str,
        opportunity_type: str | None,
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
    ) -> str:
        reasons: list[str] = []
        if opportunity_type:
            reasons.append(f"{opportunity_type.replace('_', ' ')} setup")
        if bias is not None and bias.bias != "neutral":
            reasons.append(f"{bias.bias} bias alignment")
        if structure is not None and structure.trend != "neutral":
            reasons.append(f"{structure.trend} structure intact")
        if not reasons:
            return f"{'Buy' if side == 'buy' else 'Sell'} on story trigger"
        return "; ".join(reasons)

    @staticmethod
    def _evidence(
        *,
        side: str,
        bias: MultiTimeframeBiasResult | None,
        structure: MarketContext | None,
        opportunity_type: str | None,
        rr: float,
    ) -> list[str]:
        evidence: list[str] = []
        if bias is not None:
            evidence.append(f"MTF bias {bias.bias} ({bias.confidence:.0%})")
        if structure is not None:
            evidence.append(f"H1 trend {structure.trend}")
        if opportunity_type:
            evidence.append(f"Opportunity: {opportunity_type}")
        evidence.append(f"Reward/risk {rr:.2f}")
        return evidence

    def _reject(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        market_story: str,
        reason: str,
    ) -> TradeThesis:
        direction: ThesisDirection = side if side in {"buy", "sell"} else "buy"  # type: ignore[assignment]
        return TradeThesis(
            market_story=market_story,
            direction=direction,
            entry_reason="",
            invalidation_reason=reason,
            expected_path="",
            risk=0.0,
            reward=0.0,
            confidence=0.0,
            symbol=symbol,
            entry_price=entry_price,
            is_tradeable=False,
            rejection_reason=reason,
        )


__all__ = [
    "ThesisEngine",
    "ThesisEngineConfig",
    "ThesisEngineError",
    "TradeThesis",
    "ThesisDirection",
]
