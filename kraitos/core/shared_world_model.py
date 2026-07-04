"""
SharedWorldModel: The unified picture of market reality.

This is Kraitos' current understanding of what is happening in the market.
It is NOT a trading signal. It is a story—a coherent narrative assembled
from evidence contributed by councils.

The Shared World Model evolves as new observations arrive.
It holds confidence and uncertainty simultaneously.
"""

from dataclasses import dataclass, field
from datetime import datetime
from kraitos.core.council_report import CouncilReport


@dataclass
class SharedWorldModel:
    """
    The unified, evolving understanding of market reality.

    This model represents what Kraitos currently believes is happening in a market.
    It is built from evidence contributed by councils. It is not a prediction.
    It is a story—a coherent narrative about the present and immediate future.

    Confidence and uncertainty are separate dimensions. High confidence does not
    mean low uncertainty. The model can be both confident and uncertain about
    different aspects of the market.

    Attributes
    ----------
    symbol : str
        The market instrument (e.g., "EURUSD", "BTC/USD").
    timeframe : str
        The time horizon of this understanding (e.g., "1H", "4H", "1D").
    timestamp : datetime
        When this model was created or last updated.
    current_story : str
        Plain-English narrative of what is happening in the market right now.
    current_chapter : str
        The immediate phase or regime of the current story.
    dominant_next_chapter : str
        What the model believes is most likely to happen next.
    possible_next_chapters : list[str]
        Alternative next chapters, ranked by plausibility.
    confidence : float
        How confident is this model in its story? [0.0, 1.0]
    uncertainty : float
        How much unknown/unknowable remains? [0.0, 1.0]
    council_reports : list[CouncilReport]
        All council reports that contributed to this model.
    contradictions : list[str]
        Conflicts or tensions in the evidence.
    unknowns : list[str]
        Known gaps in understanding.
    evidence_summary : list[str]
        Key pieces of evidence supporting the story.
    """

    symbol: str
    timeframe: str
    timestamp: datetime
    current_story: str = ""
    current_chapter: str = ""
    dominant_next_chapter: str = ""
    possible_next_chapters: list[str] = field(default_factory=list)
    confidence: float = 0.5
    uncertainty: float = 0.5
    council_reports: list[CouncilReport] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    evidence_summary: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Validate the Shared World Model on creation.

        Raises
        ------
        ValueError
            If confidence or uncertainty are outside [0.0, 1.0].
        ValueError
            If symbol or timeframe are empty.
        """
        # Validate symbol and timeframe
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty.")

        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty.")

        # Validate confidence and uncertainty are in [0.0, 1.0]
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

        if not (0.0 <= self.uncertainty <= 1.0):
            raise ValueError(
                f"uncertainty must be between 0.0 and 1.0, got {self.uncertainty}."
            )

    def add_report(self, report: CouncilReport) -> None:
        """
        Add a council report to this model.

        Parameters
        ----------
        report : CouncilReport
            The council report to add.

        Raises
        ------
        TypeError
            If report is not a CouncilReport.
        """
        if not isinstance(report, CouncilReport):
            raise TypeError(
                f"Expected CouncilReport, got {type(report).__name__}."
            )

        self.council_reports.append(report)

    def summarize_evidence(self) -> list[str]:
        """
        Compile evidence summary from all council reports.

        Returns
        -------
        list[str]
            Summary of supporting evidence from all councils.
        """
        summary = []
        for report in self.council_reports:
            if report.supporting_evidence:
                summary.extend(report.supporting_evidence)

        self.evidence_summary = summary
        return summary

    def summarize_contradictions(self) -> list[str]:
        """
        Compile contradictions from all council reports.

        Returns
        -------
        list[str]
            All contradictions or tensions in the evidence.
        """
        contradictions = []
        for report in self.council_reports:
            if report.contradictory_evidence:
                contradictions.extend(report.contradictory_evidence)

        self.contradictions = contradictions
        return contradictions

    def summarize_unknowns(self) -> list[str]:
        """
        Compile known unknowns from all council reports.

        Returns
        -------
        list[str]
            All gaps and uncertainties identified by councils.
        """
        unknowns = []
        for report in self.council_reports:
            if report.uncertainty:
                unknowns.extend(report.uncertainty)

        self.unknowns = unknowns
        return unknowns

    def overall_state(self) -> dict[str, str | float]:
        """
        Return a summary of the current understanding state.

        This is the current mental picture. It is not actionable until
        translated into a Trade Thesis by the Story Expression engine.

        Returns
        -------
        dict[str, str | float]
            Dictionary containing:
            - "story": the current narrative
            - "chapter": the current phase
            - "confidence": how sure we are [0.0, 1.0]
            - "uncertainty": how much remains unknown [0.0, 1.0]
            - "next": the dominant next chapter
        """
        return {
            "story": self.current_story,
            "chapter": self.current_chapter,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "next": self.dominant_next_chapter,
        }

    def __str__(self) -> str:
        """Return a human-readable representation of this model."""
        return (
            f"SharedWorldModel({self.symbol} {self.timeframe} @ {self.timestamp}) "
            f"confidence={self.confidence:.2f} uncertainty={self.uncertainty:.2f} "
            f"story='{self.current_story[:50]}...'"
        )
