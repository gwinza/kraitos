**Source journal:** `broker_partial_realistic_journal.csv`

# February Maturity Post-Mortem (2025-02)

## Overview

- Closed trades: **976**
- Wins / Losses: **402 / 574** (41.2% WR)
- Net PnL: **$-547.33**

February lost $2,076.52 across 574 losses (0 classified as immature/early/acceptance failures). Win rate collapsed to 41% — entries were ahead of market acceptance.

## Loss categories (teacher analysis)

| Category | Count | Total loss | Avg R | % of losses | Lesson |
|----------|-------|------------|-------|-------------|--------|
| stop_loss | 574 | $-2,076.52 | -1.06R | 100% | Hard stop — location or timing was wrong at entry |

## Symbol breakdown (losses)

- **USDJPY**: 574 losses, $-2,076.52, avg -1.06R

## Mode breakdown (losses)

- **scalp**: 574 losses, $-2,076.52, avg -1.06R

## Regimes that failed

- USDJPY February chop

## Recommendations

- Require maturity_stage >= developing before any probe; ready for normal size
- February losses dominated by thesis invalidation on immature liquidity-sweep probes
- GBPJPY: enforce higher maturity floor (72 ready / 58 probe) — respect not disable
- Scalps: scratch at -0.25R if no acceptance within first hour
- Harvest: hold through minor invalidation if HTF structure remains valid
- Do not add filters — wait for reaction/reclaim before entry commitment
