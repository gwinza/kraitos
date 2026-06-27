# Kraitos DNA — Thesis Doctrine Edition

**Permanent checkpoint:** Kraitos upgrades from signal hunter to thesis-driven trade manager.

## Core doctrine

Every trade defines:

1. **Market story** — why the opportunity exists
2. **Directional thesis** — bullish, bearish, or neutral
3. **Invalidation level** — exact price where the idea is wrong
4. **Risk amount** — fixed before entry
5. **Target liquidity** — where price is likely trying to go
6. **Entry trigger** — objective reason to enter now
7. **Exit plan** — actions if right and if wrong

## Flow

```
Observe → Understand → Thesis → Participate → Manage → Allocate
```

Momentum and indicators remain **informational**. They do not veto valid story-clear theses.

## Reject only when

- Stop geometry is invalid
- Spread destroys reward/risk (unless story-clear)
- Target liquidity genuinely unclear (unless story-clear)
- Market story genuinely insufficient/incoherent/noise

## Split-exit management

- **TP1** at 1.0–1.5R — close 50% partial
- Move runner to break-even
- Trail runner on M1/M5 structure or 10/20 EMA
- Full exit on thesis invalidation

## Module

- `intelligence/kraitos_thesis_doctrine.py` — `KraitosThesisEngine`, `TradeThesis`, `ThesisExitManager`

## Reports

- `logs/thesis_doctrine_report.md`
- `logs/thesis_doctrine_validation_report.md`
