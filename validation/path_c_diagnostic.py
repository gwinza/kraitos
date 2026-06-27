"""Full diagnostic: Path C broker journal vs Thesis baseline."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

from validation.r_metrics import CLOSED_RESULTS


def _parse_open_reason(reason: str) -> dict:
    r = reason or ""
    pers = re.search(r"Individual v1\.1: ([^|]+)", r)
    tp = re.search(r"(FAST_TP|NORMAL_TP|EXPANSION_TP)", r)
    grade = re.search(r"grade=([A+BC]+)", r)
    state = re.search(r"(READY_NOW|WAIT_FOR_TRAVEL|SKIP_WEAK)", r)
    return {
        "personality": pers.group(1).strip() if pers else "unknown",
        "tp_mode": tp.group(1) if tp else "unknown",
        "grade": grade.group(1) if grade else "unknown",
        "readiness": state.group(1) if state else "unknown",
        "rearmed": "REARMED" in r,
        "story_opp": (
            re.search(r"Story opportunity: ([^.;]+)", r).group(1).strip()
            if re.search(r"Story opportunity: ([^.;]+)", r)
            else "unknown"
        ),
    }


def _trade_outcomes(opens: pd.DataFrame, closed: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tid in opens["trade_id"].unique():
        o = opens[opens.trade_id == tid].iloc[0]
        ex = closed[closed.trade_id == tid].sort_values("event_time")
        meta = _parse_open_reason(str(o.get("reason", "")))
        if ex.empty:
            rows.append(
                {
                    "trade_id": tid,
                    "symbol": o["symbol"],
                    "side": o["direction"],
                    "mode": o["mode"],
                    "outcome": "still_open",
                    "net_pl": 0.0,
                    "r_sum": 0.0,
                    "partial": False,
                    "early": False,
                    "sl": False,
                    **meta,
                }
            )
            continue
        partial = (ex["reason"] == "partial_take_profit").any()
        sl = (ex["reason"] == "stop_loss").any()
        early = (ex["reason"] == "early_exit_stagnation").any()
        if partial and not sl:
            outcome = "tp1_runner_or_be"
        elif early and not partial:
            outcome = "early_exit_only"
        elif sl and not partial:
            outcome = "full_sl"
        elif partial and sl:
            outcome = "tp1_then_sl"
        else:
            outcome = str(ex.iloc[-1]["reason"])
        rows.append(
            {
                "trade_id": tid,
                "symbol": o["symbol"],
                "side": o["direction"],
                "mode": o["mode"],
                "outcome": outcome,
                "net_pl": float(ex["profit_loss"].sum()),
                "r_sum": float(ex["r_multiple"].astype(float).sum()),
                "partial": partial,
                "early": early,
                "sl": sl,
                **meta,
            }
        )
    return pd.DataFrame(rows)


def analyze_journal(path: Path, *, label: str, end_time: pd.Timestamp | None = None) -> dict:
    df = pd.read_csv(path)
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
    if end_time is not None:
        df = df[df["event_time"] <= end_time]
    opens = df[df["result"] == "open"].copy()
    closed = df[df["result"].astype(str).str.lower().isin(CLOSED_RESULTS)].copy()
    trades = _trade_outcomes(opens, closed)

    early = closed[closed["reason"] == "early_exit_stagnation"]
    partials = closed[closed["reason"] == "partial_take_profit"]
    sl_rows = closed[closed["reason"] == "stop_loss"]

    full_sl = int((trades.outcome == "full_sl").sum())
    closed_trades = trades[trades.outcome != "still_open"]

    return {
        "label": label,
        "path": str(path),
        "last_event": str(df["event_time"].max()),
        "unique_trades": len(trades),
        "closed_trades": len(closed_trades),
        "win_rate": round((closed_trades["net_pl"] > 0).mean() * 100, 1) if len(closed_trades) else 0,
        "net_pl": round(closed_trades["net_pl"].sum(), 2),
        "avg_r": round(closed_trades["r_sum"].mean(), 3) if len(closed_trades) else 0,
        "outcomes": dict(trades["outcome"].value_counts()),
        "side": dict(trades.groupby("side").size()),
        "symbol": dict(trades.groupby("symbol").size().sort_values(ascending=False)),
        "personality": dict(Counter(trades["personality"]).most_common(10)),
        "tp_mode": dict(Counter(trades["tp_mode"])),
        "grade": dict(Counter(trades["grade"])),
        "rearmed_n": int(trades["rearmed"].sum()),
        "rearmed_wr": round(
            (trades[trades.rearmed & (trades.outcome != "still_open")]["net_pl"] > 0).mean() * 100, 1
        )
        if (trades.rearmed & (trades.outcome != "still_open")).any()
        else 0,
        "rearmed_net": round(trades[trades.rearmed]["net_pl"].sum(), 2),
        "non_rearmed_wr": round(
            (trades[~trades.rearmed & (trades.outcome != "still_open")]["net_pl"] > 0).mean() * 100, 1
        )
        if (~trades.rearmed & (trades.outcome != "still_open")).any()
        else 0,
        "early_exits": len(early),
        "early_avg_r": round(early["r_multiple"].astype(float).mean(), 3) if len(early) else 0,
        "early_net": round(early["profit_loss"].sum(), 2),
        "partial_n": len(partials),
        "partial_avg_r": round(partials["r_multiple"].astype(float).mean(), 3) if len(partials) else 0,
        "partial_net": round(partials["profit_loss"].sum(), 2),
        "full_sl_before_tp1": full_sl,
        "sl_net": round(sl_rows["profit_loss"].sum(), 2),
        "trades_df": trades,
    }


def personality_breakdown(trades: pd.DataFrame, min_n: int = 15) -> list[dict]:
    rows = []
    closed = trades[trades.outcome != "still_open"]
    for key, g in closed.groupby("personality"):
        if len(g) < min_n:
            continue
        rows.append(
            {
                "personality": key[:50],
                "n": len(g),
                "wr": round((g.net_pl > 0).mean() * 100, 1),
                "net": round(g.net_pl.sum(), 2),
                "avg_r": round(g.r_sum.mean(), 3),
                "early_pct": round(g.early.mean() * 100, 1),
                "full_sl_pct": round((g.outcome == "full_sl").mean() * 100, 1),
            }
        )
    return sorted(rows, key=lambda x: x["net"])


def main() -> None:
    root = Path.cwd()
    logs = root / "logs"
    path_c = logs / "path_c_broker_journal.csv"
    thesis = logs / "broker_partial_journal.csv"

    pc = analyze_journal(path_c, label="PATH C")
    end = pd.Timestamp(pc["last_event"])
    th = analyze_journal(thesis, label="THESIS same window", end_time=end)

    print("=" * 60)
    print("PATH C FAILURE DIAGNOSTIC")
    print("=" * 60)
    print(f"Window end: {end}")
    print()

    for snap in (th, pc):
        print(f"--- {snap['label']} ---")
        print(f"  trades: {snap['unique_trades']}  closed: {snap['closed_trades']}")
        print(f"  win_rate: {snap['win_rate']}%  net: ${snap['net_pl']}  avg_r: {snap['avg_r']}R")
        print(f"  outcomes: {snap['outcomes']}")
        print(f"  full_sl_before_tp1: {snap['full_sl_before_tp1']}")
        print(f"  early_exits: {snap['early_exits']} avg_r={snap['early_avg_r']} net=${snap['early_net']}")
        print(f"  partials: {snap['partial_n']} avg_r={snap['partial_avg_r']} net=${snap['partial_net']}")
        print(f"  sl_net: ${snap['sl_net']}")
        print(f"  side: {snap['side']}")
        print(f"  tp_mode: {snap['tp_mode']}")
        print(f"  grade: {snap['grade']}")
        print()

    print("--- PATH C REARM vs NON-REARM ---")
    print(f"  rearmed: n={pc['rearmed_n']} wr={pc['rearmed_wr']}% net=${pc['rearmed_net']}")
    print(f"  non_rearmed wr={pc['non_rearmed_wr']}%")
    print()

    print("--- WORST PERSONALITIES (Path C) ---")
    for row in personality_breakdown(pc["trades_df"])[:8]:
        print(f"  {row}")
    print()

    print("--- BEST PERSONALITIES (Path C) ---")
    for row in personality_breakdown(pc["trades_df"])[-5:]:
        print(f"  {row}")
    print()

    # PnL attribution
    t = pc["trades_df"]
    t_closed = t[t.outcome != "still_open"]
    print("--- PnL ATTRIBUTION (Path C) ---")
    for outcome, g in t_closed.groupby("outcome"):
        print(
            f"  {outcome}: n={len(g)} net=${round(g.net_pl.sum(),2)} "
            f"wr={round((g.net_pl>0).mean()*100,1)}%"
        )
    print()

    # Sell vs buy
    print("--- BUY vs SELL (Path C closed) ---")
    for side, g in t_closed.groupby("side"):
        print(
            f"  {side}: n={len(g)} wr={round((g.net_pl>0).mean()*100,1)}% "
            f"net=${round(g.net_pl.sum(),2)} avg_r={round(g.r_sum.mean(),3)}"
        )
    print()

    # FAST_TP vs NORMAL
    print("--- TP MODE (Path C closed) ---")
    for tp, g in t_closed.groupby("tp_mode"):
        print(
            f"  {tp}: n={len(g)} wr={round((g.net_pl>0).mean()*100,1)}% "
            f"net=${round(g.net_pl.sum(),2)} early_pct={round(g.early.mean()*100,1)}%"
        )

    # Estimate rejection funnel from tracker if journal has no rejects
    try:
        from intelligence.individual_trade_doctrine import get_individual_trade_tracker

        tr = get_individual_trade_tracker().summary()
        print()
        print("--- RUNTIME DOCTRINE TRACKER (current process; may be partial) ---")
        print(tr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
