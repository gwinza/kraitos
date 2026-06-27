# Metric Integrity Audit

**Generated:** 2026-06-12T11:51:59.050834+00:00
**Edition:** Kraitos DNA v1.0 — Thesis Doctrine (frozen)
**Journal:** `C:\Users\Asus\kraitos\logs\conservative_trade_journal.csv`
**Trust verdict:** `QUESTIONABLE` | Data source: `synthetic`

## Executive finding

Headline performance metrics (WR, PF, DD, Avg R) **recompute exactly** from `conservative_trade_journal.csv`. Reported values are **mathematically consistent** with implemented formulas. Material reporting caveats exist for **trades/day normalization**, **TP1 hit rate denominator**, and **runner PnL journal completeness**.

## Formulas and verification

| Metric | Reported | Recomputed | Confidence | Notes |
|--------|----------|------------|------------|-------|
| Win Rate | 0.8197 | 0.8197 | HIGH | Position-level WR 81.9% (4290 positions) vs event-level 82.0% (4298 events). Δ 8 |
| Profit Factor | 8.5318 | 8.5318 | HIGH | Position-aggregated PF identical — partial PnL included once per slice. |
| Max Drawdown | 2.8657 | 2.8657 | HIGH |  |
| Average R | 0.8985 | 0.8985 | MEDIUM | Position-aggregated mean R +0.90R. Partial exits report ~1.35R on the closed sli |
| Average R:R (thesis report) | 0.6120 | 2.1330 | MEDIUM | Thesis tracker uses net_reward after spread to liquidity target — not realised R |
| Trades/day (reported) | 8.5300 | 8.5278 | LOW | Active-day rate: 1072/day over 4 journal days only. |
| TP1 hit rate | 0.4993 | 0.6760 | LOW | Reported 49.9% vs corrected 67.6%. |
| Runner continuation rate | 0.0000 | 0.0028 | LOW | 2892 partial trades lack runner close in journal. |

## Formula reference

- **Win rate:** `count(profit_loss > 0) / count(closed events)`
- **Profit factor:** `sum(win PnL) / abs(sum(loss PnL))`
- **Max drawdown:** sequential peak-to-trough on post-trade balance
- **Average R:** `mean(r_multiple)`; fallback `PnL / initial_risk_amount(entry, SL, lots)`
- **Thesis avg R:R:** `mean((target_liquidity_pips - spread) / risk_pips)` at thesis build (pre-trade)
- **TP1 hit rate (reported):** `ThesisTracker.tp1_hits / theses_tradeable`
- **TP1 hit rate (corrected):** `partial_take_profit events / positions opened`

## Average R:R classification

The thesis report **Average R:R (0.612)** is **pre-trade structural R:R** at thesis construction (reward to liquidity target minus spread, divided by stop distance). It is **not** realised R:R, **not** expectancy-adjusted R:R, and **not** the same as journal TP2/risk ratio (mean ~2.133 from open rows).

## Partial exit accounting

- Partial TP1 events: **2900**
- Unique trades with partial: **2900**
- Mean R on partial slice: **1.35R** (median 1.33R)
- Trades with runner close in journal: **8**
- Partial trades **without** runner journal close: **2892**
- Positions with 2+ close events: **8**
- Break-even stop exits (|PnL| < $1): **1**

**Finding:** After TP1 partial, runner PnL is often **not journaled** unless the runner hits stop/TP/backtest_end. ~67% of positions take TP1 partial; most runner outcomes are invisible in the journal, understating total trade lifecycle visibility.

## PF and split exits

PF uses **every closed journal row**. Partial wins add to gross profit; runner closes (when journaled) add separately. Position-level PF matches event-level PF in this run — no double-count of the same PnL.

## Simultaneous exposure

Participation tracker recorded max **1232** simultaneous open positions (unlimited opportunity doctrine). Exposure caps are allocation-scaled, not hard vetoes.

## Sample trade calculations

- `cbt-NZDUSD-2023-01-10T09-25-00+00-00-harvest` | loss | PnL $-4.82 | R=-1.02 | reason=stop_loss
- `cbt-USDCAD-2023-01-10T09-15-00+00-00-harvest` | loss | PnL $-5.03 | R=-1.02 | reason=stop_loss
- `cbt-USDCAD-2023-01-10T09-25-00+00-00-harvest` | loss | PnL $-4.82 | R=-1.02 | reason=stop_loss

## Discrepancies and corrected values

| Issue | Reported | Corrected / Interpretation |
|-------|----------|---------------------------|
| Trade count | 4298 events | **4290 positions** (8 partial double-counts) |
| TP1 hit rate | 49.9% (vs theses) | **67.6%** (vs positions) |
| Trades/day | 8.53 / 504 calendar days | **1072** / 4 active journal days |
| Runner continuation | 0.0% | **Not instrumented**; proxy 0.3% |

