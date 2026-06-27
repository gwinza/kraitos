"""Trade intelligence — master self-improvement metrics and over-caution detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from analytics.trade_records import EnrichedTradeRecord, RejectedOpportunityRecord, SkippedPeriodMetrics

ImprovementSignal = Literal["improving", "stable", "degrading", "insufficient_data"]
OvercautionLevel = Literal["none", "watch", "warning", "critical"]


@dataclass(frozen=True)
class CorePerformanceMetrics:
    """Primary risk-adjusted performance statistics."""

    total_trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    average_r: float
    max_drawdown: float
    gross_profit_r: float
    gross_loss_r: float
    conviction_accuracy: float
    thesis_accuracy: float

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "average_r": round(self.average_r, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "gross_profit_r": round(self.gross_profit_r, 3),
            "gross_loss_r": round(self.gross_loss_r, 3),
            "conviction_accuracy": round(self.conviction_accuracy, 4),
            "thesis_accuracy": round(self.thesis_accuracy, 4),
        }


@dataclass(frozen=True)
class OvercautionWarning:
    """Warning when filtering destroys edge."""

    level: OvercautionLevel
    triggered: bool
    trade_count_falling: bool
    missed_opportunities_rising: bool
    rejected_winners_increasing: bool
    explanation: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "triggered": self.triggered,
            "trade_count_falling": self.trade_count_falling,
            "missed_opportunities_rising": self.missed_opportunities_rising,
            "rejected_winners_increasing": self.rejected_winners_increasing,
            "explanation": self.explanation,
            "recommendations": list(self.recommendations),
        }


@dataclass(frozen=True)
class TradeIntelligenceReport:
    """Master self-improvement report."""

    core: CorePerformanceMetrics
    improvement_signal: ImprovementSignal
    overcaution: OvercautionWarning
    risk_adjusted_score: float
    summary: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "core": self.core.to_dict(),
            "improvement_signal": self.improvement_signal,
            "overcaution": self.overcaution.to_dict(),
            "risk_adjusted_score": round(self.risk_adjusted_score, 2),
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


class TradeIntelligenceEngine:
    """Compute master performance intelligence from enriched trade history."""

    def build_report(
        self,
        trades: list[EnrichedTradeRecord],
        *,
        rejected: list[RejectedOpportunityRecord] | None = None,
        period_metrics: list[SkippedPeriodMetrics] | None = None,
        initial_balance: float = 10_000.0,
    ) -> TradeIntelligenceReport:
        rejected = rejected or []
        core = self._core_metrics(trades, initial_balance)
        overcaution = self.detect_overcaution(
            trades=trades,
            rejected=rejected,
            period_metrics=period_metrics,
        )
        signal = self._improvement_signal(core)
        score = self._risk_adjusted_score(core)
        evidence = self._evidence(core, overcaution)

        summary = (
            f"Expectancy {core.expectancy:.2f}R | PF {core.profit_factor:.2f} | "
            f"Avg R {core.average_r:.2f} | Thesis accuracy {core.thesis_accuracy:.0%} | "
            f"Risk-adjusted score {score:.0f}/100"
        )

        return TradeIntelligenceReport(
            core=core,
            improvement_signal=signal,
            overcaution=overcaution,
            risk_adjusted_score=score,
            summary=summary,
            evidence=tuple(evidence),
        )

    @staticmethod
    def _core_metrics(
        trades: list[EnrichedTradeRecord],
        initial_balance: float,
    ) -> CorePerformanceMetrics:
        if not trades:
            return CorePerformanceMetrics(
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                expectancy=0.0,
                average_r=0.0,
                max_drawdown=0.0,
                gross_profit_r=0.0,
                gross_loss_r=0.0,
                conviction_accuracy=0.0,
                thesis_accuracy=0.0,
            )

        r_values = [t.r_multiple for t in trades]
        winners = [r for r in r_values if r > 0]
        losers = [r for r in r_values if r < 0]
        gross_profit_r = sum(winners)
        gross_loss_r = abs(sum(losers))
        win_rate = len(winners) / len(trades)
        avg_r = sum(r_values) / len(r_values)
        expectancy = avg_r

        if gross_loss_r > 0:
            profit_factor = gross_profit_r / gross_loss_r
        elif gross_profit_r > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        max_dd = TradeIntelligenceEngine._max_drawdown(trades, initial_balance)

        conviction_hits = 0
        conviction_total = 0
        for t in trades:
            if t.conviction_score <= 0:
                continue
            conviction_total += 1
            high_conviction = t.conviction_score >= 61
            if (high_conviction and t.won) or (not high_conviction and not t.lost):
                conviction_hits += 1
            elif t.conviction_score >= 46 and t.r_multiple >= -0.5:
                conviction_hits += 1
        conviction_accuracy = conviction_hits / conviction_total if conviction_total else 0.5

        thesis_scored = [t for t in trades if t.thesis_correct is not None]
        if thesis_scored:
            thesis_accuracy = sum(
                1.0 if t.thesis_correct else (0.5 if t.thesis_partial else 0.0)
                for t in thesis_scored
            ) / len(thesis_scored)
        else:
            thesis_accuracy = sum(1 for t in trades if t.won) / len(trades)

        return CorePerformanceMetrics(
            total_trades=len(trades),
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            expectancy=round(expectancy, 4),
            average_r=round(avg_r, 4),
            max_drawdown=round(max_dd, 4),
            gross_profit_r=round(gross_profit_r, 3),
            gross_loss_r=round(gross_loss_r, 3),
            conviction_accuracy=round(conviction_accuracy, 4),
            thesis_accuracy=round(thesis_accuracy, 4),
        )

    @staticmethod
    def _max_drawdown(trades: list[EnrichedTradeRecord], initial_balance: float) -> float:
        ordered = sorted(trades, key=lambda t: t.exit_time)
        balance = initial_balance
        peak = initial_balance
        max_dd = 0.0
        for trade in ordered:
            if trade.balance is not None:
                balance = trade.balance
            else:
                balance += trade.pnl
            peak = max(peak, balance)
            if peak > 0:
                max_dd = max(max_dd, (peak - balance) / peak)
        return max_dd

    @staticmethod
    def detect_overcaution(
        *,
        trades: list[EnrichedTradeRecord],
        rejected: list[RejectedOpportunityRecord],
        period_metrics: list[SkippedPeriodMetrics] | None = None,
    ) -> OvercautionWarning:
        rejected_winners = [r for r in rejected if r.would_have_won]
        missed_r = sum(r.missed_r for r in rejected_winners)
        lost_r = abs(sum(t.r_multiple for t in trades if t.lost))

        trade_count_falling = False
        rejected_winners_rising = len(rejected_winners) >= 3 and missed_r > lost_r * 0.8
        missed_rising = missed_r > lost_r * 1.1 if lost_r > 0 else len(rejected_winners) >= 4

        if period_metrics and len(period_metrics) >= 2:
            recent = period_metrics[-1]
            prior = period_metrics[-2]
            trade_count_falling = recent.trade_count < prior.trade_count * 0.75
            rejected_winners_rising = (
                rejected_winners_rising
                or recent.rejected_winners > prior.rejected_winners + 1
            )

        triggers = sum([trade_count_falling, missed_rising, rejected_winners_rising])
        if triggers >= 3:
            level: OvercautionLevel = "critical"
        elif triggers >= 2:
            level = "warning"
        elif triggers >= 1:
            level = "watch"
        else:
            level = "none"

        recommendations: list[str] = []
        if trade_count_falling:
            recommendations.append("Trade count falling — review conviction floors and probe logic")
        if missed_rising:
            recommendations.append(f"Missed {missed_r:.1f}R vs {lost_r:.1f}R taken — reduce over-filtering")
        if rejected_winners_rising:
            recommendations.append("Rejected winners increasing — loosen anti-paralysis thresholds")

        return OvercautionWarning(
            level=level,
            triggered=level in {"warning", "critical"},
            trade_count_falling=trade_count_falling,
            missed_opportunities_rising=missed_rising,
            rejected_winners_increasing=rejected_winners_rising,
            explanation=(
                f"Over-caution {level}: missed {missed_r:.1f}R, "
                f"{len(rejected_winners)} rejected winners"
            ),
            recommendations=tuple(recommendations or ("Filtering balanced",)),
        )

    @staticmethod
    def _improvement_signal(core: CorePerformanceMetrics) -> ImprovementSignal:
        if core.total_trades < 5:
            return "insufficient_data"
        if core.expectancy >= 0.25 and core.profit_factor >= 1.4:
            return "improving"
        if core.expectancy < 0 or core.profit_factor < 0.9:
            return "degrading"
        return "stable"

    @staticmethod
    def _risk_adjusted_score(core: CorePerformanceMetrics) -> float:
        if core.total_trades == 0:
            return 0.0
        pf_score = min(40, max(0, (core.profit_factor - 0.5) * 25))
        exp_score = min(35, max(0, (core.expectancy + 0.5) * 35))
        dd_penalty = min(25, core.max_drawdown * 50)
        thesis_bonus = core.thesis_accuracy * 15
        conviction_bonus = core.conviction_accuracy * 10
        return max(0, min(100, pf_score + exp_score + thesis_bonus + conviction_bonus - dd_penalty))

    @staticmethod
    def _evidence(core: CorePerformanceMetrics, overcaution: OvercautionWarning) -> list[str]:
        evidence = [
            f"{core.total_trades} trades — expectancy {core.expectancy:.2f}R drives success",
            f"Profit factor {core.profit_factor:.2f} (not win rate {core.win_rate:.0%} alone)",
            f"Thesis accuracy {core.thesis_accuracy:.0%}, conviction accuracy {core.conviction_accuracy:.0%}",
        ]
        if overcaution.triggered:
            evidence.append(f"OVERCAUTION {overcaution.level}: {overcaution.explanation}")
        return evidence


__all__ = [
    "CorePerformanceMetrics",
    "ImprovementSignal",
    "OvercautionLevel",
    "OvercautionWarning",
    "TradeIntelligenceEngine",
    "TradeIntelligenceReport",
]
