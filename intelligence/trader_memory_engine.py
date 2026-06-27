"""Trader Memory Engine — remember past behaviour, never suppress opportunities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from intelligence.evidence_synthesis_engine import EvidencePiece
from intelligence.indicator_interpretation_engine import FORBIDDEN_OUTPUT

if TYPE_CHECKING:
    from intelligence.evidence_synthesis_engine import MarketStorySummary
    from intelligence.market_psychology_engine import MarketPsychologyResult, PsychologyState
    from intelligence.story_evolution_engine import NestedStoryState
    from intelligence.story_forecast_engine import StoryForecastResult

TRADER_MEMORY_DNA = """
Experienced traders remember.

Kraitos remembers how assets behaved before, how similar stories evolved,
which narratives succeeded, and which narratives failed.

For each trade Kraitos stores evidence summary, psychological state, story
explanation, forecast, outcome, and evolution path.

Memory informs interpretation — it never suppresses, vetoes, or refuses opportunities.
Understanding expands opportunities.
""".strip()

MEMORY_FILENAME = "trader_memory.json"
PRIMARY_TIMEFRAME = "H1"
MAX_STORED_TRADES = 5000

OUTCOME_SUCCESS = frozenset({"win", "success", "tp", "target"})
OUTCOME_FAILURE = frozenset({"loss", "fail", "sl", "stop"})

VALID_RECALL_EXPANSIONS = frozenset({
    "repeat_success_pattern",
    "learn_from_failure",
    "asset_familiarity",
    "evolution_precedent",
    "narrative_continuation",
    "contrarian_after_failures",
})


@dataclass
class TradeMemoryRecord:
    """One remembered trade — context and outcome for future recall."""

    trade_id: str
    symbol: str
    timestamp: str
    evidence_summary: str
    psychological_state: dict[str, Any]
    story_explanation: str
    forecast: str
    outcome: str
    evolution_path: tuple[str, ...]
    r_multiple: float = 0.0
    pips: float = 0.0
    story_fingerprint: str = ""
    dominant_emotion: str = ""
    macro_story: str = ""
    succeeded: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "evidence_summary": self.evidence_summary,
            "psychological_state": self.psychological_state,
            "story_explanation": self.story_explanation,
            "forecast": self.forecast,
            "outcome": self.outcome,
            "evolution_path": list(self.evolution_path),
            "r_multiple": round(self.r_multiple, 3),
            "pips": round(self.pips, 2),
            "story_fingerprint": self.story_fingerprint,
            "dominant_emotion": self.dominant_emotion,
            "macro_story": self.macro_story,
            "succeeded": self.succeeded,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TradeMemoryRecord:
        return cls(
            trade_id=str(raw.get("trade_id", "")),
            symbol=str(raw.get("symbol", "")).upper(),
            timestamp=str(raw.get("timestamp", "")),
            evidence_summary=str(raw.get("evidence_summary", "")),
            psychological_state=dict(raw.get("psychological_state", {})),
            story_explanation=str(raw.get("story_explanation", "")),
            forecast=str(raw.get("forecast", "")),
            outcome=str(raw.get("outcome", "pending")),
            evolution_path=tuple(str(p) for p in raw.get("evolution_path", ())),
            r_multiple=float(raw.get("r_multiple", 0.0)),
            pips=float(raw.get("pips", 0.0)),
            story_fingerprint=str(raw.get("story_fingerprint", "")),
            dominant_emotion=str(raw.get("dominant_emotion", "")),
            macro_story=str(raw.get("macro_story", "")),
            succeeded=raw.get("succeeded"),
        )


@dataclass(frozen=True)
class MemoryRecallInsight:
    """Recalled experience — informs interpretation, never blocks."""

    symbol: str
    similar_count: int
    success_rate: float
    failure_rate: float
    asset_behaviour_summary: str
    narrative_success_notes: tuple[str, ...]
    narrative_failure_notes: tuple[str, ...]
    evolution_patterns: tuple[str, ...]
    interpretation_contribution: str
    opportunity_expansion: tuple[str, ...]
    recall_score: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "similar_count": self.similar_count,
            "success_rate": round(self.success_rate, 3),
            "failure_rate": round(self.failure_rate, 3),
            "asset_behaviour_summary": self.asset_behaviour_summary,
            "narrative_success_notes": list(self.narrative_success_notes),
            "narrative_failure_notes": list(self.narrative_failure_notes),
            "evolution_patterns": list(self.evolution_patterns),
            "interpretation_contribution": self.interpretation_contribution,
            "opportunity_expansion": list(self.opportunity_expansion),
            "recall_score": round(self.recall_score, 2),
        }

    def to_evidence_pieces(self) -> list[EvidencePiece]:
        direction = "bullish" if self.success_rate >= 0.55 else (
            "bearish" if self.failure_rate >= 0.55 else "neutral"
        )
        strength = min(100.0, 40.0 + self.recall_score * 8.0 + self.similar_count * 2.0)
        return [
            EvidencePiece(
                category="trader_memory",
                timeframe=PRIMARY_TIMEFRAME,
                signal="experience_recall",
                description=self.interpretation_contribution,
                direction=direction,
                strength=strength,
            ),
            EvidencePiece(
                category="trader_memory",
                timeframe=PRIMARY_TIMEFRAME,
                signal="asset_behaviour",
                description=self.asset_behaviour_summary,
                direction="neutral",
                strength=min(85.0, 45.0 + self.similar_count * 3.0),
            ),
        ]


@dataclass
class MemoryStats:
    """Accumulated memory metrics for reporting."""

    recorded: int = 0
    recalls: int = 0
    successes_tracked: int = 0
    failures_tracked: int = 0
    evidence_pieces_added: int = 0


class TraderMemoryEngine:
    """
    Remember past trades and recall similar narratives.

    Memory enriches understanding — never creates trades or refuses them.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self.path = (
            self.project_root / "logs" / MEMORY_FILENAME if self.project_root else None
        )
        self._records: list[TradeMemoryRecord] = []
        self._latest_recall: dict[str, MemoryRecallInsight] = {}
        self.stats = MemoryStats()
        if self.path is not None and self.path.exists():
            self._load()

    def record_trade(
        self,
        *,
        trade_id: str,
        symbol: str,
        evidence_summary: str,
        psychological_state: dict[str, Any] | PsychologyState,
        story_explanation: str,
        forecast: str,
        outcome: str,
        evolution_path: tuple[str, ...] | list[str],
        r_multiple: float = 0.0,
        pips: float = 0.0,
        macro_story: str = "",
        dominant_emotion: str = "",
        timestamp: str | None = None,
    ) -> TradeMemoryRecord:
        symbol = symbol.strip().upper()
        psych = (
            psychological_state.to_dict()
            if hasattr(psychological_state, "to_dict")
            else dict(psychological_state)
        )
        emotion = dominant_emotion or str(psych.get("dominant_emotion", ""))
        path = tuple(evolution_path)
        fingerprint = _story_fingerprint(
            symbol=symbol,
            story_explanation=story_explanation,
            dominant_emotion=emotion,
            macro_story=macro_story,
            evolution_path=path,
        )
        succeeded = _outcome_succeeded(outcome, r_multiple)

        record = TradeMemoryRecord(
            trade_id=trade_id,
            symbol=symbol,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            evidence_summary=evidence_summary.strip(),
            psychological_state=psych,
            story_explanation=story_explanation.strip(),
            forecast=forecast.strip(),
            outcome=outcome.strip().lower(),
            evolution_path=path,
            r_multiple=r_multiple,
            pips=pips,
            story_fingerprint=fingerprint,
            dominant_emotion=emotion,
            macro_story=macro_story,
            succeeded=succeeded,
        )
        self._records.append(record)
        if len(self._records) > MAX_STORED_TRADES:
            self._records = self._records[-MAX_STORED_TRADES:]
        self.stats.recorded += 1
        if succeeded is True:
            self.stats.successes_tracked += 1
        elif succeeded is False:
            self.stats.failures_tracked += 1
        self._save()
        return record

    def record_from_context(
        self,
        *,
        trade_id: str,
        symbol: str,
        outcome: str,
        r_multiple: float = 0.0,
        pips: float = 0.0,
        market_story: MarketStorySummary | None = None,
        market_psychology: MarketPsychologyResult | None = None,
        story_evolution: NestedStoryState | None = None,
        story_forecast: StoryForecastResult | None = None,
        evidence_summary: str = "",
    ) -> TradeMemoryRecord:
        """Convenience recorder from pipeline artefacts."""
        story_explanation = market_story.current_explanation if market_story else ""
        if not evidence_summary and market_story is not None:
            evidence_summary = "; ".join(market_story.supporting_evidence[:5])
        psych_state: dict[str, Any] = (
            market_psychology.psychology_state.to_dict()
            if market_psychology is not None
            else {}
        )
        forecast = story_forecast.expected_next_move if story_forecast else ""
        if story_forecast is not None and story_forecast.invalidation:
            forecast = f"{forecast} | invalidation: {story_forecast.invalidation}"
        evolution_path = _evolution_path_from_state(story_evolution)
        macro_story = story_evolution.macro_story if story_evolution else ""
        emotion = psych_state.get("dominant_emotion", "")
        return self.record_trade(
            trade_id=trade_id,
            symbol=symbol,
            evidence_summary=evidence_summary,
            psychological_state=psych_state,
            story_explanation=story_explanation,
            forecast=forecast,
            outcome=outcome,
            evolution_path=evolution_path,
            r_multiple=r_multiple,
            pips=pips,
            macro_story=macro_story,
            dominant_emotion=str(emotion),
        )

    def update_outcome(
        self,
        trade_id: str,
        *,
        outcome: str,
        r_multiple: float = 0.0,
        pips: float = 0.0,
    ) -> TradeMemoryRecord | None:
        for record in reversed(self._records):
            if record.trade_id == trade_id:
                record.outcome = outcome.strip().lower()
                record.r_multiple = r_multiple
                record.pips = pips
                record.succeeded = _outcome_succeeded(outcome, r_multiple)
                if record.succeeded is True:
                    self.stats.successes_tracked += 1
                elif record.succeeded is False:
                    self.stats.failures_tracked += 1
                self._save()
                return record
        return None

    def recall(
        self,
        *,
        symbol: str,
        story_explanation: str = "",
        psychological_state: dict[str, Any] | PsychologyState | None = None,
        evolution_path: tuple[str, ...] | list[str] | None = None,
        macro_story: str = "",
        limit: int = 8,
    ) -> MemoryRecallInsight:
        symbol = symbol.strip().upper()
        psych = (
            psychological_state.to_dict()
            if psychological_state is not None and hasattr(psychological_state, "to_dict")
            else dict(psychological_state or {})
        )
        emotion = str(psych.get("dominant_emotion", ""))
        path = tuple(evolution_path or ())
        query_fp = _story_fingerprint(
            symbol=symbol,
            story_explanation=story_explanation,
            dominant_emotion=emotion,
            macro_story=macro_story,
            evolution_path=path,
        )

        scored: list[tuple[float, TradeMemoryRecord]] = []
        for record in self._records:
            if record.outcome == "pending":
                continue
            score = _similarity_score(
                query_symbol=symbol,
                query_fp=query_fp,
                query_story=story_explanation,
                query_emotion=emotion,
                query_path=path,
                record=record,
            )
            if score >= 2.0:
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        matches = [r for _, r in scored[:limit]]

        insight = _build_recall_insight(symbol, matches, scored[0][0] if scored else 0.0)
        self._latest_recall[symbol] = insight
        self.stats.recalls += 1
        self.stats.evidence_pieces_added += len(insight.to_evidence_pieces())
        return insight

    def refresh_from_journal(self, journal_path: Path) -> int:
        """Update pending memory records from closed conservative journal rows."""
        import pandas as pd
        from validation.r_metrics import CLOSED_RESULTS

        path = Path(journal_path)
        if not path.exists():
            return 0
        frame = pd.read_csv(path)
        if frame.empty:
            return 0
        updated = 0
        closed = frame[frame["result"].isin(CLOSED_RESULTS)]
        pending_ids = {r.trade_id for r in self._records if r.outcome == "pending"}
        for _, row in closed.iterrows():
            trade_id = str(row.get("trade_id", "")).strip()
            if not trade_id or trade_id not in pending_ids:
                continue
            result = str(row.get("result", "")).strip().lower()
            r_multiple = float(row.get("r_multiple", 0.0) or 0.0)
            profit = float(row.get("profit_loss", 0.0) or 0.0)
            sym = str(row.get("symbol", "EURUSD")).upper()
            pip_size = 0.01 if "JPY" in sym else 0.0001
            lot = float(row.get("lot_size", 0.1) or 0.1)
            pips = profit / (pip_size * 100_000 * lot) if lot > 0 else 0.0
            if self.update_outcome(trade_id, outcome=result, r_multiple=r_multiple, pips=pips):
                updated += 1
        return updated

    def asset_history_summary(self, symbol: str) -> str:
        symbol = symbol.strip().upper()
        symbol_records = [r for r in self._records if r.symbol == symbol and r.outcome != "pending"]
        if not symbol_records:
            return f"No prior remembered behaviour for {symbol}."
        wins = sum(1 for r in symbol_records if r.succeeded is True)
        losses = sum(1 for r in symbol_records if r.succeeded is False)
        avg_r = sum(r.r_multiple for r in symbol_records) / len(symbol_records)
        return (
            f"{symbol}: {len(symbol_records)} remembered trades, "
            f"{wins} succeeded, {losses} failed, avg {avg_r:+.2f}R."
        )

    def write_trader_memory_report(self, path: Path | None = None) -> Path | None:
        if self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "trader_memory_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Trader Memory Report",
            "",
            f"**Generated:** {now}",
            "",
            "Remembered trades inform interpretation — never suppress opportunities.",
            "",
            f"- Recorded: **{self.stats.recorded}**",
            f"- Recalls: **{self.stats.recalls}**",
            f"- Successes tracked: **{self.stats.successes_tracked}**",
            f"- Failures tracked: **{self.stats.failures_tracked}**",
            "",
        ]
        by_symbol: dict[str, list[TradeMemoryRecord]] = {}
        for record in self._records[-100:]:
            by_symbol.setdefault(record.symbol, []).append(record)
        for sym in sorted(by_symbol):
            lines.extend([f"## {sym}", ""])
            for record in by_symbol[sym][-5:]:
                outcome_label = record.outcome
                if record.succeeded is True:
                    outcome_label = f"success ({record.r_multiple:+.2f}R)"
                elif record.succeeded is False:
                    outcome_label = f"failure ({record.r_multiple:+.2f}R)"
                lines.append(
                    f"- **{record.trade_id}** — {record.story_explanation[:80]}… "
                    f"→ {outcome_label}"
                )
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_narrative_outcome_report(self, path: Path | None = None) -> Path | None:
        if self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "narrative_outcome_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        succeeded: dict[str, int] = {}
        failed: dict[str, int] = {}
        for record in self._records:
            if record.succeeded is None:
                continue
            key = record.macro_story or record.story_fingerprint[:40] or "unknown"
            if record.succeeded:
                succeeded[key] = succeeded.get(key, 0) + 1
            else:
                failed[key] = failed.get(key, 0) + 1

        lines = [
            "# Narrative Outcome Report",
            "",
            f"**Generated:** {now}",
            "",
            "## Narratives that succeeded",
            "",
        ]
        for narrative, count in sorted(succeeded.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"- **{narrative}** — {count} trades")
        lines.extend(["", "## Narratives that failed", ""])
        for narrative, count in sorted(failed.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"- **{narrative}** — {count} trades")
        lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_all_reports(self) -> tuple[Path | None, Path | None]:
        return (
            self.write_trader_memory_report(),
            self.write_narrative_outcome_report(),
        )

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._records = [TradeMemoryRecord.from_dict(item) for item in raw.get("trades", [])]

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "trades": [r.to_dict() for r in self._records],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _story_fingerprint(
    *,
    symbol: str,
    story_explanation: str,
    dominant_emotion: str,
    macro_story: str,
    evolution_path: tuple[str, ...],
) -> str:
    tokens = _tokenize(story_explanation)[:8]
    path_tag = "|".join(evolution_path[:4])
    return f"{symbol}:{macro_story}:{dominant_emotion}:{','.join(tokens)}:{path_tag}"


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    stop = {"with", "from", "that", "this", "have", "been", "into", "than", "then"}
    return [w for w in words if w not in stop]


def _outcome_succeeded(outcome: str, r_multiple: float) -> bool | None:
    normalized = outcome.strip().lower()
    if normalized in OUTCOME_SUCCESS or r_multiple > 0.05:
        return True
    if normalized in OUTCOME_FAILURE or r_multiple < -0.05:
        return False
    if normalized in {"pending", "open", ""}:
        return None
    if normalized == "breakeven":
        return None
    return None


def _evolution_path_from_state(state: NestedStoryState | None) -> tuple[str, ...]:
    if state is None:
        return ()
    return (
        f"novel:{state.macro_story or state.novel.story}",
        f"chapter:{state.chapter_story or state.chapter.story}",
        f"paragraph:{state.paragraph_story or state.paragraph.story}",
        f"sentence:{state.sentence_story or state.sentence.story}",
        f"evolution:{state.probable_evolution}",
    )


def _similarity_score(
    *,
    query_symbol: str,
    query_fp: str,
    query_story: str,
    query_emotion: str,
    query_path: tuple[str, ...],
    record: TradeMemoryRecord,
) -> float:
    score = 0.0
    if record.symbol == query_symbol:
        score += 3.0
    if query_emotion and record.dominant_emotion == query_emotion:
        score += 2.5
    if record.story_fingerprint and record.story_fingerprint == query_fp:
        score += 4.0
    query_tokens = set(_tokenize(query_story))
    record_tokens = set(_tokenize(record.story_explanation))
    if query_tokens and record_tokens:
        overlap = len(query_tokens & record_tokens) / max(len(query_tokens | record_tokens), 1)
        score += overlap * 4.0
    path_overlap = len(set(query_path) & set(record.evolution_path))
    score += path_overlap * 0.8
    if record.macro_story and record.macro_story in query_fp:
        score += 1.5
    return score


def _build_recall_insight(
    symbol: str,
    matches: list[TradeMemoryRecord],
    top_score: float,
) -> MemoryRecallInsight:
    if not matches:
        return MemoryRecallInsight(
            symbol=symbol,
            similar_count=0,
            success_rate=0.0,
            failure_rate=0.0,
            asset_behaviour_summary=f"No similar remembered stories for {symbol} yet.",
            narrative_success_notes=(),
            narrative_failure_notes=(),
            evolution_patterns=(),
            interpretation_contribution=(
                f"Memory: no prior similar narratives for {symbol} — fresh interpretation."
            ),
            opportunity_expansion=("asset_familiarity", "narrative_continuation"),
            recall_score=0.0,
        )

    resolved = [m for m in matches if m.succeeded is not None]
    wins = sum(1 for m in resolved if m.succeeded is True)
    losses = sum(1 for m in resolved if m.succeeded is False)
    denom = max(len(resolved), 1)
    success_rate = wins / denom
    failure_rate = losses / denom

    success_notes = tuple(
        f"{m.story_explanation[:70]} (+{m.r_multiple:.2f}R)"
        for m in matches if m.succeeded is True
    )[:4]
    failure_notes = tuple(
        f"{m.story_explanation[:70]} ({m.r_multiple:.2f}R)"
        for m in matches if m.succeeded is False
    )[:4]

    evolution_counts: dict[str, int] = {}
    for m in matches:
        for step in m.evolution_path:
            evolution_counts[step] = evolution_counts.get(step, 0) + 1
    evolution_patterns = tuple(
        step for step, _ in sorted(evolution_counts.items(), key=lambda x: -x[1])[:5]
    )

    symbol_records = [m for m in matches if m.symbol == symbol]
    avg_r = sum(m.r_multiple for m in symbol_records) / max(len(symbol_records), 1)
    asset_summary = (
        f"{symbol} remembered behaviour: {len(symbol_records)} similar episodes, "
        f"success rate {success_rate:.0%}, average {avg_r:+.2f}R."
    )

    contribution = (
        f"Memory recalls {len(matches)} similar narratives for {symbol}: "
        f"{success_rate:.0%} succeeded, {failure_rate:.0%} failed. "
        f"Experience informs interpretation — opportunities remain open."
    )

    expansions: list[str] = ["asset_familiarity", "evolution_precedent"]
    if success_rate >= 0.55:
        expansions.append("repeat_success_pattern")
        expansions.append("narrative_continuation")
    if failure_rate >= 0.55:
        expansions.append("learn_from_failure")
        if success_rate < 0.45:
            expansions.append("contrarian_after_failures")
    if not any(x in expansions for x in {"repeat_success_pattern", "learn_from_failure"}):
        expansions.append("narrative_continuation")

    deduped: list[str] = []
    for hint in expansions:
        if hint in VALID_RECALL_EXPANSIONS and hint not in deduped:
            deduped.append(hint)

    return MemoryRecallInsight(
        symbol=symbol,
        similar_count=len(matches),
        success_rate=success_rate,
        failure_rate=failure_rate,
        asset_behaviour_summary=asset_summary,
        narrative_success_notes=success_notes,
        narrative_failure_notes=failure_notes,
        evolution_patterns=evolution_patterns,
        interpretation_contribution=contribution,
        opportunity_expansion=tuple(deduped),
        recall_score=min(10.0, top_score),
    )


__all__ = [
    "FORBIDDEN_OUTPUT",
    "TRADER_MEMORY_DNA",
    "MemoryRecallInsight",
    "TradeMemoryRecord",
    "TraderMemoryEngine",
]
