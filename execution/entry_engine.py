"""
Trade entry engine for Kraitos.

Professional trader doctrine: only enter when the market story is clear,
price action supports it, the setup is tradable, and expectancy is positive.
Entry timing only decides how to express an already-approved thesis.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from core.helpers import pip_size_for_symbol
from logs.event_logger import KraitosEventLogger
from execution.models import (
    EntryConfirmation,
    EntryContext,
    EntryDecision,
    EntryAction,
)
from execution.atr_timing_engine import should_enter
from risk.models import TradeRequest
from strategies.models import (
    MarketContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    RegimeResult,
)

HARD_CONSTRAINTS = frozenset(
    {
        "spread",
        "risk",
        "expectancy_veto",
    }
)
HARD_CONFIRMATIONS = HARD_CONSTRAINTS  # legacy alias — constraints, not confirmations

SOFT_EVIDENCE = frozenset(
    {
        "bias",
        "liquidity",
        "conviction",
        "structure",
        "market_regime",
        "range_intelligence",
        "momentum",
        "trend_quality",
        "scalping_intelligence",
        "tradability",
        "expectancy",
    }
)
SOFT_CONFIRMATIONS = SOFT_EVIDENCE  # legacy alias


@dataclass(frozen=True)
class EntryEngineConfig:
    """Thresholds for entry evaluation."""

    min_bias_confidence: float = 0.45
    min_structure_swings: int = 2
    min_tp1_r: float = 0.80
    min_expected_value_r: float = 0.05
    slippage_cost_pips: float = 0.2


class EntryEngineError(Exception):
    """Raised when entry context is invalid."""


class EntryEngine:
    """Evaluate whether a trade thesis is worth expressing as an entry."""

    def __init__(
        self,
        config: EntryEngineConfig | None = None,
        event_logger: KraitosEventLogger | None = None,
    ) -> None:
        self.config = config or EntryEngineConfig()
        self._event_logger = event_logger

    def evaluate(self, context: EntryContext) -> EntryDecision:
        """
        Evaluate entry confirmations and return an action.

        Hard gates (objective only): spread, risk sizing, catastrophic negative expectancy.
        All other modules contribute evidence and size — bias, liquidity, conviction,
        structure, momentum, and trend quality shape allocation instead of blocking.
        """
        self._validate_context(context)
        trace_id = context.trace_id
        if trace_id is None and self._event_logger is not None:
            trace_id = self._event_logger.new_trace_id()

        resolved_side = self._resolved_side(context)

        confirmations = (
            self._check_bias(
                context.bias,
                min_confidence=context.min_bias_confidence,
                context=context,
            ),
            self._check_structure(
                context.bias,
                context.structure,
                min_swings=context.min_structure_swings,
            ),
            self._check_market_regime(context),
            self._check_range_intelligence(context),
            self._check_liquidity(context.regime),
            self._check_momentum(context.bias, context.momentum),
            self._check_trend_quality(context),
            self._check_scalping_intelligence(context),
            self._check_spread(context.current_spread, context.spread_limit),
            self._check_tradability(context),
            self._check_expectancy(context),
            self._check_expectancy_veto(context),
            self._check_risk(context, trace_id=trace_id, resolved_side=resolved_side),
            self._check_conviction(context),
            self._check_timing(context),
        )

        failed_hard = [c for c in confirmations if c.name in HARD_CONFIRMATIONS and not c.passed]

        if failed_hard:
            names = ", ".join(check.name for check in failed_hard)
            details = "; ".join(check.detail for check in failed_hard)
            explanation = f"Entry rejected: failed {names}. {details}"
            logger.info(f"Entry reject {context.symbol}: {explanation}")
            self._log_rejected(context.symbol, trace_id, explanation, confirmations)
            return EntryDecision(
                action="reject",
                explanation=explanation,
                lot_size=0.0,
                confirmations=confirmations,
            )

        risk_check = next(check for check in confirmations if check.name == "risk")
        lot_size = self._extract_lot_size(risk_check.detail)
        soft_issues = [c for c in confirmations if c.name in SOFT_CONFIRMATIONS and not c.passed]
        reduction_count = len(soft_issues)
        trend_check = next(check for check in confirmations if check.name == "trend_quality")
        if "reduced-size" in trend_check.detail or "probe only" in trend_check.detail:
            reduction_count += 1
        if reduction_count:
            lot_size *= max(0.25, 1.0 - 0.25 * reduction_count)
        cognitive = getattr(context, "cognitive_decision", None)
        if cognitive is not None:
            cio_mult = float(getattr(cognitive.execution, "allocation_multiplier", 1.0))
            if cio_mult < 1.0:
                lot_size *= max(0.05, cio_mult)
        timing_check = next(check for check in confirmations if check.name == "timing")

        if not timing_check.passed:
            explanation = f"Entry waiting: ATR timing — {timing_check.detail}"
            logger.info(f"Entry wait {context.symbol}: {explanation}")
            self._log_decision(
                context.symbol,
                trace_id,
                "wait",
                explanation,
                confirmations,
                lot_size=0.0,
            )
            return EntryDecision(
                action="wait",
                explanation=explanation,
                lot_size=0.0,
                confirmations=confirmations,
            )

        if resolved_side == "buy" or context.bias.bias == "bullish":
            action: EntryAction = "enter_buy"
            explanation = (
                f"Enter BUY: trader thesis approved with lot_size {lot_size:.2f}. "
                f"Bias {context.bias.bias} ({context.bias.confidence:.2f}), "
                f"structure {context.structure.trend}, momentum {context.momentum.action}."
            )
        elif resolved_side == "sell" or context.bias.bias == "bearish":
            action = "enter_sell"
            explanation = (
                f"Enter SELL: trader thesis approved with lot_size {lot_size:.2f}. "
                f"Bias {context.bias.bias} ({context.bias.confidence:.2f}), "
                f"structure {context.structure.trend}, momentum {context.momentum.action}."
            )
        elif resolved_side in {"buy", "sell"}:
            action = "enter_buy" if resolved_side == "buy" else "enter_sell"
            explanation = (
                f"Enter {action.replace('enter_', '').upper()}: story-resolved side with "
                f"lot_size {lot_size:.2f}. Bias {context.bias.bias} "
                f"({context.bias.confidence:.2f}) is advisory."
            )
        else:
            explanation = "Entry rejected: directional bias is not actionable"
            self._log_rejected(context.symbol, trace_id, explanation, confirmations)
            return EntryDecision(
                action="reject",
                explanation=explanation,
                lot_size=0.0,
                confirmations=confirmations,
            )

        if soft_issues:
            notes = "; ".join(check.detail for check in soft_issues)
            explanation += f" Probe constraints: {notes}."

        logger.info(f"Entry {action} {context.symbol}: {explanation}")
        self._log_decision(
            context.symbol,
            trace_id,
            action,
            explanation,
            confirmations,
            lot_size=lot_size,
        )
        return EntryDecision(
            action=action,
            explanation=explanation,
            lot_size=lot_size,
            confirmations=confirmations,
        )

    def _validate_context(self, context: EntryContext) -> None:
        if not context.symbol.strip():
            raise EntryEngineError("symbol is required")
        if context.entry_price <= 0:
            raise EntryEngineError("entry_price must be positive")
        if context.stop_loss <= 0:
            raise EntryEngineError("stop_loss must be positive")
        if context.spread_limit <= 0:
            raise EntryEngineError("spread_limit must be positive")

    @staticmethod
    def _resolved_side(context: EntryContext) -> str | None:
        if context.resolved_side in {"buy", "sell"}:
            return context.resolved_side
        if context.bias.bias == "bullish":
            return "buy"
        if context.bias.bias == "bearish":
            return "sell"
        return None

    def _check_bias(
        self,
        bias: MultiTimeframeBiasResult,
        *,
        min_confidence: float | None = None,
        context: EntryContext | None = None,
    ) -> EntryConfirmation:
        threshold = (
            min_confidence
            if min_confidence is not None
            else self.config.min_bias_confidence
        )
        resolved = self._resolved_side(context) if context is not None else None
        if context is not None and context.patience_ready and resolved in {"buy", "sell"}:
            return EntryConfirmation(
                name="bias",
                passed=True,
                detail=(
                    f"Patience-confirmed {resolved} — MTF bias {bias.bias} "
                    f"({bias.confidence:.2f}) is advisory"
                ),
            )
        if resolved in {"buy", "sell"}:
            required = "bullish" if resolved == "buy" else "bearish"
            structure_ok = (
                context is not None
                and (
                    context.structure.trend == required
                    or (required == "bullish" and context.structure.higher_highs)
                    or (required == "bearish" and context.structure.lower_lows)
                )
            )
            if bias.bias == required and bias.confidence >= threshold:
                passed = True
            elif bias.bias == "neutral" and structure_ok:
                passed = True
            else:
                passed = False
            detail = (
                f"Story-resolved {resolved} with structure {context.structure.trend if context else 'n/a'}"
                if passed
                else f"Bias unavailable or weak: {bias.bias} ({bias.confidence:.2f})"
            )
            return EntryConfirmation(name="bias", passed=passed, detail=detail)

        passed = (
            bias.bias in {"bullish", "bearish"}
            and bias.confidence >= threshold
        )
        detail = (
            f"Multi-timeframe bias {bias.bias} (confidence {bias.confidence:.2f})"
            if passed
            else f"Bias unavailable or weak: {bias.bias} ({bias.confidence:.2f})"
        )
        return EntryConfirmation(name="bias", passed=passed, detail=detail)

    def _check_structure(
        self,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        *,
        min_swings: int | None = None,
    ) -> EntryConfirmation:
        swing_threshold = (
            min_swings if min_swings is not None else self.config.min_structure_swings
        )
        if len(structure.swing_highs) < swing_threshold:
            return EntryConfirmation(
                name="structure",
                passed=False,
                detail="Structure note: insufficient swing highs",
            )
        if len(structure.swing_lows) < swing_threshold:
            return EntryConfirmation(
                name="structure",
                passed=False,
                detail="Structure note: insufficient swing lows",
            )

        if bias.bias == "bullish":
            passed = structure.trend == "bullish" or (
                structure.higher_highs and structure.higher_lows
            )
            detail = (
                f"Structure confirms bullish trend ({structure.trend})"
                if passed
                else "Structure note: does not fully confirm bullish bias"
            )
        elif bias.bias == "bearish":
            passed = structure.trend == "bearish" or (
                structure.lower_highs and structure.lower_lows
            )
            detail = (
                f"Structure confirms bearish trend ({structure.trend})"
                if passed
                else "Structure note: does not fully confirm bearish bias"
            )
        else:
            passed = False
            detail = "Structure note: no directional bias to confirm"

        return EntryConfirmation(name="structure", passed=passed, detail=detail)

    def _check_market_regime(self, context: EntryContext) -> EntryConfirmation:
        regime = context.market_regime_intelligence
        if regime is None:
            return EntryConfirmation(
                name="market_regime",
                passed=True,
                detail="Market regime intelligence unavailable — neutral evidence",
            )
        current = str(getattr(regime, "market_regime", "unclear") or "unclear")
        strategy = str(getattr(regime, "strategy_bias", "wait_for_clarity") or "wait_for_clarity")
        confidence = float(getattr(regime, "regime_confidence", 0.0) or 0.0)
        side = "buy" if context.bias.bias == "bullish" else "sell"
        wrong_side = (
            side == "buy" and current in {"strong_downtrend", "healthy_downtrend", "mature_downtrend", "distribution"}
        ) or (
            side == "sell" and current in {"strong_uptrend", "healthy_uptrend", "mature_uptrend", "accumulation"}
        )
        if wrong_side and confidence >= 0.55:
            return EntryConfirmation(
                name="market_regime",
                passed=False,
                detail=f"Regime mismatch: {side} thesis inside {current} ({strategy})",
            )
        if strategy == "range_logic" and context.structure.trend in {"bullish", "bearish"}:
            return EntryConfirmation(
                name="market_regime",
                passed=True,
                detail=f"Regime is ranging_market — trend logic secondary ({confidence:.0%})",
            )
        return EntryConfirmation(
            name="market_regime",
            passed=True,
            detail=f"Regime {current} supports strategy bias {strategy} ({confidence:.0%})",
        )

    def _check_range_intelligence(self, context: EntryContext) -> EntryConfirmation:
        range_info = context.range_intelligence
        if range_info is None:
            return EntryConfirmation(
                name="range_intelligence",
                passed=True,
                detail="Range intelligence unavailable — neutral evidence",
            )
        status = str(getattr(range_info, "range_status", "unclear") or "unclear")
        location = str(getattr(range_info, "price_location", "") or "")
        quality = int(getattr(range_info, "range_quality_score", 0) or 0)
        breakout_risk = int(getattr(range_info, "breakout_risk_score", 0) or 0)
        side = "buy" if context.bias.bias == "bullish" else "sell"
        if status in {"horizontal_range", "diagonal_range", "triangular_range"} and quality >= 55:
            buy_ok = side == "buy" and location in {"near_support", "lower_half"}
            sell_ok = side == "sell" and location in {"near_resistance", "upper_half"}
            if not (buy_ok or sell_ok):
                return EntryConfirmation(
                    name="range_intelligence",
                    passed=False,
                    detail=(
                        f"Range location weak for {side}: {location}, "
                        f"quality {quality}/100, breakout risk {breakout_risk}/100"
                    ),
                )
        return EntryConfirmation(
            name="range_intelligence",
            passed=True,
            detail=(
                f"Range {status}: location {location}, quality {quality}/100, "
                f"breakout risk {breakout_risk}/100"
            ),
        )

    def _check_liquidity(self, regime: RegimeResult) -> EntryConfirmation:
        passed = regime.regime not in {"low_liquidity", "news_risk"}
        detail = (
            f"Liquidity acceptable (regime {regime.regime})"
            if passed
            else f"Liquidity poor (regime {regime.regime})"
        )
        return EntryConfirmation(name="liquidity", passed=passed, detail=detail)

    def _check_momentum(
        self,
        bias: MultiTimeframeBiasResult,
        momentum: MicroScalpSignal,
    ) -> EntryConfirmation:
        if momentum.action == "no_trade":
            passed = False
            detail = f"Price action rejected: {momentum.reason}"
        elif bias.bias == "bullish" and momentum.action == "buy":
            passed = True
            detail = f"Momentum confirms buy conviction ({momentum.reason})"
        elif bias.bias == "bearish" and momentum.action == "sell":
            passed = True
            detail = f"Momentum confirms sell conviction ({momentum.reason})"
        else:
            passed = False
            detail = (
                f"Price action conflicts with story (bias={bias.bias}, "
                f"momentum={momentum.action})"
            )
        return EntryConfirmation(name="momentum", passed=passed, detail=detail)

    def _check_trend_quality(self, context: EntryContext) -> EntryConfirmation:
        trend_quality = context.trend_quality
        if trend_quality is None:
            return EntryConfirmation(
                name="trend_quality",
                passed=True,
                detail="Trend quality not evaluated — legacy path",
            )

        side = "buy" if context.bias.bias == "bullish" else "sell"
        direction = getattr(trend_quality, "trend_direction", "neutral")
        phase = getattr(trend_quality, "trend_phase", "reversal_warning")
        continuation = float(getattr(trend_quality, "continuation_probability", 0.0) or 0.0)
        reversal = float(getattr(trend_quality, "reversal_probability", 0.0) or 0.0)
        score = int(getattr(trend_quality, "trend_quality_score", 0) or 0)

        if phase == "confirmed_reversal":
            reversal_side = "sell" if direction == "bearish" else "buy" if direction == "bullish" else "none"
            passed = side == reversal_side and reversal >= continuation
            detail = (
                f"Confirmed reversal supports new {side} bias "
                f"(score {score}, continuation {continuation:.0%}, reversal {reversal:.0%})"
                if passed
                else (
                    f"Confirmed reversal blocks old {side} bias "
                    f"(trend {direction}, continuation {continuation:.0%}, reversal {reversal:.0%})"
                )
            )
            return EntryConfirmation(name="trend_quality", passed=passed, detail=detail)

        old_trend_buy_block = side == "buy" and direction == "bullish"
        old_trend_sell_block = side == "sell" and direction == "bearish"
        dangerous_old_trend = (
            phase in {"exhaustion", "distribution", "reversal_warning"}
            and (old_trend_buy_block or old_trend_sell_block)
        )
        if dangerous_old_trend and reversal >= continuation:
            return EntryConfirmation(
                name="trend_quality",
                passed=False,
                detail=(
                    f"Trend quality blocks aggressive {side}: {phase}, "
                    f"continuation {continuation:.0%} <= reversal {reversal:.0%}"
                ),
            )

        if phase in {"exhaustion", "distribution"}:
            return EntryConfirmation(
                name="trend_quality",
                passed=True,
                detail=(
                    f"Trend quality reduced-size/probe only: {phase}, score {score}, "
                    f"continuation {continuation:.0%}, reversal {reversal:.0%}"
                ),
            )

        if continuation <= reversal:
            return EntryConfirmation(
                name="trend_quality",
                passed=False,
                detail=(
                    f"Trend quality rejected: continuation {continuation:.0%} "
                    f"not stronger than reversal {reversal:.0%}"
                ),
            )

        return EntryConfirmation(
            name="trend_quality",
            passed=True,
            detail=(
                f"Trend quality supports {side}: {phase}, score {score}, "
                f"continuation {continuation:.0%}, reversal {reversal:.0%}"
            ),
        )

    def _check_scalping_intelligence(self, context: EntryContext) -> EntryConfirmation:
        scalp = context.scalping_intelligence
        if scalp is None:
            return EntryConfirmation(
                name="scalping_intelligence",
                passed=True,
                detail="Scalping intelligence unavailable — neutral evidence",
            )
        quality = int(getattr(scalp, "scalp_quality_score", 50) or 50)
        expectancy = int(getattr(scalp, "scalp_expectancy_score", 50) or 50)
        action = str(getattr(scalp, "suggested_action", "harvest") or "harvest")
        explanation = str(getattr(scalp, "explanation", "") or "")
        if quality < 40 or expectancy < 35:
            return EntryConfirmation(
                name="scalping_intelligence",
                passed=False,
                detail=(
                    f"Scalping intelligence weak: quality {quality}/100, "
                    f"expectancy {expectancy}/100 ({action}). {explanation[:180]}"
                ),
            )
        return EntryConfirmation(
            name="scalping_intelligence",
            passed=True,
            detail=(
                f"Scalping intelligence {action}: quality {quality}/100, "
                f"expectancy {expectancy}/100"
            ),
        )

    def _check_spread(self, current_spread: float, spread_limit: float) -> EntryConfirmation:
        passed = current_spread <= spread_limit
        detail = (
            f"Spread approved ({current_spread:.2f} <= {spread_limit:.2f})"
            if passed
            else f"Spread too wide ({current_spread:.2f} > {spread_limit:.2f})"
        )
        return EntryConfirmation(name="spread", passed=passed, detail=detail)

    def _check_tradability(self, context: EntryContext) -> EntryConfirmation:
        stop_pips = self._stop_distance_pips(context)
        target_pips = self._target_distance_pips(context)
        if stop_pips <= 0:
            return EntryConfirmation(
                name="tradability",
                passed=False,
                detail="Stop loss is not logically placed beyond entry",
            )
        if target_pips <= 0:
            return EntryConfirmation(
                name="tradability",
                passed=False,
                detail="No measurable room to TP1",
            )

        tp1_r = target_pips / stop_pips
        spread_drag = context.current_spread / max(target_pips, 0.01)
        passed = tp1_r >= self.config.min_tp1_r and spread_drag <= 0.35
        exec_note = ""
        exec_q = context.execution_quality
        if exec_q is not None:
            trad = getattr(exec_q, "tradability", None)
            entry_q = getattr(exec_q, "entry", None)
            if trad is not None and entry_q is not None:
                exec_note = (
                    f" | exec {getattr(entry_q, 'entry_style', 'wait')} "
                    f"timing {getattr(entry_q, 'timing_score', 0)}/100"
                )
                if getattr(trad, "executable", False) and getattr(
                    entry_q, "entry_allowed", False
                ):
                    passed = passed or tp1_r >= self.config.min_tp1_r * 0.75
        detail = (
            f"Tradable setup: TP1 {tp1_r:.2f}R, spread drag {spread_drag:.1%}{exec_note}"
            if passed
            else (
                f"Setup not tradable: TP1 {tp1_r:.2f}R, "
                f"spread drag {spread_drag:.1%}{exec_note}"
            )
        )
        return EntryConfirmation(name="tradability", passed=passed, detail=detail)

    def _check_expectancy(self, context: EntryContext) -> EntryConfirmation:
        stop_pips = self._stop_distance_pips(context)
        target_pips = self._target_distance_pips(context)
        if stop_pips <= 0 or target_pips <= 0:
            return EntryConfirmation(
                name="expectancy",
                passed=False,
                detail="Expectancy rejected: missing valid stop or TP1 distance",
            )

        expected_win_r = target_pips / stop_pips
        expected_loss_r = 1.0
        probability_of_win = self._estimate_win_probability(context)
        probability_of_loss = 1.0 - probability_of_win
        cost_r = (context.current_spread + self.config.slippage_cost_pips) / stop_pips
        expected_value = (
            probability_of_win * expected_win_r
            - probability_of_loss * expected_loss_r
            - cost_r
        )
        passed = expected_value > self.config.min_expected_value_r
        detail = (
            f"Positive expectancy {expected_value:.2f}R "
            f"(p_win {probability_of_win:.0%}, win {expected_win_r:.2f}R, cost {cost_r:.2f}R)"
            if passed
            else (
                f"Expectancy rejected {expected_value:.2f}R "
                f"(p_win {probability_of_win:.0%}, win {expected_win_r:.2f}R, cost {cost_r:.2f}R)"
            )
        )
        return EntryConfirmation(name="expectancy", passed=passed, detail=detail)

    def _check_expectancy_veto(self, context: EntryContext) -> EntryConfirmation:
        """Hard veto only for objectively poor risk-reward after costs."""
        stop_pips = self._stop_distance_pips(context)
        target_pips = self._target_distance_pips(context)
        if stop_pips <= 0 or target_pips <= 0:
            return EntryConfirmation(
                name="expectancy_veto",
                passed=True,
                detail="Expectancy veto not applicable — geometry unresolved",
            )
        expected_win_r = target_pips / stop_pips
        cost_r = (context.current_spread + self.config.slippage_cost_pips) / stop_pips
        probability_of_win = self._estimate_win_probability(context)
        expected_value = (
            probability_of_win * expected_win_r
            - (1.0 - probability_of_win) * 1.0
            - cost_r
        )
        poor_rr = expected_win_r < 0.50
        deeply_negative = expected_value < -0.35
        passed = not (poor_rr and deeply_negative)
        detail = (
            "Risk-reward acceptable for probe sizing"
            if passed
            else (
                f"Hard veto: poor R:R ({expected_win_r:.2f}R) with negative expectancy "
                f"({expected_value:.2f}R)"
            )
        )
        return EntryConfirmation(name="expectancy_veto", passed=passed, detail=detail)

    def _check_risk(
        self,
        context: EntryContext,
        *,
        trace_id: str | None = None,
        resolved_side: str | None = None,
    ) -> EntryConfirmation:
        side = resolved_side or self._resolved_side(context)
        if side not in {"buy", "sell"}:
            return EntryConfirmation(
                name="risk",
                passed=False,
                detail="Risk rejected: no resolved trade side",
            )
        request = TradeRequest(
            symbol=context.symbol,
            side=side,  # type: ignore[arg-type]
            entry_price=context.entry_price,
            stop_loss=context.stop_loss,
        )
        decision = context.risk_manager.evaluate(
            request,
            context.portfolio,
            trace_id=trace_id,
        )
        detail = (
            f"Risk approved with lot_size {decision.lot_size:.2f}"
            if decision.approved
            else f"Risk rejected: {decision.reason}"
        )
        return EntryConfirmation(name="risk", passed=decision.approved, detail=detail)

    def _check_conviction(self, context: EntryContext) -> EntryConfirmation:
        conviction = context.conviction
        if conviction is None:
            return EntryConfirmation(
                name="conviction",
                passed=True,
                detail="conviction not evaluated — legacy path",
            )
        if (
            getattr(conviction, "participation_mode", None) == "avoid"
            and not getattr(conviction, "anti_paralysis_override", False)
        ):
            return EntryConfirmation(
                name="conviction",
                passed=False,
                detail=(
                    f"conviction {conviction.conviction_score:.0f}/100 — watch only "
                    f"({conviction.story})"
                ),
            )
        return EntryConfirmation(
            name="conviction",
            passed=True,
            detail=(
                f"{conviction.participation_mode} mode "
                f"({conviction.conviction_score:.0f}/100): {conviction.story}"
            ),
        )

    def _check_timing(self, context: EntryContext) -> EntryConfirmation:
        if context.patience_ready:
            detail = context.patience_explanation or "Patience engine confirmed professional entry location"
            return EntryConfirmation(name="timing", passed=True, detail=detail)

        side = self._resolved_side(context) or (
            "buy" if context.bias.bias == "bullish" else "sell"
        )
        if side not in {"buy", "sell"}:
            return EntryConfirmation(
                name="timing",
                passed=False,
                detail="no resolved side for timing",
            )

        if context.conviction is not None:
            from strategies.conviction_engine import ConvictionEngine

            allowed, detail = ConvictionEngine.entry_timing_allowed(
                context.conviction,
                side=side,
                candles=context.candles,
            )
            return EntryConfirmation(
                name="timing",
                passed=allowed,
                detail=detail,
            )

        timing = should_enter(side=side, candles=context.candles)
        if timing.allowed:
            detail = f"ATR entry timing OK ({timing.trigger}): {timing.reason}"
            return EntryConfirmation(name="timing", passed=True, detail=detail)

        return EntryConfirmation(
            name="timing",
            passed=False,
            detail=timing.reason,
        )

    @staticmethod
    def _stop_distance_pips(context: EntryContext) -> float:
        pip_size = pip_size_for_symbol(context.symbol)
        if pip_size <= 0:
            return 0.0
        return abs(context.entry_price - context.stop_loss) / pip_size

    @staticmethod
    def _target_distance_pips(context: EntryContext) -> float:
        if context.expected_target_pips is not None:
            return max(float(context.expected_target_pips), 0.0)
        return max(float(getattr(context.momentum, "target_pips", 0.0) or 0.0), 0.0)

    def _estimate_win_probability(self, context: EntryContext) -> float:
        probability = 0.40
        probability += max(context.bias.confidence, 0.0) * 0.18
        probability += max(context.regime.confidence, 0.0) * 0.10

        structure = context.structure
        if context.bias.bias == "bullish" and (
            structure.trend == "bullish" or (structure.higher_highs and structure.higher_lows)
        ):
            probability += 0.08
        elif context.bias.bias == "bearish" and (
            structure.trend == "bearish" or (structure.lower_highs and structure.lower_lows)
        ):
            probability += 0.08

        if (
            context.bias.bias == "bullish"
            and context.momentum.action == "buy"
            or context.bias.bias == "bearish"
            and context.momentum.action == "sell"
        ):
            probability += 0.07

        if context.conviction is not None:
            score = float(getattr(context.conviction, "conviction_score", 0.0) or 0.0)
            probability += min(max(score, 0.0), 100.0) / 100.0 * 0.10

        return min(max(probability, 0.35), 0.72)

    def _log_rejected(
        self,
        symbol: str,
        trace_id: str | None,
        explanation: str,
        confirmations: tuple[EntryConfirmation, ...],
    ) -> None:
        if self._event_logger is None or trace_id is None:
            return
        self._event_logger.rejected_trade(
            explanation,
            symbol=symbol,
            trace_id=trace_id,
            reason=explanation,
            data={"confirmations": self._confirmation_data(confirmations)},
        )

    def _log_decision(
        self,
        symbol: str,
        trace_id: str | None,
        action: str,
        explanation: str,
        confirmations: tuple[EntryConfirmation, ...],
        *,
        lot_size: float = 0.0,
    ) -> None:
        if self._event_logger is None or trace_id is None:
            return
        self._event_logger.trade_decision(
            explanation,
            symbol=symbol,
            trace_id=trace_id,
            action=action,
            data={
                "lot_size": lot_size,
                "confirmations": self._confirmation_data(confirmations),
            },
        )

    @staticmethod
    def _confirmation_data(confirmations: tuple[EntryConfirmation, ...]) -> list[dict[str, object]]:
        return [
            {"name": check.name, "passed": check.passed, "detail": check.detail}
            for check in confirmations
        ]

    @staticmethod
    def _extract_lot_size(detail: str) -> float:
        marker = "lot_size "
        if marker not in detail:
            return 0.0
        try:
            return float(detail.split(marker, 1)[1].split()[0])
        except (IndexError, ValueError):
            return 0.0
