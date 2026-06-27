# Data Import Report

**Generated:** 2026-06-27T10:27:43.707467+00:00

## Summary

- Files processed: **5**
- Successful imports: **5**
- Failed: **0**
- No CSV files found: **False**

## Expected drop locations

- `data/mt5_exports/` — MT5 History Center exports
- `data/exness_exports/` — Exness historical CSV
- `data/dukascopy_exports/` — Dukascopy tick/minute CSV
- `data/broker_history/` — legacy broker path (also scanned)

Normalized output: `data/normalized/{SYMBOL}_M1.csv`

## Normalized schema

`timestamp, symbol, open, high, low, close, volume, spread` (UTC)

## Import details

### AUDUSD (mt5) — OK
- Input: `C:\Users\Asus\kraitos\data\mt5_exports\AUDUSD_M1.csv`
- Output: `C:\Users\Asus\kraitos\data\normalized\AUDUSD_M1.csv`
- Rows: 371221 read → 372783 written (dupes removed: 60, gaps filled: 1622)

### EURUSD (mt5) — OK
- Input: `C:\Users\Asus\kraitos\data\mt5_exports\EURUSD_M1.csv`
- Output: `C:\Users\Asus\kraitos\data\normalized\EURUSD_M1.csv`
- Rows: 372084 read → 372999 written (dupes removed: 60, gaps filled: 975)

### GBPJPY (mt5) — OK
- Input: `C:\Users\Asus\kraitos\data\mt5_exports\GBPJPY_M1.csv`
- Output: `C:\Users\Asus\kraitos\data\normalized\GBPJPY_M1.csv`
- Rows: 371076 read → 371751 written (dupes removed: 60, gaps filled: 735)

### GBPUSD (mt5) — OK
- Input: `C:\Users\Asus\kraitos\data\mt5_exports\GBPUSD_M1.csv`
- Output: `C:\Users\Asus\kraitos\data\normalized\GBPUSD_M1.csv`
- Rows: 371091 read → 372784 written (dupes removed: 60, gaps filled: 1753)

### USDJPY (mt5) — OK
- Input: `C:\Users\Asus\kraitos\data\mt5_exports\USDJPY_M1.csv`
- Output: `C:\Users\Asus\kraitos\data\normalized\USDJPY_M1.csv`
- Rows: 371703 read → 372905 written (dupes removed: 60, gaps filled: 1262)

