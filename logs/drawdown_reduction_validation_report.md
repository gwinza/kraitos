# Drawdown Reduction Validation Report

**Generated:** 2026-06-12T11:41:29.531801+00:00

**Safety:** Live trading remains disabled. Drawdown reports are diagnostic only.

## Metrics comparison

| Snapshot | Trades | Win rate | PF | Max DD | Avg R |
|----------|--------|----------|-----|--------|-------|
| Baseline (pre drawdown controls @ 22:39 UTC) | 430 | 86.5% | 2.03 | 21.80% | +0.13R |
| Drawdown controls (current) | 4298 | 82.0% | 8.53 | 2.87% | +0.90R |

## Target gates

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Trades | ≥ 430 | 4298 | PASS |
| Win rate | ≥ 65% | 82.0% | PASS |
| Profit factor | ≥ 1.5 | 8.53 | PASS |
| Max drawdown | ≤ 15% (ideal <12%) | 2.87% | PASS |
| Average R | ≥ +0.15 | +0.90 | PASS |

## Delta vs baseline

- Trades: +3868
- Win rate: -4.5%
- PF: +6.50
- Max DD: -18.93pp
- Avg R: +0.77R
