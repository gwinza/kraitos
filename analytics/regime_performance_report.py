"""Regime performance report — performance by market regime."""

from __future__ import annotations

from dataclasses import dataclass, field

from analytics.trade_records import EnrichedTradeRecord, RegimeLabel

REGIME_BUCKETS: tuple[RegimeLabel, ...] = (
    "trend",
    "range",
    "breakout",
    "reversal",
    "chaos",
    "unknown",
)


@dataclass(frozen=True)
class RegimePerformanceSlice:
    """Performance statistics for one regime bucket."""

    regime: RegimeLabel
    trade_count: int
    win_rate: float
    profit_factor: float
    expectancy: float
    average_r: float
    conviction_accuracy: float
    thesis_accuracy: float
    net_r: float

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "trade_count": self.trade_count,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "average_r": round(self.average_r, 4),
            "conviction_accuracy": round(self.conviction_accuracy, 4),
            "thesis_accuracy": round(self.thesis_accuracy, 4),
            "net_r": round(self.net_r, 3),
        }


@dataclass(frozen=True)
class RegimePerformanceReport:
    """Full regime breakdown."""

    slices: tuple[RegimePerformanceSlice, ...]
    best_regime: RegimeLabel
    worst_regime: RegimeLabel
    strongest_expectancy_regime: RegimeLabel
    summary: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "slices": [s.to_dict() for s in self.slices],
            "best_regime": self.best_regime,
            "worst_regime": self.worst_regime,
            "strongest_expectancy_regime": self.strongest_expectancy_regime,
            "summary": self.summary,
            "recommendations": list(self.recommendations),
        }


class RegimePerformanceReporter:
    """Show performance by trend, range, breakout, reversal, and chaos."""

    def build(self, trades: list[EnrichedTradeRecord]) -> RegimePerformanceReport:
        slices: list[RegimePerformanceSlice] = []
        for regime in REGIME_BUCKETS:
            bucket = [t for t in trades if self._normalize_regime(t.primary_regime) == regime]
            if not bucket and regime == "unknown":
                continue
            slices.append(self._slice(regime, bucket))

        active = [s for s in slices if s.trade_count > 0]
        if not active:
            return RegimePerformanceReport(
                slices=tuple(slices),
                best_regime="unknown",
                worst_regime="unknown",
                strongest_expectancy_regime="unknown",
                summary="No trades to analyse by regime",
            )

        best = max(active, key=lambda s: s.net_r).regime
        worst = min(active, key=lambda s: s.net_r).regime
        strongest = max(active, key=lambda s: s.expectancy).regime

        recommendations: list[str] = []
        for s in active:
            if s.expectancy >= 0.3 and s.trade_count >= 3:
                recommendations.append(f"Increase allocation in {s.regime} — expectancy {s.expectancy:.2f}R")
            if s.expectancy < -0.2 and s.trade_count >= 3:
                recommendations.append(f"Review {s.regime} logic — negative expectancy {s.expectancy:.2f}R")

        return RegimePerformanceReport(
            slices=tuple(slices),
            best_regime=best,
            worst_regime=worst,
            strongest_expectancy_regime=strongest,
            summary=(
                f"Best regime: {best} | Strongest expectancy: {strongest} | "
                f"Weakest: {worst}"
            ),
            recommendations=tuple(recommendations or ("Gather more regime-tagged trades",)),
        )

    @staticmethod
    def _normalize_regime(regime: str) -> RegimeLabel:
        r = (regime or "").lower()
        if r in {"trend", "trending"}:
            return "trend"
        if r in {"range", "ranging", "mean_reversion"}:
            return "range"
        if r in {"breakout", "breakout_preparation", "breakout_in_progress"}:
            return "breakout"
        if r in {"reversal", "reversal_warning", "confirmed_reversal"}:
            return "reversal"
        if r in {"chaos", "volatile", "transition"}:
            return "chaos"
        return "unknown"

    @staticmethod
    def _slice(regime: RegimeLabel, trades: list[EnrichedTradeRecord]) -> RegimePerformanceSlice:
        if not trades:
            return RegimePerformanceSlice(
                regime=regime,
                trade_count=0,
                win_rate=0.0,
                profit_factor=0.0,
                expectancy=0.0,
                average_r=0.0,
                conviction_accuracy=0.0,
                thesis_accuracy=0.0,
                net_r=0.0,
            )

        r_values = [t.r_multiple for t in trades]
        winners = [r for r in r_values if r > 0]
        losers = [r for r in r_values if r < 0]
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        avg_r = sum(r_values) / len(r_values)

        conv_hits = sum(
            1 for t in trades
            if t.conviction_score >= 61 and t.won or t.conviction_score < 61 and not t.lost
        )
        conv_total = sum(1 for t in trades if t.conviction_score > 0)
        conv_acc = conv_hits / conv_total if conv_total else 0.5

        thesis_scored = [t for t in trades if t.thesis_correct is not None]
        if thesis_scored:
            thesis_acc = sum(
                1.0 if t.thesis_correct else (0.5 if t.thesis_partial else 0.0)
                for t in thesis_scored
            ) / len(thesis_scored)
        else:
            thesis_acc = len(winners) / len(trades)

        return RegimePerformanceSlice(
            regime=regime,
            trade_count=len(trades),
            win_rate=len(winners) / len(trades),
            profit_factor=min(pf, 999.0),
            expectancy=avg_r,
            average_r=avg_r,
            conviction_accuracy=conv_acc,
            thesis_accuracy=thesis_acc,
            net_r=sum(r_values),
        )


__all__ = [
    "RegimePerformanceReport",
    "RegimePerformanceReporter",
    "RegimePerformanceSlice",
]
