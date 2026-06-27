# Risk Manager Allocation-Only Report

**Generated:** 2026-06-12T11:41:30.752427+00:00

## Core law

RiskManager scales size — NEVER blocks except catastrophic conditions.

### Block only if

1. Emergency stop active
2. Live trading safety violation
3. Broker/execution unavailable
4. No valid TraderBrain story
5. DD ≥ 50%: stop new trades
6. DD ≥ 40%: extreme defensive micro-allocation (scale to floor)

### Scale (never reject)

| Factor | Scale bands |
|--------|-------------|
| Max open trades | 75% / 50% / 25% / 10% slot crowding |
| Daily loss budget | 100% / 75% / 50% / 25% |
| Correlation cluster | 100% / 80% / 60% / 40% / 20% |
| Portfolio heat | 100% / 75% / 50% / 25% / 10% |
| Symbol exposure | soft scale 75% / 50% / 25% |
| USD stacking | soft scale via exposure netting |
| Loss streaks | 75% (3+) / 50% (5+) — report only |
| OAS score | size tier only (defer 15%, watchlist 25%) |
| Normal drawdown | 75% (15%+) / 50% (25%+) / 10% (40%+) |

## Opportunity tiers (base risk)

| Tier | Risk range |
|------|------------|
| HARVEST | 0.10–0.30% |
| PROPER | 0.50–1.00% |
| ELITE | 1.00–1.50% |

## Floor

Minimum allocated risk: **0.01%** or **0.01 lot** — never zero unless catastrophic.
