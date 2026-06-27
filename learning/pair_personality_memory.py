"""Pair personality memory — each instrument behaves differently.

Tracks per-symbol profiles so future entry, exit, and session decisions
reflect learned behaviour. Priority instruments (EURUSD, GBPUSD, USDJPY,
GBPJPY, XAUUSD) and every other traded symbol maintain separate memory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import pandas as pd

from intelligence.harvest_opportunity_score import infer_session
from validation.r_metrics import CLOSED_RESULTS

PRIORITY_INSTRUMENTS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "GBPJPY",
    "XAUUSD",
)

MEMORY_FILENAME = "pair_personality_memory.json"
MIN_SETUP_SAMPLES = 4
MIN_SESSION_SAMPLES = 3

EntryType = Literal[
    "pullback_into_value",
    "retest_broken_structure",
    "breakout_retest",
    "liquidity_sweep_rejection",
    "compression_before_expansion",
    "trend_continuation",
    "mean_reversion",
    "session_breakout",
    "unknown",
]

ExitStyle = Literal["HOLD", "SCALE_OUT", "TRAIL", "EXIT", "unknown"]

ENTRY_ALIASES: dict[str, str] = {
    "liquidity_sweep": "liquidity_sweep_rejection",
    "liquidity_sweep_reversal": "liquidity_sweep_rejection",
    "liquidity_sweep_continuation": "liquidity_sweep_rejection",
    "breakout_retest_harvest": "breakout_retest",
    "breakout_retest": "retest_broken_structure",
    "pullback_continuation": "pullback_into_value",
    "compression_breakout": "compression_before_expansion",
    "compression_pop": "compression_before_expansion",
    "ny_liquidity_sweep": "liquidity_sweep_rejection",
    "london_pullback_harvest": "pullback_into_value",
}


@dataclass
class SetupPerformance:
    """Win rate, profit factor, and average R for one setup bucket."""

    setup_key: str
    trades: int = 0
    wins: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_r: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss > 0:
            return self.gross_profit / self.gross_loss
        if self.gross_profit > 0:
            return 3.0
        return 0.0

    @property
    def average_r(self) -> float:
        return self.total_r / self.trades if self.trades else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_key": self.setup_key,
            "trades": self.trades,
            "wins": self.wins,
            "gross_profit": round(self.gross_profit, 4),
            "gross_loss": round(self.gross_loss, 4),
            "total_r": round(self.total_r, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "average_r": round(self.average_r, 4),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SetupPerformance:
        return cls(
            setup_key=str(payload.get("setup_key", "")),
            trades=int(payload.get("trades", 0)),
            wins=int(payload.get("wins", 0)),
            gross_profit=float(payload.get("gross_profit", 0.0)),
            gross_loss=float(payload.get("gross_loss", 0.0)),
            total_r=float(payload.get("total_r", 0.0)),
        )


@dataclass
class PairPersonalityProfile:
    """Learned behavioural profile for one symbol."""

    symbol: str
    total_trades: int = 0
    entry_type_stats: dict[str, SetupPerformance] = field(default_factory=dict)
    exit_style_stats: dict[str, SetupPerformance] = field(default_factory=dict)
    setup_stats: dict[str, SetupPerformance] = field(default_factory=dict)
    session_stats: dict[str, SetupPerformance] = field(default_factory=dict)
    failure_patterns: dict[str, int] = field(default_factory=dict)
    impulse_pips_total: float = 0.0
    impulse_samples: int = 0
    pullback_depth_total: float = 0.0
    pullback_samples: int = 0

    @property
    def average_impulse_pips(self) -> float:
        return self.impulse_pips_total / self.impulse_samples if self.impulse_samples else 0.0

    @property
    def average_pullback_depth_pct(self) -> float:
        return (
            self.pullback_depth_total / self.pullback_samples if self.pullback_samples else 0.0
        )

    @property
    def best_entry_types(self) -> tuple[str, ...]:
        return self._rank_setups(self.entry_type_stats)

    @property
    def best_exit_styles(self) -> tuple[str, ...]:
        return self._rank_setups(self.exit_style_stats)

    @property
    def best_sessions(self) -> tuple[str, ...]:
        ranked = sorted(
            (
                (session, stats.average_r, stats.win_rate, stats.trades)
                for session, stats in self.session_stats.items()
                if stats.trades >= MIN_SESSION_SAMPLES
            ),
            key=lambda item: (item[1], item[2]),
            reverse=True,
        )
        return tuple(session for session, _, _, _ in ranked[:3])

    @property
    def worst_sessions(self) -> tuple[str, ...]:
        ranked = sorted(
            (
                (session, stats.average_r, stats.trades)
                for session, stats in self.session_stats.items()
                if stats.trades >= MIN_SESSION_SAMPLES
            ),
            key=lambda item: item[1],
        )
        return tuple(session for session, _, _ in ranked[:3])

    @property
    def common_failure_patterns(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            sorted(self.failure_patterns.items(), key=lambda item: item[1], reverse=True)[:8]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "total_trades": self.total_trades,
            "average_impulse_pips": round(self.average_impulse_pips, 2),
            "average_pullback_depth_pct": round(self.average_pullback_depth_pct, 4),
            "best_entry_types": list(self.best_entry_types),
            "best_exit_styles": list(self.best_exit_styles),
            "best_sessions": list(self.best_sessions),
            "worst_sessions": list(self.worst_sessions),
            "entry_type_stats": {k: v.to_dict() for k, v in self.entry_type_stats.items()},
            "exit_style_stats": {k: v.to_dict() for k, v in self.exit_style_stats.items()},
            "setup_stats": {k: v.to_dict() for k, v in self.setup_stats.items()},
            "session_stats": {k: v.to_dict() for k, v in self.session_stats.items()},
            "failure_patterns": dict(self.failure_patterns),
            "impulse_pips_total": round(self.impulse_pips_total, 4),
            "impulse_samples": self.impulse_samples,
            "pullback_depth_total": round(self.pullback_depth_total, 6),
            "pullback_samples": self.pullback_samples,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PairPersonalityProfile:
        def load_stats(key: str) -> dict[str, SetupPerformance]:
            return {
                str(name): SetupPerformance.from_dict({**vals, "setup_key": name})
                for name, vals in payload.get(key, {}).items()
            }

        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            total_trades=int(payload.get("total_trades", 0)),
            entry_type_stats=load_stats("entry_type_stats"),
            exit_style_stats=load_stats("exit_style_stats"),
            setup_stats=load_stats("setup_stats"),
            session_stats=load_stats("session_stats"),
            failure_patterns={
                str(k): int(v) for k, v in payload.get("failure_patterns", {}).items()
            },
            impulse_pips_total=float(payload.get("impulse_pips_total", 0.0)),
            impulse_samples=int(payload.get("impulse_samples", 0)),
            pullback_depth_total=float(payload.get("pullback_depth_total", 0.0)),
            pullback_samples=int(payload.get("pullback_samples", 0)),
        )

    @staticmethod
    def _rank_setups(stats: dict[str, SetupPerformance]) -> tuple[str, ...]:
        ranked = sorted(
            (
                (key, perf.average_r, perf.profit_factor, perf.win_rate, perf.trades)
                for key, perf in stats.items()
                if perf.trades >= MIN_SETUP_SAMPLES
            ),
            key=lambda item: (item[1], item[2], item[3]),
            reverse=True,
        )
        return tuple(key for key, _, _, _, _ in ranked)


@dataclass(frozen=True)
class EntryPreference:
    """Ranked entry type preference for decision engines."""

    entry_type: str
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_type": self.entry_type,
            "score": round(self.score, 4),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PersonalityGuidance:
    """Actionable personality-aware decision hints."""

    symbol: str
    preferred_entry: str | None
    preferred_exit: str | None
    session_bias: str | None
    entry_rankings: tuple[EntryPreference, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "preferred_entry": self.preferred_entry,
            "preferred_exit": self.preferred_exit,
            "session_bias": self.session_bias,
            "entry_rankings": [item.to_dict() for item in self.entry_rankings],
            "explanation": self.explanation,
        }


class PairPersonalityMemory:
    """Persist and query per-symbol instrument personality."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / "logs" / MEMORY_FILENAME
        self._profiles: dict[str, PairPersonalityProfile] = {}
        self._pending: dict[str, dict[str, Any]] = {}
        self.load()

    def normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()

    def is_priority_instrument(self, symbol: str) -> bool:
        return self.normalize_symbol(symbol) in PRIORITY_INSTRUMENTS

    def get_profile(self, symbol: str) -> PairPersonalityProfile:
        symbol = self.normalize_symbol(symbol)
        if symbol not in self._profiles:
            self._profiles[symbol] = PairPersonalityProfile(symbol=symbol)
        return self._profiles[symbol]

    def record_pending_entry(
        self,
        *,
        trade_id: str,
        symbol: str,
        entry_type: str,
        exit_style: str = "unknown",
        setup_key: str = "",
        session: str = "any",
        impulse_pips: float | None = None,
        pullback_depth_pct: float | None = None,
        failure_pattern: str = "",
    ) -> None:
        """Store entry context to enrich the next closed-trade update."""
        key = self._normalize_trade_id(trade_id)
        self._pending[key] = {
            "symbol": self.normalize_symbol(symbol),
            "entry_type": normalize_entry_type(entry_type),
            "exit_style": normalize_exit_style(exit_style),
            "setup_key": setup_key or normalize_entry_type(entry_type),
            "session": session,
            "impulse_pips": impulse_pips,
            "pullback_depth_pct": pullback_depth_pct,
            "failure_pattern": failure_pattern,
        }

    def record_outcome(
        self,
        *,
        trade_id: str,
        symbol: str,
        won: bool,
        r_multiple: float,
        net_pl: float,
        entry_type: str | None = None,
        exit_style: str | None = None,
        setup_key: str | None = None,
        session: str | None = None,
        impulse_pips: float | None = None,
        pullback_depth_pct: float | None = None,
        failure_pattern: str = "",
    ) -> PairPersonalityProfile:
        """Update personality memory from one closed trade."""
        pending = self._pending.pop(self._normalize_trade_id(trade_id), {})
        symbol = self.normalize_symbol(symbol)
        profile = self.get_profile(symbol)

        entry = normalize_entry_type(entry_type or pending.get("entry_type", "unknown"))
        exit_style_norm = normalize_exit_style(
            exit_style or pending.get("exit_style", "unknown")
        )
        setup = setup_key or pending.get("setup_key") or entry
        session_name = session or pending.get("session") or "any"
        impulse = impulse_pips if impulse_pips is not None else pending.get("impulse_pips")
        pullback = (
            pullback_depth_pct
            if pullback_depth_pct is not None
            else pending.get("pullback_depth_pct")
        )
        fail_pattern = failure_pattern or pending.get("failure_pattern") or ""

        self._update_setup(profile.entry_type_stats, entry, won, net_pl, r_multiple)
        self._update_setup(profile.exit_style_stats, exit_style_norm, won, net_pl, r_multiple)
        self._update_setup(profile.setup_stats, str(setup), won, net_pl, r_multiple)
        self._update_setup(profile.session_stats, str(session_name), won, net_pl, r_multiple)

        if impulse is not None and impulse > 0:
            profile.impulse_pips_total += float(impulse)
            profile.impulse_samples += 1
        if pullback is not None and pullback > 0:
            profile.pullback_depth_total += float(pullback)
            profile.pullback_samples += 1

        if not won:
            pattern = fail_pattern or infer_failure_pattern(
                entry_type=entry,
                exit_style=exit_style_norm,
                session=str(session_name),
            )
            if pattern:
                profile.failure_patterns[pattern] = profile.failure_patterns.get(pattern, 0) + 1

        profile.total_trades += 1
        self.save()
        return profile

    def rank_entry_types(
        self,
        symbol: str,
        candidates: tuple[str, ...] | list[str],
    ) -> list[EntryPreference]:
        """Rank entry types by learned edge for this symbol."""
        profile = self.get_profile(symbol)
        ranked: list[EntryPreference] = []
        for raw in candidates:
            entry_type = normalize_entry_type(raw)
            stats = profile.entry_type_stats.get(entry_type)
            if stats is None or stats.trades < MIN_SETUP_SAMPLES:
                ranked.append(
                    EntryPreference(
                        entry_type=entry_type,
                        score=0.50,
                        reason=f"{profile.symbol}: insufficient {entry_type} history",
                    )
                )
                continue
            score = self._setup_score(stats)
            ranked.append(
                EntryPreference(
                    entry_type=entry_type,
                    score=score,
                    reason=(
                        f"{profile.symbol} {entry_type}: "
                        f"{stats.win_rate:.0%} WR, {stats.average_r:+.2f}R avg, "
                        f"PF {stats.profit_factor:.2f} over {stats.trades} trades"
                    ),
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked

    def prefer_entry_type(
        self,
        symbol: str,
        candidates: tuple[str, ...] | list[str],
    ) -> EntryPreference | None:
        """Return the best entry type for this symbol from candidates."""
        ranked = self.rank_entry_types(symbol, candidates)
        return ranked[0] if ranked else None

    def entry_type_boost(self, symbol: str, entry_type: str) -> float:
        """0.5–1.25 multiplier for conviction/sizing from learned edge."""
        stats = self.get_profile(symbol).entry_type_stats.get(normalize_entry_type(entry_type))
        if stats is None or stats.trades < MIN_SETUP_SAMPLES:
            return 1.0
        score = self._setup_score(stats)
        return round(0.75 + score * 0.50, 3)

    def session_score(self, symbol: str, session: str) -> float:
        """0–1 score for trading this symbol in the given session."""
        stats = self.get_profile(symbol).session_stats.get(session)
        if stats is None or stats.trades < MIN_SESSION_SAMPLES:
            return 0.55
        return max(0.0, min(1.0, 0.35 + stats.win_rate * 0.35 + stats.average_r * 0.15))

    def failure_penalty(self, symbol: str, pattern: str) -> float:
        """0–1 penalty when a known failure pattern is repeating on this symbol."""
        if not pattern:
            return 0.0
        count = self.get_profile(symbol).failure_patterns.get(pattern, 0)
        if count <= 0:
            return 0.0
        return min(0.35, 0.08 * count)

    def guidance_for(
        self,
        symbol: str,
        *,
        entry_candidates: tuple[str, ...] | list[str],
        session: str | None = None,
    ) -> PersonalityGuidance:
        """Bundle personality hints for downstream decision engines."""
        profile = self.get_profile(symbol)
        rankings = self.rank_entry_types(symbol, entry_candidates)
        preferred_entry = rankings[0].entry_type if rankings else None
        preferred_exit = profile.best_exit_styles[0] if profile.best_exit_styles else None
        session_bias = None
        if session is not None:
            score = self.session_score(symbol, session)
            if score >= 0.65:
                session_bias = session
            elif profile.worst_sessions and session in profile.worst_sessions:
                session_bias = f"avoid_{session}"

        if preferred_entry and rankings:
            explanation = (
                f"{symbol} personality favours {preferred_entry.replace('_', ' ')} "
                f"({rankings[0].reason})"
            )
        else:
            explanation = f"{symbol} personality still forming — use structure-first defaults"

        return PersonalityGuidance(
            symbol=profile.symbol,
            preferred_entry=preferred_entry,
            preferred_exit=preferred_exit,
            session_bias=session_bias,
            entry_rankings=tuple(rankings),
            explanation=explanation,
        )

    def refresh_from_journal(self, journal_path: Path | None = None) -> dict[str, PairPersonalityProfile]:
        """Rebuild personality profiles from closed journal trades."""
        path = journal_path or (self.project_root / "logs" / "conservative_trade_journal.csv")
        if not path.exists():
            return {}

        frame = pd.read_csv(path)
        closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)].copy()
        if closed.empty:
            return {}

        self._profiles.clear()
        self._pending.clear()

        if "event_time" in closed.columns:
            closed["event_time"] = pd.to_datetime(closed["event_time"], utc=True, errors="coerce")
            closed["session"] = closed["event_time"].dt.hour.map(
                lambda h: infer_session(int(h)) if pd.notna(h) else "any"
            )
        else:
            closed["session"] = "any"

        for _, row in closed.iterrows():
            symbol = str(row.get("symbol", "")).upper()
            if not symbol:
                continue
            reason = str(row.get("reason", "") or "")
            entry_type = infer_entry_type_from_reason(reason)
            setup_key = entry_type
            exit_style = infer_exit_style_from_reason(reason)
            net_pl = float(row.get("profit_loss", 0.0) or 0.0)
            r_multiple = float(row.get("r_multiple", 0.0) or 0.0)
            won = net_pl > 0.01 or r_multiple > 0.05
            trade_id = str(row.get("trade_id", row.name))
            self.record_outcome(
                trade_id=trade_id,
                symbol=symbol,
                won=won,
                r_multiple=r_multiple,
                net_pl=net_pl,
                entry_type=entry_type,
                exit_style=exit_style,
                setup_key=setup_key,
                session=str(row.get("session", "any")),
            )

        self.save()
        return dict(self._profiles)

    def load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._profiles = {
            str(symbol).upper(): PairPersonalityProfile.from_dict(payload)
            for symbol, payload in raw.get("profiles", {}).items()
        }

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "priority_instruments": list(PRIORITY_INSTRUMENTS),
            "profiles": {
                symbol: profile.to_dict()
                for symbol, profile in sorted(self._profiles.items())
            },
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return self.path

    def write_report(self, path: Path | None = None) -> Path:
        report_path = path or (self.project_root / "logs" / "pair_personality_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Pair Personality Report",
            "",
            f"**Generated:** {now}",
            "",
            f"Priority instruments: {', '.join(PRIORITY_INSTRUMENTS)}",
            "",
        ]
        symbols = sorted(
            self._profiles.keys(),
            key=lambda s: (s not in PRIORITY_INSTRUMENTS, s),
        )
        for symbol in symbols:
            profile = self._profiles[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"- Trades: **{profile.total_trades}**",
                f"- Avg impulse: **{profile.average_impulse_pips:.1f} pips**",
                f"- Avg pullback depth: **{profile.average_pullback_depth_pct:.0%}**",
                f"- Best entries: {', '.join(profile.best_entry_types) or '—'}",
                f"- Best exits: {', '.join(profile.best_exit_styles) or '—'}",
                f"- Best sessions: {', '.join(profile.best_sessions) or '—'}",
                f"- Worst sessions: {', '.join(profile.worst_sessions) or '—'}",
                "",
                "| Setup | Trades | WR | PF | Avg R |",
                "|-------|--------|-----|-----|-------|",
            ])
            for setup_key, stats in sorted(
                profile.setup_stats.items(),
                key=lambda item: item[1].average_r,
                reverse=True,
            ):
                lines.append(
                    f"| {setup_key} | {stats.trades} | {stats.win_rate:.0%} | "
                    f"{stats.profit_factor:.2f} | {stats.average_r:+.2f}R |"
                )
            if profile.common_failure_patterns:
                lines.extend(["", "**Common failure patterns:**"])
                for pattern, count in profile.common_failure_patterns:
                    lines.append(f"- {pattern}: {count}")
            lines.append("")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    @staticmethod
    def _normalize_trade_id(trade_id: str) -> str:
        return trade_id.replace(":", "-")[:80]

    @staticmethod
    def _setup_score(stats: SetupPerformance) -> float:
        pf_component = min(1.0, stats.profit_factor / 2.0) * 0.35
        wr_component = stats.win_rate * 0.35
        r_component = max(0.0, min(1.0, (stats.average_r + 0.5) / 1.5)) * 0.30
        return max(0.0, min(1.0, pf_component + wr_component + r_component))

    @staticmethod
    def _update_setup(
        bucket: dict[str, SetupPerformance],
        key: str,
        won: bool,
        net_pl: float,
        r_multiple: float,
    ) -> None:
        stats = bucket.get(key)
        if stats is None:
            stats = SetupPerformance(setup_key=key)
            bucket[key] = stats
        stats.trades += 1
        stats.total_r += r_multiple
        if won:
            stats.wins += 1
            stats.gross_profit += max(net_pl, 0.0)
        else:
            stats.gross_loss += abs(min(net_pl, 0.0))


def normalize_entry_type(raw: str) -> str:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return "unknown"
    return ENTRY_ALIASES.get(key, key)


def normalize_exit_style(raw: str) -> str:
    key = raw.strip().upper().replace(" ", "_")
    if key in {"HOLD", "SCALE_OUT", "TRAIL", "EXIT"}:
        return key
    return "unknown"


def infer_entry_type_from_reason(reason: str) -> str:
    text = reason.lower()
    patterns = [
        (r"liquidity_sweep|liquidity sweep|sell-side liquidity|buy-side liquidity", "liquidity_sweep_rejection"),
        (r"breakout_retest|breakout retest|retest of broken", "retest_broken_structure"),
        (r"pullback|retrace|into value", "pullback_into_value"),
        (r"compression|coil|before expansion", "compression_before_expansion"),
        (r"mean_reversion|snapback", "mean_reversion"),
        (r"session_transition|session open", "session_breakout"),
        (r"trend continuation|continuation", "trend_continuation"),
    ]
    for pattern, entry_type in patterns:
        if re.search(pattern, text):
            return entry_type
    return "unknown"


def infer_exit_style_from_reason(reason: str) -> str:
    text = reason.lower()
    if "scale out" in text or "partial" in text or "50%" in text:
        return "SCALE_OUT"
    if "trail" in text or "runner" in text:
        return "TRAIL"
    if "invalidat" in text or "cut loss" in text or "exit early" in text:
        return "EXIT"
    if "hold" in text:
        return "HOLD"
    return "unknown"


def infer_failure_pattern(*, entry_type: str, exit_style: str, session: str) -> str:
    return f"{entry_type}_loss_{session}" if entry_type != "unknown" else f"{exit_style}_loss_{session}"


_lock = Lock()
_memory: PairPersonalityMemory | None = None


def get_pair_personality_memory(project_root: Path | None = None) -> PairPersonalityMemory | None:
    global _memory
    if project_root is None:
        return _memory
    with _lock:
        if _memory is None or _memory.project_root != project_root.resolve():
            _memory = PairPersonalityMemory(project_root)
        return _memory


def reset_pair_personality_memory(project_root: Path) -> PairPersonalityMemory:
    global _memory
    with _lock:
        _memory = PairPersonalityMemory(project_root)
        return _memory


__all__ = [
    "EntryPreference",
    "ExitStyle",
    "EntryType",
    "MEMORY_FILENAME",
    "PRIORITY_INSTRUMENTS",
    "PairPersonalityMemory",
    "PairPersonalityProfile",
    "PersonalityGuidance",
    "SetupPerformance",
    "get_pair_personality_memory",
    "infer_entry_type_from_reason",
    "normalize_entry_type",
    "reset_pair_personality_memory",
]
