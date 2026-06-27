"""Forecast learning — record narrative forecast outcomes after trades."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEEDBACK_FILENAME = "forecast_feedback.jsonl"
REPORT_FILENAME = "forecast_accuracy_report.md"


@dataclass
class ForecastOutcome:
    """One completed trade forecast vs outcome."""

    symbol: str
    trace_id: str
    forecast_story: str
    expected_move: str
    confidence: float
    strategy: str
    council_edge: str
    regime: str
    result: str
    success: bool
    r_multiple: float
    error_reason: str
    timestamp: str
    council_members: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trace_id": self.trace_id,
            "forecast_story": self.forecast_story,
            "expected_move": self.expected_move,
            "confidence": round(self.confidence, 2),
            "strategy": self.strategy,
            "council_edge": self.council_edge,
            "regime": self.regime,
            "result": self.result,
            "success": self.success,
            "r_multiple": round(self.r_multiple, 4),
            "error_reason": self.error_reason,
            "timestamp": self.timestamp,
            "council_members": list(self.council_members),
        }


@dataclass
class ForecastFeedbackStore:
    """Persist and learn from forecast accuracy."""

    project_root: Path
    outcomes: list[ForecastOutcome] = field(default_factory=list)
    _pending: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register_trade_forecast(
        self,
        *,
        trace_id: str,
        symbol: str,
        forecast_story: str,
        expected_move: str,
        confidence: float,
        strategy: str,
        council_edge: str,
        regime: str,
        council_members: tuple[str, ...] = (),
    ) -> None:
        self._pending[trace_id] = {
            "symbol": symbol,
            "forecast_story": forecast_story,
            "expected_move": expected_move,
            "confidence": confidence,
            "strategy": strategy,
            "council_edge": council_edge,
            "regime": regime,
            "council_members": council_members,
        }

    def record_trade_outcome(
        self,
        *,
        trace_id: str,
        result: str,
        r_multiple: float,
        error_reason: str = "",
    ) -> ForecastOutcome | None:
        pending = self._pending.pop(trace_id, None)
        if pending is None:
            return None
        success = result in {"win", "breakeven"} or r_multiple > 0
        if result == "loss" and r_multiple < -0.1:
            success = False
            if not error_reason:
                error_reason = "Forecast direction or timing wrong"
        outcome = ForecastOutcome(
            symbol=pending["symbol"],
            trace_id=trace_id,
            forecast_story=pending["forecast_story"],
            expected_move=pending["expected_move"],
            confidence=float(pending["confidence"]),
            strategy=pending["strategy"],
            council_edge=pending["council_edge"],
            regime=pending["regime"],
            result=result,
            success=success,
            r_multiple=r_multiple,
            error_reason=error_reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            council_members=tuple(pending.get("council_members", ())),
        )
        self.outcomes.append(outcome)
        self._append_jsonl(outcome)
        return outcome

    def refresh_from_journal(self, journal_path: Path) -> int:
        """Load closed trades from journal and match pending forecasts."""
        if not journal_path.exists():
            return 0
        try:
            import pandas as pd
            from validation.r_metrics import CLOSED_RESULTS

            frame = pd.read_csv(journal_path)
            if frame.empty:
                return 0
            closed = frame[frame["result"].isin(CLOSED_RESULTS)]
            count = 0
            for _, row in closed.iterrows():
                tid = str(row.get("trace_id", ""))
                if not tid or tid not in self._pending:
                    continue
                self.record_trade_outcome(
                    trace_id=tid,
                    result=str(row.get("result", "")),
                    r_multiple=float(row.get("r_multiple", 0.0)),
                )
                count += 1
            return count
        except Exception:
            return 0

    def update_council_memory(self, memory: object) -> None:
        """Feed outcomes into council member performance tracking."""
        from council.council_memory import CouncilMemory

        if not isinstance(memory, CouncilMemory):
            return
        for outcome in self.outcomes[-50:]:
            members = outcome.council_members or ("opportunity",)
            for member in members:
                memory.record_outcome(
                    member=member,
                    regime=outcome.regime,
                    confidence=outcome.confidence,
                    success=outcome.success,
                )
        memory.save()

    def write_accuracy_report(self, path: Path | None = None) -> Path | None:
        if not self.outcomes:
            recent = self._load_recent_jsonl()
            if not recent:
                return None
            self.outcomes = recent

        report_path = path or (self.project_root / "logs" / REPORT_FILENAME)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        total = len(self.outcomes)
        wins = sum(1 for o in self.outcomes if o.success)
        avg_conf = sum(o.confidence for o in self.outcomes) / max(total, 1)
        avg_r = sum(o.r_multiple for o in self.outcomes) / max(total, 1)

        by_strategy: dict[str, list[ForecastOutcome]] = {}
        by_regime: dict[str, list[ForecastOutcome]] = {}
        for o in self.outcomes:
            by_strategy.setdefault(o.strategy, []).append(o)
            by_regime.setdefault(o.regime, []).append(o)

        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Forecast Accuracy Report",
            "",
            f"**Generated:** {now}",
            "",
            f"**Total forecasts:** {total}",
            f"**Success rate:** {wins / max(total, 1):.1%}",
            f"**Average confidence:** {avg_conf:.1f}",
            f"**Average R:** {avg_r:+.2f}",
            "",
            "## By strategy",
            "",
            "| Strategy | Trades | Win% | Avg R |",
            "|----------|--------|------|-------|",
        ]
        for strat, items in sorted(by_strategy.items()):
            wr = sum(1 for i in items if i.success) / len(items)
            ar = sum(i.r_multiple for i in items) / len(items)
            lines.append(f"| {strat} | {len(items)} | {wr:.0%} | {ar:+.2f} |")

        lines.extend(["", "## By regime", ""])
        for regime, items in sorted(by_regime.items()):
            wr = sum(1 for i in items if i.success) / len(items)
            lines.append(f"- **{regime}:** {len(items)} trades, {wr:.0%} win rate")

        lines.extend(["", "## Recent errors", ""])
        errors = [o for o in self.outcomes[-20:] if not o.success]
        for o in errors[-10:]:
            lines.append(f"- {o.symbol} {o.strategy}: {o.error_reason} ({o.r_multiple:+.2f}R)")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def _append_jsonl(self, outcome: ForecastOutcome) -> None:
        path = self.project_root / "logs" / FEEDBACK_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(outcome.to_dict()) + "\n")

    def _load_recent_jsonl(self, limit: int = 500) -> list[ForecastOutcome]:
        path = self.project_root / "logs" / FEEDBACK_FILENAME
        if not path.exists():
            return []
        outcomes: list[ForecastOutcome] = []
        try:
            for line in path.read_text(encoding="utf-8").strip().splitlines()[-limit:]:
                data = json.loads(line)
                outcomes.append(ForecastOutcome(
                    symbol=data["symbol"],
                    trace_id=data["trace_id"],
                    forecast_story=data["forecast_story"],
                    expected_move=data["expected_move"],
                    confidence=float(data["confidence"]),
                    strategy=data["strategy"],
                    council_edge=data.get("council_edge", ""),
                    regime=data.get("regime", "unknown"),
                    result=data["result"],
                    success=bool(data["success"]),
                    r_multiple=float(data["r_multiple"]),
                    error_reason=data.get("error_reason", ""),
                    timestamp=data["timestamp"],
                    council_members=tuple(data.get("council_members", [])),
                ))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
        return outcomes
