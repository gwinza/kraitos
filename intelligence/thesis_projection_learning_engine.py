"""
Self-learning layer for thesis-projected entry and exit levels.

Learns from closed journal outcomes per personality|side|session bucket and adapts
TP geometry, size, and stagnation exit timing — never blocks entries.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

LEARNING_FILENAME = "thesis_projection_learning.json"
MIN_BUCKET_SAMPLES = 8
WIN_RATE_TIGHTEN = 0.40
WIN_RATE_LOOSEN = 0.55
AVG_R_TIGHTEN = -0.10
AVG_R_LOOSEN = 0.15


def _normalize_trade_id(trade_id: str) -> str:
    return trade_id.replace(":", "-")[:64]


@dataclass(frozen=True)
class ThesisProjectionAdjustments:
    tp1_r_multiplier: float = 1.0
    size_multiplier_delta: float = 0.0
    stagnation_bars_delta: int = 0


@dataclass
class ThesisProjectionBucketStats:
    samples: int = 0
    wins: int = 0
    total_r: float = 0.0
    tp1_r_multiplier: float = 1.0
    size_multiplier_delta: float = 0.0
    stagnation_bars_delta: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.samples if self.samples else 0.0

    @property
    def avg_r(self) -> float:
        return self.total_r / self.samples if self.samples else 0.0


@dataclass
class ThesisProjectionLearningEngine:
    project_root: Path
    buckets: dict[str, ThesisProjectionBucketStats] = field(default_factory=dict)
    pending: dict[str, dict] = field(default_factory=dict)
    successful_lifecycle_patterns: dict[str, int] = field(default_factory=dict)
    successful_retracement_patterns: dict[str, int] = field(default_factory=dict)
    successful_reversal_patterns: dict[str, int] = field(default_factory=dict)
    failed_retracement_classifications: dict[str, int] = field(default_factory=dict)
    failed_reversal_classifications: dict[str, int] = field(default_factory=dict)
    failed_distribution_detections: dict[str, int] = field(default_factory=dict)

    def bucket_key(
        self,
        *,
        personality: str,
        side: str,
        in_active_session: bool,
    ) -> str:
        session = "active" if in_active_session else "off"
        return f"{personality}|{side}|{session}"

    def get_adjustments(
        self,
        *,
        personality: str,
        side: str,
        in_active_session: bool,
    ) -> ThesisProjectionAdjustments:
        key = self.bucket_key(
            personality=personality,
            side=side,
            in_active_session=in_active_session,
        )
        bucket = self.buckets.get(key)
        if bucket is None:
            return ThesisProjectionAdjustments()
        return ThesisProjectionAdjustments(
            tp1_r_multiplier=bucket.tp1_r_multiplier,
            size_multiplier_delta=bucket.size_multiplier_delta,
            stagnation_bars_delta=bucket.stagnation_bars_delta,
        )

    def record_pending_entry(
        self,
        *,
        trade_id: str,
        personality: str,
        side: str,
        in_active_session: bool,
        thesis_confidence: float,
        projected_reward_r: float,
        lifecycle_pattern: str = "",
        retracement_pattern: str = "",
        reversal_pattern: str = "",
        distribution_pattern: str = "",
    ) -> None:
        self.pending[_normalize_trade_id(trade_id)] = {
            "personality": personality,
            "side": side,
            "in_active_session": in_active_session,
            "thesis_confidence": thesis_confidence,
            "projected_reward_r": projected_reward_r,
            "lifecycle_pattern": lifecycle_pattern,
            "retracement_pattern": retracement_pattern,
            "reversal_pattern": reversal_pattern,
            "distribution_pattern": distribution_pattern,
        }

    def refresh_from_journal(self, journal_path: Path) -> None:
        if not journal_path.exists():
            return
        import pandas as pd

        frame = pd.read_csv(journal_path)
        if frame.empty:
            return

        id_col = "trace_id" if "trace_id" in frame.columns else "trade_id"
        if id_col not in frame.columns:
            return

        closed = frame[frame["result"].isin({"win", "loss", "breakeven"})].copy()
        for _, row in closed.iterrows():
            trade_id = _normalize_trade_id(str(row.get(id_col, "")))
            pending = self.pending.pop(trade_id, None)
            if pending is None:
                for key, val in list(self.pending.items()):
                    if _normalize_trade_id(key) == trade_id:
                        pending = self.pending.pop(key)
                        break
            if pending is None:
                continue
            r_mult = float(row.get("r_multiple", 0.0) or 0.0)
            net_col = "net_pl" if "net_pl" in row.index else "profit_loss"
            net = float(row.get(net_col, 0.0) or 0.0)
            won = net > 0.01 or r_mult > 0.05
            key = self.bucket_key(
                personality=str(pending["personality"]),
                side=str(pending["side"]),
                in_active_session=bool(pending["in_active_session"]),
            )
            bucket = self.buckets.setdefault(key, ThesisProjectionBucketStats())
            bucket.samples += 1
            bucket.total_r += r_mult
            if won:
                bucket.wins += 1
            self._record_lifecycle_learning(pending, won=won)
            self._adapt_bucket(bucket)

        self._persist()

    def _adapt_bucket(self, bucket: ThesisProjectionBucketStats) -> None:
        if bucket.samples < MIN_BUCKET_SAMPLES:
            return
        wr = bucket.win_rate
        avg_r = bucket.avg_r
        if wr < WIN_RATE_TIGHTEN or avg_r < AVG_R_TIGHTEN:
            bucket.tp1_r_multiplier = max(0.75, bucket.tp1_r_multiplier - 0.05)
            bucket.size_multiplier_delta = max(-0.30, bucket.size_multiplier_delta - 0.10)
            bucket.stagnation_bars_delta = min(4, bucket.stagnation_bars_delta + 1)
        elif wr > WIN_RATE_LOOSEN and avg_r > AVG_R_LOOSEN:
            bucket.tp1_r_multiplier = min(1.20, bucket.tp1_r_multiplier + 0.03)
            bucket.size_multiplier_delta = min(0.10, bucket.size_multiplier_delta + 0.05)
            bucket.stagnation_bars_delta = max(-2, bucket.stagnation_bars_delta - 1)

    def _persist(self) -> None:
        path = self.project_root / "logs" / LEARNING_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "buckets": {
                key: asdict(stats) for key, stats in self.buckets.items()
            },
            "successful_lifecycle_patterns": self.successful_lifecycle_patterns,
            "successful_retracement_patterns": self.successful_retracement_patterns,
            "successful_reversal_patterns": self.successful_reversal_patterns,
            "failed_retracement_classifications": self.failed_retracement_classifications,
            "failed_reversal_classifications": self.failed_reversal_classifications,
            "failed_distribution_detections": self.failed_distribution_detections,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> None:
        path = self.project_root / "logs" / LEARNING_FILENAME
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.buckets = {
            key: ThesisProjectionBucketStats(**vals)
            for key, vals in raw.get("buckets", {}).items()
        }
        self.successful_lifecycle_patterns = raw.get("successful_lifecycle_patterns", {})
        self.successful_retracement_patterns = raw.get("successful_retracement_patterns", {})
        self.successful_reversal_patterns = raw.get("successful_reversal_patterns", {})
        self.failed_retracement_classifications = raw.get(
            "failed_retracement_classifications", {}
        )
        self.failed_reversal_classifications = raw.get("failed_reversal_classifications", {})
        self.failed_distribution_detections = raw.get("failed_distribution_detections", {})

    def write_report(self, path: Path | None = None) -> None:
        report_path = path or (self.project_root / "logs" / "thesis_projection_learning_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Thesis Projection Learning Report",
            "",
            f"Updated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "| Bucket | Samples | Win% | Avg R | TP1 mult | Size Δ | Stagn Δ |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for key, bucket in sorted(self.buckets.items()):
            lines.append(
                f"| {key} | {bucket.samples} | {bucket.win_rate:.0%} | "
                f"{bucket.avg_r:.2f} | {bucket.tp1_r_multiplier:.2f} | "
                f"{bucket.size_multiplier_delta:+.0%} | {bucket.stagnation_bars_delta:+d} |"
            )
        if not self.buckets:
            lines.append("| _(no buckets yet)_ | | | | | | |")
        lines.extend(
            [
                "",
                "## Lifecycle Learning",
                "",
                f"- Successful lifecycle patterns: {self.successful_lifecycle_patterns or {}}",
                f"- Successful retracement patterns: {self.successful_retracement_patterns or {}}",
                f"- Successful reversal patterns: {self.successful_reversal_patterns or {}}",
                f"- Failed retracement classifications: {self.failed_retracement_classifications or {}}",
                f"- Failed reversal classifications: {self.failed_reversal_classifications or {}}",
                f"- Failed distribution detections: {self.failed_distribution_detections or {}}",
            ]
        )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _record_lifecycle_learning(self, pending: dict, *, won: bool) -> None:
        lifecycle = str(pending.get("lifecycle_pattern", "") or "")
        retracement = str(pending.get("retracement_pattern", "") or "")
        reversal = str(pending.get("reversal_pattern", "") or "")
        distribution = str(pending.get("distribution_pattern", "") or "")
        if won:
            self._inc(self.successful_lifecycle_patterns, lifecycle)
            self._inc(self.successful_retracement_patterns, retracement)
            self._inc(self.successful_reversal_patterns, reversal)
            return
        self._inc(self.failed_retracement_classifications, retracement)
        self._inc(self.failed_reversal_classifications, reversal)
        self._inc(self.failed_distribution_detections, distribution)

    @staticmethod
    def _inc(bucket: dict[str, int], key: str) -> None:
        if not key:
            return
        bucket[key] = bucket.get(key, 0) + 1


_lock = Lock()
_engine: ThesisProjectionLearningEngine | None = None


def get_thesis_projection_learning_engine(
    project_root: Path | None = None,
) -> ThesisProjectionLearningEngine | None:
    global _engine
    if project_root is None:
        return _engine
    with _lock:
        if _engine is None or _engine.project_root != project_root:
            _engine = ThesisProjectionLearningEngine(project_root=project_root)
            _engine.load()
        return _engine


def reset_thesis_projection_learning_engine(
    project_root: Path,
) -> ThesisProjectionLearningEngine:
    global _engine
    with _lock:
        _engine = ThesisProjectionLearningEngine(project_root=project_root)
        return _engine


__all__ = [
    "ThesisProjectionAdjustments",
    "ThesisProjectionBucketStats",
    "ThesisProjectionLearningEngine",
    "get_thesis_projection_learning_engine",
    "reset_thesis_projection_learning_engine",
]
