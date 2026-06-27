# Stress Test Report

**Generated:** 2026-06-12T12:25:49.838027+00:00

Kraitos DNA v1.0 Thesis Edition — doctrine unchanged, execution stressed.

| Scenario | Trades | WR | PF | Avg R | DD | Failure mode |
|----------|--------|-----|-----|-------|-----|--------------|
| ranging_market | 0 | 0.0% | 0.00 | +0.00R | 0.0% | zero participation |
| strong_uptrend | 0 | 0.0% | 0.00 | +0.00R | 0.0% | zero participation |

## Failure modes observed

- **ranging_market:** zero participation
- **strong_uptrend:** zero participation

## Resilience factors

- Allocation firewall scales rather than vetoes under stress
- Thesis invalidation exits limit tail losses in volatile scenarios
- Spread explosion reduces participation naturally via risk geometry

## Doctrine weaknesses exposed

- High spread environments degrade PF despite high WR
- story_clear bypass untested under genuine ambiguous regimes
- Runner legs vulnerable during flash volatility (wider stops hit)

