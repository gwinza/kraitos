"""Competing World Model templates — every explanation is a candidate until eliminated."""

from __future__ import annotations

from reality.reality_efficiency import MAX_WORLD_MODELS
from reality.reality_models import WorldModel

# Relevance keywords for fast pre-filter before full division investigation
_MODEL_SIGNATURE_HINTS: dict[str, tuple[str, ...]] = {
    "institutional_accumulation": ("accumulation", "reclaim", "support", "institutional"),
    "bull_trap": ("trap", "false", "reject", "failure"),
    "short_covering": ("cover", "squeeze", "short"),
    "liquidity_sweep_low": ("sweep", "liquidity", "reclaim", "low"),
    "news_reaction_bull": ("news", "reaction", "spike"),
    "momentum_continuation": ("momentum", "continuation", "trend"),
    "distribution": ("distribution", "supply", "exhaustion"),
    "algorithmic_repricing": ("algo", "drift", "repric"),
    "institutional_distribution": ("distribution", "breakdown", "supply"),
    "bear_trap": ("trap", "reclaim", "false"),
    "long_liquidation": ("liquidation", "long", "flush"),
    "liquidity_sweep_high": ("sweep", "liquidity", "high", "reject"),
    "momentum_breakdown": ("breakdown", "momentum", "bearish"),
    "range_equilibrium": ("range", "equilibrium", "mean"),
    "compression_before_expansion": ("compression", "coil", "squeeze"),
}


def world_models_for_event(
    *,
    event_signature: str,
    direction_hint: str = "neutral",
    max_models: int = MAX_WORLD_MODELS,
) -> tuple[WorldModel, ...]:
    """
    Generate competing World Models from a market event signature.

    Never assume one explanation because it appears first.
    """
    sig = event_signature.lower()
    bullish = direction_hint == "bullish" or any(
        w in sig for w in ("bullish", "reclaim", "breakout up", "sweep low", "accumulation")
    )
    bearish = direction_hint == "bearish" or any(
        w in sig for w in ("bearish", "breakdown", "sweep high", "distribution", "reject")
    )

    models: list[WorldModel] = []

    if direction_hint == "bullish":
        models.extend(_bullish_event_models(sig))
    elif direction_hint == "bearish":
        models.extend(_bearish_event_models(sig))
    elif bullish and bearish:
        models.extend(_bullish_event_models(sig)[:4])
        models.extend(_bearish_event_models(sig)[:3])
    elif bullish:
        models.extend(_bullish_event_models(sig))
    elif bearish:
        models.extend(_bearish_event_models(sig))
    else:
        models.extend(_neutral_models(sig))

    if len(models) <= max_models:
        return tuple(models)

    scored = sorted(
        models,
        key=lambda m: _relevance_score(m.model_id, sig),
        reverse=True,
    )
    return tuple(scored[:max_models])


def _relevance_score(model_id: str, sig: str) -> float:
    hints = _MODEL_SIGNATURE_HINTS.get(model_id, ())
    if not hints:
        return 1.0
    hits = sum(1 for h in hints if h in sig)
    return hits + 0.1


def _bullish_event_models(sig: str) -> list[WorldModel]:
    return [
        WorldModel(
            model_id="institutional_accumulation",
            name="Institutional Accumulation",
            description="Smart money absorbing supply before continuation higher.",
            direction="bullish",
            assumptions=("Institutions are positioned for higher prices",),
            expected_events=("Higher lows hold", "Volume on up moves expands", "Liquidity above gets targeted"),
            falsification_events=("Immediate rejection below sweep low", "Volume dries on rallies"),
        ),
        WorldModel(
            model_id="bull_trap",
            name="Bull Trap",
            description="False breakout designed to trap late buyers before reversal.",
            direction="bearish",
            assumptions=("Retail chased the breakout", "No institutional follow-through"),
            expected_events=("Quick failure below breakout level", "Aggressive sell volume"),
            falsification_events=("Sustained acceptance above breakout", "Follow-through volume"),
        ),
        WorldModel(
            model_id="short_covering",
            name="Short Covering",
            description="Forced short exits driving price — may not imply new demand.",
            direction="bullish",
            assumptions=("Open interest was skewed short", "Move is squeeze-driven"),
            expected_events=("Sharp spike then stall", "Momentum fades quickly"),
            falsification_events=("Continued trend after spike", "New highs with volume"),
        ),
        WorldModel(
            model_id="liquidity_sweep_low",
            name="Liquidity Sweep (Low)",
            description="Stops hunted below support before potential reversal or continuation.",
            direction="bullish",
            assumptions=("Liquidity pool existed below support", "Sweep was intentional"),
            expected_events=("Reclaim of swept level", "Trapped shorts fuel move"),
            falsification_events=("No reclaim", "Acceptance below swept level"),
        ),
        WorldModel(
            model_id="news_reaction_bull",
            name="News Reaction (Bullish)",
            description="Macro headline repricing causing aggressive bid.",
            direction="bullish",
            assumptions=("News was unexpected", "Repricing is incomplete"),
            expected_events=("Volatility expansion", "Trend in news direction"),
            falsification_events=("Immediate mean reversion", "No follow-through"),
        ),
        WorldModel(
            model_id="momentum_continuation",
            name="Momentum Continuation",
            description="Trend participants adding — move is extension not reversal.",
            direction="bullish",
            assumptions=("Trend structure intact", "Pullback was shallow"),
            expected_events=("New highs", "Momentum acceleration"),
            falsification_events=("Structure break", "Momentum divergence"),
        ),
        WorldModel(
            model_id="distribution",
            name="Distribution",
            description="Institutions selling into strength — bullish candle is exit liquidity.",
            direction="bearish",
            assumptions=("Price reached premium", "Volume shows absorption not demand"),
            expected_events=("Failure at highs", "Lower high formation"),
            falsification_events=("Breakout with volume", "Higher high acceptance"),
        ),
        WorldModel(
            model_id="algorithmic_repricing",
            name="Algorithmic Repricing",
            description="Systematic flow adjusting to new fair value — not discretionary.",
            direction="neutral",
            assumptions=("Algo models repricing simultaneously",),
            expected_events=("Smooth directional drift", "Mean reversion after initial move"),
            falsification_events=("Discretionary follow-through", "Liquidity event"),
        ),
    ]


def _bearish_event_models(sig: str) -> list[WorldModel]:
    return [
        WorldModel(
            model_id="institutional_distribution",
            name="Institutional Distribution",
            description="Smart money distributing into demand before lower prices.",
            direction="bearish",
            assumptions=("Institutions reducing exposure",),
            expected_events=("Lower highs", "Support failures", "Liquidity below targeted"),
            falsification_events=("Reclaim of breakdown level", "Strong bid absorption"),
        ),
        WorldModel(
            model_id="bear_trap",
            name="Bear Trap",
            description="False breakdown trapping late sellers before reversal up.",
            direction="bullish",
            assumptions=("Retail chased breakdown",),
            expected_events=("Quick reclaim above breakdown", "Short squeeze"),
            falsification_events=("Acceptance below breakdown",),
        ),
        WorldModel(
            model_id="long_liquidation",
            name="Long Liquidation",
            description="Forced long exits driving price — may not imply new supply.",
            direction="bearish",
            assumptions=("Leveraged longs caught",),
            expected_events=("Sharp drop then bounce", "Momentum fades"),
            falsification_events=("New lows with volume", "Trend continuation"),
        ),
        WorldModel(
            model_id="liquidity_sweep_high",
            name="Liquidity Sweep (High)",
            description="Stops hunted above resistance before potential reversal.",
            direction="bearish",
            assumptions=("Liquidity pool above resistance",),
            expected_events=("Rejection from swept high", "Trapped longs"),
            falsification_events=("Acceptance above sweep",),
        ),
        WorldModel(
            model_id="momentum_breakdown",
            name="Momentum Breakdown",
            description="Trend failure — bearish extension not pullback.",
            direction="bearish",
            assumptions=("Trend structure broken",),
            expected_events=("Lower lows", "Momentum acceleration down"),
            falsification_events=("Structure reclaim",),
        ),
    ]


def _neutral_models(sig: str) -> list[WorldModel]:
    return [
        WorldModel(
            model_id="range_equilibrium",
            name="Range Equilibrium",
            description="Two-sided auction with no dominant participant.",
            direction="neutral",
            assumptions=("Neither side in control",),
            expected_events=("Mean reversion to range midpoint",),
            falsification_events=("Breakout with acceptance",),
        ),
        WorldModel(
            model_id="compression_before_expansion",
            name="Compression Before Expansion",
            description="Volatility coiling — direction unknown until release.",
            direction="neutral",
            assumptions=("Energy building", "Direction not yet revealed"),
            expected_events=("Volatility expansion", "Directional break"),
            falsification_events=("Continued compression beyond expectation",),
        ),
    ]
