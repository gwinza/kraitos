"""Symbol specialisation control — tilt capital toward proven edges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class SymbolSpecialisationProfile:
    """Per-symbol confidence and risk adjustments."""

    symbol: str
    confidence_boost: float = 0.0
    risk_multiplier: float = 1.0
    min_conviction_for_full_risk: float = 0.0
    note: str = ""


# Broker report findings: GBPJPY best, GBPUSD worst.
BROKER_REPORT_OVERRIDES: dict[str, SymbolSpecialisationProfile] = {
    "GBPJPY": SymbolSpecialisationProfile(
        symbol="GBPJPY",
        confidence_boost=8.0,
        risk_multiplier=1.12,
        note="Best-performing pair — confidence weighting increased",
    ),
    "GBPUSD": SymbolSpecialisationProfile(
        symbol="GBPUSD",
        confidence_boost=-6.0,
        risk_multiplier=0.55,
        min_conviction_for_full_risk=78.0,
        note="Worst performer — reduced risk unless setup quality exceptional",
    ),
}


@dataclass(frozen=True)
class SymbolSpecialisationDecision:
    """Applied symbol tilt for conviction sizing."""

    confidence_adjustment: float
    risk_multiplier: float
    explanation: str


class SymbolSpecialisationControl:
    """Apply temporary symbol tilts from broker expectancy findings."""

    def __init__(
        self,
        overrides: dict[str, SymbolSpecialisationProfile] | None = None,
    ) -> None:
        self._overrides = overrides or BROKER_REPORT_OVERRIDES

    def evaluate(
        self,
        *,
        symbol: str,
        conviction_score: float,
        setup_quality: float | None = None,
    ) -> SymbolSpecialisationDecision:
        sym = symbol.strip().upper()
        profile = self._overrides.get(sym)
        if profile is None:
            return SymbolSpecialisationDecision(0.0, 1.0, "")

        quality = setup_quality if setup_quality is not None else conviction_score
        risk_mult = profile.risk_multiplier

        if profile.min_conviction_for_full_risk > 0 and quality < profile.min_conviction_for_full_risk:
            risk_mult = min(risk_mult, 0.55)
            note = (
                f"{sym}: reduced risk {risk_mult:.0%} — "
                f"setup quality {quality:.0f} below {profile.min_conviction_for_full_risk:.0f}"
            )
        else:
            note = profile.note or f"{sym} specialisation applied"

        return SymbolSpecialisationDecision(
            confidence_adjustment=profile.confidence_boost,
            risk_multiplier=risk_mult,
            explanation=note,
        )

    def adjust_conviction_score(self, symbol: str, score: float) -> float:
        """Boost or reduce conviction score for symbol edge."""
        sym = symbol.strip().upper()
        profile = self._overrides.get(sym)
        if profile is None:
            return score
        return max(0.0, min(100.0, score + profile.confidence_boost))


_default_control: SymbolSpecialisationControl | None = None


def get_symbol_specialisation_control() -> SymbolSpecialisationControl:
    """Return shared symbol specialisation controller."""
    global _default_control
    if _default_control is None:
        _default_control = SymbolSpecialisationControl()
    return _default_control


__all__ = [
    "BROKER_REPORT_OVERRIDES",
    "SymbolSpecialisationControl",
    "SymbolSpecialisationDecision",
    "SymbolSpecialisationProfile",
    "get_symbol_specialisation_control",
]
