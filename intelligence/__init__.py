"""Dynamic trend-based strategy intelligence for Kraitos."""



from intelligence.asset_strategy_memory import AssetStrategyMemory, DynamicStrategy

from intelligence.asset_trend_analyzer import AssetState, AssetTrendAnalyzer, AssetTrendSnapshot

from intelligence.dynamic_strategy_selector import DynamicStrategySelector, StrategySelection

from intelligence.indicator_interpretation_engine import INDICATOR_INTERPRETATION_DNA

from intelligence.market_psychology_engine import MARKET_PSYCHOLOGY_DNA

from intelligence.trader_memory_engine import TRADER_MEMORY_DNA

from intelligence.human_trader_reasoning_layer import HUMAN_TRADER_REASONING_DNA

from intelligence.kraitos_thesis_doctrine import KRAITOS_THESIS_DNA

from intelligence.story_aware_participation_doctrine import STORY_AWARE_PARTICIPATION_DNA



STORY_EVOLUTION_DNA = """

The market is a living narrative.



Every new candle contributes evidence to an evolving story.



Lower timeframes shape higher timeframes through accumulated information.



Higher timeframes provide context to lower timeframes.



Kraitos understands not only what the market is doing, but how it evolved and where it is likely to go next.



Kraitos does not analyse isolated charts.



He reads the unfolding story of the market.

""".strip()



EVIDENCE_SYNTHESIS_DNA = """

Kraitos does not interpret trends, pullbacks, liquidity sweeps, candlestick patterns, sessions, volume shifts, and momentum as separate stories.



They are evidence.



Kraitos synthesises all available evidence into a single coherent explanation of what the asset is doing, why it is doing it, what is likely to happen next, and what action should be taken.



The market story is not a label.



It is the picture painted by all the evidence combined.

""".strip()



__all__ = [

    "AssetState",

    "AssetStrategyMemory",

    "AssetTrendAnalyzer",

    "AssetTrendSnapshot",

    "DynamicStrategy",

    "DynamicStrategySelector",

    "EVIDENCE_SYNTHESIS_DNA",

    "INDICATOR_INTERPRETATION_DNA",

    "MARKET_PSYCHOLOGY_DNA",

    "TRADER_MEMORY_DNA",

    "HUMAN_TRADER_REASONING_DNA",

    "STORY_AWARE_PARTICIPATION_DNA",

    "KRAITOS_THESIS_DNA",

    "STORY_EVOLUTION_DNA",

    "StrategySelection",

]


