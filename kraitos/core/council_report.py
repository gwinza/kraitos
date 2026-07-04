"""
CouncilReport: Evidence contribution from market analysis councils.

Councils observe the market and contribute evidence to the Shared World Model.
They do not make trading decisions. They do not output signals.
They only describe what they see and how it fits the story.
"""

from dataclasses import dataclass, field
from kraitos.core.constitution import ConstitutionViolation, validate_action


@dataclass
class CouncilReport:
    """
    A council's contribution of evidence to the Shared World Model.

    A council observes market conditions and contributes a story about what
    those conditions mean. Councils are specialists—they see part of the picture.
    The Shared World Model assembles their reports into a coherent understanding.

    No council may output trading instructions or gatekeeping decisions.
    They may only contribute evidence and narrative interpretation.

    Attributes
    ----------
    council_name : str
        Name of the council providing this report (e.g., "LiquidityCouncil").
    observations : list[str]
        Raw market observations that led to this report.
    story_contribution : str
        Plain-English description of what this council sees in the story.
        Must not contain trading instructions or gatekeeping actions.
    supporting_evidence : list[str]
        Evidence that supports this council's interpretation.
    contradictory_evidence : list[str]
        Evidence that contradicts or complicates this interpretation.
    uncertainty : list[str]
        Known unknowns and gaps in this council's knowledge.
    confidence : float
        How confident is this council in its contribution? [0.0, 1.0]
    possible_next_chapters : list[str]
        What might happen next according to this council's narrative?
    """

    council_name: str
    observations: list[str] = field(default_factory=list)
    story_contribution: str = ""
    supporting_evidence: list[str] = field(default_factory=list)
    contradictory_evidence: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    confidence: float = 0.5
    possible_next_chapters: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Validate the council report on creation.

        Raises
        ------
        ValueError
            If council_name is empty.
        ValueError
            If confidence is not in [0.0, 1.0].
        ConstitutionViolation
            If story_contribution contains forbidden actions.
        """
        # Rule 1: council_name cannot be empty
        if not self.council_name or not self.council_name.strip():
            raise ValueError("council_name cannot be empty.")

        # Rule 2: confidence must be in [0.0, 1.0]
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

        # Rule 3: story_contribution must not contain forbidden actions
        if self.story_contribution:
            self._validate_story_contribution()

    def _validate_story_contribution(self) -> None:
        """
        Check that story_contribution does not contain forbidden actions.

        Forbidden actions: BUY, SELL, LONG, SHORT, ENTER, EXIT, VETO, APPROVE, REJECT, BLOCK

        Raises
        ------
        ConstitutionViolation
            If story_contribution contains a forbidden action.
        """
        forbidden = (
            "BUY",
            "SELL",
            "LONG",
            "SHORT",
            "ENTER",
            "EXIT",
            "VETO",
            "APPROVE",
            "REJECT",
            "BLOCK",
        )

        text_upper = self.story_contribution.upper()
        for action in forbidden:
            if action in text_upper:
                raise ConstitutionViolation(
                    f"Council '{self.council_name}' story_contribution contains "
                    f"forbidden action '{action}'. "
                    f"Councils may only contribute evidence and narrative, "
                    f"not trading instructions or gatekeeping decisions."
                )

    def __str__(self) -> str:
        """Return a human-readable representation of this council report."""
        return (
            f"CouncilReport(council='{self.council_name}', "
            f"confidence={self.confidence:.2f}, "
            f"contribution='{self.story_contribution[:60]}...')"
        )
