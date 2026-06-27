"""Session intelligence engine — score London, New York, overlap, and Asia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

SessionLabel = Literal["london", "new_york", "overlap", "asia", "off_hours"]


@dataclass(frozen=True)
class SessionScores:
    """Per-session quality scores (0–100)."""

    london: int
    new_york: int
    overlap: int
    asia: int

    def to_dict(self) -> dict:
        return {
            "london": self.london,
            "new_york": self.new_york,
            "overlap": self.overlap,
            "asia": self.asia,
        }


@dataclass(frozen=True)
class SessionIntelligenceResult:
    """Session quality assessment for timing and sizing."""

    symbol: str
    active_session: SessionLabel
    session_quality: int
    session_scores: SessionScores
    volatility_expectation: Literal["high", "moderate", "low"]
    explanation: str
    trade_opportunity: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "active_session": self.active_session,
            "session_quality": self.session_quality,
            "session_scores": self.session_scores.to_dict(),
            "volatility_expectation": self.volatility_expectation,
            "explanation": self.explanation,
            "trade_opportunity": self.trade_opportunity,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class SessionIntelligenceConfig:
    """Default session windows in UTC."""

    london_start: int = 7
    london_end: int = 16
    new_york_start: int = 12
    new_york_end: int = 21
    asia_start: int = 0
    asia_end: int = 8


class SessionIntelligenceEngine:
    """Score trading sessions — improves timing, never blocks opportunity."""

    def __init__(self, config: SessionIntelligenceConfig | None = None) -> None:
        self.config = config or SessionIntelligenceConfig()

    def analyze(
        self,
        *,
        symbol: str = "",
        at_time: datetime | None = None,
    ) -> SessionIntelligenceResult:
        moment = at_time or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        hour = moment.astimezone(timezone.utc).hour

        cfg = self.config
        in_london = cfg.london_start <= hour < cfg.london_end
        in_ny = cfg.new_york_start <= hour < cfg.new_york_end
        in_asia = hour < cfg.asia_end or hour >= 22
        in_overlap = in_london and in_ny

        london_score = 78 if in_london else 55
        ny_score = 80 if in_ny else 52
        overlap_score = 92 if in_overlap else 40
        asia_score = 62 if in_asia else 38

        symbol_key = symbol.strip().upper()
        if symbol_key in {"USDJPY", "AUDJPY", "NZDJPY", "EURJPY", "GBPJPY"}:
            asia_score = min(95, asia_score + 18)
        if symbol_key in {"EURUSD", "GBPUSD", "EURGBP", "XAUUSD", "GOLD"}:
            london_score = min(95, london_score + 12)
            overlap_score = min(98, overlap_score + 8)
        if symbol_key in {"US30", "NAS100", "SPX500", "XAUUSD", "GOLD"}:
            ny_score = min(95, ny_score + 15)

        scores = SessionScores(
            london=london_score,
            new_york=ny_score,
            overlap=overlap_score,
            asia=asia_score,
        )

        if in_overlap:
            active: SessionLabel = "overlap"
            quality = overlap_score
            vol: Literal["high", "moderate", "low"] = "high"
        elif in_london:
            active = "london"
            quality = london_score
            vol = "moderate"
        elif in_ny:
            active = "new_york"
            quality = ny_score
            vol = "high"
        elif in_asia:
            active = "asia"
            quality = asia_score
            vol = "moderate"
        else:
            active = "off_hours"
            quality = 42
            vol = "low"

        opportunity = self._trade_opportunity(active, quality, symbol_key)
        evidence = (
            f"UTC hour {hour}",
            f"active session: {active}",
            f"volatility expectation: {vol}",
        )

        return SessionIntelligenceResult(
            symbol=symbol_key,
            active_session=active,
            session_quality=quality,
            session_scores=scores,
            volatility_expectation=vol,
            explanation=f"Session quality {quality}/100 — {active.replace('_', ' ')} active",
            trade_opportunity=opportunity,
            evidence=evidence,
        )

    @staticmethod
    def _trade_opportunity(session: SessionLabel, quality: int, symbol: str) -> str:
        if session == "overlap":
            return "Peak liquidity — trend continuation and breakout setups favoured"
        if session == "london":
            return "London drive — scout directional moves and sweep setups"
        if session == "new_york":
            return "NY session — momentum and news-driven continuation trades"
        if session == "asia":
            if "JPY" in symbol:
                return "Asia session — JPY pairs offer range and carry setups"
            return "Asia session — range scout with reduced size unless JPY pair"
        if quality >= 50:
            return "Off-hours — probe only with tight risk; prefer limit entries"
        return "Off-hours — scout micro edges at reduced size, never skip entirely"


__all__ = [
    "SessionIntelligenceConfig",
    "SessionIntelligenceEngine",
    "SessionIntelligenceResult",
    "SessionLabel",
    "SessionScores",
]
