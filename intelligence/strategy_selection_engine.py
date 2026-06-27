"""Strategy Selection Engine — rank professional playbooks against the market picture."""

from __future__ import annotations

from intelligence.picture_models import LiveMarketStory, MarketPicture, StrategyFit
from intelligence.strategy_playbook import PROFESSIONAL_STRATEGY_PLAYBOOK, StrategyDefinition


class StrategySelectionEngine:
    """Evaluate which professional strategy best exploits the current story."""

    def rank(
        self,
        *,
        picture: MarketPicture,
        story: LiveMarketStory,
    ) -> tuple[StrategyFit, ...]:
        scores: list[StrategyFit] = []
        narrative = f"{story.narrative} {picture.summary}".lower()
        dept_text = " ".join(d.observation.lower() for d in picture.departments)

        for strategy in PROFESSIONAL_STRATEGY_PLAYBOOK:
            fit = self._score_strategy(strategy, picture, narrative, dept_text)
            scores.append(fit)

        scores.sort(key=lambda item: item.fit_score, reverse=True)
        return tuple(scores)

    def rank_top(
        self,
        *,
        picture: MarketPicture,
        story: LiveMarketStory,
        n: int = 5,
    ) -> tuple[StrategyFit, ...]:
        """Score strategies and return only the top N — avoids full sort when n is small."""
        narrative = f"{story.narrative} {picture.summary}".lower()
        dept_text = " ".join(d.observation.lower() for d in picture.departments)

        top: list[StrategyFit] = []
        for strategy in PROFESSIONAL_STRATEGY_PLAYBOOK:
            fit = self._score_strategy(strategy, picture, narrative, dept_text)
            top.append(fit)
            if len(top) > n * 2:
                top.sort(key=lambda item: item.fit_score, reverse=True)
                top = top[:n]

        top.sort(key=lambda item: item.fit_score, reverse=True)
        return tuple(top[:n])

    def _score_strategy(
        self,
        strategy: StrategyDefinition,
        picture: MarketPicture,
        narrative: str,
        dept_text: str,
    ) -> StrategyFit:
        score = strategy.base_expectancy * 100
        rationale_parts: list[str] = []

        for condition in strategy.works_when:
            tokens = condition.lower().split()
            if any(token in narrative or token in dept_text for token in tokens if len(token) > 4):
                score += 8
                rationale_parts.append(f"fits: {condition}")

        for condition in strategy.fails_when:
            tokens = condition.lower().split()
            if any(token in narrative or token in dept_text for token in tokens if len(token) > 4):
                score -= 12
                rationale_parts.append(f"risk: {condition}")

        if picture.clarity == "clear":
            score += 6
        elif picture.clarity == "conflicted":
            score -= 15

        if "sweep" in narrative and "liquidity_sweep" in strategy.strategy_id:
            score += 18
            rationale_parts.append("liquidity sweep in narrative")
        if picture.regime == "trending" and "trend" in strategy.strategy_id:
            score += 10
        if picture.regime == "ranging" and "range" in strategy.strategy_id:
            score += 10
        if picture.regime == "compressed" and "breakout" in strategy.strategy_id:
            score += 8
        if picture.regime == "volatile" and strategy.strategy_id == "momentum_scalp":
            score -= 8

        if picture.dominant_side == "neutral" and strategy.strategy_id in {
            "trend_continuation",
            "liquidity_sweep_continuation",
        }:
            score -= 10

        score = max(5.0, min(98.0, score))
        rationale = "; ".join(rationale_parts[:4]) or f"Base playbook fit for {picture.regime} regime"

        return StrategyFit(
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            fit_score=round(score, 1),
            rationale=rationale,
            entry_model=strategy.entry_model,
            stop_model=strategy.stop_model,
            target_model=strategy.target_model,
            failure_signs=strategy.failure_signs,
        )
