# Opportunity Allocation Validation Report

**Generated:** 2026-06-12T11:41:26.530357+00:00

Conservative walk-forward validation with Trend Strength Engine, Strategy Marketplace,
Dynamic Strategy Allocation, Trend Maximiser, and Adaptive Confirmation.

**Safety:** Live trading remains disabled. No artificial gate lowering.

## Metrics comparison

| Snapshot | Trades | Win rate | PF | Max DD | Avg R |
|----------|--------|----------|-----|--------|-------|
| Baseline (pre dynamic selector) | 359 | 80.5% | 1.02 | 15.27% | +0.01R |
| Dynamic selector | 382 | 83.5% | 1.26 | 12.40% | +0.04R |
| Opportunity allocation (current) | 4298 | 82.0% | 8.53 | 2.87% | +0.90R |

## Target gates

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Trades | ≥ 500 | 4298 | PASS |
| Win rate | ≥ 65% | 82.0% | PASS |
| Profit factor | ≥ 1.5 | 8.53 | PASS |
| Max drawdown | ≤ 15% | 2.87% | PASS |
| Average R | ≥ +0.15 | +0.90 | PASS |

## Delta vs dynamic selector

- Trades: +3916
- Win rate: -1.5%
- PF: +7.27
- Max DD: -9.53pp
- Avg R: +0.86R
