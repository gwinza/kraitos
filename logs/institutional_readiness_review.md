# Institutional Readiness Review

**Generated:** 2026-06-12T11:51:59.488217+00:00
**Edition:** DNA v1.0 Thesis Doctrine (frozen audit)

## Doctrine stack assessment

| Doctrine | Maturity | Notes |
|----------|----------|-------|
| Story Doctrine | Strong | Evidence synthesis, story-clear path well wired |
| Participation Doctrine | Strong | Momentum informational; harvest probes active |
| Thesis Doctrine | Moderate | Complete contract; discrimination bypassed by story_clear |
| Allocation Firewall | Strong | Scales risk; catastrophic-only blocks |
| Exit Architecture | Moderate | TP1 partial works; runner journal/trail incomplete |

## Scores (1–10)

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Trade Selection | 7/10 | Thesis contract enforced; synthetic overfitting risk |
| Risk Management | 8/10 | DD gates, allocation layers, geometry validation |
| Participation Efficiency | 6/10 | High intraday count; calendar TPD metric misleading |
| Exit Management | 5/10 | TP1 partial OK; runner continuation not instrumented |
| Capital Preservation | 8/10 | 2.87% DD; 50% catastrophic gate |
| Transparency | 6/10 | Rich logs; journal gaps on runner leg; trust QUESTIONABLE |
| Adaptability | 7/10 | Multi-symbol, story evolution, council integration |
| Scalability | 4/10 | 1232 max open — not desk-realistic without caps |
| Institutional Readiness | 5/10 | Synthetic validation only; audit fixes needed |

## Major strengths

- Coherent doctrine stack: Story → Participation → Thesis → Allocate
- Pre-trade thesis contract with invalidation, targets, exit plan
- Allocation-based sizing replaces veto-heavy risk model
- Conservative backtest engine with closed-candle evaluation
- Extensive validation reporting pipeline

## Major weaknesses

- **Synthetic data only** — trust capped at QUESTIONABLE
- **5-day journal window** vs 2-year walk-forward label
- **Runner exit accounting gap** (2892 partials without runner close row)
- **story_clear bypass** eliminates thesis rejection in practice
- **Simultaneous exposure** unrealistic for institutional deployment

## Critical risks

1. Performance may not replicate on broker historical data
2. PF 8.5 on synthetic vs Snapshot M PF 1.39 — regime sensitivity unknown
3. LIVE_TRADING must remain disabled until real-data validation

## Non-critical improvements

- Fix TP1 hit rate denominator (positions not theses)
- Wire `record_runner_continuation()` in backtest
- Report trades/day on active days
- Persist thesis objects for offline discrimination audit

