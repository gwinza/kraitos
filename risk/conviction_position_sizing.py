"""Conviction-based position sizing — risk scales with evidence quality, not habit.

Risk percent follows conviction score tiers. Size never increases for revenge,
loss recovery, or emotional pressure — only when evidence is genuinely strong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from core.helpers import pip_size_for_symbol, pip_value_per_lot
from risk.models import RiskLimits
from risk.risk_manager import RiskManager
from risk.symbol_specialisation_control import get_symbol_specialisation_control

if TYPE_CHECKING:
    from brain.market_story_engine import MarketStory
    from execution.patience_engine import EntryOpportunity
    from intelligence.harvest_archetype_memory import ArchetypeRecord, HarvestArchetypeMemory
    from strategies.models import MarketContext

Side = Literal["buy", "sell"]

RISK_BY_SCORE: tuple[tuple[float, float], ...] = (
    (90.0, 2.00),
    (75.0, 1.00),
    (60.0, 0.50),
    (50.0, 0.25),
    (0.0, 0.15),
)

ENTRY_TYPE_TIMING: dict[str, float] = {
    "liquidity_sweep_rejection": 92.0,
    "retest_broken_structure": 86.0,
    "pullback_into_value": 78.0,
    "compression_before_expansion": 72.0,
}


@dataclass(frozen=True)
class SetupExpectancy:
    """Historical performance for a symbol/setup bucket."""

    average_r: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    sample_size: int = 0
    setup_label: str = ""

    @classmethod
    def from_archetype_record(cls, record: ArchetypeRecord) -> SetupExpectancy:
        return cls(
            average_r=record.average_r,
            win_rate=record.win_rate,
            profit_factor=record.profit_factor,
            sample_size=record.trades,
            setup_label=record.archetype,
        )


@dataclass(frozen=True)
class ConvictionSizing:
    """Sized participation from evidence quality."""

    score: float
    risk_percent: float
    position_size: float
    explanation: str
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "risk_percent": round(self.risk_percent, 3),
            "position_size": round(self.position_size, 2),
            "explanation": self.explanation,
            "components": {k: round(v, 2) for k, v in self.components.items()},
        }


@dataclass(frozen=True)
class ConvictionSizingConfig:
    """Weights for conviction score components (must sum to 1.0)."""

    story_weight: float = 0.22
    structure_weight: float = 0.20
    liquidity_weight: float = 0.15
    entry_timing_weight: float = 0.20
    risk_reward_weight: float = 0.13
    expectancy_weight: float = 0.10
    emotional_pressure_cap_pct: float = 0.50
    min_expectancy_samples: int = 6


class ConvictionPositionSizer:
    """Map evidence quality to risk percent and lot size."""

    def __init__(
        self,
        config: ConvictionSizingConfig | None = None,
        *,
        limits: RiskLimits | None = None,
        archetype_memory: HarvestArchetypeMemory | None = None,
    ) -> None:
        self.config = config or ConvictionSizingConfig()
        self.limits = limits or RiskLimits()
        self._risk_manager = RiskManager(self.limits)
        self._archetype_memory = archetype_memory

    def size(
        self,
        *,
        symbol: str,
        side: Side,
        balance: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float | None = None,
        story: MarketStory | None = None,
        structure: MarketContext | None = None,
        entry_opportunity: EntryOpportunity | None = None,
        setup_expectancy: SetupExpectancy | None = None,
        setup_key: str = "",
        loss_streak: int = 0,
        revenge_trading: bool = False,
        recovery_mode: bool = False,
        emotional_pressure: bool = False,
    ) -> ConvictionSizing:
        """Compute conviction score, risk tier, and position size."""
        symbol = symbol.strip().upper()
        expectancy = setup_expectancy or self._lookup_expectancy(symbol, setup_key)

        components = {
            "market_story": self._story_quality(story, side),
            "structure": self._structure_quality(structure, side),
            "liquidity": self._liquidity_quality(story),
            "entry_timing": self._entry_timing_quality(entry_opportunity),
            "risk_reward": self._risk_reward_quality(
                side=side,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                story=story,
            ),
            "historical_expectancy": self._expectancy_quality(expectancy),
        }

        cfg = self.config
        score = (
            components["market_story"] * cfg.story_weight
            + components["structure"] * cfg.structure_weight
            + components["liquidity"] * cfg.liquidity_weight
            + components["entry_timing"] * cfg.entry_timing_weight
            + components["risk_reward"] * cfg.risk_reward_weight
            + components["historical_expectancy"] * cfg.expectancy_weight
        )
        score = max(0.0, min(100.0, round(score, 2)))

        spec = get_symbol_specialisation_control().evaluate(
            symbol=symbol,
            conviction_score=score,
            setup_quality=components.get("entry_timing"),
        )
        if spec.confidence_adjustment:
            score = max(0.0, min(100.0, round(score + spec.confidence_adjustment, 2)))

        risk_percent = self._risk_percent_for_score(score)
        notes: list[str] = [f"Conviction {score:.0f}/100 → {risk_percent:.2f}% risk"]
        if spec.explanation:
            notes.append(spec.explanation)

        pressure = revenge_trading or recovery_mode or emotional_pressure or loss_streak >= 2
        if pressure:
            capped = min(risk_percent, cfg.emotional_pressure_cap_pct)
            if capped < risk_percent:
                notes.append(
                    "Emotional/recovery pressure detected — size capped; "
                    "never scale up to chase losses"
                )
                risk_percent = capped
            elif loss_streak >= 2:
                notes.append(
                    f"Loss streak {loss_streak} — size held at evidence tier, not increased"
                )

        pip_size = pip_size_for_symbol(symbol)
        pip_value = pip_value_per_lot(
            symbol,
            entry_price,
            contract_size=self.limits.contract_size,
        )
        position_size = self._risk_manager.calculate_lot_size(
            balance=balance,
            risk_pct=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            pip_size=pip_size,
            pip_value_per_lot=pip_value,
        )
        if spec.risk_multiplier < 0.999:
            position_size = round(
                max(self.limits.min_lot_size, position_size * spec.risk_multiplier),
                2,
            )

        top = max(components, key=components.get)  # type: ignore[arg-type]
        notes.append(f"Lead evidence: {top.replace('_', ' ')} ({components[top]:.0f})")
        if entry_opportunity is not None:
            notes.append(f"Entry: {entry_opportunity.entry_type.replace('_', ' ')}")
        if expectancy.sample_size >= cfg.min_expectancy_samples:
            notes.append(
                f"History: {expectancy.setup_label or setup_key} "
                f"avg R {expectancy.average_r:+.2f} over {expectancy.sample_size} trades"
            )

        return ConvictionSizing(
            score=score,
            risk_percent=risk_percent,
            position_size=position_size,
            explanation=" | ".join(notes),
            components=components,
        )

    def _lookup_expectancy(self, symbol: str, setup_key: str) -> SetupExpectancy:
        if self._archetype_memory is None or not setup_key:
            return SetupExpectancy()
        record = self._archetype_memory.get(symbol, setup_key)
        if record is None:
            return SetupExpectancy(setup_label=setup_key)
        return SetupExpectancy.from_archetype_record(record)

    @staticmethod
    def _story_quality(story: MarketStory | None, side: Side) -> float:
        if story is None:
            return 42.0
        score = story.confidence * 0.55 + story.trend_strength * 0.25
        aligned = (
            (side == "buy" and story.direction == "bullish")
            or (side == "sell" and story.direction == "bearish")
        )
        if aligned:
            score += 12.0
        elif story.direction == "neutral":
            score -= 15.0
        if story.controlling_side in {"buyers", "sellers"}:
            score += 4.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _structure_quality(structure: MarketContext | None, side: Side) -> float:
        if structure is None:
            return 40.0
        score = 48.0
        if side == "buy":
            if structure.trend == "bullish":
                score += 18.0
            if structure.higher_highs and structure.higher_lows:
                score += 16.0
            elif structure.higher_lows:
                score += 8.0
        else:
            if structure.trend == "bearish":
                score += 18.0
            if structure.lower_highs and structure.lower_lows:
                score += 16.0
            elif structure.lower_highs:
                score += 8.0
        if structure.last_bos is not None:
            bos_dir = "buy" if "bullish" in structure.last_bos.kind else "sell"
            if bos_dir == side:
                score += 10.0
        if structure.last_choch is not None:
            score += 4.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _liquidity_quality(story: MarketStory | None) -> float:
        if story is None:
            return 45.0
        score = 40.0 + min(20.0, len(story.liquidity_targets) * 4.0)
        if story.trapped_traders:
            score += 14.0
        state = story.structure_state.lower()
        if "sweep" in state or "liquidity" in state:
            score += 12.0
        if "reclaim" in state:
            score += 8.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _entry_timing_quality(entry: EntryOpportunity | None) -> float:
        if entry is None:
            return 38.0
        base = ENTRY_TYPE_TIMING.get(entry.entry_type, 70.0)
        blended = base * 0.55 + entry.confidence * 0.45
        return max(0.0, min(100.0, blended))

    @staticmethod
    def _risk_reward_quality(
        *,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float | None,
        story: MarketStory | None,
    ) -> float:
        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return 20.0

        target = take_profit
        if target is None and story is not None:
            target = story.next_objective

        if target is None:
            return 50.0

        reward = abs(target - entry_price)
        if side == "buy" and target <= entry_price:
            reward = 0.0
        if side == "sell" and target >= entry_price:
            reward = 0.0

        r_multiple = reward / risk if risk > 0 else 0.0
        if r_multiple >= 2.5:
            return 95.0
        if r_multiple >= 2.0:
            return 88.0
        if r_multiple >= 1.5:
            return 78.0
        if r_multiple >= 1.2:
            return 65.0
        if r_multiple >= 1.0:
            return 52.0
        if r_multiple >= 0.8:
            return 38.0
        return 25.0

    def _expectancy_quality(self, expectancy: SetupExpectancy) -> float:
        if expectancy.sample_size < self.config.min_expectancy_samples:
            return 50.0

        score = 50.0
        if expectancy.average_r is not None:
            score += min(25.0, max(-20.0, expectancy.average_r * 18.0))
        if expectancy.win_rate is not None:
            score += (expectancy.win_rate - 0.50) * 40.0
        if expectancy.profit_factor is not None:
            if expectancy.profit_factor >= 1.8:
                score += 12.0
            elif expectancy.profit_factor >= 1.2:
                score += 6.0
            elif expectancy.profit_factor < 0.9:
                score -= 15.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _risk_percent_for_score(score: float) -> float:
        for threshold, risk_pct in RISK_BY_SCORE:
            if score >= threshold:
                return risk_pct
        return RISK_BY_SCORE[-1][1]


__all__ = [
    "ConvictionPositionSizer",
    "ConvictionSizing",
    "ConvictionSizingConfig",
    "RISK_BY_SCORE",
    "SetupExpectancy",
]
