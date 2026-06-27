# Brain Separation Audit

**Generated:** 2026-06-12T11:41:30.759519+00:00

## Decision ownership matrix

| Concern | Owner | Notes |
|---------|-------|-------|
| Market story | Trader Brain | `market_story_engine` |
| Story forecast | Trader Brain | `story_forecast_engine` |
| Opportunity scoring | Trader Brain | harvest, allocator, structure |
| Council observers | Trader Brain | observers-only, no vote gates |
| Indicator confirmation | Trader Brain | boost only, never veto |
| Entry candidates | Trader Brain | harvest + micro scalp + entry engine |
| Portfolio sizing | Trader Brain | size only, no discovery suppression |
| Conservative execution | Auditor Brain | next-bar, spread, slippage, SL-first |
| Closed-candle slicing | Auditor Brain | anti-lookahead in backtest |
| Validation gates | Auditor Brain | diagnostic reporting only |
| Trust verdict | Auditor Brain | red-team comparison |
| Strategy quality filters | Auditor Brain | NOT wired into trader pipeline |

## Enforcement

- `brains/trader_brain.py` — no imports from `execution_model`, `conservative_validation`
- `brains/auditor_brain.py` — no imports from story/harvest scoring engines
- `core/pipeline.py` — delegates discovery to `TraderBrain`
- `backtesting/conservative_backtest_engine.py` — auditor execution path only
- `validation/conservative_validation.py` — uses `AuditorBrain.verify_run`

## Violations found and fixed

- Removed `StrategyQualityGate` from trader discovery path (`pipeline.py`, `trader_brain.py`)
- Removed validation gate checks from `_run_entry_and_risk` trader path
- Moved conservative execution ownership to `AuditorBrain`
- `build_backtest_stack(apply_strategy_quality=False)` for trader signal generation
- Validation gates remain in `AuditorBrain.check_validation_gates` (diagnostic only)

## Snapshot comparison

| | Trades | WR | PF | DD | Avg R |
|---|--------|-----|-----|--------|-------|
| G (pre-split) | 802 | 96.3% | 2.56 | 2.50% | +0.11 |
| H (post-split) | 4298 | 82.0% | 8.53 | 2.87% | +0.90 |

**Trade count delta (H − G):** +3496

Trade count must NOT drop due to auditor leakage into trader.