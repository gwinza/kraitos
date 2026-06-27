# Harvest Intelligence Validation Report

**Generated:** 2026-06-12T11:41:26.531363+00:00

Conservative walk-forward validation with Harvest Opportunity Score,
Archetype Memory, Strategy Marketplace (EV selection), and ATR Dynamic Pip Targets.

**Maturity estimate:** 95%

**Safety:** Live trading remains disabled. No artificial gate lowering.

## Metrics comparison

| Snapshot | Trades | Win rate | PF | Max DD | Avg R |
|----------|--------|----------|-----|--------|-------|
| Baseline (pre-harvest intelligence) | 430 | 86.5% | 2.03 | 21.80% | +0.13R |
| Harvest intelligence (current) | 4298 | 82.0% | 8.53 | 2.87% | +0.90R |

## Target gates

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Trades | ≥ 500 | 4298 | PASS |
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

## Harvest intelligence modules

- **Harvest Opportunity Score** — trend/momentum/liquidity/session/spread/ATR scoring
- **Archetype Memory** — per-symbol/session/regime archetype performance gates
- **Strategy Marketplace** — EV-based strategy competition (50/100/250 windows)
- **Dynamic Pip Targets** — ATR-band targets with spread and choppiness filters
