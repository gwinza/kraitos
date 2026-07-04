"""
EpisodicMemory: Store complete market stories.

Not trades.
Stories.

Every important market episode becomes an experience.

Similarity is based on narrative structure, not price patterns:
- Macro environment
- Liquidity behavior
- Structure behavior
- Psychology
- Capital flow
- Risk environment
- Volatility regime

This file will eventually become Kraitos' experience.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class MarketEpisode:
    """
    A complete market story: what happened and why.

    This is not a trade record. It is a full narrative of a market episode,
    including context, behavior, psychology, and outcome.

    Attributes
    ----------
    episode_id : str
        Unique identifier (UUID).
    date : datetime
        Start date of the episode.
    symbol : str
        Market or instrument (e.g., "EURUSD", "ES", "GC", "AAPL").
    macro_environment : str
        Macro context (e.g., "rising rates", "stagflation fears", "flight to safety").
    market_story : str
        The narrative: what was the market story?
    current_chapter : str
        The market chapter during this episode (e.g., "Accumulation", "Expansion").
    next_chapter : str
        What chapter followed.
    major_events : list[str]
        Key events that shaped the episode.
    liquidity_behavior : str
        How liquidity behaved (e.g., "normal", "dried up", "rushed to exits").
    structure_behavior : str
        How price structure evolved (e.g., "broke key levels", "respecting support").
    psychology : str
        Market psychology (e.g., "complacent", "fearful", "greedy").
    capital_flow : str
        Direction and character of capital flows.
    risk_environment : str
        Risk sentiment (e.g., "risk-on", "risk-off", "transition").
    volatility_regime : str
        Volatility state (e.g., "low", "elevated", "extreme spike").
    duration : int
        Duration in days.
    what_happened : str
        Outcome: what actually occurred?
    lesson : str
        Plain English lesson from this episode.
    confidence : float
        How confident we are in understanding this episode [0.0, 1.0].
    tags : list[str]
        Tags for categorization (e.g., "central_bank", "earnings", "liquidity_crisis").
    similar_episodes : list[str]
        IDs of similar historical episodes.
    context : str
        Additional context or notes.
    """

    episode_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    date: datetime = field(default_factory=datetime.now)
    symbol: str = ""
    macro_environment: str = ""
    market_story: str = ""
    current_chapter: str = ""
    next_chapter: str = ""
    major_events: list[str] = field(default_factory=list)
    liquidity_behavior: str = ""
    structure_behavior: str = ""
    psychology: str = ""
    capital_flow: str = ""
    risk_environment: str = ""
    volatility_regime: str = ""
    duration: int = 0
    what_happened: str = ""
    lesson: str = ""
    confidence: float = 0.7
    tags: list[str] = field(default_factory=list)
    similar_episodes: list[str] = field(default_factory=list)
    context: str = ""

    def __post_init__(self) -> None:
        """Validate the episode on creation."""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

        if not self.symbol:
            raise ValueError("symbol cannot be empty.")

        if not self.market_story:
            raise ValueError("market_story cannot be empty.")

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"MarketEpisode({self.symbol}, {self.date.strftime('%Y-%m-%d')}, "
            f"{self.current_chapter}, confidence={self.confidence:.1%})"
        )


@dataclass
class StoryMatch:
    """
    Result of comparing two market stories.

    Attributes
    ----------
    similarity_score : float
        Overall similarity [0.0, 1.0].
    episode : MarketEpisode
        The matching episode.
    macro_alignment : float
        How similar the macro environments are.
    liquidity_alignment : float
        How similar the liquidity behaviors are.
    structure_alignment : float
        How similar the structures are.
    psychology_alignment : float
        How similar the psychologies are.
    capital_flow_alignment : float
        How similar the capital flows are.
    risk_alignment : float
        How similar the risk environments are.
    volatility_alignment : float
        How similar the volatility regimes are.
    narrative_alignment : float
        How similar the core narratives are.
    supporting_reasons : list[str]
        Why these stories match.
    differences : list[str]
        Key differences.
    historical_outcome : str
        What happened in the historical episode.
    lessons : list[str]
        Lessons from the historical episode.
    """

    similarity_score: float
    episode: MarketEpisode
    macro_alignment: float = 0.0
    liquidity_alignment: float = 0.0
    structure_alignment: float = 0.0
    psychology_alignment: float = 0.0
    capital_flow_alignment: float = 0.0
    risk_alignment: float = 0.0
    volatility_alignment: float = 0.0
    narrative_alignment: float = 0.0
    supporting_reasons: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    historical_outcome: str = ""
    lessons: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"StoryMatch({self.episode.symbol}, "
            f"similarity={self.similarity_score:.1%})"
        )


class EpisodicMemory:
    """
    Store and retrieve complete market stories.

    The EpisodicMemory is Kraitos' experience. Every significant market episode
    is stored with full context: macro, liquidity, structure, psychology,
    capital flows, and risk environment.

    Stories can be searched for similarity across multiple dimensions, enabling
    Kraitos to recognize when a current market episode matches a historical pattern.
    """

    def __init__(self) -> None:
        """Initialize the EpisodicMemory."""
        self.episodes: dict[str, MarketEpisode] = {}
        self.symbol_index: dict[str, list[str]] = {}
        self.tag_index: dict[str, list[str]] = {}
        self.chapter_index: dict[str, list[str]] = {}

    def store_episode(
        self,
        symbol: str,
        macro_environment: str,
        market_story: str,
        current_chapter: str,
        next_chapter: str,
        major_events: list[str],
        liquidity_behavior: str,
        structure_behavior: str,
        psychology: str,
        capital_flow: str,
        risk_environment: str,
        volatility_regime: str = "normal",
        duration: int = 0,
        what_happened: str = "",
        lesson: str = "",
        confidence: float = 0.7,
        tags: Optional[list[str]] = None,
        context: str = "",
    ) -> MarketEpisode:
        """
        Store a complete market episode.

        Parameters
        ----------
        symbol : str
            Market or instrument.
        macro_environment : str
            Macro context.
        market_story : str
            The narrative.
        current_chapter : str
            Current market chapter.
        next_chapter : str
            Following chapter.
        major_events : list[str]
            Key events.
        liquidity_behavior : str
            Liquidity behavior.
        structure_behavior : str
            Structure behavior.
        psychology : str
            Market psychology.
        capital_flow : str
            Capital flow direction.
        risk_environment : str
            Risk sentiment.
        volatility_regime : str, optional
            Volatility state.
        duration : int, optional
            Duration in days.
        what_happened : str, optional
            Outcome.
        lesson : str, optional
            Learned lesson.
        confidence : float, optional
            Confidence in understanding [0.0, 1.0].
        tags : list[str], optional
            Categorization tags.
        context : str, optional
            Additional context.

        Returns
        -------
        MarketEpisode
            The stored episode.
        """
        episode = MarketEpisode(
            symbol=symbol,
            macro_environment=macro_environment,
            market_story=market_story,
            current_chapter=current_chapter,
            next_chapter=next_chapter,
            major_events=major_events,
            liquidity_behavior=liquidity_behavior,
            structure_behavior=structure_behavior,
            psychology=psychology,
            capital_flow=capital_flow,
            risk_environment=risk_environment,
            volatility_regime=volatility_regime,
            duration=duration,
            what_happened=what_happened,
            lesson=lesson,
            confidence=confidence,
            tags=tags or [],
            context=context,
        )

        self.episodes[episode.episode_id] = episode

        # Update indices
        self._update_symbol_index(episode.episode_id, symbol)
        self._update_tag_index(episode.episode_id, tags or [])
        self._update_chapter_index(episode.episode_id, current_chapter)

        return episode

    def find_similar_story(
        self,
        market_story: str,
        symbol: Optional[str] = None,
        max_results: int = 5,
    ) -> list[StoryMatch]:
        """
        Find episodes with similar narratives.

        Parameters
        ----------
        market_story : str
            The story to match.
        symbol : str, optional
            Restrict to specific symbol.
        max_results : int, optional
            Maximum results to return.

        Returns
        -------
        list[StoryMatch]
            Matching episodes ranked by similarity.
        """
        matches = []
        story_lower = market_story.lower()

        for episode in self.episodes.values():
            if symbol and episode.symbol != symbol:
                continue

            # Calculate narrative alignment
            narrative_sim = self._calculate_narrative_similarity(
                market_story, episode.market_story
            )

            if narrative_sim > 0.3:
                # Full comparison
                match = self.calculate_story_similarity(market_story, episode)
                matches.append(match)

        # Sort and limit
        matches.sort(key=lambda x: -x.similarity_score)
        return matches[:max_results]

    def find_similar_macro(
        self,
        macro_environment: str,
        max_results: int = 5,
    ) -> list[StoryMatch]:
        """
        Find episodes with similar macro environments.

        Parameters
        ----------
        macro_environment : str
            The macro context to match.
        max_results : int, optional
            Maximum results.

        Returns
        -------
        list[StoryMatch]
            Matching episodes ranked by macro similarity.
        """
        matches = []

        for episode in self.episodes.values():
            macro_sim = self._calculate_text_similarity(
                macro_environment, episode.macro_environment
            )

            if macro_sim > 0.4:
                # Create simple match focusing on macro
                match = StoryMatch(
                    similarity_score=macro_sim,
                    episode=episode,
                    macro_alignment=macro_sim,
                    supporting_reasons=[
                        f"Similar macro: {macro_environment[:50]}... vs {episode.macro_environment[:50]}..."
                    ],
                )
                matches.append(match)

        matches.sort(key=lambda x: -x.similarity_score)
        return matches[:max_results]

    def find_similar_liquidity(
        self,
        liquidity_behavior: str,
        max_results: int = 5,
    ) -> list[StoryMatch]:
        """
        Find episodes with similar liquidity behavior.

        Parameters
        ----------
        liquidity_behavior : str
            The liquidity pattern to match.
        max_results : int, optional
            Maximum results.

        Returns
        -------
        list[StoryMatch]
            Matching episodes ranked by liquidity similarity.
        """
        matches = []

        for episode in self.episodes.values():
            liquidity_sim = self._calculate_text_similarity(
                liquidity_behavior, episode.liquidity_behavior
            )

            if liquidity_sim > 0.4:
                match = StoryMatch(
                    similarity_score=liquidity_sim,
                    episode=episode,
                    liquidity_alignment=liquidity_sim,
                    supporting_reasons=[
                        f"Similar liquidity: {liquidity_behavior[:50]}... vs {episode.liquidity_behavior[:50]}..."
                    ],
                )
                matches.append(match)

        matches.sort(key=lambda x: -x.similarity_score)
        return matches[:max_results]

    def find_similar_structure(
        self,
        structure_behavior: str,
        max_results: int = 5,
    ) -> list[StoryMatch]:
        """
        Find episodes with similar structure behavior.

        Parameters
        ----------
        structure_behavior : str
            The structure pattern to match.
        max_results : int, optional
            Maximum results.

        Returns
        -------
        list[StoryMatch]
            Matching episodes ranked by structure similarity.
        """
        matches = []

        for episode in self.episodes.values():
            structure_sim = self._calculate_text_similarity(
                structure_behavior, episode.structure_behavior
            )

            if structure_sim > 0.4:
                match = StoryMatch(
                    similarity_score=structure_sim,
                    episode=episode,
                    structure_alignment=structure_sim,
                    supporting_reasons=[
                        f"Similar structure: {structure_behavior[:50]}... vs {episode.structure_behavior[:50]}..."
                    ],
                )
                matches.append(match)

        matches.sort(key=lambda x: -x.similarity_score)
        return matches[:max_results]

    def find_similar_psychology(
        self,
        psychology: str,
        max_results: int = 5,
    ) -> list[StoryMatch]:
        """
        Find episodes with similar market psychology.

        Parameters
        ----------
        psychology : str
            The psychology to match.
        max_results : int, optional
            Maximum results.

        Returns
        -------
        list[StoryMatch]
            Matching episodes ranked by psychology similarity.
        """
        matches = []

        for episode in self.episodes.values():
            psychology_sim = self._calculate_text_similarity(
                psychology, episode.psychology
            )

            if psychology_sim > 0.4:
                match = StoryMatch(
                    similarity_score=psychology_sim,
                    episode=episode,
                    psychology_alignment=psychology_sim,
                    supporting_reasons=[
                        f"Similar psychology: {psychology[:50]}... vs {episode.psychology[:50]}..."
                    ],
                )
                matches.append(match)

        matches.sort(key=lambda x: -x.similarity_score)
        return matches[:max_results]

    def calculate_story_similarity(
        self,
        market_story: str,
        episode: MarketEpisode,
        macro: Optional[str] = None,
        liquidity: Optional[str] = None,
        structure: Optional[str] = None,
        psychology: Optional[str] = None,
        capital_flow: Optional[str] = None,
        risk_environment: Optional[str] = None,
        volatility_regime: Optional[str] = None,
    ) -> StoryMatch:
        """
        Calculate comprehensive story similarity.

        Compares across multiple dimensions:
        - Narrative
        - Macro environment
        - Liquidity behavior
        - Structure behavior
        - Psychology
        - Capital flow
        - Risk environment
        - Volatility regime

        Parameters
        ----------
        market_story : str
            Current narrative.
        episode : MarketEpisode
            Historical episode to compare.
        macro : str, optional
            Current macro environment.
        liquidity : str, optional
            Current liquidity behavior.
        structure : str, optional
            Current structure behavior.
        psychology : str, optional
            Current psychology.
        capital_flow : str, optional
            Current capital flow.
        risk_environment : str, optional
            Current risk environment.
        volatility_regime : str, optional
            Current volatility regime.

        Returns
        -------
        StoryMatch
            Comprehensive similarity analysis.
        """
        # Calculate individual alignments
        narrative_alignment = self._calculate_narrative_similarity(
            market_story, episode.market_story
        )

        macro_alignment = (
            self._calculate_text_similarity(macro, episode.macro_environment)
            if macro
            else 0.0
        )

        liquidity_alignment = (
            self._calculate_text_similarity(liquidity, episode.liquidity_behavior)
            if liquidity
            else 0.0
        )

        structure_alignment = (
            self._calculate_text_similarity(structure, episode.structure_behavior)
            if structure
            else 0.0
        )

        psychology_alignment = (
            self._calculate_text_similarity(psychology, episode.psychology)
            if psychology
            else 0.0
        )

        capital_flow_alignment = (
            self._calculate_text_similarity(capital_flow, episode.capital_flow)
            if capital_flow
            else 0.0
        )

        risk_alignment = (
            self._calculate_text_similarity(risk_environment, episode.risk_environment)
            if risk_environment
            else 0.0
        )

        volatility_alignment = (
            self._calculate_text_similarity(volatility_regime, episode.volatility_regime)
            if volatility_regime
            else 0.0
        )

        # Calculate weighted average
        alignments = [
            (narrative_alignment, 0.25),  # Narrative is most important
            (macro_alignment, 0.15),
            (liquidity_alignment, 0.15),
            (structure_alignment, 0.15),
            (psychology_alignment, 0.10),
            (capital_flow_alignment, 0.10),
            (risk_alignment, 0.05),
            (volatility_alignment, 0.05),
        ]

        # Only average non-zero alignments
        weighted_sum = sum(
            alignment * weight
            for alignment, weight in alignments
            if alignment > 0
        )
        total_weight = sum(
            weight for alignment, weight in alignments if alignment > 0
        )

        similarity_score = (
            weighted_sum / total_weight if total_weight > 0 else 0.0
        )

        # Generate supporting reasons
        reasons = self._generate_supporting_reasons(
            narrative_alignment,
            macro_alignment,
            liquidity_alignment,
            structure_alignment,
            psychology_alignment,
            capital_flow_alignment,
            risk_alignment,
            volatility_alignment,
        )

        # Generate differences
        differences = self._generate_differences(
            market_story,
            episode,
            macro,
            liquidity,
            structure,
            psychology,
            capital_flow,
            risk_environment,
            volatility_regime,
        )

        return StoryMatch(
            similarity_score=similarity_score,
            episode=episode,
            macro_alignment=macro_alignment,
            liquidity_alignment=liquidity_alignment,
            structure_alignment=structure_alignment,
            psychology_alignment=psychology_alignment,
            capital_flow_alignment=capital_flow_alignment,
            risk_alignment=risk_alignment,
            volatility_alignment=volatility_alignment,
            narrative_alignment=narrative_alignment,
            supporting_reasons=reasons,
            differences=differences,
            historical_outcome=episode.what_happened,
            lessons=[episode.lesson] if episode.lesson else [],
        )

    def retrieve_best_matches(
        self,
        market_story: str,
        macro: str,
        liquidity: str,
        structure: str,
        psychology: str,
        capital_flow: str,
        risk_environment: str,
        volatility_regime: str = "normal",
        max_results: int = 5,
    ) -> list[StoryMatch]:
        """
        Retrieve best matching episodes across all dimensions.

        Parameters
        ----------
        market_story : str
            Current narrative.
        macro : str
            Current macro environment.
        liquidity : str
            Current liquidity behavior.
        structure : str
            Current structure behavior.
        psychology : str
            Current psychology.
        capital_flow : str
            Current capital flow.
        risk_environment : str
            Current risk environment.
        volatility_regime : str, optional
            Current volatility regime.
        max_results : int, optional
            Maximum results.

        Returns
        -------
        list[StoryMatch]
            Best matching episodes ranked by overall similarity.
        """
        matches = []

        for episode in self.episodes.values():
            match = self.calculate_story_similarity(
                market_story=market_story,
                episode=episode,
                macro=macro,
                liquidity=liquidity,
                structure=structure,
                psychology=psychology,
                capital_flow=capital_flow,
                risk_environment=risk_environment,
                volatility_regime=volatility_regime,
            )

            if match.similarity_score > 0.4:
                matches.append(match)

        # Sort by similarity
        matches.sort(key=lambda x: -x.similarity_score)
        return matches[:max_results]

    def _calculate_narrative_similarity(self, story1: str, story2: str) -> float:
        """Calculate similarity between narratives using key phrases."""
        if not story1 or not story2:
            return 0.0

        words1 = set(story1.lower().split())
        words2 = set(story2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        if not text1 or not text2:
            return 0.0

        # Simple keyword overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _generate_supporting_reasons(
        self,
        narrative: float,
        macro: float,
        liquidity: float,
        structure: float,
        psychology: float,
        capital_flow: float,
        risk: float,
        volatility: float,
    ) -> list[str]:
        """Generate reasons why stories match."""
        reasons = []

        if narrative > 0.6:
            reasons.append("Core narrative is very similar")
        elif narrative > 0.4:
            reasons.append("Narrative has significant overlap")

        if macro > 0.6:
            reasons.append("Macro environments are similar")

        if liquidity > 0.6:
            reasons.append("Liquidity behavior patterns match")

        if structure > 0.6:
            reasons.append("Price structure behavior is similar")

        if psychology > 0.6:
            reasons.append("Market psychology matches")

        if capital_flow > 0.5:
            reasons.append("Capital flow direction is similar")

        if risk > 0.5:
            reasons.append("Risk environment is comparable")

        return reasons

    def _generate_differences(
        self,
        market_story: str,
        episode: MarketEpisode,
        macro: Optional[str],
        liquidity: Optional[str],
        structure: Optional[str],
        psychology: Optional[str],
        capital_flow: Optional[str],
        risk_environment: Optional[str],
        volatility_regime: Optional[str],
    ) -> list[str]:
        """Generate key differences between stories."""
        differences = []

        # Symbol difference
        if episode.symbol:
            differences.append(
                f"Current story involves different markets/instruments"
            )

        # Macro difference
        if macro and macro != episode.macro_environment:
            differences.append("Macro environment differs")

        # Liquidity difference
        if liquidity and liquidity != episode.liquidity_behavior:
            differences.append("Liquidity conditions are different")

        # Psychology difference
        if psychology and psychology != episode.psychology:
            differences.append("Market psychology differs")

        # Risk environment difference
        if risk_environment and risk_environment != episode.risk_environment:
            differences.append("Risk environment is different")

        # Duration difference (if applicable)
        if episode.duration > 0:
            differences.append(
                f"Historical episode lasted {episode.duration} days"
            )

        return differences[:5]  # Return top 5 differences

    def _update_symbol_index(self, episode_id: str, symbol: str) -> None:
        """Update symbol index."""
        if symbol not in self.symbol_index:
            self.symbol_index[symbol] = []

        self.symbol_index[symbol].append(episode_id)

    def _update_tag_index(self, episode_id: str, tags: list[str]) -> None:
        """Update tag index."""
        for tag in tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = []

            self.tag_index[tag].append(episode_id)

    def _update_chapter_index(self, episode_id: str, chapter: str) -> None:
        """Update chapter index."""
        if chapter not in self.chapter_index:
            self.chapter_index[chapter] = []

        self.chapter_index[chapter].append(episode_id)

    def get_episodes_by_symbol(self, symbol: str) -> list[MarketEpisode]:
        """Get all episodes for a specific symbol."""
        if symbol not in self.symbol_index:
            return []

        episode_ids = self.symbol_index[symbol]
        return [self.episodes[eid] for eid in episode_ids if eid in self.episodes]

    def get_episodes_by_chapter(self, chapter: str) -> list[MarketEpisode]:
        """Get all episodes for a specific chapter."""
        if chapter not in self.chapter_index:
            return []

        episode_ids = self.chapter_index[chapter]
        return [self.episodes[eid] for eid in episode_ids if eid in self.episodes]

    def get_summary(self) -> dict:
        """Get summary statistics."""
        return {
            "total_episodes": len(self.episodes),
            "symbols_tracked": len(self.symbol_index),
            "tags_used": len(self.tag_index),
            "chapters_recorded": len(self.chapter_index),
            "avg_confidence": (
                sum(e.confidence for e in self.episodes.values()) / len(self.episodes)
                if self.episodes
                else 0.0
            ),
        }

    def __str__(self) -> str:
        """Return a human-readable representation."""
        summary = self.get_summary()
        return (
            f"EpisodicMemory({summary['total_episodes']} episodes, "
            f"{summary['symbols_tracked']} symbols)"
        )
