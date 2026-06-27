"""Narrator Engine — plain-English market story every cycle."""

from __future__ import annotations

from intelligence.picture_models import (
    DepartmentContribution,
    LiveMarketStory,
    MarketPicture,
    NarratorOutput,
)


class NarratorEngine:
    """
    Write continuous plain-English market narration.

    The narrator is part of reasoning — departments challenge and update
    the narration until the picture becomes coherent.
    """

    def narrate(
        self,
        *,
        story: LiveMarketStory,
        picture: MarketPicture,
        departments: tuple[DepartmentContribution, ...],
    ) -> NarratorOutput:
        dept_map = {d.department: d for d in departments}

        opening = f"The market is currently {story.what_is_happening[:200]}"
        institutions = self._dept_line(dept_map, "liquidity", "order_flow", default=story.who_is_in_control)
        retail = story.who_is_trapped or self._dept_line(
            dept_map, "psychology", default="Retail positioning unclear from current evidence."
        )
        liquidity = story.liquidity_location or self._dept_line(dept_map, "liquidity")
        momentum = self._dept_line(dept_map, "trend", "order_flow", default="Momentum mixed.")
        volatility = self._dept_line(dept_map, "volatility", default="Volatility regime transitional.")
        next_event = story.next_likely_chapter
        confidence_statement = (
            f"Confidence is {picture.confidence:.0f}/100 — picture is {picture.clarity}."
        )
        invalidation = (
            f"This thesis is invalidated if {picture.dominant_side} control fails "
            f"or key liquidity level is lost."
        )
        if picture.contradictions:
            invalidation += f" Watch: {'; '.join(picture.contradictions[:2])}."

        paragraphs = [
            opening,
            f"Institutions appear to be {institutions}",
            f"Retail traders are likely {retail}",
            f"Liquidity is {liquidity}",
            f"Momentum is {momentum}",
            f"Volatility is {volatility}",
            f"The next likely event is {next_event}",
            confidence_statement,
            invalidation,
        ]
        full = " ".join(paragraphs)

        return NarratorOutput(
            symbol=story.symbol,
            opening=opening,
            institutions=institutions,
            retail=retail,
            liquidity=liquidity,
            momentum=momentum,
            volatility=volatility,
            next_event=next_event,
            confidence_statement=confidence_statement,
            invalidation=invalidation,
            full_narration=full,
        )

    @staticmethod
    def _dept_line(
        dept_map: dict[str, DepartmentContribution],
        *names: str,
        default: str = "unclear from current evidence",
    ) -> str:
        for name in names:
            dept = dept_map.get(name)
            if dept is not None and dept.observation:
                return dept.observation[:180]
        return default
