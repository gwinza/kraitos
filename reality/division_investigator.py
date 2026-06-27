"""Every division investigates every World Model — optimized batch path."""

from __future__ import annotations

from council.cognitive_models import CouncilObservation
from intelligence.picture_models import DepartmentContribution
from reality.reality_models import DivisionInvestigation, WorldModel

_COUNCIL_TO_DIVISION = {
    "story": "narrative",
    "psychology": "behaviour",
    "order_flow": "order_flow",
    "memory": "memory",
    "session": "session",
}

_MODEL_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "institutional_accumulation": {
        "strengthen": ("accumulation", "absorption", "institutional", "reclaim", "support", "volume"),
        "weaken": ("distribution", "trap", "exhaustion", "reject", "weak volume"),
    },
    "bull_trap": {
        "strengthen": ("trap", "false", "reject", "failure", "exhaustion", "overbought"),
        "weaken": ("continuation", "breakout", "acceptance", "follow-through", "volume"),
    },
    "liquidity_sweep_low": {
        "strengthen": ("sweep", "liquidity", "stop hunt", "reclaim", "trapped"),
        "weaken": ("no reclaim", "acceptance below", "continuation down"),
    },
    "liquidity_sweep_high": {
        "strengthen": ("sweep", "liquidity", "stop hunt", "reject", "trapped"),
        "weaken": ("acceptance above", "breakout", "continuation up"),
    },
    "momentum_continuation": {
        "strengthen": ("trend", "momentum", "continuation", "higher high", "lower low"),
        "weaken": ("reversal", "exhaustion", "divergence", "range"),
    },
    "distribution": {
        "strengthen": ("distribution", "supply", "reject", "lower high", "exhaustion"),
        "weaken": ("breakout", "demand", "accumulation", "acceptance"),
    },
    "institutional_distribution": {
        "strengthen": ("distribution", "supply", "reject", "breakdown"),
        "weaken": ("reclaim", "accumulation", "support"),
    },
    "range_equilibrium": {
        "strengthen": ("range", "equilibrium", "mean reversion", "compression"),
        "weaken": ("breakout", "trend", "expansion"),
    },
    "compression_before_expansion": {
        "strengthen": ("compression", "coil", "atr low", "squeeze"),
        "weaken": ("trending", "expansion complete"),
    },
    "bear_trap": {
        "strengthen": ("trap", "false", "reclaim", "squeeze"),
        "weaken": ("breakdown", "acceptance below"),
    },
    "momentum_breakdown": {
        "strengthen": ("breakdown", "momentum", "bearish", "lower low"),
        "weaken": ("reclaim", "reversal"),
    },
}


class DivisionInvestigator:
    """Investigate World Models from division evidence — batch-optimized."""

    def investigate_all(
        self,
        *,
        models: tuple[WorldModel, ...],
        departments: tuple[DepartmentContribution, ...],
        council_observations: tuple[CouncilObservation, ...],
    ) -> tuple[DivisionInvestigation, ...]:
        if not models:
            return ()

        dept_map = {d.department: d for d in departments}
        council_map = {obs.council: obs for obs in council_observations}

        # Only divisions with actual evidence — skip empty V8 slots
        divisions: list[str] = []
        seen: set[str] = set()
        for dept in departments:
            if dept.department not in seen:
                divisions.append(dept.department)
                seen.add(dept.department)
        for council in council_map:
            mapped = _COUNCIL_TO_DIVISION.get(council, council)
            if mapped not in seen:
                divisions.append(mapped)
                seen.add(mapped)

        # Precompute evidence text once per division
        division_text: dict[str, str] = {}
        division_dept: dict[str, DepartmentContribution | None] = {}
        for division in divisions:
            division_text[division] = self._division_text(division, dept_map, council_map)
            division_dept[division] = dept_map.get(division)
            if division_dept[division] is None:
                for council, mapped in _COUNCIL_TO_DIVISION.items():
                    if mapped == division:
                        division_dept[division] = dept_map.get(council)
                        break

        investigations: list[DivisionInvestigation] = []
        for division in divisions:
            text = division_text[division]
            dept = division_dept[division]
            for model in models:
                investigations.append(
                    self._investigate_one(
                        division=division,
                        model=model,
                        evidence_text=text,
                        dept=dept,
                    )
                )
        return tuple(investigations)

    @staticmethod
    def _division_text(
        division: str,
        dept_map: dict[str, DepartmentContribution],
        council_map: dict[str, CouncilObservation],
    ) -> str:
        parts: list[str] = []
        dept = dept_map.get(division)
        if dept is not None:
            parts.append(dept.observation)
            parts.extend(dept.evidence)
        for council, mapped in _COUNCIL_TO_DIVISION.items():
            if mapped == division and council in council_map:
                obs = council_map[council]
                parts.append(obs.headline)
                parts.append(obs.reasoning)
                parts.extend(obs.evidence)
        obs = council_map.get(division)
        if obs is not None:
            parts.append(obs.headline)
            parts.append(obs.reasoning)
        return " ".join(parts).lower()

    @staticmethod
    def _investigate_one(
        *,
        division: str,
        model: WorldModel,
        evidence_text: str,
        dept: DepartmentContribution | None,
    ) -> DivisionInvestigation:
        keywords = _MODEL_KEYWORDS.get(model.model_id, {})
        strengthen_kw = keywords.get("strengthen", ())
        weaken_kw = keywords.get("weaken", ())

        strengthen_hits = [kw for kw in strengthen_kw if kw in evidence_text]
        weaken_hits = [kw for kw in weaken_kw if kw in evidence_text]

        if dept is not None:
            obs_lower = dept.observation.lower()
            if model.direction == "bullish" and any(w in obs_lower for w in ("bearish", "sell")):
                weaken_hits.append("directional mismatch")
            elif model.direction == "bearish" and any(w in obs_lower for w in ("bullish", "buy")):
                weaken_hits.append("directional mismatch")

        strengthens = len(strengthen_hits) > len(weaken_hits) and bool(strengthen_hits)
        weakens = len(weaken_hits) > len(strengthen_hits) and bool(weaken_hits)
        confidence = float(dept.confidence if dept else 50.0)

        evidence: list[str] = []
        if strengthen_hits:
            evidence.append(f"Supports: {', '.join(strengthen_hits[:3])}")
        if weaken_hits:
            evidence.append(f"Weakens: {', '.join(weaken_hits[:3])}")
        if not evidence:
            evidence.append(f"No strong {division} evidence for or against")

        unexplained = ""
        if not strengthens and not weakens:
            unexplained = f"{division} inconclusive for {model.name}"

        return DivisionInvestigation(
            division=division,
            world_model_id=model.model_id,
            strengthens=strengthens,
            weakens=weakens,
            evidence=tuple(evidence),
            confidence=confidence,
            unexplained=unexplained,
        )
