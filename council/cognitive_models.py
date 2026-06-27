"""Data models for Kraitos V3 Cognitive Council Architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CouncilName = Literal[
    "story",
    "trend",
    "structure",
    "liquidity",
    "volume",
    "volatility",
    "order_flow",
    "session",
    "psychology",
    "memory",
    "risk",
    "execution",
]

DirectionBias = Literal["bullish", "bearish", "neutral"]
TradeSideHint = Literal["buy", "sell", "observe"]
ExecutionMode = Literal["observe", "probe", "reduced", "normal", "full", "wait"]


@dataclass(frozen=True)
class CouncilObservation:
    """One specialist council's view — evidence, not permission."""

    council: CouncilName
    headline: str
    reasoning: str
    direction: DirectionBias
    confidence: float
    success_probability: float
    evidence: tuple[str, ...] = ()
    forecasts: tuple[str, ...] = ()
    weight_hint: float = 1.0

    def to_dict(self) -> dict:
        return {
            "council": self.council,
            "headline": self.headline,
            "reasoning": self.reasoning,
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "success_probability": round(self.success_probability, 4),
            "evidence": list(self.evidence),
            "forecasts": list(self.forecasts),
            "weight_hint": round(self.weight_hint, 3),
        }


@dataclass(frozen=True)
class DeliberationMessage:
    """Inter-council communication during internal debate."""

    round_index: int
    from_council: CouncilName
    to_council: CouncilName | None
    message: str

    def to_dict(self) -> dict:
        return {
            "round": self.round_index,
            "from": self.from_council,
            "to": self.to_council,
            "message": self.message,
        }


@dataclass(frozen=True)
class MarketUnderstanding:
    """Coherent answers to what / why / who / where / next."""

    what_is_happening: str
    why_it_is_happening: str
    who_controls: str
    liquidity_location: str
    price_destination: str
    smart_money_view: str
    highest_probability_outcome: str

    def to_dict(self) -> dict:
        return {
            "what_is_happening": self.what_is_happening,
            "why_it_is_happening": self.why_it_is_happening,
            "who_controls": self.who_controls,
            "liquidity_location": self.liquidity_location,
            "price_destination": self.price_destination,
            "smart_money_view": self.smart_money_view,
            "highest_probability_outcome": self.highest_probability_outcome,
        }


@dataclass(frozen=True)
class CognitiveThesis:
    """Fused market thesis from CIO reasoning — probabilistic, not binary."""

    side: TradeSideHint
    market_understanding: MarketUnderstanding
    success_probability: float
    expected_reward_r: float
    confidence: float
    opportunity_quality: float
    risk_score: float
    narrative: str
    forecast: str
    conflicts: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "market_understanding": self.market_understanding.to_dict(),
            "success_probability": round(self.success_probability, 4),
            "expected_reward_r": round(self.expected_reward_r, 3),
            "confidence": round(self.confidence, 2),
            "opportunity_quality": round(self.opportunity_quality, 2),
            "risk_score": round(self.risk_score, 2),
            "narrative": self.narrative,
            "forecast": self.forecast,
            "conflicts": list(self.conflicts),
            "supporting_evidence": list(self.supporting_evidence),
        }


@dataclass(frozen=True)
class ExecutionStrategy:
    """How conviction maps to capital expression."""

    mode: ExecutionMode
    allocation_multiplier: float
    timing_guidance: str
    entry_style: str
    rationale: str

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "allocation_multiplier": round(self.allocation_multiplier, 3),
            "timing_guidance": self.timing_guidance,
            "entry_style": self.entry_style,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class HardVeto:
    """Objective constraint that fully blocks trading."""

    code: str
    reason: str

    def to_dict(self) -> dict:
        return {"code": self.code, "reason": self.reason}


@dataclass(frozen=True)
class CIODecision:
    """Chief Intelligence Officer output — one coherent view of the market."""

    symbol: str
    thesis: CognitiveThesis
    execution: ExecutionStrategy
    hard_vetoes: tuple[HardVeto, ...]
    deliberation: tuple[DeliberationMessage, ...]
    council_observations: tuple[CouncilObservation, ...]
    regime: str
    can_trade: bool
    observe_only: bool
    summary: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "thesis": self.thesis.to_dict(),
            "execution": self.execution.to_dict(),
            "hard_vetoes": [v.to_dict() for v in self.hard_vetoes],
            "deliberation": [m.to_dict() for m in self.deliberation],
            "council_observations": [o.to_dict() for o in self.council_observations],
            "regime": self.regime,
            "can_trade": self.can_trade,
            "observe_only": self.observe_only,
            "summary": self.summary,
        }

    @classmethod
    def from_snapshot_json(cls, payload: str, *, symbol: str = "") -> CIODecision | None:
        import json

        try:
            data = json.loads(payload)
        except Exception:
            return None
        if not isinstance(data, dict) or "thesis" not in data:
            return None
        understanding_raw = data.get("thesis", {}).get("market_understanding", {})
        if not isinstance(understanding_raw, dict):
            understanding_raw = {}
        understanding = MarketUnderstanding(
            what_is_happening=str(understanding_raw.get("what_is_happening", "")),
            why_it_is_happening=str(understanding_raw.get("why_it_is_happening", "")),
            who_controls=str(understanding_raw.get("who_controls", "")),
            liquidity_location=str(understanding_raw.get("liquidity_location", "")),
            price_destination=str(understanding_raw.get("price_destination", "")),
            smart_money_view=str(understanding_raw.get("smart_money_view", "")),
            highest_probability_outcome=str(
                understanding_raw.get("highest_probability_outcome", "")
            ),
        )
        thesis_raw = data.get("thesis", {})
        if not isinstance(thesis_raw, dict):
            return None
        thesis = CognitiveThesis(
            side=thesis_raw.get("side", "observe"),  # type: ignore[arg-type]
            market_understanding=understanding,
            success_probability=float(thesis_raw.get("success_probability", 0.0)),
            expected_reward_r=float(thesis_raw.get("expected_reward_r", 0.0)),
            confidence=float(thesis_raw.get("confidence", 0.0)),
            opportunity_quality=float(thesis_raw.get("opportunity_quality", 0.0)),
            risk_score=float(thesis_raw.get("risk_score", 0.0)),
            narrative=str(thesis_raw.get("narrative", "")),
            forecast=str(thesis_raw.get("forecast", "")),
        )
        exec_raw = data.get("execution", {})
        if not isinstance(exec_raw, dict):
            exec_raw = {}
        execution = ExecutionStrategy(
            mode=exec_raw.get("mode", "observe"),  # type: ignore[arg-type]
            allocation_multiplier=float(exec_raw.get("allocation_multiplier", 0.0)),
            timing_guidance=str(exec_raw.get("timing_guidance", "")),
            entry_style=str(exec_raw.get("entry_style", "")),
            rationale=str(exec_raw.get("rationale", "")),
        )
        observations = tuple(
            CouncilObservation(
                council=item.get("council", "story"),  # type: ignore[arg-type]
                headline=str(item.get("headline", "")),
                reasoning=str(item.get("reasoning", "")),
                direction=item.get("direction", "neutral"),  # type: ignore[arg-type]
                confidence=float(item.get("confidence", 0.0)),
                success_probability=float(item.get("success_probability", 0.0)),
            )
            for item in data.get("council_observations", [])
            if isinstance(item, dict)
        )
        return cls(
            symbol=str(data.get("symbol", symbol)),
            thesis=thesis,
            execution=execution,
            hard_vetoes=(),
            deliberation=(),
            council_observations=observations,
            regime=str(data.get("regime", "unknown")),
            can_trade=bool(data.get("can_trade", False)),
            observe_only=bool(data.get("observe_only", False)),
            summary=str(data.get("summary", "")),
        )


COGNITIVE_COUNCILS: tuple[CouncilName, ...] = (
    "story",
    "trend",
    "structure",
    "liquidity",
    "volume",
    "volatility",
    "order_flow",
    "session",
    "psychology",
    "memory",
    "risk",
    "execution",
)

ALLOCATION_TIERS: tuple[tuple[float, ExecutionMode, float], ...] = (
    (95.0, "full", 1.0),
    (85.0, "normal", 0.75),
    (75.0, "reduced", 0.50),
    (65.0, "probe", 0.25),
    (50.0, "wait", 0.12),
    (0.0, "observe", 0.0),
)
