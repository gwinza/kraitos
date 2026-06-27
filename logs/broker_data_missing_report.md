# Broker Data Missing Report

**Generated:** 2026-06-12T12:49:48.186893+00:00
**DNA:** v1.0 Thesis Edition (frozen)

## Status: BROKER DATA NOT FOUND

Broker-grade proof run **cannot proceed**. No CSV files were detected in import folders.

## Folder status

- `data/mt5_exports/` — **exists** (empty)
- `data/exness_exports/` — **exists** (empty)
- `data/dukascopy_exports/` — **exists** (empty)
- `data/normalized/` — **exists** (empty)

## Required symbols

- **EURUSD**
- **GBPUSD**
- **AUDUSD**
- **USDJPY**
- **GBPJPY**
- **XAUUSD**

## Required timeframe

**M1 (1-minute OHLCV)** — UTC timestamps preferred

## Required years

- **2022**
- **2023**
- **2024**
- **2025**
- **2026 YTD**

## Required columns

`time/timestamp, open, high, low, close, volume` (optional: `spread` or `spread_pips`)

## Example filenames

- `data/mt5_exports/EURUSD_M1.csv`
- `data/mt5_exports/EURUSD.csv`
- `data/exness_exports/EURUSD-M1.csv`
- `data/dukascopy_exports/EURUSD_dukascopy_m1.csv`
- `data/mt5_exports/GBPUSD_M1.csv`
- `data/mt5_exports/GBPUSD.csv`
- `data/exness_exports/GBPUSD-M1.csv`
- `data/dukascopy_exports/GBPUSD_dukascopy_m1.csv`
- `data/mt5_exports/AUDUSD_M1.csv`
- `data/mt5_exports/AUDUSD.csv`
- `data/exness_exports/AUDUSD-M1.csv`
- `data/dukascopy_exports/AUDUSD_dukascopy_m1.csv`
- _(and similar for remaining symbols — 6 total)_

## Scanned inventory

CSV files found: **0**

## Next steps

1. Export M1 history from MT5, Exness, or Dukascopy for each symbol
2. Place files in the appropriate `data/*_exports/` folder
3. Re-run: `python -m validation.broker_grade_proof`

> **Do not** substitute synthetic data for broker proof. Kraitos must be judged on real imports.

