"""Opportunity Hunter Council — observers only, no voting gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from council.council_memory import CouncilMemory
from council.council_reports import CouncilReportWriter
from intelligence.harvest_opportunity_score import infer_session

if TYPE_CHECKING:
    from intelligence.market_narrative_engine import MarketNarrativeResult
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.narrative_forecast_engine import NarrativeForecastResult
    from intelligence.story_forecast_engine import StoryForecastResult
    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult


@dataclass(frozen=True)
class CouncilExpansionConfig:
    """Expansion mode — observer notes only, no vote thresholds."""

    enabled: bool = True
    micro_harvest_min_pips: float = 1.0
    micro_harvest_max_pips: float = 3.0


@dataclass(frozen=True)
class CouncilMemberOpinion:
    """One professor's narrative assessment — observational only."""

    member_name: str
    story: str
    forecast: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "member_name": self.member_name,
            "story": self.story,
            "forecast": self.forecast,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True)
class CouncilConsensus:
    """Council observer notes — never veto trades."""

    symbol: str
    consensus_narrative: str
    consensus_forecast: str
    consensus_confidence: float
    member_opinions: tuple[CouncilMemberOpinion, ...]
    allow_opportunity: bool
    opportunity_edge: str
    hunter_mode: bool = True
    expansion_mode: bool = False
    micro_harvest: bool = False
    votes_for: int = 0
    votes_against: int = 0
    vote_breakdown: tuple[tuple[str, bool, float], ...] = ()
    price_action_reason: str = ""
    volume_reason: str = ""
    micro_narrative_class: str | None = None
    observer_only: bool = True
    story_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "consensus_narrative": self.consensus_narrative,
            "consensus_forecast": self.consensus_forecast,
            "consensus_confidence": round(self.consensus_confidence, 2),
            "allow_opportunity": self.allow_opportunity,
            "opportunity_edge": self.opportunity_edge,
            "hunter_mode": self.hunter_mode,
            "expansion_mode": self.expansion_mode,
            "micro_harvest": self.micro_harvest,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "vote_breakdown": [
                {"member": m, "approve": a, "confidence": round(c, 2)}
                for m, a, c in self.vote_breakdown
            ],
            "price_action_reason": self.price_action_reason,
            "volume_reason": self.volume_reason,
            "micro_narrative_class": self.micro_narrative_class,
            "observer_only": self.observer_only,
            "story_notes": self.story_notes,
            "members": [m.to_dict() for m in self.member_opinions],
        }


class OpportunityHunterCouncil:
    """
    Six professors observe market story — provide notes, never veto.

    Price Action, Volume, Market Structure, Session, Volatility, Opportunity.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        expansion_config: CouncilExpansionConfig | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.expansion = expansion_config or CouncilExpansionConfig()
        self.memory = CouncilMemory(project_root)
        self.memory.load()
        self.reports = CouncilReportWriter(project_root)
        self._latest: dict[str, CouncilConsensus] = {}

    def observe(
        self,
        *,
        symbol: str,
        market_story: MarketStoryResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        narrative: MarketNarrativeResult | None = None,
        forecast: NarrativeForecastResult | None = None,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        regime: RegimeResult,
        evaluation_moment: datetime | None = None,
        indicator_confirmation_boost: float = 0.0,
        spread_pips: float = 0.0,
    ) -> CouncilConsensus:
        """Record observer notes — no voting gates."""
        if narrative is None and market_story is not None:
            narrative = market_story.to_narrative_result()
        if forecast is None and story_forecast is not None:
            forecast = story_forecast.to_narrative_forecast()
        if narrative is None or forecast is None:
            raise ValueError("market_story/story_forecast or narrative/forecast required")

        regime_label = regime.regime
        hour = evaluation_moment.hour if evaluation_moment else 12
        session = infer_session(hour)

        opinions = (
            self._price_action_professor(narrative, structure, bias, market_story),
            self._volume_professor(narrative, structure, market_story),
            self._market_structure_professor(narrative, structure, regime, market_story),
            self._session_professor(narrative, session, evaluation_moment, market_story),
            self._volatility_professor(narrative, forecast, market_story),
            self._opportunity_professor(narrative, forecast, structure, market_story, story_forecast),
        )

        weighted_sum = 0.0
        weight_total = 0.0
        for op in opinions:
            member_key = op.member_name.lower().replace(" ", "_")
            w = self.memory.weight_for(member_key, regime_label)
            weighted_sum += op.confidence * w
            weight_total += w
        consensus_conf = weighted_sum / max(weight_total, 0.01)
        consensus_conf = min(100.0, consensus_conf + indicator_confirmation_boost)

        narratives = [op.story for op in opinions if op.confidence >= 45]
        forecasts = [op.forecast for op in opinions if op.confidence >= 40]
        consensus_narrative = (
            " | ".join(narratives[:3]) if narratives else narrative.primary_story
        )
        consensus_forecast = forecasts[0] if forecasts else forecast.expected_next_move

        pa_op = opinions[0]
        vol_op = opinions[1]
        price_action_reason = pa_op.story
        volume_reason = vol_op.story
        micro_class = getattr(narrative, "micro_narrative_class", None)

        vote_breakdown, votes_for, votes_against = self._observational_votes(opinions)
        edge = self._detect_tiny_edge(narrative, forecast, structure, session, market_story, story_forecast)

        story_clear = (
            market_story.story_clear
            if market_story is not None
            else narrative.overall_confidence >= 38
        )
        micro_harvest = self._detect_micro_harvest(
            pa_op=pa_op,
            vol_op=vol_op,
            structure=structure,
            forecast=forecast,
            spread_pips=spread_pips,
            narrative=narrative,
            market_story=market_story,
        )

        allow = story_clear or micro_harvest or bool(edge)
        if market_story is not None and market_story.overall_confidence >= 38:
            allow = True
        opportunity_edge = edge or (
            story_forecast.opportunity_type if story_forecast else None
        ) or micro_class or forecast.recommended_strategy
        if micro_harvest and micro_class:
            opportunity_edge = str(micro_class)

        story_notes = self._compile_story_notes(
            market_story, story_forecast, opinions, story_clear
        )

        result = CouncilConsensus(
            symbol=symbol,
            consensus_narrative=consensus_narrative,
            consensus_forecast=consensus_forecast,
            consensus_confidence=consensus_conf,
            member_opinions=opinions,
            allow_opportunity=allow,
            opportunity_edge=str(opportunity_edge),
            hunter_mode=True,
            expansion_mode=self.expansion.enabled,
            micro_harvest=micro_harvest,
            votes_for=votes_for,
            votes_against=votes_against,
            vote_breakdown=vote_breakdown,
            price_action_reason=price_action_reason,
            volume_reason=volume_reason,
            micro_narrative_class=str(micro_class) if micro_class else None,
            observer_only=True,
            story_notes=story_notes,
        )
        self._latest[symbol] = result
        self.reports.record(symbol, result)
        return result

    def debate(self, **kwargs) -> CouncilConsensus:
        """Alias for observe — council does not debate/vote."""
        return self.observe(**kwargs)

    @staticmethod
    def _observational_votes(
        opinions: tuple[CouncilMemberOpinion, ...],
    ) -> tuple[tuple[tuple[str, bool, float], ...], int, int]:
        """Confidence scores for reporting — not used as gates."""
        breakdown: list[tuple[str, bool, float]] = []
        votes_for = 0
        for op in opinions:
            member_key = op.member_name.lower().replace(" ", "_")
            approved = op.confidence >= 50.0
            if approved:
                votes_for += 1
            breakdown.append((member_key, approved, op.confidence))
        votes_against = len(opinions) - votes_for
        return tuple(breakdown), votes_for, votes_against

    @staticmethod
    def _compile_story_notes(
        market_story: MarketStoryResult | None,
        story_forecast: StoryForecastResult | None,
        opinions: tuple[CouncilMemberOpinion, ...],
        story_clear: bool,
    ) -> str:
        parts: list[str] = []
        if market_story is not None:
            parts.append(
                f"Macro {market_story.macro_story}, H1 {market_story.h1_integrity}"
            )
            if market_story.opportunity_type:
                parts.append(f"Opp: {market_story.opportunity_type}")
            if market_story.strike.strike != "none":
                parts.append(f"Strike: {market_story.strike.strike}")
        if story_forecast is not None:
            parts.append(f"Forecast: {story_forecast.expected_next_move[:40]}")
        top = sorted(opinions, key=lambda o: o.confidence, reverse=True)[:2]
        for op in top:
            parts.append(f"{op.member_name}: {op.story[:35]}")
        parts.append("CLEAR" if story_clear else "UNCLEAR")
        return " — ".join(parts)

    @staticmethod
    def _detect_micro_harvest(
        *,
        pa_op: CouncilMemberOpinion,
        vol_op: CouncilMemberOpinion,
        structure: MarketContext,
        forecast: NarrativeForecastResult,
        spread_pips: float,
        narrative: MarketNarrativeResult,
        market_story: MarketStoryResult | None,
    ) -> bool:
        """Flag micro-harvest opportunity — observational, not a gate."""
        pa_ok = pa_op.confidence >= 40.0
        vol_ok = vol_op.confidence >= 40.0
        structure_ok = (
            structure.trend != "ranging"
            or structure.liquidity_zones
            or structure.last_bos is not None
            or len(structure.swing_highs) >= 2
        )
        net_pips = forecast.expected_pip_range - spread_pips
        pip_ok = net_pips >= 1.0
        micro_signal = (
            market_story is not None
            and (
                market_story.opportunity_type is not None
                or market_story.strike.strike != "none"
            )
        ) or getattr(narrative, "micro_narrative_class", None) is not None
        if pa_ok and vol_ok and structure_ok and (pip_ok or micro_signal):
            return True
        if micro_signal and pa_ok and structure_ok:
            return True
        return False

    def maybe_write_reports(self) -> Path | None:
        return self.reports.write_report()

    def latest(self, symbol: str) -> CouncilConsensus | None:
        return self._latest.get(symbol.strip().upper())

    @staticmethod
    def _price_action_professor(
        narrative: MarketNarrativeResult,
        structure: MarketContext,
        bias: MultiTimeframeBiasResult,
        market_story: MarketStoryResult | None,
    ) -> CouncilMemberOpinion:
        if market_story is not None:
            story = f"PA: {market_story.macro_story} — {market_story.strike.narrative}"
            conf = min(100.0, market_story.overall_confidence + 5.0)
            forecast = market_story.opportunity_type or "watch price action"
            if structure.last_bos is not None:
                story = f"BOS — {structure.last_bos.description}"
                conf = min(100.0, conf + 8.0)
            return CouncilMemberOpinion("Price Action Professor", story, str(forecast), conf)

        h1 = narrative.slice_for("H1")
        story = h1.what if h1 else "Price action unclear"
        conf = 55.0
        if structure.higher_highs and structure.higher_lows and bias.bias == "bullish":
            conf = 78.0
            forecast = "Continuation higher after pullback"
        elif structure.lower_highs and structure.lower_lows and bias.bias == "bearish":
            conf = 78.0
            forecast = "Continuation lower after pullback"
        else:
            forecast = h1.likely_next if h1 else "Range chop"
        return CouncilMemberOpinion("Price Action Professor", str(story), forecast, conf)

    @staticmethod
    def _volume_professor(
        narrative: MarketNarrativeResult,
        structure: MarketContext,
        market_story: MarketStoryResult | None,
    ) -> CouncilMemberOpinion:
        if market_story is not None:
            vol_story = market_story.volume_signal
            conf = 58.0
            if "expanding" in vol_story:
                conf = 72.0
                forecast = "Participation confirms move"
            elif "accumulation" in vol_story:
                conf = 68.0
                forecast = "Quiet bid — breakout pending"
            elif "distribution" in vol_story:
                conf = 70.0
                forecast = "Selling pressure — fade rallies"
            else:
                forecast = "Volume steady — follow structure"
            return CouncilMemberOpinion("Volume Professor", vol_story, forecast, conf)

        m15 = narrative.slice_for("M15")
        vol_story = m15.what if m15 else "Volume neutral"
        conf = m15.confidence if m15 else 50.0
        forecast = "Participation steady"
        return CouncilMemberOpinion("Volume Professor", str(vol_story), forecast, conf)

    @staticmethod
    def _market_structure_professor(
        narrative: MarketNarrativeResult,
        structure: MarketContext,
        regime: RegimeResult,
        market_story: MarketStoryResult | None,
    ) -> CouncilMemberOpinion:
        if market_story is not None:
            story = market_story.structure_signal
            conf = 60.0
            if structure.higher_highs or structure.lower_lows:
                conf = min(100.0, conf + 12.0)
            forecast = f"Structure supports {market_story.macro_story}"
            return CouncilMemberOpinion(
                "Market Structure Professor", story, forecast, conf
            )

        h4 = narrative.slice_for("H4")
        story = f"{regime.regime} — structure {structure.trend}"
        conf = h4.confidence if h4 else regime.confidence * 100
        forecast = "Trend architecture intact" if regime.regime == "trending" else "Range"
        return CouncilMemberOpinion("Market Structure Professor", story, forecast, conf)

    @staticmethod
    def _session_professor(
        narrative: MarketNarrativeResult,
        session: str,
        evaluation_moment: datetime | None,
        market_story: MarketStoryResult | None,
    ) -> CouncilMemberOpinion:
        story = f"Session {session}"
        if session == "london_ny_overlap":
            conf, forecast = 72.0, "Peak participation window"
        elif session == "london":
            conf, forecast = 68.0, "London impulse likely"
        elif session == "new_york":
            conf, forecast = 65.0, "NY continuation or retest"
        elif session == "asia":
            conf, forecast = 48.0, "Range/compression session"
        else:
            conf, forecast = 45.0, "Thin liquidity"
        if market_story and market_story.opportunity_type == "session_transition":
            conf = min(100.0, conf + 10.0)
            forecast = "Session transition momentum"
        return CouncilMemberOpinion("Session Professor", story, forecast, conf)

    @staticmethod
    def _volatility_professor(
        narrative: MarketNarrativeResult,
        forecast: NarrativeForecastResult,
        market_story: MarketStoryResult | None,
    ) -> CouncilMemberOpinion:
        if market_story is not None:
            macro = market_story.macro_story
            if macro == "expansion":
                conf, story = 70.0, "ATR expansion — ride impulse"
            elif macro == "compression":
                conf, story = 62.0, "Volatility squeeze — pop setup"
            elif macro == "exhaustion":
                conf, story = 68.0, "Climax vol — snapback zone"
            else:
                conf, story = 55.0, f"Vol baseline — {macro}"
            fc = f"Expected {forecast.expected_pip_range:.0f} pips"
            return CouncilMemberOpinion("Volatility Professor", story, fc, conf)

        h1 = narrative.slice_for("H1")
        story = str(h1.what) if h1 else "Volatility baseline"
        conf = h1.confidence if h1 else 52.0
        return CouncilMemberOpinion(
            "Volatility Professor",
            story,
            f"Expected {forecast.expected_pip_range:.0f} pips",
            conf,
        )

    @staticmethod
    def _opportunity_professor(
        narrative: MarketNarrativeResult,
        forecast: NarrativeForecastResult,
        structure: MarketContext,
        market_story: MarketStoryResult | None,
        story_forecast: StoryForecastResult | None,
    ) -> CouncilMemberOpinion:
        edges: list[str] = []
        conf = 50.0
        if market_story and market_story.opportunity_type:
            edges.append(market_story.opportunity_type)
            conf = 72.0
        if market_story and market_story.strike.strike != "none":
            edges.append(market_story.strike.strike)
            conf = max(conf, 70.0)
        if story_forecast and story_forecast.opportunity_type:
            edges.append(story_forecast.opportunity_type)
            conf = max(conf, 68.0)
        micro = getattr(narrative, "micro_narrative_class", None)
        if micro:
            edges.append(str(micro))
            conf = max(conf, 72.0)
        if structure.last_bos is not None:
            edges.append("BOS continuation")
            conf = max(conf, 65.0)
        if not edges:
            edges.append("micro edge in story")
            conf = max(conf, forecast.confidence * 0.85)
        story = f"Edges: {', '.join(edges)}"
        return CouncilMemberOpinion(
            "Opportunity Professor",
            story,
            forecast.expected_next_move,
            min(100.0, conf),
        )

    @staticmethod
    def _detect_tiny_edge(
        narrative: MarketNarrativeResult,
        forecast: NarrativeForecastResult,
        structure: MarketContext,
        session: str,
        market_story: MarketStoryResult | None,
        story_forecast: StoryForecastResult | None,
    ) -> str | None:
        if market_story and market_story.opportunity_type:
            return market_story.opportunity_type
        if story_forecast and story_forecast.opportunity_type:
            return story_forecast.opportunity_type
        micro = getattr(narrative, "micro_narrative_class", None)
        if micro:
            return str(micro)
        if narrative.exhaustion_detected:
            return "exhaustion_snapback"
        if narrative.compression_detected:
            return "compression_breakout"
        if structure.last_bos is not None and structure.liquidity_zones:
            return "liquidity_sweep_continuation"
        if session in {"london", "london_ny_overlap"} and forecast.confidence >= 45:
            return "session_transition_momentum"
        return None
