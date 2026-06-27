"""Generate average R diagnostic report from trade journal and council logs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def pip_size(symbol: str) -> float:
    if symbol == "XAUUSD":
        return 0.1
    if "JPY" in symbol:
        return 0.01
    return 0.0001


def infer_session(hour: int) -> str:
    if 0 <= hour < 8:
        return "asia"
    if 8 <= hour < 13:
        return "london"
    if 13 <= hour < 17:
        return "london_ny"
    if 17 <= hour < 22:
        return "ny"
    return "late"


def target_bucket(pips: float) -> str:
    if pips < 3:
        return "micro_<3p"
    if pips < 6:
        return "small_3-6p"
    if pips < 12:
        return "medium_6-12p"
    return "large_12p+"


def stop_bucket(pips: float) -> str:
    if pips < 30:
        return "tight_<30p"
    if pips < 45:
        return "medium_30-45p"
    return "wide_45p+"


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def table_md(title: str, rows: list[tuple[str, int, float, float]]) -> list[str]:
    lines = [f"## {title}", "", "| Bucket | Trades | Avg R | Win% |", "|--------|--------|-------|------|"]
    for bucket, n, mean_r, wr in sorted(rows, key=lambda r: -r[1]):
        lines.append(f"| {bucket} | {n} | {mean_r:+.3f} | {wr:.1f}% |")
    lines.append("")
    return lines


def main() -> Path:
    root = Path(__file__).resolve().parent.parent
    journal = root / "logs" / "conservative_trade_journal.csv"
    jsonl = root / "logs" / "json" / "council_opportunity_acceptance.jsonl"
    out = root / "logs" / "average_r_diagnostic_report.md"

    rows = list(csv.DictReader(journal.open(encoding="utf-8")))
    closed = [r for r in rows if r["result"] in ("win", "loss", "breakeven")]
    all_r = [float(r["r_multiple"]) for r in closed]

    by_symbol: dict[str, list[float]] = defaultdict(list)
    by_mode: dict[str, list[float]] = defaultdict(list)
    by_session: dict[str, list[float]] = defaultdict(list)
    by_reason: dict[str, list[float]] = defaultdict(list)
    by_target: dict[str, list[float]] = defaultdict(list)
    by_stop: dict[str, list[float]] = defaultdict(list)
    wins_by_target: dict[str, int] = defaultdict(int)
    count_by_target: dict[str, int] = defaultdict(int)

    for r in closed:
        r_val = float(r["r_multiple"])
        pip = pip_size(r["symbol"])
        entry = float(r["entry"])
        tp = float(r["take_profit"]) if r["take_profit"] else 0.0
        sl = float(r["stop_loss"])
        target_pips = abs(tp - entry) / pip if tp else 0.0
        stop_pips = abs(entry - sl) / pip

        hour = datetime.fromisoformat(r["event_time"]).hour
        by_symbol[r["symbol"]].append(r_val)
        by_mode[r["mode"]].append(r_val)
        by_session[infer_session(hour)].append(r_val)
        by_reason[r["reason"]].append(r_val)
        tb = target_bucket(target_pips)
        by_target[tb].append(r_val)
        by_stop[stop_bucket(stop_pips)].append(r_val)
        count_by_target[tb] += 1
        if r["result"] == "win":
            wins_by_target[tb] += 1

    council_micro: dict[str, list[float]] = defaultdict(list)
    council_narrative: dict[str, list[float]] = defaultdict(list)
    council_strategy: dict[str, list[float]] = defaultdict(list)
    if jsonl.exists():
        for line in jsonl.open(encoding="utf-8"):
            rec = json.loads(line)
            mc = rec.get("micro_class", "unknown")
            narrative = (rec.get("narrative") or "")[:40]
            phase = narrative.split(":")[0].split("(")[0].strip() or "unknown"
            council_micro[mc].append(float(rec.get("expected_pips", 0)))
            council_narrative[phase].append(float(rec.get("expected_pips", 0)))
            council_strategy[rec.get("strategy_selected", "unknown")].append(
                float(rec.get("expected_pips", 0))
            )

    def summarize(data: dict[str, list[float]], is_r: bool = True) -> list[tuple[str, int, float, float]]:
        out_rows = []
        for key, vals in data.items():
            n = len(vals)
            mean = avg(vals)
            if is_r:
                # win rate not available per bucket without joining — approximate from positive R
                wr = 100.0 * sum(1 for v in vals if v > 0) / n
            else:
                wr = 0.0
            out_rows.append((key, n, mean, wr))
        return out_rows

    lines = [
        "# Average R Diagnostic Report",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Source:** `{journal.name}` ({len(closed)} closed trades)",
        "",
        "## Snapshot E Baseline",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Trades | {len(closed)} |",
        f"| Avg R | {avg(all_r):+.3f} |",
        f"| Median R | {sorted(all_r)[len(all_r)//2]:+.3f} |",
        f"| Max R | {max(all_r):+.3f} |",
        f"| Min R | {min(all_r):+.3f} |",
        "",
        "### Key Finding",
        "",
        "Avg R is capped by **micro take-profit targets** (majority <3 pip TP) against "
        "**wide structural stops** (~38-49 pip SL). Wins cluster at +0.07 to +0.13 R; "
        "larger targets (6+ pips) show materially higher avg R.",
        "",
    ]

    lines.extend(table_md("By Symbol", summarize(by_symbol)))
    lines.extend(table_md("By Strategy Mode", summarize(by_mode)))
    lines.extend(table_md("By Session (UTC)", summarize(by_session)))
    lines.extend(table_md("By Exit Reason", summarize(by_reason)))
    lines.extend(table_md("By Target Size (pips)", summarize(by_target)))
    lines.extend(table_md("By Stop Size (pips)", summarize(by_stop)))

    lines.append("## Council Acceptance — Narrative Class (expected pips)")
    lines.append("")
    lines.append("| Micro class | Acceptances | Avg expected pips |")
    lines.append("|-------------|---------------|-------------------|")
    for mc, vals in sorted(council_micro.items(), key=lambda x: -len(x[1])):
        lines.append(f"| {mc} | {len(vals)} | {avg(vals):.2f} |")
    lines.append("")

    lines.append("## Council — Narrative Phase (expected pips)")
    lines.append("")
    lines.append("| Phase | Acceptances | Avg expected pips |")
    lines.append("|-------|---------------|-------------------|")
    for phase, vals in sorted(council_narrative.items(), key=lambda x: -len(x[1]))[:12]:
        lines.append(f"| {phase} | {len(vals)} | {avg(vals):.2f} |")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    lines.append("1. **Expand TP for high-confidence continuation** — council expects ~4 pips but "
                 "journal shows most TPs <3 pips; align dynamic pip targets to 3-5 pips when "
                 "forecast confidence >75 and trend score strong.")
    lines.append("2. **Partial + runner exits** — lock micro profit at first target, trail runner "
                 "toward narrative expected move to lift avg R without reducing trade count.")
    lines.append("3. **Narrative exit tuning** — liquidity_sweep_snapback should exit faster; "
                 "continuation/trend_pause_resume should allow runners.")
    lines.append("4. **Spread-aware sizing** — reduce size only when net expected R <0.08 after "
                 "spread; do not block setups broadly.")
    lines.append("5. **R-aware boost** — slight size increase when narrative expected R >0.20.")
    lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


if __name__ == "__main__":
    path = main()
    print(f"Wrote {path}")
