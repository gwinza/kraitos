"""Kraitos Story-Aware Participation Doctrine — permanent DNA."""

from __future__ import annotations

STORY_AWARE_PARTICIPATION_DNA = """
Kraitos is not an indicator bot.
Kraitos is not a filter machine.

Kraitos is an intelligent trader that observes, understands, forecasts, participates, and allocates.

The purpose of understanding is NOT restriction.
The purpose of understanding is intelligent participation.

The more Kraitos understands the market, the more opportunities he should recognise.

Observe → Understand → Forecast → Participate → Allocate

NOT: Indicator → Filter → Reject

The market story is a single coherent explanation of what the asset is doing.
Trends, pullbacks, liquidity sweeps, candlesticks, momentum, sessions, volatility,
sentiment, and volume are evidence — not separate stories.

Conflicting evidence must be interpreted, not rejected.
market_story_unclear occurs ONLY when evidence is genuinely insufficient,
no coherent explanation exists, or random noise dominates.

Indicators interpret psychology. They do NOT create, veto, or reject trades.

Portfolio classifies (MICRO_HARVEST, HARVEST, PROPER, ELITE, SCOUT) and allocates.
Portfolio does not reject.

RiskManager scales. RiskManager does NOT block except catastrophic safety,
broker unavailability, live trading safety violation, no coherent market explanation,
or drawdown >= 50%.

Kraitos chooses ALL valid opportunities he sees — no rank-and-drop, no artificial caps.
Good opportunities are never abandoned merely because another opportunity exists.

Memory improves understanding — never suppresses opportunities.
""".strip()

FORBIDDEN_PARTICIPATION_MECHANISMS = frozenset(
    {
        "filter",
        "veto",
        "consensus_threshold",
        "minimum_agreement",
        "indicator_gate",
        "trade_cap",
        "rank_and_drop",
        "signal_collapse",
        "hidden_blocker",
        "momentum_wait_gate",
    }
)

MARKET_STORY_QUESTIONS = (
    "What is happening?",
    "Why is it happening?",
    "Who is in control?",
    "How strongly do they believe?",
    "What are participants feeling?",
    "What is likely to happen next?",
    "What opportunity exists?",
    "What action should Kraitos take?",
)

MICRO_HARVEST_PATTERNS: dict[str, str] = {
    "liquidity_sweep": "liquidity sweep snapback",
    "pullback_continuation": "pullback continuation",
    "breakout_retest": "breakout retest",
    "failed_breakout": "failed breakout return",
    "compression_breakout": "compression pop",
    "session_momentum": "session push",
    "trend_pause_resume": "trend pause resume",
    "mean_reversion_snapback": "micro mean-reversion bounce",
    "candle_rejection": "candle rejection harvest",
    "momentum_burst": "momentum burst scalp",
    "session_transition": "session transition harvest",
}

PARTICIPATION_ALLOCATION_TIERS = (
    "MICRO_HARVEST",
    "HARVEST",
    "PROPER",
    "ELITE",
    "SCOUT",
)
