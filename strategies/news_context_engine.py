"""News context engine — interpret macro events as context, not veto."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from strategies.models import NewsEvent, NewsImpactLevel

NewsCategory = Literal[
    "nfp",
    "cpi",
    "fomc",
    "rates",
    "geopolitical",
    "general",
    "none",
]

NewsPosture = Literal[
    "elevated_volatility",
    "directional_bias",
    "range_expected",
    "neutral",
]


@dataclass(frozen=True)
class NewsContextResult:
    """Macro news context — informs sizing and timing, never auto-vetoes."""

    symbol: str
    active_category: NewsCategory
    news_posture: NewsPosture
    context_score: int
    volatility_multiplier: float
    size_multiplier: float
    directional_hint: Literal["bullish", "bearish", "neutral"]
    nearby_event: bool
    explanation: str
    trade_opportunity: str
    events_considered: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "active_category": self.active_category,
            "news_posture": self.news_posture,
            "context_score": self.context_score,
            "volatility_multiplier": round(self.volatility_multiplier, 3),
            "size_multiplier": round(self.size_multiplier, 3),
            "directional_hint": self.directional_hint,
            "nearby_event": self.nearby_event,
            "explanation": self.explanation,
            "trade_opportunity": self.trade_opportunity,
            "events_considered": list(self.events_considered),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class NewsContextConfig:
    """Lookahead/lookback windows for context (not blocking)."""

    context_before_minutes: int = 120
    context_after_minutes: int = 60
    nfp_size_multiplier: float = 0.70
    cpi_size_multiplier: float = 0.75
    fomc_size_multiplier: float = 0.65
    rates_size_multiplier: float = 0.80
    geo_size_multiplier: float = 0.85


class NewsContextEngine:
    """Interpret NFP, CPI, FOMC, rates, geopolitical — context only, no veto."""

    _CATEGORY_KEYWORDS: dict[NewsCategory, tuple[str, ...]] = {
        "nfp": ("nfp", "non-farm", "nonfarm", "payroll", "employment"),
        "cpi": ("cpi", "inflation", "pce", "consumer price"),
        "fomc": ("fomc", "fed", "federal reserve", "powell", "interest rate decision"),
        "rates": ("rate", "yield", "treasury", "bond", "central bank", "ecb", "boe", "boj"),
        "geopolitical": ("war", "sanction", "geopolitical", "conflict", "election", "tariff"),
    }

    def __init__(self, config: NewsContextConfig | None = None) -> None:
        self.config = config or NewsContextConfig()

    def analyze(
        self,
        events: list[NewsEvent] | None = None,
        *,
        symbol: str = "",
        at_time: datetime | None = None,
    ) -> NewsContextResult:
        symbol_key = symbol.strip().upper()
        moment = at_time or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)

        relevant = self._relevant_events(events or [], symbol_key, moment)
        if not relevant:
            return NewsContextResult(
                symbol=symbol_key,
                active_category="none",
                news_posture="neutral",
                context_score=50,
                volatility_multiplier=1.0,
                size_multiplier=1.0,
                directional_hint="neutral",
                nearby_event=False,
                explanation="No macro news context — trade structure normally",
                trade_opportunity="Full participation on structure — no news overlay",
                evidence=("No scheduled macro events in context window",),
            )

        primary = relevant[0]
        category = self._categorize(primary)
        nearby = self._is_imminent(primary, moment)
        posture, vol_mult, size_mult, hint = self._posture(category, primary.impact_level, nearby)
        opportunity = self._trade_opportunity(category, posture, nearby, hint)
        event_names = tuple(
            f"{e.title or e.currency} ({e.impact_level})" for e in relevant[:5]
        )
        evidence = (
            f"Primary event: {primary.title or primary.currency}",
            f"Category: {category}",
            f"Posture: {posture}",
            "News provides context — does not veto trades",
        )

        return NewsContextResult(
            symbol=symbol_key,
            active_category=category,
            news_posture=posture,
            context_score=self._context_score(category, primary.impact_level, nearby),
            volatility_multiplier=vol_mult,
            size_multiplier=size_mult,
            directional_hint=hint,
            nearby_event=nearby,
            explanation=(
                f"{category.upper()} context — {posture.replace('_', ' ')}; "
                f"size x{size_mult:.2f}, vol x{vol_mult:.2f}"
            ),
            trade_opportunity=opportunity,
            events_considered=event_names,
            evidence=evidence,
        )

    def _relevant_events(
        self,
        events: list[NewsEvent],
        symbol: str,
        moment: datetime,
    ) -> list[NewsEvent]:
        window_start = moment - timedelta(minutes=self.config.context_before_minutes)
        window_end = moment + timedelta(minutes=self.config.context_after_minutes)
        relevant: list[NewsEvent] = []
        for event in events:
            event_time = self._parse_time(event.news_time)
            if not (window_start <= event_time <= window_end):
                continue
            if not self._symbol_affected(symbol, event.currency):
                continue
            relevant.append(event)
        relevant.sort(key=lambda e: abs((self._parse_time(e.news_time) - moment).total_seconds()))
        return relevant

    @classmethod
    def _categorize(cls, event: NewsEvent) -> NewsCategory:
        text = f"{event.title or ''} {event.currency}".lower()
        for category, keywords in cls._CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return category
        return "general"

    @staticmethod
    def _is_imminent(event: NewsEvent, moment: datetime) -> bool:
        event_time = NewsContextEngine._parse_time(event.news_time)
        delta = abs((event_time - moment).total_seconds()) / 60.0
        return delta <= 45

    def _posture(
        self,
        category: NewsCategory,
        impact: NewsImpactLevel,
        nearby: bool,
    ) -> tuple[NewsPosture, float, float, Literal["bullish", "bearish", "neutral"]]:
        size_map = {
            "nfp": self.config.nfp_size_multiplier,
            "cpi": self.config.cpi_size_multiplier,
            "fomc": self.config.fomc_size_multiplier,
            "rates": self.config.rates_size_multiplier,
            "geopolitical": self.config.geo_size_multiplier,
            "general": 0.90,
            "none": 1.0,
        }
        size_mult = size_map.get(category, 0.90)
        if impact == "high":
            vol_mult = 1.35 if nearby else 1.20
        elif impact == "medium":
            vol_mult = 1.15 if nearby else 1.05
        else:
            vol_mult = 1.05

        if category in {"nfp", "cpi", "fomc"} and nearby:
            posture: NewsPosture = "elevated_volatility"
        elif category == "geopolitical":
            posture = "directional_bias"
            hint: Literal["bullish", "bearish", "neutral"] = "neutral"
            return posture, vol_mult, size_mult, hint
        elif category == "rates":
            posture = "directional_bias"
        else:
            posture = "range_expected" if not nearby else "elevated_volatility"

        hint = "neutral"
        return posture, vol_mult, size_mult, hint

    @staticmethod
    def _context_score(category: NewsCategory, impact: NewsImpactLevel, nearby: bool) -> int:
        base = {"nfp": 85, "cpi": 80, "fomc": 90, "rates": 70, "geopolitical": 75, "general": 55, "none": 50}
        score = base.get(category, 55)
        if impact == "high":
            score += 8
        if nearby:
            score += 5
        return min(100, score)

    @staticmethod
    def _trade_opportunity(
        category: NewsCategory,
        posture: NewsPosture,
        nearby: bool,
        hint: str,
    ) -> str:
        if category == "none":
            return "Trade structure — no macro overlay"
        if nearby and category == "nfp":
            return "NFP imminent — scout post-release momentum with reduced size, not flat"
        if nearby and category == "cpi":
            return "CPI imminent — inflation surprise trades; use wider stops, probe size"
        if nearby and category == "fomc":
            return "FOMC context — expect volatility expansion; trend or fade first spike"
        if category == "geopolitical":
            return "Geopolitical shock — safe-haven flows; Gold/JPY/CHF scout opportunities"
        if category == "rates":
            return "Rates context — USD and bond-sensitive pairs offer directional edges"
        if posture == "elevated_volatility":
            return "Elevated vol — reduce size, widen targets; volatility IS the opportunity"
        return "Macro context active — adjust size, keep trading valid structure"

    @staticmethod
    def _parse_time(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _symbol_affected(symbol: str, currency: str) -> bool:
        cur = currency.strip().upper()
        sym = symbol.strip().upper()
        if sym in {"XAUUSD", "GOLD"}:
            return cur in {"USD", "XAU", "GOLD"}
        return cur in sym[:3] or cur in sym[3:6]


__all__ = [
    "NewsCategory",
    "NewsContextConfig",
    "NewsContextEngine",
    "NewsContextResult",
    "NewsPosture",
]
