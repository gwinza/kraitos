# Portfolio vs Drawdown Controls Comparison

**Generated:** 2026-06-12T11:41:29.532816+00:00

## A / B / C comparison

| Variant | Trades | WR | PF | DD | Avg R | Trade preservation | DD control |
|---------|--------|-----|-----|-----|-------|-------------------|------------|
| A — Opportunity Allocation | 430 | 86.5% | 2.03 | 21.8% | +0.13R | High | Low |
| B — Drawdown Controls | 274 | 85.8% | 1.83 | 11.6% | +0.11R | Low (-156) | High |
| C — Portfolio Construction | 4298 | 82.0% | 8.53 | 2.87% | +0.90R | High | High |

## Design intent

- **A** maximizes opportunity capture but accepts high drawdown.
- **B** cuts drawdown via trade starvation (430→274).
- **C** ranks and scales capital via OAS, risk budget, correlation, heat — preserving scan volume.

## C vs B deltas

- Trades recovered: +4024 (target: recover ≥156)
- DD change: -8.73pp
- PF change: +6.70
- Avg R change: +0.79R
