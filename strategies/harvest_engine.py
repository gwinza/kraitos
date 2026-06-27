"""
Kraitos harvest engine.

Evaluates mandatory and secondary conditions to permit conditional or full
harvest modes with pip targets.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from strategies.models import (
    HarvestContext,
    HarvestDecision,
    HarvestMode,
    MarketContext,
    MultiTimeframeBiasResult,
    RegimeResult,
)

CONDITIONAL_SECONDARY_MIN = 1
FULL_SECONDARY_MIN = 4

CONDITIONAL_PIPS_RANGE = (1.0, 5.0)
FULL_PIPS_RANGE = (3.0, 7.0)
STORY_DRIVEN_PIPS_RANGE = (1.0, 4.0)


@dataclass(frozen=True)
class HarvestEngineConfig:
    """Thresholds for harvest evaluation."""

    min_bias_confidence: float = 0.45
    min_structure_swings: int = 2


class HarvestEngineError(Exception):
    """Raised when harvest inputs are invalid."""


class HarvestEngine:
    """Apply Kraitos harvest rules to strategy context."""

    def __init__(self, config: HarvestEngineConfig | None = None) -> None:
        self.config = config or HarvestEngineConfig()

    def evaluate(self, context: HarvestContext) -> HarvestDecision:
        """
        Evaluate harvest rules and return trade permission.

        Rules:
            - Mandatory failure -> no trade
            - Mandatory pass + 2 secondary -> conditional harvest (1-10 pips)
            - Mandatory pass + 3+ secondary -> full harvest (5-10 pips)
        """
        self._validate_context(context)

        story_driven = context.story_clear and (
            context.opportunity_type is not None or context.price_action_valid
        )

        mandatory_results = self._evaluate_mandatory(context, story_driven=story_driven)
        failed_mandatory = [name for name, passed in mandatory_results if not passed]

        if failed_mandatory and not story_driven:
            reason = (
                "Mandatory conditions failed: "
                + ", ".join(failed_mandatory)
            )
            logger.info(f"Harvest blocked for {context.symbol}: {reason}")
            return HarvestDecision(
                mode="none",
                allowed=False,
                target_pips=0.0,
                reason=reason,
            )

        secondary_results = self._evaluate_secondary(context)
        passed_secondary = [name for name, passed in secondary_results if passed]
        secondary_count = len(passed_secondary)

        min_secondary = CONDITIONAL_SECONDARY_MIN
        if story_driven:
            min_secondary = 1
        if context.council_micro_harvest:
            min_secondary = 1
            if context.volume_momentum_strong and secondary_count == 0:
                passed_secondary = ["council_micro_harvest"]
                secondary_count = 1
        if story_driven and context.price_action_valid and secondary_count == 0:
            passed_secondary = ["story_price_action"]
            secondary_count = 1
        if story_driven and context.volume_momentum_strong and secondary_count < min_secondary:
            passed_secondary = list(passed_secondary) + ["story_volume"]
            secondary_count = len(passed_secondary)

        if secondary_count < min_secondary:
            reason = (
                "Mandatory conditions passed but insufficient secondary support "
                f"({secondary_count}/{min_secondary} required): "
                + ", ".join(passed_secondary) if passed_secondary else "none met"
            )
            logger.info(f"Harvest blocked for {context.symbol}: {reason}")
            return HarvestDecision(
                mode="none",
                allowed=False,
                target_pips=0.0,
                reason=reason,
            )

        if secondary_count >= FULL_SECONDARY_MIN and not story_driven:
            mode: HarvestMode = "full"
            target_pips = self._calculate_target_pips(
                mode=mode,
                secondary_count=secondary_count,
                bias_confidence=context.bias.confidence,
                regime_confidence=context.regime.confidence,
                story_driven=story_driven,
            )
            reason = (
                f"Full harvest approved with {secondary_count} secondary conditions: "
                + ", ".join(passed_secondary)
            )
        else:
            mode = "conditional"
            target_pips = self._calculate_target_pips(
                mode=mode,
                secondary_count=secondary_count,
                bias_confidence=context.bias.confidence,
                regime_confidence=context.regime.confidence,
                story_driven=story_driven,
            )
            reason = (
                f"Conditional harvest approved with {secondary_count} secondary conditions: "
                + ", ".join(passed_secondary)
            )

        logger.info(
            f"Harvest {mode} for {context.symbol}: target={target_pips:.1f} pips"
        )
        return HarvestDecision(
            mode=mode,
            allowed=True,
            target_pips=target_pips,
            reason=reason,
        )

    def _validate_context(self, context: HarvestContext) -> None:
        if not context.symbol.strip():
            raise HarvestEngineError("symbol is required")
        if context.spread_limit <= 0:
            raise HarvestEngineError("spread_limit must be positive")
        if context.current_spread < 0:
            raise HarvestEngineError("current_spread cannot be negative")

    def _evaluate_mandatory(
        self,
        context: HarvestContext,
        *,
        story_driven: bool = False,
    ) -> list[tuple[str, bool]]:
        bias_ok = self._has_directional_bias(context.bias)
        if not bias_ok and story_driven and context.narrative_direction in {"bullish", "bearish"}:
            bias_ok = True
        structure_ok = self._has_valid_structure(context.bias, context.structure)
        if not structure_ok and story_driven and context.structure_supports:
            swings = len(context.structure.swing_highs) + len(context.structure.swing_lows)
            structure_ok = swings >= 2
        return [
            ("directional_bias", bias_ok),
            ("valid_market_structure", structure_ok),
            ("sufficient_liquidity", self._has_sufficient_liquidity(context)),
        ]

    def _evaluate_secondary(
        self,
        context: HarvestContext,
    ) -> list[tuple[str, bool]]:
        pa_support = context.price_action_valid or self._momentum_aligned(
            context.bias, context.structure
        )
        vol_support = context.volume_momentum_strong or self._volatility_aligned(
            context.bias, context.regime
        )
        return [
            ("momentum_alignment", pa_support),
            ("volatility_alignment", vol_support),
            ("session_strength", context.in_active_session),
            ("acceptable_spread", context.current_spread <= context.spread_limit),
            ("correlation_support", context.correlation_support or context.story_clear),
            ("news_fundamental_support", self._fundamental_support(context)),
        ]

    def _has_directional_bias(self, bias: MultiTimeframeBiasResult) -> bool:
        if bias.bias in {"bullish", "bearish"} and bias.confidence >= self.config.min_bias_confidence:
            return True
        if bias.bias == "neutral" and bias.confidence >= 0.40:
            macro_layers = [layer for layer in bias.layers if layer.role == "macro"]
            if macro_layers and all(layer.bias == macro_layers[0].bias for layer in macro_layers):
                return macro_layers[0].bias in {"bullish", "bearish"}
        return False

    def _has_valid_structure(
        self,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
    ) -> bool:
        if len(structure.swing_highs) < self.config.min_structure_swings:
            return False
        if len(structure.swing_lows) < self.config.min_structure_swings:
            return False

        if bias.bias == "bullish":
            return structure.trend == "bullish" or (
                structure.higher_highs and structure.higher_lows
            )
        if bias.bias == "bearish":
            return structure.trend == "bearish" or (
                structure.lower_highs and structure.lower_lows
            )
        return False

    def _has_sufficient_liquidity(self, context: HarvestContext) -> bool:
        if context.news_risk_active:
            return False
        if context.regime.regime in {"low_liquidity", "news_risk"}:
            return False
        return True

    def _momentum_aligned(
        self,
        bias: MultiTimeframeBiasResult,
        structure: MarketContext,
    ) -> bool:
        precision_layers = [
            layer for layer in bias.layers if layer.role == "precision_entry"
        ]
        precision_aligned = any(layer.bias == bias.bias for layer in precision_layers)

        if bias.bias == "bullish":
            structure_aligned = structure.last_bos is not None and structure.last_bos.kind in {
                "bos_bullish",
                "choch_bullish",
            }
            return precision_aligned or structure_aligned or structure.higher_highs

        if bias.bias == "bearish":
            structure_aligned = structure.last_bos is not None and structure.last_bos.kind in {
                "bos_bearish",
                "choch_bearish",
            }
            return precision_aligned or structure_aligned or structure.lower_lows

        return False

    def _volatility_aligned(self, bias: MultiTimeframeBiasResult, regime: RegimeResult) -> bool:
        if regime.regime == "trending":
            return True
        if regime.regime == "ranging" and bias.confidence >= 0.55:
            return True
        return regime.regime not in {"volatile", "unclear", "low_liquidity", "news_risk"}

    def _fundamental_support(self, context: HarvestContext) -> bool:
        """Placeholder for news and fundamental filters."""
        if context.news_risk_active:
            return False
        if context.regime.regime == "news_risk":
            return False
        return context.fundamental_support

    def _calculate_target_pips(
        self,
        *,
        mode: HarvestMode,
        secondary_count: int,
        bias_confidence: float,
        regime_confidence: float,
        story_driven: bool = False,
    ) -> float:
        if story_driven:
            low, high = STORY_DRIVEN_PIPS_RANGE
            strength = (
                0.15
                + min(secondary_count, 3) * 0.08
                + bias_confidence * 0.20
                + regime_confidence * 0.12
            )
        elif mode == "conditional":
            low, high = CONDITIONAL_PIPS_RANGE
            strength = (
                0.20
                + min(secondary_count, 2) * 0.08
                + bias_confidence * 0.22
                + regime_confidence * 0.15
            )
        elif mode == "full":
            low, high = FULL_PIPS_RANGE
            extra = max(0, secondary_count - FULL_SECONDARY_MIN)
            strength = (
                0.30
                + min(extra, 3) * 0.08
                + bias_confidence * 0.20
                + regime_confidence * 0.12
            )
        else:
            return 0.0

        strength = max(0.0, min(1.0, strength))
        target = low + (high - low) * strength
        return round(target, 1)
