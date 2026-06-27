# Drawdown Throttle Undo Report

**Generated:** 2026-06-10

## Summary

Removed drawdown-aware trade starvation layers while preserving catastrophic protection (DD >25% hard block), emergency stop, and live-trading-disabled safety.

## Files Changed

| File | Change |
|------|--------|
| `controls/drawdown_risk.py` | Replaced multi-tier throttle with catastrophic-only guard |
| `intelligence/trend_maximiser.py` | Restored pullback/retest/add-on harvesting; removed DD gates |
| `intelligence/opportunity_allocator.py` | Removed DD-based confirmation tightening |
| `portfolio/correlation_allocator.py` | Soft mild scaling only; no DD>10% same-direction block |
| `portfolio/opportunity_score.py` | Removed DD penalties from stability score |
| `validation/drawdown_attribution.py` | Reports marked diagnostic-only |
| `tests/test_drawdown_risk.py` | Updated for catastrophic-only behavior |
| `tests/test_drawdown_risk_portfolio_scaling.py` | Cluster overflow no longer blocked |
| `tests/test_trend_maximiser.py` | Add-ons allowed at elevated DD |
| `tests/test_correlation_allocator.py` | Mild same-direction scale only |

## Throttles Removed

- DD 5–10% → 70% risk multiplier
- DD 10–15% → 40% risk multiplier and no add-ons
- DD >15% → A+ setups only
- 3-loss rule → 50% risk reduction
- 5-loss rule → 24h pause
- Hard correlation cluster cap (max 2 per cluster as block)
- Same-direction USD stacking block at DD >10%
- Trend maximiser: disable add-ons when DD >8%
- Trend maximiser: M15 tight trailing after DD ≥5%
- Trend maximiser: partial exit at 1R and ATR-contraction early partials
- Trend maximiser: critical DD A+ only block at 15%
- Opportunity allocator: DD-tier confirmation tightening (5/10/15%)
- OAS stability score: DD-based score penalties
- Correlation allocator: DD>10% same-direction 50% penalty
- Correlation allocator: aggressive cluster overflow (0.35^n) and same-dir 70% cut

## Protections Kept

| Protection | Behavior |
|------------|----------|
| DD >20% | Defensive advisory log only — no sizing cuts |
| DD >25% | Hard block on new entries |
| Emergency stop | Unchanged |
| Live trading disabled | `LIVE_TRADING=false`, `ENABLE_LIVE_TRADING=false`, `LIVE_TRADING_ENABLED=false` |
| Validation gate | Unchanged |
| Conservative validation default | Unchanged |
| Portfolio heat catastrophic | `halt_new_risk` at critical heat (>14%) — portfolio safety, not DD throttle |

## Drawdown Reports — Diagnostic Only

- `validation/drawdown_attribution.py` — analysis and reports only, no enforcement hooks
- `write_drawdown_reduction_validation_report` — comparison metrics only
- `write_risk_cluster_report` — recommendations replaced with diagnostic notes
- Loss streaks tracked in `DrawdownRiskController` for logging; `is_paused()` always returns False; `loss_streak_multiplier()` always 1.0

## Live Trading

Live trading remains **disabled**. Validation runs verify `.env` flags before execution.
