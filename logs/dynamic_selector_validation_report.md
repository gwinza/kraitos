# Dynamic Selector Validation Report

**Generated:** 2026-06-09T18:00:00+00:00  
**Validation run:** 2026-06-09T17:02:48+00:00 (full walk-forward, `quick=False`)  
**Engine:** Conservative backtest with Dynamic Trend-Based Strategy Selector + Strategy Quality Gate  
**Data source:** synthetic  
**Live trading:** **DISABLED** (`LIVE_TRADING=false`, unchanged)

---

## 1. Conservative metrics — baseline vs selector run

| Metric | Baseline (strategy-quality only) | With dynamic selector | Δ |
|--------|----------------------------------|----------------------|---|
| Closed trades | 359 | **382** | **+23 (+6.4%)** |
| Win rate | 80.5% | **83.5%** | **+3.0 pp** |
| Profit factor | 1.02 | **1.26** | **+0.24 (+24%)** |
| Max drawdown | 15.27% | **12.40%** | **−2.87 pp** |
| Average R | +0.01 | **+0.04** | **+0.03R** |
| Net return | +$132 (approx.) | **+15.18%** | Improved |
| Validation status | NEEDS_MORE_DATA | **NEEDS_MORE_DATA** | Unchanged (382 < 500 gate) |
| Trust verdict | QUESTIONABLE | **QUESTIONABLE** | Unchanged (synthetic data) |

**Source:** `logs/validation_metrics.json` (`conservative_metrics`), compared to pre-selector baseline from prior full walk-forward.

---

## 2. New conservative results (selector active)

| # | Metric | Value |
|---|--------|-------|
| 1 | Conservative closed trades | **382** |
| 2 | Win rate | **83.5%** |
| 3 | Profit factor | **1.26** |
| 4 | Max drawdown | **12.40%** |
| 5 | Average R | **+0.04** |

Additional: gross profit $7,630 / gross loss $5,053, final balance $11,518 (+15.2% on $10k).

---

## 3. Asset status (dynamic selector + strategy memory)

**Runtime (last pipeline snapshot, `dynamic_strategy_report.md`):**

| Status | Count | Symbols |
|--------|-------|---------|
| **APPROVED** | 7 | AUDUSD, EURJPY, EURUSD, GBPJPY, GBPUSD, USDJPY, XAUUSD |
| **QUARANTINED** | 4 | EURGBP, NZDUSD, USDCAD, USDCHF |

**Research-backed memory (`asset_strategy_memory.json`, symbols with ≥5 closed trades):**

| Status | Count | Symbols |
|--------|-------|---------|
| **APPROVED** | 2 | AUDUSD, GBPUSD |
| **QUARANTINED** | 4 | EURGBP, NZDUSD, USDCAD, USDCHF |
| **CONDITIONAL** | 0 | — |
| **DISABLED** | 0 | — |

Symbols without journal history default to APPROVED at runtime until researched. Quarantined symbols use `no_trade` (not permanent disable).

---

## 4. Strategy switches

| Item | Value |
|------|-------|
| Switch log | `logs/strategy_switch_log.csv` |
| Confirmed switches recorded | **1,858** |
| First switch example | EURUSD: `normal_trend` → `reduced_risk_harvest` (strong_uptrend → weak_trend) |

Selector re-evaluated on each M5 step with 2-evaluation confirmation and cooldown. High switch count reflects active regime adaptation across 11 symbols × 5 years of synthetic walk-forward.

---

## 5. Performance verdict — improved or reduced?

**Verdict: IMPROVED vs baseline.**

| Gate | Baseline | Selector run | Pass? |
|------|----------|--------------|-------|
| Profit factor > 1.3 | 1.02 | 1.26 | Closer; not yet |
| Max DD < 15% | 15.27% | 12.40% | **Yes** |
| Average R > 0 | +0.01 | +0.04 | **Yes** |
| Trades ≥ 500 | 359 | 382 | No |

The dynamic selector improved quality metrics (PF, WR, DD, avg R) without sacrificing sample size. PF moved from 1.02 → 1.26 but remains below the 1.3 live-readiness gate.

---

## 6. Trade count collapse check

| Threshold | Result |
|-----------|--------|
| Baseline trades | 359 |
| Selector trades | **382 (+6.4%)** |
| Concerning collapse (<200) | **No** |
| Live-readiness minimum (500) | **Not met** (382) |

**Verdict:** Trade count did **not** collapse. Filtering quarantined symbols (EURGBP, NZDUSD, USDCAD, USDCHF) was offset by better selection on approved symbols and range-scalp routing on ranging states (EURJPY, GBPJPY, USDJPY, XAUUSD).

---

## 7. Selector behaviour highlights

- **Strong trends:** harvest / normal_trend on APPROVED majors (EURUSD, GBPUSD, AUDUSD).
- **Quarantined:** `no_trade` — zero risk multiplier, no harvest/scalp.
- **Ranging:** range_scalper on JPY crosses and XAUUSD.
- **Weak trend transitions:** reduced_risk_harvest with 50% risk scaling.
- **Strategy quality gate:** still active (not bypassed).

Top symbol performers (walk-forward splits): AUDUSD PF 2.91 (52 trades), GBPUSD PF ∞ (30 trades, 100% WR).

---

## 8. Safety confirmation

| Check | Status |
|-------|--------|
| `LIVE_TRADING` | **false** |
| `ENABLE_LIVE_TRADING` | **false** |
| `LIVE_TRADING_ENABLED` | **false** |
| Conservative engine default | **Yes** |
| Validation gate bypassed | **No** |
| Artificial trade inflation | **No** (trade count rose modestly) |

---

## 9. Overall conclusion

The Dynamic Trend-Based Strategy Selector **improved** conservative validation quality versus the strategy-quality-only baseline:

- Higher PF, win rate, and average R
- Lower max drawdown (now under 15% gate)
- Trade count **increased** slightly (382 vs 359), not collapsed

Remaining gaps for live readiness: PF still below 1.3, trades below 500, synthetic data trust remains QUESTIONABLE. **Live trading remains disabled.**

---

## Related files

- `logs/validation_metrics.json`
- `logs/live_readiness_report.md`
- `logs/dynamic_strategy_report.md`
- `logs/asset_strategy_fit_report.md`
- `logs/asset_underperformance_report.md`
- `logs/strategy_switch_log.csv`
- `logs/asset_strategy_memory.json`
