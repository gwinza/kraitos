# Post Drawdown Throttle Undo Validation Report

**Generated:** 2026-06-12T11:41:30.743390+00:00

Validation after removing drawdown-aware trade starvation layers.
Harvesting restored; catastrophic protection only (DD >25% hard block).

**Safety:** Live trading remains disabled.
Drawdown attribution and reduction reports are **diagnostic only** — no enforcement.

See also: `logs/drawdown_throttle_undo_report.md` for code changes and throttles removed.

## Metrics comparison

| Snapshot | Trades | Win rate | PF | Max DD | Avg R |
|----------|--------|----------|-----|--------|-------|
| A (pre-DD throttles) | 430 | 86.5% | 2.03 | 21.80% | +0.13R |
| B (DD throttles) | 274 | 85.8% | 1.83 | 11.56% | +0.11R |
| C (portfolio) | 200 | 76.5% | 1.33 | 11.19% | +0.07R |
| D (post-undo — current) | 4298 | 82.0% | 8.53 | 2.87% | +0.90R |

## Target gates (post-undo)

Max drawdown may rise vs throttled runs — acceptable to preserve harvesting.

| Metric | Target | Current (D) | Status |
|--------|--------|-------------|--------|
| Trades | ≥ 430 | 4298 | PASS |
| Win rate | ≥ 65% | 82.0% | PASS |
| Profit factor | ≥ 1.5 | 8.53 | PASS |
| Average R | ≥ +0.13 | +0.90 | PASS |
| Max drawdown | informational (may exceed 15%) | 2.87% | — |

## Delta vs pre-throttle baseline (A)

- Trades: +3868
- Win rate: -4.5%
- PF: +6.50
- Max DD: -18.93pp
- Avg R: +0.77R

## Delta vs throttled portfolio (C)

- Trades: +4098
- Win rate: +5.5%
- PF: +7.20
- Max DD: -8.32pp
- Avg R: +0.83R

## Undo scope (diagnostic drawdown, catastrophic protection only)

- **Removed:** multi-tier DD risk multipliers, loss-streak pauses, DD-based add-on blocks,
  correlation cluster hard caps, same-direction DD stacking blocks, OAS DD penalties.
- **Kept:** DD >25% new-entry hard block, emergency stop, live-trading-disabled gate,
  portfolio heat catastrophic halt, validation gate.
- **Reports:** `drawdown_attribution_report.md`, `drawdown_reduction_validation_report.md`,
  and `risk_cluster_report.md` are analysis-only — no trade suppression.
