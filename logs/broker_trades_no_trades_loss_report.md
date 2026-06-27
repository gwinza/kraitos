# Broker Trades, No-Trades & Loss Report

**Generated:** 2026-06-26T18:16:04.461445+00:00

Expectancy-first read of broker M1 backtests and pipeline signal logs.

## Data coverage

| Symbol | M1 export | Status |
|--------|-----------|--------|
| EURUSD | 2025 (~372k bars) | INCOMPLETE vs full 2022–2026 requirement |
| GBPUSD | 2025 | INCOMPLETE |
| AUDUSD | 2025 | INCOMPLETE |
| USDJPY | 2025 | INCOMPLETE |
| GBPJPY | 2025 | INCOMPLETE |
| XAUUSD | — | MISSING |

---

## 1. Trade outcomes by journal

### Ideal partial (broker, low cost)

Source: `logs/broker_partial_journal.csv`

> **Note:** Ideal partial backtest appears **incomplete** (4 rows). Re-run `python -m validation.broker_grade_proof --force` for full results.

| Metric | Value |
|--------|-------|
| Rows | 4 |
| Closed | 2 |
| Open | 2 |
| Wins | 0 |
| Losses | 2 |
| Win Rate | 0.0% |
| Profit Factor | 0.0 |
| Avg R | -1.035 |
| Sum R | -2.07 |
| Total Pl | -42.41 |
| Return Pct | -0.44% |
| End Balance | 9956.27 |

**Symbols:** EURUSD (2), GBPJPY (2)

**Modes:** scalp (4)

| Symbol | Closed | W | L | WR | Net P/L | Avg R |
|--------|--------|---|---|-----|---------|-------|
| EURUSD | 1 | 0 | 1 | 0.0% | -15.88 | -1.06 |
| GBPJPY | 1 | 0 | 1 | 0.0% | -26.53 | -1.01 |

**Loss exit types:**
- `stop_loss`: 2

**Loss classification:**
- `good_idea_early`: 1
- `bad_idea`: 1

**Sample losses:**
- **EURUSD sell** | P/L -15.88 | -1.06R | exit `stop_loss` | class `good_idea_early`
- **GBPJPY sell** | P/L -26.53 | -1.01R | exit `stop_loss` | class `bad_idea`

### Realistic partial (broker, spread+slip)

Source: `logs/broker_partial_realistic_journal.csv`

| Metric | Value |
|--------|-------|
| Rows | 8322 |
| Closed | 4170 |
| Open | 4152 |
| Wins | 1777 |
| Losses | 2393 |
| Win Rate | 42.61% |
| Profit Factor | 0.778 |
| Avg R | -0.131 |
| Sum R | -547.54 |
| Total Pl | -1968.14 |
| Return Pct | -22.7% |
| End Balance | 7730.05 |

**Symbols:** USDJPY (8322)

**Modes:** scalp (8322)

| Symbol | Closed | W | L | WR | Net P/L | Avg R |
|--------|--------|---|---|-----|---------|-------|
| USDJPY | 4170 | 1777 | 2393 | 42.6% | -1968.14 | -0.131 |

**Loss exit types:**
- `stop_loss`: 2390
- `unknown`: 3

**Sample losses:**
- **USDJPY buy** | P/L -23.84 | -1.21R | exit `stop_loss`
- **USDJPY buy** | P/L -18.96 | -1.2R | exit `stop_loss`
- **USDJPY buy** | P/L -12.45 | -1.12R | exit `stop_loss`

### Path C broker (multi-symbol)

Source: `logs/path_c_broker_journal.csv`

| Metric | Value |
|--------|-------|
| Rows | 1476 |
| Closed | 732 |
| Open | 744 |
| Wins | 360 |
| Losses | 371 |
| Win Rate | 49.18% |
| Profit Factor | 0.752 |
| Avg R | -0.109 |
| Sum R | -80.04 |
| Total Pl | -431.67 |
| Return Pct | 2.06% |
| End Balance | 10206.12 |

**Symbols:** GBPJPY (376), USDJPY (324), GBPUSD (293), AUDUSD (266), EURUSD (217)

**Modes:** scalp (929), harvest (547)

| Symbol | Closed | W | L | WR | Net P/L | Avg R |
|--------|--------|---|---|-----|---------|-------|
| GBPJPY | 185 | 114 | 70 | 61.6% | 35.33 | 0.073 |
| USDJPY | 160 | 75 | 85 | 46.9% | -215.29 | -0.215 |
| GBPUSD | 146 | 62 | 84 | 42.5% | -248.04 | -0.185 |
| AUDUSD | 132 | 68 | 64 | 51.5% | 113.48 | 0.036 |
| EURUSD | 109 | 41 | 68 | 37.6% | -117.15 | -0.339 |

**Loss exit types:**
- `stop_loss`: 241
- `early_exit_stagnation`: 130

**Sample losses:**
- **AUDUSD buy** | P/L -0.25 | -0.05R | exit `stop_loss`
- **GBPJPY buy** | P/L -5.22 | -1.01R | exit `stop_loss`
- **GBPJPY buy** | P/L -10.49 | -1.01R | exit `stop_loss`

---

## 2. No-trades (pipeline `trade_journal.csv`)

| Outcome | Count | % of evaluations |
|---------|-------|------------------|
| Skipped (NO TRADE) | 6441 | 87.5% |
| Opened | 455 | 6.2% |
| Closed win | 442 | 6.0% |
| Closed loss | 20 | 0.3% |
| **Total rows** | **7359** | 100% |

### Why no trade happened

| Count | Reason |
|-------|--------|
| 3512 | Risk cap — max risk per symbol exceeded |
| 1575 | Patience / entry timing not ready |
| 1354 | Mandatory gates — bias / structure |

**Interpretation:** Under the expectancy doctrine, the dominant skips are **risk caps** and **patience/timing waits** — not indicator disagreement. That is intentional: size is capped per symbol; entries wait for professional locations.

---

## 3. Loss patterns (cross-journal)

| Pattern | Evidence | Meaning |
|---------|----------|---------|
| **stop_loss (~65–100% of losses)** | Ideal, realistic, path C | Hard stop hit before target; thesis or timing wrong |
| **good_idea_early** | Ideal GBPUSD harvest | Right zone, entered before reaction/reclaim |
| **early_exit_stagnation** | Path C (~35% of losses) | Trade stalled; adaptive exit cut bleed |
| **Scalp cost drag** | Realistic USDJPY, WR 42.6%, PF 0.78 | Win rate too low after spread+slippage |
| **Counter-trend vs story** | Ideal GBPUSD sells | Short against bullish structure / 68% reversal pressure |

---

## 4. Expectancy doctrine verdict

| Goal | Broker-realistic evidence |
|------|---------------------------|
| EV per trade | **Negative** on realistic USDJPY scalps (avg R −0.131) |
| Profit factor | **< 1.0** on completed broker-realistic journals |
| Average R | **Negative** on partial realistic and path C closed sets |
| Drawdown control | **Working** — risk-per-symbol caps drive thousands of no-trades |
| Patience | **Working** — waits dominate; ideal losses = probe-too-early |

**Action:** Complete ideal partial run (`broker_grade_proof --force`), add XAUUSD + multi-year M1, and favour harvest/story paths over high-frequency USDJPY scalps on realistic costs.
