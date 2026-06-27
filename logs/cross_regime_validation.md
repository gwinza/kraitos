# Cross-Regime Validation

**Generated:** 2026-06-12T11:51:59.487204+00:00

## Scope limitation (critical)

- Data source: **synthetic** synthetic candles
- Trust verdict: **QUESTIONABLE**
- Journal active window: **4 days** (2023-01-10 → 2023-01-14)
- Walk-forward years configured: **[2022, 2023]** — **2022 data produced zero closed trades** in journal

True multi-regime validation **requires imported/broker history** across labelled years. Below: best-available slices from this run.

## By symbol (proxy for asset/regime behaviour)

| Symbol | Trades | WR | PF | Avg R | DD | Assessment |
|--------|--------|-----|-----|-------|-----|------------|
| EURGBP | 530 | 78.9% | 5.10 | +0.82R | 0.86% | Excels |
| AUDUSD | 529 | 97.7% | 67.91 | +1.20R | 0.60% | Excels |
| EURUSD | 529 | 99.4% | inf | +1.16R | 0.04% | Excels |
| GBPUSD | 529 | 99.2% | 591.65 | +1.19R | 0.00% | Excels |
| NZDUSD | 529 | 92.6% | 17.35 | +1.11R | 0.34% | Excels |
| USDCAD | 529 | 87.0% | 8.79 | +0.99R | 0.35% | Excels |
| USDCHF | 529 | 82.6% | 6.46 | +0.90R | 0.41% | Excels |
| EURJPY | 151 | 27.8% | 0.20 | -0.05R | 0.20% | Deteriorates |
| GBPJPY | 150 | 30.7% | 0.28 | -0.03R | 0.20% | Deteriorates |
| XAUUSD | 150 | 34.7% | 0.55 | -0.02R | 2.87% | Deteriorates |
| USDJPY | 143 | 7.0% | 0.01 | -0.15R | 0.33% | Deteriorates |

## By year / regime label

| Period | Regime | Trades | WR | PF | Avg R |
|--------|--------|--------|-----|-----|-------|
| 2023 (trending) | trending | 4298 | 82.0% | 8.53 | +0.90R |

## Regime matrix (evidence vs required)

| Regime | Tested? | WR | PF | Trades/day | Notes |
|--------|---------|-----|-----|------------|-------|
| Trending bull | Partial | 82% | 8.5 | high intraday | Synthetic 2023 window |
| Trending bear | No | — | — | — | Not isolated |
| Ranging | No (2022 empty) | — | — | — | YEAR_REGIME 2022 unused |
| Volatile | No | — | — | — | 2024+ not in journal |
| News-driven | No | — | — | — | Synthetic has no news calendar |
| Low liquidity | No | — | — | — | Spread model static |

## Kraitos behaviour summary

- **Excels:** G10 majors (EURUSD, GBPUSD, AUDUSD) — high WR, PF >> 1.5
- **Deteriorates:** JPY crosses, XAUUSD — negative Avg R, quarantined by strategy quality
- **Overly selective:** Neutral bias hard-rejects ~26% (appropriate safety)
- **Overly aggressive:** Intraday open count >> desk capacity (1232 max simultaneous)

## TP1 / runner by slice

TP1 partial rate ~67% of positions. Runner tracking incomplete in journal — regime-specific runner effectiveness **not measurable** from current artifacts.

