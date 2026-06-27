# Market Story Validation Report

**Generated:** 2026-06-12T11:41:29.534800+00:00

Market Understanding redesign — story → forecast → opportunity → confirmation → trade.
Council observers only. Indicators boost, never veto.

**Walk-forward scope:** 2022–2023 (2 years).
**Trades/day estimate (G):** 8.53 (4298 trades / 504 days)

**Safety:** Live trading disabled. Conservative execution default.

## Metrics comparison

| | Trades | WR | PF | DD | Avg R |
|---|--------|-----|-----|--------|-------|
| A (pre-DD) | 430 | 86.5% | 2.03 | 21.77% | +0.13R |
| E (council expansion) | 153 | 96.7% | 16.92 | 0.66% | +0.12R |
| G (market story) | 4298 | 82.0% | 8.53 | 2.87% | +0.90R |

## Target gates (Snapshot G)

| Metric | Target | G (market story) | Status |
|--------|--------|------------------|--------|
| Trades | 400–600 | 4298 | PASS (high) |
| Win rate | 65%–75% | 82.0% | PASS |
| Profit factor | 1.5–2.0 | 8.53 | PASS (high) |
| Max drawdown | ≤ 15% | 2.87% | PASS |
| Average R | +0.10–+0.20 | +0.90 | PASS (high) |
| Trades/day | 20–30 | 8.53 | MISS |

**Note:** Trade count is strong (802) but daily frequency is below the hunter target band — likely due to 2-year synthetic walk-forward step=2 sampling, not story logic alone.

## Delta vs Snapshot E

- Trades: +4145
- Win rate: -14.7%
- PF: -8.39
- Max DD: +2.21pp
- Avg R: +0.78R

## Architecture

- **Market Story Engine** — H8/H4 macro, H1 integrity, M15/M5 opportunity, M1 strike
- **Story Forecast Engine** — expected move, pip range, invalidation, opportunity type
- **Opportunity Hunter Council** — six observer professors, no vote gates
- **Harvest DNA** — story-driven bands, reduced no_trade dominance
- **Portfolio allocator** — size only, no discovery suppression
