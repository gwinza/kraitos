# Artificial Trade Limit Audit

**Generated:** unlimited-opportunity execution pass

Doctrine: classify + allocate — never rank-and-drop. NO_TRADE only for absent story, emergency stop, live safety, broker unavailable, DD ≥ 50%.

| Location | Cap / behavior | Action |
|----------|----------------|--------|
| `risk/risk_manager.py` `_scale_max_open_trades` | Slot crowding scale 75→10% | **KEEP** (scale only) |
| `risk/risk_manager.py` `_scale_daily_loss` | Daily loss budget scale | **KEEP** (scale only) |
| `risk/risk_manager.py` `_scale_symbol_exposure` | Symbol exposure scale | **KEEP** (scale only) |
| `risk/risk_manager.py` `_scale_correlated_exposure` | Correlation cluster scale | **KEEP** (scale only) |
| `risk/risk_manager.py` `catastrophic_gate` | DD ≥ 50% hard block | **KEEP** |
| `controls/drawdown_risk.py` `tier_for_drawdown` | DD ≥ 50% block_new_entries | **KEEP** |
| `controls/drawdown_risk.py` `loss_streak_multiplier` | Loss streak scale | **KEEP** (scale only) |
| `portfolio/portfolio_heat.py` | Heat bands scale to 10% | **KEEP** (scale only) |
| `portfolio/risk_budget.py` | Heat/daily/OAS scale | **KEEP** (scale only) |
| `portfolio/opportunity_score.py` `_tier_for_oas` | OAS defer/watchlist scale | **KEEP** (scale only) |
| `portfolio/capital_allocator.py` | MIN_ALLOCATED_RISK_PCT floor | **KEEP** |
| `portfolio/portfolio_construction.py` `_open_position_budget_multiplier` | Tier crowding scale | **KEEP** (scale only) |
| `portfolio/opportunity_allocator.py` `rank_all` | OAS ranking for size | **KEEP** (rank for allocation) |
| `paper_trading/virtual_account.py` `can_trade` | Was 5%/15% DD halt | **REMOVED** → catastrophic 50% only |
| `brains/trader_brain.py` defensive_mode reject | DD>15% hard NO_TRADE | **REMOVED** → scale |
| `intelligence/opportunity_allocator.py` defensive_mode | Zeroed harvest/scalp | **REMOVED** → scale paths |
| `core/risk_controller.py` strategy_quality | Symbol hard reject | **REMOVED** → micro scale |
| `brains/trader_brain.py` single candidate | One path per symbol | **REMOVED** → `evaluate_all` |
| `core/pipeline.py` `run` | Single `PipelineResult` | **REMOVED** → list of candidates |
| `core/signal_router.py` | Single signal | **REMOVED** → `route_all` |
| `core/engine.py` | One signal per symbol | **REMOVED** → all candidates routed |
| `backtesting/*_engine.py` | One signal per bar | **REMOVED** → all cycle signals |
| `config/settings.py` `max_open_trades` | Config reference limit | **KEEP** (scale reference only) |

## Remaining intentional gates (not artificial caps)

- Market story unclear / no opportunity type → NO_TRADE (no valid story)
- Emergency stop (`controls/emergency_stop.py`)
- Live trading safety (`controls/trading_gate.py`)
- Invalid trade request validation (bad SL geometry)
- Entry engine `wait` / momentum confirmation (story execution quality — not portfolio cap)
