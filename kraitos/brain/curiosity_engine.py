"""
CuriosityEngine: Prevent Kraitos from jumping to conclusions.

The CuriosityEngine asks:
- What is missing?
- What could we be misunderstanding?
- What evidence would change the story?
- What alternative explanation still survives?

It protects Kraitos from false certainty by identifying gaps,
contradictions, and competing hypotheses.

This engine never outputs BUY or SELL.
It only protects against premature conclusions.
"""

from dataclasses import dataclass, field
from kraitos.core.shared_world_model import SharedWorldModel
from kraitos.core.market_story import MarketStory
from kraitos.brain.simulation_engine import PossibleMarketFutures


@dataclass
class CuriosityReport:
    """
    A report on gaps, unknowns, and alternative explanations.

    This report identifies what is missing, what could be misunderstood,
    what evidence would change the story, and what alternative explanations
    still survive the current evidence.

    Attributes
    ----------
    unanswered_questions : list[str]
        Critical questions that remain unanswered.
    missing_evidence : list[str]
        Evidence that would significantly clarify the story.
    alternative_explanations : list[str]
        Alternative hypotheses that are still viable.
    evidence_needed_next : list[str]
        Specific observations that would answer key questions.
    curiosity_level : float
        How much more we need to know [0.0, 1.0].
        0.0 = Story fully understood. 1.0 = Story highly uncertain.
    should_delay_action : bool
        True if missing evidence is critical for decision-making.
    reason : str
        Explanation of curiosity assessment.
    high_impact_uncertainties : list[str]
        Unknowns that would significantly change the narrative if resolved.
    false_certainty_risks : list[str]
        Risks of acting on incomplete information.
    """

    unanswered_questions: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    alternative_explanations: list[str] = field(default_factory=list)
    evidence_needed_next: list[str] = field(default_factory=list)
    curiosity_level: float = 0.5
    should_delay_action: bool = False
    reason: str = ""
    high_impact_uncertainties: list[str] = field(default_factory=list)
    false_certainty_risks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the report on creation."""
        if not (0.0 <= self.curiosity_level <= 1.0):
            raise ValueError(
                f"curiosity_level must be between 0.0 and 1.0, "
                f"got {self.curiosity_level}."
            )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"CuriosityReport(curiosity={self.curiosity_level:.1%}, "
            f"delay_action={self.should_delay_action}, "
            f"questions={len(self.unanswered_questions)})"
        )


class CuriosityEngine:
    """
    Identify gaps, unknowns, and competing hypotheses.

    The CuriosityEngine prevents Kraitos from jumping to conclusions by
    systematically identifying what is missing, what could be misunderstood,
    and what alternative explanations still survive.

    It increases curiosity when evidence diverges, decreases it when
    evidence converges.
    """

    def __init__(
        self,
        world_model: SharedWorldModel | None = None,
        market_story: MarketStory | None = None,
        simulation_results: PossibleMarketFutures | None = None,
    ) -> None:
        """
        Initialize the CuriosityEngine.

        Parameters
        ----------
        world_model : SharedWorldModel, optional
            Current market understanding.
        market_story : MarketStory, optional
            Current market narrative.
        simulation_results : PossibleMarketFutures, optional
            Simulated market futures.
        """
        self.world_model = world_model
        self.market_story = market_story
        self.simulation_results = simulation_results

    def analyze(
        self,
        world_model: SharedWorldModel,
        market_story: MarketStory,
        simulation_results: PossibleMarketFutures,
    ) -> CuriosityReport:
        """
        Analyze gaps and unknowns in current understanding.

        Parameters
        ----------
        world_model : SharedWorldModel
            Current market understanding.
        market_story : MarketStory
            Current market narrative.
        simulation_results : PossibleMarketFutures
            Simulated market futures.

        Returns
        -------
        CuriosityReport
            Report on gaps, unknowns, and alternatives.
        """
        self.world_model = world_model
        self.market_story = market_story
        self.simulation_results = simulation_results

        # Generate components
        unanswered = self._identify_unanswered_questions()
        missing = self._identify_missing_evidence()
        alternatives = self._identify_alternative_explanations()
        evidence_next = self._identify_evidence_needed_next()
        high_impact = self._identify_high_impact_uncertainties()
        false_certainty = self._identify_false_certainty_risks()

        # Calculate curiosity level
        curiosity = self._calculate_curiosity_level(
            unanswered, missing, alternatives, high_impact
        )

        # Determine if action should be delayed
        should_delay = self._should_delay_action(
            curiosity, high_impact, false_certainty
        )

        # Create reason
        reason = self._create_reason(curiosity, unanswered, missing)

        return CuriosityReport(
            unanswered_questions=unanswered,
            missing_evidence=missing,
            alternative_explanations=alternatives,
            evidence_needed_next=evidence_next,
            curiosity_level=curiosity,
            should_delay_action=should_delay,
            reason=reason,
            high_impact_uncertainties=high_impact,
            false_certainty_risks=false_certainty,
        )

    def _identify_unanswered_questions(self) -> list[str]:
        """Identify critical unanswered questions."""
        questions = []

        if not self.world_model:
            return questions

        # Question about overall direction
        questions.append("What is the primary direction of current momentum?")

        # Questions about structure
        if len(self.world_model.support_levels) < 2:
            questions.append("Where are the key support and resistance levels?")

        # Questions about participation
        if not self.market_story or not self.market_story.participation_narrative:
            questions.append("What is the current participation level?")

        # Questions about regime
        questions.append("What market regime are we in (trend, range, transition)?")

        # Questions about macro
        if not self.world_model.macro_context:
            questions.append("How does current macro environment influence price action?")

        # Questions about liquidity
        questions.append("Where is liquidity concentrated? Where are the voids?")

        # Questions about contradictions
        if self.world_model.contradictions:
            questions.append("Why do price action and macro environment diverge?")

        # Questions about simulations
        if self.simulation_results and len(self.simulation_results.futures) > 2:
            questions.append(
                "Why do simulation results diverge? What resolves the ambiguity?"
            )

        return questions[:8]  # Return top 8

    def _identify_missing_evidence(self) -> list[str]:
        """Identify missing evidence that would clarify the story."""
        missing = []

        if not self.world_model:
            return missing

        # Missing volume/participation data
        if not self.market_story or not self.market_story.participation_narrative:
            missing.append("Volume profile at current price")
            missing.append("Participation vs. price action coherence")

        # Missing macro data
        missing.append("Macro catalyst alignment with current price action")

        # Missing liquidity data
        missing.append("Liquidity depth at key price levels")

        # Missing time/frequency analysis
        missing.append("Multi-timeframe confirmation of current structure")

        # Missing divergence data
        if self.world_model.contradictions:
            missing.append("Evidence explaining contradiction between macro and price")

        # Missing council specificity
        if self.world_model.council_reports:
            council_names = [r.council_name for r in self.world_model.council_reports]
            if "Sentiment" not in str(council_names):
                missing.append("Participant sentiment at current price")

            if "Liquidity" not in str(council_names):
                missing.append("Liquidity council confirmation")

        return missing[:7]  # Return top 7

    def _identify_alternative_explanations(self) -> list[str]:
        """Identify alternative hypotheses that still survive."""
        alternatives = []

        if not self.simulation_results:
            return alternatives

        # Map each future to an alternative explanation
        for future in self.simulation_results.futures[:3]:
            if future.probability and future.probability < 0.5:
                alternatives.append(
                    f"'{future.scenario_name}' could unfold if {future.story[:50]}..."
                )

        # Add contradictions as alternatives
        if self.world_model and self.world_model.contradictions:
            for contradiction in self.world_model.contradictions[:2]:
                alternatives.append(
                    f"Current understanding could be wrong about: {contradiction}"
                )

        # Add liquidity alternative
        alternatives.append(
            "Market could be hunting liquidity at key levels (unrelated to trend)"
        )

        # Add macro alternative
        if self.world_model and self.world_model.macro_context:
            alternatives.append(
                "Market could be repricing macro regime (not just trend/range shift)"
            )

        return alternatives[:6]  # Return top 6

    def _identify_evidence_needed_next(self) -> list[str]:
        """Identify specific evidence that would answer key questions."""
        needed = []

        if not self.world_model:
            return needed

        # Support/resistance test
        if self.world_model.support_levels:
            nearest_support = self.world_model.support_levels[0]
            needed.append(f"Test of support at {nearest_support}")

        if self.world_model.resistance_levels:
            nearest_resistance = self.world_model.resistance_levels[0]
            needed.append(f"Test of resistance at {nearest_resistance}")

        # Volume confirmation
        needed.append("Volume surge or divergence at next structure test")

        # Macro confirmation
        needed.append("Macro news or data release that aligns with price action")

        # Participation
        needed.append("Increased or decreased participation at current price")

        # Liquidity grab evidence
        needed.append("Sharp spike in volatility at key levels")

        # Time-based
        needed.append("Confirmation on longer timeframe (4hr, daily)")

        return needed[:7]  # Return top 7

    def _identify_high_impact_uncertainties(self) -> list[str]:
        """Identify unknowns that would significantly change the narrative."""
        high_impact = []

        if not self.world_model:
            return high_impact

        # Macro unknowns
        if len(self.world_model.unknowns) > 0:
            high_impact.extend(self.world_model.unknowns[:2])

        # Structural ambiguity
        if len(self.world_model.support_levels) < 2 or len(
            self.world_model.resistance_levels
        ) < 2:
            high_impact.append(
                "Lack of clear structural support/resistance definitions"
            )

        # Council disagreement
        if (
            self.world_model.council_reports
            and len(self.world_model.council_reports) > 2
        ):
            confidences = [r.confidence for r in self.world_model.council_reports]
            if max(confidences) - min(confidences) > 0.4:
                high_impact.append("Significant disagreement between councils")

        # Macro-price conflict
        if self.world_model.contradictions:
            high_impact.append("Macro environment vs. price action divergence")

        # Simulation uncertainty
        if self.simulation_results and self.simulation_results.confidence_in_all_forecasts < 0.5:
            high_impact.append(
                "Simulation results show high divergence (low forecast confidence)"
            )

        return high_impact[:5]  # Return top 5

    def _identify_false_certainty_risks(self) -> list[str]:
        """Identify risks of acting on incomplete information."""
        risks = []

        if not self.world_model:
            return risks

        # Risk from low conviction
        if self.world_model.confidence < 0.5:
            risks.append(
                "Acting before confidence is high risks being wrong-footed by subtle contradictions"
            )

        # Risk from high uncertainty
        if self.world_model.uncertainty > 0.6:
            risks.append(
                "High uncertainty means key assumptions could be invalidated quickly"
            )

        # Risk from contradictions
        if len(self.world_model.contradictions) > 2:
            risks.append(
                f"Multiple contradictions ({len(self.world_model.contradictions)}) suggest story may be incomplete"
            )

        # Risk from low council count
        if len(self.world_model.council_reports) < 3:
            risks.append(
                f"Only {len(self.world_model.council_reports)} councils reporting. Insufficient perspective."
            )

        # Risk from simulation divergence
        if self.simulation_results:
            probs_sum = self.simulation_results.probabilities_sum()
            if probs_sum > 1.2 or probs_sum < 0.8:
                risks.append(
                    "Simulation results diverge significantly (probabilities don't converge)"
                )

        # Risk from missing evidence
        risks.append(
            "Action before gathering key evidence risks directional surprise"
        )

        return risks[:6]  # Return top 6

    def _calculate_curiosity_level(
        self,
        unanswered: list[str],
        missing: list[str],
        alternatives: list[str],
        high_impact: list[str],
    ) -> float:
        """Calculate overall curiosity level."""
        base_curiosity = 0.5

        # Increase from unanswered questions
        curiosity = base_curiosity + (len(unanswered) * 0.05)

        # Increase from missing evidence
        curiosity += len(missing) * 0.04

        # Increase from alternative explanations
        curiosity += len(alternatives) * 0.03

        # Increase from high-impact uncertainties
        curiosity += len(high_impact) * 0.06

        # Modify by world model confidence
        if self.world_model:
            confidence_adjustment = (1.0 - self.world_model.confidence) * 0.2
            curiosity += confidence_adjustment

            # Modify by uncertainty
            uncertainty_adjustment = self.world_model.uncertainty * 0.15
            curiosity += uncertainty_adjustment

            # Reduce if contradictions are minor
            contradiction_factor = min(len(self.world_model.contradictions) * 0.05, 0.2)
            curiosity += contradiction_factor

        # Modify by simulation results
        if self.simulation_results:
            forecast_confidence = (
                1.0 - self.simulation_results.confidence_in_all_forecasts
            ) * 0.1
            curiosity += forecast_confidence

        # Cap at 1.0
        return min(1.0, curiosity)

    def _should_delay_action(
        self, curiosity: float, high_impact: list[str], false_certainty: list[str]
    ) -> bool:
        """Determine if action should be delayed."""
        # Delay if curiosity is very high
        if curiosity > 0.7:
            return True

        # Delay if many high-impact uncertainties
        if len(high_impact) > 3:
            return True

        # Delay if many false certainty risks
        if len(false_certainty) > 4:
            return True

        # Delay if world model confidence is low
        if self.world_model and self.world_model.confidence < 0.4:
            return True

        # Delay if uncertainty is high
        if self.world_model and self.world_model.uncertainty > 0.7:
            return True

        return False

    def _create_reason(
        self, curiosity: float, unanswered: list[str], missing: list[str]
    ) -> str:
        """Create explanation of curiosity assessment."""
        if curiosity > 0.75:
            primary = "High uncertainty across multiple dimensions."
        elif curiosity > 0.5:
            primary = "Moderate gaps in understanding."
        else:
            primary = "Story is relatively coherent."

        question_count = len(unanswered)
        missing_count = len(missing)

        secondary = (
            f"There are {question_count} unanswered questions and {missing_count} "
            "critical evidence gaps."
        )

        if curiosity > 0.7:
            tertiary = "Recommend gathering more information before committing."
        elif curiosity > 0.5:
            tertiary = "Additional confirmation would strengthen conviction."
        else:
            tertiary = "Story appears sufficiently clear for action."

        return f"{primary} {secondary} {tertiary}"

    def __str__(self) -> str:
        """Return a human-readable representation."""
        status = (
            "ready"
            if self.world_model and self.market_story and self.simulation_results
            else "idle"
        )
        return f"CuriosityEngine({status})"
