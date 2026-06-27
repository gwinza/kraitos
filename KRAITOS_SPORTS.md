# Kraitos Sports

Elite AI Sports Intelligence — **Kraitos does not pick winners. Kraitos finds edges.**

## Golden Rule

**Data → Probability → Value → Risk → Decision**

If the edge is unclear, Kraitos preserves capital and recommends no action.

## Architecture

```
sports/                    Domain models, fixtures, demo data
  engines/                 17 intelligence engines
brains/sports_brain.py     Orchestrator (mirrors TraderBrain pattern)
api/main.py                FastAPI for mobile client
mobile/kraitos-sports/     Expo React Native app (APK)
```

## Engines

| # | Engine | Purpose |
|---|--------|---------|
| 1 | Match Scanner | Continuous upcoming event scan |
| 2 | Arbitrage Engine | Cross-bookmaker surebets |
| 3 | Value Betting Engine | EV vs fair probability |
| 4 | Team Strength Engine | Squad quality, injuries, depth |
| 5 | Coach Intelligence | Tactical overperformance |
| 6 | Form Analysis | Momentum, false streaks |
| 7 | Advanced xG | Luck, overrated/underrated |
| 8 | Market Intelligence | Odds movement, sharp money |
| 9 | Deep Match Intelligence | Motivation, fatigue, rivalry |
| 10 | Monte Carlo | 10,000 simulation distributions |
| 11 | Bayesian Live | In-play probability updates |
| 12 | RL Harvester | Learn from outcomes |
| 13 | Multi-Agent Council | 8 specialist agents |
| 14 | Red Team | Internal critic |
| 15 | Portfolio Intelligence | Exposure, bankroll limits |
| 16 | Explainability | Transparent reasoning |
| 17 | Opportunity Ranker | Edge score, grade, sort |
| 18 | Lower League Predictor | European 3rd/4th tier outcomes + reasoning |

## Lower League Predictions

European third and fourth tier coverage includes:

- England: EFL League One/Two, National League
- Germany: Regionalliga, 3. Liga
- Italy: Serie C / Serie D
- Spain: Segunda / Tercera Federación
- France: National / National 2
- Netherlands, Portugal, Scotland, Poland, and more

```powershell
python sports_main.py --lower-leagues
python sports_main.py --match-id eng-l2-001
curl http://localhost:8000/analyze/lower-leagues
```

Every lower-league match includes:

- **prediction** — model outcome (Home/Draw/Away)
- **prediction_reasoning** — narrative summary
- **prediction_detail.reasons** — factor-by-factor explanation (xG, form, travel, market mispricing)
- **model vs market divergence** — where Kraitos disagrees with bookmakers

## Quick Start

### CLI

```powershell
pip install -r requirements.txt -r requirements-sports.txt
python sports_main.py
python sports_main.py --match-id bund-001
python sports_main.py --json
```

### API Server

```powershell
python run_sports_api.py
# GET http://localhost:8000/analyze
# GET http://localhost:8000/analyze/epl-001
```

### Mobile App

See `mobile/kraitos-sports/BUILD.md` for APK build instructions.

The app works **offline in demo mode** when the API is unavailable.

### Tests

```powershell
pytest tests/test_sports_brain.py -v
```

## Human-in-the-Loop

Kraitos never places bets automatically. It provides intelligence; the human provides execution.

## Supported Sports (demo data)

Soccer, Basketball, Tennis, Cricket, American Football — extend via `sports/demo_data.py` or live odds APIs.
