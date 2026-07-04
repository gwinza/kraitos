"""
ConvictionEngine: Measure confidence in understanding, not price prediction.

Professional traders don't ask "Is this bullish?"
They ask "How convinced am I in this narrative?"

The ConvictionEngine measures the quality and coherence of understanding
assembled from council evidence. It produces a ConvictionReport.

It never outputs trading signals.
It only measures conviction in understanding.
"""

from dataclasses import dataclass, field
from kraitos.core.shared_world_model import SharedWorldModel


@dataclass
class ConvictionReport:
    """
    A measurement of conviction in market understanding.

    This is NOT a trading signal. It is a professional assessment of how
    confident we should be in the current narrative.

    Attributes
    ----------
    confidence : float
        How certain is the current story? [0.0, 1.0]
    uncertainty : float
        How much remains unknown? [0.0, 1.0]
    agreement_score : float
        Do councils agree? [0.0, 1.0] (1.0 = full agreement)
    contradiction_score : float
        How many contradictions exist? [0.0, 1.0] (0.0 = no contradictions)
    missing_information : list[str]
        Critical gaps in understanding that would change conviction.
    conviction_level : str
        Qualitative assessment: "Very High", "High", "Moderate", "Low", "Very Low"
    story_quality : float
        How complete and coherent is the narrative? [0.0, 1.0]
    council_count : int
        How many councils contributed?
    evidence_count : int
        Total evidence pieces assembled.
    """

    confidence: float
    uncertainty: float
    agreement_score: float
    contradiction_score: float
    missing_information: list[str] = field(default_factory=list)
    conviction_level: str = "Low"
    story_quality: float = 0.5
    council_count: int = 0
    evidence_count: int = 0

    def __post_init__(self) -> None:
        """Validate conviction report on creation."""
        # Validate all scores are in [0.0, 1.0]
        for attr in [
            "confidence",
            "uncertainty",
            "agreement_score",
            "contradiction_score",
            "story_quality",
        ]:
            value = getattr(self, attr)
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{attr} must be between 0.0 and 1.0, got {value}.")

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"ConvictionReport(level={self.conviction_level}, "
            f"confidence={self.confidence:.2f}, uncertainty={self.uncertainty:.2f}, "
            f"agreement={self.agreement_score:.2f})"
        )


class ConvictionEngine:
    """
    Measure conviction in market understanding.

    The ConvictionEngine receives a SharedWorldModel and produces a ConvictionReport.
    It measures the quality, coherence, and consensus of the assembled narrative.

    Conviction increases when councils agree, evidence converges, and story is complete.
    Conviction decreases when evidence conflicts, critical information is missing, or
    councils disagree significantly.

    This is a confidence measurement, not a trading signal.
    """

    def __init__(self, world_model: SharedWorldModel | None = None) -> None:
        """
        Initialize the ConvictionEngine.

        Parameters
        ----------
        world_model : SharedWorldModel, optional
            The market understanding to evaluate.
        """
        self.world_model = world_model

    def calculate_conviction(
        self, world_model: SharedWorldModel
    ) -> ConvictionReport:
        """
        Calculate overall conviction in the current understanding.

        Parameters
        ----------
        world_model : SharedWorldModel
            The market understanding to evaluate.

        Returns
        -------
        ConvictionReport
            A comprehensive conviction assessment.

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

        # Calculate component scores
        confidence = self.calculate_confidence()
        uncertainty = self.calculate_uncertainty()
        agreement_score = self.calculate_agreement_score()
        contradiction_score = self.calculate_contradiction_score()
        story_quality = self.calculate_story_quality()

        # Identify missing information
        missing_info = self._identify_missing_information()

        # Determine conviction level
        conviction_level = self._determine_conviction_level(
            confidence, agreement_score, contradiction_score, story_quality
        )

        # Count evidence and councils
        council_count = len(world_model.council_reports)
        evidence_count = len(world_model.evidence_summary)

        return ConvictionReport(
            confidence=confidence,
            uncertainty=uncertainty,
            agreement_score=agreement_score,
            contradiction_score=contradiction_score,
            missing_information=missing_info,
            conviction_level=conviction_level,
            story_quality=story_quality,
            council_count=council_count,
            evidence_count=evidence_count,
        )

    def calculate_confidence(self) -> float:
        """
        Calculate confidence in the current understanding.

        Confidence increases when:
        - Councils report high individual confidence
        - Evidence is abundant
        - Story chapters are well-defined

        Returns
        -------
        float
            Confidence score [0.0, 1.0]

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call calculate_conviction() first.")

        if not self.world_model.council_reports:
            return 0.3  # Low confidence with no council input

        # Average council confidence
        council_confidences = [
            r.confidence for r in self.world_model.council_reports
        ]
        avg_council_confidence = sum(council_confidences) / len(council_confidences)

        # Boost for abundant evidence
        evidence_boost = min(
            0.2, len(self.world_model.evidence_summary) * 0.02
        )  # Max +0.2

        # Reduce for missing narrative
        narrative_penalty = 0.0
        if not self.world_model.current_story:
            narrative_penalty += 0.15
        if not self.world_model.current_chapter:
            narrative_penalty += 0.1
        if not self.world_model.dominant_next_chapter:
            narrative_penalty += 0.1

        confidence = avg_council_confidence + evidence_boost - narrative_penalty
        return max(0.0, min(1.0, confidence))

    def calculate_uncertainty(self) -> float:
        """
        Calculate uncertainty in the current understanding.

        Uncertainty increases when:
        - Unknowns are identified
        - Contradictions exist
        - Evidence is scarce

        Returns
        -------
        float
            Uncertainty score [0.0, 1.0]

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call calculate_conviction() first.")

        uncertainty = self.world_model.uncertainty

        # Add for contradictions
        contradiction_penalty = min(
            0.2, len(self.world_model.contradictions) * 0.05
        )

        # Add for unknowns
        unknown_penalty = min(0.2, len(self.world_model.unknowns) * 0.05)

        # Reduce for many councils (more sources = more confidence)
        council_boost = min(
            0.15, len(self.world_model.council_reports) * 0.03
        )  # Negative uncertainty

        uncertainty = (
            uncertainty + contradiction_penalty + unknown_penalty - council_boost
        )
        return max(0.0, min(1.0, uncertainty))

    def calculate_story_quality(self) -> float:
        """
        Calculate the quality and completeness of the narrative.

        Story quality increases when:
        - All narrative components are present
        - Evidence is balanced (supporting and contradicting)
        - Alternative stories are considered

        Returns
        -------
        float
            Story quality score [0.0, 1.0]

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call calculate_conviction() first.")

        quality = 0.5  # Start at neutral

        # Bonus for narrative completeness
        if self.world_model.current_story:
            quality += 0.1
        if self.world_model.current_chapter:
            quality += 0.1
        if self.world_model.dominant_next_chapter:
            quality += 0.1

        # Bonus for balanced evidence (both supporting and contradicting)
        if self.world_model.supporting_evidence and self.world_model.contradictions:
            quality += 0.15

        # Bonus for acknowledging unknowns
        if self.world_model.unknowns:
            quality += 0.1

        # Bonus for alternative chapters
        if self.world_model.possible_next_chapters:
            quality += 0.1

        # Penalty for too many councils with low individual story quality
        low_quality_councils = sum(
            1 for r in self.world_model.council_reports if r.confidence < 0.4
        )
        if low_quality_councils > len(self.world_model.council_reports) * 0.5:
            quality -= 0.2

        return max(0.0, min(1.0, quality))

    def calculate_agreement_score(self) -> float:
        """
        Calculate the degree of council agreement.

        Agreement increases when councils report similar confidence levels.
        Agreement decreases when councils strongly disagree.

        Returns
        -------
        float
            Agreement score [0.0, 1.0] (1.0 = perfect agreement)

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call calculate_conviction() first.")

        if len(self.world_model.council_reports) < 2:
            return 0.5  # Neutral with only one council

        confidences = [r.confidence for r in self.world_model.council_reports]

        # Calculate variance in confidence
        mean_confidence = sum(confidences) / len(confidences)
        variance = sum((c - mean_confidence) ** 2 for c in confidences) / len(
            confidences
        )
        std_dev = variance ** 0.5

        # Convert std dev to agreement score (lower std = higher agreement)
        # Std dev of 0 = perfect agreement (score 1.0)
        # Std dev of 0.5 = perfect disagreement (score 0.0)
        agreement = max(0.0, 1.0 - (std_dev * 2.0))
        return min(1.0, agreement)

    def calculate_contradiction_score(self) -> float:
        """
        Calculate the severity of contradictions in evidence.

        Returns a score where 0.0 = no contradictions, 1.0 = severe contradictions.

        Returns
        -------
        float
            Contradiction score [0.0, 1.0] (0.0 = none, 1.0 = severe)

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call calculate_conviction() first.")

        if not self.world_model.contradictions:
            return 0.0

        num_contradictions = len(self.world_model.contradictions)
        total_evidence = len(self.world_model.evidence_summary)

        if total_evidence == 0:
            return min(1.0, num_contradictions * 0.3)

        # Ratio of contradictions to total evidence
        contradiction_ratio = num_contradictions / (total_evidence + num_contradictions)

        return min(1.0, contradiction_ratio)

    def _identify_missing_information(self) -> list[str]:
        """
        Identify critical gaps in understanding.

        Returns
        -------
        list[str]
            List of critical missing information.
        """
        missing = []

        # Check for missing macro context
        if not any("macro" in str(u).lower() for u in self.world_model.unknowns):
            missing.append("Macro economic context could be better understood.")

        # Check for missing liquidity assessment
        if not any("liquidity" in r.council_name.lower() for r in self.world_model.council_reports):
            missing.append("Liquidity assessment is absent.")

        # Check for missing volume analysis
        if not any("volume" in r.council_name.lower() for r in self.world_model.council_reports):
            missing.append("Volume analysis is absent.")

        # Check for high unknowns
        if len(self.world_model.unknowns) > len(self.world_model.evidence_summary):
            missing.append("Unknowns exceed evidence — narrative is speculative.")

        # Check for unresolved contradictions
        if self.calculate_contradiction_score() > 0.4:
            missing.append(
                "Major contradictions remain unresolved — understanding may be flawed."
            )

        return missing

    def _determine_conviction_level(
        self,
        confidence: float,
        agreement_score: float,
        contradiction_score: float,
        story_quality: float,
    ) -> str:
        """
        Determine qualitative conviction level from component scores.

        Parameters
        ----------
        confidence : float
            Confidence score [0.0, 1.0]
        agreement_score : float
            Agreement score [0.0, 1.0]
        contradiction_score : float
            Contradiction score [0.0, 1.0]
        story_quality : float
            Story quality score [0.0, 1.0]

        Returns
        -------
        str
            Conviction level: "Very High", "High", "Moderate", "Low", "Very Low"
        """
        # Composite score: average the positive indicators, penalize contradictions
        composite = (
            confidence * 0.4 + agreement_score * 0.3 + story_quality * 0.3
        ) - (contradiction_score * 0.2)

        if composite >= 0.8:
            return "Very High"
        elif composite >= 0.6:
            return "High"
        elif composite >= 0.4:
            return "Moderate"
        elif composite >= 0.2:
            return "Low"
        else:
            return "Very Low"

    def __str__(self) -> str:
        """Return a human-readable representation of this engine."""
        status = "ready" if self.world_model else "idle"
        return f"ConvictionEngine({status})"
