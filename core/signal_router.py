"""Route pipeline outputs into final TRADE / NO TRADE signals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from config.settings import SignalDecision, TradeMode
from core.expectancy_gates import MIN_EXPECTED_R, participation_unlock, story_actionable
from core.pipeline_models import PipelineResult
from execution.models import EntryDecision
from risk.models import RiskDecision

TradeDirection = Literal["buy", "sell", "none"]


@dataclass(frozen=True)
class TradeSignal:
    """Final integrated signal emitted by the Kraitos pipeline."""

    symbol: str
    decision: SignalDecision
    direction: TradeDirection
    confidence: float
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_pct: float
    lot_size: float
    reason: str
    mode: TradeMode
    trace_id: str
    executed: bool = False
    execution_id: str | None = None
    partial_tp: float | None = None
    runner_tp: float | None = None
    partial_fraction: float = 0.5
    move_stop_to_breakeven: bool = False
    enable_early_exit: bool = True
    stagnation_bars_limit: int = 12
    min_progress_r: float = 0.20
    spread_limit_pips: float = 3.0
    runner_allowed: bool = True
    conviction_score: float = 0.0
    invalidation_level: float = 0.0
    trade_theme: str = ""
    theme_confidence: float = 0.0
    thesis_snapshot: str = ""
    entry_stage: str = ""
    scout_or_commit: str = ""
    setup_kind: str = ""
    acceptance_score_at_entry: int = 50
    rejection_score_at_entry: int = 50
    momentum_clarity_at_entry: str = ""
    location_quality_at_entry: int = 0
    timing_quality_at_entry: int = 0
    scratch_eligible: bool = False
    entry_type: str = ""
    story_direction: str = ""
    story_confidence: float = 0.0
    story_narrative: str = ""
    cio_confidence: float = 0.0
    cio_allocation: float = 0.0
    cio_mode: str = ""
    cio_summary: str = ""
    cognitive_snapshot: str = ""
    picture_clarity: str = ""
    picture_confidence: float = 0.0
    selected_strategy: str = ""
    strategy_fit: float = 0.0
    narrator_story: str = ""
    storyteller_snapshot: str = ""
    mind_state: str = ""
    market_mind_snapshot: str = ""
    reality_model: str = ""
    convergence_score: float = 0.0
    reality_narrative: str = ""
    reality_snapshot: str = ""
    world_models_active: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the signal for CLI JSON output."""
        return asdict(self)


class SignalRouter:
    """Combine pipeline stage outputs into trade decisions — never drop valid candidates."""

    def route_all(
        self,
        results: list[PipelineResult],
        *,
        risk_pct: float,
    ) -> list[TradeSignal]:
        """Map every pipeline result to a signal without rank-and-drop."""
        return [self.route(result, risk_pct=risk_pct) for result in results]

    def route(self, result: PipelineResult, *, risk_pct: float) -> TradeSignal:
        """Map a completed pipeline result to a final trade signal."""
        mode = self._resolve_mode(result)
        direction = self._resolve_direction(result.entry)
        confidence = self._resolve_confidence(result)
        reason = self._resolve_reason(result)

        partial_tp, runner_tp, partial_fraction, move_be = self._resolve_exit_plan(result)
        plan = getattr(result, "individual_trade_plan", None)
        enable_early = False
        spread_lim = result.spread_limit
        runner_allowed = True
        if plan is not None and getattr(plan, "entry_allowed", False):
            enable_early = True
            runner_allowed = plan.runner_allowed
            if not runner_allowed:
                runner_tp = partial_tp
        conviction = getattr(result, "conviction_assessment", None)
        invalidation = 0.0
        conviction_score = 0.0
        if getattr(result, "thesis", None) is not None:
            invalidation = float(getattr(result.thesis, "invalidation_level", 0.0) or 0.0)
        if conviction is not None:
            conviction_score = float(getattr(conviction, "conviction_score", 0.0))
        sizing = getattr(result, "conviction_sizing", None)
        if sizing is not None:
            conviction_score = max(
                conviction_score,
                float(getattr(sizing, "score", 0.0) or 0.0),
            )
        story_meta = self._resolve_story_metadata(result)
        trade_theme, theme_confidence = self._resolve_theme(result)
        thesis_snapshot = self._resolve_thesis_snapshot(result)
        cognitive_meta = self._resolve_cognitive_metadata(result)
        storyteller_meta = self._resolve_storyteller_metadata(result)
        mind_meta = self._resolve_market_mind_metadata(result)
        reality_meta = self._resolve_reality_metadata(result)
        scout_meta = self._resolve_scout_metadata(result)
        journal_meta = {**cognitive_meta, **storyteller_meta, **mind_meta, **reality_meta}
        if self._is_trade(result):
            return TradeSignal(
                symbol=result.symbol,
                decision="TRADE",
                direction=direction,
                confidence=confidence,
                entry=result.entry_price,
                stop_loss=result.stop_loss,
                take_profit=result.take_profit,
                risk_pct=risk_pct,
                lot_size=result.risk.lot_size,
                reason=reason,
                mode=mode,
                trace_id=result.trace_id,
                partial_tp=partial_tp,
                runner_tp=runner_tp,
                partial_fraction=partial_fraction,
                move_stop_to_breakeven=move_be,
                enable_early_exit=enable_early,
                spread_limit_pips=spread_lim,
                runner_allowed=runner_allowed,
                conviction_score=conviction_score,
                invalidation_level=invalidation,
                trade_theme=trade_theme,
                theme_confidence=theme_confidence,
                thesis_snapshot=thesis_snapshot,
                **scout_meta,
                **story_meta,
                **journal_meta,
            )

        return TradeSignal(
            symbol=result.symbol,
            decision="NO_TRADE",
            direction="none",
            confidence=confidence,
            entry=result.entry_price,
            stop_loss=result.stop_loss,
            take_profit=result.take_profit,
            risk_pct=risk_pct,
            lot_size=0.0,
            reason=reason,
            mode=mode,
            trace_id=result.trace_id,
            trade_theme=trade_theme,
            theme_confidence=theme_confidence,
            thesis_snapshot=thesis_snapshot,
            **journal_meta,
        )

    @staticmethod
    def _resolve_storyteller_metadata(result: PipelineResult) -> dict[str, object]:
        from intelligence.picture_reports import storyteller_journal_fields

        decision = getattr(result, "storyteller_decision", None)
        return storyteller_journal_fields(decision)

    @staticmethod
    def _resolve_market_mind_metadata(result: PipelineResult) -> dict[str, object]:
        from intelligence.market_mind_reports import market_mind_journal_fields

        decision = getattr(result, "market_mind_decision", None)
        return market_mind_journal_fields(decision)

    @staticmethod
    def _resolve_reality_metadata(result: PipelineResult) -> dict[str, object]:
        from reality.reality_reports import reality_journal_fields

        decision = getattr(result, "reality_decision", None)
        return reality_journal_fields(decision)

    @staticmethod
    def _resolve_cognitive_metadata(result: PipelineResult) -> dict[str, object]:
        from council.cognitive_reports import cognitive_journal_fields

        decision = getattr(result, "cognitive_decision", None)
        return cognitive_journal_fields(decision)

    @staticmethod
    def _is_trade(result: PipelineResult) -> bool:
        if result.entry is None:
            return False
        if result.entry.action not in {"enter_buy", "enter_sell"}:
            return False
        harvest_ok = result.harvest.allowed
        scalp_ok = (
            result.micro_scalp is not None
            and result.micro_scalp.action in {"buy", "sell"}
            and result.strategy_selection is not None
            and result.strategy_selection.allow_micro_scalp
        )
        expected_r = None
        thesis = getattr(result, "thesis", None)
        if thesis is not None:
            expected_r = getattr(thesis, "reward_risk_ratio", None)
        if not participation_unlock(
            harvest_allowed=harvest_ok,
            brain_story=getattr(result, "brain_story", None),
            legacy_story=result.market_story,
            harvest_score_band=(
                result.harvest_score.band if result.harvest_score is not None else None
            ),
            expected_r=expected_r,
            scalp_ok=scalp_ok,
        ):
            return False
        plan = getattr(result, "individual_trade_plan", None)
        if plan is not None and not getattr(plan, "entry_allowed", True):
            if not story_actionable(
                getattr(result, "brain_story", None),
                result.market_story,
            ):
                return False
        if not result.risk.approved:
            return False
        if result.risk.lot_size <= 0:
            return False
        return True

    @staticmethod
    def _resolve_direction(entry: EntryDecision | None) -> TradeDirection:
        if entry is None:
            return "none"
        if entry.action == "enter_buy":
            return "buy"
        if entry.action == "enter_sell":
            return "sell"
        return "none"

    @staticmethod
    def _resolve_mode(result: PipelineResult) -> TradeMode:
        if result.strategy_selection is not None:
            if result.strategy_selection.selected_strategy == "no_trade":
                return "normal"
            return result.strategy_selection.trade_mode
        scalp_action = result.micro_scalp.action
        if scalp_action in {"buy", "sell"}:
            return "scalp"
        if result.harvest.mode in {"conditional", "full"}:
            return "harvest"
        return "normal"

    @staticmethod
    def _resolve_confidence(result: PipelineResult) -> float:
        scores = [
            result.bias.confidence,
            result.regime.confidence,
        ]
        if result.market_story is not None:
            scores.append(result.market_story.overall_confidence / 100.0)
        brain_story = getattr(result, "brain_story", None)
        if brain_story is not None:
            scores.append(float(getattr(brain_story, "confidence", 0.0) or 0.0) / 100.0)
        sizing = getattr(result, "conviction_sizing", None)
        if sizing is not None:
            scores.append(float(getattr(sizing, "score", 0.0) or 0.0) / 100.0)
        thesis = getattr(result, "thesis", None)
        if thesis is not None:
            rr = float(getattr(thesis, "reward_risk_ratio", 0.0) or 0.0)
            if rr > 0:
                scores.append(min(1.0, rr / 2.0))
        if result.story_forecast is not None:
            scores.append(result.story_forecast.confidence / 100.0)
        elif result.harvest_score is not None:
            scores.append(result.harvest_score.score / 100.0)
        if result.entry is not None and result.entry.action in {"enter_buy", "enter_sell"}:
            passed = sum(1 for check in result.entry.confirmations if check.passed)
            total = max(len(result.entry.confirmations), 1)
            scores.append(0.35 * (passed / total))
        return round(sum(scores) / max(len(scores), 1), 4)

    @staticmethod
    def _resolve_exit_plan(
        result: PipelineResult,
    ) -> tuple[float | None, float | None, float, bool]:
        thesis = getattr(result, "thesis", None)
        plan = getattr(result, "individual_trade_plan", None)
        if plan is not None and getattr(plan, "entry_allowed", False):
            frac = 0.50 if plan.runner_allowed else 1.0
            return (
                plan.take_profit_1,
                plan.take_profit_2 if plan.runner_allowed else plan.take_profit_1,
                frac,
                plan.runner_allowed,
            )
        if thesis is not None and thesis.is_tradeable and result.entry_price is not None:
            return (
                thesis.take_profit_1,
                thesis.take_profit_2,
                0.50,
                True,
            )
        pip = result.dynamic_pip_target
        if pip is None or not pip.allow_partial_exit or result.entry_price is None:
            return None, None, 0.5, False
        from core.helpers import pip_size_for_symbol

        pip_size = pip_size_for_symbol(result.symbol)
        side = "buy"
        if result.entry is not None and result.entry.action == "enter_sell":
            side = "sell"
        elif result.bias is not None and result.bias.bias == "bearish":
            side = "sell"

        partial_pips = pip.partial_tp_pips
        runner_pips = pip.target_pips
        if side == "buy":
            partial_tp = result.entry_price + partial_pips * pip_size
            runner_tp = result.entry_price + runner_pips * pip_size
        else:
            partial_tp = result.entry_price - partial_pips * pip_size
            runner_tp = result.entry_price - runner_pips * pip_size
        return partial_tp, runner_tp, pip.partial_fraction, pip.move_stop_to_breakeven

    @staticmethod
    def _resolve_reason(result: PipelineResult) -> str:
        if result.entry is not None and result.entry.explanation:
            return result.entry.explanation
        actionable = story_actionable(
            getattr(result, "brain_story", None),
            result.market_story,
        )
        if (
            result.market_story is not None
            and not result.market_story.story_clear
            and not actionable
        ):
            return "Market story low confidence — waiting for expectancy edge"
        if result.harvest_score is not None and not result.harvest_score.allow_harvest:
            if not actionable and (
                result.market_story is None or not result.market_story.opportunity_type
            ):
                return result.harvest_score.reason
        if result.archetype_check is not None and not result.archetype_check.allowed:
            return result.archetype_check.reason
        if result.dynamic_pip_target is not None and result.dynamic_pip_target.skip_trade:
            return result.dynamic_pip_target.reason
        if not result.harvest.allowed:
            return result.harvest.reason
        if not result.risk.approved:
            return result.risk.reason
        return "No trade setup identified"

    @staticmethod
    def _resolve_theme(result: PipelineResult) -> tuple[str, float]:
        construction = getattr(result, "portfolio_construction", None)
        if construction is None:
            return "", 0.0
        exposure = getattr(construction, "exposure_decision", None)
        if exposure is not None:
            return exposure.trade_theme, float(exposure.theme_confidence)
        relative = getattr(construction, "relative_strength", None)
        if relative is not None:
            return relative.trade_theme, float(relative.theme_confidence)
        return "", 0.0

    @staticmethod
    def _resolve_thesis_snapshot(result: PipelineResult) -> str:
        thesis = getattr(result, "thesis", None)
        if thesis is None:
            return ""
        try:
            payload = thesis.to_dict() if hasattr(thesis, "to_dict") else {}
            if not isinstance(payload, dict):
                payload = {}
            intelligence: dict = {}
            conviction = getattr(result, "conviction_assessment", None)
            if conviction is not None and hasattr(conviction, "to_dict"):
                intelligence["conviction"] = conviction.to_dict()
            decision = getattr(result, "decision_result", None)
            if decision is not None and hasattr(decision, "to_dict"):
                intelligence["decision"] = decision.to_dict()
            exec_q = getattr(result, "execution_quality", None)
            if exec_q is not None and hasattr(exec_q, "to_dict"):
                intelligence["execution_quality"] = exec_q.to_dict()
            regime = getattr(result, "market_regime_intelligence", None)
            if regime is not None:
                primary = getattr(regime, "primary_regime", None) or getattr(
                    regime, "market_regime", None
                )
                if primary:
                    intelligence["primary_regime"] = str(primary)
            session = getattr(result, "session_intelligence", None)
            if session is not None:
                intelligence["session"] = getattr(session, "active_session", "unknown")
            if intelligence:
                payload["intelligence"] = intelligence
            maturity = getattr(result, "trade_maturity", None)
            if maturity is not None and hasattr(maturity, "to_dict"):
                payload["maturity"] = maturity.to_dict()
            cognitive = getattr(result, "cognitive_decision", None)
            if cognitive is not None and hasattr(cognitive, "to_dict"):
                payload["cognitive_council"] = cognitive.to_dict()
            return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        except Exception:
            return ""

    @staticmethod
    def _resolve_story_metadata(result: PipelineResult) -> dict[str, object]:
        """Extract expectancy pipeline artifacts for execution and learning."""
        patience = getattr(result, "patience_decision", None)
        opportunity = getattr(patience, "opportunity", None) if patience else None
        entry_type = str(getattr(opportunity, "entry_type", "") or "")
        brain_story = getattr(result, "brain_story", None)
        if brain_story is not None:
            return {
                "entry_type": entry_type,
                "story_direction": str(getattr(brain_story, "direction", "neutral") or "neutral"),
                "story_confidence": float(getattr(brain_story, "confidence", 0.0) or 0.0),
                "story_narrative": str(getattr(brain_story, "narrative", "") or "")[:500],
            }
        if result.market_story is not None:
            return {
                "entry_type": entry_type,
                "story_direction": str(getattr(result.market_story, "direction", "neutral") or "neutral"),
                "story_confidence": float(
                    getattr(result.market_story, "overall_confidence", 0.0) or 0.0
                ),
                "story_narrative": str(getattr(result.market_story, "primary_story", "") or "")[:500],
            }
        return {
            "entry_type": entry_type,
            "story_direction": "",
            "story_confidence": 0.0,
            "story_narrative": "",
        }

    @staticmethod
    def _resolve_scout_metadata(result: PipelineResult) -> dict[str, object]:
        maturity = getattr(result, "trade_maturity", None)
        if maturity is None:
            setup = str(getattr(result, "setup_kind", "") or "")
            return {
                "entry_stage": "",
                "scout_or_commit": "scout" if setup == "micro_scalp" else "",
                "setup_kind": setup,
                "acceptance_score_at_entry": 50,
                "rejection_score_at_entry": 50,
                "momentum_clarity_at_entry": "",
                "location_quality_at_entry": 0,
                "timing_quality_at_entry": 0,
                "scratch_eligible": setup == "micro_scalp",
            }
        scout = getattr(maturity, "scout_commit", None)
        accept = getattr(maturity, "acceptance", None)
        return {
            "entry_stage": str(getattr(maturity, "maturity_stage", "") or ""),
            "scout_or_commit": str(getattr(scout, "scout_or_commit", "") or ""),
            "setup_kind": str(
                getattr(scout, "effective_setup_kind", None)
                or getattr(result, "setup_kind", "")
                or ""
            ),
            "acceptance_score_at_entry": int(
                getattr(accept, "acceptance_score", 50) if accept else 50
            ),
            "rejection_score_at_entry": int(
                getattr(accept, "rejection_score", 50) if accept else 50
            ),
            "momentum_clarity_at_entry": str(
                getattr(scout, "momentum_clarity", "") if scout else ""
            ),
            "location_quality_at_entry": int(getattr(maturity, "location_quality", 0) or 0),
            "timing_quality_at_entry": int(getattr(maturity, "timing_quality", 0) or 0),
            "scratch_eligible": bool(getattr(scout, "scratch_eligible", False) if scout else False),
        }
