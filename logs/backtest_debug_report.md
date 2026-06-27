# Kraitos Backtest Debug Report

**Generated:** 2026-06-08T17:44:26.493637+00:00
**Symbols:** EURUSD, GBPUSD, USDJPY

## Engine configuration

- driver_timeframe: `M5`
- step: `2`
- min_warmup_bars: `0`
- m1_bars_per_symbol: `35000`
- symbols: `EURUSD, GBPUSD, USDJPY`
- timeframe_note: `M1 base resampled to M5/M15/H1/H4/H8`
- live_trading: `False`
- min_closed_trades_target: `100`

## Results

- Closed trades: **239**
- Open positions remaining: **0**
- Total signals collected: **4308**

## Performance metrics

- Win rate: **96.2%**
- Profit factor: **7.59**
- Max drawdown: **0.20%**
- Average R: **+0.17R**
- Total closed trades: **239**

## Performance summary

```text
=== Kraitos Validation Performance ===
Initial balance:     $10,000.00
Final balance:       $14,910.25
Equity:              $14,910.25
Total return:        +49.10%
Max drawdown:        0.20%
Daily drawdown:      0.00%
Total trades:        239
Win rate:            96.2%
Profit factor:       7.59
Average R:           +0.17R
Gross profit:        $5,655.26
Gross loss:          $745.01
Daily P/L:
  2025-01-16: $+209.85
  2025-01-17: $+391.79
  2025-01-20: $+407.63
  2025-01-21: $+477.77
  2025-01-22: $+398.95
  2025-01-23: $+495.97
  2025-01-24: $+623.36
  2025-01-27: $+362.53
  2025-01-28: $+408.82
  2025-01-29: $+630.48
  2025-01-30: $+503.09
Safety: ACTIVE
```

## Skip analysis excerpt

# Kraitos Skip Analysis

**Generated:** 2026-06-08T17:44:26.493637+00:00

## Overview

- Timeline evaluations: **4308**
- Warmup skips: **0**
- Account safety skips: **0**
- TRADE signals: **239**
- Positions opened: **239**
- Positions closed: **239**
- NO_TRADE records: **4069**

## Root causes checked

| Check | Finding |
|-------|---------|
| Timeframe alignment | M1 base resampled to M5/M15/H1/H4/H8 |
| Session filter | Uses bar timestamp in backtest (`evaluation_moment`) |
| Validation gate | Does not block backtest execution |
| Live trading | Remains disabled |
| Risk controller | Active — rejections listed below |

## NO_TRADE reason counts

- **842** — Mandatory conditions failed: directional_bias, valid_market_structure
- **188** — Entry waiting: pending momentum. Momentum conflicts with bias: bias=bullish, momentum=sell
- **38** — Mandatory conditions failed: directional_bias
- **16** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $420.00 > $319.30 (3.00%)
- **15** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $460.00 > $356.58 (3.00%)
- **15** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $520.00 > $397.24 (3.00%)
- **10** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000006, M5 momentum 0.000015)
- **10** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $400.00 > $311.46 (3.00%)
- **10** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000004, M5 momentum 0.000019)
- **9** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $440.00 > $344.61 (3.00%)
- **9** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $500.00 > $382.84 (3.00%)
- **8** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000005, M5 momentum 0.000018)
- **8** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $540.00 > $412.52 (3.00%)
- **8** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $560.00 > $423.04 (3.00%)
- **7** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000002, M5 momentum 0.000021)
- **7** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000003, M5 momentum 0.000023)
- **7** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000001, M5 momentum -0.000002)
- **7** — Entry rejected: failed risk. Risk rejected: Max risk per symbol exceeded for EURUSD: $315.00 > $212.87 (2.00%)
- **7** — Entry waiting: pending momentum. Momentum not confirmed: Direction is unclear (M1 momentum 0.000002, M5 momentum 0.000010)
- **7** — Entry rejected: failed risk. Risk rejected: Max correlated exposure exceeded in group 'usd_majors': $440.00 > $334.83 (3.00%)

## Mandatory harvest failures

- **880** — directional_bias
- **842** — valid_market_structure

## Pipeline stage failures

- **entry_reject**: 3086
- **risk_reject**: 3086
- **entry_wait**: 983

## Executor events

- **take_profit_or_stop_loss**: 236
- **backtest_end_close**: 3