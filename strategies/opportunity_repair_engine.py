"""Opportunity repair engine — scale down and tighten when thesis weakens, don't panic close."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

RepairAction = Literal[
    "monitor",
    "scale_down",
    "reduce_exposure",
    "tighten_management",
    "tighten_and_scale",
]
ThesisHealth = Literal["strong", "weakening", "fragile", "critical"]


@dataclass(frozen=True)
class OpportunityRepairResult:
    """Repair actions when thesis weakens — preserve upside, cut risk."""

    symbol: str
    side: str
    thesis_health: ThesisHealth
    repair_action: RepairAction
    size_multiplier: float
    stop_tighten_factor: float
    trail_aggressiveness: float
    instant_close: bool
    explanation: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "thesis_health": self.thesis_health,
            "repair_action": self.repair_action,
            "size_multiplier": round(self.size_multiplier, 3),
            "stop_tighten_factor": round(self.stop_tighten_factor, 3),
            "trail_aggressiveness": round(self.trail_aggressiveness, 3),
            "instant_close": self.instant_close,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class OpportunityRepairConfig:
    weakening_trend_quality: int = 50
    fragile_trend_quality: int = 38
    critical_reversal_pressure: int = 70
    scale_down_multiplier: float = 0.65
    reduce_exposure_multiplier: float = 0.45
    tighten_factor: float = 0.75


class OpportunityRepairEngine:
    """Repair weakening opportunities — reduce exposure, tighten stops, never panic."""

    def __init__(self, config: OpportunityRepairConfig | None = None) -> None:
        self.config = config or OpportunityRepairConfig()

    def evaluate(
        self,
        *,
        symbol: str,
        side: str,
        current_r: float = 0.0,
        trend_quality_score: int | None = None,
        reversal_pressure_score: int | None = None,
        retracement_probability: float | None = None,
        thesis_confidence: float | None = None,
        conviction_score: float | None = None,
        partial_taken: bool = False,
    ) -> OpportunityRepairResult:
        evidence: list[str] = []
        health = self._assess_health(
            trend_quality_score,
            reversal_pressure_score,
            retracement_probability,
            thesis_confidence,
            conviction_score,
            current_r,
            evidence,
        )

        action: RepairAction = "monitor"
        size_mult = 1.0
        tighten = 1.0
        trail = 0.5

        if health == "strong":
            action = "monitor"
            size_mult = 1.0
        elif health == "weakening":
            action = "tighten_management"
            tighten = self.config.tighten_factor
            trail = 0.65
            evidence.append("thesis weakening — tighten management, hold position")
        elif health == "fragile":
            action = "scale_down" if not partial_taken else "reduce_exposure"
            size_mult = (
                self.config.scale_down_multiplier
                if not partial_taken
                else self.config.reduce_exposure_multiplier
            )
            tighten = self.config.tighten_factor
            trail = 0.75
            evidence.append("fragile thesis — scale down exposure")
        elif health == "critical":
            if current_r > 0.5:
                action = "tighten_and_scale"
                size_mult = self.config.reduce_exposure_multiplier
                tighten = 0.60
                trail = 0.85
                evidence.append("critical but profitable — tighten and scale, protect profit")
            else:
                action = "reduce_exposure"
                size_mult = self.config.reduce_exposure_multiplier
                tighten = 0.55
                trail = 0.80
                evidence.append("critical thesis — reduce exposure, defer to fast failure for exit")

        return OpportunityRepairResult(
            symbol=symbol,
            side=side,
            thesis_health=health,
            repair_action=action,
            size_multiplier=size_mult,
            stop_tighten_factor=tighten,
            trail_aggressiveness=trail,
            instant_close=False,
            explanation=f"Thesis {health} — {action.replace('_', ' ')} (no instant close)",
            evidence=tuple(evidence or (f"Thesis health: {health}",)),
        )

    def _assess_health(
        self,
        trend_quality: int | None,
        reversal_pressure: int | None,
        retracement_prob: float | None,
        thesis_confidence: float | None,
        conviction: float | None,
        current_r: float,
        evidence: list[str],
    ) -> ThesisHealth:
        cfg = self.config
        weak_signals = 0
        critical_signals = 0

        if trend_quality is not None:
            if trend_quality < cfg.fragile_trend_quality:
                critical_signals += 1
                evidence.append(f"trend quality critical ({trend_quality})")
            elif trend_quality < cfg.weakening_trend_quality:
                weak_signals += 1
                evidence.append(f"trend quality weakening ({trend_quality})")

        if reversal_pressure is not None and reversal_pressure >= cfg.critical_reversal_pressure:
            critical_signals += 1
            evidence.append(f"reversal pressure elevated ({reversal_pressure})")
        elif reversal_pressure is not None and reversal_pressure >= 50:
            weak_signals += 1

        if retracement_prob is not None and retracement_prob < 0.40:
            weak_signals += 1
            evidence.append("low retracement probability — reversal risk")

        if thesis_confidence is not None and thesis_confidence < 0.40:
            weak_signals += 1
        if conviction is not None and conviction < 46:
            weak_signals += 1

        if current_r > 1.0 and weak_signals <= 1:
            return "strong"
        if critical_signals >= 2:
            return "critical"
        if critical_signals >= 1 or weak_signals >= 3:
            return "fragile"
        if weak_signals >= 1:
            return "weakening"
        return "strong"


__all__ = [
    "OpportunityRepairConfig",
    "OpportunityRepairEngine",
    "OpportunityRepairResult",
    "RepairAction",
    "ThesisHealth",
]
