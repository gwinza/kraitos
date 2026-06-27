"""ATR-based dynamic pip targets for harvest and scalp modes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from intelligence.harvest_opportunity_score import HarvestOpportunityScore
from intelligence.trend_strength_engine import TrendStrengthResult

AtrBand = Literal["low", "medium", "high", "skip"]


@dataclass(frozen=True)
class DynamicPipTargetDecision:
    """Dynamic pip target and exit management parameters."""

    symbol: str
    atr_band: AtrBand
    target_pips: float
    stop_loss_pips: float
    partial_tp_pips: float
    trail_distance_pips: float
    break_even_trigger_pips: float
    allow_micro_pyramiding: bool
    risk_multiplier: float
    skip_trade: bool
    reason: str
    second_target_pips: float = 0.0
    allow_second_target: bool = False
    allow_partial_exit: bool = False
    partial_fraction: float = 0.5
    move_stop_to_breakeven: bool = False

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "atr_band": self.atr_band,
            "target_pips": round(self.target_pips, 2),
            "stop_loss_pips": round(self.stop_loss_pips, 2),
            "partial_tp_pips": round(self.partial_tp_pips, 2),
            "trail_distance_pips": round(self.trail_distance_pips, 2),
            "break_even_trigger_pips": round(self.break_even_trigger_pips, 2),
            "allow_micro_pyramiding": self.allow_micro_pyramiding,
            "risk_multiplier": round(self.risk_multiplier, 2),
            "skip_trade": self.skip_trade,
            "reason": self.reason,
            "second_target_pips": round(self.second_target_pips, 2),
            "allow_second_target": self.allow_second_target,
            "allow_partial_exit": self.allow_partial_exit,
            "partial_fraction": round(self.partial_fraction, 2),
            "move_stop_to_breakeven": self.move_stop_to_breakeven,
        }


class DynamicPipTargetEngine:
    """Compute ATR-aware pip targets and exit parameters."""

    LOW_ATR_RANGE = (1.0, 3.0)
    MEDIUM_ATR_RANGE = (3.0, 5.0)
    HIGH_ATR_RANGE = (5.0, 10.0)
    MAX_SPREAD_TO_TARGET = 0.50
    MIN_ATR_RATIO = 0.40
    MICRO_MAX_SPREAD_TO_TARGET = 0.72

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, DynamicPipTargetDecision] = {}

    def evaluate(
        self,
        *,
        symbol: str,
        atr_ratio: float,
        atr_pips: float,
        spread_pips: float,
        trend: TrendStrengthResult,
        harvest_score: HarvestOpportunityScore | None = None,
        choppiness: float = 0.0,
        allow_pyramiding: bool = False,
        micro_harvest: bool = False,
        forecast_confidence: float = 0.0,
        price_action_volume_agree: bool = False,
        narrative_target_multiplier: float = 1.0,
        expected_pip_range: float | None = None,
        allow_runner: bool = False,
        partial_fraction: float = 0.5,
        move_stop_to_breakeven: bool = False,
        exit_speed: float = 1.0,
    ) -> DynamicPipTargetDecision:
        band, base_target = self._atr_band(atr_pips, atr_ratio)
        strong_trend = trend.score >= 75 and trend.quality in {
            "institutional_trend",
            "developing_trend",
        }
        high_confidence = forecast_confidence > 75.0

        if micro_harvest:
            if high_confidence and strong_trend:
                base_target = max(5.0, min(7.0, base_target * 0.9 + 2.5))
            elif high_confidence or strong_trend:
                base_target = max(4.0, min(6.0, base_target * 0.75 + 2.0))
            else:
                base_target = max(1.5, min(3.0, base_target * 0.45))

        spread_limit = (
            self.MICRO_MAX_SPREAD_TO_TARGET if micro_harvest else self.MAX_SPREAD_TO_TARGET
        )
        spread_ratio = spread_pips / max(base_target, 0.5)
        widened = False
        if spread_ratio > spread_limit:
            if micro_harvest and spread_ratio <= spread_limit + 0.18:
                base_target = min(5.5, base_target + spread_pips * 0.55)
                widened = True
            else:
                decision = DynamicPipTargetDecision(
                    symbol=symbol,
                    atr_band="skip",
                    target_pips=0.0,
                    stop_loss_pips=0.0,
                    partial_tp_pips=0.0,
                    trail_distance_pips=0.0,
                    break_even_trigger_pips=0.0,
                    allow_micro_pyramiding=False,
                    risk_multiplier=0.0,
                    skip_trade=True,
                    reason=f"Spread {spread_pips:.1f}p too large vs target {base_target:.1f}p",
                )
                self._latest[symbol] = decision
                return decision

        min_atr = 0.30 if micro_harvest else self.MIN_ATR_RATIO
        if atr_ratio < min_atr:
            if micro_harvest and spread_pips <= 2.0:
                base_target = max(1.0, 2.0 - spread_pips * 0.3)
                band = "low"
            else:
                decision = DynamicPipTargetDecision(
                    symbol=symbol,
                    atr_band="skip",
                    target_pips=0.0,
                    stop_loss_pips=0.0,
                    partial_tp_pips=0.0,
                    trail_distance_pips=0.0,
                    break_even_trigger_pips=0.0,
                    allow_micro_pyramiding=False,
                    risk_multiplier=0.0,
                    skip_trade=True,
                    reason=f"ATR ratio {atr_ratio:.2f} too low — noise filter",
                )
                self._latest[symbol] = decision
                return decision

        target = base_target * max(0.85, narrative_target_multiplier)
        if exit_speed > 1.0:
            target /= min(1.35, exit_speed)
        risk_mult = 1.0
        sl_pips = max(8.0, target * 1.5)
        partial = target * 0.45
        trail = target * 0.4
        be_trigger = target * 0.35
        pyramiding = allow_pyramiding

        if band == "high":
            target = min(self.HIGH_ATR_RANGE[1] * 1.2, target * 1.2)
            risk_mult = 0.75
            sl_pips = target * 1.8
        elif band == "medium" and atr_ratio >= 0.75:
            target = min(self.HIGH_ATR_RANGE[1], target * 1.08)
        elif band == "low":
            sl_pips = max(6.0, target * 1.3)

        if strong_trend:
            target = min(self.HIGH_ATR_RANGE[1] * 1.15, target * 1.12)

        if expected_pip_range is not None and expected_pip_range > target:
            target = min(self.HIGH_ATR_RANGE[1] * 1.25, max(target, expected_pip_range * 0.85))

        if choppiness > 0.6:
            target *= 0.85
            risk_mult = min(risk_mult, 0.7)
            pyramiding = False

        if harvest_score is not None:
            if harvest_score.band == "aggressive":
                target = min(self.HIGH_ATR_RANGE[1] * 1.15, target * 1.08)
            elif harvest_score.band == "conditional":
                target *= 0.9
                risk_mult = min(risk_mult, 0.8)
            elif harvest_score.band == "no_harvest" and not micro_harvest:
                decision = DynamicPipTargetDecision(
                    symbol=symbol,
                    atr_band=band,
                    target_pips=0.0,
                    stop_loss_pips=0.0,
                    partial_tp_pips=0.0,
                    trail_distance_pips=0.0,
                    break_even_trigger_pips=0.0,
                    allow_micro_pyramiding=False,
                    risk_multiplier=0.0,
                    skip_trade=True,
                    reason="Harvest score below conditional threshold",
                )
                self._latest[symbol] = decision
                return decision

        allow_second = (
            price_action_volume_agree
            and strong_trend
            and allow_runner
        )
        second_target = 0.0
        if allow_second:
            second_target = min(
                self.HIGH_ATR_RANGE[1] * 1.5,
                target * 1.65,
            )
            if expected_pip_range is not None:
                second_target = max(second_target, min(expected_pip_range * 1.1, 12.0))
        elif allow_runner and high_confidence and strong_trend:
            second_target = min(self.HIGH_ATR_RANGE[1] * 1.3, target * 1.35)

        allow_partial = allow_runner and allow_second and second_target > target * 1.08
        if allow_partial:
            partial = min(partial, target * partial_fraction * 1.1)
            target = second_target if second_target > target else target

        reason = f"ATR band {band} target {target:.1f}p (ratio {atr_ratio:.2f})"
        if widened:
            reason += "; spread-widened target"
        if allow_partial:
            reason += f"; partial {partial:.1f}p runner {target:.1f}p"

        decision = DynamicPipTargetDecision(
            symbol=symbol,
            atr_band=band,
            target_pips=round(target, 2),
            stop_loss_pips=round(sl_pips, 2),
            partial_tp_pips=round(partial, 2),
            trail_distance_pips=round(trail, 2),
            break_even_trigger_pips=round(be_trigger, 2),
            allow_micro_pyramiding=pyramiding and band != "low",
            risk_multiplier=risk_mult,
            skip_trade=False,
            reason=reason,
            second_target_pips=round(second_target, 2),
            allow_second_target=allow_second,
            allow_partial_exit=allow_partial,
            partial_fraction=partial_fraction,
            move_stop_to_breakeven=move_stop_to_breakeven and allow_partial,
        )
        self._latest[symbol] = decision
        return decision

    def _atr_band(self, atr_pips: float, atr_ratio: float) -> tuple[AtrBand, float]:
        effective = atr_pips * max(0.5, atr_ratio)
        if effective < self.LOW_ATR_RANGE[1]:
            mid = (self.LOW_ATR_RANGE[0] + self.LOW_ATR_RANGE[1]) / 2
            return "low", mid
        if effective < self.MEDIUM_ATR_RANGE[1]:
            mid = (self.MEDIUM_ATR_RANGE[0] + self.MEDIUM_ATR_RANGE[1]) / 2
            return "medium", mid
        mid = min(self.HIGH_ATR_RANGE[1], (self.HIGH_ATR_RANGE[0] + self.HIGH_ATR_RANGE[1]) / 2)
        return "high", mid

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        if self.project_root is None and path is None:
            return None
        report_path = path or (self.project_root / "logs" / "dynamic_pip_target_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Dynamic Pip Target Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Band | Target | SL | Partial | Trail | BE | Risk | Skip |",
            "|--------|------|--------|-----|---------|-------|-----|------|------|",
        ]
        for symbol in sorted(self._latest):
            d = self._latest[symbol]
            lines.append(
                f"| {symbol} | {d.atr_band} | {d.target_pips:.1f} | {d.stop_loss_pips:.1f} | "
                f"{d.partial_tp_pips:.1f} | {d.trail_distance_pips:.1f} | "
                f"{d.break_even_trigger_pips:.1f} | {d.risk_multiplier:.0%} | "
                f"{'Y' if d.skip_trade else 'N'} |"
            )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path
