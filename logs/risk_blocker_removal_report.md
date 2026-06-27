# Risk Blocker Removal Report

**Generated:** 2026-06-12T11:41:30.753416+00:00

## Before (binary reject)

| Blocker | Old behavior |
|---------|--------------|
| Max open trades | Hard reject at cap |
| Daily loss budget | Hard reject at limit |
| Symbol exposure | Hard reject over limit |
| Correlated exposure | Hard reject over limit |
| Portfolio heat | Suppress at catastrophic |
| Daily loss 100% | Catastrophic suppress |
| Drawdown 25% | Hard block new entries |
| MIN combined score | Hard floor reject |

## After (scale only)

| Blocker | New behavior |
|---------|--------------|
| Max open trades | Slot crowding scale 75→10% |
| Daily loss budget | Scale 100→25% |
| Symbol exposure | Soft scale 75→25% |
| Correlated exposure | Position cluster scale 100→20% |
| Portfolio heat | Scale to 10% floor |
| Daily loss 100% | Scale to 25% |
| Drawdown 40% | Micro-allocation 10% |
| Drawdown 50% | Only hard block |
| OAS / combined | Micro-allocation floor 0.01% |

## Unchanged (catastrophic only)

- Emergency stop
- Live trading safety
- Broker unavailable
- No valid TraderBrain story
- DD ≥ 50%
