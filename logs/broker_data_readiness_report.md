# Broker Data Readiness Report

**Generated:** 2026-06-27T09:14:28.606722+00:00
**Overall:** 0/6 symbols READY

## Status: NOT READY

Fix issues below, then re-run:

```
python -m validation.broker_data_readiness
```

## Per-symbol status

| Symbol | Status | File | Rows | M1 | Years | Issues |
|--------|--------|------|------|-----|-------|--------|
| EURUSD | **INCOMPLETE** | `C:\Users\Asus\kraitos\data\mt5_exports\EURUSD_M1.csv` | 372,084 | yes | 2025 | Missing or thin year coverage: 2022, 2023, 2024, 2026 |
| GBPUSD | **INCOMPLETE** | `C:\Users\Asus\kraitos\data\mt5_exports\GBPUSD_M1.csv` | 371,091 | yes | 2025 | Missing or thin year coverage: 2022, 2023, 2024, 2026 |
| AUDUSD | **INCOMPLETE** | `C:\Users\Asus\kraitos\data\mt5_exports\AUDUSD_M1.csv` | 371,221 | yes | 2025 | Missing or thin year coverage: 2022, 2023, 2024, 2026 |
| USDJPY | **INCOMPLETE** | `C:\Users\Asus\kraitos\data\mt5_exports\USDJPY_M1.csv` | 371,703 | yes | 2025 | Missing or thin year coverage: 2022, 2023, 2024, 2026 |
| GBPJPY | **INCOMPLETE** | `C:\Users\Asus\kraitos\data\mt5_exports\GBPJPY_M1.csv` | 371,076 | yes | 2025 | Missing or thin year coverage: 2022, 2023, 2024, 2026 |
| XAUUSD | **MISSING** | — | 0 | no | — | No CSV found for XAUUSD in data/*_exports/ |

## Required coverage

- Symbols: EURUSD, GBPUSD, AUDUSD, USDJPY, GBPJPY, XAUUSD
- Timeframe: M1
- Years: 2022, 2023, 2024, 2025, 2026 (2026 = YTD)

## Accepted filename examples

- `data/mt5_exports/EURUSD_M1.csv`
- `data/mt5_exports/GBPUSD_M1.csv`
- `data/mt5_exports/AUDUSD_M1.csv`
- `data/mt5_exports/USDJPY_M1.csv`
- `data/mt5_exports/GBPJPY_M1.csv`
- `data/mt5_exports/XAUUSD_M1.csv`

## Export guide

See `logs/how_to_export_mt5_m1_data.md` for MT5/Exness export steps.

