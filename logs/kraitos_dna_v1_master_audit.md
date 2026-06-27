# Kraitos DNA v1.0 — Master Audit Report

**Generated:** 2026-06-12T11:51:59.489497+00:00
**Status:** Thesis Edition **FROZEN** — audit only, no doctrine changes

## 1. Executive Summary

Kraitos DNA v1.0 Thesis Doctrine shows **strong synthetic backtest metrics** (WR 82%, PF 8.5, DD 2.9%, Avg R +0.90R) that **recompute faithfully** from the journal. However, **data trust is QUESTIONABLE** (synthetic, 5-day active window, story_clear bypass). Thesis discrimination is **structurally permissive** though **runtime-consistent**. Primary participation bottleneck is **neutral bias + stop geometry**, not thesis quality.

**Deployment verdict: REQUIRES ADDITIONAL VALIDATION**

## 2. Validation of reported statistics

| Edition | Trades | WR | PF | DD | Avg R | T/day |
|---------|--------|-----|-----|--------|-------|-------|
| Snapshot M | 1035 | 81.6% | 1.39 | 1.95% | +0.17R | 2.05 |
| Story-Aware | 4290 | 82.6% | 2.91 | 5.87% | +0.28R | 8.51 |
| Thesis Doctrine | 4298 | 82.0% | 8.53 | 2.87% | +0.90R | 8.53 |

Thesis vs Story-Aware: +8 trades, −0.6pp WR, +5.6 PF, −3pp DD, +0.62R Avg R.

## 3. Is current performance genuine?

**Internally consistent — externally unproven.** Metrics match formulas. Synthetic trending window, story_clear on 100% of evals, and incomplete runner accounting mean reported edge is **not yet demonstrated on real market data**.

## 4. Is Thesis Doctrine performance trustworthy?

**Trustworthy as implementation audit; not trustworthy as live expectancy.** See `metric_integrity_audit.md` and `thesis_discrimination_audit.md`.

## 5. Is discrimination logic healthy?

**Logic is sound; calibration is permissive.** 0% rejection is artefact of story_clear override + synthetic clarity, not proof of selective edge.

## 6. Participation bottlenecks

- 26% entry-stage rejection (neutral bias / geometry)
- 0% thesis rejection
- Trades/day metric understates intraday intensity (858 opens/day active)

## 7. Regime strengths and weaknesses

- Majors excel; JPY/XAU quarantined
- 2022 ranging untested; single 5-day 2023 window

## 8. Institutional readiness verdict

Score **5/10** — see `institutional_readiness_review.md`.

## 9. Recommended next actions (by impact)

1. **Run validation on imported/broker historical CSV** (unblocks trust)
2. **Fix runner journal + continuation metrics** (audit integrity)
3. **Re-report trades/day on active trading days**
4. **Persist thesis snapshots** for offline discrimination QA
5. **Cross-regime replay** 2022 ranging + 2024 volatile years
6. **Extended paper trading** on demo account with live feeds

## 10. Conclusion

### REQUIRES ADDITIONAL VALIDATION

Do **not** proceed to controlled live pilot until broker/imported data confirms WR > 65%, PF > 1.5, DD < 50%, and positive Avg R outside synthetic story-clear conditions.

## Audit artifacts

- `logs/metric_integrity_audit.md`
- `logs/thesis_discrimination_audit.md`
- `logs/participation_funnel_audit.md`
- `logs/cross_regime_validation.md`
- `logs/institutional_readiness_review.md`

