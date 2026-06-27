# Average R Diagnostic Report

**Generated:** 2026-06-11T00:54:31.879937
**Source:** `conservative_trade_journal.csv` (151 closed trades)

## Snapshot E Baseline

| Metric | Value |
|--------|-------|
| Trades | 151 |
| Avg R | +0.136 |
| Median R | +0.110 |
| Max R | +0.470 |
| Min R | -1.020 |

### Key Finding

Avg R is capped by **micro take-profit targets** (majority <3 pip TP) against **wide structural stops** (~38-49 pip SL). Wins cluster at +0.07 to +0.13 R; larger targets (6+ pips) show materially higher avg R.

## By Symbol

| Bucket | Trades | Avg R | Win% |
|--------|--------|-------|------|
| GBPUSD | 151 | +0.136 | 96.7% |

## By Strategy Mode

| Bucket | Trades | Avg R | Win% |
|--------|--------|-------|------|
| harvest | 151 | +0.136 | 96.7% |

## By Session (UTC)

| Bucket | Trades | Avg R | Win% |
|--------|--------|-------|------|
| asia | 42 | +0.138 | 95.2% |
| ny | 36 | +0.144 | 97.2% |
| london | 32 | +0.117 | 93.8% |
| london_ny | 25 | +0.149 | 100.0% |
| late | 16 | +0.126 | 100.0% |

## By Exit Reason

| Bucket | Trades | Avg R | Win% |
|--------|--------|-------|------|
| take_profit | 148 | +0.146 | 98.6% |
| backtest_end_mark | 2 | -0.050 | 0.0% |
| stop_loss | 1 | -1.020 | 0.0% |

## By Target Size (pips)

| Bucket | Trades | Avg R | Win% |
|--------|--------|-------|------|
| small_3-6p | 67 | +0.100 | 100.0% |
| medium_6-12p | 62 | +0.148 | 98.4% |
| large_12p+ | 20 | +0.230 | 90.0% |
| micro_<3p | 2 | -0.005 | 0.0% |

## By Stop Size (pips)

| Bucket | Trades | Avg R | Win% |
|--------|--------|-------|------|
| wide_45p+ | 97 | +0.102 | 97.9% |
| medium_30-45p | 54 | +0.195 | 94.4% |

## Council Acceptance — Narrative Class (expected pips)

| Micro class | Acceptances | Avg expected pips |
|-------------|---------------|-------------------|
| liquidity_sweep_snapback | 2743 | 3.87 |

## Council — Narrative Phase (expected pips)

| Phase | Acceptances | Avg expected pips |
|-------|---------------|-------------------|
| continuation | 1606 | 4.40 |
| liquidity_sweep | 853 | 3.35 |
| ranging | 284 | 2.43 |

## Recommendations

1. **Expand TP for high-confidence continuation** — council expects ~4 pips but journal shows most TPs <3 pips; align dynamic pip targets to 3-5 pips when forecast confidence >75 and trend score strong.
2. **Partial + runner exits** — lock micro profit at first target, trail runner toward narrative expected move to lift avg R without reducing trade count.
3. **Narrative exit tuning** — liquidity_sweep_snapback should exit faster; continuation/trend_pause_resume should allow runners.
4. **Spread-aware sizing** — reduce size only when net expected R <0.08 after spread; do not block setups broadly.
5. **R-aware boost** — slight size increase when narrative expected R >0.20.
