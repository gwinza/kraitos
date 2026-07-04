"""
SimulationEngine: Generate plausible market futures.

Humans constantly imagine possible futures. Kraitos must do the same.

The SimulationEngine receives a SharedWorldModel and generates multiple
plausible market futures, each with supporting evidence, contradicting evidence,
and invalidation criteria.

The engine does NOT predict. It simulates.
The probabilities do NOT have to sum to 100%.
The engine can say "I don't know."
"""

from dataclasses import dataclass, field
from kraitos.core.shared_world_model import SharedWorldModel


@dataclass
class PossibleFuture:
    """
    A single plausible market future.

    This is NOT a prediction. It is a scenario that could unfold
    given current evidence and understanding.

    Attributes
    ----------
    scenario_name : str
        Name of this market scenario (e.g., "Trend Continuation", "Liquidity Grab")
    story : str
        Narrative description of how this future would unfold.
    supporting_evidence : list[str]
        Evidence that currently favors this scenario.
    contradicting_evidence : list[str]
        Evidence that currently conflicts with this scenario.
    invalidation_criteria : list[str]
        Specific conditions that would prove this scenario wrong.
    probability : float
        Estimated likelihood [0.0, 1.0]. Can be None if insufficient data.
    confidence_in_estimate : float
        How confident in the probability estimate? [0.0, 1.0]
    key_inflection_points : list[str]
        Critical levels or events that would trigger this future.
    dependencies : list[str]
        External dependencies (macro events, other markets, etc.)
    """

    scenario_name: str
    story: str
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    invalidation_criteria: list[str] = field(default_factory=list)
    probability: float | None = None
    confidence_in_estimate: float = 0.5
    key_inflection_points: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the future on creation."""
        if not self.scenario_name or not self.scenario_name.strip():
            raise ValueError("scenario_name cannot be empty.")

        if not self.story or not self.story.strip():
            raise ValueError("story cannot be empty.")

        if self.probability is not None:
            if not (0.0 <= self.probability <= 1.0):
                raise ValueError(
                    f"probability must be between 0.0 and 1.0, got {self.probability}."
                )

        if not (0.0 <= self.confidence_in_estimate <= 1.0):
            raise ValueError(
                f"confidence_in_estimate must be between 0.0 and 1.0, "
                f"got {self.confidence_in_estimate}."
            )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        prob_str = (
            f"{self.probability:.1%}"
            if self.probability is not None
            else "Unknown"
        )
        return (
            f"PossibleFuture({self.scenario_name}, "
            f"probability={prob_str}, "
            f"confidence={self.confidence_in_estimate:.2f})"
        )


@dataclass
class PossibleMarketFutures:
    """
    A collection of plausible market futures.

    This represents the set of scenarios that could unfold from the current
    market state given current evidence and understanding.

    Attributes
    ----------
    symbol : str
        The market being simulated.
    timeframe : str
        The time horizon of the simulation.
    base_world_model : SharedWorldModel
        The understanding from which these futures were generated.
    futures : list[PossibleFuture]
        All plausible futures.
    baseline_scenario : PossibleFuture, optional
        The most likely future (highest probability).
    tail_scenarios : list[PossibleFuture]
        Unlikely but significant scenarios.
    extreme_scenarios : list[PossibleFuture]
        Very low probability but severe impact scenarios.
    unknowns_affecting_forecast : list[str]
        Critical unknowns that could invalidate all forecasts.
    confidence_in_all_forecasts : float
        Overall confidence in the simulation [0.0, 1.0]
    """

    symbol: str
    timeframe: str
    base_world_model: SharedWorldModel
    futures: list[PossibleFuture] = field(default_factory=list)
    baseline_scenario: PossibleFuture | None = None
    tail_scenarios: list[PossibleFuture] = field(default_factory=list)
    extreme_scenarios: list[PossibleFuture] = field(default_factory=list)
    unknowns_affecting_forecast: list[str] = field(default_factory=list)
    confidence_in_all_forecasts: float = 0.5

    def __post_init__(self) -> None:
        """Validate the futures collection."""
        if not (0.0 <= self.confidence_in_all_forecasts <= 1.0):
            raise ValueError(
                f"confidence_in_all_forecasts must be between 0.0 and 1.0, "
                f"got {self.confidence_in_all_forecasts}."
            )

    def probabilities_sum(self) -> float:
        """
        Calculate the sum of all probabilities.

        Returns
        -------
        float
            Sum of all probability estimates (may be < 1.0 or > 1.0)
        """
        total = 0.0
        for future in self.futures:
            if future.probability is not None:
                total += future.probability
        return total

    def __str__(self) -> str:
        """Return a human-readable representation."""
        prob_sum = self.probabilities_sum()
        return (
            f"PossibleMarketFutures({self.symbol} {self.timeframe}, "
            f"{len(self.futures)} scenarios, "
            f"prob_sum={prob_sum:.1%}, "
            f"confidence={self.confidence_in_all_forecasts:.2f})"
        )


class SimulationEngine:
    """
    Generate multiple plausible market futures.

    The SimulationEngine simulates possible market outcomes based on current
    understanding. It is NOT a predictor. It is a scenario generator.

    Each scenario includes supporting evidence, contradicting evidence,
    invalidation criteria, and a probability estimate (which may be None).

    Probabilities do NOT sum to 100%.
    The engine can say "I don't know."
    """

    def __init__(self, world_model: SharedWorldModel | None = None) -> None:
        """
        Initialize the SimulationEngine.

        Parameters
        ----------
        world_model : SharedWorldModel, optional
            The market understanding to simulate from.
        """
        self.world_model = world_model

    def generate_futures(
        self, world_model: SharedWorldModel
    ) -> PossibleMarketFutures:
        """
        Generate multiple plausible market futures.

        Parameters
        ----------
        world_model : SharedWorldModel
            The current market understanding.

        Returns
        -------
        PossibleMarketFutures
            A collection of plausible scenarios.

        Raises
        ------
        ValueError
            If world_model is not a SharedWorldModel.
        """
        if not isinstance(world_model, SharedWorldModel):
            raise ValueError(
                f"Expected SharedWorldModel, got {type(world_model).__name__}."
            )

        self.world_model = world_model

        # Generate base scenarios
        futures = []
        futures.append(self._generate_continuation_scenario())
        futures.append(self._generate_liquidity_scenario())
        futures.append(self._generate_distribution_scenario())
        futures.append(self._generate_reversal_scenario())

        # Add alternative scenarios based on unknowns
        if world_model.unknowns:
            futures.append(self._generate_unknown_scenario())

        # Categorize scenarios
        baseline = self._identify_baseline(futures)
        tail_scenarios = self._identify_tail_scenarios(futures)
        extreme_scenarios = self._identify_extreme_scenarios(futures)

        # Calculate overall confidence
        overall_confidence = self._calculate_forecast_confidence()

        # Identify unknowns affecting forecast
        unknowns = self._identify_forecast_unknowns()

        return PossibleMarketFutures(
            symbol=world_model.symbol,
            timeframe=world_model.timeframe,
            base_world_model=world_model,
            futures=futures,
            baseline_scenario=baseline,
            tail_scenarios=tail_scenarios,
            extreme_scenarios=extreme_scenarios,
            unknowns_affecting_forecast=unknowns,
            confidence_in_all_forecasts=overall_confidence,
        )

    def _generate_continuation_scenario(self) -> PossibleFuture:
        """Generate a trend continuation scenario."""
        future = PossibleFuture(
            scenario_name="Trend Continuation",
            story=(
                "Current momentum persists. Market extends recent direction "
                "with liquidity participating. Structure remains intact."
            ),
            supporting_evidence=[],
            contradicting_evidence=[],
            invalidation_criteria=[
                "Break of key support/resistance",
                "Volume deterioration",
                "Reversal candle patterns",
            ],
            probability=None,
            confidence_in_estimate=0.5,
            key_inflection_points=[
                "Previous swing high/low",
                "Major round numbers",
            ],
            dependencies=["Macro conditions remain supportive", "Liquidity sustained"],
        )

        # Add evidence from world model
        if self.world_model:
            future.supporting_evidence = self.world_model.evidence_summary[:3]
            future.contradicting_evidence = self.world_model.contradictions[:2]
            future.probability = self._estimate_continuation_probability()

        return future

    def _generate_liquidity_scenario(self) -> PossibleFuture:
        """Generate a liquidity grab scenario."""
        future = PossibleFuture(
            scenario_name="Liquidity Grab",
            story=(
                "Market moves aggressively to collect liquidity at key levels. "
                "Participants hunt stops and orders. Sharp move followed by reversal."
            ),
            supporting_evidence=[],
            contradicting_evidence=[],
            invalidation_criteria=[
                "No spike in volume during move",
                "Move lacks aggression",
                "No reversal after liquidity take",
            ],
            probability=None,
            confidence_in_estimate=0.5,
            key_inflection_points=[
                "Previous local highs/lows",
                "Stop-loss clustering areas",
                "High volume nodes",
            ],
            dependencies=["Participants aware of key levels", "Sufficient liquidity to grab"],
        )

        # Add evidence from world model
        if self.world_model:
            future.probability = self._estimate_liquidity_probability()

        return future

    def _generate_distribution_scenario(self) -> PossibleFuture:
        """Generate a distribution (accumulation) scenario."""
        future = PossibleFuture(
            scenario_name="Distribution Phase",
            story=(
                "Market enters phase where participants are gradually reducing positions. "
                "Price action may appear bullish but volume participation is declining. "
                "Foundation for reversal being established."
            ),
            supporting_evidence=[],
            contradicting_evidence=[],
            invalidation_criteria=[
                "Volume participation remains strong",
                "New buyers enter aggressively",
                "Breakout above resistance on volume",
            ],
            probability=None,
            confidence_in_estimate=0.5,
            key_inflection_points=[
                "Test of key resistance",
                "Divergence between price and volume",
            ],
            dependencies=["Participants ready to exit", "No new catalyst"],
        )

        # Add evidence from world model
        if self.world_model:
            future.probability = self._estimate_distribution_probability()

        return future

    def _generate_reversal_scenario(self) -> PossibleFuture:
        """Generate a reversal scenario."""
        future = PossibleFuture(
            scenario_name="Reversal",
            story=(
                "Market reverses sharply from current direction. "
                "Structural support/resistance breaks. Participants caught wrong-sided. "
                "New regime begins."
            ),
            supporting_evidence=[],
            contradicting_evidence=[],
            invalidation_criteria=[
                "Recovery from break",
                "Strong counter-move",
                "Rejection of new direction",
            ],
            probability=None,
            confidence_in_estimate=0.5,
            key_inflection_points=[
                "Major structural support/resistance",
                "Key round numbers",
                "Previous swing extremes",
            ],
            dependencies=["Macro shift", "Participant sentiment shift", "Key level break"],
        )

        # Add evidence from world model
        if self.world_model:
            future.probability = self._estimate_reversal_probability()

        return future

    def _generate_unknown_scenario(self) -> PossibleFuture:
        """Generate a scenario based on identified unknowns."""
        future = PossibleFuture(
            scenario_name="Scenario Dependent on Unknowns",
            story=(
                "Market outcome hinges on information that is currently unknown. "
                "Resolution of unknowns could trigger any of the above scenarios. "
                "This scenario has highest uncertainty."
            ),
            supporting_evidence=[],
            contradicting_evidence=[],
            invalidation_criteria=["Information becomes known"],
            probability=None,  # Explicitly unknown
            confidence_in_estimate=0.1,  # Very low confidence
            key_inflection_points=self.world_model.unknowns if self.world_model else [],
            dependencies=self.world_model.unknowns if self.world_model else [],
        )

        return future

    def _estimate_continuation_probability(self) -> float | None:
        """Estimate probability of trend continuation."""
        if not self.world_model:
            return None

        # Higher if agreement score is high
        agreement_boost = 0.0
        if len(self.world_model.council_reports) > 1:
            confidences = [r.confidence for r in self.world_model.council_reports]
            avg_confidence = sum(confidences) / len(confidences)
            agreement_boost = avg_confidence * 0.2

        # Lower if many contradictions
        contradiction_penalty = len(self.world_model.contradictions) * 0.1

        # Base probability for continuation
        base = 0.4
        probability = base + agreement_boost - contradiction_penalty

        return max(0.1, min(0.8, probability))

    def _estimate_liquidity_probability(self) -> float | None:
        """Estimate probability of liquidity grab scenario."""
        if not self.world_model:
            return None

        # Check for liquidity council evidence
        has_liquidity_council = any(
            "liquidity" in r.council_name.lower()
            for r in self.world_model.council_reports
        )

        base = 0.25 if has_liquidity_council else 0.15

        # Increase if market is near key levels
        probability = base

        return max(0.1, min(0.6, probability))

    def _estimate_distribution_probability(self) -> float | None:
        """Estimate probability of distribution scenario."""
        if not self.world_model:
            return None

        # Higher if confidence is declining
        if self.world_model.confidence < 0.5:
            base = 0.35
        else:
            base = 0.25

        probability = base

        return max(0.1, min(0.7, probability))

    def _estimate_reversal_probability(self) -> float | None:
        """Estimate probability of reversal scenario."""
        if not self.world_model:
            return None

        # Higher if many contradictions
        contradiction_factor = len(self.world_model.contradictions) * 0.05

        base = 0.2
        probability = base + contradiction_factor

        return max(0.1, min(0.6, probability))

    def _identify_baseline(self, futures: list[PossibleFuture]) -> PossibleFuture | None:
        """Identify the most likely baseline scenario."""
        futures_with_prob = [f for f in futures if f.probability is not None]

        if not futures_with_prob:
            return None

        return max(futures_with_prob, key=lambda f: f.probability or 0)

    def _identify_tail_scenarios(
        self, futures: list[PossibleFuture]
    ) -> list[PossibleFuture]:
        """Identify tail (low probability but plausible) scenarios."""
        tail = [f for f in futures if f.probability and 0.1 <= f.probability < 0.3]
        return sorted(tail, key=lambda f: f.probability or 0, reverse=True)

    def _identify_extreme_scenarios(
        self, futures: list[PossibleFuture]
    ) -> list[PossibleFuture]:
        """Identify extreme (very low probability) scenarios."""
        extreme = [f for f in futures if f.probability and f.probability < 0.1]
        return sorted(extreme, key=lambda f: f.probability or 0, reverse=True)

    def _calculate_forecast_confidence(self) -> float:
        """Calculate overall confidence in all forecasts."""
        if not self.world_model:
            return 0.3

        # Based on underlying conviction
        base_confidence = self.world_model.confidence

        # Reduce if many unknowns
        unknown_penalty = min(0.3, len(self.world_model.unknowns) * 0.05)

        # Reduce if high uncertainty
        uncertainty_penalty = self.world_model.uncertainty * 0.2

        confidence = base_confidence - unknown_penalty - uncertainty_penalty

        return max(0.1, min(0.9, confidence))

    def _identify_forecast_unknowns(self) -> list[str]:
        """Identify unknowns that most affect the forecast."""
        if not self.world_model:
            return []

        return self.world_model.unknowns[:5]

    def __str__(self) -> str:
        """Return a human-readable representation."""
        status = "ready" if self.world_model else "idle"
        return f"SimulationEngine({status})"
