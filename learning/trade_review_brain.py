"""Trade Review Brain — mentor-style post-trade analysis.

After every closed trade, Kraitos explains why it worked or failed and
feeds structured lessons into personality memory, conviction scoring, entry
patience, and adaptive exits. PnL alone is never sufficient.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from learning.pair_personality_memory import PairPersonalityMemory

LESSONS_FILENAME = "trade_lessons.jsonl"
REPORT_FILENAME = "trade_review_report.md"

TimingVerdict = Literal["too_early", "too_late", "well_timed", "unclear"]
ExitVerdict = Literal["too_early", "too_late", "correct", "unclear"]
StoryVerdict = Literal["correct", "partially_correct", "incorrect", "unclear"]
RecommendedChange = Literal[
    "none",
    "boost_entry_type_on_symbol",
    "reduce_entry_type_on_symbol",
    "increase_entry_patience",
    "reduce_entry_patience",
    "tighten_stop_selection",
    "widen_stop_when_vol_expands",
    "scale_out_at_liquidity",
    "hold_runners_on_acceleration",
    "reduce_size_on_setup",
    "boost_conviction_on_setup",
    "avoid_session_on_symbol",
    "prefer_session_on_symbol",
    "improve_story_confirmation",
]


@dataclass(frozen=True)
class ClosedTradeContext:
    """Everything needed to review one closed trade like a mentor."""

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    r_multiple: float
    net_pl: float
    won: bool
    take_profit: float | None = None
    entry_type: str = "unknown"
    exit_action: str = "unknown"
    peak_r: float | None = None
    trough_r: float | None = None
    bars_held: int = 0
    story_direction: str = "neutral"
    story_confidence: float = 0.0
    story_narrative: str = ""
    thesis_text: str = ""
    invalidation_level: float | None = None
    session: str = "any"
    stop_pips: float | None = None
    target_pips: float | None = None
    thesis_followed: bool = True
    story_correct_at_entry: bool | None = None
    loss_classification: str = ""
    stop_forensics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "r_multiple": round(self.r_multiple, 4),
            "net_pl": round(self.net_pl, 4),
            "won": self.won,
            "entry_type": self.entry_type,
            "exit_action": self.exit_action,
            "peak_r": self.peak_r,
            "trough_r": self.trough_r,
            "bars_held": self.bars_held,
            "story_direction": self.story_direction,
            "story_confidence": self.story_confidence,
            "session": self.session,
        }


@dataclass(frozen=True)
class TradeLesson:
    """Actionable learning output for downstream systems."""

    lesson: str
    confidence: float
    recommended_change: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson": self.lesson,
            "confidence": round(self.confidence, 2),
            "recommended_change": self.recommended_change,
        }


@dataclass(frozen=True)
class TradeReviewFindings:
    """Structured mentor analysis dimensions."""

    story_verdict: StoryVerdict
    entry_timing: TimingVerdict
    stop_loss_logical: bool
    take_profit_realistic: bool
    exit_timing: ExitVerdict
    thesis_followed: bool
    summary: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeReviewRecord:
    """Full review artifact stored for learning loops."""

    trade_id: str
    symbol: str
    won: bool
    r_multiple: float
    findings: TradeReviewFindings
    lesson: TradeLesson
    reviewed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "won": self.won,
            "r_multiple": round(self.r_multiple, 4),
            "findings": {
                "story_verdict": self.findings.story_verdict,
                "entry_timing": self.findings.entry_timing,
                "stop_loss_logical": self.findings.stop_loss_logical,
                "take_profit_realistic": self.findings.take_profit_realistic,
                "exit_timing": self.findings.exit_timing,
                "thesis_followed": self.findings.thesis_followed,
                "summary": self.findings.summary,
                "details": list(self.findings.details),
            },
            "lesson": self.lesson.to_dict(),
            "reviewed_at": self.reviewed_at,
        }


class TradeReviewBrain:
    """Review closed trades and publish lessons for future decisions."""

    def __init__(
        self,
        project_root: Path,
        *,
        personality_memory: PairPersonalityMemory | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.lessons_path = self.project_root / "logs" / LESSONS_FILENAME
        self._personality = personality_memory
        self._history: list[TradeReviewRecord] = []

    @property
    def personality_memory(self) -> PairPersonalityMemory | None:
        return self._personality

    def review(self, trade: ClosedTradeContext) -> TradeReviewRecord:
        """Analyse a closed trade and return a mentor lesson."""
        findings = self._analyse(trade)
        lesson = self._compose_lesson(trade, findings)
        record = TradeReviewRecord(
            trade_id=trade.trade_id,
            symbol=trade.symbol.strip().upper(),
            won=trade.won,
            r_multiple=trade.r_multiple,
            findings=findings,
            lesson=lesson,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._history.append(record)
        self._persist_lesson(record)
        self._feed_learning(trade, record)
        return record

    def recent_lessons(self, *, symbol: str | None = None, limit: int = 20) -> list[TradeReviewRecord]:
        if symbol is None:
            return self._history[-limit:]
        sym = symbol.strip().upper()
        filtered = [rec for rec in self._history if rec.symbol == sym]
        return filtered[-limit:]

    def scoring_adjustments(self, symbol: str) -> dict[str, float]:
        """Aggregate lesson hints for conviction / opportunity scoring."""
        sym = symbol.strip().upper()
        lessons = self.recent_lessons(symbol=sym, limit=30)
        if not lessons:
            return {}

        adjustments: dict[str, float] = {
            "conviction_boost": 0.0,
            "patience_boost": 0.0,
            "exit_runner_bias": 0.0,
            "size_reduction": 0.0,
        }
        for rec in lessons:
            weight = rec.lesson.confidence / 100.0
            change = rec.lesson.recommended_change
            if change == "boost_conviction_on_setup" and rec.won:
                adjustments["conviction_boost"] += 0.03 * weight
            elif change == "reduce_size_on_setup" and not rec.won:
                adjustments["size_reduction"] += 0.04 * weight
            elif change == "increase_entry_patience":
                adjustments["patience_boost"] += 0.05 * weight
            elif change == "hold_runners_on_acceleration" and rec.won:
                adjustments["exit_runner_bias"] += 0.04 * weight
            elif change == "scale_out_at_liquidity":
                adjustments["exit_runner_bias"] -= 0.02 * weight

        return {key: round(min(0.15, max(-0.15, val)), 4) for key, val in adjustments.items()}

    def write_report(self, path: Path | None = None) -> Path:
        report_path = path or (self.project_root / "logs" / REPORT_FILENAME)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Trade Review Report",
            "",
            f"**Generated:** {now}",
            "",
            "Mentor reviews — why trades worked or failed, not just PnL.",
            "",
        ]
        for rec in self._history[-40:]:
            lines.extend([
                f"## {rec.symbol} `{rec.trade_id}` ({'WIN' if rec.won else 'LOSS'}, {rec.r_multiple:+.2f}R)",
                "",
                f"**Story:** {rec.findings.story_verdict} | "
                f"**Entry:** {rec.findings.entry_timing} | "
                f"**Exit:** {rec.findings.exit_timing}",
                "",
                f"> {rec.lesson.lesson}",
                "",
                f"*Recommended change:* `{rec.lesson.recommended_change}` "
                f"({rec.lesson.confidence:.0f}% confidence)",
                "",
            ])
        if not self._history:
            lines.append("_No trade reviews recorded yet._")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def _analyse(self, trade: ClosedTradeContext) -> TradeReviewFindings:
        details: list[str] = []
        risk = abs(trade.entry_price - trade.stop_loss) or 1e-9
        peak_r = trade.peak_r if trade.peak_r is not None else max(trade.r_multiple, 0.0)
        trough_r = trade.trough_r if trade.trough_r is not None else min(trade.r_multiple, 0.0)

        story_verdict = self._story_verdict(trade, details)
        entry_timing = self._entry_timing(trade, peak_r, trough_r, details)
        stop_logical = self._stop_logical(trade, risk, details)
        tp_realistic = self._take_profit_realistic(trade, risk, peak_r, details)
        exit_timing = self._exit_timing(trade, peak_r, details)
        thesis_ok = trade.thesis_followed and story_verdict != "incorrect"

        if trade.won:
            summary = "Winner — story and execution aligned enough to capture edge."
        elif story_verdict == "incorrect":
            summary = "Loss — market story was wrong; reduce conviction on similar setups."
        elif entry_timing == "too_late":
            summary = "Loss — chased price; patience engine should wait for value."
        elif exit_timing == "too_late":
            summary = "Loss — held too long after momentum failed."
        else:
            summary = "Loss — thesis did not pay; review entry quality and stop placement."

        return TradeReviewFindings(
            story_verdict=story_verdict,
            entry_timing=entry_timing,
            stop_loss_logical=stop_logical,
            take_profit_realistic=tp_realistic,
            exit_timing=exit_timing,
            thesis_followed=thesis_ok,
            summary=summary,
            details=tuple(details),
        )

    @staticmethod
    def _story_verdict(trade: ClosedTradeContext, details: list[str]) -> StoryVerdict:
        if trade.story_correct_at_entry is True and trade.won:
            details.append("Market story direction played out as anticipated.")
            return "correct"
        if trade.story_correct_at_entry is False:
            details.append("Market story was disputed at entry and failed.")
            return "incorrect"

        aligned = (
            (trade.side == "buy" and trade.story_direction == "bullish")
            or (trade.side == "sell" and trade.story_direction == "bearish")
        )
        if not aligned and trade.story_direction != "neutral":
            details.append("Trade side did not align with the primary market story.")
            return "incorrect"

        if trade.invalidation_level is not None:
            if trade.side == "buy" and trade.exit_price < trade.invalidation_level:
                details.append("Exit below story invalidation — narrative broke.")
                return "incorrect"
            if trade.side == "sell" and trade.exit_price > trade.invalidation_level:
                details.append("Exit above story invalidation — narrative broke.")
                return "incorrect"

        if trade.won and aligned:
            details.append("Story direction supported the trade outcome.")
            return "correct"
        if trade.won:
            details.append("Trade won but story alignment was mixed.")
            return "partially_correct"
        if aligned and trade.r_multiple > -0.5:
            details.append("Story had merit but execution did not capture it.")
            return "partially_correct"
        if trade.story_confidence >= 60 and not trade.won:
            details.append("High-confidence story still failed — review entry filter.")
            return "partially_correct"
        return "unclear"

    @staticmethod
    def _entry_timing(
        trade: ClosedTradeContext,
        peak_r: float,
        trough_r: float,
        details: list[str],
    ) -> TimingVerdict:
        if trough_r <= -0.85 and peak_r < 0.4:
            details.append("Immediate adverse excursion — entry likely too early or stop too tight.")
            return "too_early"
        if trough_r <= -0.5 and trade.bars_held <= 3:
            details.append("Quick drawdown after entry — poor location or late chase into extension.")
            return "too_late" if peak_r < 0.2 else "too_early"

        if peak_r >= 0.5 and trough_r > -0.45:
            details.append("Entry offered favourable risk before expansion.")
            return "well_timed"

        if trade.entry_type in {"liquidity_sweep_rejection", "pullback_into_value"} and trough_r > -0.35:
            details.append("Patient entry type paid with controlled heat.")
            return "well_timed"

        if trade.r_multiple < -0.5 and peak_r < 0.25:
            details.append("Price never accepted the entry — likely late or against flow.")
            return "too_late"

        return "unclear"

    @staticmethod
    def _stop_logical(trade: ClosedTradeContext, risk: float, details: list[str]) -> bool:
        if trade.stop_pips is not None and trade.stop_pips > 50:
            details.append(f"Stop width {trade.stop_pips:.0f} pips — wide for the thesis.")
            return False
        if trade.invalidation_level is not None:
            if trade.side == "buy" and trade.stop_loss < trade.invalidation_level - risk * 0.5:
                details.append("Stop sits far below story invalidation — risk/reward skewed.")
                return False
            if trade.side == "sell" and trade.stop_loss > trade.invalidation_level + risk * 0.5:
                details.append("Stop sits far above story invalidation — risk/reward skewed.")
                return False
        details.append("Stop placement respected structure and invalidation logic.")
        return True

    @staticmethod
    def _take_profit_realistic(
        trade: ClosedTradeContext,
        risk: float,
        peak_r: float,
        details: list[str],
    ) -> bool:
        if trade.take_profit is None:
            details.append("No hard take profit — managed exit only.")
            return True
        target_r = abs(trade.take_profit - trade.entry_price) / risk
        if target_r > peak_r + 1.5 and not trade.won:
            details.append("Take profit target exceeded what price delivered — objective too ambitious.")
            return False
        if target_r < 0.8:
            details.append("Take profit target was modest relative to stop — realistic scalp geometry.")
            return True
        if peak_r >= target_r * 0.85:
            details.append("Take profit was reachable within observed price travel.")
            return True
        details.append("Target sat beyond practical liquidity — consider story-based objectives.")
        return target_r <= 2.5

    @staticmethod
    def _exit_timing(trade: ClosedTradeContext, peak_r: float, details: list[str]) -> ExitVerdict:
        giveback = peak_r - trade.r_multiple
        if trade.won and giveback >= 1.0:
            details.append(f"Left {giveback:.1f}R on the table — exit too early for the move.")
            return "too_early"
        if trade.won and giveback <= 0.35:
            details.append("Exit captured most of the available move.")
            return "correct"
        if not trade.won and peak_r >= 0.8 and trade.r_multiple <= 0:
            details.append("Trade was in profit but closed red — exit too late or trail too loose.")
            return "too_late"
        if trade.won:
            details.append("Exit reasonable relative to peak progress.")
            return "correct"
        if peak_r < 0.2:
            details.append("Never reached meaningful profit — thesis failed early.")
            return "correct"
        return "unclear"

    def _compose_lesson(
        self,
        trade: ClosedTradeContext,
        findings: TradeReviewFindings,
    ) -> TradeLesson:
        symbol = trade.symbol.strip().upper()
        entry = trade.entry_type.replace("_", " ")

        if trade.won and findings.exit_timing == "too_early" and (trade.peak_r or 0) - trade.r_multiple >= 1.0:
            return TradeLesson(
                lesson=(
                    f"{symbol} {entry} worked — story was {findings.story_verdict.replace('_', ' ')} "
                    f"but exit left {(trade.peak_r or 0) - trade.r_multiple:.1f}R. "
                    "Hold runners longer when trend accelerates."
                ),
                confidence=78.0,
                recommended_change="hold_runners_on_acceleration",
            )

        if trade.won and findings.entry_timing == "well_timed":
            return TradeLesson(
                lesson=(
                    f"{symbol} winner: {entry} at {findings.entry_timing.replace('_', ' ')} "
                    f"with {findings.story_verdict.replace('_', ' ')} story. "
                    f"Repeat this entry type when personality memory confirms edge."
                ),
                confidence=min(92.0, 65.0 + trade.story_confidence * 0.25),
                recommended_change="boost_entry_type_on_symbol",
            )

        if not trade.won and findings.story_verdict == "incorrect":
            return TradeLesson(
                lesson=(
                    f"{symbol} loss — market story was wrong before entry. "
                    "Require clearer narrative confirmation before sizing up."
                ),
                confidence=82.0,
                recommended_change="improve_story_confirmation",
            )

        if not trade.won and findings.entry_timing == "too_late":
            return TradeLesson(
                lesson=(
                    f"{symbol} loss — entry was late into extension on {entry}. "
                    "Patience engine must wait for pullback, retest, or sweep rejection."
                ),
                confidence=80.0,
                recommended_change="increase_entry_patience",
            )

        if not trade.won and findings.entry_timing == "too_early":
            return TradeLesson(
                lesson=(
                    f"{symbol} loss — entry was too early before structure confirmed. "
                    "Wait for reclaim or retest before committing risk."
                ),
                confidence=76.0,
                recommended_change="reduce_entry_patience",
            )

        if not trade.won and not findings.stop_loss_logical:
            return TradeLesson(
                lesson=(
                    f"{symbol} loss — stop was too wide or poorly anchored for the story. "
                    "Tighten stop selection to structure invalidation."
                ),
                confidence=74.0,
                recommended_change="tighten_stop_selection",
            )

        if not trade.won and findings.exit_timing == "too_late":
            return TradeLesson(
                lesson=(
                    f"{symbol} loss — gave back open profit. "
                    "Tighten adaptive trail when momentum collapses."
                ),
                confidence=77.0,
                recommended_change="scale_out_at_liquidity",
            )

        if trade.won and findings.exit_timing == "correct":
            return TradeLesson(
                lesson=(
                    f"{symbol} clean win (+{trade.r_multiple:.2f}R): thesis followed, "
                    f"exit timed correctly. Maintain current scoring weight for {entry}."
                ),
                confidence=70.0,
                recommended_change="boost_conviction_on_setup",
            )

        if not trade.won:
            return TradeLesson(
                lesson=(
                    f"{symbol} loss ({trade.r_multiple:+.2f}R): {findings.summary} "
                    f"Reduce size on similar {entry} setups until edge returns."
                ),
                confidence=68.0,
                recommended_change="reduce_size_on_setup",
            )

        return TradeLesson(
            lesson=findings.summary,
            confidence=55.0,
            recommended_change="none",
        )

    def _feed_learning(self, trade: ClosedTradeContext, record: TradeReviewRecord) -> None:
        if self._personality is None:
            return
        failure = ""
        if not trade.won:
            failure = record.lesson.recommended_change
        self._personality.record_outcome(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            won=trade.won,
            r_multiple=trade.r_multiple,
            net_pl=trade.net_pl,
            entry_type=trade.entry_type,
            exit_style=trade.exit_action,
            setup_key=trade.entry_type,
            session=trade.session,
            failure_pattern=failure,
        )

    def _persist_lesson(self, record: TradeReviewRecord) -> None:
        self.lessons_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lessons_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict()) + "\n")


_lock = Lock()
_brain: TradeReviewBrain | None = None


def get_trade_review_brain(project_root: Path | None = None) -> TradeReviewBrain | None:
    global _brain
    if project_root is None:
        return _brain
    with _lock:
        if _brain is None or _brain.project_root != project_root.resolve():
            from learning.pair_personality_memory import PairPersonalityMemory

            _brain = TradeReviewBrain(
                project_root,
                personality_memory=PairPersonalityMemory(project_root),
            )
        return _brain


def reset_trade_review_brain(project_root: Path) -> TradeReviewBrain:
    global _brain
    with _lock:
        from learning.pair_personality_memory import PairPersonalityMemory

        _brain = TradeReviewBrain(
            project_root,
            personality_memory=PairPersonalityMemory(project_root),
        )
        return _brain


__all__ = [
    "ClosedTradeContext",
    "LESSONS_FILENAME",
    "TradeLesson",
    "TradeReviewBrain",
    "TradeReviewFindings",
    "TradeReviewRecord",
    "get_trade_review_brain",
    "reset_trade_review_brain",
]
