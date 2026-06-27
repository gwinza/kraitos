# Kraitos Backtest Red-Team Report

**Generated:** 2026-06-08T18:07:09.558632+00:00
**Trust rating:** **INVALID**

## Executive summary

Backtest results are **not credible** for strategy validation under the default engine.

## Reported debug backtest (optimistic path)

- Win rate: **96.2%**
- Total return: **+49.10%**

## Verdict reasons

- Return drops 67.9 pts under conservative fills (+104.3% -> +36.4%).
- Published backtest win rate 96.2% is unusually high for FX.
- Published return +49.1% over a short synthetic window is aggressive.
- 2 critical optimistic bias(es) documented in default engine.

## Bias checklist

| Code | Severity | Optimistic? | Mitigation |
|------|----------|-------------|------------|
| incomplete_bar_lookahead | critical | yes | Evaluate at bar close with closed-candle slice only. |
| htf_partial_period | critical | yes | Exclude HTF bars until bar_close_time <= moment. |
| same_bar_entry | high | yes | Queue fills for next bar open. |
| tp_sl_ambiguity | medium | no | Stop loss is checked first when both levels trade. |
| missing_commission | high | yes | Round-turn commission debited on open and close. |
| missing_slippage | medium | yes | Configurable slippage pips applied against the trader. |
| backtest_end_close | medium | yes | Mark at spread-adjusted price; label as backtest_end_mark. |
| synthetic_weekday_filter | medium | yes | Use longer spans and real tick data for production validation. |
| short_sample_window | medium | yes | Extend history and include volatile/ranging regimes. |
| overlapping_signals | low | yes | Risk controller enforces correlated exposure (unchanged). |

## Optimistic vs conservative replay

- Sample: **35000** M1 bars, symbols EURUSD, GBPUSD

| Metric | Optimistic | Conservative |
|--------|------------|--------------|
| Closed trades | 502 | 161 |
| Win rate | 98.8% | 96.3% |
| Total return | +104.29% | +36.36% |
| Profit factor | 33.52 | 8.19 |
| Max drawdown | 0.10% | 0.13% |

### Conservative execution assumptions

- Closed candles only (no partial HTF periods)
- Signal at bar close, entry at next bar open
- Stop loss first when TP and SL share a bar
- Spread 1.2 pips, slippage 0.3 pips, commission $7/lot round turn

## Recommendations

1. Adopt `ConservativeBacktestEngine` for validation gates.
2. Replace inclusive candle slicing in the default engine when auditing.
3. Validate on real tick or M1 data spanning multiple regimes.
4. Keep `LIVE_TRADING` disabled until forward/paper sample is sufficient.
