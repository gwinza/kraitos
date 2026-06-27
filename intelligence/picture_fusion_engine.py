"""Picture Fusion Engine — fuse department observations into one market picture."""

from __future__ import annotations

from council.cognitive_models import CouncilObservation
from intelligence.market_mind_tuning import (
    DOMINANT_SIDE_MARGIN,
    KEY_EVIDENCE_MIN_CONF,
    NOISE_MAX_CONF,
    clarity_from_metrics,
    weighted_department_confidence,
)
from intelligence.picture_models import DepartmentContribution, MarketPicture, PictureClarity, PictureRegime


class PictureFusionEngine:
    """
    Combine department observations into one coherent market picture.

    No voting. No rule chains. Reasons about coherence, contradictions, and
    which evidence matters in the current regime.
    """

    def fuse(
        self,
        *,
        symbol: str,
        departments: tuple[DepartmentContribution, ...],
        regime_label: str = "unknown",
    ) -> MarketPicture:
        if not departments:
            return self._empty_picture(symbol)

        contributions = list(departments)
        bullish_weight = 0.0
        bearish_weight = 0.0
        total_weight = 0.0
        supporting: list[str] = []
        contradictions: list[str] = []
        noise: list[str] = []
        key_evidence: list[str] = []

        for dept in contributions:
            weight = dept.confidence / 100.0
            total_weight += weight
            for item in dept.evidence[:2]:
                supporting.append(f"{dept.department}: {item}")
            for item in dept.contradictions:
                contradictions.append(f"{dept.department}: {item}")
            if dept.uncertainty and dept.confidence < NOISE_MAX_CONF:
                noise.append(f"{dept.department}: {dept.uncertainty}")
            if dept.confidence >= KEY_EVIDENCE_MIN_CONF and dept.evidence:
                key_evidence.append(f"{dept.department}: {dept.evidence[0]}")

        obs_map = {d.department: d for d in contributions}
        trend = obs_map.get("trend")
        structure = obs_map.get("structure")
        liquidity = obs_map.get("liquidity")
        macro = obs_map.get("macro")
        if trend and structure:
            if trend.observation and structure.observation:
                if any(w in trend.observation.lower() for w in ("bullish", "buy")) and any(
                    w in structure.observation.lower() for w in ("bearish", "sell", "lower")
                ):
                    contradictions.append("trend vs structure directional mismatch")
                elif any(w in trend.observation.lower() for w in ("bearish", "sell")) and any(
                    w in structure.observation.lower() for w in ("bullish", "buy", "higher")
                ):
                    contradictions.append("trend vs structure directional mismatch")

        if liquidity and "stop hunt" in liquidity.observation.lower():
            key_evidence.append(f"liquidity: {liquidity.observation[:120]}")

        dominant_side = "neutral"
        if trend:
            if "bullish" in trend.observation.lower() or "buy" in trend.observation.lower():
                bullish_weight += trend.confidence
            elif "bearish" in trend.observation.lower() or "sell" in trend.observation.lower():
                bearish_weight += trend.confidence
        if structure:
            if "bullish" in structure.observation.lower():
                bullish_weight += structure.confidence * 0.8
            elif "bearish" in structure.observation.lower():
                bearish_weight += structure.confidence * 0.8
        if macro:
            macro_obs = macro.observation.lower()
            if "bullish" in macro_obs or "buy" in macro_obs:
                bullish_weight += macro.confidence * 0.9
            elif "bearish" in macro_obs or "sell" in macro_obs:
                bearish_weight += macro.confidence * 0.9
            if macro.confidence >= 65:
                key_evidence.append(f"macro: {macro.observation[:120]}")

        if bullish_weight > bearish_weight + DOMINANT_SIDE_MARGIN:
            dominant_side = "bullish"
        elif bearish_weight > bullish_weight + DOMINANT_SIDE_MARGIN:
            dominant_side = "bearish"

        avg_conf = weighted_department_confidence(tuple(contributions))
        contradiction_ratio = len(contradictions) / max(len(contributions), 1)
        regime = self._classify_regime(regime_label, contributions)

        clarity_label, coherent, thesis_supported, reason = clarity_from_metrics(
            avg_conf=avg_conf,
            contradiction_ratio=contradiction_ratio,
            dominant_side=dominant_side,
            coherent=contradiction_ratio <= 0.48,
        )
        clarity: PictureClarity = clarity_label  # type: ignore[assignment]

        if regime == "compressed" and liquidity and "inconclusive" in liquidity.observation.lower():
            clarity = "incomplete"
            reason = reason or "Compression with unclear liquidity objective"

        summary_parts = [d.observation for d in contributions if d.confidence >= 55][:4]
        summary = ". ".join(summary_parts) if summary_parts else "Market picture forming."

        return MarketPicture(
            symbol=symbol,
            clarity=clarity,
            regime=regime,
            dominant_side=dominant_side,
            coherent_story=coherent,
            summary=summary,
            supporting_evidence=tuple(supporting[:10]),
            contradictions=tuple(contradictions[:8]),
            noise_evidence=tuple(noise[:6]),
            key_evidence=tuple(key_evidence[:8]),
            departments=tuple(contributions),
            confidence=round(avg_conf, 2),
            professional_thesis_supported=thesis_supported,
            reason_not_clear=reason,
        )

    @staticmethod
    def contribution_from_council(obs: CouncilObservation) -> DepartmentContribution:
        contradictions: list[str] = []
        uncertainty = ""
        if obs.confidence < 45:
            uncertainty = obs.detail if hasattr(obs, "detail") else obs.reasoning[:80]
        if "conflict" in obs.reasoning.lower() or "weak" in obs.headline.lower():
            contradictions.append(obs.headline)
        return DepartmentContribution(
            department=obs.council,
            observation=obs.headline,
            evidence=obs.evidence or (obs.reasoning[:120],),
            confidence=obs.confidence,
            contradictions=tuple(contradictions),
            implications=obs.forecasts,
            uncertainty=uncertainty,
        )

    @staticmethod
    def _classify_regime(
        regime_label: str,
        departments: list[DepartmentContribution],
    ) -> PictureRegime:
        label = regime_label.lower()
        if "low_liquidity" in label or "news" in label:
            return "volatile"
        if "trend" in label:
            return "trending"
        if "range" in label or "ranging" in label:
            return "ranging"
        vol = next((d for d in departments if d.department == "volatility"), None)
        if vol and "compression" in vol.observation.lower():
            return "compressed"
        if vol and "caution" in vol.observation.lower():
            return "volatile"
        return "transitional"

    @staticmethod
    def _empty_picture(symbol: str) -> MarketPicture:
        return MarketPicture(
            symbol=symbol,
            clarity="incomplete",
            regime="transitional",
            dominant_side="neutral",
            coherent_story=False,
            summary="Insufficient department observations to paint a picture.",
            supporting_evidence=(),
            contradictions=(),
            noise_evidence=(),
            key_evidence=(),
            departments=(),
            confidence=0.0,
            professional_thesis_supported=False,
            reason_not_clear="No department data",
        )
