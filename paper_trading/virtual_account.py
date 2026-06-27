"""Virtual account with drawdown safety gates and trade journaling."""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from core.helpers import pip_size_for_symbol, pip_value_per_lot, trade_pnl
from risk.models import OpenPosition, PortfolioState
from risk.risk_manager import RiskManager

TradeResult = Literal["win", "loss", "breakeven", "open", "skipped"]
TradeDirection = Literal["buy", "sell", "none"]

JOURNAL_COLUMNS = [
    "trade_id",
    "event_time",
    "symbol",
    "timeframe",
    "direction",
    "entry",
    "stop_loss",
    "take_profit",
    "confidence",
    "mode",
    "result",
    "profit_loss",
    "reason",
    "balance",
    "equity",
    "lot_size",
    "r_multiple",
    "trade_theme",
    "theme_confidence",
    "market_phase",
    "trend_quality_score",
    "reversal_pressure_score",
    "continuation_probability",
    "thesis_snapshot",
    "thesis_completion_report",
    "entry_stage",
    "scout_or_commit",
    "acceptance_score_at_entry",
    "acceptance_score_after_entry",
    "rejection_score_at_entry",
    "rejection_score_after_entry",
    "momentum_clarity_at_entry",
    "location_quality_at_entry",
    "timing_quality_at_entry",
    "scratch_eligible",
    "scratch_triggered",
    "why_not_scratch",
    "thesis_matured_true_false",
    "loss_classification",
    "cio_confidence",
    "cio_allocation",
    "cio_mode",
    "cio_summary",
    "cognitive_snapshot",
    "picture_clarity",
    "picture_confidence",
    "selected_strategy",
    "strategy_fit",
    "narrator_story",
    "storyteller_snapshot",
    "mind_state",
    "market_mind_snapshot",
]


@dataclass(frozen=True)
class SafetyLimits:
    """Drawdown safety thresholds for validation runs."""

    max_daily_drawdown_pct: float = 50.0
    max_total_drawdown_pct: float = 50.0
    catastrophic_drawdown_pct: float = 50.0


@dataclass(frozen=True)
class ValidationConfig:
    """Defaults for paper trading and backtest validation."""

    initial_balance: float = 100.0
    risk_per_trade_pct: float = 1.0
    contract_size: float = 100_000.0
    spread_pips: float = 1.0
    safety: SafetyLimits = field(default_factory=SafetyLimits)


@dataclass
class TradeJournalEntry:
    """One row in the trade journal."""

    trade_id: str
    event_time: datetime
    symbol: str
    timeframe: str
    direction: TradeDirection
    entry: float
    stop_loss: float
    take_profit: float | None
    confidence: float
    mode: str
    result: TradeResult
    profit_loss: float
    reason: str
    balance: float
    equity: float
    lot_size: float = 0.0
    r_multiple: float = 0.0
    trade_theme: str = ""
    theme_confidence: float = 0.0
    market_phase: str = ""
    trend_quality_score: int = 0
    reversal_pressure_score: float = 0.0
    continuation_probability: float = 0.0
    thesis_snapshot: str = ""
    thesis_completion_report: str = ""
    entry_stage: str = ""
    scout_or_commit: str = ""
    acceptance_score_at_entry: int = 0
    acceptance_score_after_entry: int = 0
    rejection_score_at_entry: int = 0
    rejection_score_after_entry: int = 0
    momentum_clarity_at_entry: str = ""
    location_quality_at_entry: int = 0
    timing_quality_at_entry: int = 0
    scratch_eligible: bool = False
    scratch_triggered: bool = False
    why_not_scratch: str = ""
    thesis_matured_true_false: bool = False
    loss_classification: str = ""
    cio_confidence: float = 0.0
    cio_allocation: float = 0.0
    cio_mode: str = ""
    cio_summary: str = ""
    cognitive_snapshot: str = ""
    picture_clarity: str = ""
    picture_confidence: float = 0.0
    selected_strategy: str = ""
    strategy_fit: float = 0.0
    narrator_story: str = ""
    storyteller_snapshot: str = ""
    mind_state: str = ""
    market_mind_snapshot: str = ""

    def to_row(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "event_time": self.event_time.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "entry": round(self.entry, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit": round(self.take_profit, 5) if self.take_profit is not None else "",
            "confidence": round(self.confidence, 4),
            "mode": self.mode,
            "result": self.result,
            "profit_loss": round(self.profit_loss, 2),
            "reason": self.reason,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "lot_size": round(self.lot_size, 2),
            "r_multiple": round(self.r_multiple, 2),
            "trade_theme": self.trade_theme,
            "theme_confidence": round(self.theme_confidence, 3),
            "market_phase": self.market_phase,
            "trend_quality_score": self.trend_quality_score,
            "reversal_pressure_score": round(self.reversal_pressure_score, 4),
            "continuation_probability": round(self.continuation_probability, 4),
            "thesis_snapshot": self.thesis_snapshot,
            "thesis_completion_report": self.thesis_completion_report,
            "entry_stage": self.entry_stage,
            "scout_or_commit": self.scout_or_commit,
            "acceptance_score_at_entry": self.acceptance_score_at_entry,
            "acceptance_score_after_entry": self.acceptance_score_after_entry,
            "rejection_score_at_entry": self.rejection_score_at_entry,
            "rejection_score_after_entry": self.rejection_score_after_entry,
            "momentum_clarity_at_entry": self.momentum_clarity_at_entry,
            "location_quality_at_entry": self.location_quality_at_entry,
            "timing_quality_at_entry": self.timing_quality_at_entry,
            "scratch_eligible": self.scratch_eligible,
            "scratch_triggered": self.scratch_triggered,
            "why_not_scratch": self.why_not_scratch,
            "thesis_matured_true_false": self.thesis_matured_true_false,
            "loss_classification": self.loss_classification,
            "cio_confidence": self.cio_confidence,
            "cio_allocation": self.cio_allocation,
            "cio_mode": self.cio_mode,
            "cio_summary": self.cio_summary,
            "cognitive_snapshot": self.cognitive_snapshot,
            "picture_clarity": self.picture_clarity,
            "picture_confidence": round(self.picture_confidence, 2),
            "selected_strategy": self.selected_strategy,
            "strategy_fit": round(self.strategy_fit, 2),
            "narrator_story": self.narrator_story,
            "storyteller_snapshot": self.storyteller_snapshot,
            "mind_state": self.mind_state,
            "market_mind_snapshot": self.market_mind_snapshot,
        }


@dataclass
class OpenVirtualPosition:
    """An open simulated position."""

    trade_id: str
    symbol: str
    timeframe: str
    direction: TradeDirection
    entry: float
    stop_loss: float
    take_profit: float | None
    lot_size: float
    confidence: float
    mode: str
    reason: str
    risk_amount: float
    entry_time: datetime
    partial_tp: float | None = None
    runner_tp: float | None = None
    partial_fraction: float = 0.5
    partial_taken: bool = False
    tp2_taken: bool = False
    move_stop_to_breakeven: bool = False
    original_lot_size: float = 0.0
    bars_since_entry: int = 0
    enable_early_exit: bool = True
    spread_limit_pips: float = 3.0
    best_price: float = 0.0
    conviction_score: float = 0.0
    invalidation_level: float = 0.0
    trade_theme: str = ""
    theme_confidence: float = 0.0
    thesis_snapshot: str = ""
    market_phase: str = ""
    trend_quality_score: int = 0
    reversal_pressure_score: float = 0.0
    continuation_probability: float = 0.0
    entry_stage: str = ""
    scout_or_commit: str = ""
    setup_kind: str = ""
    acceptance_score_at_entry: int = 50
    acceptance_score_after_entry: int = 50
    rejection_score_at_entry: int = 50
    rejection_score_after_entry: int = 50
    momentum_clarity_at_entry: str = ""
    location_quality_at_entry: int = 0
    timing_quality_at_entry: int = 0
    scratch_eligible: bool = False
    scratch_triggered: bool = False
    why_not_scratch: str = ""
    thesis_matured: bool = False
    cio_confidence: float = 0.0
    cio_allocation: float = 0.0
    cio_mode: str = ""
    cio_summary: str = ""
    cognitive_snapshot: str = ""
    picture_clarity: str = ""
    picture_confidence: float = 0.0
    selected_strategy: str = ""
    strategy_fit: float = 0.0
    narrator_story: str = ""
    storyteller_snapshot: str = ""
    mind_state: str = ""
    market_mind_snapshot: str = ""
    peak_acceptance_score: int = 0

    def __post_init__(self) -> None:
        if self.original_lot_size <= 0:
            self.original_lot_size = self.lot_size
        if self.best_price <= 0:
            self.best_price = self.entry
        if self.peak_acceptance_score <= 0:
            self.peak_acceptance_score = self.acceptance_score_at_entry


class VirtualAccount:
    """Track balance, equity, drawdown, and safety limits for simulated trading."""

    def __init__(
        self,
        config: ValidationConfig | None = None,
        *,
        journal_path: Path | None = None,
    ) -> None:
        self.config = config or ValidationConfig()
        self.journal_path = journal_path or (
            Path(__file__).resolve().parent.parent / "logs" / "trade_journal.csv"
        )
        self.balance = self.config.initial_balance
        self.peak_balance = self.config.initial_balance
        self.day_start_balance = self.config.initial_balance
        self.current_day: str = ""
        self.daily_realized_pnl = 0.0
        self.trading_halted_daily = False
        self.trading_disabled = False
        self.open_positions: dict[str, OpenVirtualPosition] = {}
        self.closed_entries: list[TradeJournalEntry] = []
        self.daily_pnl: dict[str, float] = {}
        self._ensure_journal()

    def reset_trading(self) -> None:
        """Manually re-enable trading after total drawdown halt."""
        self.trading_disabled = False
        self.trading_halted_daily = False
        self.peak_balance = self.balance
        self.day_start_balance = self.balance
        self.daily_realized_pnl = 0.0

    def portfolio_state(self, risk_manager: RiskManager) -> PortfolioState:
        """Build a portfolio snapshot for pipeline risk checks."""
        positions: list[OpenPosition] = []
        for position in self.open_positions.values():
            pip_size = pip_size_for_symbol(position.symbol)
            pip_value = pip_value_per_lot(
                position.symbol,
                position.entry,
                contract_size=risk_manager.limits.contract_size,
            )
            risk_amount = RiskManager.position_risk_amount(
                volume=position.lot_size,
                entry_price=position.entry,
                stop_loss=position.stop_loss,
                pip_size=pip_size,
                pip_value_per_lot=pip_value,
            )
            positions.append(
                OpenPosition(
                    symbol=position.symbol,
                    side=position.direction,  # type: ignore[arg-type]
                    volume=position.lot_size,
                    entry_price=position.entry,
                    stop_loss=position.stop_loss,
                    risk_amount=risk_amount,
                )
            )
        return PortfolioState(
            balance=self.balance,
            open_positions=tuple(positions),
            daily_realized_pnl=self.daily_realized_pnl,
            day_start_balance=self.day_start_balance,
            peak_balance=self.peak_balance,
        )

    @property
    def equity(self) -> float:
        return self.balance

    @property
    def total_drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return max(0.0, (self.peak_balance - self.equity) / self.peak_balance * 100.0)

    @property
    def daily_drawdown_pct(self) -> float:
        if self.day_start_balance <= 0:
            return 0.0
        loss = max(0.0, self.day_start_balance - self.equity)
        return loss / self.day_start_balance * 100.0

    def can_trade(self, moment: datetime | None = None) -> tuple[bool, str]:
        """Block new entries only at catastrophic portfolio drawdown (≥50%)."""
        now = moment or datetime.now(timezone.utc)
        self._roll_day(now)

        catastrophic = self.config.safety.catastrophic_drawdown_pct
        if self.total_drawdown_pct >= catastrophic:
            self.trading_disabled = True
            return (
                False,
                f"Catastrophic drawdown ({self.total_drawdown_pct:.1f}% ≥ {catastrophic:.0f}%)",
            )
        if self.trading_disabled:
            self.trading_disabled = False
        self.trading_halted_daily = False
        return True, "ok"

    def open_position(self, position: OpenVirtualPosition) -> None:
        self._apply_scout_metadata(position)
        lifecycle = self._lifecycle_from_snapshot(position.thesis_snapshot)
        position.market_phase = position.market_phase or str(lifecycle.get("market_phase", ""))
        position.trend_quality_score = position.trend_quality_score or int(
            lifecycle.get("trend_quality_score", 0) or 0
        )
        position.reversal_pressure_score = (
            position.reversal_pressure_score
            or float(lifecycle.get("reversal_pressure_score", 0.0) or 0.0)
        )
        position.continuation_probability = (
            position.continuation_probability
            or float(lifecycle.get("continuation_probability", 0.0) or 0.0)
        )
        self.open_positions[position.trade_id] = position
        self._append_journal(
            TradeJournalEntry(
                trade_id=position.trade_id,
                event_time=position.entry_time,
                symbol=position.symbol,
                timeframe=position.timeframe,
                direction=position.direction,
                entry=position.entry,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                confidence=position.confidence,
                mode=position.mode,
                result="open",
                profit_loss=0.0,
                reason=position.reason,
                balance=self.balance,
                equity=self.equity,
                lot_size=position.lot_size,
                r_multiple=0.0,
                trade_theme=position.trade_theme,
                theme_confidence=position.theme_confidence,
                market_phase=position.market_phase,
                trend_quality_score=position.trend_quality_score,
                reversal_pressure_score=position.reversal_pressure_score,
                continuation_probability=position.continuation_probability,
                thesis_snapshot=position.thesis_snapshot,
                **self._journal_intel_fields(position),
            )
        )

    def scale_out_position(
        self,
        trade_id: str,
        *,
        exit_price: float,
        exit_time: datetime,
        fraction: float,
        reason: str,
        new_stop_loss: float | None = None,
        runner_tp: float | None = None,
    ) -> TradeJournalEntry | None:
        """Close a fraction of an open position and optionally trail the runner."""
        position = self.open_positions.get(trade_id)
        if position is None or fraction <= 0:
            return None

        close_volume = round(position.lot_size * min(1.0, fraction), 2)
        if close_volume <= 0:
            return None

        pnl = trade_pnl(
            symbol=position.symbol,
            side=position.direction,
            entry_price=position.entry,
            exit_price=exit_price,
            lot_size=close_volume,
            contract_size=self.config.contract_size,
        )
        self.balance += pnl
        self.daily_realized_pnl += pnl
        self.peak_balance = max(self.peak_balance, self.balance)
        self._roll_day(exit_time)

        day_key = exit_time.date().isoformat()
        self.daily_pnl[day_key] = self.daily_pnl.get(day_key, 0.0) + pnl

        risk_slice = position.risk_amount * (close_volume / max(position.original_lot_size, 0.01))
        r_multiple = pnl / risk_slice if risk_slice > 0 else 0.0
        result: TradeResult = "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven")

        entry = TradeJournalEntry(
            trade_id=position.trade_id,
            event_time=exit_time,
            symbol=position.symbol,
            timeframe=position.timeframe,
            direction=position.direction,
            entry=position.entry,
            stop_loss=position.stop_loss,
            take_profit=position.partial_tp or position.take_profit,
            confidence=position.confidence,
            mode=position.mode,
            result=result,
            profit_loss=pnl,
            reason=reason,
            balance=self.balance,
            equity=self.balance,
            lot_size=close_volume,
            r_multiple=r_multiple,
            trade_theme=position.trade_theme,
            theme_confidence=position.theme_confidence,
            market_phase=position.market_phase,
            trend_quality_score=position.trend_quality_score,
            reversal_pressure_score=position.reversal_pressure_score,
            continuation_probability=position.continuation_probability,
            thesis_snapshot=position.thesis_snapshot,
            thesis_completion_report=self._completion_report(
                position,
                result=result,
                profit_loss=pnl,
                r_multiple=r_multiple,
                reason=reason,
            ),
            **self._journal_intel_fields(
                position, reason=reason, result=result, r_multiple=r_multiple
            ),
        )
        self.closed_entries.append(entry)
        self._append_journal(entry)

        remaining = round(position.lot_size - close_volume, 2)
        if remaining <= 0:
            self.open_positions.pop(trade_id, None)
            self._evaluate_safety_after_close(exit_time)
            return entry

        position.lot_size = remaining
        position.partial_taken = True
        position.risk_amount = position.risk_amount * (remaining / max(position.original_lot_size, 0.01))
        if new_stop_loss is not None:
            position.stop_loss = new_stop_loss
        if runner_tp is not None:
            position.take_profit = runner_tp
            position.runner_tp = runner_tp
        return entry

    def close_position(
        self,
        trade_id: str,
        *,
        exit_price: float,
        exit_time: datetime,
        reason: str,
    ) -> TradeJournalEntry:
        position = self.open_positions.pop(trade_id)
        pnl = trade_pnl(
            symbol=position.symbol,
            side=position.direction,
            entry_price=position.entry,
            exit_price=exit_price,
            lot_size=position.lot_size,
            contract_size=self.config.contract_size,
        )
        self.balance += pnl
        self.daily_realized_pnl += pnl
        self.peak_balance = max(self.peak_balance, self.balance)
        self._roll_day(exit_time)

        day_key = exit_time.date().isoformat()
        self.daily_pnl[day_key] = self.daily_pnl.get(day_key, 0.0) + pnl

        if position.risk_amount > 0:
            r_multiple = pnl / position.risk_amount
        else:
            r_multiple = 0.0

        if pnl > 0:
            result: TradeResult = "win"
        elif pnl < 0:
            result = "loss"
        else:
            result = "breakeven"

        entry = TradeJournalEntry(
            trade_id=position.trade_id,
            event_time=exit_time,
            symbol=position.symbol,
            timeframe=position.timeframe,
            direction=position.direction,
            entry=position.entry,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            confidence=position.confidence,
            mode=position.mode,
            result=result,
            profit_loss=pnl,
            reason=reason,
            balance=self.balance,
            equity=self.balance,
            lot_size=position.lot_size,
            r_multiple=r_multiple,
            trade_theme=position.trade_theme,
            theme_confidence=position.theme_confidence,
            market_phase=position.market_phase,
            trend_quality_score=position.trend_quality_score,
            reversal_pressure_score=position.reversal_pressure_score,
            continuation_probability=position.continuation_probability,
            thesis_snapshot=position.thesis_snapshot,
            thesis_completion_report=self._completion_report(
                position,
                result=result,
                profit_loss=pnl,
                r_multiple=r_multiple,
                reason=reason,
            ),
            **self._journal_intel_fields(
                position, reason=reason, result=result, r_multiple=r_multiple
            ),
        )
        self.closed_entries.append(entry)
        self._append_journal(entry)
        try:
            from analytics.journal_bridge import get_learning_loop

            get_learning_loop().record_closed_trade(entry)
        except Exception:
            pass
        self._evaluate_safety_after_close(exit_time)
        return entry

    def record_skipped(
        self,
        *,
        symbol: str,
        timeframe: str,
        direction: TradeDirection,
        entry: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        confidence: float,
        mode: str,
        reason: str,
        moment: datetime,
    ) -> None:
        self._append_journal(
            TradeJournalEntry(
                trade_id=self._new_trade_id(),
                event_time=moment,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                entry=entry or 0.0,
                stop_loss=stop_loss or 0.0,
                take_profit=take_profit,
                confidence=confidence,
                mode=mode,
                result="skipped",
                profit_loss=0.0,
                reason=reason,
                balance=self.balance,
                equity=self.equity,
            )
        )

    def _evaluate_safety_after_close(self, moment: datetime) -> None:
        self._roll_day(moment)
        if self.total_drawdown_pct >= self.config.safety.catastrophic_drawdown_pct:
            self.trading_disabled = True

    def _roll_day(self, moment: datetime) -> None:
        day_key = moment.astimezone(timezone.utc).date().isoformat()
        if not self.current_day:
            self.current_day = day_key
            return
        if day_key != self.current_day:
            self.current_day = day_key
            self.day_start_balance = self.balance
            self.daily_realized_pnl = 0.0
            self.trading_halted_daily = False

    @staticmethod
    def _scout_meta_from_snapshot(snapshot: str) -> dict[str, object]:
        if not snapshot:
            return {}
        try:
            payload = json.loads(snapshot)
        except Exception:
            return {}
        maturity = payload.get("maturity", {})
        if not isinstance(maturity, dict):
            maturity = {}
        scout = maturity.get("scout_commit", {})
        if not isinstance(scout, dict):
            scout = {}
        acceptance = maturity.get("acceptance", {})
        if not isinstance(acceptance, dict):
            acceptance = {}
        return {
            "entry_stage": str(maturity.get("maturity_stage", "") or ""),
            "scout_or_commit": str(scout.get("scout_or_commit", "") or ""),
            "acceptance_score_at_entry": int(acceptance.get("acceptance_score", 50) or 50),
            "rejection_score_at_entry": int(acceptance.get("rejection_score", 50) or 50),
            "momentum_clarity_at_entry": str(scout.get("momentum_clarity", "") or ""),
            "location_quality_at_entry": int(maturity.get("location_quality", 0) or 0),
            "timing_quality_at_entry": int(maturity.get("timing_quality", 0) or 0),
            "scratch_eligible": bool(scout.get("scratch_eligible", False)),
            "setup_kind": str(scout.get("effective_setup_kind", "") or ""),
        }

    @classmethod
    def _apply_scout_metadata(cls, position: OpenVirtualPosition) -> None:
        meta = cls._scout_meta_from_snapshot(position.thesis_snapshot)
        if not meta:
            return
        position.entry_stage = str(meta.get("entry_stage", "") or position.entry_stage)
        position.scout_or_commit = str(meta.get("scout_or_commit", "") or position.scout_or_commit)
        position.acceptance_score_at_entry = int(
            meta.get("acceptance_score_at_entry", position.acceptance_score_at_entry) or 50
        )
        position.rejection_score_at_entry = int(
            meta.get("rejection_score_at_entry", position.rejection_score_at_entry) or 50
        )
        position.momentum_clarity_at_entry = str(
            meta.get("momentum_clarity_at_entry", "") or position.momentum_clarity_at_entry
        )
        position.location_quality_at_entry = int(
            meta.get("location_quality_at_entry", 0) or position.location_quality_at_entry
        )
        position.timing_quality_at_entry = int(
            meta.get("timing_quality_at_entry", 0) or position.timing_quality_at_entry
        )
        position.scratch_eligible = bool(meta.get("scratch_eligible", position.scratch_eligible))
        setup_kind = str(meta.get("setup_kind", "") or "")
        if setup_kind:
            position.setup_kind = setup_kind
        position.peak_acceptance_score = max(
            position.peak_acceptance_score, position.acceptance_score_at_entry
        )

    @staticmethod
    def _classify_loss(position: OpenVirtualPosition, reason: str, r_multiple: float) -> str:
        reason_lower = reason.lower()
        if "scratch" in reason_lower:
            if position.scout_or_commit == "scout":
                return "good_idea_no_acceptance"
            return "good_idea_early"
        if "spread" in reason_lower or "slippage" in reason_lower:
            return "spread_slippage"
        if position.scout_or_commit == "commit" and position.acceptance_score_at_entry >= 58:
            if "invalidation" in reason_lower or "thesis" in reason_lower:
                return "accepted_then_failed"
        if position.scout_or_commit == "scout" or position.entry_stage in {"developing", "idea"}:
            if position.location_quality_at_entry < 55:
                return "good_idea_poor_location"
            if position.acceptance_score_at_entry < 58:
                return "good_idea_no_acceptance"
            return "good_idea_early"
        if position.momentum_clarity_at_entry == "unclear":
            return "good_idea_no_acceptance"
        if "invalidation" in reason_lower or "thesis" in reason_lower:
            return "true_thesis_failure"
        if r_multiple < -0.5 and position.timing_quality_at_entry < 50:
            return "late_entry"
        return "bad_idea"

    @classmethod
    def _journal_intel_fields(
        cls,
        position: OpenVirtualPosition,
        *,
        reason: str = "",
        result: TradeResult = "open",
        r_multiple: float = 0.0,
    ) -> dict[str, object]:
        loss_class = ""
        if result == "loss":
            loss_class = cls._classify_loss(position, reason, r_multiple)
        return {
            "entry_stage": position.entry_stage,
            "scout_or_commit": position.scout_or_commit,
            "acceptance_score_at_entry": position.acceptance_score_at_entry,
            "acceptance_score_after_entry": position.acceptance_score_after_entry,
            "rejection_score_at_entry": position.rejection_score_at_entry,
            "rejection_score_after_entry": position.rejection_score_after_entry,
            "momentum_clarity_at_entry": position.momentum_clarity_at_entry,
            "location_quality_at_entry": position.location_quality_at_entry,
            "timing_quality_at_entry": position.timing_quality_at_entry,
            "scratch_eligible": position.scratch_eligible,
            "scratch_triggered": position.scratch_triggered,
            "why_not_scratch": position.why_not_scratch,
            "thesis_matured_true_false": position.thesis_matured,
            "loss_classification": loss_class,
            "cio_confidence": position.cio_confidence,
            "cio_allocation": position.cio_allocation,
            "cio_mode": position.cio_mode,
            "cio_summary": position.cio_summary,
            "cognitive_snapshot": position.cognitive_snapshot,
            "picture_clarity": position.picture_clarity,
            "picture_confidence": position.picture_confidence,
            "selected_strategy": position.selected_strategy,
            "strategy_fit": position.strategy_fit,
            "narrator_story": position.narrator_story,
            "storyteller_snapshot": position.storyteller_snapshot,
            "mind_state": position.mind_state,
            "market_mind_snapshot": position.market_mind_snapshot,
        }

    @staticmethod
    def _lifecycle_from_snapshot(snapshot: str) -> dict[str, object]:
        if not snapshot:
            return {}
        try:
            payload = json.loads(snapshot)
        except Exception:
            return {}
        market_context = payload.get("market_context", {})
        if not isinstance(market_context, dict):
            return {}
        return market_context

    @staticmethod
    def _completion_report(
        position: OpenVirtualPosition,
        *,
        result: TradeResult,
        profit_loss: float,
        r_multiple: float,
        reason: str,
    ) -> str:
        entry_story = ""
        warning_signs: list[str] = []
        lifecycle_clues: list[str] = []
        if position.thesis_snapshot:
            try:
                payload = json.loads(position.thesis_snapshot)
                report = payload.get("thesis_completion_report", {})
                challenges = payload.get("thesis_challenges", {})
                lifecycle = payload.get("lifecycle_analysis", {})
                if isinstance(report, dict):
                    entry_story = str(report.get("entry_story", "") or "")
                if isinstance(challenges, dict):
                    for key in (
                        "evidence_reversal_not_retracement",
                        "evidence_distribution_not_continuation",
                        "evidence_trend_quality_deteriorating",
                    ):
                        val = challenges.get(key, ())
                        if isinstance(val, list):
                            warning_signs.extend(str(item) for item in val if item)
                if isinstance(lifecycle, dict):
                    for key in (
                        "evidence_of_accumulation",
                        "evidence_of_distribution",
                        "evidence_of_trend_exhaustion",
                        "evidence_of_reversal",
                    ):
                        val = lifecycle.get(key, ())
                        if isinstance(val, list):
                            lifecycle_clues.extend(str(item) for item in val if item)
            except Exception:
                pass
        thesis_correct = result == "win" and profit_loss > 0
        thesis_partially_correct = result == "win" or reason == "partial_take_profit"
        report = {
            "entry_story": entry_story,
            "mid_trade_story": (
                f"Lifecycle at entry: phase={position.market_phase}, "
                f"quality={position.trend_quality_score}, "
                f"reversal_pressure={position.reversal_pressure_score:.2f}, "
                f"continuation={position.continuation_probability:.2f}."
            ),
            "exit_story": f"Closed as {result} for {profit_loss:.2f} ({r_multiple:.2f}R): {reason}",
            "thesis_correct": thesis_correct,
            "thesis_partially_correct": thesis_partially_correct,
            "warning_signs_missed": warning_signs,
            "lifecycle_clues_present": lifecycle_clues,
        }
        return json.dumps(report, separators=(",", ":"), ensure_ascii=True)

    def _ensure_journal(self) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        if self.journal_path.exists() and self.journal_path.stat().st_size > 0:
            with self.journal_path.open("r", encoding="utf-8") as handle:
                header = handle.readline().strip().split(",")
                if header == JOURNAL_COLUMNS:
                    return
            self._migrate_journal_columns()
            return
        with self.journal_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=JOURNAL_COLUMNS)
            writer.writeheader()

    def _migrate_journal_columns(self) -> None:
        with self.journal_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        with self.journal_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=JOURNAL_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in JOURNAL_COLUMNS})

    def _append_journal(self, entry: TradeJournalEntry) -> None:
        with self.journal_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=JOURNAL_COLUMNS)
            writer.writerow(entry.to_row())
            handle.flush()

    @staticmethod
    def _new_trade_id() -> str:
        return uuid.uuid4().hex[:12]
