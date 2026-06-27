"""Currency-leg exposure control for FX portfolio construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from portfolio.currency_strength_engine import PairStrengthAnalysis, TRACKED_CURRENCIES
from risk.models import PortfolioState, TradeSide

ExposureAction = Literal["allow", "scale", "reject"]

NORMAL_MAX_CURRENCY_EXPOSURE = 0.40
EXCEPTIONAL_MAX_CURRENCY_EXPOSURE = 0.60


@dataclass(frozen=True)
class CurrencyExposureSnapshot:
    """Net portfolio exposure by individual currency."""

    currency_net: dict[str, float]
    total_gross: float
    dominant_currency: str | None
    dominant_share: float
    independent_ideas: int
    theme_exposure: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "currency_net": {k: round(v, 4) for k, v in self.currency_net.items()},
            "total_gross": round(self.total_gross, 4),
            "dominant_currency": self.dominant_currency,
            "dominant_share": round(self.dominant_share, 3),
            "independent_ideas": self.independent_ideas,
            "theme_exposure": {k: round(v, 4) for k, v in self.theme_exposure.items()},
        }


@dataclass(frozen=True)
class ExposureDecision:
    """Decision after simulating a new trade against current currency exposure."""

    symbol: str
    side: TradeSide
    action: ExposureAction
    scale_multiplier: float
    current: CurrencyExposureSnapshot
    projected: CurrencyExposureSnapshot
    concentration_limit: float
    portfolio_fit: float
    independent_idea: bool
    trade_theme: str
    theme_confidence: float
    justification_required: bool
    reason: str

    @property
    def allow_trade(self) -> bool:
        return self.action != "reject"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "action": self.action,
            "scale_multiplier": round(self.scale_multiplier, 3),
            "current": self.current.to_dict(),
            "projected": self.projected.to_dict(),
            "concentration_limit": round(self.concentration_limit, 2),
            "portfolio_fit": round(self.portfolio_fit, 2),
            "independent_idea": self.independent_idea,
            "trade_theme": self.trade_theme,
            "theme_confidence": round(self.theme_confidence, 2),
            "justification_required": self.justification_required,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AdaptiveConviction:
    """Human portfolio-manager conviction decomposition."""

    pair_conviction: float
    currency_conviction: float
    portfolio_fit: float
    final_conviction: float
    dialogue: tuple[str, ...]
    invalidators: tuple[str, ...]
    reward_worth_risk: bool

    def to_dict(self) -> dict:
        return {
            "pair_conviction": round(self.pair_conviction, 2),
            "currency_conviction": round(self.currency_conviction, 2),
            "portfolio_fit": round(self.portfolio_fit, 2),
            "final_conviction": round(self.final_conviction, 2),
            "dialogue": list(self.dialogue),
            "invalidators": list(self.invalidators),
            "reward_worth_risk": self.reward_worth_risk,
        }


class ExposureEngine:
    """Simulate currency concentration before adding a new FX trade."""

    def __init__(
        self,
        *,
        normal_limit: float = NORMAL_MAX_CURRENCY_EXPOSURE,
        exceptional_limit: float = EXCEPTIONAL_MAX_CURRENCY_EXPOSURE,
    ) -> None:
        self.normal_limit = normal_limit
        self.exceptional_limit = exceptional_limit
        self._position_themes: dict[str, str] = {}

    def snapshot(
        self,
        portfolio: PortfolioState,
        *,
        position_themes: dict[str, str] | None = None,
    ) -> CurrencyExposureSnapshot:
        themes = position_themes or self._position_themes
        currency_net = {currency: 0.0 for currency in TRACKED_CURRENCIES}
        theme_exposure: dict[str, float] = {}
        balance = max(portfolio.balance, 1.0)

        for position in portfolio.open_positions:
            base, quote = _pair_currencies(position.symbol)
            if base is None or quote is None:
                continue
            sign = 1.0 if position.side == "buy" else -1.0
            weight = position.risk_amount / balance
            currency_net[base] = currency_net.get(base, 0.0) + sign * weight
            currency_net[quote] = currency_net.get(quote, 0.0) - sign * weight
            theme = themes.get(position.symbol, _fallback_theme(position.symbol, position.side))
            theme_exposure[theme] = theme_exposure.get(theme, 0.0) + weight

        return _snapshot_from_net(currency_net, theme_exposure)

    def evaluate_trade(
        self,
        *,
        portfolio: PortfolioState,
        symbol: str,
        side: TradeSide,
        proposed_risk_pct: float,
        pair_analysis: PairStrengthAnalysis | None = None,
        exceptional_conviction: bool = False,
    ) -> ExposureDecision:
        normalized = _normalize_symbol(symbol)
        current = self.snapshot(portfolio)
        base, quote = _pair_currencies(normalized)
        if base is None or quote is None:
            return ExposureDecision(
                symbol=normalized,
                side=side,
                action="allow",
                scale_multiplier=1.0,
                current=current,
                projected=current,
                concentration_limit=self.normal_limit,
                portfolio_fit=0.0,
                independent_idea=True,
                trade_theme="unknown",
                theme_confidence=0.0,
                justification_required=False,
                reason="Non-FX or unsupported currency symbol",
            )

        sign = 1.0 if side == "buy" else -1.0
        risk_weight = max(0.0, proposed_risk_pct) / 100.0
        trade_theme = (
            pair_analysis.trade_theme
            if pair_analysis is not None
            else _fallback_theme(normalized, side)
        )
        theme_confidence = pair_analysis.theme_confidence if pair_analysis else 0.5
        projected_net = dict(current.currency_net)
        projected_net[base] = projected_net.get(base, 0.0) + sign * risk_weight
        projected_net[quote] = projected_net.get(quote, 0.0) - sign * risk_weight
        projected_themes = dict(current.theme_exposure)
        projected_themes[trade_theme] = projected_themes.get(trade_theme, 0.0) + risk_weight
        projected = _snapshot_from_net(projected_net, projected_themes)

        limit = self.exceptional_limit if exceptional_conviction else self.normal_limit
        action: ExposureAction = "allow"
        scale = 1.0
        reasons: list[str] = []
        max_projected = projected.dominant_share
        independent_idea = trade_theme not in current.theme_exposure

        if max_projected > self.exceptional_limit:
            action = "reject"
            scale = 0.0
            reasons.append(
                f"{projected.dominant_currency} would dominate {max_projected:.0%}"
            )
        elif max_projected > limit:
            action = "scale"
            scale = max(0.10, limit / max(max_projected, 1e-9))
            reasons.append(
                f"{projected.dominant_currency} concentration {max_projected:.0%} over {limit:.0%}"
            )
        elif max_projected > self.normal_limit * 0.85:
            action = "scale"
            scale = 0.75
            reasons.append(
                f"{projected.dominant_currency} nearing concentration limit"
            )

        if not independent_idea:
            scale = min(scale, 0.85)
            if action == "allow":
                action = "scale"
            reasons.append(f"Adds to existing theme: {trade_theme}")

        diversification_delta = projected.independent_ideas - current.independent_ideas
        concentration_penalty = max(0.0, max_projected - current.dominant_share) * 10.0
        portfolio_fit = _clamp(
            (1.0 if independent_idea else -0.5)
            + diversification_delta * 0.5
            - concentration_penalty,
            -3.0,
            3.0,
        )
        justification_required = max_projected > self.normal_limit
        if not reasons:
            reasons.append("Currency exposure remains diversified")

        return ExposureDecision(
            symbol=normalized,
            side=side,
            action=action,
            scale_multiplier=round(scale, 3),
            current=current,
            projected=projected,
            concentration_limit=limit,
            portfolio_fit=round(portfolio_fit, 2),
            independent_idea=independent_idea,
            trade_theme=trade_theme,
            theme_confidence=theme_confidence,
            justification_required=justification_required,
            reason="; ".join(reasons),
        )

    def adaptive_conviction(
        self,
        *,
        symbol: str,
        side: TradeSide,
        pair_conviction: float,
        pair_analysis: PairStrengthAnalysis | None,
        exposure: ExposureDecision,
        expected_r: float | None = None,
    ) -> AdaptiveConviction:
        normalized = _normalize_symbol(symbol)
        base, quote = _pair_currencies(normalized)
        if pair_analysis is None or base is None or quote is None:
            currency_conviction = 0.0
            base_story = "Base currency story unavailable"
            quote_story = "Quote currency story unavailable"
            stronger = "unknown"
        else:
            side_aligned = (
                side == "buy" and pair_analysis.pair_strength > 0
            ) or (side == "sell" and pair_analysis.pair_strength < 0)
            currency_conviction = min(3.0, abs(pair_analysis.pair_strength) / 10.0 * 3.0)
            if not side_aligned:
                currency_conviction *= -1.0
            base_story = f"{base} strength {pair_analysis.base_strength:+.1f}"
            quote_story = f"{quote} strength {pair_analysis.quote_strength:+.1f}"
            stronger = base if pair_analysis.pair_strength > 0 else quote

        final = _clamp(
            pair_conviction + currency_conviction + exposure.portfolio_fit,
            0.0,
            15.0,
        )
        reward_worth_risk = expected_r is None or expected_r >= 1.2 or final >= 10.0
        dialogue = (
            f"What is driving the base currency? {base_story}.",
            f"What is driving the quote currency? {quote_story}.",
            f"Which side is stronger? {stronger}.",
            f"What macro theme explains this? {exposure.trade_theme}.",
            "Am I expressing a new idea? "
            + ("Yes." if exposure.independent_idea else "No, this doubles an existing theme."),
            f"What would invalidate this view? {normalized} relative strength flips against {side}.",
            "Is reward worth portfolio risk? "
            + ("Yes." if reward_worth_risk and exposure.allow_trade else "No."),
        )
        invalidators = (
            "Currency strength spread compresses below 2 points",
            f"{exposure.trade_theme} theme confidence deteriorates",
            f"{exposure.projected.dominant_currency or 'Dominant currency'} concentration exceeds limit",
        )
        return AdaptiveConviction(
            pair_conviction=pair_conviction,
            currency_conviction=round(currency_conviction, 2),
            portfolio_fit=exposure.portfolio_fit,
            final_conviction=round(final, 2),
            dialogue=dialogue,
            invalidators=invalidators,
            reward_worth_risk=reward_worth_risk and exposure.allow_trade,
        )


def _snapshot_from_net(
    currency_net: dict[str, float],
    theme_exposure: dict[str, float],
) -> CurrencyExposureSnapshot:
    gross_by_currency = {currency: abs(value) for currency, value in currency_net.items()}
    total_gross = sum(gross_by_currency.values())
    dominant_currency = None
    dominant_share = 0.0
    if gross_by_currency:
        dominant_currency = max(gross_by_currency, key=gross_by_currency.get)
        dominant_share = gross_by_currency[dominant_currency]
    independent_ideas = sum(1 for value in theme_exposure.values() if value > 0)
    return CurrencyExposureSnapshot(
        currency_net=currency_net,
        total_gross=total_gross,
        dominant_currency=dominant_currency,
        dominant_share=dominant_share,
        independent_ideas=independent_ideas,
        theme_exposure=theme_exposure,
    )


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalpha())[:6]


def _pair_currencies(symbol: str) -> tuple[str | None, str | None]:
    normalized = _normalize_symbol(symbol)
    if len(normalized) < 6:
        return None, None
    base = normalized[:3]
    quote = normalized[3:6]
    if base not in TRACKED_CURRENCIES or quote not in TRACKED_CURRENCIES:
        return None, None
    return base, quote


def _fallback_theme(symbol: str, side: str) -> str:
    base, quote = _pair_currencies(symbol)
    if base is None or quote is None:
        return "unknown"
    stronger = base if side == "buy" else quote
    weaker = quote if side == "buy" else base
    if weaker == "USD":
        return "USD weakness"
    if stronger == "JPY":
        return "JPY risk-off"
    if stronger == "CHF":
        return "CHF defensive demand"
    if stronger in {"AUD", "CAD", "NZD"}:
        return "Commodity rotation"
    if stronger in {"EUR", "GBP"}:
        return "European strength"
    return f"{stronger} over {weaker}"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


__all__ = [
    "AdaptiveConviction",
    "CurrencyExposureSnapshot",
    "ExposureDecision",
    "ExposureEngine",
    "NORMAL_MAX_CURRENCY_EXPOSURE",
    "EXCEPTIONAL_MAX_CURRENCY_EXPOSURE",
]
