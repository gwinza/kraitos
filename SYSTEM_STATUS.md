# Kraitos System Status

**Audit date:** 2026-06-08  
**Project path:** `C:\Users\Asus\kraitos`  
**Python:** `C:\Program Files\LibreOffice\program\python.exe` (3.12.12)

## Overall verdict: OPERATIONAL (paper/simulation mode)

Kraitos starts cleanly, all automated tests pass, and safety gates are active. Live trading remains disabled by default.

---

## Audit checklist

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `main.py` starts without errors | **PASS** | Exit code 0 with `--no-execute --no-dashboard --symbols EURUSD` |
| 2 | All tests pass | **PASS** | 252 / 252 pytest tests |
| 3 | Backtesting runs end-to-end | **PASS** | `tests/test_backtest_engine.py` — pipeline replay, journal write, performance report |
| 4 | Paper trading without live execution | **PASS** | `TradeExecutor` simulates only; `execution_mode: simulation` |
| 5 | `LIVE_TRADING` false by default | **PASS** | `config.yaml`, `.env`, `BrokerSettings` defaults |
| 6 | Emergency stop blocks trades | **PASS** | `controls/emergency_stop.py` + `tests/test_command_center.py` |
| 7 | Validation gate blocks live unless `LIVE_READY` | **PASS** | `controls/trading_gate.py` + `tests/test_strategy_validator.py` |
| 8 | Logs and `trade_journal.csv` written | **PASS** | Files present with valid CSV headers and rows |

---

## Runtime configuration

| Setting | Value |
|---------|-------|
| Pipeline mode | `simulation` |
| `trading.live_enabled` | `false` |
| `trading.paper_enabled` | `true` |
| `pipeline.execute_trades` | `false` |
| `LIVE_TRADING` (env) | `false` |
| `ENABLE_LIVE_TRADING` (env) | `false` |
| `LIVE_TRADING_ENABLED` (env) | `false` |
| Command center | Launched by default from `main.py` |
| Emergency stop | **Inactive** (cleared after audit) |
| Manual override | **Running** (not paused) |
| Validation status | `NEEDS_MORE_DATA` (no `logs/validation_metrics.json`) |

---

## Active subsystems

| Subsystem | Status | Notes |
|-----------|--------|-------|
| Integrated pipeline (`main.py`) | OK | MT5 connect → analyse → signal → optional paper execute |
| Command center | OK | CLI dashboard, health monitor, error reporter |
| Broker layer | OK | MT5/Deriv/IQ Option adapters; live blocked by default |
| Backtest engine | OK | Replays candles through same pipeline |
| Paper trading | OK | `PaperTrader` + `VirtualAccount` + journal |
| Validation gate | OK | Requires `LIVE_READY` + broker flags for live |
| Legacy orchestrator | Present | Separate 14-step loop; not default `main.py` entry |

---

## Log artifacts verified

| File | Status |
|------|--------|
| `logs/kraitos.log` | Present |
| `logs/trade_journal.csv` | Present — 17-column header, skipped/trade rows |
| `logs/paper_trades.csv` | Present — open/close events |
| `logs/pipeline_signals.json` | Present — latest pipeline output |
| `logs/json/*.jsonl` | Present — trade_decisions, system_events, errors, etc. |
| `logs/csv/*.csv` | Present — mirrored structured logs |
| `logs/command_center_state.json` | Present — emergency/override state |

---

## How to run

```powershell
cd C:\Users\Asus\kraitos
$PY = "C:\Program Files\LibreOffice\program\python.exe"

& $PY main.py --no-execute                    # command center + pipeline
& $PY main.py --no-execute --symbols EURUSD   # single symbol
& $PY -m pytest tests/ -q                     # full test suite
```
