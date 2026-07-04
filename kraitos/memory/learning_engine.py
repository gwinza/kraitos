"""
LearningEngine: Compare what Kraitos expected with what reality did.

Kraitos does not learn trades.
Kraitos learns stories.

The LearningEngine evaluates whether:
1. The story Kraitos told was correct
2. The action Kraitos took was appropriate given the story
3. The outcome confirmed or contradicted the narrative

It adjusts conviction only when patterns repeat, not from single events.
It separates process quality from outcome quality.
"""

from dataclasses import dataclass, field
from datetime import datetime
from kraitos.core.market_story import MarketStory
from kraitos.brain.executive_cortex import ExecutiveDecision
from kraitos.brain.next_chapter_engine import NextChapter


@dataclass
class LearningRecord:
    """
    A record of what Kraitos expected vs. what actually happened.

    This record separates outcome quality (did we make money?) from
    process quality (was the story correct?).

    Attributes
    ----------
    story_before : str
        The narrative Kraitos told before action.
    expected_next_chapter : str
        The market chapter Kraitos predicted.
    actual_outcome : str
        What actually happened in the market.
    action_taken : str
        The expression Kraitos chose (WAIT, PROBE, ENTER, etc.).
    was_story_correct : bool
        True if the narrative proved accurate.
    was_action_correct : bool
        True if the action was appropriate for the outcome.
    realized_pnl : float
        Profit/loss from the position.
    lesson : str
        Plain English lesson from this outcome.
    confidence_adjustment : float
        Change to confidence [-0.1, 0.1]. Small adjustments only.
    tags : list[str]
        Tags for categorizing this learning (e.g., "liquidity_search", "false_breakout").
    timestamp : datetime
        When this record was created.
    reasoning_quality : str
        Assessment: EXCELLENT, GOOD, ACCEPTABLE, POOR, FLAWED.
    outcome_quality : str
        Assessment: EXCELLENT, GOOD, ACCEPTABLE, POOR, FLAWED.
    win_despite_poor_story : bool
        True if we profited despite flawed reasoning.
    loss_despite_good_story : bool
        True if we lost despite sound reasoning.
    repeat_pattern : str
        If this error/success repeats, what pattern is it?
    """

    story_before: str
    expected_next_chapter: str
    actual_outcome: str
    action_taken: str
    was_story_correct: bool
    was_action_correct: bool
    realized_pnl: float
    lesson: str
    confidence_adjustment: float = 0.0
    tags: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    reasoning_quality: str = "ACCEPTABLE"
    outcome_quality: str = "ACCEPTABLE"
    win_despite_poor_story: bool = False
    loss_despite_good_story: bool = False
    repeat_pattern: str = ""

    def __post_init__(self) -> None:
        """Validate the record on creation."""
        if not (-0.1 <= self.confidence_adjustment <= 0.1):
            raise ValueError(
                f"confidence_adjustment must be in [-0.1, 0.1], "
                f"got {self.confidence_adjustment}."
            )

        valid_qualities = {"EXCELLENT", "GOOD", "ACCEPTABLE", "POOR", "FLAWED"}
        if self.reasoning_quality not in valid_qualities:
            raise ValueError(
                f"Invalid reasoning_quality: {self.reasoning_quality}. "
                f"Must be one of: {valid_qualities}"
            )

        if self.outcome_quality not in valid_qualities:
            raise ValueError(
                f"Invalid outcome_quality: {self.outcome_quality}. "
                f"Must be one of: {valid_qualities}"
            )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        pnl_str = f"+{self.realized_pnl:.2f}" if self.realized_pnl >= 0 else f"{self.realized_pnl:.2f}"
        return (
            f"LearningRecord({self.action_taken}, "
            f"story={'✓' if self.was_story_correct else '✗'}, "
            f"pnl={pnl_str}, "
            f"reasoning={self.reasoning_quality})"
        )


class LearningEngine:
    """
    Learn from market outcomes and narrative accuracy.

    The LearningEngine evaluates whether Kraitos understood the market story
    correctly, whether the action was appropriate, and how to adjust conviction
    based on patterns (not single events).

    It separates:
    - Story accuracy (did the narrative prove correct?)
    - Action quality (was the decision appropriate?)
    - Outcome quality (did we make money?)
    """

    def __init__(self) -> None:
        """Initialize the LearningEngine."""
        self.learning_history: list[LearningRecord] = []
        self.story_accuracy_tracker: dict[str, list[bool]] = {}
        self.action_tracker: dict[str, list[tuple[bool, float]]] = {}

    def create_learning_record(
        self,
        story_before: str | MarketStory,
        expected_next_chapter: str | NextChapter,
        actual_outcome: str,
        action_taken: str | ExecutiveDecision,
        realized_pnl: float,
        notes: str = "",
    ) -> LearningRecord:
        """
        Create a comprehensive learning record.

        Parameters
        ----------
        story_before : str or MarketStory
            The narrative before action.
        expected_next_chapter : str or NextChapter
            The predicted market chapter.
        actual_outcome : str
            What actually happened.
        action_taken : str or ExecutiveDecision
            The action Kraitos took.
        realized_pnl : float
            Profit/loss from the trade.
        notes : str, optional
            Additional context.

        Returns
        -------
        LearningRecord
            Complete learning record.
        """
        # Normalize inputs
        story_str = (
            story_before.complete_story
            if isinstance(story_before, MarketStory)
            else story_before
        )

        chapter_str = (
            expected_next_chapter.chapter_name
            if isinstance(expected_next_chapter, NextChapter)
            else expected_next_chapter
        )

        action_str = (
            action_taken.expression
            if isinstance(action_taken, ExecutiveDecision)
            else action_taken
        )

        # Evaluate story accuracy
        was_story_correct = self.evaluate_story_accuracy(
            story_str, actual_outcome
        )

        # Evaluate action quality
        was_action_correct = self.evaluate_action_quality(
            action_str, actual_outcome, realized_pnl
        )

        # Generate lesson
        lesson = self.generate_lesson(
            story_str, actual_outcome, was_story_correct, was_action_correct
        )

        # Calculate confidence adjustment
        confidence_adj = self.calculate_confidence_adjustment(
            was_story_correct, was_action_correct, realized_pnl, chapter_str
        )

        # Assess reasoning and outcome quality
        reasoning_quality = self._assess_reasoning_quality(
            was_story_correct, was_action_correct
        )

        outcome_quality = self._assess_outcome_quality(realized_pnl)

        # Check for win/loss mismatches
        win_despite_poor = (
            realized_pnl > 0 and reasoning_quality in ["POOR", "FLAWED"]
        )
        loss_despite_good = (
            realized_pnl < 0 and reasoning_quality in ["GOOD", "EXCELLENT"]
        )

        # Generate tags
        tags = self._generate_tags(
            chapter_str, actual_outcome, was_story_correct, notes
        )

        # Create record
        record = LearningRecord(
            story_before=story_str[:100],
            expected_next_chapter=chapter_str,
            actual_outcome=actual_outcome,
            action_taken=action_str,
            was_story_correct=was_story_correct,
            was_action_correct=was_action_correct,
            realized_pnl=realized_pnl,
            lesson=lesson,
            confidence_adjustment=confidence_adj,
            tags=tags,
            reasoning_quality=reasoning_quality,
            outcome_quality=outcome_quality,
            win_despite_poor_story=win_despite_poor,
            loss_despite_good_story=loss_despite_good,
        )

        # Track in history
        self.learning_history.append(record)

        # Update tracking
        self._update_trackers(chapter_str, was_story_correct, was_action_correct, realized_pnl)

        return record

    def evaluate_story_accuracy(self, story: str, actual_outcome: str) -> bool:
        """
        Evaluate whether the story Kraitos told was correct.

        Parameters
        ----------
        story : str
            The narrative before action.
        actual_outcome : str
            What actually happened.

        Returns
        -------
        bool
            True if the story proved accurate.
        """
        story_lower = story.lower()
        outcome_lower = actual_outcome.lower()

        # Check for direct contradictions
        contradictions = [
            ("expansion" in story_lower and "capitulation" in outcome_lower),
            ("accumulation" in story_lower and "distribution" in outcome_lower),
            ("trend" in story_lower and "reversal" in outcome_lower),
            ("consolidation" in story_lower and "breakout" in outcome_lower),
        ]

        if any(contradictions):
            return False

        # Check for alignment
        alignments = [
            ("expansion" in story_lower and "higher" in outcome_lower),
            ("accumulation" in story_lower and "consolidat" in outcome_lower),
            ("distribution" in story_lower and "lower" in outcome_lower),
            ("liquidity" in story_lower and "spike" in outcome_lower or "sharp" in outcome_lower),
            ("trend" in story_lower and "continu" in outcome_lower),
        ]

        if any(alignments):
            return True

        # Neutral if no clear contradiction or alignment
        return None  # type: ignore

    def evaluate_action_quality(
        self, action: str, actual_outcome: str, realized_pnl: float
    ) -> bool:
        """
        Evaluate whether the action was appropriate for the outcome.

        Note: This is NOT "did we make money?" but "was this the right action?"

        Parameters
        ----------
        action : str
            The expression chosen (WAIT, PROBE, ENTER, etc.).
        actual_outcome : str
            What actually happened.
        realized_pnl : float
            Profit/loss.

        Returns
        -------
        bool
            True if action was appropriate given the outcome.
        """
        # WAIT is always correct if market moved sharply
        if action == "WAIT":
            if "sharp" in actual_outcome.lower() or "volatile" in actual_outcome.lower():
                return True

        # OBSERVE_MORE is correct if more information was needed
        if action == "OBSERVE_MORE":
            if "unclear" in actual_outcome.lower() or "mixed" in actual_outcome.lower():
                return True

        # ENTER_LONG is correct if market went up
        if action in ["ENTER_LONG", "PROBE_LONG"]:
            if realized_pnl > 0 or "higher" in actual_outcome.lower():
                return True

        # ENTER_SHORT is correct if market went down
        if action in ["ENTER_SHORT", "PROBE_SHORT"]:
            if realized_pnl < 0 or "lower" in actual_outcome.lower():
                return True

        # REDUCE_RISK is correct if we avoided catastrophic loss
        if action == "REDUCE_RISK":
            if abs(realized_pnl) < 1.0:  # Arbitrary small threshold
                return True

        # EXIT is correct if market invalidated story
        if action == "EXIT":
            if "invalidated" in actual_outcome.lower() or realized_pnl > 0:
                return True

        # HOLD is correct if story remained intact
        if action == "HOLD":
            if "continued" in actual_outcome.lower() or realized_pnl > 0:
                return True

        return False

    def generate_lesson(
        self,
        story: str,
        actual_outcome: str,
        was_story_correct: bool,
        was_action_correct: bool,
    ) -> str:
        """
        Generate a plain English lesson from this outcome.

        Parameters
        ----------
        story : str
            The narrative before action.
        actual_outcome : str
            What actually happened.
        was_story_correct : bool
            Whether the story proved accurate.
        was_action_correct : bool
            Whether the action was appropriate.

        Returns
        -------
        str
            Plain English lesson.
        """
        if was_story_correct and was_action_correct:
            return (
                "Story was correct and action was appropriate. "
                "This confirms the narrative framework."
            )

        if was_story_correct and not was_action_correct:
            return (
                "Story was correct but action was poorly timed or sized. "
                "Review execution, not narrative."
            )

        if not was_story_correct and was_action_correct:
            return (
                "Story was incorrect but action was defensive or cautious. "
                "Good risk management protected against narrative error."
            )

        # Both false
        return (
            f"Story '{story[:50]}...' did not match outcome '{actual_outcome[:50]}...'. "
            "Narrative framework needs revision."
        )

    def calculate_confidence_adjustment(
        self,
        was_story_correct: bool,
        was_action_correct: bool,
        realized_pnl: float,
        chapter: str,
    ) -> float:
        """
        Calculate small confidence adjustment based on outcome.

        Rules:
        - Do NOT overfit one trade
        - Adjust only when patterns repeat
        - Separate process from outcome
        - Max adjustment: ±0.05 for single event
        - Larger adjustments only after multiple confirmations

        Parameters
        ----------
        was_story_correct : bool
            Whether story was accurate.
        was_action_correct : bool
            Whether action was appropriate.
        realized_pnl : float
            Profit/loss.
        chapter : str
            The market chapter.

        Returns
        -------
        float
            Confidence adjustment [-0.1, 0.1].
        """
        base_adjustment = 0.0

        # Story correctness contributes ±0.02
        if was_story_correct:
            base_adjustment += 0.02
        elif not was_story_correct:
            base_adjustment -= 0.02

        # Action quality contributes ±0.02
        if was_action_correct:
            base_adjustment += 0.02
        elif not was_action_correct:
            base_adjustment -= 0.02

        # Check for repeat patterns
        pattern_count = self._count_similar_patterns(chapter, was_story_correct)

        if pattern_count > 1:
            # Only increase adjustment if pattern repeats
            if was_story_correct:
                base_adjustment = min(base_adjustment * 1.5, 0.08)
            else:
                base_adjustment = max(base_adjustment * 1.5, -0.08)

        # Cap adjustment
        return max(min(base_adjustment, 0.1), -0.1)

    def _assess_reasoning_quality(
        self, was_story_correct: bool, was_action_correct: bool
    ) -> str:
        """Assess quality of reasoning."""
        if was_story_correct and was_action_correct:
            return "EXCELLENT"
        elif was_story_correct or was_action_correct:
            return "GOOD"
        elif was_story_correct is None:  # Neutral
            return "ACCEPTABLE"
        else:
            return "POOR"

    def _assess_outcome_quality(self, realized_pnl: float) -> str:
        """Assess quality of outcome."""
        if realized_pnl > 1.0:
            return "EXCELLENT"
        elif realized_pnl > 0.1:
            return "GOOD"
        elif realized_pnl > -0.1:
            return "ACCEPTABLE"
        elif realized_pnl > -1.0:
            return "POOR"
        else:
            return "FLAWED"

    def _generate_tags(
        self,
        chapter: str,
        actual_outcome: str,
        was_story_correct: bool,
        notes: str,
    ) -> list[str]:
        """Generate categorization tags."""
        tags = []

        # Chapter tag
        tags.append(chapter.lower().replace(" ", "_"))

        # Outcome tags
        if "higher" in actual_outcome.lower():
            tags.append("moved_up")
        elif "lower" in actual_outcome.lower():
            tags.append("moved_down")

        if "volatile" in actual_outcome.lower():
            tags.append("volatile")

        if "range" in actual_outcome.lower():
            tags.append("rangebound")

        # Story accuracy tags
        if was_story_correct:
            tags.append("story_confirmed")
        elif not was_story_correct:
            tags.append("story_invalidated")
        else:
            tags.append("story_neutral")

        # Notes tags
        if notes:
            tags.append("has_notes")

        return tags

    def _count_similar_patterns(self, chapter: str, was_correct: bool) -> int:
        """Count how many times this pattern has repeated."""
        count = 0
        for record in self.learning_history[-10:]:  # Look at last 10 records
            if record.expected_next_chapter == chapter:
                if record.was_story_correct == was_correct:
                    count += 1

        return count

    def _update_trackers(
        self,
        chapter: str,
        was_story_correct: bool,
        was_action_correct: bool,
        realized_pnl: float,
    ) -> None:
        """Update internal tracking."""
        # Track story accuracy
        if chapter not in self.story_accuracy_tracker:
            self.story_accuracy_tracker[chapter] = []

        self.story_accuracy_tracker[chapter].append(was_story_correct)

        # Track action quality
        if chapter not in self.action_tracker:
            self.action_tracker[chapter] = []

        self.action_tracker[chapter].append((was_action_correct, realized_pnl))

    def get_learning_summary(self, chapter: str | None = None) -> dict:
        """
        Get summary of learning across records.

        Parameters
        ----------
        chapter : str, optional
            Filter by chapter. If None, return all chapters.

        Returns
        -------
        dict
            Summary statistics.
        """
        if chapter:
            records = [r for r in self.learning_history if r.expected_next_chapter == chapter]
        else:
            records = self.learning_history

        if not records:
            return {
                "total_records": 0,
                "story_accuracy": 0.0,
                "action_accuracy": 0.0,
                "avg_pnl": 0.0,
            }

        story_accurate = sum(1 for r in records if r.was_story_correct)
        action_accurate = sum(1 for r in records if r.was_action_correct)
        total_pnl = sum(r.realized_pnl for r in records)

        return {
            "total_records": len(records),
            "story_accuracy": story_accurate / len(records),
            "action_accuracy": action_accurate / len(records),
            "avg_pnl": total_pnl / len(records),
            "total_pnl": total_pnl,
            "chapter": chapter or "all",
        }

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"LearningEngine({len(self.learning_history)} records, "
            f"{len(self.story_accuracy_tracker)} chapters tracked)"
        )
