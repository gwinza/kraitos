"""Harvest Opportunity Score (0–100) for harvest entry quality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from typing import TYPE_CHECKING

from intelligence.asset_trend_analyzer import AssetTrendSnapshot
from intelligence.trend_strength_engine import TrendStrengthResult
from risk.models import DEFAULT_CORRELATION_GROUPS
from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

if TYPE_CHECKING:
    from council.opportunity_hunter_council import CouncilConsensus
    from intelligence.market_narrative_engine import MarketNarrativeResult
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.narrative_forecast_engine import NarrativeForecastResult
    from intelligence.story_evolution_engine import NestedStoryState
    from intelligence.story_forecast_engine import StoryForecastResult

HarvestBand = Literal["aggressive", "standard", "conditional", "no_harvest"]

BAND_THRESHOLDS = {
    "aggressive": 68,
    "standard": 50,
    "conditional": 28,
}

SESSION_BUCKETS = (
    (0, 8, "asia"),
    (8, 13, "london"),
    (13, 17, "london_ny_overlap"),
    (17, 22, "new_york"),
    (22, 24, "late_ny"),
)


@dataclass(frozen=True)
class HarvestOpportunityScore:
    """Composite harvest opportunity assessment."""

    symbol: str
    score: float
    band: HarvestBand
    allow_harvest: bool
    components: dict[str, float]
    reason: str
    session: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 2),
            "band": self.band,
            "allow_harvest": self.allow_harvest,
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "reason": self.reason,
            "session": self.session,
        }


def infer_session(hour: int) -> str:
    """Map UTC hour to trading session bucket."""
    for start, end, label in SESSION_BUCKETS:
        if start <= hour < end:
            return label
    return "late_ny"


def _correlation_risk(symbol: str, open_symbols: tuple[str, ...] = ()) -> float:
    """Return 0–1 penalty for correlated exposure."""
    normalized = symbol.strip().upper()
    if not open_symbols:
        return 0.0
    cluster = None
    for name, members in DEFAULT_CORRELATION_GROUPS.items():
        if normalized in members:
            cluster = set(members)
            break
    if cluster is None:
        return 0.0
    overlap = sum(1 for s in open_symbols if s.strip().upper() in cluster)
    return min(1.0, overlap / max(len(cluster), 1))


class HarvestOpportunityScorer:
    """Compute harvest opportunity score from trend and market context."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, HarvestOpportunityScore] = {}

    def score(
        self,
        *,
        symbol: str,
        trend: TrendStrengthResult,
        snapshot: AssetTrendSnapshot,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
        regime: RegimeResult,
        spread_pips: float,
        target_pips: float = 8.0,
        in_active_session: bool = True,
        evaluation_moment: datetime | None = None,
        open_symbols: tuple[str, ...] = (),
        narrative: MarketNarrativeResult | None = None,
        market_story: MarketStoryResult | None = None,
        forecast: NarrativeForecastResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        story_evolution: NestedStoryState | None = None,
        council: CouncilConsensus | None = None,
        indicator_insight: float = 0.0,
    ) -> HarvestOpportunityScore:
        f = snapshot.features
        components: dict[str, float] = {}

        if market_story is not None:
            narrative_score = market_story.overall_confidence
            if market_story.story_clear:
                narrative_score = min(100.0, narrative_score + 8.0)
            if market_story.opportunity_type:
                narrative_score = min(100.0, narrative_score + 6.0)
        elif narrative is not None:
            narrative_score = narrative.overall_confidence
            if narrative.exhaustion_detected or narrative.compression_detected:
                narrative_score = min(100.0, narrative_score + 8.0)
        else:
            narrative_score = 50.0
        components["market_story"] = narrative_score * 0.28

        council_score = 45.0
        if council is not None:
            council_score = council.consensus_confidence
        components["council_observer_notes"] = council_score * 0.08

        if story_forecast is not None:
            forecast_score = story_forecast.confidence
        elif forecast is not None:
            forecast_score = forecast.confidence
        else:
            forecast_score = 45.0
        if story_evolution is not None:
            if story_evolution.alignment == "aligned":
                forecast_score = min(100.0, forecast_score + 4.0)
            elif story_evolution.confidence_trend == "strengthening":
                forecast_score = min(100.0, forecast_score + 2.0)
        components["story_forecast"] = forecast_score * 0.18

        trend_align = 1.0 if f.macro_trend == bias.bias and bias.bias != "neutral" else 0.45
        if structure.trend == bias.bias and bias.bias != "neutral":
            trend_align = min(1.0, trend_align + 0.25)
        if market_story is not None and market_story.opportunity_type:
            trend_align = min(1.0, trend_align + 0.25)
        elif narrative is not None and narrative.micro_narrative_class:
            trend_align = min(1.0, trend_align + 0.2)
        components["price_structure"] = trend_align * 12.0

        liquidity = 0.4
        if structure.liquidity_zones:
            liquidity = 0.7
        if structure.last_bos is not None:
            liquidity = min(1.0, liquidity + 0.2)
        components["liquidity_sweep"] = liquidity * 10.0

        pullback = 0.5
        if structure.higher_lows and bias.bias == "bullish":
            pullback = 0.85
        if structure.lower_highs and bias.bias == "bearish":
            pullback = 0.85
        components["pullback_quality"] = pullback * 9.0

        session_hour = (
            evaluation_moment.hour
            if evaluation_moment is not None
            else datetime.now(timezone.utc).hour
        )
        session = infer_session(session_hour)
        session_score = f.session_strength
        if not in_active_session:
            session_score *= 0.4
        if session in {"london", "london_ny_overlap", "new_york"}:
            session_score = min(1.0, session_score + 0.15)
        components["session_quality"] = session_score * 8.0

        spread_ratio = spread_pips / max(target_pips, 0.5)
        spread_score = max(0.0, 1.0 - spread_ratio * 2.5)
        components["spread_to_target"] = spread_score * 6.0

        indicator_psychology = min(12.0, max(0.0, indicator_insight))
        components["indicator_psychology"] = indicator_psychology

        structure_clean = 0.5
        swings = len(structure.swing_highs) + len(structure.swing_lows)
        if swings >= 4:
            structure_clean = 0.75
        if (structure.higher_highs and structure.higher_lows) or (
            structure.lower_highs and structure.lower_lows
        ):
            structure_clean = 1.0
        components["structure_cleanliness"] = structure_clean * 6.0

        corr_penalty = _correlation_risk(symbol, open_symbols) * 6.0
        components["correlation_risk"] = max(0.0, 6.0 - corr_penalty)

        total = sum(components.values())
        if regime.regime in {"low_liquidity", "news_risk", "unclear"}:
            total = min(total, 45.0)
        if f.choppiness > 0.75:
            total *= 0.92

        if market_story is not None and market_story.story_clear:
            total = max(total, 42.0)
        elif market_story is not None and market_story.overall_confidence >= 55.0:
            total = max(total, 40.0)
        if market_story is not None and market_story.opportunity_type:
            total = max(total, 45.0)
            allow_floor = True
        else:
            allow_floor = False

        total = max(0.0, min(100.0, total))
        band = _band_for_score(total)
        allow = band != "no_harvest"
        if allow_floor:
            allow = True
            if band == "no_harvest":
                band = "conditional"
        if market_story is not None and market_story.story_clear:
            if band == "no_harvest":
                band = "conditional"

        reason = (
            f"Harvest score {total:.0f} ({band}) — "
            f"story-driven session {session}"
        )
        result = HarvestOpportunityScore(
            symbol=symbol,
            score=total,
            band=band,
            allow_harvest=allow,
            components=components,
            reason=reason,
            session=session,
        )
        self._latest[symbol] = result
        return result

    def write_report(self, path: Path | None = None) -> Path | None:
        if not self._latest:
            return None
        if self.project_root is None and path is None:
            return None
        report_path = path or (self.project_root / "logs" / "harvest_score_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Harvest Opportunity Score Report",
            "",
            f"**Generated:** {now}",
            "",
            "| Symbol | Score | Band | Session | Allow | Reason |",
            "|--------|-------|------|---------|-------|--------|",
        ]
        for symbol in sorted(self._latest):
            s = self._latest[symbol]
            lines.append(
                f"| {symbol} | {s.score:.0f} | {s.band} | {s.session} | "
                f"{'Y' if s.allow_harvest else 'N'} | {s.reason[:50]} |"
            )
        lines.extend(["", "## Component breakdown", ""])
        for symbol in sorted(self._latest):
            s = self._latest[symbol]
            comps = ", ".join(f"{k}={v:.1f}" for k, v in s.components.items())
            lines.append(f"- **{symbol}:** {comps}")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path


def _band_for_score(score: float) -> HarvestBand:
    if score >= BAND_THRESHOLDS["aggressive"]:
        return "aggressive"
    if score >= BAND_THRESHOLDS["standard"]:
        return "standard"
    if score >= BAND_THRESHOLDS["conditional"]:
        return "conditional"
    return "no_harvest"
