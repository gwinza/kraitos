# Kraitos Test Results

**Run date:** 2026-06-08  
**Command:** `python -m pytest tests/ -q`  
**Result:** **252 passed** in ~3s  
**Failures:** 0  
**Errors:** 0

---

## Full suite

```
252 passed in 2.97s
```

---

## Audit-focused test groups

| Suite | Tests | Result |
|-------|-------|--------|
| `tests/test_main.py` | 5 | PASS |
| `tests/test_full_pipeline.py` | — | PASS |
| `tests/test_backtest_engine.py` | 2 | PASS |
| `tests/test_paper_trading.py` | 6 | PASS |
| `tests/test_command_center.py` | 11 | PASS |
| `tests/test_strategy_validator.py` | 21 | PASS |
| `tests/test_broker_factory.py` | 22 | PASS |
| `tests/test_config.py` | — | PASS |
| All other modules | — | PASS |

---

## Manual smoke tests (audit)

| Test | Command / action | Result |
|------|------------------|--------|
| Main entry | `main.py --no-execute --no-dashboard --symbols EURUSD` | Exit 0 |
| Emergency stop | `main.py --emergency-stop --execute` | Execution blocked, exit 0 |
| Safety flags | `BrokerSettings.from_env()` | `live_trading=False`, `enable_live_trading=False` |
| Trading gate | `TradingGate.live_allowed()` | `(False, 'Live trading disabled by configuration')` |
| Paper execute | `TradeExecutor.execute()` on TRADE signal | `executed=True`, no broker order |
| Backtest E2E | `tests/test_backtest_engine.py` | Pipeline replay + journal write |

---

## Coverage by concern

| Concern | Tests exercising it |
|---------|---------------------|
| Config validation | `test_config.py`, `test_main.py` |
| Pipeline integration | `test_full_pipeline.py` |
| Paper simulation | `test_paper_trading.py`, `test_paper_trader.py` |
| Live trading blocked | `test_broker_factory.py`, `test_mt5_connector.py`, `test_execute_trade.py` |
| Emergency stop | `test_command_center.py::test_emergency_stop_blocks_trading` |
| Validation gate | `test_strategy_validator.py`, `test_command_center.py` |
| Command center | `test_command_center.py`, `test_main.py` |
| Entry engine logging | `test_entry_engine.py`, `test_event_logger.py` |

---

## Notes

- Tests run **offline** by default (`pytestmark = pytest.mark.offline` on most suites).
- MT5-dependent behaviour is mocked in unit tests; `main.py` smoke test uses a live MT5 terminal when available.
- No flaky failures observed across two consecutive full-suite runs during this audit.
