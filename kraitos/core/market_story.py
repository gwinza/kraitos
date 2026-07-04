"""
MarketStory: Narrative translation of market evidence.

This class converts evidence into plain-English explanation.
It reads like an analyst report: observational, nuanced, uncertain.

The purpose is explanation, not prediction.
No trading language. No signals. No directives.
"""

from dataclasses import dataclass, field


@dataclass
class MarketStory:
    """
    A coherent narrative explanation of market behavior.

    The MarketStory translates council evidence into human language.
    It is written from the perspective of an analyst observing and explaining
    what is happening, why it matters, and what uncertainty remains.

    Language is careful. No trading terminology.
    No BUY, SELL, ENTRY, EXIT, SIGNAL.
    Only explanation.

    Attributes
    ----------
    complete_story : str
        The full narrative explaining the current market situation.
    current_chapter : str
        The immediate phase or regime within the larger story.
    dominant_theme : str
        The central theme or tension driving market behavior.
    supporting_evidence : list[str]
        Facts and observations that support this narrative.
    contradictory_evidence : list[str]
        Evidence that complicates or contradicts the narrative.
    alternative_stories : list[str]
        Alternative narratives that could explain the same facts.
    possible_next_chapters : list[str]
        Plausible developments that could unfold from here.
    confidence : float
        How confident in this narrative? [0.0, 1.0]
    uncertainty : float
        How much remains unexplained or unknown? [0.0, 1.0]
    """

    complete_story: str
    current_chapter: str
    dominant_theme: str
    supporting_evidence: list[str] = field(default_factory=list)
    contradictory_evidence: list[str] = field(default_factory=list)
    alternative_stories: list[str] = field(default_factory=list)
    possible_next_chapters: list[str] = field(default_factory=list)
    confidence: float = 0.5
    uncertainty: float = 0.5

    def __post_init__(self) -> None:
        """
        Validate the story on creation.

        Raises
        ------
        ValueError
            If required narrative fields are empty.
        ValueError
            If confidence or uncertainty are outside [0.0, 1.0].
        ValueError
            If story contains forbidden trading language.
        """
        # Validate required fields
        if not self.complete_story or not self.complete_story.strip():
            raise ValueError("complete_story cannot be empty.")

        if not self.current_chapter or not self.current_chapter.strip():
            raise ValueError("current_chapter cannot be empty.")

        if not self.dominant_theme or not self.dominant_theme.strip():
            raise ValueError("dominant_theme cannot be empty.")

        # Validate confidence and uncertainty
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

        if not (0.0 <= self.uncertainty <= 1.0):
            raise ValueError(
                f"uncertainty must be between 0.0 and 1.0, got {self.uncertainty}."
            )

        # Validate no forbidden trading language
        self._validate_no_trading_language()

    def _validate_no_trading_language(self) -> None:
        """
        Check that the story does not contain trading directives.

        Forbidden terms: BUY, SELL, ENTRY, EXIT, SIGNAL, LONG, SHORT, GO, POSITION

        Raises
        ------
        ValueError
            If forbidden trading language is detected.
        """
        forbidden_terms = (
            "BUY",
            "SELL",
            "ENTRY",
            "EXIT",
            "SIGNAL",
            "LONG",
            "SHORT",
            "GO LONG",
            "GO SHORT",
            "POSITION",
        )

        text_upper = self.complete_story.upper()

        for term in forbidden_terms:
            if term in text_upper:
                raise ValueError(
                    f"Story contains forbidden trading language: '{term}'. "
                    f"MarketStory must explain, not prescribe. "
                    f"Use analytical language only."
                )

    def summary(self) -> str:
        """
        Return a concise summary of the story.

        Combines complete story and current chapter into one paragraph.

        Returns
        -------
        str
            Brief narrative summary.
        """
        return f"{self.complete_story}\n\n[Current Phase: {self.current_chapter}]"

    def short_summary(self) -> str:
        """
        Return a very short summary (one or two sentences).

        Focuses on dominant theme and current chapter.

        Returns
        -------
        str
            Ultra-brief narrative.
        """
        return (
            f"Theme: {self.dominant_theme}. "
            f"Current phase: {self.current_chapter}. "
            f"Confidence: {self.confidence:.1%}."
        )

    def long_summary(self) -> str:
        """
        Return a comprehensive summary including evidence and alternatives.

        Returns
        -------
        str
            Full narrative with supporting detail.
        """
        lines = [
            "=== MARKET STORY ===",
            "",
            self.complete_story,
            "",
            f"Theme: {self.dominant_theme}",
            f"Current Chapter: {self.current_chapter}",
            f"Confidence: {self.confidence:.1%} | Uncertainty: {self.uncertainty:.1%}",
            "",
        ]

        if self.supporting_evidence:
            lines.append("Supporting Evidence:")
            for evidence in self.supporting_evidence:
                lines.append(f"  • {evidence}")
            lines.append("")

        if self.contradictory_evidence:
            lines.append("Complicating Evidence:")
            for evidence in self.contradictory_evidence:
                lines.append(f"  • {evidence}")
            lines.append("")

        if self.alternative_stories:
            lines.append("Alternative Narratives:")
            for alt in self.alternative_stories:
                lines.append(f"  • {alt}")
            lines.append("")

        if self.possible_next_chapters:
            lines.append("Possible Next Chapters:")
            for next_ch in self.possible_next_chapters:
                lines.append(f"  • {next_ch}")
            lines.append("")

        return "\n".join(lines)

    def __str__(self) -> str:
        """Return a human-readable representation of this story."""
        return (
            f"MarketStory(theme='{self.dominant_theme[:50]}...', "
            f"confidence={self.confidence:.2f}, uncertainty={self.uncertainty:.2f})"
        )
