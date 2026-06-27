"""Bridge closed trades into self-improvement analytics and learning engines."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import TYPE_CHECKING, Literal

from analytics.trade_intelligence import TradeIntelligenceEngine
from analytics.trade_records import EnrichedTradeRecord, RejectedOpportunityRecord
from strategies.adaptive_aggression_engine import get_adaptive_aggression_engine
from strategies.opportunity_cost_engine import get_opportunity_cost_engine

if TYPE_CHECKING:
    from paper_trading.virtual_account import TradeJournalEntry

RegimeLabel = Literal["trend", "range", "breakout", "reversal", "chaos", "unknown"]


@dataclass
class KraitosLearningLoop:
    """Record trade outcomes and expose self-improvement analytics."""

    _trades: list[EnrichedTradeRecord] = field(default_factory=list)
    _rejected: list[RejectedOpportunityRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def record_closed_trade(self, entry: TradeJournalEntry) -> EnrichedTradeRecord:
        enriched = journal_entry_to_enriched_record(entry)
        with self._lock:
            self._trades.append(enriched)

        side = "buy" if entry.direction == "buy" else "sell"
        aggression = get_adaptive_aggression_engine()
        aggression.record_outcome(
            symbol=entry.symbol,
            side=side,
            r_multiple=entry.r_multiple,
            profit=entry.profit_loss,
            thesis_correct=_thesis_correct_from_snapshot(entry.thesis_snapshot, entry.result),
            thesis_partial=entry.result == "breakeven",
        )

        cost = get_opportunity_cost_engine()
        if enriched.lost:
            cost.record_accepted_loser(
                symbol=entry.symbol,
                side=side,
                lost_r=abs(entry.r_multiple),
                reason=entry.reason,
            )
        return enriched

    def record_rejected_opportunity(
        self,
        *,
        symbol: str,
        side: str,
        decision_time: datetime,
        reason: str,
        conviction_score: float = 0.0,
        missed_r: float = 0.0,
        missed_profit: float = 0.0,
        would_have_won: bool = False,
        primary_regime: RegimeLabel | str = "unknown",
    ) -> None:
        regime = _normalize_regime(primary_regime)
        record = RejectedOpportunityRecord(
            symbol=symbol,
            side=side,
            decision_time=decision_time,
            reason=reason,
            missed_r=missed_r,
            missed_profit=missed_profit,
            would_have_won=would_have_won,
            conviction_score=conviction_score,
            primary_regime=regime,
        )
        with self._lock:
            self._rejected.append(record)
        if would_have_won and missed_r > 0:
            get_opportunity_cost_engine().record_rejected_winner(
                symbol=symbol,
                side=side,
                missed_r=missed_r,
                missed_profit=missed_profit,
                reason=reason,
            )

    def build_report(self, *, initial_balance: float = 10_000.0):
        with self._lock:
            trades = list(self._trades)
            rejected = list(self._rejected)
        return TradeIntelligenceEngine().build_report(
            trades,
            rejected=rejected,
            initial_balance=initial_balance,
        )

    def enriched_trades(self) -> list[EnrichedTradeRecord]:
        with self._lock:
            return list(self._trades)


_learning_loop: KraitosLearningLoop | None = None
_loop_lock = Lock()


def get_learning_loop() -> KraitosLearningLoop:
    global _learning_loop
    with _loop_lock:
        if _learning_loop is None:
            _learning_loop = KraitosLearningLoop()
        return _learning_loop


def journal_entry_to_enriched_record(entry: TradeJournalEntry) -> EnrichedTradeRecord:
    meta = _parse_thesis_snapshot(entry.thesis_snapshot)
    intelligence = meta.get("intelligence", {})
    if not isinstance(intelligence, dict):
        intelligence = {}

    conviction = intelligence.get("conviction", {})
    if not isinstance(conviction, dict):
        conviction = {}

    outcome: Literal["win", "loss", "breakeven"]
    if entry.result == "win":
        outcome = "win"
    elif entry.result == "loss":
        outcome = "loss"
    else:
        outcome = "breakeven"

    primary_regime = _normalize_regime(
        intelligence.get("primary_regime")
        or meta.get("market_context", {}).get("market_phase")
    )

    return EnrichedTradeRecord(
        trade_id=entry.trade_id,
        symbol=entry.symbol,
        side=entry.direction,
        exit_time=entry.event_time,
        pnl=entry.profit_loss,
        r_multiple=entry.r_multiple,
        outcome=outcome,
        conviction_score=float(conviction.get("conviction_score", entry.confidence) or 0.0),
        conviction_class=str(conviction.get("conviction_class", "")),
        participation_mode=str(conviction.get("participation_mode", "")),
        thesis_confidence=float(meta.get("thesis_confidence", entry.confidence) or 0.0),
        thesis_correct=_thesis_correct_from_snapshot(entry.thesis_snapshot, entry.result),
        primary_regime=primary_regime,
        market_mode=str(intelligence.get("market_mode", "")),
        balance=entry.balance,
        session=str(intelligence.get("session", "unknown")),
    )


def _parse_thesis_snapshot(snapshot: str) -> dict:
    if not snapshot:
        return {}
    try:
        payload = json.loads(snapshot)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _thesis_correct_from_snapshot(snapshot: str, result: str) -> bool:
    if result == "win":
        return True
    if result == "loss":
        return False
    meta = _parse_thesis_snapshot(snapshot)
    report = meta.get("completion")
    if isinstance(report, dict) and "thesis_correct" in report:
        return bool(report["thesis_correct"])
    return result == "win"


def _normalize_regime(value: object | None) -> RegimeLabel:
    if not value:
        return "unknown"
    text = str(value).lower()
    if "trend" in text:
        return "trend"
    if "range" in text or "mean" in text:
        return "range"
    if "break" in text:
        return "breakout"
    if "reversal" in text or "distribution" in text or "accumulation" in text:
        return "reversal"
    if "chaos" in text or "volatile" in text:
        return "chaos"
    return "unknown"


__all__ = [
    "KraitosLearningLoop",
    "get_learning_loop",
    "journal_entry_to_enriched_record",
]
