"""
Kraitos Thesis Doctrine — every trade is a managed thesis, not a signal.

Observe → Understand → Thesis → Participate → Manage → Allocate
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from intelligence.human_trader_reasoning_layer import TradeReasoning
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.story_forecast_engine import StoryForecastResult
    from strategies.market_regime_engine import MarketRegimeResult
    from strategies.range_intelligence_engine import RangeIntelligenceResult
    from strategies.scalping_intelligence_engine import ScalpingIntelligenceResult
    from strategies.trend_quality_engine import TrendQualityResult
    from strategies.models import HarvestDecision, MarketContext, MultiTimeframeBiasResult

ThesisDirection = Literal["bullish", "bearish", "neutral"]

KRAITOS_THESIS_DNA = """
Kraitos is a thesis-driven trade manager, not a signal hunter.

Every trade defines: market story, directional thesis, invalidation level,
fixed risk, target liquidity, entry trigger, and exit plan.

Momentum and indicators explain behaviour — they do not veto valid theses.
Reject only when stop geometry is invalid, spread destroys reward/risk,
target liquidity is genuinely unclear, or no coherent story exists.
""".strip()

DEFAULT_TP1_R = 1.25
DEFAULT_TP1_FRACTION = 0.50
MIN_REWARD_RISK = 0.80
INVALIDATION_BUFFER_PIPS = 3.0


def _dataclass_to_dict(value: object) -> dict:
    data = asdict(value)
    return {
        key: tuple(item for item in val) if isinstance(val, list) else val
        for key, val in data.items()
    }


@dataclass(frozen=True)
class MarketLifecycleContext:
    """Market lifecycle facts that shape the thesis itself."""

    market_phase: str = "unknown"
    dominant_side: str = "unknown"
    trend_direction: str = "neutral"
    trend_quality_score: int = 0
    trend_maturity_score: float = 0.0
    continuation_probability: float = 0.0
    reversal_probability: float = 0.0
    reversal_pressure_score: float = 0.0
    distribution_probability: float = 0.0
    accumulation_probability: float = 0.0
    event_risk: str = "none_assessed"


@dataclass(frozen=True)
class ThesisMarketRegime:
    """Regime context that determines which strategy logic belongs."""

    current_regime: str = "unknown"
    regime_confidence: float = 0.0
    range_quality_score: int = 0
    breakout_risk_score: int = 0
    compression_probability: float = 0.0
    likely_next_regime: str = "unknown"
    strategy_bias: str = "wait_for_clarity"


@dataclass(frozen=True)
class ThesisStrength:
    """Why this thesis deserves, or does not deserve, risk allocation."""

    thesis_confidence: float = 0.0
    story_alignment_score: float = 0.0
    lifecycle_alignment_score: float = 0.0
    structure_quality_score: float = 0.0
    opportunity_quality_score: float = 0.0


@dataclass(frozen=True)
class PullbackAnalysis:
    """How the current retracement behaves relative to the thesis."""

    pullback_type: str = "unknown"
    retracement_depth_pct: float = 0.0
    retracement_depth_atr: float = 0.0
    structure_status: str = "unknown"
    bounce_quality: str = "unknown"


@dataclass(frozen=True)
class ControlAnalysis:
    """Which side controls the tape and whether that control is changing."""

    who_is_in_control: str = "unknown"
    is_control_strengthening: bool = False
    is_control_weakening: bool = False
    evidence_for_buyers: tuple[str, ...] = ()
    evidence_for_sellers: tuple[str, ...] = ()


@dataclass(frozen=True)
class LifecycleAnalysis:
    """Why Kraitos selected the current lifecycle phase."""

    why_current_phase_was_selected: str = ""
    evidence_of_accumulation: tuple[str, ...] = ()
    evidence_of_distribution: tuple[str, ...] = ()
    evidence_of_trend_exhaustion: tuple[str, ...] = ()
    evidence_of_reversal: tuple[str, ...] = ()
    expected_next_phase: str = "unknown"


@dataclass(frozen=True)
class ThesisChallenges:
    """Kraitos arguing against the thesis before allocating risk."""

    evidence_thesis_is_wrong: tuple[str, ...] = ()
    evidence_opposite_side_gaining_control: tuple[str, ...] = ()
    evidence_reversal_not_retracement: tuple[str, ...] = ()
    evidence_distribution_not_continuation: tuple[str, ...] = ()
    evidence_trend_quality_deteriorating: tuple[str, ...] = ()
    abandon_thesis_if: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThesisEvolution:
    """Latest live thesis state used by management decisions."""

    thesis_strength: float = 0.0
    trend_quality: int = 0
    reversal_pressure: float = 0.0
    continuation_probability: float = 0.0
    market_phase: str = "unknown"
    story_confidence: float = 0.0
    management_bias: str = "normal"


@dataclass(frozen=True)
class ThesisCompletionReport:
    """Post-trade thesis review. Filled progressively as trades close."""

    entry_story: str = ""
    mid_trade_story: str = ""
    exit_story: str = ""
    thesis_correct: bool | None = None
    thesis_partially_correct: bool | None = None
    warning_signs_missed: tuple[str, ...] = ()
    lifecycle_clues_present: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeThesis:
    """Complete trade thesis — the contract Kraitos manages."""

    asset: str
    timeframe: str
    market_story: str
    thesis_direction: ThesisDirection
    thesis_confidence: float
    entry_reason: str
    invalidation_level: float
    stop_loss: float
    risk_percent: float
    target_liquidity: float
    take_profit_1: float
    take_profit_2: float
    management_plan: str
    exit_if_wrong: str
    exit_if_right: str
    is_tradeable: bool
    rejection_reason: str = ""
    reward_risk_ratio: float = 0.0
    invalidation_pips: float = 0.0
    tp1_r_multiple: float = DEFAULT_TP1_R
    market_context: MarketLifecycleContext = field(default_factory=MarketLifecycleContext)
    market_regime: ThesisMarketRegime = field(default_factory=ThesisMarketRegime)
    thesis_strength: ThesisStrength = field(default_factory=ThesisStrength)
    pullback_analysis: PullbackAnalysis = field(default_factory=PullbackAnalysis)
    control_analysis: ControlAnalysis = field(default_factory=ControlAnalysis)
    lifecycle_analysis: LifecycleAnalysis = field(default_factory=LifecycleAnalysis)
    range_intelligence: dict[str, object] = field(default_factory=dict)
    scalping_intelligence: dict[str, object] = field(default_factory=dict)
    thesis_challenges: ThesisChallenges = field(default_factory=ThesisChallenges)
    thesis_evolution: ThesisEvolution = field(default_factory=ThesisEvolution)
    thesis_completion_report: ThesisCompletionReport = field(
        default_factory=ThesisCompletionReport
    )

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "market_story": self.market_story,
            "thesis_direction": self.thesis_direction,
            "thesis_confidence": round(self.thesis_confidence, 4),
            "entry_reason": self.entry_reason,
            "invalidation_level": self.invalidation_level,
            "stop_loss": self.stop_loss,
            "risk_percent": self.risk_percent,
            "target_liquidity": self.target_liquidity,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "management_plan": self.management_plan,
            "exit_if_wrong": self.exit_if_wrong,
            "exit_if_right": self.exit_if_right,
            "is_tradeable": self.is_tradeable,
            "rejection_reason": self.rejection_reason,
            "reward_risk_ratio": round(self.reward_risk_ratio, 3),
            "invalidation_pips": round(self.invalidation_pips, 2),
            "tp1_r_multiple": self.tp1_r_multiple,
            "market_context": _dataclass_to_dict(self.market_context),
            "market_regime": _dataclass_to_dict(self.market_regime),
            "thesis_strength": _dataclass_to_dict(self.thesis_strength),
            "pullback_analysis": _dataclass_to_dict(self.pullback_analysis),
            "control_analysis": _dataclass_to_dict(self.control_analysis),
            "lifecycle_analysis": _dataclass_to_dict(self.lifecycle_analysis),
            "range_intelligence": self.range_intelligence,
            "scalping_intelligence": self.scalping_intelligence,
            "thesis_challenges": _dataclass_to_dict(self.thesis_challenges),
            "thesis_evolution": _dataclass_to_dict(self.thesis_evolution),
            "thesis_completion_report": _dataclass_to_dict(
                self.thesis_completion_report
            ),
        }


Thesis = TradeThesis


@dataclass
class ThesisTracker:
    """Runtime thesis quality metrics."""

    built: int = 0
    tradeable: int = 0
    rejected: int = 0
    unclear_story_blocks: int = 0
    invalidation_blocks: int = 0
    target_liquidity_blocks: int = 0
    geometry_blocks: int = 0
    spread_rr_blocks: int = 0
    tp1_hits: int = 0
    runner_continuations: int = 0
    runner_closes: int = 0
    runner_wins: int = 0
    runner_losses: int = 0
    be_stopouts: int = 0
    runner_pnl_total: float = 0.0
    runner_r_total: float = 0.0
    positions_opened: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    rr_samples: list[float] = field(default_factory=list)
    invalidation_pip_samples: list[float] = field(default_factory=list)

    def record(self, thesis: TradeThesis) -> None:
        self.built += 1
        if thesis.is_tradeable:
            self.tradeable += 1
            if thesis.reward_risk_ratio > 0:
                self.rr_samples.append(thesis.reward_risk_ratio)
            if thesis.invalidation_pips > 0:
                self.invalidation_pip_samples.append(thesis.invalidation_pips)
        else:
            self.rejected += 1
            reason = thesis.rejection_reason or "unknown"
            key = reason[:100]
            self.rejection_reasons[key] = self.rejection_reasons.get(key, 0) + 1
            lower = reason.lower()
            if "unclear" in lower and "story" in lower:
                self.unclear_story_blocks += 1
            elif "invalidation" in lower:
                self.invalidation_blocks += 1
            elif "target liquidity" in lower or "liquidity target" in lower:
                self.target_liquidity_blocks += 1
            elif "geometry" in lower or "stop loss" in lower:
                self.geometry_blocks += 1
            elif "reward" in lower or "spread" in lower:
                self.spread_rr_blocks += 1

    def record_tp1_hit(self) -> None:
        self.tp1_hits += 1

    def record_runner_continuation(self) -> None:
        self.runner_continuations += 1

    def record_position_opened(self) -> None:
        self.positions_opened += 1

    def record_runner_close(
        self,
        *,
        pnl: float,
        r_multiple: float,
        reason: str,
    ) -> None:
        """Record runner leg outcome after TP1 partial."""
        self.record_runner_continuation()
        self.runner_closes += 1
        self.runner_pnl_total += pnl
        self.runner_r_total += r_multiple
        if pnl > 0.01:
            self.runner_wins += 1
        elif pnl < -0.01:
            self.runner_losses += 1
        if reason == "stop_loss" and abs(pnl) <= 1.0 and abs(r_multiple) <= 0.15:
            self.be_stopouts += 1

    def summary(self) -> dict:
        avg_rr = sum(self.rr_samples) / len(self.rr_samples) if self.rr_samples else 0.0
        avg_inv = (
            sum(self.invalidation_pip_samples) / len(self.invalidation_pip_samples)
            if self.invalidation_pip_samples
            else 0.0
        )
        tp1_denom = max(self.positions_opened or self.tradeable, 1)
        tp1_rate = self.tp1_hits / tp1_denom
        runner_rate = self.runner_continuations / max(self.tp1_hits, 1)
        runner_avg_r = self.runner_r_total / max(self.runner_closes, 1)
        return {
            "built": self.built,
            "tradeable": self.tradeable,
            "rejected": self.rejected,
            "unclear_story_blocks": self.unclear_story_blocks,
            "invalidation_blocks": self.invalidation_blocks,
            "target_liquidity_blocks": self.target_liquidity_blocks,
            "geometry_blocks": self.geometry_blocks,
            "spread_rr_blocks": self.spread_rr_blocks,
            "avg_reward_risk": round(avg_rr, 3),
            "avg_invalidation_pips": round(avg_inv, 2),
            "tp1_hit_rate": round(tp1_rate, 4),
            "tp1_hits": self.tp1_hits,
            "runner_continuation_rate": round(runner_rate, 4),
            "positions_opened": self.positions_opened,
            "runner_closes": self.runner_closes,
            "runner_wins": self.runner_wins,
            "runner_losses": self.runner_losses,
            "be_stopouts": self.be_stopouts,
            "runner_pnl_total": round(self.runner_pnl_total, 2),
            "runner_avg_r": round(runner_avg_r, 4),
            "top_rejection_reasons": sorted(
                self.rejection_reasons.items(), key=lambda x: x[1], reverse=True
            )[:10],
        }


_lock = Lock()
_tracker: ThesisTracker | None = None


def get_thesis_tracker() -> ThesisTracker:
    global _tracker
    with _lock:
        if _tracker is None:
            _tracker = ThesisTracker()
        return _tracker


def reset_thesis_tracker() -> ThesisTracker:
    global _tracker
    with _lock:
        _tracker = ThesisTracker()
        return _tracker


class KraitosThesisEngine:
    """Build and validate trade theses from market context."""

    def __init__(
        self,
        *,
        timeframe: str = "H1",
        tp1_r: float = DEFAULT_TP1_R,
        tp1_fraction: float = DEFAULT_TP1_FRACTION,
        min_reward_risk: float = MIN_REWARD_RISK,
        invalidation_buffer_pips: float = INVALIDATION_BUFFER_PIPS,
    ) -> None:
        self.timeframe = timeframe
        self.tp1_r = tp1_r
        self.tp1_fraction = tp1_fraction
        self.min_reward_risk = min_reward_risk
        self.invalidation_buffer_pips = invalidation_buffer_pips

    def build_thesis(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        pip_size: float,
        spread_pips: float,
        spread_limit: float,
        risk_percent: float = 1.0,
        market_story: MarketStoryResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        harvest: HarvestDecision | None = None,
        trade_reasoning: TradeReasoning | None = None,
        trend_quality: TrendQualityResult | None = None,
        market_regime: MarketRegimeResult | None = None,
        range_intelligence: RangeIntelligenceResult | None = None,
        scalping_intelligence: ScalpingIntelligenceResult | None = None,
        setup_kind: str = "harvest",
        momentum_note: str = "",
    ) -> TradeThesis:
        direction = self._resolve_direction(side, bias, market_story, story_forecast, structure)
        story_text = self._market_story_text(market_story, trade_reasoning, harvest)
        confidence = self._thesis_confidence(bias, market_story, story_forecast)
        confidence = self._adjust_confidence_with_scalping_intelligence(
            confidence, scalping_intelligence
        )
        entry_reason = self._entry_reason(
            market_story,
            story_forecast,
            harvest,
            setup_kind,
            momentum_note,
            scalping_intelligence=scalping_intelligence,
        )

        invalidation = self._compute_invalidation(
            side=side,
            entry_price=entry_price,
            structure=structure,
            pip_size=pip_size,
            market_story=market_story,
        )
        stop_loss = self._stop_from_invalidation(
            side=side,
            invalidation=invalidation,
            entry_price=entry_price,
            pip_size=pip_size,
        )
        inv_pips = abs(entry_price - invalidation) / pip_size if pip_size > 0 else 0.0

        target_liq = self._compute_target_liquidity(
            side=side,
            entry_price=entry_price,
            structure=structure,
            pip_size=pip_size,
            story_forecast=story_forecast,
            harvest=harvest,
        )

        risk_pips = abs(entry_price - stop_loss) / pip_size if pip_size > 0 else 0.0
        reward_pips = abs(target_liq - entry_price) / pip_size if pip_size > 0 else 0.0
        net_reward = max(0.0, reward_pips - spread_pips)
        rr = net_reward / risk_pips if risk_pips > 0 else 0.0

        tp1, tp2 = self._compute_take_profits(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_liquidity=target_liq,
            pip_size=pip_size,
        )

        management, exit_wrong, exit_right = self._management_plan(
            side=side,
            tp1_r=self.tp1_r,
            tp1_fraction=self.tp1_fraction,
            invalidation=invalidation,
            target_liq=target_liq,
        )
        lifecycle_context = self._market_lifecycle_context(
            side=side,
            structure=structure,
            trend_quality=trend_quality,
        )
        regime_context = self._market_regime_context(market_regime, range_intelligence)
        thesis_strength = self._thesis_strength(
            direction=direction,
            confidence=confidence,
            reward_risk=rr,
            structure=structure,
            market_story=market_story,
            harvest=harvest,
            trend_quality=trend_quality,
            market_regime=market_regime,
            scalping_intelligence=scalping_intelligence,
        )
        pullback_analysis = self._pullback_analysis(
            side=side,
            structure=structure,
            trend_quality=trend_quality,
        )
        control_analysis = self._control_analysis(
            side=side,
            structure=structure,
            trend_quality=trend_quality,
        )
        lifecycle_analysis = self._lifecycle_analysis(
            trend_quality,
            scalping_intelligence=scalping_intelligence,
            market_regime=market_regime,
            range_intelligence=range_intelligence,
        )
        thesis_challenges = self._thesis_challenges(
            side=side,
            structure=structure,
            market_story=market_story,
            trend_quality=trend_quality,
            market_regime=market_regime,
            range_intelligence=range_intelligence,
            scalping_intelligence=scalping_intelligence,
        )
        thesis_evolution = ThesisEvolution(
            thesis_strength=round(thesis_strength.thesis_confidence, 4),
            trend_quality=lifecycle_context.trend_quality_score,
            reversal_pressure=lifecycle_context.reversal_pressure_score,
            continuation_probability=lifecycle_context.continuation_probability,
            market_phase=lifecycle_context.market_phase,
            story_confidence=confidence,
            management_bias=self._management_bias(lifecycle_context),
        )
        completion_report = ThesisCompletionReport(
            entry_story=(
                f"{story_text} Market phase={lifecycle_context.market_phase}, "
                f"regime={regime_context.current_regime}, "
                f"trend_quality={lifecycle_context.trend_quality_score}, "
                f"reversal_pressure={lifecycle_context.reversal_pressure_score:.2f}. "
                f"{self._scalping_story_text(scalping_intelligence)}"
            )[:700],
            lifecycle_clues_present=tuple(
                item
                for group in (
                    lifecycle_analysis.evidence_of_accumulation,
                    lifecycle_analysis.evidence_of_distribution,
                    lifecycle_analysis.evidence_of_trend_exhaustion,
                    lifecycle_analysis.evidence_of_reversal,
                )
                for item in group
            ),
        )
        management = self._add_lifecycle_management(
            management,
            lifecycle_context=lifecycle_context,
            thesis_challenges=thesis_challenges,
        )
        management = self._add_regime_management(
            management,
            regime_context=regime_context,
        )

        tradeable, rejection = self._validate_tradeability(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            invalidation=invalidation,
            target_liquidity=target_liq,
            reward_risk=rr,
            spread_pips=spread_pips,
            spread_limit=spread_limit,
            market_story=market_story,
            inv_pips=inv_pips,
            risk_pips=risk_pips,
        )

        thesis = TradeThesis(
            asset=symbol.strip().upper(),
            timeframe=self.timeframe,
            market_story=story_text,
            thesis_direction=direction,
            thesis_confidence=confidence,
            entry_reason=entry_reason,
            invalidation_level=invalidation,
            stop_loss=stop_loss,
            risk_percent=risk_percent,
            target_liquidity=target_liq,
            take_profit_1=tp1,
            take_profit_2=tp2,
            management_plan=management,
            exit_if_wrong=exit_wrong,
            exit_if_right=exit_right,
            is_tradeable=tradeable,
            rejection_reason=rejection,
            reward_risk_ratio=rr,
            invalidation_pips=inv_pips,
            tp1_r_multiple=self.tp1_r,
            market_context=lifecycle_context,
            market_regime=regime_context,
            thesis_strength=thesis_strength,
            pullback_analysis=pullback_analysis,
            control_analysis=control_analysis,
            lifecycle_analysis=lifecycle_analysis,
            range_intelligence=self._range_intelligence_dict(range_intelligence),
            scalping_intelligence=self._scalping_intelligence_dict(scalping_intelligence),
            thesis_challenges=thesis_challenges,
            thesis_evolution=thesis_evolution,
            thesis_completion_report=completion_report,
        )
        get_thesis_tracker().record(thesis)
        return thesis

    @staticmethod
    def _market_lifecycle_context(
        *,
        side: str,
        structure: MarketContext,
        trend_quality: object | None,
    ) -> MarketLifecycleContext:
        if trend_quality is None:
            trend = structure.trend if structure.trend in {"bullish", "bearish"} else "neutral"
            return MarketLifecycleContext(
                market_phase="unknown",
                dominant_side="buyers" if trend == "bullish" else "sellers" if trend == "bearish" else "unknown",
                trend_direction=trend,
            )
        phase = str(getattr(trend_quality, "trend_phase", "unknown") or "unknown")
        regime = str(getattr(trend_quality, "regime", "") or "")
        trend = str(getattr(trend_quality, "trend_direction", "neutral") or "neutral")
        continuation = float(getattr(trend_quality, "continuation_probability", 0.0) or 0.0)
        reversal = float(getattr(trend_quality, "reversal_probability", 0.0) or 0.0)
        maturity_by_phase = {
            "expansion": 0.35,
            "healthy_pullback": 0.50,
            "exhaustion": 0.75,
            "distribution": 0.85,
            "reversal_warning": 0.92,
            "confirmed_reversal": 1.00,
        }
        distribution = max(reversal, 0.65) if phase == "distribution" else reversal * 0.35
        accumulation = max(reversal, 0.65) if regime == "accumulation" else 0.0
        if trend == "bullish":
            dominant = "buyers"
        elif trend == "bearish":
            dominant = "sellers"
        else:
            dominant = "buyers" if side == "buy" else "sellers"
        return MarketLifecycleContext(
            market_phase=phase,
            dominant_side=dominant,
            trend_direction=trend,
            trend_quality_score=int(getattr(trend_quality, "trend_quality_score", 0) or 0),
            trend_maturity_score=round(maturity_by_phase.get(phase, 0.50), 3),
            continuation_probability=round(continuation, 4),
            reversal_probability=round(reversal, 4),
            reversal_pressure_score=round(reversal, 4),
            distribution_probability=round(distribution, 4),
            accumulation_probability=round(accumulation, 4),
            event_risk="none_assessed",
        )

    @staticmethod
    def _market_regime_context(
        market_regime: object | None,
        range_intelligence: object | None,
    ) -> ThesisMarketRegime:
        if market_regime is None:
            return ThesisMarketRegime(
                range_quality_score=int(
                    getattr(range_intelligence, "range_quality_score", 0) or 0
                ),
                breakout_risk_score=int(
                    getattr(range_intelligence, "breakout_risk_score", 0) or 0
                ),
            )
        return ThesisMarketRegime(
            current_regime=str(getattr(market_regime, "market_regime", "unknown") or "unknown"),
            regime_confidence=float(getattr(market_regime, "regime_confidence", 0.0) or 0.0),
            range_quality_score=int(getattr(market_regime, "range_quality_score", 0) or 0),
            breakout_risk_score=int(
                getattr(market_regime, "breakout_preparation_score", 0) or 0
            ),
            compression_probability=float(
                getattr(market_regime, "compression_probability", 0.0) or 0.0
            ),
            likely_next_regime=str(
                getattr(market_regime, "likely_next_regime", "unknown") or "unknown"
            ),
            strategy_bias=str(
                getattr(market_regime, "strategy_bias", "wait_for_clarity")
                or "wait_for_clarity"
            ),
        )

    @staticmethod
    def _thesis_strength(
        *,
        direction: ThesisDirection,
        confidence: float,
        reward_risk: float,
        structure: MarketContext,
        market_story: object | None,
        harvest: object | None,
        trend_quality: object | None,
        market_regime: object | None = None,
        scalping_intelligence: object | None = None,
    ) -> ThesisStrength:
        side_trend = "bullish" if direction == "bullish" else "bearish" if direction == "bearish" else "neutral"
        trend_direction = (
            str(getattr(trend_quality, "trend_direction", "") or "")
            if trend_quality is not None
            else structure.trend
        )
        story_clear = bool(market_story is not None and getattr(market_story, "story_clear", False))
        story_conf = (
            float(getattr(market_story, "overall_confidence", 50.0) or 50.0) / 100.0
            if market_story is not None
            else confidence
        )
        story_alignment = story_conf if story_clear else confidence * 0.65
        continuation = (
            float(getattr(trend_quality, "continuation_probability", 0.0) or 0.0)
            if trend_quality is not None
            else 0.50
        )
        reversal = (
            float(getattr(trend_quality, "reversal_probability", 0.0) or 0.0)
            if trend_quality is not None
            else 0.25
        )
        lifecycle_alignment = continuation if trend_direction == side_trend else reversal
        structure_ok = structure.trend == side_trend
        structure_quality = 0.80 if structure_ok else 0.45
        if side_trend == "bullish" and structure.higher_highs and structure.higher_lows:
            structure_quality = 0.90
        if side_trend == "bearish" and structure.lower_highs and structure.lower_lows:
            structure_quality = 0.90
        harvest_quality = 0.50
        if harvest is not None and getattr(harvest, "allowed", False):
            target = float(getattr(harvest, "target_pips", 0.0) or 0.0)
            harvest_quality = min(1.0, 0.50 + target / 20.0)
        if scalping_intelligence is not None:
            scalp_quality = float(
                getattr(scalping_intelligence, "scalp_quality_score", 50) or 50
            ) / 100.0
            scalp_expectancy = float(
                getattr(scalping_intelligence, "scalp_expectancy_score", 50) or 50
            ) / 100.0
            harvest_quality = (harvest_quality + scalp_quality + scalp_expectancy) / 3.0
        rr_quality = min(1.0, max(0.0, reward_risk / 2.0))
        if market_regime is not None:
            strategy_bias = str(getattr(market_regime, "strategy_bias", "") or "")
            current_regime = str(getattr(market_regime, "market_regime", "") or "")
            if strategy_bias in {"range_logic", "prepare_breakout"} and direction in {"bullish", "bearish"}:
                lifecycle_alignment *= 0.85
            if current_regime in {"strong_uptrend", "healthy_uptrend"} and direction == "bearish":
                lifecycle_alignment *= 0.65
            if current_regime in {"strong_downtrend", "healthy_downtrend"} and direction == "bullish":
                lifecycle_alignment *= 0.65
        opportunity_quality = round((harvest_quality + rr_quality) / 2.0, 4)
        return ThesisStrength(
            thesis_confidence=round(confidence, 4),
            story_alignment_score=round(story_alignment, 4),
            lifecycle_alignment_score=round(lifecycle_alignment, 4),
            structure_quality_score=round(structure_quality, 4),
            opportunity_quality_score=opportunity_quality,
        )

    @staticmethod
    def _pullback_analysis(
        *,
        side: str,
        structure: MarketContext,
        trend_quality: object | None,
    ) -> PullbackAnalysis:
        phase = str(getattr(trend_quality, "trend_phase", "unknown") or "unknown")
        trend = str(getattr(trend_quality, "trend_direction", structure.trend) or structure.trend)
        desired = "bullish" if side == "buy" else "bearish"
        if phase == "healthy_pullback":
            pullback_type = "healthy_retracement"
            bounce_quality = "constructive"
        elif phase in {"exhaustion", "distribution", "reversal_warning", "confirmed_reversal"}:
            pullback_type = "vulnerable_or_reversal"
            bounce_quality = "weak_or_unproven"
        elif phase == "expansion":
            pullback_type = "shallow_or_none"
            bounce_quality = "trend_control"
        else:
            pullback_type = "unknown"
            bounce_quality = "unknown"
        structure_status = "aligned" if trend == desired or structure.trend == desired else "conflicting"
        depth_pct = {
            "expansion": 0.15,
            "healthy_pullback": 0.38,
            "exhaustion": 0.62,
            "distribution": 0.75,
            "reversal_warning": 0.85,
            "confirmed_reversal": 1.00,
        }.get(phase, 0.0)
        return PullbackAnalysis(
            pullback_type=pullback_type,
            retracement_depth_pct=round(depth_pct, 3),
            retracement_depth_atr=round(depth_pct * 1.8, 3),
            structure_status=structure_status,
            bounce_quality=bounce_quality,
        )

    @staticmethod
    def _control_analysis(
        *,
        side: str,
        structure: MarketContext,
        trend_quality: object | None,
    ) -> ControlAnalysis:
        desired = "bullish" if side == "buy" else "bearish"
        trend = (
            str(getattr(trend_quality, "trend_direction", "") or "")
            if trend_quality is not None
            else structure.trend
        )
        phase = str(getattr(trend_quality, "trend_phase", "unknown") or "unknown")
        deteriorating = bool(getattr(trend_quality, "deteriorating", False))
        control = "buyers" if trend == "bullish" else "sellers" if trend == "bearish" else "balanced"
        buyer_evidence: list[str] = []
        seller_evidence: list[str] = []
        if structure.higher_highs:
            buyer_evidence.append("higher highs")
        if structure.higher_lows:
            buyer_evidence.append("higher lows")
        if structure.lower_highs:
            seller_evidence.append("lower highs")
        if structure.lower_lows:
            seller_evidence.append("lower lows")
        if trend == "bullish":
            buyer_evidence.append(f"trend direction {trend}")
        elif trend == "bearish":
            seller_evidence.append(f"trend direction {trend}")
        if deteriorating:
            opposite = "sellers" if desired == "bullish" else "buyers"
            if opposite == "buyers":
                buyer_evidence.append(f"opposite pressure from {phase}")
            else:
                seller_evidence.append(f"opposite pressure from {phase}")
        return ControlAnalysis(
            who_is_in_control=control,
            is_control_strengthening=phase in {"expansion", "healthy_pullback"} and trend == desired,
            is_control_weakening=deteriorating,
            evidence_for_buyers=tuple(buyer_evidence),
            evidence_for_sellers=tuple(seller_evidence),
        )

    @staticmethod
    def _lifecycle_analysis(
        trend_quality: object | None,
        *,
        scalping_intelligence: object | None = None,
        market_regime: object | None = None,
        range_intelligence: object | None = None,
    ) -> LifecycleAnalysis:
        scalp_evidence = tuple(getattr(scalping_intelligence, "evidence", ()) or ())
        scalp_reversion = ()
        scalp_distribution = ()
        if scalping_intelligence is not None:
            reversion_state = str(
                getattr(scalping_intelligence, "micro_reversion_state", "") or ""
            )
            breakout_state = str(
                getattr(scalping_intelligence, "micro_breakout_state", "") or ""
            )
            if "overextended" in reversion_state or "failed" in breakout_state:
                scalp_reversion = scalp_evidence[:4]
            if "failed" in breakout_state or "rejection" in breakout_state:
                scalp_distribution = scalp_evidence[:4]
        regime_evidence: tuple[str, ...] = ()
        if market_regime is not None:
            regime_evidence = tuple(getattr(market_regime, "evidence", ()) or ())
        range_evidence: tuple[str, ...] = ()
        if range_intelligence is not None:
            range_evidence = tuple(getattr(range_intelligence, "evidence", ()) or ())
        if trend_quality is None:
            return LifecycleAnalysis(
                why_current_phase_was_selected=(
                    "No lifecycle result available; thesis uses structure, story, "
                    "and scalping micro-evidence."
                ),
                evidence_of_distribution=scalp_distribution + range_evidence[:3],
                evidence_of_reversal=scalp_reversion,
                expected_next_phase="unknown",
            )
        phase = str(getattr(trend_quality, "trend_phase", "unknown") or "unknown")
        explanation = str(getattr(trend_quality, "explanation", "") or "")
        reversal = float(getattr(trend_quality, "reversal_probability", 0.0) or 0.0)
        continuation = float(getattr(trend_quality, "continuation_probability", 0.0) or 0.0)
        expected_next = "continuation" if continuation >= reversal else "reversal_or_deeper_distribution"
        dist = (explanation,) if phase == "distribution" else ()
        dist = dist + scalp_distribution
        if market_regime is not None and getattr(market_regime, "market_regime", "") == "distribution":
            dist = dist + regime_evidence[:4]
        exhaustion = (explanation,) if phase in {"exhaustion", "distribution"} else ()
        reversal_ev = (explanation,) if phase in {"reversal_warning", "confirmed_reversal"} else ()
        reversal_ev = reversal_ev + scalp_reversion
        accumulation = (explanation,) if str(getattr(trend_quality, "regime", "")) == "accumulation" else ()
        if market_regime is not None and getattr(market_regime, "market_regime", "") == "accumulation":
            accumulation = accumulation + regime_evidence[:4]
        return LifecycleAnalysis(
            why_current_phase_was_selected=explanation[:500],
            evidence_of_accumulation=accumulation,
            evidence_of_distribution=dist,
            evidence_of_trend_exhaustion=exhaustion,
            evidence_of_reversal=reversal_ev,
            expected_next_phase=expected_next,
        )

    @staticmethod
    def _thesis_challenges(
        *,
        side: str,
        structure: MarketContext,
        market_story: object | None,
        trend_quality: object | None,
        market_regime: object | None = None,
        range_intelligence: object | None = None,
        scalping_intelligence: object | None = None,
    ) -> ThesisChallenges:
        desired = "bullish" if side == "buy" else "bearish"
        trend = (
            str(getattr(trend_quality, "trend_direction", "") or "")
            if trend_quality is not None
            else structure.trend
        )
        phase = str(getattr(trend_quality, "trend_phase", "unknown") or "unknown")
        quality = int(getattr(trend_quality, "trend_quality_score", 0) or 0)
        reversal = float(getattr(trend_quality, "reversal_probability", 0.0) or 0.0)
        wrong: list[str] = []
        opposite: list[str] = []
        reversal_not_pullback: list[str] = []
        distribution_not_cont: list[str] = []
        deterioration: list[str] = []
        if trend not in {"", "neutral", desired}:
            wrong.append(f"Lifecycle trend is {trend}, against {desired} thesis")
            opposite.append(f"Opposite side has lifecycle trend control ({trend})")
        if market_story is not None and not getattr(market_story, "story_clear", False):
            wrong.append("Market story is not clear")
        if phase in {"reversal_warning", "confirmed_reversal"}:
            reversal_not_pullback.append(f"Phase is {phase}")
            deterioration.append(f"Trend lifecycle warns {phase}")
        if phase == "distribution":
            distribution_not_cont.append("Distribution phase detected")
            deterioration.append("Distribution evidence is building")
        if quality and quality < 45:
            deterioration.append(f"Trend quality score weak at {quality}/100")
        if reversal >= 0.55:
            reversal_not_pullback.append(f"Reversal probability {reversal:.0%}")
        if scalping_intelligence is not None:
            reversion_state = str(
                getattr(scalping_intelligence, "micro_reversion_state", "") or ""
            )
            breakout_state = str(
                getattr(scalping_intelligence, "micro_breakout_state", "") or ""
            )
            momentum_state = str(
                getattr(scalping_intelligence, "micro_momentum_state", "") or ""
            )
            scalp_quality = int(
                getattr(scalping_intelligence, "scalp_quality_score", 0) or 0
            )
            if "diverging" in momentum_state or "slowing" in momentum_state:
                deterioration.append(f"Micro momentum {momentum_state}")
            if "overextended" in reversion_state:
                reversal_not_pullback.append(f"Micro reversion state {reversion_state}")
            if "failed" in breakout_state:
                distribution_not_cont.append(f"Micro breakout evidence {breakout_state}")
            if scalp_quality and scalp_quality < 45:
                wrong.append(f"Scalp quality weak at {scalp_quality}/100")
        if market_regime is not None:
            regime = str(getattr(market_regime, "market_regime", "") or "")
            strategy_bias = str(getattr(market_regime, "strategy_bias", "") or "")
            if strategy_bias == "range_logic":
                wrong.append("Regime is ranging_market — trend logic is secondary")
            if strategy_bias == "prepare_breakout":
                wrong.append("Regime is compression/breakout preparation — directional entry needs confirmation")
            if regime == "distribution" and side == "buy":
                distribution_not_cont.append("Distribution regime reduces buy quality")
            if regime == "accumulation" and side == "sell":
                reversal_not_pullback.append("Accumulation regime reduces sell quality")
            if regime in {"mature_uptrend", "mature_downtrend"}:
                deterioration.append(f"Regime is mature trend ({regime}); reduce risk")
        if range_intelligence is not None:
            location = str(getattr(range_intelligence, "price_location", "") or "")
            range_status = str(getattr(range_intelligence, "range_status", "") or "")
            if range_status in {"horizontal_range", "diagonal_range", "triangular_range"}:
                if side == "buy" and location not in {"near_support", "lower_half"}:
                    wrong.append("Range buy not near support")
                if side == "sell" and location not in {"near_resistance", "upper_half"}:
                    wrong.append("Range sell not near resistance")
        abandon = [
            "price closes through invalidation",
            "opposite side gains structure control",
            "reversal pressure rises above continuation probability",
            "distribution evidence increases while thesis has not reached TP1",
        ]
        return ThesisChallenges(
            evidence_thesis_is_wrong=tuple(wrong or ("No direct contradiction yet",)),
            evidence_opposite_side_gaining_control=tuple(opposite),
            evidence_reversal_not_retracement=tuple(reversal_not_pullback),
            evidence_distribution_not_continuation=tuple(distribution_not_cont),
            evidence_trend_quality_deteriorating=tuple(deterioration),
            abandon_thesis_if=tuple(abandon),
        )

    @staticmethod
    def _management_bias(context: MarketLifecycleContext) -> str:
        if (
            context.reversal_pressure_score >= 0.60
            or context.market_phase in {"distribution", "reversal_warning", "confirmed_reversal"}
        ):
            return "reduce_risk_tighten_or_exit"
        if context.trend_quality_score and context.trend_quality_score < 45:
            return "defensive"
        if context.continuation_probability >= 0.60 and context.trend_quality_score >= 60:
            return "normal_to_attack"
        return "normal"

    @staticmethod
    def _add_lifecycle_management(
        management: str,
        *,
        lifecycle_context: MarketLifecycleContext,
        thesis_challenges: ThesisChallenges,
    ) -> str:
        challenge = "; ".join(thesis_challenges.abandon_thesis_if[:2])
        return (
            f"{management} Lifecycle: phase={lifecycle_context.market_phase}, "
            f"quality={lifecycle_context.trend_quality_score}/100, "
            f"continuation={lifecycle_context.continuation_probability:.0%}, "
            f"reversal={lifecycle_context.reversal_pressure_score:.0%}. "
            f"If lifecycle deteriorates, reduce risk, tighten management, or exit early. "
            f"Abandon if: {challenge}."
        )

    @staticmethod
    def _add_regime_management(
        management: str,
        *,
        regime_context: ThesisMarketRegime,
    ) -> str:
        return (
            f"{management} Regime: {regime_context.current_regime} "
            f"({regime_context.regime_confidence:.0%}), "
            f"strategy={regime_context.strategy_bias}, "
            f"range_quality={regime_context.range_quality_score}/100, "
            f"breakout_risk={regime_context.breakout_risk_score}/100, "
            f"compression={regime_context.compression_probability:.0%}. "
            f"Trade only with logic appropriate to this regime."
        )

    @staticmethod
    def _resolve_direction(
        side: str,
        bias: MultiTimeframeBiasResult,
        market_story: object | None,
        story_forecast: object | None,
        structure: MarketContext,
    ) -> ThesisDirection:
        if side == "buy":
            return "bullish"
        if side == "sell":
            return "bearish"
        if bias.bias in {"bullish", "bearish"}:
            return bias.bias  # type: ignore[return-value]
        if story_forecast is not None:
            d = getattr(story_forecast, "direction", "neutral")
            if d in {"bullish", "bearish"}:
                return d  # type: ignore[return-value]
        if structure.trend in {"bullish", "bearish"}:
            return structure.trend  # type: ignore[return-value]
        if market_story is not None and getattr(market_story, "story_clear", False):
            opp = getattr(market_story, "opportunity_type", "") or ""
            if "bear" in opp or "short" in opp:
                return "bearish"
            if opp:
                return "bullish"
        return "neutral"

    @staticmethod
    def _market_story_text(
        market_story: object | None,
        trade_reasoning: TradeReasoning | None,
        harvest: HarvestDecision | None,
    ) -> str:
        if trade_reasoning is not None and trade_reasoning.trade_thesis:
            return trade_reasoning.trade_thesis[:500]
        if market_story is not None:
            expl = getattr(market_story, "current_explanation", "") or ""
            primary = getattr(market_story, "primary_story", "") or ""
            return (expl or primary)[:500]
        if harvest is not None and harvest.reason:
            return harvest.reason[:500]
        return "Opportunity identified from structure and bias alignment."

    @staticmethod
    def _adjust_confidence_with_scalping_intelligence(
        confidence: float,
        scalping_intelligence: object | None,
    ) -> float:
        if scalping_intelligence is None:
            return confidence
        quality = float(getattr(scalping_intelligence, "scalp_quality_score", 50) or 50)
        expectancy = float(getattr(scalping_intelligence, "scalp_expectancy_score", 50) or 50)
        evidence_score = ((quality + expectancy) / 2.0 - 50.0) / 100.0
        return round(max(0.05, min(0.98, confidence + evidence_score * 0.18)), 4)

    @staticmethod
    def _scalping_story_text(scalping_intelligence: object | None) -> str:
        if scalping_intelligence is None:
            return ""
        return (
            f"Scalping intelligence: {getattr(scalping_intelligence, 'suggested_action', 'unknown')} "
            f"with quality {getattr(scalping_intelligence, 'scalp_quality_score', 0)}/100, "
            f"expectancy {getattr(scalping_intelligence, 'scalp_expectancy_score', 0)}/100."
        )

    @staticmethod
    def _scalping_intelligence_dict(scalping_intelligence: object | None) -> dict[str, object]:
        if scalping_intelligence is None:
            return {}
        if hasattr(scalping_intelligence, "to_dict"):
            return scalping_intelligence.to_dict()
        return {
            "scalp_quality_score": getattr(scalping_intelligence, "scalp_quality_score", 0),
            "scalp_expectancy_score": getattr(scalping_intelligence, "scalp_expectancy_score", 0),
            "explanation": getattr(scalping_intelligence, "explanation", ""),
        }

    @staticmethod
    def _range_intelligence_dict(range_intelligence: object | None) -> dict[str, object]:
        if range_intelligence is None:
            return {}
        if hasattr(range_intelligence, "to_dict"):
            return range_intelligence.to_dict()
        return {
            "range_status": getattr(range_intelligence, "range_status", ""),
            "support_level": getattr(range_intelligence, "support_level", 0.0),
            "resistance_level": getattr(range_intelligence, "resistance_level", 0.0),
            "range_quality_score": getattr(range_intelligence, "range_quality_score", 0),
            "breakout_risk_score": getattr(range_intelligence, "breakout_risk_score", 0),
        }

    @staticmethod
    def _thesis_confidence(
        bias: MultiTimeframeBiasResult,
        market_story: object | None,
        story_forecast: object | None,
    ) -> float:
        scores = [bias.confidence]
        if market_story is not None:
            scores.append(getattr(market_story, "overall_confidence", 50.0) / 100.0)
        if story_forecast is not None:
            scores.append(getattr(story_forecast, "confidence", 50.0) / 100.0)
        return round(sum(scores) / len(scores), 4)

    @staticmethod
    def _entry_reason(
        market_story: object | None,
        story_forecast: object | None,
        harvest: HarvestDecision | None,
        setup_kind: str,
        momentum_note: str,
        *,
        scalping_intelligence: object | None = None,
    ) -> str:
        parts: list[str] = []
        if market_story is not None and getattr(market_story, "opportunity_type", None):
            parts.append(f"Story opportunity: {market_story.opportunity_type}")
        elif story_forecast is not None:
            parts.append(f"Forecast: {getattr(story_forecast, 'expected_next_move', 'continuation')}")
        elif harvest is not None and harvest.allowed:
            parts.append(f"Harvest: {harvest.reason[:120]}")
        else:
            parts.append(f"{setup_kind} setup with structural alignment")
        if momentum_note:
            parts.append(f"Momentum note: {momentum_note}")
        if scalping_intelligence is not None:
            questions = getattr(scalping_intelligence, "thesis_questions", None) or {}
            parts.append(
                "Scalping intelligence: "
                f"{getattr(scalping_intelligence, 'suggested_action', 'harvest')} "
                f"quality={getattr(scalping_intelligence, 'scalp_quality_score', 0)}/100, "
                f"expectancy={getattr(scalping_intelligence, 'scalp_expectancy_score', 0)}/100"
            )
            if isinstance(questions, dict) and questions:
                parts.append(
                    "Scalp thesis: "
                    f"why now={questions.get('why_move_immediately', '')}; "
                    f"liquidity={questions.get('where_is_liquidity', '')}; "
                    f"trapped={questions.get('who_is_trapped', '')}; "
                    f"invalidates={questions.get('what_invalidates', '')}"
                )
        return "; ".join(parts)

    def _compute_invalidation(
        self,
        *,
        side: str,
        entry_price: float,
        structure: MarketContext,
        pip_size: float,
        market_story: object | None,
    ) -> float:
        buffer = self.invalidation_buffer_pips * pip_size
        sweep_level = self._liquidity_sweep_level(structure, side, entry_price, market_story)

        if side == "buy":
            if sweep_level is not None and sweep_level < entry_price:
                return sweep_level - buffer
            if structure.swing_lows:
                lows = [s.price for s in structure.swing_lows if s.price < entry_price]
                if lows:
                    return min(lows) - buffer
                return structure.swing_lows[-1].price - buffer
            return entry_price - 20 * pip_size

        if sweep_level is not None and sweep_level > entry_price:
            return sweep_level + buffer
        if structure.swing_highs:
            highs = [s.price for s in structure.swing_highs if s.price > entry_price]
            if highs:
                return max(highs) + buffer
            return structure.swing_highs[-1].price + buffer
        return entry_price + 20 * pip_size

    @staticmethod
    def _liquidity_sweep_level(
        structure: MarketContext,
        side: str,
        entry_price: float,
        market_story: object | None,
    ) -> float | None:
        opp = ""
        if market_story is not None:
            opp = str(getattr(market_story, "opportunity_type", "") or "").lower()
        if "liquidity_sweep" not in opp and "sweep" not in opp:
            return None
        zones = structure.liquidity_zones
        if not zones:
            return None
        if side == "buy":
            below = [z.mid for z in zones if z.mid < entry_price]
            return below[-1] if below else None
        above = [z.mid for z in zones if z.mid > entry_price]
        return above[-1] if above else None

    @staticmethod
    def _stop_from_invalidation(
        *,
        side: str,
        invalidation: float,
        entry_price: float,
        pip_size: float,
    ) -> float:
        if side == "buy":
            stop = min(invalidation, entry_price - pip_size)
            return max(stop, entry_price - 50 * pip_size)
        stop = max(invalidation, entry_price + pip_size)
        return min(stop, entry_price + 50 * pip_size)

    def _compute_target_liquidity(
        self,
        *,
        side: str,
        entry_price: float,
        structure: MarketContext,
        pip_size: float,
        story_forecast: object | None,
        harvest: HarvestDecision | None,
    ) -> float:
        forecast_pips = 0.0
        if story_forecast is not None:
            lo = float(getattr(story_forecast, "expected_pip_range_min", 0) or 0)
            hi = float(getattr(story_forecast, "expected_pip_range_max", 0) or 0)
            if hi > 0:
                forecast_pips = (lo + hi) / 2.0
        elif harvest is not None and harvest.target_pips > 0:
            forecast_pips = harvest.target_pips

        if side == "buy":
            candidates: list[float] = []
            for zone in structure.resistance_zones:
                if zone.mid > entry_price:
                    candidates.append(zone.mid)
            for zone in structure.liquidity_zones:
                if zone.mid > entry_price:
                    candidates.append(zone.mid)
            if structure.swing_highs:
                highs = [s.price for s in structure.swing_highs if s.price > entry_price]
                candidates.extend(highs)
            if candidates:
                return min(candidates)
            if forecast_pips > 0:
                return entry_price + forecast_pips * pip_size
            return entry_price + max(10.0, forecast_pips or 8.0) * pip_size

        candidates = []
        for zone in structure.support_zones:
            if zone.mid < entry_price:
                candidates.append(zone.mid)
        for zone in structure.liquidity_zones:
            if zone.mid < entry_price:
                candidates.append(zone.mid)
        if structure.swing_lows:
            lows = [s.price for s in structure.swing_lows if s.price < entry_price]
            candidates.extend(lows)
        if candidates:
            return max(candidates)
        if forecast_pips > 0:
            return entry_price - forecast_pips * pip_size
        return entry_price - max(10.0, forecast_pips or 8.0) * pip_size

    def _compute_take_profits(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        target_liquidity: float,
        pip_size: float,
    ) -> tuple[float, float]:
        risk_dist = abs(entry_price - stop_loss)
        tp1_dist = risk_dist * self.tp1_r
        if side == "buy":
            tp1 = entry_price + tp1_dist
            tp2 = max(target_liquidity, entry_price + risk_dist * 2.0)
            return tp1, tp2
        tp1 = entry_price - tp1_dist
        tp2 = min(target_liquidity, entry_price - risk_dist * 2.0)
        return tp1, tp2

    @staticmethod
    def _management_plan(
        *,
        side: str,
        tp1_r: float,
        tp1_fraction: float,
        invalidation: float,
        target_liq: float,
    ) -> tuple[str, str, str]:
        management = (
            f"TP1 at {tp1_r:.2f}R — close {tp1_fraction:.0%} partial. "
            f"Move runner stop to break-even. Trail runner on M1/M5 structure or 10/20 EMA. "
            f"Full exit at liquidity target {target_liq:.5f}."
        )
        exit_wrong = f"Full exit if price closes through invalidation {invalidation:.5f}."
        exit_right = (
            f"Scale {tp1_fraction:.0%} at TP1, break-even runner, trail to {target_liq:.5f}."
        )
        return management, exit_wrong, exit_right

    def _validate_tradeability(
        self,
        *,
        side: str,
        entry_price: float,
        stop_loss: float,
        invalidation: float,
        target_liquidity: float,
        reward_risk: float,
        spread_pips: float,
        spread_limit: float,
        market_story: object | None,
        inv_pips: float,
        risk_pips: float,
    ) -> tuple[bool, str]:
        story_clear = market_story is not None and getattr(market_story, "story_clear", False)
        synthesis = getattr(market_story, "synthesis", None) if market_story else None
        genuinely_unclear = (
            market_story is not None
            and not story_clear
            and synthesis is not None
            and getattr(synthesis, "unclear_reason", "") in {"insufficient", "incoherent", "random"}
        )
        if genuinely_unclear and not story_clear:
            return False, "Market story unclear — no coherent thesis"

        if side == "buy":
            if stop_loss >= entry_price or invalidation >= entry_price:
                return False, "Invalid stop geometry for long thesis"
        else:
            if stop_loss <= entry_price or invalidation <= entry_price:
                return False, "Invalid stop geometry for short thesis"

        if inv_pips < 1.0 or risk_pips < 1.0:
            return False, "Invalidation level undefined — insufficient structural anchor"

        if spread_pips > spread_limit:
            return False, f"Spread too wide for thesis R:R ({spread_pips:.1f} > {spread_limit:.1f})"

        if reward_risk < self.min_reward_risk and not story_clear:
            return (
                False,
                f"Poor reward/risk after spread ({reward_risk:.2f} < {self.min_reward_risk})",
            )

        target_dist = abs(target_liquidity - entry_price)
        if target_dist <= 0 and not story_clear:
            return False, "Target liquidity unclear — no structural objective"

        return True, ""


class ThesisExitManager:
    """Split-exit management: TP1 partial, break-even runner, structure/EMA trail."""

    def __init__(
        self,
        *,
        tp1_fraction: float = DEFAULT_TP1_FRACTION,
        move_stop_to_breakeven: bool = True,
    ) -> None:
        self.tp1_fraction = tp1_fraction
        self.move_stop_to_breakeven = move_stop_to_breakeven

    @staticmethod
    def tp1_hit(side: str, *, high: float, low: float, tp1: float) -> bool:
        if side == "buy":
            return high >= tp1
        return low <= tp1

    @staticmethod
    def invalidation_hit(side: str, *, high: float, low: float, invalidation: float) -> bool:
        if side == "buy":
            return low <= invalidation
        return high >= invalidation

    def breakeven_stop(
        self,
        *,
        side: str,
        entry_price: float,
        pip_size: float,
        spread_pips: float = 1.0,
    ) -> float:
        buffer = spread_pips * pip_size
        if side == "buy":
            return entry_price + buffer
        return entry_price - buffer

    def trail_runner_stop(
        self,
        *,
        side: str,
        candles_close: list[float],
        current_stop: float,
        pip_size: float,
    ) -> float | None:
        """Trail using 10/20 period EMA proxy on recent closes."""
        if len(candles_close) < 20:
            return None
        ema10 = _ema(candles_close[-10:], 10)
        ema20 = _ema(candles_close[-20:], 20)
        trail = min(ema10, ema20) if side == "buy" else max(ema10, ema20)
        if side == "buy" and trail > current_stop:
            return round(trail - pip_size, 5)
        if side == "sell" and trail < current_stop:
            return round(trail + pip_size, 5)
        return None


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def write_thesis_doctrine_report(project_root, *, tracker: ThesisTracker | None = None) -> "Path":
    from datetime import datetime, timezone
    from pathlib import Path

    project_root = Path(project_root).resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stats = (tracker or get_thesis_tracker()).summary()
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Thesis Doctrine Report",
        "",
        f"**Generated:** {now}",
        "",
        "## DNA",
        "",
        KRAITOS_THESIS_DNA,
        "",
        "## Thesis quality",
        "",
        f"- Theses built: **{stats['built']}**",
        f"- Tradeable theses: **{stats['tradeable']}**",
        f"- Rejected theses: **{stats['rejected']}**",
        f"- Blocked — unclear story: **{stats['unclear_story_blocks']}**",
        f"- Blocked — invalidation: **{stats['invalidation_blocks']}**",
        f"- Blocked — target liquidity: **{stats['target_liquidity_blocks']}**",
        f"- Blocked — stop geometry: **{stats['geometry_blocks']}**",
        f"- Blocked — spread/R:R: **{stats['spread_rr_blocks']}**",
        "",
        "## Performance proxies",
        "",
        f"- Average R:R: **{stats['avg_reward_risk']}**",
        f"- Average invalidation distance (pips): **{stats['avg_invalidation_pips']}**",
        f"- TP1 hit rate: **{stats['tp1_hit_rate']:.1%}**",
        f"- Runner continuation rate: **{stats['runner_continuation_rate']:.1%}**",
        "",
        "## Top rejection reasons",
        "",
    ]
    for reason, count in stats.get("top_rejection_reasons", []):
        lines.append(f"- {reason}: {count}")
    if not stats.get("top_rejection_reasons"):
        lines.append("- (none)")
    path = logs / "thesis_doctrine_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = [
    "KRAITOS_THESIS_DNA",
    "ControlAnalysis",
    "TradeThesis",
    "LifecycleAnalysis",
    "MarketLifecycleContext",
    "PullbackAnalysis",
    "ThesisChallenges",
    "ThesisCompletionReport",
    "ThesisEvolution",
    "ThesisMarketRegime",
    "ThesisStrength",
    "Thesis",
    "ThesisTracker",
    "KraitosThesisEngine",
    "ThesisExitManager",
    "get_thesis_tracker",
    "reset_thesis_tracker",
    "write_thesis_doctrine_report",
]
