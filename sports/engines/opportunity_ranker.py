"""Opportunity ranking — edge score, grade, and sort order."""

from __future__ import annotations

from sports.models import (
    ArbitrageResult,
    Decision,
    MatchAnalysis,
    OpportunityGrade,
    RiskLevel,
    ValueBetResult,
)


class OpportunityRanker:
    """Assign edge score, confidence, grade, and risk level."""

    def rank(
        self,
        analysis: MatchAnalysis,
        *,
        value_bet: ValueBetResult | None,
        arbitrage: ArbitrageResult,
        council_confidence: float,
        context_risk: float,
    ) -> MatchAnalysis:
        edge = 0.0
        confidence = 40.0

        if arbitrage.detected:
            edge = min(100, 60 + arbitrage.profit_pct * 8)
            confidence = 90.0
            analysis.decision = Decision.ARBITRAGE
            analysis.risk_level = arbitrage.risk_level
        elif value_bet and value_bet.positive_ev:
            edge = min(100, value_bet.value_score * 0.7 + value_bet.ev_pct * 2)
            confidence = (value_bet.confidence + council_confidence) / 2
            analysis.decision = Decision.VALUE_BET
            analysis.risk_level = self._ev_risk(value_bet.ev_pct, context_risk)
        elif value_bet and value_bet.ev_pct > 0:
            edge = value_bet.value_score * 0.4
            confidence = value_bet.confidence * 0.7
            analysis.decision = Decision.WATCHLIST
            analysis.risk_level = RiskLevel.MEDIUM
        else:
            edge = max(0, 30 - context_risk)
            confidence = 35.0
            analysis.decision = Decision.PASS
            analysis.pass_reason = self._pass_reason(context_risk)
            analysis.risk_level = RiskLevel.LOW

        edge = max(0, edge - context_risk * 0.5)
        analysis.edge_score = round(edge, 1)
        analysis.confidence = round(confidence, 1)
        analysis.grade = self._grade(edge, confidence, analysis.decision)

        if analysis.red_team and not analysis.red_team.approved:
            if analysis.decision != Decision.ARBITRAGE or not arbitrage.detected:
                analysis.decision = Decision.PASS
                analysis.pass_reason = "PASS — Capital Preservation Mode Activated."
                analysis.grade = OpportunityGrade.PASS

        return analysis

    def sort_analyses(self, analyses: list[MatchAnalysis]) -> list[MatchAnalysis]:
        return sorted(
            analyses,
            key=lambda a: (a.decision.value != "Pass", a.edge_score, a.confidence),
            reverse=True,
        )

    def _grade(
        self, edge: float, confidence: float, decision: Decision
    ) -> OpportunityGrade:
        if decision == Decision.PASS:
            return OpportunityGrade.PASS
        combined = edge * 0.6 + confidence * 0.4
        if combined >= 85:
            return OpportunityGrade.A_PLUS
        if combined >= 70:
            return OpportunityGrade.A
        if combined >= 55:
            return OpportunityGrade.B
        return OpportunityGrade.C

    def _ev_risk(self, ev_pct: float, context_risk: float) -> RiskLevel:
        if ev_pct >= 10 and context_risk < 8:
            return RiskLevel.LOW
        if ev_pct >= 5:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    def _pass_reason(self, context_risk: float) -> str:
        if context_risk > 10:
            return "PASS — Capital Preservation Mode Activated."
        return "PASS — No Edge Detected."
