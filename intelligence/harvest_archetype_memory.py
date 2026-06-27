"""Harvest archetype memory — per-symbol/session/regime performance tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from intelligence.harvest_opportunity_score import infer_session
from validation.r_metrics import CLOSED_RESULTS

HarvestArchetype = Literal[
    "london_pullback_harvest",
    "ny_liquidity_sweep",
    "asian_range_scalp",
    "breakout_retest_harvest",
    "trend_continuation_harvest",
    "mean_reversion_snapback",
    "compression_breakout",
]

ArchetypeStatus = Literal["APPROVED", "CONDITIONAL", "REDUCED_RISK", "QUARANTINED"]

ALL_ARCHETYPES: tuple[HarvestArchetype, ...] = (
    "london_pullback_harvest",
    "ny_liquidity_sweep",
    "asian_range_scalp",
    "breakout_retest_harvest",
    "trend_continuation_harvest",
    "mean_reversion_snapback",
    "compression_breakout",
)

MEMORY_FILENAME = "harvest_archetype_memory.json"
MIN_TRADES_FOR_STATUS = 6


@dataclass
class ArchetypeRecord:
    """Performance stats for one archetype bucket."""

    symbol: str
    archetype: str
    session: str = "any"
    regime: str = "any"
    trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    average_r: float = 0.0
    average_pips: float = 0.0
    max_drawdown_pct: float = 0.0
    deterioration: bool = False
    status: ArchetypeStatus = "APPROVED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "archetype": self.archetype,
            "session": self.session,
            "regime": self.regime,
            "trades": self.trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "average_r": round(self.average_r, 4),
            "average_pips": round(self.average_pips, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "deterioration": self.deterioration,
            "status": self.status,
        }


@dataclass
class ArchetypeCheckResult:
    """Runtime archetype gate for harvest entries."""

    symbol: str
    archetype: str
    session: str
    regime: str
    allowed: bool
    status: ArchetypeStatus
    risk_multiplier: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "archetype": self.archetype,
            "session": self.session,
            "regime": self.regime,
            "allowed": self.allowed,
            "status": self.status,
            "risk_multiplier": round(self.risk_multiplier, 2),
            "reason": self.reason,
        }


def infer_archetype(
    *,
    session: str,
    regime: str,
    trend_quality: str,
    asset_state: str,
) -> str:
    """Map market context to a harvest archetype label."""
    if session in {"london", "london_ny_overlap"} and trend_quality in {
        "institutional_trend", "developing_trend",
    }:
        return "london_pullback_harvest"
    if session == "new_york" and regime in {"trending", "volatile"}:
        return "ny_liquidity_sweep"
    if session == "asia" and asset_state in {"ranging", "mean_reverting"}:
        return "asian_range_scalp"
    if asset_state == "volatile_breakout":
        return "breakout_retest_harvest"
    if trend_quality in {"institutional_trend", "developing_trend"}:
        return "trend_continuation_harvest"
    if asset_state in {"mean_reverting", "ranging"}:
        return "mean_reversion_snapback"
    if asset_state == "volatile_breakout" or regime == "compression":
        return "compression_breakout"
    return "trend_continuation_harvest"


class HarvestArchetypeMemory:
    """Persist and query harvest archetype performance."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / "logs" / MEMORY_FILENAME
        self._records: dict[str, ArchetypeRecord] = {}
        self.load()

    def _key(self, symbol: str, archetype: str, session: str, regime: str) -> str:
        return f"{symbol.upper()}|{archetype}|{session}|{regime}"

    def load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        for entry in raw.get("records", []):
            rec = ArchetypeRecord(
                symbol=str(entry.get("symbol", "")),
                archetype=str(entry.get("archetype", "")),
                session=str(entry.get("session", "any")),
                regime=str(entry.get("regime", "any")),
                trades=int(entry.get("trades", 0)),
                win_rate=float(entry.get("win_rate", 0)),
                profit_factor=float(entry.get("profit_factor", 0)),
                average_r=float(entry.get("average_r", 0)),
                average_pips=float(entry.get("average_pips", 0)),
                max_drawdown_pct=float(entry.get("max_drawdown_pct", 0)),
                deterioration=bool(entry.get("deterioration", False)),
                status=entry.get("status", "APPROVED"),  # type: ignore[assignment]
            )
            key = self._key(rec.symbol, rec.archetype, rec.session, rec.regime)
            self._records[key] = rec

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "records": [r.to_dict() for r in sorted(
                self._records.values(),
                key=lambda x: (x.symbol, x.archetype, x.session, x.regime),
            )],
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return self.path

    def get(
        self,
        symbol: str,
        archetype: str,
        session: str = "any",
        regime: str = "any",
    ) -> ArchetypeRecord | None:
        key = self._key(symbol, archetype, session, regime)
        if key in self._records:
            return self._records[key]
        fallback = self._key(symbol, archetype, "any", regime)
        if fallback in self._records:
            return self._records[fallback]
        fallback2 = self._key(symbol, archetype, session, "any")
        return self._records.get(fallback2)

    def check(
        self,
        *,
        symbol: str,
        session: str,
        regime: str,
        trend_quality: str,
        asset_state: str,
    ) -> ArchetypeCheckResult:
        archetype = infer_archetype(
            session=session,
            regime=regime,
            trend_quality=trend_quality,
            asset_state=asset_state,
        )
        record = self.get(symbol, archetype, session, regime)
        if record is None or record.trades < MIN_TRADES_FOR_STATUS:
            return ArchetypeCheckResult(
                symbol=symbol,
                archetype=archetype,
                session=session,
                regime=regime,
                allowed=True,
                status="APPROVED",
                risk_multiplier=1.0,
                reason=f"Archetype {archetype} — insufficient history, default approved",
            )

        status = record.status
        if status == "QUARANTINED":
            return ArchetypeCheckResult(
                symbol=symbol,
                archetype=archetype,
                session=session,
                regime=regime,
                allowed=False,
                status=status,
                risk_multiplier=0.0,
                reason=f"Archetype {archetype} quarantined (PF {record.profit_factor:.2f})",
            )
        if status == "REDUCED_RISK":
            return ArchetypeCheckResult(
                symbol=symbol,
                archetype=archetype,
                session=session,
                regime=regime,
                allowed=True,
                status=status,
                risk_multiplier=0.5,
                reason=f"Archetype {archetype} reduced risk (WR {record.win_rate:.0%})",
            )
        if status == "CONDITIONAL":
            return ArchetypeCheckResult(
                symbol=symbol,
                archetype=archetype,
                session=session,
                regime=regime,
                allowed=True,
                status=status,
                risk_multiplier=0.75,
                reason=f"Archetype {archetype} conditional (deterioration={record.deterioration})",
            )
        return ArchetypeCheckResult(
            symbol=symbol,
            archetype=archetype,
            session=session,
            regime=regime,
            allowed=True,
            status="APPROVED",
            risk_multiplier=1.0,
            reason=f"Archetype {archetype} approved (PF {record.profit_factor:.2f})",
        )

    def refresh_from_journal(
        self,
        journal_path: Path | None = None,
        *,
        initial_balance: float = 10_000.0,
    ) -> dict[str, ArchetypeRecord]:
        path = journal_path or self.project_root / "logs" / "conservative_trade_journal.csv"
        if not path.exists():
            return {}
        frame = pd.read_csv(path)
        closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)].copy()
        if closed.empty:
            return {}

        closed["event_time"] = pd.to_datetime(closed["event_time"], utc=True, errors="coerce")
        closed["session"] = closed["event_time"].dt.hour.map(
            lambda h: infer_session(int(h)) if pd.notna(h) else "any"
        )
        if "regime" not in closed.columns:
            closed["regime"] = "trending"
        else:
            closed["regime"] = closed["regime"].astype(str)
        closed["archetype"] = closed.apply(
            lambda row: infer_archetype(
                session=str(row.get("session", "any")),
                regime=str(row.get("regime", "trending")),
                trend_quality="developing_trend",
                asset_state="weak_trend",
            ),
            axis=1,
        )
        harvest_only = closed[closed["mode"].astype(str).str.lower().isin({"harvest", "normal"})]
        if harvest_only.empty:
            harvest_only = closed

        self._records.clear()
        for (symbol, archetype, session, regime), subset in harvest_only.groupby(
            ["symbol", "archetype", "session", "regime"]
        ):
            record = _build_record(
                str(symbol).upper(),
                str(archetype),
                str(session),
                str(regime),
                subset,
                initial_balance,
            )
            key = self._key(record.symbol, record.archetype, record.session, record.regime)
            self._records[key] = record

        self.save()
        return dict(self._records)

    def write_report(self, path: Path | None = None) -> Path:
        report_path = path or (self.project_root / "logs" / "harvest_archetype_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Harvest Archetype Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Archetype | Session | Regime | Trades | WR | PF | Avg R | Status |",
            "|--------|-----------|---------|--------|--------|-----|-----|-------|--------|",
        ]
        for rec in sorted(
            self._records.values(),
            key=lambda r: (r.symbol, r.archetype, r.session),
        ):
            lines.append(
                f"| {rec.symbol} | {rec.archetype} | {rec.session} | {rec.regime} | "
                f"{rec.trades} | {rec.win_rate:.0%} | {rec.profit_factor:.2f} | "
                f"{rec.average_r:+.2f}R | {rec.status} |"
            )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path


def _build_record(
    symbol: str,
    archetype: str,
    session: str,
    regime: str,
    frame: pd.DataFrame,
    initial_balance: float,
) -> ArchetypeRecord:
    pnls = pd.to_numeric(frame["profit_loss"], errors="coerce").fillna(0.0)
    winners = pnls[pnls > 0]
    losers = pnls[pnls < 0]
    gross_profit = float(winners.sum())
    gross_loss = abs(float(losers.sum()))
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = 3.0
    else:
        pf = 0.0

    win_rate = len(winners) / len(pnls) if len(pnls) else 0.0
    r_vals = pd.to_numeric(frame.get("r_multiple"), errors="coerce").dropna()
    avg_r = float(r_vals.mean()) if not r_vals.empty else 0.0
    if "pips" in frame.columns:
        pip_vals = pd.to_numeric(frame["pips"], errors="coerce").dropna()
        avg_pips = float(pip_vals.mean()) if not pip_vals.empty else 0.0
    else:
        avg_pips = 0.0

    balances = pd.to_numeric(frame.get("balance"), errors="coerce").fillna(initial_balance)
    peak = float(balances.cummax().iloc[-1]) if not balances.empty else initial_balance
    trough = float(balances.min()) if not balances.empty else initial_balance
    dd = max(0.0, (peak - trough) / peak * 100) if peak > 0 else 0.0

    short = frame.tail(max(1, len(frame) // 3))
    long_ = frame
    short_pf = _quick_pf(short)
    long_pf = _quick_pf(long_)
    deterioration = (
        len(frame) >= 12
        and short_pf < long_pf * 0.7
        and short_pf < 1.0
    )

    status: ArchetypeStatus = "APPROVED"
    if pf < 0.8 and win_rate < 0.4:
        status = "QUARANTINED"
    elif pf < 1.0 or (deterioration and pf < 1.2):
        status = "REDUCED_RISK"
    elif deterioration or win_rate < 0.55:
        status = "CONDITIONAL"

    return ArchetypeRecord(
        symbol=symbol,
        archetype=archetype,
        session=session,
        regime=regime,
        trades=len(frame),
        win_rate=win_rate,
        profit_factor=pf,
        average_r=avg_r,
        average_pips=avg_pips,
        max_drawdown_pct=dd,
        deterioration=deterioration,
        status=status,
    )


def _quick_pf(frame: pd.DataFrame) -> float:
    pnls = pd.to_numeric(frame["profit_loss"], errors="coerce").fillna(0.0)
    winners = pnls[pnls > 0].sum()
    losers = abs(pnls[pnls < 0].sum())
    if losers > 0:
        return float(winners / losers)
    return 3.0 if winners > 0 else 0.0
