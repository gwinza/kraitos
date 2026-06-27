"""Strategy-related data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MarketRegime = Literal[
    "trending",
    "ranging",
    "volatile",
    "low_liquidity",
    "news_risk",
    "unclear",
]


@dataclass(frozen=True)
class RegimeResult:
    """Output of market regime classification."""

    regime: MarketRegime
    confidence: float
    reason: str


MarketBias = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class TimeframeBiasDetail:
    """Bias assessment for a single timeframe."""

    timeframe: str
    bias: MarketBias
    score: float
    role: str


@dataclass(frozen=True)
class MultiTimeframeBiasResult:
    """Combined multi-timeframe directional bias."""

    bias: MarketBias
    confidence: float
    explanation: str
    layers: tuple[TimeframeBiasDetail, ...]


StructureTrend = Literal["bullish", "bearish", "ranging"]
SwingKind = Literal["high", "low"]
ZoneKind = Literal["support", "resistance", "liquidity"]
StructureEventKind = Literal[
    "higher_high",
    "higher_low",
    "lower_high",
    "lower_low",
    "bos_bullish",
    "bos_bearish",
    "choch_bullish",
    "choch_bearish",
]


@dataclass(frozen=True)
class SwingPoint:
    """Detected swing high or swing low."""

    bar_index: int
    time: object
    price: float
    kind: SwingKind


@dataclass(frozen=True)
class StructureEvent:
    """Market structure event."""

    kind: StructureEventKind
    bar_index: int
    time: object
    price: float
    reference_price: float
    description: str


@dataclass(frozen=True)
class PriceZone:
    """Support, resistance, or liquidity zone."""

    kind: ZoneKind
    lower: float
    upper: float
    mid: float
    touches: int
    times: tuple[object, ...]


@dataclass(frozen=True)
class MarketContext:
    """Structured market structure context for downstream modules."""

    symbol: str
    timeframe: str
    trend: StructureTrend
    higher_highs: bool
    higher_lows: bool
    lower_highs: bool
    lower_lows: bool
    swing_highs: tuple[SwingPoint, ...]
    swing_lows: tuple[SwingPoint, ...]
    structure_events: tuple[StructureEvent, ...]
    support_zones: tuple[PriceZone, ...]
    resistance_zones: tuple[PriceZone, ...]
    liquidity_zones: tuple[PriceZone, ...]
    last_bos: StructureEvent | None
    last_choch: StructureEvent | None


HarvestMode = Literal["none", "conditional", "full"]


@dataclass(frozen=True)
class HarvestDecision:
    """Harvest engine trade permission and target."""

    mode: HarvestMode
    allowed: bool
    target_pips: float
    reason: str


@dataclass(frozen=True)
class HarvestContext:
    """Inputs required to evaluate harvest rules."""

    symbol: str
    bias: MultiTimeframeBiasResult
    structure: MarketContext
    regime: RegimeResult
    current_spread: float
    spread_limit: float
    in_active_session: bool = True
    correlation_support: bool = False
    fundamental_support: bool = True
    news_risk_active: bool = False
    council_micro_harvest: bool = False
    narrative_direction: str = "neutral"
    volume_momentum_strong: bool = False
    story_clear: bool = False
    opportunity_type: str | None = None
    price_action_valid: bool = False
    structure_supports: bool = False


MicroScalpAction = Literal["buy", "sell", "no_trade"]


@dataclass(frozen=True)
class MicroScalpSignal:
    """Micro scalper trade signal."""

    action: MicroScalpAction
    reason: str
    target_pips: float = 0.0


NewsImpactLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class NewsEvent:
    """Manual news event placeholder (no external API)."""

    news_time: object
    currency: str
    impact_level: NewsImpactLevel
    restriction_before_minutes: int | None = None
    restriction_after_minutes: int | None = None
    title: str = ""


@dataclass(frozen=True)
class NewsFilterResult:
    """Outcome of a news filter check."""

    allowed: bool
    reason: str
    blocking_event: NewsEvent | None = None
    affected_pairs: tuple[str, ...] = ()
