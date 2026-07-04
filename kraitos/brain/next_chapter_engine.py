"""
NextChapterEngine: Predict the next market chapter.

Markets unfold like books. The current candle is not the story.
It is one sentence. The NextChapterEngine predicts the next chapter,
not the next candle.

Possible chapters: Accumulation, Expansion, Distribution, Capitulation,
Mean Reversion, Breakout, Consolidation, Volatility Compression,
Liquidity Search, Trend Continuation, Risk-Off Rotation, Risk-On Rotation,
Macro Repricing.
"""

from dataclasses import dataclass, field
from kraitos.core.market_story import MarketStory
from kraitos.brain.simulation_engine import PossibleMarketFutures


# Valid market chapters
VALID_CHAPTERS = {
    "Accumulation": "Participants building positions at low prices.",
    "Expansion": "Market accelerates higher with broad participation.",
    "Distribution": "Participants gradually exiting positions.",
    "Capitulation": "Panic selling at extremes. Capitulation phase.",
    "Mean Reversion": "Price reverting toward moving average or fair value.",
    "Breakout": "Market breaks key level with volume.",
    "Consolidation": "Price consolidating in range. Gathering energy.",
    "Volatility Compression": "Declining volatility before potential move.",
    "Liquidity Search": "Market hunting liquidity at key levels.",
    "Trend Continuation": "Established trend persists.",
    "Risk-Off Rotation": "Participants rotating away from risk assets.",
    "Risk-On Rotation": "Participants rotating into risk assets.",
    "Macro Repricing": "Market repricing due to macro regime shift.",
}


@dataclass
class NextChapter:
    """
    A predicted next market chapter.

    This is NOT a prediction of the next candle. It is a prediction of
    the next phase of market development.

    Attributes
    ----------
    chapter_name : str
        Name of the chapter (from VALID_CHAPTERS).
    description : str
        Plain-English description of this chapter.
    why : str
        Why this chapter is likely based on evidence.
    confidence : float
        Confidence in this chapter prediction [0.0, 1.0].
    invalidated_by : list[str]
        Specific conditions that would prove this chapter wrong.
    possible_after : list[str]
        Possible chapters that could follow this one.
    estimated_duration : str
        Rough estimate of how long this chapter might last (e.g., "2-5 candles", "days to weeks").
    key_watch_points : list[str]
        Critical prices or events to watch during this chapter.
    """

    chapter_name: str
    description: str
    why: str
    confidence: float = 0.5
    invalidated_by: list[str] = field(default_factory=list)
    possible_after: list[str] = field(default_factory=list)
    estimated_duration: str = "Unknown"
    key_watch_points: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the chapter on creation."""
        if self.chapter_name not in VALID_CHAPTERS:
            raise ValueError(
                f"Invalid chapter: '{self.chapter_name}'. "
                f"Must be one of: {', '.join(VALID_CHAPTERS.keys())}"
            )

        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"NextChapter({self.chapter_name}, "
            f"confidence={self.confidence:.1%}, "
            f"duration={self.estimated_duration})"
        )


class NextChapterEngine:
    """
    Predict the next chapter of market development.

    The NextChapterEngine receives a MarketStory and SimulationResults
    and predicts the next chapter of market evolution.

    It does NOT predict the next candle. It predicts the next phase.
    """

    def __init__(
        self,
        market_story: MarketStory | None = None,
        simulation_results: PossibleMarketFutures | None = None,
    ) -> None:
        """
        Initialize the NextChapterEngine.

        Parameters
        ----------
        market_story : MarketStory, optional
            The current market narrative.
        simulation_results : PossibleMarketFutures, optional
            Simulated future scenarios.
        """
        self.market_story = market_story
        self.simulation_results = simulation_results

    def choose_best_chapter(
        self,
        market_story: MarketStory,
        simulation_results: PossibleMarketFutures,
    ) -> NextChapter:
        """
        Choose the most likely next chapter.

        Parameters
        ----------
        market_story : MarketStory
            The current market narrative.
        simulation_results : PossibleMarketFutures
            Simulated future scenarios.

        Returns
        -------
        NextChapter
            The predicted next chapter.

        Raises
        ------
        ValueError
            If inputs are invalid.
        """
        if not isinstance(market_story, MarketStory):
            raise ValueError(
                f"Expected MarketStory, got {type(market_story).__name__}."
            )

        if not isinstance(simulation_results, PossibleMarketFutures):
            raise ValueError(
                f"Expected PossibleMarketFutures, got {type(simulation_results).__name__}."
            )

        self.market_story = market_story
        self.simulation_results = simulation_results

        # Rank all possible chapters
        ranked = self.rank_chapters()

        if not ranked:
            return self._default_chapter()

        return ranked[0]

    def rank_chapters(self) -> list[NextChapter]:
        """
        Rank all possible next chapters by likelihood.

        Returns
        -------
        list[NextChapter]
            Chapters ranked by confidence (highest first).

        Raises
        ------
        ValueError
            If market_story or simulation_results not set.
        """
        if not self.market_story:
            raise ValueError("No market_story set. Call choose_best_chapter() first.")

        if not self.simulation_results:
            raise ValueError(
                "No simulation_results set. Call choose_best_chapter() first."
            )

        chapters = []

        # Generate chapter for each possible future
        for future in self.simulation_results.futures:
            chapter = self._generate_chapter_from_future(future)
            if chapter:
                chapters.append(chapter)

        # Sort by confidence descending
        chapters.sort(key=lambda c: c.confidence, reverse=True)

        return chapters

    def _generate_chapter_from_future(
        self, future
    ) -> NextChapter | None:
        """
        Generate a NextChapter from a possible future scenario.

        Parameters
        ----------
        future : PossibleFuture
            A simulated market future.

        Returns
        -------
        NextChapter or None
            A predicted chapter, or None if scenario doesn't map to a chapter.
        """
        scenario = future.scenario_name.lower()

        # Map scenarios to chapters
        if "continuation" in scenario:
            return self._build_trend_continuation_chapter(future)

        elif "liquidity" in scenario:
            return self._build_liquidity_search_chapter(future)

        elif "distribution" in scenario:
            return self._build_distribution_chapter(future)

        elif "reversal" in scenario:
            return self._build_capitulation_chapter(future)

        elif "unknown" in scenario:
            return None  # Skip unknown scenarios

        return None

    def _build_trend_continuation_chapter(self, future) -> NextChapter:
        """Build Trend Continuation chapter."""
        return NextChapter(
            chapter_name="Trend Continuation",
            description=(
                "The established trend persists with market momentum intact. "
                "Participants continue in the current direction."
            ),
            why=future.story,
            confidence=future.probability if future.probability else 0.5,
            invalidated_by=future.invalidation_criteria,
            possible_after=["Expansion", "Distribution", "Consolidation"],
            estimated_duration="Multiple candles to days",
            key_watch_points=future.key_inflection_points,
        )

    def _build_liquidity_search_chapter(self, future) -> NextChapter:
        """Build Liquidity Search chapter."""
        return NextChapter(
            chapter_name="Liquidity Search",
            description=(
                "Market moves aggressively to collect liquidity at key levels. "
                "Sharp moves to hunt stops followed by potential reversal."
            ),
            why=future.story,
            confidence=future.probability if future.probability else 0.4,
            invalidated_by=future.invalidation_criteria,
            possible_after=["Mean Reversion", "Consolidation", "Trend Continuation"],
            estimated_duration="Minutes to hours",
            key_watch_points=future.key_inflection_points,
        )

    def _build_distribution_chapter(self, future) -> NextChapter:
        """Build Distribution chapter."""
        return NextChapter(
            chapter_name="Distribution",
            description=(
                "Market enters distribution phase. Participants gradually reduce positions. "
                "Price may appear strong but volume participation is declining."
            ),
            why=future.story,
            confidence=future.probability if future.probability else 0.45,
            invalidated_by=future.invalidation_criteria,
            possible_after=["Capitulation", "Mean Reversion", "Consolidation"],
            estimated_duration="Days to weeks",
            key_watch_points=future.key_inflection_points,
        )

    def _build_capitulation_chapter(self, future) -> NextChapter:
        """Build Capitulation chapter."""
        return NextChapter(
            chapter_name="Capitulation",
            description=(
                "Market reverses sharply. Participants exit abruptly. "
                "Capitulation phase marks transition to new regime."
            ),
            why=future.story,
            confidence=future.probability if future.probability else 0.4,
            invalidated_by=future.invalidation_criteria,
            possible_after=["Mean Reversion", "Accumulation", "Consolidation"],
            estimated_duration="Hours to days",
            key_watch_points=future.key_inflection_points,
        )

    def _infer_chapters_from_story(self) -> list[str]:
        """
        Infer likely next chapters from the market story.

        Returns
        -------
        list[str]
            List of plausible next chapters.
        """
        chapters = []

        if not self.market_story:
            return chapters

        story_lower = (
            self.market_story.complete_story
            + self.market_story.dominant_theme
        ).lower()

        # Infer from dominant theme
        if "accumulation" in story_lower or "buyers defending" in story_lower:
            chapters.append("Expansion")

        if "distribution" in story_lower or "sellers appearing" in story_lower:
            chapters.append("Capitulation")

        if "volatility" in story_lower or "compressed" in story_lower:
            chapters.append("Breakout")

        if "ranging" in story_lower or "consolidat" in story_lower:
            chapters.append("Volatility Compression")

        if "rotation" in story_lower or "risk-off" in story_lower:
            chapters.append("Risk-Off Rotation")

        if "participation" in story_lower and "weak" not in story_lower:
            chapters.append("Expansion")

        # Infer from contradictions
        if self.market_story and len(self.market_story.contradictory_evidence) > 3:
            chapters.append("Mean Reversion")

        return list(dict.fromkeys(chapters))  # Remove duplicates

    def _default_chapter(self) -> NextChapter:
        """Return a default chapter when prediction is uncertain."""
        return NextChapter(
            chapter_name="Consolidation",
            description=(
                "Market consolidates. Insufficient evidence for more specific prediction. "
                "Awaiting clarity before next major move."
            ),
            why="Prediction uncertainty too high. Insufficient council agreement or too many unknowns.",
            confidence=0.3,
            invalidated_by=["Sustained breakout on volume"],
            possible_after=list(VALID_CHAPTERS.keys()),
            estimated_duration="Variable",
            key_watch_points=[
                "Key support/resistance",
                "Volume behavior",
                "Participation levels",
            ],
        )

    def _estimate_chapter_duration(self, chapter_name: str) -> str:
        """
        Estimate typical duration of a chapter.

        Parameters
        ----------
        chapter_name : str
            The chapter name.

        Returns
        -------
        str
            Estimated duration.
        """
        durations = {
            "Accumulation": "Days to weeks",
            "Expansion": "Days to weeks",
            "Distribution": "Days to weeks",
            "Capitulation": "Hours to days",
            "Mean Reversion": "Hours to days",
            "Breakout": "Hours to days",
            "Consolidation": "Hours to days",
            "Volatility Compression": "Hours to days",
            "Liquidity Search": "Minutes to hours",
            "Trend Continuation": "Multiple candles",
            "Risk-Off Rotation": "Days to weeks",
            "Risk-On Rotation": "Days to weeks",
            "Macro Repricing": "Hours to days",
        }

        return durations.get(chapter_name, "Unknown")

    def __str__(self) -> str:
        """Return a human-readable representation."""
        status = "ready" if self.market_story and self.simulation_results else "idle"
        return f"NextChapterEngine({status})"
