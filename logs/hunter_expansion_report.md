# Hunter Expansion Report

**Generated:** 2026-06-11T15:50:11.848472+00:00
**Current executed rate:** 0.50 trades/day (253 over 504 days)
**Target band:** 20–30 trades/day

| Blocker | Action | Rationale | Est. trades/day gain |
|---------|--------|-----------|---------------------:|
| `portfolio_heat_correlation` | **RELAX** | USD-major correlation cap stacks with max-open, serially blocking symbols. | +6.4 |
| `portfolio_max_open_trades` | **RELAX** | Max 5 open trades rejects valid signals when slots full. | +4.4 |
| `story_unclear` | **RELAX** | Story gate fires before forecast/opportunity; largest funnel choke. | +1.7 |
| `pa_reject` | **RELAX** | M1 strike required for funnel progression; blocks volume-only edges. | +0.5 |
| `portfolio_daily_loss_cap` | **KEEP** | Auditor risk budget — removing would inflate DD beyond Snapshot H guardrails. | +0.0 |
| `harvest_secondary_insufficient` | **RELAX** | Secondary harvest conditions still block story-driven council paths. | +0.0 |
| `marketplace_no_trade` | **RELAX** | Strategy marketplace returns no_trade despite story micro-edge. | +0.0 |
| `dynamic_pip_skip` | **RELAX** | Spread/ATR dynamic pip skip_trade on unclear-story branch. | +0.0 |
| `risk_lot_zero` | **KEEP** | Position sizing integrity — wide stops / min lot physics. | +0.0 |
| `defensive_mode` | **KEEP** | Drawdown defensive mode — auditor protection, not hunter expansion. | +0.0 |

## Combined estimate

If top 3 structural blockers relaxed (story gate, PA strike, portfolio caps): **~12.6 trades/day** → potential **~13.1 trades/day**.
