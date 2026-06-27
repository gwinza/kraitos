"""February 2025 loss post-mortem — teach Kraitos from immature thesis failures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class LossCategorySummary:
    category: str
    count: int
    total_loss: float
    avg_r: float
    pct_of_losses: float
    lesson: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "count": self.count,
            "total_loss": round(self.total_loss, 2),
            "avg_r": round(self.avg_r, 3),
            "pct_of_losses": round(self.pct_of_losses, 1),
            "lesson": self.lesson,
        }


@dataclass(frozen=True)
class FebruaryPostmortemReport:
    month: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    categories: tuple[LossCategorySummary, ...]
    symbol_breakdown: dict[str, dict]
    mode_breakdown: dict[str, dict]
    regimes_failed: tuple[str, ...]
    summary: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "month": self.month,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 1),
            "net_pnl": round(self.net_pnl, 2),
            "categories": [c.to_dict() for c in self.categories],
            "symbol_breakdown": self.symbol_breakdown,
            "mode_breakdown": self.mode_breakdown,
            "regimes_failed": list(self.regimes_failed),
            "summary": self.summary,
            "recommendations": list(self.recommendations),
        }

    def to_markdown(self) -> str:
        lines = [
            f"# February Maturity Post-Mortem ({self.month})",
            "",
            "## Overview",
            "",
            f"- Closed trades: **{self.total_trades}**",
            f"- Wins / Losses: **{self.wins} / {self.losses}** ({self.win_rate:.1f}% WR)",
            f"- Net PnL: **${self.net_pnl:,.2f}**",
            "",
            self.summary,
            "",
            "## Loss categories (teacher analysis)",
            "",
            "| Category | Count | Total loss | Avg R | % of losses | Lesson |",
            "|----------|-------|------------|-------|-------------|--------|",
        ]
        for cat in self.categories:
            lines.append(
                f"| {cat.category} | {cat.count} | ${cat.total_loss:,.2f} | "
                f"{cat.avg_r:.2f}R | {cat.pct_of_losses:.0f}% | {cat.lesson} |"
            )
        lines.extend(["", "## Symbol breakdown (losses)", ""])
        for sym, data in sorted(self.symbol_breakdown.items(), key=lambda x: x[1]["total_loss"]):
            lines.append(
                f"- **{sym}**: {data['count']} losses, ${data['total_loss']:,.2f}, "
                f"avg {data['avg_r']:.2f}R"
            )
        lines.extend(["", "## Mode breakdown (losses)", ""])
        for mode, data in self.mode_breakdown.items():
            lines.append(
                f"- **{mode}**: {data['count']} losses, ${data['total_loss']:,.2f}, "
                f"avg {data['avg_r']:.2f}R"
            )
        if self.regimes_failed:
            lines.extend(["", "## Regimes that failed", ""])
            for regime in self.regimes_failed:
                lines.append(f"- {regime}")
        lines.extend(["", "## Recommendations", ""])
        for rec in self.recommendations:
            lines.append(f"- {rec}")
        return "\n".join(lines) + "\n"


def _classify_loss(row: pd.Series) -> str:
    reason = str(row.get("reason", "")).lower()
    open_rows = str(row.get("open_reason", "")).lower()

    if "thesis_invalidation" in reason:
        if any(x in open_rows for x in ("unclear", "no reaction", "probe constraints", "not confirmed")):
            return "immature_thesis"
        if "momentum" in open_rows and "unclear" in open_rows:
            return "failed_acceptance"
        return "thesis_invalidation"
    if "stop_loss" in reason:
        return "stop_loss"
    if any(x in open_rows for x in ("unclear", "too early", "no reaction")):
        return "early_entry"
    if "chaotic" in open_rows or "volatility" in open_rows:
        return "poor_timing"
    if "premium" in open_rows or "discount" in open_rows:
        return "poor_location"
    if row.get("mode") == "scalp":
        return "scalp_maturity_failure"
    if row.get("mode") == "harvest":
        return "harvest_maturity_failure"
    return "other"


def _open_reason_lookup(df: pd.DataFrame) -> dict[str, str]:
    opens = df[df["result"] == "open"]
    return {
        str(row["trade_id"]): str(row.get("reason", ""))
        for _, row in opens.iterrows()
    }


def analyze_february_losses(
    journal_path: Path,
    *,
    month_prefix: str = "2025-02",
) -> FebruaryPostmortemReport:
    frame = pd.read_csv(journal_path)
    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    month_frame = frame[frame["event_time"].dt.strftime("%Y-%m") == month_prefix]
    if month_frame.empty:
        return FebruaryPostmortemReport(
            month=month_prefix,
            total_trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            net_pnl=0.0,
            categories=(),
            symbol_breakdown={},
            mode_breakdown={},
            regimes_failed=(),
            summary=f"No trades found for {month_prefix}.",
        )

    open_reasons = _open_reason_lookup(frame)
    closed = (
        month_frame[month_frame["result"].isin(["win", "loss"])]
        .sort_values("event_time")
        .groupby("trade_id", as_index=False)
        .last()
    )
    closed["open_reason"] = closed["trade_id"].map(open_reasons).fillna("")

    wins = closed[closed["result"] == "win"]
    losses = closed[closed["result"] == "loss"]
    net = float(closed["profit_loss"].sum())

    losses = losses.copy()
    losses["loss_category"] = losses.apply(_classify_loss, axis=1)

    category_lessons = {
        "immature_thesis": "Entered before market showed acceptance — wait for maturity",
        "early_entry": "Zone touched without reaction — timing engine should wait",
        "failed_acceptance": "Market rejected thesis — acceptance read was undecided",
        "thesis_invalidation": "Thesis died in trade — review invalidation vs harvest hold",
        "stop_loss": "Hard stop — location or timing was wrong at entry",
        "poor_timing": "Entered into chaotic volatility without trap/sweep acceptance",
        "poor_location": "Direction ok but location wrong — premium/discount mismatch",
        "scalp_maturity_failure": "Scalp lacked immediate acceptance — should scratch faster",
        "harvest_maturity_failure": "Harvest entered without HTF story maturity",
        "other": "Review individual trade context",
    }

    total_loss_count = len(losses)
    categories: list[LossCategorySummary] = []
    for cat, group in losses.groupby("loss_category"):
        categories.append(
            LossCategorySummary(
                category=str(cat),
                count=len(group),
                total_loss=float(group["profit_loss"].sum()),
                avg_r=float(group["r_multiple"].mean()),
                pct_of_losses=(len(group) / total_loss_count * 100) if total_loss_count else 0,
                lesson=category_lessons.get(str(cat), ""),
            )
        )
    categories.sort(key=lambda c: c.total_loss)

    symbol_breakdown = {
        str(sym): {
            "count": int(len(grp)),
            "total_loss": float(grp["profit_loss"].sum()),
            "avg_r": float(grp["r_multiple"].mean()),
        }
        for sym, grp in losses.groupby("symbol")
    }
    mode_breakdown = {
        str(mode): {
            "count": int(len(grp)),
            "total_loss": float(grp["profit_loss"].sum()),
            "avg_r": float(grp["r_multiple"].mean()),
        }
        for mode, grp in losses.groupby("mode")
    }

    immature = sum(1 for c in categories if c.category in {"immature_thesis", "early_entry", "failed_acceptance"})
    regimes_failed = tuple(
        sorted(
            {
                "GBPJPY volatility" if sym == "GBPJPY" else f"{sym} February chop"
                for sym in losses["symbol"].unique()
            }
        )
    )

    recommendations = (
        "Require maturity_stage >= developing before any probe; ready for normal size",
        "February losses dominated by thesis invalidation on immature liquidity-sweep probes",
        "GBPJPY: enforce higher maturity floor (72 ready / 58 probe) — respect not disable",
        "Scalps: scratch at -0.25R if no acceptance within first hour",
        "Harvest: hold through minor invalidation if HTF structure remains valid",
        "Do not add filters — wait for reaction/reclaim before entry commitment",
    )

    summary = (
        f"February lost ${abs(float(losses['profit_loss'].sum())):,.2f} across {total_loss_count} "
        f"losses ({immature} classified as immature/early/acceptance failures). "
        f"Win rate collapsed to {len(wins)/len(closed)*100:.0f}% — entries were ahead of market acceptance."
    )

    return FebruaryPostmortemReport(
        month=month_prefix,
        total_trades=len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(closed) * 100 if len(closed) else 0,
        net_pnl=net,
        categories=tuple(categories),
        symbol_breakdown=symbol_breakdown,
        mode_breakdown=mode_breakdown,
        regimes_failed=regimes_failed,
        summary=summary,
        recommendations=recommendations,
    )


def _count_february_closed(journal_path: Path, month_prefix: str) -> int:
    if not journal_path.exists():
        return 0
    frame = pd.read_csv(journal_path)
    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    month_frame = frame[frame["event_time"].dt.strftime("%Y-%m") == month_prefix]
    return int(month_frame[month_frame["result"].isin(["win", "loss"])].groupby("trade_id").ngroups)


def resolve_february_journal(
    project_root: Path,
    *,
    journal_name: str | None = None,
    month_prefix: str = "2025-02",
) -> Path:
    logs = project_root / "logs"
    if journal_name:
        return logs / journal_name
    candidates = (
        "broker_partial_journal.csv",
        "broker_partial_realistic_journal.csv",
        "path_c_broker_journal.csv",
    )
    best_path = logs / candidates[0]
    best_count = 0
    for name in candidates:
        path = logs / name
        count = _count_february_closed(path, month_prefix)
        if count > best_count:
            best_count = count
            best_path = path
    return best_path


def write_february_postmortem(
    project_root: Path,
    *,
    journal_name: str | None = None,
    month_prefix: str = "2025-02",
) -> Path:
    journal = resolve_february_journal(
        project_root, journal_name=journal_name, month_prefix=month_prefix
    )
    report = analyze_february_losses(journal, month_prefix=month_prefix)
    out_md = project_root / "logs" / "february_maturity_postmortem.md"
    out_json = project_root / "logs" / "february_maturity_postmortem.json"
    md = report.to_markdown()
    md = f"**Source journal:** `{journal.name}`\n\n" + md
    out_md.write_text(md, encoding="utf-8")
    payload = report.to_dict()
    payload["source_journal"] = journal.name
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_md


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    path = write_february_postmortem(root)
    print(f"February post-mortem written to {path}")
