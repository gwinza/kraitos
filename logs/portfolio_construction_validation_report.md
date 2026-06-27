# Portfolio Construction Validation Report

**Generated:** 2026-06-12T11:41:29.532816+00:00

Institutional Portfolio Construction and Allocation Engine validation.

**Safety:** Live trading remains disabled. Portfolio scales risk; does not starve opportunities.

## Metrics comparison

| Snapshot | Trades | Win rate | PF | Max DD | Avg R |
|----------|--------|----------|-----|--------|-------|
| Opportunity Allocation (A) | 430 | 86.5% | 2.03 | 21.8% | +0.13R |
| Drawdown Controls (B) | 274 | 85.8% | 1.83 | 11.6% | +0.11R |
| Portfolio Construction (C) | 4298 | 82.0% | 8.53 | 2.87% | +0.90R |

## Target gates (C)

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Trades | ≥ 430 (500+ ideal) | 4298 | PASS |
| Win rate | ≥ 65% | 82.0% | PASS |
| Profit factor | ≥ 1.5 | 8.53 | PASS |
| Max drawdown | ≤ 15% (14% ideal) | 2.87% | PASS |
| Average R | ≥ +0.15 | +0.90R | PASS |

## Delta vs drawdown controls (B)

- Trades: +4024
- Win rate: -3.8%
- PF: +6.70
- Max DD: -8.73pp
- Avg R: +0.79R
