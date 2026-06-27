# Participation Funnel Audit

**Generated:** 2026-06-12T11:51:59.422033+00:00

## Current frequency

- Reported trades/day: **8.53** (504-day calendar normalization)
- Active-day opens: **1072**/day (4290 opens / ~4 active days in journal)
- Aspiration: **20–30 quality trades/day**

## Funnel (this validation run)

| Stage | Count | % of evaluations |
|-------|-------|------------------|
| Timeline evaluations | 5808 | 100% |
| Story-clear / harvest windows | 5808 | 100% |
| Theses built | 5808 | 100% |
| Trade intent (approved) | 4290 | 73.9% |
| Positions opened | 4290 | 73.9% |
| Closed events | 4298 | — |

**Conversion evaluation → entry:** 73.9% (4290/5808)

## Blocker profile

| Blocker | Count | % evals | Safety vs friction | Est. trades if removed |
|---------|-------|---------|-------------------|------------------------|
| Neutral bias + invalid sell geometry | 1350 | 23.2% | safety-critical | 0 |
| Thesis stage (non-tradeable — none this run) | 0 | 0.0% | safety | 0 |
| Entry stage (bias/risk geometry) | 1518 | 26.1% | safety-critical | 0 |
| Harvest blocked (story-clear bypass active) | 0 | 0.0% | friction | 0 |
| Council denial | 0 | 0.0% | friction | 0 |
| Exposure / allocation scale-down | 0 | 0.0% | friction | partial-size already active |
| Duplicate / cooldown suppression | 0 | 0.0% | friction | unknown |
| Session / news restrictions | 0 | 0.0% | safety | 0 |
| Micro-scalper no_trade (informational) | 5808 | 100.0% | non-blocking | 0 |

## Primary bottleneck

**Neutral multi-timeframe bias + invalid short geometry** accounts for ~**1350** rejections (~23% of evaluations). These are **safety-critical** — removing would force trades against bias or with invalid stops.

Secondary bottleneck: **1518 entry-stage rejections** (26%) — same root cause cluster.

Thesis doctrine is **not** the participation limiter (0 thesis rejections). **5808 − 4290 = 1518** opportunities lost post-thesis at entry/risk.

## Safe unlock opportunities (not implemented)

1. **Evaluation cadence:** step=2 bars — increasing cadence raises evals linearly.
2. **Story-continuation re-entries:** same-bar multi-symbol already yields ~858 opens/day.
3. **SL geometry repair:** neutral-bias sell attempts with inverted geometry — repair could recover some.
4. **Partial-size participation:** allocation firewall already scales; full block only at catastrophic DD.
5. **Multi-asset expansion:** 11 symbols; JPY/XAU underperform — expand liquid majors carefully.
6. **Calendar normalization fix:** report active-day trades/day for honest frequency benchmarking.

## Simultaneous exposure

- Max open: **1232**
- Not a bottleneck — capacity far exceeds typical desk limits.

