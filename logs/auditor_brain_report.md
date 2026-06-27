# Auditor Brain Report

**Generated:** 2026-06-12T11:41:30.758534+00:00

## DNA

The Auditor Brain validates outcomes using conservative assumptions to prevent
bias and self-deception. The Auditor never dictates how opportunities are discovered.

## Conservative execution assumptions

- Closed candles only (no partial-period lookahead)
- Next-bar entry fill after signal confirmation
- Spread: 1.2 pips, slippage: 0.3 pips, commission: $7/lot round-turn
- Stop-loss prioritized when TP and SL share a bar (worst-case)
- Mark open positions at backtest end

## Separation guarantees

- Does NOT participate in story/opportunity/scoring decisions
- Validation gates are diagnostic only — never feed back into trader thresholds
- Trader generates intent; auditor executes conservatively in backtest

## Verification stats

- Validation runs: **1**
- Trust verdict: **QUESTIONABLE**
- Conservative trades: **4298**
- Last verification: `2026-06-12T11:41:26.485145+00:00`

## Snapshot H metrics (post-split)

| Metric | Value |
|--------|-------|
| Trades | 4298 |
| Win rate | 82.0% |
| Profit factor | 8.53 |
| Max drawdown | 2.87% |
| Average R | +0.90 |

## Validation gates (diagnostic only)

- Passed: **14**
- Failed: **1**
- Diagnostic only: **True**

| Gate | Status |
|------|--------|
| average_r | PASS |
| backtest_trade_count | PASS |
| critical_system_errors | PASS |
| daily_drawdown_breach | PASS |
| max_drawdown | PASS |
| paper_trade_count | PASS |
| profit_factor | PASS |
| total_drawdown_halt | PASS |
| trust_verdict | FAIL |
| win_rate | PASS |

## Snapshot comparison (G vs H)

| | Trades | WR | PF | DD | Avg R |
|---|--------|-----|-----|--------|-------|
| G (pre-split) | 802 | 96.3% | 2.56 | 2.50% | +0.11 |
| H (post-split) | 4298 | 82.0% | 8.53 | 2.87% | +0.90 |