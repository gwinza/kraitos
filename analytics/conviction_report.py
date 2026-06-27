"""Conviction report — measure conviction score vs trade outcome."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from analytics.trade_records import EnrichedTradeRecord

ConvictionBucket = Literal["avoid", "watchlist", "probe", "normal", "aggressive", "unscored"]


@dataclass(frozen=True)
class ConvictionBucketStats:
    """Outcome stats for a conviction participation band."""

    bucket: ConvictionBucket
    trade_count: int
    win_rate: float
    average_r: float
    expectancy: float
    profit_factor: float
    calibration_score: float

    def to_dict(self) -> dict:
        return {
            "bucket": self.bucket,
            "trade_count": self.trade_count,
            "win_rate": round(self.win_rate, 4),
            "average_r": round(self.average_r, 4),
            "expectancy": round(self.expectancy, 4),
            "profit_factor": round(self.profit_factor, 4),
            "calibration_score": round(self.calibration_score, 4),
        }


@dataclass(frozen=True)
class ConvictionReport:
    """Conviction vs outcome analysis."""

    overall_conviction_accuracy: float
    high_conviction_win_rate: float
    probe_conviction_expectancy: float
    buckets: tuple[ConvictionBucketStats, ...]
    conviction_outcome_correlation: float
    miscalibrated: bool
    summary: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "overall_conviction_accuracy": round(self.overall_conviction_accuracy, 4),
            "high_conviction_win_rate": round(self.high_conviction_win_rate, 4),
            "probe_conviction_expectancy": round(self.probe_conviction_expectancy, 4),
            "buckets": [b.to_dict() for b in self.buckets],
            "conviction_outcome_correlation": round(self.conviction_outcome_correlation, 4),
            "miscalibrated": self.miscalibrated,
            "summary": self.summary,
            "recommendations": list(self.recommendations),
        }


class ConvictionReporter:
    """Measure whether conviction scores predict outcomes."""

    BUCKETS: tuple[ConvictionBucket, ...] = (
        "avoid", "watchlist", "probe", "normal", "aggressive", "unscored"
    )

    def build(self, trades: list[EnrichedTradeRecord]) -> ConvictionReport:
        buckets = [self._bucket_stats(b, trades) for b in self.BUCKETS]
        scored = [t for t in trades if t.conviction_score > 0]

        overall_acc = self._conviction_accuracy(scored)
        high = [t for t in scored if t.conviction_score >= 61]
        probe = [t for t in scored if 46 <= t.conviction_score < 61]
        high_wr = sum(1 for t in high if t.won) / len(high) if high else 0.0
        probe_exp = sum(t.r_multiple for t in probe) / len(probe) if probe else 0.0

        correlation = self._correlation(scored)
        miscalibrated = correlation < 0.15 and len(scored) >= 10

        recommendations: list[str] = []
        if miscalibrated:
            recommendations.append("Conviction miscalibrated — recalibrate module weights")
        probe_stats = next((b for b in buckets if b.bucket == "probe"), None)
        if probe_stats and probe_stats.trade_count >= 3 and probe_stats.expectancy > 0.2:
            recommendations.append("Probe band profitable — expand probe participation")
        aggressive = next((b for b in buckets if b.bucket == "aggressive"), None)
        if aggressive and aggressive.trade_count >= 3 and aggressive.expectancy < 0:
            recommendations.append("Aggressive band underperforming — tighten attack threshold")

        return ConvictionReport(
            overall_conviction_accuracy=overall_acc,
            high_conviction_win_rate=high_wr,
            probe_conviction_expectancy=probe_exp,
            buckets=tuple(buckets),
            conviction_outcome_correlation=correlation,
            miscalibrated=miscalibrated,
            summary=(
                f"Conviction accuracy {overall_acc:.0%} | "
                f"high-conviction win rate {high_wr:.0%} | "
                f"probe expectancy {probe_exp:.2f}R"
            ),
            recommendations=tuple(recommendations or ("Conviction calibration adequate",)),
        )

    def _bucket_stats(
        self, bucket: ConvictionBucket, trades: list[EnrichedTradeRecord]
    ) -> ConvictionBucketStats:
        bucket_trades = [t for t in trades if self._assign_bucket(t) == bucket]
        if not bucket_trades:
            return ConvictionBucketStats(
                bucket=bucket,
                trade_count=0,
                win_rate=0.0,
                average_r=0.0,
                expectancy=0.0,
                profit_factor=0.0,
                calibration_score=0.0,
            )

        r_values = [t.r_multiple for t in bucket_trades]
        winners = [r for r in r_values if r > 0]
        losers = [r for r in r_values if r < 0]
        gp = sum(winners)
        gl = abs(sum(losers))
        pf = gp / gl if gl > 0 else (999.0 if gp > 0 else 0.0)
        avg_r = sum(r_values) / len(r_values)
        wr = len(winners) / len(bucket_trades)

        expected_wr = {"avoid": 0.35, "watchlist": 0.42, "probe": 0.48, "normal": 0.55, "aggressive": 0.62}.get(
            bucket, 0.50
        )
        calibration = 1.0 - min(1.0, abs(wr - expected_wr))

        return ConvictionBucketStats(
            bucket=bucket,
            trade_count=len(bucket_trades),
            win_rate=wr,
            average_r=avg_r,
            expectancy=avg_r,
            profit_factor=min(pf, 999.0),
            calibration_score=calibration,
        )

    @staticmethod
    def _assign_bucket(trade: EnrichedTradeRecord) -> ConvictionBucket:
        mode = (trade.participation_mode or "").lower()
        if mode in {"avoid", "watchlist", "probe", "normal", "aggressive"}:
            return mode  # type: ignore[return-value]
        score = trade.conviction_score
        if score <= 0:
            return "unscored"
        if score <= 25:
            return "avoid"
        if score <= 45:
            return "watchlist"
        if score <= 60:
            return "probe"
        if score <= 80:
            return "normal"
        return "aggressive"

    @staticmethod
    def _conviction_accuracy(trades: list[EnrichedTradeRecord]) -> float:
        if not trades:
            return 0.0
        hits = 0
        for t in trades:
            predicted_win = t.conviction_score >= 61
            if (predicted_win and t.won) or (not predicted_win and t.r_multiple >= -0.3):
                hits += 1
        return hits / len(trades)

    @staticmethod
    def _correlation(trades: list[EnrichedTradeRecord]) -> float:
        if len(trades) < 3:
            return 0.0
        scores = [t.conviction_score for t in trades]
        outcomes = [1.0 if t.won else 0.0 for t in trades]
        mean_s = sum(scores) / len(scores)
        mean_o = sum(outcomes) / len(outcomes)
        num = sum((s - mean_s) * (o - mean_o) for s, o in zip(scores, outcomes))
        den_s = sum((s - mean_s) ** 2 for s in scores) ** 0.5
        den_o = sum((o - mean_o) ** 2 for o in outcomes) ** 0.5
        if den_s <= 0 or den_o <= 0:
            return 0.0
        return num / (den_s * den_o)


__all__ = ["ConvictionBucketStats", "ConvictionReport", "ConvictionReporter"]
