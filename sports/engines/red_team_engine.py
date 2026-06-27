"""Red team engine — internal critic challenging every recommendation."""

from __future__ import annotations

from sports.models import ArbitrageResult, MatchContext, RedTeamResult, ValueBetResult


class RedTeamEngine:
    """Challenge assumptions before approving recommendations."""

    MIN_EDGE_FOR_APPROVAL = 55.0
    MIN_CONFIDENCE = 50.0

    def analyze(
        self,
        context: MatchContext,
        *,
        value_bet: ValueBetResult | None,
        arbitrage: ArbitrageResult,
        edge_score: float,
        confidence: float,
        council_edge: bool,
    ) -> RedTeamResult:
        concerns: list[str] = []
        challenges: list[str] = [
            "What could go wrong?",
            "Is this data misleading?",
            "Is the market seeing something we missed?",
            "Is this supported by enough evidence?",
            "Are we falling victim to bias?",
        ]

        if not value_bet and not arbitrage.detected:
            return RedTeamResult(
                approved=False,
                concerns=("No quantitative edge identified.",),
                challenges=challenges,
                summary="REJECT — Insufficient evidence for any recommendation.",
            )

        if value_bet and value_bet.ev_pct < 5 and not arbitrage.detected:
            concerns.append(f"Marginal EV ({value_bet.ev_pct:.1f}%) — easily erased by line movement.")

        if edge_score < self.MIN_EDGE_FOR_APPROVAL:
            concerns.append(f"Edge score {edge_score:.0f} below approval threshold ({self.MIN_EDGE_FOR_APPROVAL}).")

        if confidence < self.MIN_CONFIDENCE:
            concerns.append(f"Confidence {confidence:.0f}% insufficient for action.")

        if not council_edge:
            concerns.append("Multi-agent council did not confirm edge.")

        if any("rivalry" in f.lower() or "variance" in f.lower() for f in context.context_factors):
            concerns.append("High-variance context — model uncertainty elevated.")

        if value_bet and "False" in (context.home_form.trend_label if context.home_form else ""):
            concerns.append("Home form flagged as potentially misleading.")

        if arbitrage.detected and arbitrage.profit_pct < 1.0:
            concerns.append("Thin arbitrage margin — execution risk may eliminate profit.")

        approved = len(concerns) <= 1 and (
            arbitrage.detected or (value_bet is not None and value_bet.positive_ev and edge_score >= 50)
        )

        if approved:
            summary = "APPROVED — Edge survives red team scrutiny with manageable concerns."
        elif arbitrage.detected and arbitrage.profit_pct >= 1.5:
            summary = "CONDITIONAL APPROVE — Arbitrage valid but monitor execution risk."
            approved = True
        else:
            summary = "REJECT — Weak opportunity. PASS recommended."

        return RedTeamResult(
            approved=approved,
            concerns=tuple(concerns),
            challenges=challenges,
            summary=summary,
        )
