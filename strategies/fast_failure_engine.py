"""Fast failure engine — exit losers early when thesis, momentum, or structure fails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.market_reading_utils import atr_series, validate_candles
from strategies.models import MarketContext, MicroScalpSignal

FailureType = Literal["thesis", "momentum", "structure", "combined", "none"]
FailureAction = Literal["hold", "tighten", "reduce", "exit_early", "scratch"]
ScratchReason = Literal[
    "acceptance_failure",
    "rejection_rise",
    "momentum_unclear",
    "path_failure",
    "spread_worsening",
    "confidence_decay",
    "none",
]


@dataclass(frozen=True)
class FastFailureResult:
    """Early failure detection for open trades."""

    symbol: str
    side: str
    failure_detected: bool
    failure_type: FailureType
    failure_score: int
    recommended_action: FailureAction
    thesis_failure: bool
    momentum_failure: bool
    structure_failure: bool
    current_r: float
    explanation: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "failure_detected": self.failure_detected,
            "failure_type": self.failure_type,
            "failure_score": self.failure_score,
            "recommended_action": self.recommended_action,
            "thesis_failure": self.thesis_failure,
            "momentum_failure": self.momentum_failure,
            "structure_failure": self.structure_failure,
            "current_r": round(self.current_r, 3),
            "explanation": self.explanation,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ScoutScratchResult:
    should_scratch: bool
    scratch_reason: ScratchReason
    max_r_cap: float
    adaptive_window_bars: int
    current_r: float
    explanation: str
    scratch_triggered: bool = False
    why_not_scratch: str = ""
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "should_scratch": self.should_scratch,
            "scratch_reason": self.scratch_reason,
            "max_r_cap": round(self.max_r_cap, 3),
            "adaptive_window_bars": self.adaptive_window_bars,
            "current_r": round(self.current_r, 3),
            "explanation": self.explanation,
            "scratch_triggered": self.scratch_triggered,
            "why_not_scratch": self.why_not_scratch,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class FastFailureConfig:
    min_candles: int = 15
    thesis_invalidation_buffer_atr: float = 0.1
    momentum_failure_bars: int = 5
    structure_break_atr: float = 0.15
    exit_early_r_threshold: float = -0.35
    reduce_r_threshold: float = -0.15
    scout_scratch_r: float = -0.35
    unclear_scalp_scratch_r: float = -0.50
    acceptance_improvement_min: int = 5
    rejection_rise_trigger: int = 12


class FastFailureEngineError(Exception):
    pass


class FastFailureEngine:
    """Detect thesis, momentum, and structure failure to protect capital."""

    def __init__(self, config: FastFailureConfig | None = None) -> None:
        self.config = config or FastFailureConfig()

    def evaluate(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        current_price: float,
        candles: pd.DataFrame | None = None,
        structure: MarketContext | None = None,
        momentum: MicroScalpSignal | None = None,
        invalidation_level: float | None = None,
        thesis_direction: str | None = None,
    ) -> FastFailureResult:
        if side not in {"buy", "sell"}:
            raise FastFailureEngineError("side must be buy or sell")

        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            risk = 1e-9
        if side == "buy":
            current_r = (current_price - entry_price) / risk
        else:
            current_r = (entry_price - current_price) / risk

        evidence: list[str] = []
        thesis_fail = self._thesis_failure(
            side, current_price, invalidation_level, entry_price, stop_loss, evidence
        )
        momentum_fail = self._momentum_failure(side, momentum, candles, evidence)
        structure_fail = self._structure_failure(side, structure, current_price, candles, evidence)

        failures = sum([thesis_fail, momentum_fail, structure_fail])
        score = 0
        if thesis_fail:
            score += 45
        if momentum_fail:
            score += 30
        if structure_fail:
            score += 35
        score = min(100, score)

        if failures >= 2:
            ftype: FailureType = "combined"
        elif thesis_fail:
            ftype = "thesis"
        elif structure_fail:
            ftype = "structure"
        elif momentum_fail:
            ftype = "momentum"
        else:
            ftype = "none"

        detected = failures > 0 and current_r <= self.config.exit_early_r_threshold
        if not detected and failures > 0 and current_r <= self.config.reduce_r_threshold:
            action: FailureAction = "reduce"
        elif detected and (thesis_fail or failures >= 2):
            action = "exit_early"
        elif detected:
            action = "tighten"
        elif failures > 0:
            action = "tighten"
        else:
            action = "hold"

        if current_r > 0.25 and not thesis_fail:
            action = "hold"
            detected = False
            score = max(0, score - 30)

        return FastFailureResult(
            symbol=symbol,
            side=side,
            failure_detected=detected or (failures > 0 and current_r < 0),
            failure_type=ftype,
            failure_score=score,
            recommended_action=action,
            thesis_failure=thesis_fail,
            momentum_failure=momentum_fail,
            structure_failure=structure_fail,
            current_r=current_r,
            explanation=self._explain(ftype, action, current_r, failures),
            evidence=tuple(evidence),
        )

    def _thesis_failure(
        self,
        side: str,
        current_price: float,
        invalidation_level: float | None,
        entry_price: float,
        stop_loss: float,
        evidence: list[str],
    ) -> bool:
        level = invalidation_level
        if level is None or level <= 0:
            level = stop_loss
        if side == "buy" and current_price < level:
            evidence.append(f"thesis failure — price below invalidation {level:.5f}")
            return True
        if side == "sell" and current_price > level:
            evidence.append(f"thesis failure — price above invalidation {level:.5f}")
            return True
        return False

    @staticmethod
    def _momentum_failure(
        side: str,
        momentum: MicroScalpSignal | None,
        candles: pd.DataFrame | None,
        evidence: list[str],
    ) -> bool:
        if momentum is not None:
            if side == "buy" and momentum.action == "sell":
                evidence.append("momentum failure — M1 flipped bearish against long")
                return True
            if side == "sell" and momentum.action == "buy":
                evidence.append("momentum failure — M1 flipped bullish against short")
                return True
        if candles is not None and len(candles) >= 6:
            close = candles["close"].astype(float)
            recent = float(close.iloc[-1]) - float(close.iloc[-5])
            if side == "buy" and recent < 0:
                opp = float((close.diff() < 0).tail(5).mean())
                if opp >= 0.6:
                    evidence.append("momentum failure — consecutive bearish closes")
                    return True
            if side == "sell" and recent > 0:
                opp = float((close.diff() > 0).tail(5).mean())
                if opp >= 0.6:
                    evidence.append("momentum failure — consecutive bullish closes")
                    return True
        return False

    def _structure_failure(
        self,
        side: str,
        structure: MarketContext | None,
        current_price: float,
        candles: pd.DataFrame | None,
        evidence: list[str],
    ) -> bool:
        if structure is not None:
            if side == "buy" and structure.last_choch is not None:
                if structure.last_choch.kind == "choch_bearish":
                    evidence.append("structure failure — bearish CHoCH against long")
                    return True
            if side == "sell" and structure.last_choch is not None:
                if structure.last_choch.kind == "choch_bullish":
                    evidence.append("structure failure — bullish CHoCH against short")
                    return True
            if side == "buy" and structure.swing_lows:
                key_low = min(s.price for s in structure.swing_lows[-3:])
                if current_price < key_low:
                    evidence.append("structure failure — prior swing low broken")
                    return True
            if side == "sell" and structure.swing_highs:
                key_high = max(s.price for s in structure.swing_highs[-3:])
                if current_price > key_high:
                    evidence.append("structure failure — prior swing high broken")
                    return True

        if candles is not None:
            try:
                frame = validate_candles(candles, min_candles=10, engine="FastFailureEngine")
                atr = float(atr_series(frame).iloc[-1]) or 1e-9
                if side == "buy" and structure is not None and structure.swing_lows:
                    level = min(s.price for s in structure.swing_lows[-2:])
                    if current_price < level - atr * self.config.structure_break_atr:
                        evidence.append("structure failure — decisive break below support")
                        return True
            except ValueError:
                pass
        return False

    @staticmethod
    def _explain(ftype: FailureType, action: FailureAction, current_r: float, failures: int) -> str:
        if failures == 0:
            return f"No failure signals — hold (current {current_r:.2f}R)"
        return (
            f"Fast failure {ftype} — {action} at {current_r:.2f}R "
            f"({failures} signal{'s' if failures > 1 else ''})"
        )

    def evaluate_scout_scratch(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        current_price: float,
        bars_since_entry: int,
        setup_kind: str,
        scout_or_commit: str,
        momentum_clarity: str,
        entry_acceptance_score: int,
        current_acceptance_score: int,
        entry_rejection_score: int,
        current_rejection_score: int,
        spread_pips: float,
        spread_limit: float,
        candles: pd.DataFrame | None = None,
        partial_taken: bool = False,
    ) -> ScoutScratchResult:
        risk = abs(entry_price - stop_loss) or 1e-9
        if side == "buy":
            current_r = (current_price - entry_price) / risk
        else:
            current_r = (entry_price - current_price) / risk

        is_scout = scout_or_commit == "scout" or scout_or_commit in {"probe", "micro_probe"}
        unclear = momentum_clarity == "unclear"
        window = self._adaptive_scratch_window(
            setup_kind=setup_kind,
            bars_since_entry=bars_since_entry,
            candles=candles,
            is_scout=is_scout,
            unclear=unclear,
            spread_pips=spread_pips,
        )
        max_cap = (
            self.config.unclear_scalp_scratch_r
            if unclear and setup_kind == "micro_scalp"
            else self.config.scout_scratch_r
        )
        if not is_scout and scout_or_commit == "commit":
            max_cap = -0.60

        evidence: list[str] = []
        reason: ScratchReason = "none"
        should = False

        acceptance_delta = current_acceptance_score - entry_acceptance_score
        rejection_delta = current_rejection_score - entry_rejection_score

        if partial_taken and current_r > 0:
            return ScoutScratchResult(
                should_scratch=False,
                scratch_reason="none",
                max_r_cap=max_cap,
                adaptive_window_bars=window,
                current_r=current_r,
                explanation="Partial taken in profit — scratch not applicable",
                why_not_scratch="trade already working",
            )

        if current_rejection_score >= 72 and is_scout:
            should = True
            reason = "rejection_rise"
            evidence.append(f"rejection elevated to {current_rejection_score}")

        if rejection_delta >= self.config.rejection_rise_trigger and current_r <= 0:
            should = True
            reason = "rejection_rise"
            evidence.append(f"rejection rose {rejection_delta} since entry")

        if bars_since_entry >= window and acceptance_delta < self.config.acceptance_improvement_min:
            if current_r <= 0 and is_scout:
                should = True
                reason = "acceptance_failure"
                evidence.append(
                    f"no acceptance improvement ({acceptance_delta}) after {bars_since_entry} bars"
                )

        if unclear and bars_since_entry >= max(2, window - 1) and current_r <= -0.10 and is_scout:
            should = True
            reason = "momentum_unclear"
            evidence.append("momentum still unclear with no progress")

        if spread_pips > spread_limit and current_r <= 0 and is_scout:
            should = True
            reason = "spread_worsening"
            evidence.append(f"spread {spread_pips:.1f} > limit {spread_limit:.1f}")

        if candles is not None and len(candles) >= 4 and is_scout:
            close = candles["close"].astype(float)
            if side == "buy" and float(close.iloc[-1]) <= float(close.iloc[-3]):
                if current_r <= -0.08:
                    should = True
                    reason = "path_failure"
                    evidence.append("price not moving toward expected bullish path")
            if side == "sell" and float(close.iloc[-1]) >= float(close.iloc[-3]):
                if current_r <= -0.08:
                    should = True
                    reason = "path_failure"
                    evidence.append("price not moving toward expected bearish path")

        if current_r <= max_cap and is_scout:
            should = True
            if reason == "none":
                reason = "acceptance_failure"
            evidence.append(f"R cap {max_cap:.2f} reached at {current_r:.2f}R")

        if current_r <= -0.10 and is_scout and bars_since_entry >= 1:
            if current_acceptance_score < entry_acceptance_score:
                should = True
                reason = "confidence_decay"
                evidence.append("acceptance decaying on scout")

        if should and current_r > 0.15 and not unclear:
            should = False
            why = "trade working — defer scratch"
        elif should:
            why = ""
        else:
            why = (
                f"within scratch window ({bars_since_entry}/{window})"
                if bars_since_entry < window
                else "acceptance improving or trade working"
            )

        explanation = (
            f"Scout scratch ({reason}) at {current_r:.2f}R after {bars_since_entry} bars"
            if should
            else f"Hold scout — {why} ({current_r:.2f}R, window {window})"
        )
        return ScoutScratchResult(
            should_scratch=should,
            scratch_reason=reason,
            max_r_cap=max_cap,
            adaptive_window_bars=window,
            current_r=current_r,
            explanation=explanation,
            scratch_triggered=should,
            why_not_scratch=why,
            evidence=tuple(evidence),
        )

    def _adaptive_scratch_window(
        self,
        *,
        setup_kind: str,
        bars_since_entry: int,
        candles: pd.DataFrame | None,
        is_scout: bool,
        unclear: bool,
        spread_pips: float,
    ) -> int:
        base = 3 if setup_kind == "micro_scalp" else 5 if setup_kind == "harvest" else 4
        if unclear:
            base = max(2, base - 1)
        if is_scout:
            base = max(2, base - 1)
        if spread_pips > 2.5:
            base = max(2, base - 1)
        if candles is not None and len(candles) >= 20:
            try:
                frame = validate_candles(candles, min_candles=15, engine="FastFailureEngine")
                atr = atr_series(frame)
                recent = float(atr.iloc[-1]) or 1e-9
                median = float(atr.tail(20).median()) or recent
                if recent > median * 1.2:
                    base += 1
            except ValueError:
                pass
        return max(2, min(8, base))


__all__ = [
    "FailureAction",
    "FailureType",
    "FastFailureConfig",
    "FastFailureEngine",
    "FastFailureEngineError",
    "FastFailureResult",
    "ScoutScratchResult",
    "ScratchReason",
]
