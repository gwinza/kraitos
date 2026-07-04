"""
NarrativeEngine: Translator between evidence and understanding.

The NarrativeEngine receives a SharedWorldModel and produces a MarketStory.
It answers fundamental questions:

- What is happening?
- Why is it happening?
- Who appears to be acting?
- What evidence supports this?
- What evidence contradicts this?
- What chapter of the story are we currently in?
- What chapters are most likely next?

It does NOT predict price.
It explains market behavior through the lens of evidence and participant intent.
"""

from kraitos.core.shared_world_model import SharedWorldModel
from kraitos.core.market_story import MarketStory
from kraitos.core.council_report import CouncilReport


class NarrativeEngine:
    """
    Translates evidence into coherent market narrative.

    The NarrativeEngine receives a SharedWorldModel (assembled from council reports)
    and produces a MarketStory (human-readable analysis).

    It is written in the voice of a senior macro analyst:
    - Evidence-driven
    - Uncertainty-aware
    - Contradiction-honest
    - Terminology-careful (no BUY/SELL/SIGNAL)

    Attributes
    ----------
    world_model : SharedWorldModel, optional
        The current understanding to build a story from.
    """

    def __init__(self, world_model: SharedWorldModel | None = None) -> None:
        """
        Initialize the NarrativeEngine.

        Parameters
        ----------
        world_model : SharedWorldModel, optional
            Initial world model to work from.
        """
        self.world_model = world_model

    def build_story(self, world_model: SharedWorldModel) -> MarketStory:
        """
        Build a complete MarketStory from a SharedWorldModel.

        Parameters
        ----------
        world_model : SharedWorldModel
            The current market understanding.

        Returns
        -------
        MarketStory
            A human-readable narrative of the market situation.

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

        # Build story components
        theme = self.identify_theme()
        participants = self.identify_participants()
        intent = self.identify_market_intent()
        complete_narrative = self.explain_story(theme, participants, intent)
        next_chapters = self.estimate_next_chapters()

        # Compile supporting and contradictory evidence
        supporting = world_model.summarize_evidence()
        contradicting = world_model.summarize_contradictions()
        unknowns = world_model.summarize_unknowns()

        # Build alternative narratives from unknowns
        alternatives = self._build_alternatives(unknowns)

        # Create the story
        story = MarketStory(
            complete_story=complete_narrative,
            current_chapter=world_model.current_chapter,
            dominant_theme=theme,
            supporting_evidence=supporting,
            contradictory_evidence=contradicting,
            alternative_stories=alternatives,
            possible_next_chapters=next_chapters,
            confidence=world_model.confidence,
            uncertainty=world_model.uncertainty,
        )

        return story

    def identify_theme(self) -> str:
        """
        Identify the dominant market theme from evidence.

        Analyzes council reports to extract the central tension or force
        driving current market behavior.

        Returns
        -------
        str
            Plain-English description of the dominant theme.

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call build_story() first.")

        if not self.world_model.council_reports:
            return "Insufficient evidence to identify theme."

        # Aggregate council confidence levels
        avg_confidence = sum(
            r.confidence for r in self.world_model.council_reports
        ) / len(self.world_model.council_reports)

        # Check for high contradiction
        if self.world_model.contradictions:
            return (
                f"Market shows conflicting signals with {len(self.world_model.contradictions)} "
                f"contradictions identified. Theme confidence: {avg_confidence:.1%}."
            )

        # Extract from story if available
        if self.world_model.current_story:
            return self.world_model.current_story.split(".")[0]

        return "Mixed evidence presents an unclear market structure."

    def identify_participants(self) -> str:
        """
        Identify likely market participants and their apparent objectives.

        Infers from volume, liquidity, and price structure who might be acting.

        Returns
        -------
        str
            Description of apparent participants and intent.

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call build_story() first.")

        participants = []

        for report in self.world_model.council_reports:
            if "liquidity" in report.council_name.lower():
                participants.append(
                    "Institutional participants are present (evidenced by liquidity patterns)."
                )
            if "volume" in report.council_name.lower():
                participants.append(
                    "Retail participation appears active (suggested by volume indicators)."
                )
            if "momentum" in report.council_name.lower():
                participants.append(
                    "Trend-following or algorithmic activity is likely present."
                )

        if not participants:
            return (
                "Limited evidence about participant composition. "
                "Councils have not reported on market participants."
            )

        return " ".join(list(dict.fromkeys(participants)))

    def identify_market_intent(self) -> str:
        """
        Identify apparent intent in market structure and behavior.

        Is the market in accumulation? Distribution? Rotation?

        Returns
        -------
        str
            Description of apparent market intent.

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call build_story() first.")

        # Check for disagreement between councils
        if len(self.world_model.council_reports) > 1:
            confidences = [r.confidence for r in self.world_model.council_reports]
            confidence_variance = max(confidences) - min(confidences)

            if confidence_variance > 0.3:
                return (
                    "Market intent is ambiguous. Councils show significant "
                    "disagreement in confidence levels, suggesting unclear structure."
                )

        # Check contradictions
        if self.world_model.contradictions:
            return (
                f"Market exhibits contradictory signals ({len(self.world_model.contradictions)} "
                f"identified). Intent remains unclear pending resolution."
            )

        # Use current_story if available
        if self.world_model.current_story:
            return self.world_model.current_story

        return "Insufficient evidence to characterize market intent."

    def explain_story(
        self, theme: str, participants: str, intent: str
    ) -> str:
        """
        Compose a complete narrative explaining the market situation.

        Written in the voice of a senior macro analyst.

        Parameters
        ----------
        theme : str
            The dominant theme.
        participants : str
            Description of participants.
        intent : str
            Description of market intent.

        Returns
        -------
        str
            Complete narrative explanation.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call build_story() first.")

        parts = [
            f"Theme: {theme}",
            f"Participants: {participants}",
            f"Intent: {intent}",
        ]

        # Add contradiction awareness if present
        if self.world_model.contradictions:
            parts.append(
                f"\nHowever, {len(self.world_model.contradictions)} "
                f"contradictions complicate this picture."
            )

        # Add uncertainty awareness
        if self.world_model.uncertainty > 0.6:
            parts.append(
                f"Confidence in this analysis is limited ({self.world_model.confidence:.0%}) "
                f"due to high uncertainty ({self.world_model.uncertainty:.0%})."
            )

        # Add evidence weakness awareness
        if len(self.world_model.council_reports) < 3:
            parts.append(
                "Limited council input means this analysis may be incomplete."
            )

        return "\n".join(parts)

    def estimate_next_chapters(self) -> list[str]:
        """
        Estimate plausible next chapters based on current evidence.

        Returns
        -------
        list[str]
            Ranked list of possible next market chapters.

        Raises
        ------
        ValueError
            If no world_model is set.
        """
        if self.world_model is None:
            raise ValueError("No world_model set. Call build_story() first.")

        next_chapters = []

        # Use world model's predicted chapters if available
        if self.world_model.possible_next_chapters:
            next_chapters.extend(self.world_model.possible_next_chapters)

        # Add chapters from all councils
        for report in self.world_model.council_reports:
            if report.possible_next_chapters:
                next_chapters.extend(report.possible_next_chapters)

        # Remove duplicates while preserving order
        seen = set()
        unique_chapters = []
        for chapter in next_chapters:
            if chapter not in seen:
                seen.add(chapter)
                unique_chapters.append(chapter)

        # If high uncertainty, add hedge
        if self.world_model.uncertainty > 0.7:
            unique_chapters.append(
                "Regime change or unexpected event (high uncertainty environment)."
            )

        return unique_chapters if unique_chapters else [
            "Insufficient evidence for chapter prediction."
        ]

    def _build_alternatives(self, unknowns: list[str]) -> list[str]:
        """
        Build alternative narratives from known unknowns.

        Parameters
        ----------
        unknowns : list[str]
            Known unknowns from council reports.

        Returns
        -------
        list[str]
            Alternative explanations of current market behavior.
        """
        alternatives = []

        if not unknowns:
            return alternatives

        # If macro events are unknown
        if any("macro" in u.lower() for u in unknowns):
            alternatives.append(
                "If macro conditions deteriorate, current structure could reverse."
            )

        # If participant intent is unknown
        if any("intent" in u.lower() or "participant" in u.lower() for u in unknowns):
            alternatives.append(
                "If major participants shift objectives, market structure may be reinterpreted."
            )

        # If key support/resistance is unclear
        if any(
            "support" in u.lower() or "resistance" in u.lower() for u in unknowns
        ):
            alternatives.append(
                "If key structural levels are broken, the entire narrative may change."
            )

        # Generic hedge
        if self.world_model and self.world_model.uncertainty > 0.5:
            alternatives.append(
                "High uncertainty means alternative interpretations deserve consideration."
            )

        return alternatives

    def __str__(self) -> str:
        """Return a human-readable representation of this engine."""
        status = "ready" if self.world_model else "idle"
        return f"NarrativeEngine({status})"
