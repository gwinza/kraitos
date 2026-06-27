# Kraitos Next Steps

**Audit date:** 2026-06-08  
Prioritized operational actions after system audit. No new features implied — readiness and safety first.

---

## Immediate (before any live consideration)

1. **Confirm emergency stop is clear** before scheduled runs:
   ```powershell
   # Check logs/command_center_state.json → emergency_stop.active should be false
   # Or: main.py --clear-emergency --no-execute --no-dashboard
   ```

2. **Keep all live flags false** in `.env` and `config/config.yaml` until validation passes:
   - `LIVE_TRADING=false`
   - `ENABLE_LIVE_TRADING=false`
   - `LIVE_TRADING_ENABLED=false`
   - `trading.live_enabled: false`
   - `pipeline.execution_mode: simulation`

3. **Run routine health check:**
   ```powershell
   & $PY -m pytest tests/ -q
   & $PY main.py --no-execute --symbols EURUSD
   ```

---

## Validation path to `LIVE_READY`

1. Run backtest collection until ≥ 100 closed trades with acceptable metrics.
2. Run forward paper testing until ≥ 30 closed paper trades.
3. Write results to `logs/validation_metrics.json`:
   ```json
   {
     "backtest": { "total_trades": 100, "win_rate": 0.55, "profit_factor": 1.5, ... },
     "paper": { "total_trades": 30, "win_rate": 0.55, "profit_factor": 1.4, ... }
   }
   ```
4. Generate readiness report via `LiveReadinessReport` and confirm `LIVE_READY`.
5. Only then review broker guard settings — still requires explicit operator sign-off.

---

## Paper trading operations

1. Use `main.py --execute` for simulated fills (never live with current config).
2. Monitor `logs/paper_trades.csv` and `logs/trade_journal.csv` after each session.
3. Use command center controls as needed:
   - `main.py --pause` / `--resume`
   - `main.py --emergency-stop` / `--clear-emergency`

---

## Monitoring

| What to watch | Where |
|---------------|-------|
| Pipeline signals | `logs/pipeline_signals.json` |
| Paper trades | `logs/paper_trades.csv` |
| Validation journal | `logs/trade_journal.csv` |
| System errors | `logs/json/errors.jsonl` |
| Command center state | `logs/command_center_state.json` |
| Application log | `logs/kraitos.log` |

---

## Before enabling live (future — not recommended now)

- [ ] Validation status = `LIVE_READY`
- [ ] All broker confirmation guards pass (`BROKER_NAME`, `BROKER_ACCOUNT_ID`, risk ≤ 1%, daily limit ≤ 5%)
- [ ] `ENABLE_LIVE_TRADING=true` AND `LIVE_TRADING=true` set deliberately
- [ ] `trading.live_enabled: true` and `pipeline.execution_mode: live` in config
- [ ] Emergency stop tested and cleared
- [ ] Final paper session under live-market conditions

**Current audit recommendation:** Remain in **paper / simulation mode**.
