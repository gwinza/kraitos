"""Expectancy participation gates — import-safe (no learning/runtime deps)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.market_story_engine import MarketStory
    from intelligence.market_story_engine import MarketStoryResult

MIN_STORY_CONFIDENCE = 38.0
MIN_EXPECTED_R = 0.05


def story_actionable(
    brain_story: MarketStory | None,
    legacy_story: MarketStoryResult | None,
) -> bool:
    if brain_story is not None:
        if brain_story.direction != "neutral" and brain_story.confidence >= MIN_STORY_CONFIDENCE:
            return True
    if legacy_story is not None and legacy_story.story_clear:
        return True
    return False


def participation_unlock(
    *,
    harvest_allowed: bool,
    brain_story: MarketStory | None,
    legacy_story: MarketStoryResult | None,
    harvest_score_band: str | None,
    expected_r: float | None = None,
    scalp_ok: bool = False,
) -> bool:
    """Whether a pipeline result may participate — expectancy-first, not story_clear."""
    if scalp_ok or harvest_allowed:
        return True
    if story_actionable(brain_story, legacy_story):
        return True
    if harvest_score_band not in {None, "no_harvest"}:
        return True
    if expected_r is not None and expected_r >= MIN_EXPECTED_R:
        return True
    return False
