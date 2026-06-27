# Kraitos DNA — Story-Aware Participation Edition

**Permanent checkpoint:** Story-Aware Participation Doctrine aligned across TraderBrain, harvesting, entry, portfolio, risk, memory, and reporting.

## Core philosophy

Kraitos is an intelligent trader that **observes → understands → forecasts → participates → allocates**.

Understanding expands opportunity. It does not restrict it.

**Forbidden:** new filters, vetoes, consensus thresholds, indicator gates, trade caps, rank-and-drop.

## Systems aligned

| System | Doctrine |
|--------|----------|
| Market Story | Single coherent explanation; conflicting evidence interpreted, not rejected |
| Indicator Interpretation | Psychology only — never create/veto/reject trades |
| TraderBrain | Trade theses via Human Trader Reasoning; unlimited opportunity split |
| Story-Aware Harvest Engine | Active 1–5 pip micro harvest inside narrative |
| Entry Engine | Enter when bias/liquidity/spread/risk support; momentum explains urgency |
| Portfolio | Classify and allocate (MICRO_HARVEST … SCOUT); never reject |
| Risk Manager | Scale only; block on catastrophic safety / DD ≥ 50% / no coherent story |
| Memory | Remember stories, psychology, forecasts, outcomes — never suppress |
| Simultaneous execution | Unlimited same-timestamp entries subject to catastrophic protection |

## New modules

- `intelligence/story_aware_participation_doctrine.py` — DNA constants
- `intelligence/story_aware_harvest_engine.py` — story-first micro harvesting
- `intelligence/participation_tracker.py` — opportunities seen/taken/missed
- `intelligence/participation_reports.py` — doctrine and activity reports

## Entry logic change

Removed indefinite momentum waiting. Structure and momentum are **informational** confirmations included in the explanation — they do not return `wait`.

Hard gates remain: bias direction, liquidity, spread, risk sizing.

## Validation

Run: `python -m validation.run_single_validation`

Compare against Snapshot M in `logs/story_aware_participation_validation_report.md`.

Targets: higher trade frequency toward 20–30/day, WR > 65%, PF > 1.5, acceptable DD, positive Avg R.

**LIVE_TRADING remains disabled.**

## Reports generated

- `logs/story_aware_participation_doctrine_report.md`
- `logs/participation_activity_report.md`
- `logs/story_aware_participation_validation_report.md`
