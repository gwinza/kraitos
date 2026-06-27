"""Story-aware harvesting — actively search 1–5 pip opportunities inside the market story."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from intelligence.participation_tracker import get_participation_tracker
from intelligence.story_aware_participation_doctrine import MICRO_HARVEST_PATTERNS
from strategies.harvest_engine import HarvestEngine
from strategies.models import HarvestContext, HarvestDecision

MICRO_PIP_RANGE = (1.0, 5.0)


@dataclass
class MicroHarvestWindow:
    """A 1–5 pip harvest opportunity recognised inside the market story."""

    pattern_key: str
    pattern_label: str
    target_pips: float
    confirms: tuple[str, ...] = ()
    weakens: tuple[str, ...] = ()
    likely_next: str = ""
    what_changed: str = ""


@dataclass
class StoryAwareHarvestStats:
    """Runtime counters for story-aware harvest probing."""

    candles_probed: int = 0
    windows_detected: int = 0
    micro_harvests_approved: int = 0
    story_overrides: int = 0
    patterns: dict[str, int] = field(default_factory=dict)
    missed_reasons: dict[str, int] = field(default_factory=dict)

    def record_window(self, pattern_key: str) -> None:
        self.windows_detected += 1
        self.patterns[pattern_key] = self.patterns.get(pattern_key, 0) + 1

    def record_missed(self, reason: str) -> None:
        key = reason[:80] if reason else "unknown"
        self.missed_reasons[key] = self.missed_reasons.get(key, 0) + 1


class StoryAwareHarvestEngine:
    """
    Wraps HarvestEngine with story-first micro-opportunity recognition.

    Does not add filters — expands participation when the story explains a harvest window.
    """

    def __init__(self, base: HarvestEngine | None = None) -> None:
        self._base = base or HarvestEngine()
        self.stats = StoryAwareHarvestStats()

    def evaluate(
        self,
        context: HarvestContext,
        *,
        story_forecast: object | None = None,
    ) -> HarvestDecision:
        self.stats.candles_probed += 1
        micro = self.probe_micro_harvest(context, story_forecast=story_forecast)
        if micro is not None:
            self.stats.record_window(micro.pattern_key)
            get_participation_tracker().record_harvest_window(micro.pattern_key)

        decision = self._base.evaluate(context)

        if micro is None:
            if not decision.allowed and context.story_clear:
                self.stats.record_missed(decision.reason)
            return decision

        if decision.allowed:
            target = min(max(micro.target_pips, MICRO_PIP_RANGE[0]), MICRO_PIP_RANGE[1])
            target = min(target, decision.target_pips, 4.0)
            mode = "conditional"
            self.stats.micro_harvests_approved += 1
            reason = (
                f"Story-aware micro harvest ({micro.pattern_label}): "
                f"{micro.what_changed or 'opportunity inside narrative'}; "
                f"{decision.reason}"
            )
            logger.info(f"Story harvest {context.symbol}: {micro.pattern_label} → {target:.1f} pips")
            return HarvestDecision(
                mode=mode,
                allowed=True,
                target_pips=target,
                reason=reason,
            )

        if context.story_clear and self._participation_supported(context, micro):
            self.stats.story_overrides += 1
            self.stats.micro_harvests_approved += 1
            reason = (
                f"Story participation harvest ({micro.pattern_label}): "
                f"{micro.what_changed or 'coherent story supports micro edge'} "
                f"(entry when thesis projects levels)"
            )
            if micro.weakens:
                reason += f"; note: {', '.join(micro.weakens)}"
            logger.info(f"Story override harvest {context.symbol}: {micro.pattern_label}")
            return HarvestDecision(
                mode="conditional",
                allowed=True,
                target_pips=micro.target_pips,
                reason=reason,
            )

        self.stats.record_missed(decision.reason)
        return decision

    def probe_micro_harvest(
        self,
        context: HarvestContext,
        *,
        story_forecast: object | None = None,
    ) -> MicroHarvestWindow | None:
        """
        For every new candle context ask:
        What changed? What opportunity emerged? Is there a 1–5 pip harvest?
        """
        if not context.story_clear:
            return None

        opp = (context.opportunity_type or "").strip().lower()
        if not opp:
            return None

        pattern_key = opp
        pattern_label = MICRO_HARVEST_PATTERNS.get(opp, opp.replace("_", " "))
        target = self._target_pips_for_pattern(opp, context, story_forecast)
        confirms: list[str] = []
        weakens: list[str] = []

        if context.price_action_valid:
            confirms.append("price action strike")
        if context.volume_momentum_strong:
            confirms.append("volume supports move")
        if context.structure_supports:
            confirms.append("structure aligns with story")
        if context.in_active_session:
            confirms.append("active session")
        if context.current_spread > context.spread_limit:
            weakens.append("spread wide")

        what_changed = f"{pattern_label} opportunity recognised in story"
        likely_next = ""
        if story_forecast is not None:
            likely_next = getattr(story_forecast, "expected_next_move", "") or ""
            mf = getattr(story_forecast, "most_likely_next", None)
            if mf:
                likely_next = str(mf)

        return MicroHarvestWindow(
            pattern_key=pattern_key,
            pattern_label=pattern_label,
            target_pips=target,
            confirms=tuple(confirms),
            weakens=tuple(weakens),
            likely_next=likely_next,
            what_changed=what_changed,
        )

    @staticmethod
    def _target_pips_for_pattern(
        opp: str,
        context: HarvestContext,
        story_forecast: object | None,
    ) -> float:
        if story_forecast is not None:
            lo = getattr(story_forecast, "expected_pip_range_min", 0.0) or 0.0
            hi = getattr(story_forecast, "expected_pip_range_max", 0.0) or 0.0
            if lo > 0 and hi > 0:
                return min(max((lo + hi) / 2.0, MICRO_PIP_RANGE[0]), MICRO_PIP_RANGE[1])

        fast_patterns = {
            "liquidity_sweep",
            "mean_reversion_snapback",
            "candle_rejection",
            "momentum_burst",
            "failed_breakout",
        }
        if opp in fast_patterns:
            return 1.5
        if opp in {"pullback_continuation", "breakout_retest", "trend_pause_resume"}:
            return 2.5
        if context.council_micro_harvest:
            return 2.0
        return 2.0

    @staticmethod
    def _participation_supported(context: HarvestContext, micro: MicroHarvestWindow) -> bool:
        """Enter when price action, structure, or volume collectively support participation."""
        if context.price_action_valid:
            return True
        if context.structure_supports and context.volume_momentum_strong:
            return True
        if len(micro.confirms) >= 1:
            return True
        if context.narrative_direction in {"bullish", "bearish"} and context.structure_supports:
            return True
        return context.story_clear and context.current_spread <= context.spread_limit
