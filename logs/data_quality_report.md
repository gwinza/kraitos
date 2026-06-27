# Kraitos Data Quality Report

**Generated:** 2026-06-09T17:02:48.817608+00:00
**Validation engine:** conservative
**Data source:** `synthetic`
**Trust verdict:** `QUESTIONABLE`
**Data quality score:** 55.6

## Coverage

- Walk-forward years: **2022, 2023, 2024, 2025, 2026**
- Symbols: **EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF, EURGBP, EURJPY, GBPJPY, XAUUSD**
- Conservative closed trades: **382**
- Paper closed trades: **42**

## Conservative metrics

- Win rate: **83.5%**
- Profit factor: **1.260634097179771**
- Max drawdown: **12.40%**
- Average R: **+0.04R**

## Error classification

- Expected test errors: **1**
- Real runtime errors: **0**
- Critical runtime errors: **0**

### Expected test errors

- Emergency stop activated: Operator emergency stop

## Per-symbol conservative trades

- **AUDUSD**: 52 trades, PF 2.9054872977019413, avg R +0.15
- **GBPUSD**: 30 trades, PF inf, avg R +0.27
- **NZDUSD**: 61 trades, PF 0.9344058811281775, avg R -0.02

## Synthetic data notice

Walk-forward validation used **synthetic** candles. Trust verdict is capped at `QUESTIONABLE` until broker or imported historical data is available.
