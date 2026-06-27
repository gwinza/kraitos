"""Execution layer data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from risk.models import PortfolioState
from risk.risk_manager import RiskManager
from strategies.models import (
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    RegimeResult,
)  # MarketContext used by EntryContext and ExitContext

if TYPE_CHECKING:
    from strategies.conviction_engine import ConvictionAssessment
    from strategies.market_regime_engine import MarketRegimeResult
    from strategies.range_intelligence_engine import RangeIntelligenceResult
    from strategies.scalping_intelligence_engine import ScalpingIntelligenceResult
    from strategies.trend_quality_engine import TrendQualityResult

EntryAction = Literal["enter_buy", "enter_sell", "wait", "reject"]
TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class EntryConfirmation:
    """Result of a single entry prerequisite check."""

    name: str
    passed: bool
    detail: str


@dataclass
class EntryContext:
    """Inputs required to evaluate a trade entry."""

    symbol: str
    bias: MultiTimeframeBiasResult
    structure: MarketContext
    regime: RegimeResult
    momentum: MicroScalpSignal
    current_spread: float
    spread_limit: float
    entry_price: float
    stop_loss: float
    portfolio: PortfolioState
    risk_manager: RiskManager
    trace_id: str | None = None
    min_bias_confidence: float | None = None
    min_structure_swings: int | None = None
    candles: object | None = None  # pd.DataFrame — M5 bars for ATR entry timing
    conviction: object | None = None  # ConvictionAssessment — adaptive confirmation
    market_regime_intelligence: object | None = None  # MarketRegimeResult
    range_intelligence: object | None = None  # RangeIntelligenceResult
    trend_quality: object | None = None  # TrendQualityResult — regime supervisor
    scalping_intelligence: object | None = None  # ScalpingIntelligenceResult — micro evidence
    expected_target_pips: float | None = None
    execution_quality: object | None = None  # ExecutionQualityResult — entry timing and sizing
    patience_ready: bool = False
    patience_explanation: str = ""
    resolved_side: TradeSide | None = None
    cognitive_decision: object | None = None


@dataclass(frozen=True)
class EntryDecision:
    """Final entry engine decision."""

    action: EntryAction
    explanation: str
    lot_size: float = 0.0
    confirmations: tuple[EntryConfirmation, ...] = ()


ExitAction = Literal[
    "take_profit",
    "cut_loss",
    "trail_stop",
    "scale_out",
    "hold_trade",
    "close_early",
]


@dataclass(frozen=True)
class OpenTrade:
    """An open position being evaluated for exit."""

    symbol: str
    side: TradeSide
    entry_price: float
    stop_loss: float
    volume: float
    take_profit: float | None = None
    target_pips: float | None = None
    bars_since_entry: int = 0
    best_price: float | None = None
    partial_taken: bool = False
    tp2_taken: bool = False
    invalidation_level: float | None = None


@dataclass
class ExitContext:
    """Inputs required to evaluate trade exit."""

    trade: OpenTrade
    current_price: float
    candles: object  # pd.DataFrame
    structure: MarketContext
    momentum: object | None = None  # MicroScalpSignal
    trend_quality_score: int | None = None
    reversal_pressure_score: int | None = None
    setup_kind: str = "harvest"
    trade_maturity: object | None = None
    scout_or_commit: str = ""
    scratch_eligible: bool = False
    momentum_clarity_at_entry: str = ""
    acceptance_score_at_entry: int = 50
    rejection_score_at_entry: int = 50
    spread_pips: float = 1.0
    spread_limit: float = 3.0


@dataclass(frozen=True)
class ExitDecision:
    """Exit engine decision."""

    action: ExitAction
    reason: str
    new_stop_loss: float | None = None
    scale_fraction: float | None = None


PaperTradeStatus = Literal["open", "closed"]


@dataclass
class PaperTrade:
    """A simulated paper trade."""

    trade_id: str
    symbol: str
    side: TradeSide
    entry_time: object
    entry_price: float
    lot_size: float
    stop_loss: float
    take_profit: float | None
    status: PaperTradeStatus = "open"
    exit_time: object | None = None
    exit_price: float | None = None
    closed_pl: float = 0.0
    exit_reason: str | None = None
    bars_since_entry: int = 0
    best_price: float = 0.0
    partial_taken: bool = False
    tp2_taken: bool = False
    invalidation_level: float | None = None
    trace_id: str | None = None
    entry_type: str | None = None
    story_direction: str | None = None
    story_confidence: float | None = None
    story_narrative: str | None = None
    cognitive_snapshot: str | None = None


@dataclass(frozen=True)
class PaperAccountSnapshot:
    """Current paper trading account state."""

    balance: float
    initial_balance: float
    closed_pl: float
    floating_pl: float
    equity: float
    open_trades: tuple[PaperTrade, ...]
    trade_history: tuple[PaperTrade, ...]
