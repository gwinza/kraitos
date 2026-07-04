"""
ExecutiveCortex: Decide how Kraitos should express its understanding.

The ExecutiveCortex does NOT generate signals.
It does NOT blindly output BUY or SELL.
It chooses the correct expression of the current market understanding.

Allowed expressions:
- WAIT: Insufficient clarity. Do nothing.
- OBSERVE_MORE: Story promising but missing critical evidence.
- PREPARE_LONG: Conditions developing for potential long entry.
- PREPARE_SHORT: Conditions developing for potential short entry.
- PROBE_LONG: Small position to test hypothesis.
- PROBE_SHORT: Small position to test hypothesis.
- ENTER_LONG: High conviction entry signal.
- ENTER_SHORT: High conviction entry signal.
- REDUCE_RISK: Uncertainty rising. Reduce exposure.
- HOLD: Maintain current exposure. Story intact.
- EXIT: Story invalidated. Exit position.

The ExecutiveCortex explains every decision in plain English.
It never calls a broker. It never places orders.
It only decides the best StoryExpression.
"""

from dataclasses import dataclass, field
from kraitos.core.shared_world_model import SharedWorldModel
from kraitos.core.market_story import MarketStory
from kraitos.brain.conviction_engine import ConvictionReport
from kraitos.brain.simulation_engine import PossibleMarketFutures
from kraitos.brain.next_chapter_engine import NextChapter


# Valid expressions
VALID_EXPRESSIONS = {
    "WAIT",
    "OBSERVE_MORE",
    "PREPARE_LONG",
    "PREPARE_SHORT",
    "PROBE_LONG",
    "PROBE_SHORT",
    "ENTER_LONG",
    "ENTER_SHORT",
    "REDUCE_RISK",
    "HOLD",
    "EXIT",
}

# Risk postures
RISK_POSTURES = {
    "DEFENSIVE": "Capital preservation priority.",
    "CONSERVATIVE": "Low risk tolerance.",
    "NEUTRAL": "Balanced risk and reward.",
    "AGGRESSIVE": "Willing to take tactical risk.",
    "EXTREME": "Maximum conviction. High risk accepted.",
}


@dataclass
class ExecutiveDecision:
    """
    A decision on how Kraitos should express its market understanding.

    This is NOT a trade signal. It is a framework for understanding
    and managing market exposure based on narrative quality and conviction.

    Attributes
    ----------
    expression : str
        How Kraitos should express itself (one of VALID_EXPRESSIONS).
    reason : str
        Plain English explanation of why this expression was chosen.
    confidence : float
        Confidence in this expression [0.0, 1.0].
    risk_posture : str
        Current recommended risk posture (one of RISK_POSTURES).
    required_conditions : list[str]
        Conditions that must be met for this expression to remain valid.
    invalidation : str
        Specific condition that would invalidate this expression.
    notes : list[str]
        Additional context and warnings.
    """

    expression: str
    reason: str
    confidence: float = 0.5
    risk_posture: str = "NEUTRAL"
    required_conditions: list[str] = field(default_factory=list)
    invalidation: str = ""
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the decision on creation."""
        if self.expression not in VALID_EXPRESSIONS:
            raise ValueError(
                f"Invalid expression: '{self.expression}'. "
                f"Must be one of: {', '.join(sorted(VALID_EXPRESSIONS))}"
            )

        if self.risk_posture not in RISK_POSTURES:
            raise ValueError(
                f"Invalid risk_posture: '{self.risk_posture}'. "
                f"Must be one of: {', '.join(sorted(RISK_POSTURES.keys()))}"
            )

        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"ExecutiveDecision({self.expression}, "
            f"confidence={self.confidence:.1%}, "
            f"posture={self.risk_posture})"
        )


class ExecutiveCortex:
    """
    Decide how Kraitos should express its market understanding.

    The ExecutiveCortex receives comprehensive market analysis and produces
    a clear decision on how Kraitos should behave: WAIT, OBSERVE_MORE,
    PREPARE, PROBE, ENTER, HOLD, REDUCE_RISK, or EXIT.

    This is NOT a trading system. It is a narrative management system.
    """

    def __init__(
        self,
        world_model: SharedWorldModel | None = None,
        market_story: MarketStory | None = None,
        conviction_report: ConvictionReport | None = None,
        simulation_results: PossibleMarketFutures | None = None,
        next_chapter: NextChapter | None = None,
        current_position: str | None = None,
    ) -> None:
        """
        Initialize the ExecutiveCortex.

        Parameters
        ----------
        world_model : SharedWorldModel, optional
            Current shared market understanding.
        market_story : MarketStory, optional
            Current market narrative.
        conviction_report : ConvictionReport, optional
            Current conviction in understanding.
        simulation_results : PossibleMarketFutures, optional
            Simulated market futures.
        next_chapter : NextChapter, optional
            Predicted next market phase.
        current_position : str, optional
            Current position status (FLAT, LONG, SHORT).
        """
        self.world_model = world_model
        self.market_story = market_story
        self.conviction_report = conviction_report
        self.simulation_results = simulation_results
        self.next_chapter = next_chapter
        self.current_position = current_position or "FLAT"

    def decide(
        self,
        world_model: SharedWorldModel,
        market_story: MarketStory,
        conviction_report: ConvictionReport,
        simulation_results: PossibleMarketFutures,
        next_chapter: NextChapter,
        current_position: str | None = None,
    ) -> ExecutiveDecision:
        """
        Decide how Kraitos should express its understanding.

        Parameters
        ----------
        world_model : SharedWorldModel
            Current shared market understanding.
        market_story : MarketStory
            Current market narrative.
        conviction_report : ConvictionReport
            Current conviction in understanding.
        simulation_results : PossibleMarketFutures
            Simulated market futures.
        next_chapter : NextChapter
            Predicted next market phase.
        current_position : str, optional
            Current position (FLAT, LONG, SHORT).

        Returns
        -------
        ExecutiveDecision
            Decision on how to express market understanding.
        """
        self.world_model = world_model
        self.market_story = market_story
        self.conviction_report = conviction_report
        self.simulation_results = simulation_results
        self.next_chapter = next_chapter
        self.current_position = current_position or "FLAT"

        # Decision hierarchy
        # 1. Check for invalidation (must EXIT)
        if self._check_exit_condition():
            return self._make_exit_decision()

        # 2. Check for high uncertainty (must REDUCE_RISK or WAIT)
        if self._check_reduce_risk_condition():
            return self._make_reduce_risk_decision()

        # 3. Check for insufficient data (must OBSERVE_MORE or WAIT)
        if self._check_observe_more_condition():
            return self._make_observe_more_decision()

        # 4. Check for entry conditions (can PREPARE, PROBE, or ENTER)
        if self._check_entry_condition():
            if self.current_position == "FLAT":
                return self._make_entry_decision()
            else:
                return self._make_hold_decision()

        # 5. Default to WAIT
        return self._make_wait_decision()

    def _check_exit_condition(self) -> bool:
        """Check if current story is invalidated."""
        if self.current_position == "FLAT":
            return False

        # Exit if contradictions are severe
        if (
            self.conviction_report.contradiction_score > 0.6
            and self.conviction_report.confidence < 0.4
        ):
            return True

        # Exit if confidence drops sharply
        if self.conviction_report.confidence < 0.2:
            return True

        # Exit if next chapter explicitly invalidates current position
        if self.next_chapter and self.current_position == "LONG":
            invalidating_chapters = [
                "Capitulation",
                "Mean Reversion",
                "Distribution",
            ]
            if self.next_chapter.chapter_name in invalidating_chapters:
                if self.conviction_report.confidence < 0.5:
                    return True

        if self.next_chapter and self.current_position == "SHORT":
            invalidating_chapters = ["Expansion", "Trend Continuation", "Breakout"]
            if self.next_chapter.chapter_name in invalidating_chapters:
                if self.conviction_report.confidence < 0.5:
                    return True

        return False

    def _check_reduce_risk_condition(self) -> bool:
        """Check if uncertainty is rising while exposed."""
        if self.current_position == "FLAT":
            return False

        # Reduce risk if uncertainty rises
        if self.conviction_report.uncertainty > 0.7:
            return True

        # Reduce risk if agreement score drops
        if self.conviction_report.agreement_score < 0.3:
            return True

        # Reduce risk if many missing information gaps
        if len(self.conviction_report.missing_information) > 3:
            return True

        return False

    def _check_observe_more_condition(self) -> bool:
        """Check if more evidence is needed."""
        # Observe more if many unknowns
        if len(self.world_model.unknowns) > len(self.world_model.evidence_summary):
            return True

        # Observe more if conviction is low but trending up
        if (
            self.conviction_report.conviction_level == "Low"
            and self.conviction_report.story_quality < 0.4
        ):
            return True

        # Observe more if council count is low (< 3)
        if self.conviction_report.council_count < 3:
            return True

        return False

    def _check_entry_condition(self) -> bool:
        """Check if conditions support entry or holding."""
        # ENTER requires high conviction
        if self.conviction_report.conviction_level not in [
            "High",
            "Very High",
        ]:
            return False

        # ENTER requires clear next chapter
        if not self.next_chapter:
            return False

        # ENTER requires acceptable uncertainty
        if self.conviction_report.uncertainty > 0.6:
            return False

        # ENTER requires no fatal contradictions
        if self.conviction_report.contradiction_score > 0.5:
            return False

        # ENTER requires good story quality
        if self.conviction_report.story_quality < 0.6:
            return False

        return True

    def _make_wait_decision(self) -> ExecutiveDecision:
        """Create a WAIT decision."""
        return ExecutiveDecision(
            expression="WAIT",
            reason=(
                "Insufficient market clarity. Current narrative is incomplete or unclear. "
                "Awaiting better definition before any action."
            ),
            confidence=0.3,
            risk_posture="DEFENSIVE",
            required_conditions=[
                "Conviction rises to 'Moderate' or higher",
                "Story quality improves",
                "Council agreement increases",
            ],
            invalidation="Clear market structure emerges",
            notes=[
                "This is not a bearish view. It is an uncertainty acknowledgment.",
                "Waiting is appropriate when the cost of being wrong exceeds potential gain.",
            ],
        )

    def _make_observe_more_decision(self) -> ExecutiveDecision:
        """Create an OBSERVE_MORE decision."""
        missing_info = self.conviction_report.missing_information[:3]
        conditions = [f"Resolve: {info}" for info in missing_info]

        return ExecutiveDecision(
            expression="OBSERVE_MORE",
            reason=(
                "Story is developing but critical information is missing. "
                "Continuing observation to gather complete picture before commitment."
            ),
            confidence=0.4,
            risk_posture="CONSERVATIVE",
            required_conditions=conditions,
            invalidation=self.world_model.unknowns[0]
            if self.world_model.unknowns
            else "Unknown resolved",
            notes=[
                f"Critical gaps: {', '.join(missing_info)}",
                "New evidence may significantly change the narrative.",
            ],
        )

    def _make_reduce_risk_decision(self) -> ExecutiveDecision:
        """Create a REDUCE_RISK decision."""
        return ExecutiveDecision(
            expression="REDUCE_RISK",
            reason=(
                f"Uncertainty rising while exposed. "
                f"Current uncertainty: {self.conviction_report.uncertainty:.1%}. "
                "Reducing position size to protect capital."
            ),
            confidence=0.7,
            risk_posture="DEFENSIVE",
            required_conditions=[
                "Uncertainty stabilizes or declines",
                "Agreement score recovers",
            ],
            invalidation=(
                "Uncertainty drops below 0.5 and conviction improves"
            ),
            notes=[
                "This is risk management, not a prediction.",
                "Smaller position size allows for continued participation if story improves.",
            ],
        )

    def _make_entry_decision(self) -> ExecutiveDecision:
        """Create an ENTER decision."""
        direction = "long"
        if self.next_chapter.chapter_name in [
            "Capitulation",
            "Mean Reversion",
            "Distribution",
        ]:
            direction = "short"

        return ExecutiveDecision(
            expression=f"ENTER_{direction.upper()}",
            reason=(
                f"High conviction in '{self.next_chapter.chapter_name}' chapter. "
                f"Story is clear, councils agree, and conditions support action. "
                f"Conviction: {self.conviction_report.conviction_level}."
            ),
            confidence=self.next_chapter.confidence,
            risk_posture="AGGRESSIVE",
            required_conditions=self.next_chapter.key_watch_points,
            invalidation=self.next_chapter.invalidated_by[0]
            if self.next_chapter.invalidated_by
            else "Unknown",
            notes=[
                f"Next chapter: {self.next_chapter.chapter_name}",
                f"Duration estimate: {self.next_chapter.estimated_duration}",
                f"Story quality: {self.conviction_report.story_quality:.1%}",
            ],
        )

    def _make_probe_decision(self) -> ExecutiveDecision:
        """Create a PROBE decision."""
        direction = "long"
        if self.next_chapter.chapter_name in [
            "Capitulation",
            "Mean Reversion",
            "Distribution",
        ]:
            direction = "short"

        return ExecutiveDecision(
            expression=f"PROBE_{direction.upper()}",
            reason=(
                f"Story is promising but incomplete. "
                f"Testing '{self.next_chapter.chapter_name}' hypothesis with small position. "
                f"Awaiting additional confirmation before scaling."
            ),
            confidence=self.next_chapter.confidence - 0.2,
            risk_posture="CONSERVATIVE",
            required_conditions=[
                "Monitor key watch points closely",
                "Ready to exit if story changes",
            ],
            invalidation=self.next_chapter.invalidated_by[0]
            if self.next_chapter.invalidated_by
            else "Story invalidated",
            notes=[
                f"Small position to validate hypothesis",
                f"Next chapter: {self.next_chapter.chapter_name}",
                "Be prepared to quickly reduce or exit.",
            ],
        )

    def _make_hold_decision(self) -> ExecutiveDecision:
        """Create a HOLD decision."""
        return ExecutiveDecision(
            expression="HOLD",
            reason=(
                f"Current story remains intact. "
                f"'{self.next_chapter.chapter_name}' chapter confirms position alignment. "
                "Maintaining current exposure."
            ),
            confidence=self.conviction_report.confidence,
            risk_posture="NEUTRAL",
            required_conditions=self.next_chapter.key_watch_points,
            invalidation=self.next_chapter.invalidated_by[0]
            if self.next_chapter.invalidated_by
            else "Story invalidated",
            notes=[
                f"Current story: {self.market_story.complete_story[:100]}...",
                f"Conviction: {self.conviction_report.conviction_level}",
                "Watch for invalidation criteria.",
            ],
        )

    def _make_exit_decision(self) -> ExecutiveDecision:
        """Create an EXIT decision."""
        return ExecutiveDecision(
            expression="EXIT",
            reason=(
                f"Current narrative is invalidated. "
                f"Contradiction score: {self.conviction_report.contradiction_score:.1%}. "
                f"Confidence: {self.conviction_report.confidence:.1%}. "
                "Story no longer supports current position. Exiting."
            ),
            confidence=0.9,
            risk_posture="DEFENSIVE",
            required_conditions=[],
            invalidation="Story re-validates unexpectedly",
            notes=[
                "This is rule-based risk management.",
                "Exit does not predict future direction.",
                "Capital preserved for next opportunity.",
            ],
        )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        status = "ready" if self.world_model and self.market_story else "idle"
        return f"ExecutiveCortex({status})"
