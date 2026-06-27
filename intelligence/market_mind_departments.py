"""V5 Market Mind — specialist departments that describe reality, never gate trades."""

from __future__ import annotations

from typing import TYPE_CHECKING

from intelligence.picture_models import DepartmentContribution, LiveMarketStory, MarketPicture

if TYPE_CHECKING:
    from brains.models import TradeCandidate


class MacroDepartment:
    """Macro department — paints higher-timeframe institutional backdrop (H8/H4)."""

    def analyze(self, candidate: TradeCandidate) -> DepartmentContribution:
        evidence: list[str] = []
        observation = "Macro backdrop not yet mapped."
        confidence = 40.0
        implications: list[str] = ()
        uncertainty = ""

        bias = candidate.bias
        if bias is not None:
            layers = getattr(bias, "layers", ()) or ()
            macro_layers = [
                layer
                for layer in layers
                if getattr(layer, "role", "") in {"macro", "higher", "h8", "h4"}
                or getattr(layer, "timeframe", "") in {"H8", "H4", "D1"}
            ]
            if macro_layers:
                for layer in macro_layers[:2]:
                    tf = getattr(layer, "timeframe", "macro")
                    direction = getattr(layer, "bias", getattr(layer, "direction", "neutral"))
                    layer_conf = float(getattr(layer, "confidence", 0.5) or 0.5) * 100
                    evidence.append(f"{tf} {direction} ({layer_conf:.0f}%)")
                    confidence = max(confidence, layer_conf)
                dominant = macro_layers[0]
                direction = getattr(dominant, "bias", getattr(dominant, "direction", "neutral"))
                observation = f"Higher timeframe macro bias is {direction}"
                implications = (f"Macro {direction} frames lower-timeframe opportunity",)
            else:
                observation = f"Multi-timeframe bias is {bias.bias} ({bias.confidence:.0%})"
                confidence = float(bias.confidence or 0.5) * 100
                evidence.append(f"Composite bias {bias.bias}")

        story = candidate.market_story
        if story is not None:
            macro_story = getattr(story, "macro_story", None)
            if macro_story is not None:
                macro_dir = getattr(macro_story, "direction", "")
                macro_narr = getattr(macro_story, "narrative", "") or getattr(
                    macro_story, "summary", ""
                )
                if macro_narr:
                    evidence.append(macro_narr[:100])
                if macro_dir:
                    observation = f"Macro story: {macro_dir} control on H8/H4"
                    confidence = max(confidence, float(getattr(macro_story, "confidence", 0.6) or 0.6) * 100)
                    implications = (macro_narr[:120] or observation,)

        if not evidence:
            uncertainty = "No H8/H4 macro data — using tactical read only"

        return DepartmentContribution(
            department="macro",
            observation=observation,
            evidence=tuple(evidence) or ("Macro data unavailable",),
            confidence=confidence,
            implications=implications,
            uncertainty=uncertainty,
        )


class NarratorDepartment:
    """
    Narrator department — paints the live story as evidence for the picture.

    The NarratorEngine produces the final voice; this department contributes
    observations that other departments can challenge during fusion.
    """

    def analyze(
        self,
        *,
        story: LiveMarketStory,
        picture: MarketPicture | None = None,
    ) -> DepartmentContribution:
        evidence = (
            f"What: {story.what_is_happening[:120]}",
            f"Why: {story.why_it_is_happening[:100]}",
            f"Who: {story.who_is_in_control[:80]}",
        )
        contradictions: tuple[str, ...] = ()
        if picture is not None and picture.contradictions:
            contradictions = tuple(
                f"Narrator notes tension: {item[:80]}" for item in picture.contradictions[:2]
            )

        observation = (
            f"The market is {story.what_is_happening[:100]}. "
            f"Next chapter: {story.next_likely_chapter[:80]}"
        )
        implications = (
            f"Objective: {story.market_objective[:80]}",
            f"Trapped cohort: {story.who_is_trapped[:80]}",
        )

        return DepartmentContribution(
            department="narrator",
            observation=observation,
            evidence=evidence,
            confidence=story.confidence,
            contradictions=contradictions,
            implications=implications,
        )
