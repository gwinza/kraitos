"""Fast Path C diagnostic — path_c journal only."""
import re
from collections import Counter
import pandas as pd

j = pd.read_csv("logs/path_c_broker_journal.csv")
j["event_time"] = pd.to_datetime(j["event_time"], utc=True)
opens = j[j.result == "open"].copy()
closed = j[j.result.isin(["win", "loss"])].copy()

# trade-level
rows = []
for tid, o in opens.groupby("trade_id"):
    o = o.iloc[0]
    ex = closed[closed.trade_id == tid]
    r = str(o.reason)
    rows.append({
        "tid": tid, "sym": o.symbol, "side": o.direction,
        "rearmed": "REARMED" in r,
        "tp": "FAST" if "FAST_TP" in r else ("NORMAL" if "NORMAL_TP" in r else "OTHER"),
        "pers": (re.search(r"Individual v1\.1: ([^|]+)", r) or [None, "?"])[1].strip()[:35],
        "net": ex.profit_loss.sum() if len(ex) else 0,
        "r": ex.r_multiple.astype(float).sum() if len(ex) else 0,
        "early": (ex.reason == "early_exit_stagnation").any(),
        "partial": (ex.reason == "partial_take_profit").any(),
        "sl": (ex.reason == "stop_loss").any() and not (ex.reason == "partial_take_profit").any(),
        "tp1_sl": (ex.reason == "partial_take_profit").any() and (ex.reason == "stop_loss").any(),
    })
t = pd.DataFrame(rows)
ct = t[t.net != 0]  # closed-ish

print("TRADES", len(t), "CLOSED", len(ct))
print("WR", round((ct.net > 0).mean() * 100, 1), "NET", round(ct.net.sum(), 2))
print("OUTCOMES early", ct.early.sum(), "full_sl", ct.sl.sum(), "tp1_sl", ct.tp1_sl.sum(), "partial_only", ((ct.partial) & (~ct.sl)).sum())
print("REARMED", ct.rearmed.sum(), "wr", round((ct[ct.rearmed].net > 0).mean() * 100, 1) if ct.rearmed.any() else 0, "net", round(ct[ct.rearmed].net.sum(), 2))
print("NON_REARM wr", round((ct[~ct.rearmed].net > 0).mean() * 100, 1), "net", round(ct[~ct.rearmed].net.sum(), 2))
print("SIDE")
for s, g in ct.groupby("side"):
    print(f"  {s}: n={len(g)} wr={round((g.net>0).mean()*100,1)} net={round(g.net.sum(),2)}")
print("TP MODE")
for s, g in ct.groupby("tp"):
    print(f"  {s}: n={len(g)} wr={round((g.net>0).mean()*100,1)} net={round(g.net.sum(),2)} early={g.early.sum()}")
print("TOP PERS LOSS")
for p, g in ct.groupby("pers"):
    if len(g) >= 10:
        print(f"  {p}: n={len(g)} wr={round((g.net>0).mean()*100,1)} net={round(g.net.sum(),2)}")
early = closed[closed.reason == "early_exit_stagnation"]
print("EARLY avg_r", round(early.r_multiple.astype(float).mean(), 3), "net", round(early.profit_loss.sum(), 2))
part = closed[closed.reason == "partial_take_profit"]
print("PARTIAL avg_r", round(part.r_multiple.astype(float).mean(), 3), "net", round(part.profit_loss.sum(), 2))

# thesis same window count only
b = pd.read_csv("logs/broker_partial_journal.csv", usecols=["event_time", "result", "trade_id"])
b["event_time"] = pd.to_datetime(b["event_time"], utc=True)
end = j.event_time.max()
b = b[b.event_time <= end]
print("THESIS same window trades", b[b.result == "open"].trade_id.nunique())
