"""Classify valid TraderBrain opportunities — allocate, don't deny."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from intelligence.market_story_engine import MarketStoryResult, OpportunityType
    from intelligence.opportunity_allocator import OpportunityAllocation
    from intelligence.story_forecast_engine import StoryForecastResult

OpportunityClass = Literal[
    "MICRO_HARVEST", "HARVEST", "PROPER", "ELITE", "SCOUT", "NO_TRADE"
]

HARVEST_TYPES: frozenset[str] = frozenset({
    "liquidity_sweep",
    "compression_breakout",
    "breakout_retest",
    "trend_pause_resume",
    "mean_reversion_snapback",
    "session_transition",
    "failed_breakout",
})

PROPER_TYPES: frozenset[str] = frozenset({
    "pullback_continuation",
})

RISK_RANGES: dict[OpportunityClass, tuple[float, float]] = {
    "MICRO_HARVEST": (0.05, 0.15),
    "HARVEST": (0.10, 0.30),
    "PROPER": (0.50, 1.00),
    "ELITE": (1.00, 1.50),
    "SCOUT": (0.01, 0.10),
    "NO_TRADE": (0.0, 0.0),
}

CATASTROPHIC_DD_PCT = 50.0
DEFENSIVE_DD_PCT = 40.0


@dataclass(frozen=True)
class OpportunityClassification:
    """Portfolio tier classification for one valid opportunity."""

    symbol: str
    opportunity_class: OpportunityClass
    opportunity_type: str | None
    base_risk_pct: float
    risk_pct_min: float
    risk_pct_max: float
    confidence: float
    no_trade: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "opportunity_class": self.opportunity_class,
            "opportunity_type": self.opportunity_type,
            "base_risk_pct": round(self.base_risk_pct, 3),
            "risk_pct_min": round(self.risk_pct_min, 3),
            "risk_pct_max": round(self.risk_pct_max, 3),
            "confidence": round(self.confidence, 2),
            "no_trade": self.no_trade,
            "reason": self.reason,
        }


class OpportunityClassifier:
    """
    Classify every valid TraderBrain opportunity.

    Default response is 'How much?' — not 'No.'
    NO_TRADE only for catastrophic safety or absent valid story.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._counts: dict[OpportunityClass, int] = {
            "MICRO_HARVEST": 0,
            "HARVEST": 0,
            "PROPER": 0,
            "ELITE": 0,
            "SCOUT": 0,
            "NO_TRADE": 0,
        }
        self._history: list[OpportunityClassification] = []
        self._scaled_not_rejected = 0

    @property
    def counts(self) -> dict[OpportunityClass, int]:
        return dict(self._counts)

    @property
    def scaled_not_rejected(self) -> int:
        return self._scaled_not_rejected

    def record_scaled_allocation(self) -> None:
        """Track opportunities that would have been rejected under old binary caps."""
        self._scaled_not_rejected += 1

    def classify(
        self,
        *,
        symbol: str,
        allocation: OpportunityAllocation | None = None,
        market_story: MarketStoryResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        mode: str = "harvest",
        valid_story: bool = True,
        emergency_stop: bool = False,
        broker_available: bool = True,
        live_safety_ok: bool = True,
        drawdown_pct: float = 0.0,
        target_pips: float = 10.0,
        setup_kind: str = "harvest",
    ) -> OpportunityClassification:
        normalized = symbol.strip().upper()

        if emergency_stop:
            return self._no_trade(normalized, "Emergency stop active")
        if not broker_available:
            return self._no_trade(normalized, "Broker unavailable")
        if not live_safety_ok:
            return self._no_trade(normalized, "Live safety violated")
        if drawdown_pct >= CATASTROPHIC_DD_PCT:
            return self._no_trade(
                normalized,
                f"Catastrophic drawdown protection ({drawdown_pct:.1f}%)",
            )
        defensive_scale = 1.0
        if drawdown_pct >= DEFENSIVE_DD_PCT:
            defensive_scale = 0.10
        if not valid_story:
            return self._no_trade(normalized, "TraderBrain — no valid story")

        opp_type = self._resolve_opportunity_type(market_story, story_forecast)
        forecast_conf = self._forecast_confidence(story_forecast, allocation)
        story_conf = market_story.overall_confidence if market_story else 50.0
        harvest_band = "none"
        harvest_score = 0.0
        if allocation is not None and allocation.harvest_score is not None:
            harvest_band = allocation.harvest_score.band
            harvest_score = allocation.harvest_score.score

        oas_tier = ""
        if allocation is not None and hasattr(allocation, "marketplace"):
            oas_tier = getattr(allocation.marketplace, "recommended_action", "")

        opp_class = self._resolve_class(
            opp_type=opp_type,
            mode=mode,
            target_pips=target_pips,
            forecast_conf=forecast_conf,
            story_conf=story_conf,
            harvest_band=harvest_band,
            harvest_score=harvest_score,
            allocation=allocation,
            setup_kind=setup_kind,
            oas_tier=oas_tier,
        )

        risk_min, risk_max = RISK_RANGES[opp_class]
        strength = self._strength_score(
            forecast_conf=forecast_conf,
            story_conf=story_conf,
            harvest_score=harvest_score,
            allocation=allocation,
        )
        base_risk = risk_min + (risk_max - risk_min) * strength
        if defensive_scale < 1.0:
            base_risk = max(0.01, base_risk * defensive_scale)

        council_note = ""
        if allocation is not None and allocation.council_consensus is not None:
            council_note = f"; council {allocation.council_consensus.consensus_confidence:.0f}"

        result = OpportunityClassification(
            symbol=normalized,
            opportunity_class=opp_class,
            opportunity_type=opp_type,
            base_risk_pct=round(base_risk, 3),
            risk_pct_min=risk_min,
            risk_pct_max=risk_max,
            confidence=strength * 100.0,
            no_trade=False,
            reason=(
                f"{opp_class} ({opp_type or mode}) "
                f"risk {base_risk:.2f}% [{risk_min:.2f}-{risk_max:.2f}]{council_note}"
            ),
        )
        self._counts[opp_class] += 1
        self._history.append(result)
        return result

    def _no_trade(self, symbol: str, reason: str) -> OpportunityClassification:
        result = OpportunityClassification(
            symbol=symbol,
            opportunity_class="NO_TRADE",
            opportunity_type=None,
            base_risk_pct=0.0,
            risk_pct_min=0.0,
            risk_pct_max=0.0,
            confidence=0.0,
            no_trade=True,
            reason=reason,
        )
        self._counts["NO_TRADE"] += 1
        self._history.append(result)
        return result

    @staticmethod
    def _resolve_opportunity_type(
        market_story: MarketStoryResult | None,
        story_forecast: StoryForecastResult | None,
    ) -> str | None:
        if market_story is not None and market_story.opportunity_type is not None:
            return market_story.opportunity_type
        if story_forecast is not None and story_forecast.opportunity_type:
            return story_forecast.opportunity_type
        return None

    @staticmethod
    def _forecast_confidence(
        story_forecast: StoryForecastResult | None,
        allocation: OpportunityAllocation | None,
    ) -> float:
        if story_forecast is not None:
            return story_forecast.confidence
        if allocation is not None and allocation.narrative_forecast is not None:
            return allocation.narrative_forecast.confidence
        if allocation is not None and allocation.council_consensus is not None:
            return allocation.council_consensus.consensus_confidence
        return 50.0

    def _resolve_class(
        self,
        *,
        opp_type: str | None,
        mode: str,
        target_pips: float,
        forecast_conf: float,
        story_conf: float,
        harvest_band: str,
        harvest_score: float,
        allocation: OpportunityAllocation | None,
        setup_kind: str = "harvest",
        oas_tier: str = "",
    ) -> OpportunityClass:
        if setup_kind == "micro_scalp" or mode in {"scalp", "micro_scalp"}:
            if target_pips <= 3.0:
                return "MICRO_HARVEST"
            return "HARVEST"

        if oas_tier == "REDUCED_RISK" or harvest_band == "conditional":
            return "SCOUT"

        if opp_type in PROPER_TYPES:
            if forecast_conf >= 80.0 and story_conf >= 75.0:
                return "ELITE"
            return "PROPER"

        if opp_type in HARVEST_TYPES or mode in {"harvest", "micro_scalp", "scalp"}:
            if target_pips <= 3.5:
                return "MICRO_HARVEST"
            if target_pips <= 5.5:
                return "HARVEST"
            if forecast_conf >= 75.0:
                return "PROPER"
            return "HARVEST"

        if forecast_conf >= 85.0 and story_conf >= 80.0:
            return "ELITE"

        if allocation is not None:
            trend = allocation.trend_strength
            if trend.quality == "institutional_trend" and trend.score >= 82.0:
                if forecast_conf >= 70.0:
                    return "ELITE"
                return "PROPER"

        if harvest_band in {"premium", "standard"} and harvest_score >= 70.0:
            return "PROPER" if target_pips > 4.0 else "HARVEST"

        if target_pips <= 3.5:
            return "MICRO_HARVEST"
        if target_pips <= 4.0 or mode in {"harvest", "micro_scalp"}:
            return "HARVEST"

        if forecast_conf >= 65.0 or story_conf >= 65.0:
            return "PROPER"

        if forecast_conf < 55.0 and story_conf < 55.0:
            return "SCOUT"

        return "HARVEST"

    @staticmethod
    def _strength_score(
        *,
        forecast_conf: float,
        story_conf: float,
        harvest_score: float,
        allocation: OpportunityAllocation | None,
    ) -> float:
        parts: list[float] = [
            forecast_conf / 100.0,
            story_conf / 100.0,
        ]
        if harvest_score > 0:
            parts.append(harvest_score / 100.0)
        if allocation is not None:
            parts.append(min(1.0, allocation.trend_strength.score / 100.0))
        raw = sum(parts) / len(parts)
        return max(0.15, min(1.0, raw))

    def write_classification_report(self) -> Path | None:
        if self.project_root is None:
            return None
        logs = self.project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        total = sum(self._counts.values())
        lines = [
            "# Opportunity Classification Report",
            "",
            f"**Generated:** {now}",
            "",
            "## Tier counts",
            "",
            "| Class | Count | Share |",
            "|-------|-------|-------|",
        ]
        for tier in ("MICRO_HARVEST", "HARVEST", "PROPER", "ELITE", "SCOUT", "NO_TRADE"):
            count = self._counts.get(tier, 0)
            share = f"{count / total:.1%}" if total else "0%"
            lines.append(f"| {tier} | {count} | {share} |")
        lines.extend([
            "",
            f"**Total classified:** {total}",
            "",
            "## Recent classifications",
            "",
            "| Symbol | Class | Type | Risk % | Reason |",
            "|--------|-------|------|--------|--------|",
        ])
        for item in self._history[-20:]:
            lines.append(
                f"| {item.symbol} | {item.opportunity_class} | "
                f"{item.opportunity_type or '-'} | {item.base_risk_pct:.2f}% | "
                f"{item.reason[:60]} |"
            )
        path = logs / "opportunity_classification_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
