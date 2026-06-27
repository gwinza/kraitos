"""Thesis accuracy report — thesis, invalidation, and exit quality."""

from __future__ import annotations

from dataclasses import dataclass, field

from analytics.trade_records import EnrichedTradeRecord


@dataclass(frozen=True)
class ThesisQualityMetrics:
    """Thesis construction quality."""

    thesis_accuracy: float
    partial_accuracy: float
    thesis_confidence_calibration: float
    sample_size: int

    def to_dict(self) -> dict:
        return {
            "thesis_accuracy": round(self.thesis_accuracy, 4),
            "partial_accuracy": round(self.partial_accuracy, 4),
            "thesis_confidence_calibration": round(self.thesis_confidence_calibration, 4),
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class InvalidationQualityMetrics:
    """How well invalidation levels protected capital."""

    invalidation_hit_rate: float
    avg_loss_when_invalidated: float
    premature_invalidation_rate: float
    sample_size: int

    def to_dict(self) -> dict:
        return {
            "invalidation_hit_rate": round(self.invalidation_hit_rate, 4),
            "avg_loss_when_invalidated": round(self.avg_loss_when_invalidated, 4),
            "premature_invalidation_rate": round(self.premature_invalidation_rate, 4),
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class ExitQualityMetrics:
    """Exit timing quality."""

    exit_quality_score: float
    winners_cut_early_rate: float
    losers_held_too_long_rate: float
    avg_winner_r: float
    avg_loser_r: float
    sample_size: int

    def to_dict(self) -> dict:
        return {
            "exit_quality_score": round(self.exit_quality_score, 4),
            "winners_cut_early_rate": round(self.winners_cut_early_rate, 4),
            "losers_held_too_long_rate": round(self.losers_held_too_long_rate, 4),
            "avg_winner_r": round(self.avg_winner_r, 4),
            "avg_loser_r": round(self.avg_loser_r, 4),
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class ThesisAccuracyReport:
    """Full thesis lifecycle quality report."""

    thesis_quality: ThesisQualityMetrics
    invalidation_quality: InvalidationQualityMetrics
    exit_quality: ExitQualityMetrics
    market_reading_score: float
    summary: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "thesis_quality": self.thesis_quality.to_dict(),
            "invalidation_quality": self.invalidation_quality.to_dict(),
            "exit_quality": self.exit_quality.to_dict(),
            "market_reading_score": round(self.market_reading_score, 2),
            "summary": self.summary,
            "recommendations": list(self.recommendations),
        }


class ThesisAccuracyReporter:
    """Measure thesis quality, invalidation quality, and exit quality."""

    def build(self, trades: list[EnrichedTradeRecord]) -> ThesisAccuracyReport:
        thesis_q = self._thesis_quality(trades)
        inv_q = self._invalidation_quality(trades)
        exit_q = self._exit_quality(trades)

        reading_score = (
            thesis_q.thesis_accuracy * 35
            + inv_q.invalidation_hit_rate * 25
            + exit_q.exit_quality_score * 40
        )

        recommendations: list[str] = []
        if thesis_q.thesis_accuracy < 0.45 and thesis_q.sample_size >= 5:
            recommendations.append("Thesis accuracy low — improve market story engine")
        if inv_q.avg_loss_when_invalidated > 1.1:
            recommendations.append("Invalidation too wide — tighten stop geometry")
        if exit_q.winners_cut_early_rate > 0.35:
            recommendations.append("Cutting winners early — extend thesis protection phase")
        if exit_q.losers_held_too_long_rate > 0.40:
            recommendations.append("Holding losers too long — enable fast failure engine")

        return ThesisAccuracyReport(
            thesis_quality=thesis_q,
            invalidation_quality=inv_q,
            exit_quality=exit_q,
            market_reading_score=min(100, reading_score),
            summary=(
                f"Thesis {thesis_q.thesis_accuracy:.0%} | "
                f"Invalidation quality {inv_q.invalidation_hit_rate:.0%} | "
                f"Exit quality {exit_q.exit_quality_score:.0%}"
            ),
            recommendations=tuple(recommendations or ("Thesis lifecycle quality adequate",)),
        )

    @staticmethod
    def _thesis_quality(trades: list[EnrichedTradeRecord]) -> ThesisQualityMetrics:
        scored = [t for t in trades if t.thesis_correct is not None]
        if not scored:
            wins = sum(1 for t in trades if t.won)
            return ThesisQualityMetrics(
                thesis_accuracy=wins / len(trades) if trades else 0.0,
                partial_accuracy=0.0,
                thesis_confidence_calibration=0.5,
                sample_size=len(trades),
            )

        correct = sum(1 for t in scored if t.thesis_correct)
        partial = sum(1 for t in scored if t.thesis_partial and not t.thesis_correct)
        accuracy = correct / len(scored)
        partial_acc = partial / len(scored)

        calibration_hits = 0
        conf_scored = [t for t in scored if t.thesis_confidence > 0]
        for t in conf_scored:
            predicted = t.thesis_confidence >= 0.55
            actual = t.thesis_correct or t.thesis_partial
            if predicted == bool(actual):
                calibration_hits += 1
        calibration = calibration_hits / len(conf_scored) if conf_scored else 0.5

        return ThesisQualityMetrics(
            thesis_accuracy=accuracy,
            partial_accuracy=partial_acc,
            thesis_confidence_calibration=calibration,
            sample_size=len(scored),
        )

    @staticmethod
    def _invalidation_quality(trades: list[EnrichedTradeRecord]) -> InvalidationQualityMetrics:
        with_inv = [t for t in trades if t.invalidation_quality > 0 or t.lost]
        if not with_inv:
            return InvalidationQualityMetrics(0.0, 0.0, 0.0, 0)

        losers = [t for t in with_inv if t.lost]
        hit_rate = len(losers) / len(with_inv) if with_inv else 0.0
        avg_loss = abs(sum(t.r_multiple for t in losers) / len(losers)) if losers else 0.0

        premature = [
            t for t in trades
            if t.won and t.r_multiple < 0.8 and t.invalidation_quality >= 0.7
        ]
        premature_rate = len(premature) / len([t for t in trades if t.won]) if any(t.won for t in trades) else 0.0

        return InvalidationQualityMetrics(
            invalidation_hit_rate=hit_rate,
            avg_loss_when_invalidated=avg_loss,
            premature_invalidation_rate=premature_rate,
            sample_size=len(with_inv),
        )

    @staticmethod
    def _exit_quality(trades: list[EnrichedTradeRecord]) -> ExitQualityMetrics:
        if not trades:
            return ExitQualityMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0)

        with_exit = [t for t in trades if t.exit_quality > 0]
        exit_score = (
            sum(t.exit_quality for t in with_exit) / len(with_exit)
            if with_exit
            else 0.5
        )

        winners = [t for t in trades if t.won]
        losers = [t for t in trades if t.lost]
        cut_early = [t for t in winners if t.r_multiple < 1.0 and t.exit_quality < 0.5]
        held_long = [t for t in losers if t.r_multiple < -0.8]

        return ExitQualityMetrics(
            exit_quality_score=exit_score,
            winners_cut_early_rate=len(cut_early) / len(winners) if winners else 0.0,
            losers_held_too_long_rate=len(held_long) / len(losers) if losers else 0.0,
            avg_winner_r=sum(t.r_multiple for t in winners) / len(winners) if winners else 0.0,
            avg_loser_r=sum(t.r_multiple for t in losers) / len(losers) if losers else 0.0,
            sample_size=len(trades),
        )


__all__ = [
    "ExitQualityMetrics",
    "InvalidationQualityMetrics",
    "ThesisAccuracyReport",
    "ThesisAccuracyReporter",
    "ThesisQualityMetrics",
]
