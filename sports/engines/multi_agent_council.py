"""Multi-agent council — specialist agents with consensus mechanism."""

from __future__ import annotations

from sports.models import (
    AgentOpinion,
    ArbitrageResult,
    CouncilSummary,
    MatchContext,
    ValueBetResult,
)


class MultiAgentCouncil:
    """Specialist agents produce opinions; council synthesises consensus."""

    AGENTS = (
        "Value Expert",
        "Arbitrage Expert",
        "Team Analyst",
        "Coach Analyst",
        "xG Analyst",
        "Market Analyst",
        "Match Context Analyst",
        "Risk Analyst",
    )

    def analyze(
        self,
        context: MatchContext,
        *,
        team_strength: str,
        coach_analysis: str,
        form_analysis: str,
        xg_analysis: str,
        market_intelligence: str,
        context_summary: str,
        value_bet: ValueBetResult | None,
        arbitrage: ArbitrageResult,
        edge_score: float,
        risk_penalty: float,
    ) -> CouncilSummary:
        opinions: list[AgentOpinion] = []

        if value_bet and value_bet.positive_ev:
            opinions.append(
                AgentOpinion(
                    agent="Value Expert",
                    opinion=f"Positive EV on {value_bet.selection} ({value_bet.ev_pct:+.1f}%).",
                    confidence=value_bet.confidence,
                    evidence=(f"Fair odds {value_bet.fair_odds:.2f}", f"Market {value_bet.market_odds:.2f}"),
                )
            )
        else:
            opinions.append(
                AgentOpinion(
                    agent="Value Expert",
                    opinion="No clear value edge detected.",
                    confidence=70.0,
                    evidence=("Market efficiently priced",),
                )
            )

        if arbitrage.detected:
            opinions.append(
                AgentOpinion(
                    agent="Arbitrage Expert",
                    opinion=f"Arbitrage confirmed: {arbitrage.profit_pct:.2f}% margin.",
                    confidence=92.0,
                    evidence=arbitrage.bookmakers,
                )
            )
        else:
            opinions.append(
                AgentOpinion(
                    agent="Arbitrage Expert",
                    opinion="No arbitrage opportunity.",
                    confidence=85.0,
                )
            )

        opinions.extend(
            [
                AgentOpinion(
                    agent="Team Analyst",
                    opinion=team_strength[:120] + ("..." if len(team_strength) > 120 else ""),
                    confidence=75.0,
                    evidence=("Squad quality adjusted",),
                ),
                AgentOpinion(
                    agent="Coach Analyst",
                    opinion=coach_analysis[:120] if coach_analysis else "Limited coach data.",
                    confidence=65.0,
                ),
                AgentOpinion(
                    agent="xG Analyst",
                    opinion=xg_analysis[:120] if xg_analysis else "xG data limited.",
                    confidence=70.0 if xg_analysis else 40.0,
                ),
                AgentOpinion(
                    agent="Market Analyst",
                    opinion=market_intelligence[:120],
                    confidence=68.0,
                ),
                AgentOpinion(
                    agent="Match Context Analyst",
                    opinion=context_summary[:120] if context_summary else "Standard context.",
                    confidence=60.0,
                ),
                AgentOpinion(
                    agent="Risk Analyst",
                    opinion=f"Edge score {edge_score:.0f}/100. Context risk penalty {risk_penalty:.0f}.",
                    confidence=max(30.0, 100 - risk_penalty),
                    evidence=("Portfolio correlation check pending",),
                ),
            ]
        )

        confidences = [o.confidence for o in opinions if "No " not in o.opinion[:5]]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 40.0
        edge_votes = sum(
            1
            for o in opinions
            if any(kw in o.opinion.lower() for kw in ("ev", "arbitrage", "value", "edge", "underrated"))
        )
        edge_detected = edge_votes >= 2 or arbitrage.detected or (
            value_bet is not None and value_bet.positive_ev
        )

        if edge_detected:
            consensus = (
                f"Council detects potential edge on {context.home_team} vs {context.away_team}. "
                f"{edge_votes} specialists flag opportunity."
            )
        else:
            consensus = "Council consensus: No actionable edge — capital preservation recommended."

        return CouncilSummary(
            consensus=consensus,
            confidence=avg_confidence,
            opinions=tuple(opinions),
            edge_detected=edge_detected,
        )
