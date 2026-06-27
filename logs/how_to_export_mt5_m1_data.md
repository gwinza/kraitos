# How to Export Broker M1 Data for Kraitos Proof Testing

**DNA:** v1.0 Thesis Edition (frozen)  
**Purpose:** Prepare real broker-grade M1 CSV history — **no doctrine changes required**.

---

## Required symbols

| Symbol | Example filename |
|--------|------------------|
| EURUSD | `data/mt5_exports/EURUSD_M1.csv` |
| GBPUSD | `data/mt5_exports/GBPUSD_M1.csv` |
| AUDUSD | `data/mt5_exports/AUDUSD_M1.csv` |
| USDJPY | `data/mt5_exports/USDJPY_M1.csv` |
| GBPJPY | `data/mt5_exports/GBPJPY_M1.csv` |
| XAUUSD | `data/mt5_exports/XAUUSD_M1.csv` |

**Timeframe:** M1 (1-minute candles)  
**History:** 2022, 2023, 2024, 2025, 2026 YTD

---

## Required CSV columns

Minimum (any of these timestamp header names work):

```
time, open, high, low, close, volume
```

Also accepted:

- Timestamp: `timestamp`, `datetime`, `Date` + `Time` (MT5 split columns)
- Volume: `volume`, `tick_volume`, `TickVolume`, `vol`
- Optional: `spread` or `spread_pips` (preserved when present)

Timestamps should be **UTC** when possible.

---

## Method A — MetaTrader 5 (MT5) History Center

Use this for Exness MT5, IC Markets, or any MT5 broker terminal.

### Step 1 — Open History Center

1. Launch **MetaTrader 5** and log in to your broker account.
2. Menu: **View → Symbols** (or press `Ctrl+U`).
3. Find each required symbol (e.g. `EURUSD`) and ensure it is **visible** in Market Watch.
4. Menu: **Tools → History Center** (or press `F2`).

### Step 2 — Download M1 history

For **each symbol** (EURUSD, GBPUSD, AUDUSD, USDJPY, GBPJPY, XAUUSD):

1. In History Center, expand the symbol in the left tree.
2. Select **1 Minute (M1)**.
3. Click **Download** (cloud icon) if history is incomplete.
4. Scroll the date range to confirm data from **2022-01-01** through **today (2026 YTD)**.
5. If gaps remain, click **Download** again or switch to a longer server history if your broker offers it.

> Tip: Gold is often listed as `XAUUSD` or `GOLD` — export using the symbol your terminal trades; rename the file to `XAUUSD_M1.csv` for Kraitos.

### Step 3 — Export to CSV

1. With **M1** selected for the symbol, click **Export** (disk icon).
2. Choose **CSV** format.
3. Save as `{SYMBOL}_M1.csv` (e.g. `EURUSD_M1.csv`).
4. Repeat for all six symbols.

### Step 4 — Place files in Kraitos

Copy each exported file to:

```
C:\Users\Asus\kraitos\data\mt5_exports\
```

Expected layout:

```
data/mt5_exports/EURUSD_M1.csv
data/mt5_exports/GBPUSD_M1.csv
data/mt5_exports/AUDUSD_M1.csv
data/mt5_exports/USDJPY_M1.csv
data/mt5_exports/GBPJPY_M1.csv
data/mt5_exports/XAUUSD_M1.csv
```

### MT5 export format example

```csv
Date,Time,Open,High,Low,Close,TickVolume
2022.01.03,00:00,1.13650,1.13672,1.13640,1.13665,142
2022.01.03,00:01,1.13665,1.13680,1.13660,1.13675,118
```

---

## Method B — Exness MT5 terminal (same as Method A)

Exness uses the standard MT5 platform. Follow **Method A** exactly.

Alternative drop location (also scanned):

```
data/exness_exports/EURUSD-M1.csv
data/exness_exports/GBPUSD-M1.csv
...
```

Exness-specific column example:

```csv
datetime,open,high,low,close,tick_volume
2022-01-03 00:00:00+00:00,1.13650,1.13672,1.13640,1.13665,142
```

---

## Method C — Dukascopy (optional)

If you use Dukascopy historical data:

1. Download M1 bid/ask or OHLC from [Dukascopy historical data](https://www.dukascopy.com/swiss/english/marketwatch/historical/).
2. Place files in `data/dukascopy_exports/` (e.g. `EURUSD_dukascopy_m1.csv`).

---

## Verify before proof run

After placing CSV files, run the readiness checker:

```powershell
Set-Location C:\Users\Asus\kraitos
python -m validation.broker_data_readiness
```

When all six symbols show **READY**, run broker-grade proof:

```powershell
python -m validation.broker_grade_proof
```

Readiness report: `logs/broker_data_readiness_report.md`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| File not detected | Use exact names under `data/mt5_exports/` or ensure symbol appears in filename |
| BAD FORMAT | Include open/high/low/close columns; check timestamp column name |
| INCOMPLETE | Re-download history; ensure 2022–2026 YTD coverage |
| NOT ENOUGH DATA | Export full M1 range, not just recent weeks |
| Wrong timeframe | Re-export **M1**, not M5/H1 |
| Duplicate timestamps | Re-export; Kraitos deduplicates but large duplicate counts fail readiness |

---

## What Kraitos does NOT change

This data-loading step does **not** modify:

- Thesis doctrine logic
- Indicators or filters
- Risk rules
- Entry/exit behaviour

Broker data is imported as-is, normalized to `data/normalized/{SYMBOL}_M1.csv`, then used for proof validation only.
