# Kraitos Known Issues

**Audit date:** 2026-06-08

Issues listed here are observed limitations or gaps — not blocking paper/simulation operation.

---

## Safety / configuration

### 1. Validation metrics file not auto-populated

**Severity:** Low (by design until forward testing completes)  
**Detail:** `logs/validation_metrics.json` does not exist. The command center reports `NEEDS_MORE_DATA` and live trading remains blocked.  
**Impact:** Cannot reach `LIVE_READY` until backtest/paper metrics are written to that file or collected via `ForwardTestTracker`.  
**Workaround:** Populate `validation_metrics.json` manually or via a future validation run script.

### 2. `.env` was missing explicit broker live flags

**Severity:** Low — **fixed during audit**  
**Detail:** `.env` only had `LIVE_TRADING_ENABLED=false`. Added `LIVE_TRADING=false` and `ENABLE_LIVE_TRADING=false` for parity with `.env.example`. Code defaults were already safe.

### 3. Emergency stop persisted after audit smoke test

**Severity:** Low — **fixed during audit**  
**Detail:** Running `main.py --emergency-stop` during audit left `logs/command_center_state.json` with `active: true`. Cleared to `active: false` so normal runs are not blocked.

---

## Runtime / operations

### 4. `main.py` requires MT5 for live pipeline runs

**Severity:** Medium (environmental)  
**Detail:** Integrated pipeline connects to MetaTrader 5 for quotes and candles. Offline tests mock MT5; production `main.py` fails if terminal is unavailable.  
**Impact:** `MT5ConnectionError` → exit 1, error logged to `logs/json/errors.jsonl`.

### 5. PowerShell stderr noise from loguru

**Severity:** Cosmetic  
**Detail:** Loguru colour output on stderr can surface as `NativeCommandError` in PowerShell even when exit code is 0.  
**Impact:** None on functionality.

### 6. Legacy orchestrator separate from `main.py`

**Severity:** Low  
**Detail:** `core/orchestrator.py` (14-step loop with `--cycles`) is not the default `main.py` path. Long-running orchestrator previously crashed on rejected-trade logging (`TypeError: 'list' object is not a mapping`) — fixed in `logs/event_logger.py`.  
**Impact:** Use `main.py` for integrated pipeline; orchestrator loop is a separate entry pattern.

---

## Data / logging

### 7. `pipeline_signals.json` may contain stale test data

**Severity:** Cosmetic  
**Detail:** File can retain mock `reason: "test"` rows from unit tests if written to project `logs/`.  
**Impact:** Command center may show outdated signal until next real pipeline run.

### 8. `trade_journal.csv` records skipped signals during backtest

**Severity:** Informational  
**Detail:** Backtest journal rows with `result=skipped` are expected when strategy gates fail on synthetic data.  
**Impact:** Not an error — journal is working as designed.

### 9. `strategies.enabled` config unused

**Severity:** Low  
**Detail:** `config.yaml` `strategies.enabled: []` is not wired to pipeline gating.  
**Impact:** All configured symbols are evaluated regardless of this list.

---

## Not implemented (intentionally deferred)

- Real Deriv / IQ Option API integration (stubs only)
- Automatic population of validation metrics from backtest/paper runs
- Dedicated CLI command for backtest-only runs (engine exists; no `main.py` subcommand)
- Streamlit dashboard auto-start from `main.py` (CLI command center used instead)
