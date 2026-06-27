# Kraitos Live Readiness Report

**Generated:** 2026-06-09T17:02:48.817608+00:00
**Validation status:** `NEEDS_MORE_DATA`
**Live trading enabled:** `False` (unchanged — safe mode)

## Metrics summary (from logs)

- Validation engine: **conservative**
- Data source: **synthetic**
- Trust verdict: **QUESTIONABLE**
- Data quality score: **55.6**
- Conservative closed trades: **382**
- Paper closed trades: **42**
- Optimistic metrics: **research_demo_only**
- Backtest win rate: **83.5%**
- Paper win rate: **95.2%**
- Backtest profit factor: **1.260634097179771**
- Paper profit factor: **16.705986959098993**
- Backtest max drawdown: **12.40%**
- Paper max drawdown: **7.14%**
- Backtest average R: **+0.04R**
- Paper average R: **+0.19R**
- Daily drawdown breaches: **0**
- Expected test errors: **1**
- Real runtime errors: **0**
- Critical runtime errors: **0**

## Validation report

```text
============================================================
KRAITOS LIVE READINESS REPORT
============================================================
Strategy:          kraitos
Generated:         2026-06-09T17:02:48.832464+00:00
Status:            NEEDS_MORE_DATA
Backtest trades:   382
Paper trades:      42

SUMMARY
------------------------------------------------------------
- Insufficient trade history to complete validation.
- backtest: required >= 500, got 382

CRITERIA
------------------------------------------------------------
[BACKTEST]
  [FAIL] backtest_trade_count: required >= 500, actual 382 (Minimum conservative backtest trades collected)
  [PASS] win_rate: required >= 52%, actual 83.5% (Win rate meets minimum edge threshold)
  [FAIL] profit_factor: required >= 1.3, actual 1.26 (Profit factor meets minimum threshold)
  [PASS] max_drawdown: required <= 15%, actual 12.40% (Maximum drawdown within safety limit)
  [PASS] average_r: required > 0.0R, actual +0.04R (Average R-multiple is positive)
  [PASS] daily_drawdown_breach: required no breach, actual ok (No daily drawdown safety breach during phase)
  [FAIL] trust_verdict: required TRUSTWORTHY, actual QUESTIONABLE (Conservative backtest trust rating from red-team audit)

[PAPER]
  [PASS] paper_trade_count: required >= 30, actual 42 (Minimum forward/paper trades collected)
  [PASS] win_rate: required >= 52%, actual 95.2% (Win rate meets minimum edge threshold)
  [PASS] profit_factor: required >= 1.3, actual 16.71 (Profit factor meets minimum threshold)
  [PASS] max_drawdown: required <= 15%, actual 7.14% (Maximum drawdown within safety limit)
  [PASS] average_r: required > 0.0R, actual +0.19R (Average R-multiple is positive)
  [PASS] daily_drawdown_breach: required no breach, actual ok (No daily drawdown safety breach during phase)

[SYSTEM]
  [PASS] critical_system_errors: required none, actual 0 (No critical system errors recorded)
  [PASS] total_drawdown_halt: required no halt, actual ok (No total drawdown safety halt triggered)

LIVE TRADING GATE
------------------------------------------------------------
Strategy validation: NOT READY — current status is NEEDS_MORE_DATA.
System live trading flag: DISABLED (default safe mode).
No real orders will be placed regardless of validation status.

NEXT STEPS
------------------------------------------------------------
Collect more conservative backtest trades (minimum 500 closed trades required).
Ensure journal and performance metrics are being recorded.
Re-run validation once trade history thresholds are met.
============================================================
```
