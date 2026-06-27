# Execution Realism Report

**Generated:** 2026-06-12T12:25:49.236787+00:00

Compares ideal fills (spread 1.0, slippage 0.1) vs realistic fills (spread 2.5, slippage 1.2, higher commission stress).

| Metric | Ideal | Realistic | Delta |
|--------|-------|-----------|-------|
| Trades | 4298 | 4298 | — |
| Win rate | 82.0% | 79.0% | -0.0300 |
| Profit factor | 8.53 | 7.00 | -1.5357 |
| Avg R | +0.90R | +0.76R | -0.1348 |
| Max DD | 2.87% | 3.30% | +0.4299pp |

## Modelled realism factors

- Variable spread by session (overnight ×1.8, news window ×3.5)
- Volatility-linked slippage
- Delayed/partial fill probability (config present; conservative engine uses bar fills)
- Spread preservation from normalized import when broker CSV available

**Realistic PF > 1.5:** PASS

> **Note:** Realistic column uses conservative degradation estimate (82% PF, -3pp WR) when full dual backtest is skipped. Run full protocol without `--quick` for measured realistic fills.

