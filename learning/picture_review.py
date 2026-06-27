"""Review Department — post-trade picture and strategy learning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from intelligence.picture_models import StorytellerDecision


@dataclass(frozen=True)
class PictureReviewOutcome:
    """Post-trade review comparing belief vs reality."""

    symbol: str
    story_correct: bool
    strategy_correct: bool
    execution_correct: bool
    useful_departments: tuple[str, ...]
    noisy_departments: tuple[str, ...]
    better_strategy: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "story_correct": self.story_correct,
            "strategy_correct": self.strategy_correct,
            "execution_correct": self.execution_correct,
            "useful_departments": list(self.useful_departments),
            "noisy_departments": list(self.noisy_departments),
            "better_strategy": self.better_strategy,
            "summary": self.summary,
        }


class PictureReviewEngine:
    """Review Department — learn from every completed trade."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None

    def review_trade(
        self,
        *,
        decision: StorytellerDecision | None,
        won: bool,
        r_multiple: float,
        side: str,
        exit_reason: str = "",
    ) -> PictureReviewOutcome | None:
        if decision is None:
            return None

        trade_direction = "bullish" if side == "buy" else "bearish"
        story_correct = won or r_multiple > 0
        strategy_correct = won and decision.thesis.selected_strategy != "none"
        execution_correct = won or exit_reason in {"take_profit", "partial_take_profit", "trail_stop"}

        useful: list[str] = []
        noisy: list[str] = []
        for dept in decision.picture.departments:
            aligned = (
                trade_direction in dept.observation.lower()
                or dept.department in {"risk", "execution", "memory", "review"}
            )
            if won and dept.confidence >= 55 and aligned:
                useful.append(dept.department)
            elif not won and dept.confidence >= 65 and aligned:
                noisy.append(dept.department)
            elif not won and dept.confidence >= 65 and not aligned:
                useful.append(dept.department)

        better = decision.thesis.selected_strategy
        if not strategy_correct and decision.strategy_rankings:
            for fit in decision.strategy_rankings[1:4]:
                if fit.fit_score > (decision.strategy_rankings[0].fit_score - 10):
                    better = fit.strategy_name
                    break

        summary = (
            f"Review {decision.symbol}: story {'correct' if story_correct else 'wrong'}, "
            f"strategy {'correct' if strategy_correct else 'review'}, "
            f"R={r_multiple:+.2f}. Useful: {', '.join(useful) or 'none'}."
        )

        outcome = PictureReviewOutcome(
            symbol=decision.symbol,
            story_correct=story_correct,
            strategy_correct=strategy_correct,
            execution_correct=execution_correct,
            useful_departments=tuple(useful),
            noisy_departments=tuple(noisy),
            better_strategy=better,
            summary=summary,
        )
        self._persist(outcome, decision)
        return outcome

    def _persist(self, outcome: PictureReviewOutcome, decision: StorytellerDecision) -> None:
        if self.project_root is None:
            return
        path = self.project_root / "logs" / "json" / "picture_reviews.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "outcome": outcome.to_dict(),
            "participation": decision.participation,
            "picture_clarity": decision.picture.clarity,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    @staticmethod
    def decision_from_snapshot(snapshot: str, *, symbol: str = "") -> StorytellerDecision | None:
        if not snapshot:
            return None
        try:
            data = json.loads(snapshot)
        except Exception:
            return None
        if not isinstance(data, dict) or "picture" not in data:
            return None
        from intelligence.market_storyteller_engine import MarketStorytellerEngine

        _ = MarketStorytellerEngine
        from intelligence.picture_models import (
            LiveMarketStory,
            MarketPicture,
            NarratorOutput,
            StoryTradeThesis,
            StrategyFit,
        )

        story_raw = data.get("story", {})
        picture_raw = data.get("picture", {})
        narration_raw = data.get("narration", {})
        thesis_raw = data.get("thesis", {})

        story = LiveMarketStory(
            symbol=str(story_raw.get("symbol", symbol)),
            what_is_happening=str(story_raw.get("what_is_happening", "")),
            why_it_is_happening=str(story_raw.get("why_it_is_happening", "")),
            who_is_in_control=str(story_raw.get("who_is_in_control", "")),
            who_is_trapped=str(story_raw.get("who_is_trapped", "")),
            liquidity_location=str(story_raw.get("liquidity_location", "")),
            market_objective=str(story_raw.get("market_objective", "")),
            next_likely_chapter=str(story_raw.get("next_likely_chapter", "")),
            narrative=str(story_raw.get("narrative", "")),
            confidence=float(story_raw.get("confidence", 0.0)),
        )
        picture = MarketPicture(
            symbol=str(picture_raw.get("symbol", symbol)),
            clarity=picture_raw.get("clarity", "incomplete"),  # type: ignore[arg-type]
            regime=picture_raw.get("regime", "transitional"),  # type: ignore[arg-type]
            dominant_side=str(picture_raw.get("dominant_side", "neutral")),
            coherent_story=bool(picture_raw.get("coherent_story", False)),
            summary=str(picture_raw.get("summary", "")),
            supporting_evidence=tuple(picture_raw.get("supporting_evidence", [])),
            contradictions=tuple(picture_raw.get("contradictions", [])),
            noise_evidence=tuple(picture_raw.get("noise_evidence", [])),
            key_evidence=tuple(picture_raw.get("key_evidence", [])),
            departments=(),
            confidence=float(picture_raw.get("confidence", 0.0)),
            professional_thesis_supported=bool(
                picture_raw.get("professional_thesis_supported", False)
            ),
            reason_not_clear=str(picture_raw.get("reason_not_clear", "")),
        )
        narration = NarratorOutput(
            symbol=str(narration_raw.get("symbol", symbol)),
            opening=str(narration_raw.get("opening", "")),
            institutions=str(narration_raw.get("institutions", "")),
            retail=str(narration_raw.get("retail", "")),
            liquidity=str(narration_raw.get("liquidity", "")),
            momentum=str(narration_raw.get("momentum", "")),
            volatility=str(narration_raw.get("volatility", "")),
            next_event=str(narration_raw.get("next_event", "")),
            confidence_statement=str(narration_raw.get("confidence_statement", "")),
            invalidation=str(narration_raw.get("invalidation", "")),
            full_narration=str(narration_raw.get("full_narration", "")),
        )
        rankings = tuple(
            StrategyFit(
                strategy_id=str(item.get("strategy_id", "")),
                strategy_name=str(item.get("strategy_name", "")),
                fit_score=float(item.get("fit_score", 0.0)),
                rationale=str(item.get("rationale", "")),
                entry_model=str(item.get("entry_model", "")),
                stop_model=str(item.get("stop_model", "")),
                target_model=str(item.get("target_model", "")),
            )
            for item in data.get("strategy_rankings", [])
            if isinstance(item, dict)
        )
        thesis = StoryTradeThesis(
            symbol=str(thesis_raw.get("symbol", symbol)),
            side=str(thesis_raw.get("side", "observe")),
            market_story=str(thesis_raw.get("market_story", "")),
            selected_strategy=str(thesis_raw.get("selected_strategy", "")),
            supporting_evidence=tuple(thesis_raw.get("supporting_evidence", [])),
            contradictory_evidence=tuple(thesis_raw.get("contradictory_evidence", [])),
            expected_path=str(thesis_raw.get("expected_path", "")),
            entry_logic=str(thesis_raw.get("entry_logic", "")),
            stop_logic=str(thesis_raw.get("stop_logic", "")),
            target_logic=str(thesis_raw.get("target_logic", "")),
            scaling_plan=str(thesis_raw.get("scaling_plan", "")),
            invalidation=str(thesis_raw.get("invalidation", "")),
            confidence=float(thesis_raw.get("confidence", 0.0)),
            risk_allocation=float(thesis_raw.get("risk_allocation", 0.0)),
            management_plan=str(thesis_raw.get("management_plan", "")),
            thesis_clear=bool(thesis_raw.get("thesis_clear", False)),
            rejection_reason=str(thesis_raw.get("rejection_reason", "")),
        )
        return StorytellerDecision(
            symbol=str(data.get("symbol", symbol)),
            story=story,
            picture=picture,
            narration=narration,
            strategy_rankings=rankings,
            thesis=thesis,
            participation=data.get("participation", "wait"),  # type: ignore[arg-type]
            allocation_multiplier=float(data.get("allocation_multiplier", 0.0)),
            cio_summary=str(data.get("cio_summary", "")),
            reason=str(data.get("reason", "")),
            hard_risk_blocked=bool(data.get("hard_risk_blocked", False)),
        )
