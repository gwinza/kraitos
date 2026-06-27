"""Explainability engine — transparent reasoning for every recommendation."""

from __future__ import annotations

from typing import Any

from sports.models import MatchAnalysis


class ExplainabilityEngine:
    """Every recommendation must explain itself — no black-box decisions."""

    def build(self, analysis: MatchAnalysis) -> dict[str, Any]:
        factors_considered = [
            "Team strength (squad quality, injuries, depth)",
            "Coach intelligence (tactical edge, overperformance)",
            "Form analysis (momentum, sustainability)",
            "xG metrics (chance quality, luck adjustment)",
            "Market intelligence (odds movement, sharp money)",
            "Context factors (motivation, fatigue, rivalry)",
            "Monte Carlo simulation (10,000 runs)",
            "Multi-agent council consensus",
            "Red team challenge",
        ]

        supporting: list[str] = []
        contradictory: list[str] = []
        risks: list[str] = []

        if analysis.value_bet and analysis.value_bet.positive_ev:
            supporting.append(
                f"Value detected: {analysis.value_bet.selection} at "
                f"{analysis.value_bet.ev_pct:+.1f}% EV."
            )
        if analysis.arbitrage and analysis.arbitrage.detected:
            supporting.append(
                f"Arbitrage: {analysis.arbitrage.profit_pct:.2f}% guaranteed margin."
            )

        if analysis.red_team and analysis.red_team.concerns:
            contradictory.extend(analysis.red_team.concerns[:3])
            risks.extend(analysis.red_team.concerns)

        if analysis.council and not analysis.council.edge_detected:
            contradictory.append("Council did not confirm edge.")

        agent_summary = []
        if analysis.council:
            for op in analysis.council.opinions[:4]:
                agent_summary.append(f"{op.agent}: {op.opinion[:80]}")

        why_selected = analysis.reasoning_summary or "No action — edge unclear."
        if analysis.decision.value == "Pass":
            why_selected = analysis.pass_reason or "PASS — No Edge Detected."

        prediction_block: dict[str, Any] = {}
        if analysis.prediction:
            prediction_block = {
                "predicted_outcome": analysis.prediction,
                "prediction_confidence": analysis.prediction_confidence,
                "why_this_prediction": analysis.prediction_reasoning,
                "reasoning_factors": (
                    analysis.prediction_detail.get("reasons", [])
                    if analysis.prediction_detail
                    else []
                ),
                "model_vs_market": {
                    "model_view": analysis.prediction_detail.get("model_view"),
                    "market_view": analysis.prediction_detail.get("market_view"),
                    "divergence": analysis.prediction_detail.get("divergence"),
                },
                "caveats": (
                    analysis.prediction_detail.get("caveats", [])
                    if analysis.prediction_detail
                    else []
                ),
                "alternative_outcomes": (
                    analysis.prediction_detail.get("alternative_outcomes", [])
                    if analysis.prediction_detail
                    else []
                ),
            }

        return {
            "why_selected": why_selected,
            "prediction_explanation": prediction_block or None,
            "supporting_evidence": supporting,
            "contradictory_evidence": contradictory,
            "confidence_score": analysis.confidence,
            "risks_identified": risks,
            "factors_considered": factors_considered,
            "agent_opinions": agent_summary,
            "golden_rule": "Data → Probability → Value → Risk → Decision",
            "human_in_the_loop": (
                "Kraitos provides intelligence. The human provides execution. "
                "No automatic bet placement."
            ),
        }
