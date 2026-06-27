"""Opportunity cost report — measure what over-filtering costs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from analytics.trade_intelligence import OvercautionLevel, TradeIntelligenceEngine
from analytics.trade_records import EnrichedTradeRecord, RejectedOpportunityRecord, SkippedPeriodMetrics

OverfilterVerdict = Literal["balanced", "over_cautious", "under_disciplined"]


@dataclass(frozen=True)
class OpportunityCostReport:
    """Report on rejected winners vs accepted losers."""

    profitable_rejected_trades: int
    losing_accepted_trades: int
    missed_r: float
    missed_profit: float
    accepted_loss_r: float
    opportunity_cost_ratio: float
    over_caution_detected: bool
    overcaution_level: OvercautionLevel
    verdict: OverfilterVerdict
    explanation: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "profitable_rejected_trades": self.profitable_rejected_trades,
            "losing_accepted_trades": self.losing_accepted_trades,
            "missed_r": round(self.missed_r, 3),
            "missed_profit": round(self.missed_profit, 3),
            "accepted_loss_r": round(self.accepted_loss_r, 3),
            "opportunity_cost_ratio": round(self.opportunity_cost_ratio, 3),
            "over_caution_detected": self.over_caution_detected,
            "overcaution_level": self.overcaution_level,
            "verdict": self.verdict,
            "explanation": self.explanation,
            "recommendations": list(self.recommendations),
        }


class OpportunityCostReporter:
    """Build opportunity cost analytics for self-improvement."""

    def build(
        self,
        *,
        accepted_trades: list[EnrichedTradeRecord],
        rejected: list[RejectedOpportunityRecord],
        period_metrics: list[SkippedPeriodMetrics] | None = None,
    ) -> OpportunityCostReport:
        rejected_winners = [r for r in rejected if r.would_have_won]
        accepted_losers = [t for t in accepted_trades if t.lost]

        missed_r = sum(r.missed_r for r in rejected_winners)
        missed_profit = sum(r.missed_profit for r in rejected_winners)
        accepted_loss_r = abs(sum(t.r_multiple for t in accepted_losers))

        ratio = missed_r / max(accepted_loss_r, 0.01)

        overcaution = TradeIntelligenceEngine.detect_overcaution(
            trades=accepted_trades,
            rejected=rejected,
            period_metrics=period_metrics,
        )

        if ratio >= 1.25 and missed_r > accepted_loss_r:
            verdict: OverfilterVerdict = "over_cautious"
        elif ratio <= 0.6 and accepted_loss_r > missed_r * 1.5:
            verdict = "under_disciplined"
        else:
            verdict = "balanced"

        recommendations = list(overcaution.recommendations)
        if verdict == "over_cautious":
            recommendations.append("Increase probe participation — missed edge exceeds avoided losses")
        elif verdict == "under_disciplined":
            recommendations.append("Tighten conviction floors — accepting too many losers")

        return OpportunityCostReport(
            profitable_rejected_trades=len(rejected_winners),
            losing_accepted_trades=len(accepted_losers),
            missed_r=missed_r,
            missed_profit=missed_profit,
            accepted_loss_r=accepted_loss_r,
            opportunity_cost_ratio=ratio,
            over_caution_detected=overcaution.triggered,
            overcaution_level=overcaution.level,
            verdict=verdict,
            explanation=(
                f"Opportunity cost ratio {ratio:.2f} — "
                f"missed {missed_r:.1f}R vs accepted losses {accepted_loss_r:.1f}R"
            ),
            recommendations=tuple(dict.fromkeys(recommendations)),
        )


__all__ = ["OpportunityCostReport", "OpportunityCostReporter", "OverfilterVerdict"]
