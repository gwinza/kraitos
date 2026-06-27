"""
Allocation Firewall Engine — Kraitos capital allocation DNA.

Kraitos does not ask "Can we trade?" — it asks "How much should we allocate?"
Portfolio pressure reduces allocations; it does not eliminate participation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from risk.models import DEFAULT_CORRELATION_GROUPS, OpenPosition, PortfolioState, TradeSide

ALLOCATION_FIREWALL_DNA = """
Kraitos does not ask: "Can we trade?"
Kraitos asks: "How much of this opportunity deserves our capital?"

Risk management is not a gatekeeper — it is a capital allocator.
Good opportunities are scarce; missing valid opportunities is itself a form of risk.
Every valid opportunity deserves some allocation.
""".strip()


@dataclass(frozen=True)
class AllocationOpportunity:
    """Trade opportunity awaiting capital allocation sizing."""

    symbol: str
    side: TradeSide = "buy"
    base_risk_percent: float = 1.0
    harvest_score: float | None = None
    estimated_trade_risk: float = 0.0
    margin_utilization_pct: float | None = None


@dataclass(frozen=True)
class AllocationDecision:
    """Sized participation decision — almost always execute=True for valid opportunities."""

    execute: bool
    risk_percent: float
    allocation_multiplier: float
    explanation: str
    layer_multipliers: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class AllocationFirewallConfig:
    """Configurable allocation layer thresholds."""

    minimum_risk_percent: float = 0.05
    catastrophic_drawdown_pct: float = 50.0
    neutral_harvest_multiplier: float = 0.70

    # Layer 1: Harvest Opportunity Score (score ≥ threshold → multiplier)
    opportunity_tiers: tuple[tuple[float, float], ...] = (
        (90.0, 1.00),
        (85.0, 0.90),
        (80.0, 0.80),
        (75.0, 0.70),
        (70.0, 0.60),
        (60.0, 0.50),
        (0.0, 0.40),
    )

    # Layer 2: open position count upper bounds → multiplier
    portfolio_capacity_tiers: tuple[tuple[int, float], ...] = (
        (5, 1.00),
        (10, 0.80),
        (20, 0.60),
        (30, 0.40),
        (999_999, 0.25),
    )

    # Layer 3: correlated position index (1-based) → multiplier
    correlation_position_multipliers: tuple[float, ...] = (1.0, 0.80, 0.60, 0.40)

    # Layer 4: portfolio drawdown % upper bounds → multiplier
    drawdown_tiers: tuple[tuple[float, float], ...] = (
        (3.0, 1.00),
        (5.0, 0.80),
        (7.0, 0.60),
        (10.0, 0.40),
        (100.0, 0.20),
    )

    # Layer 5: margin utilisation % upper bounds → multiplier
    margin_tiers: tuple[tuple[float, float], ...] = (
        (30.0, 1.00),
        (50.0, 0.80),
        (70.0, 0.60),
        (85.0, 0.40),
        (100.0, 0.20),
    )

    # Supplementary scales (legacy parity — allocation not rejection)
    daily_loss_tiers: tuple[tuple[float, float], ...] = (
        (0.40, 1.00),
        (0.65, 0.75),
        (0.85, 0.50),
        (1.00, 0.25),
        (float("inf"), 0.25),
    )
    symbol_exposure_tiers: tuple[tuple[float, float], ...] = (
        (0.70, 1.00),
        (0.85, 0.75),
        (1.00, 0.50),
        (float("inf"), 0.25),
    )
    max_daily_loss_pct: float = 3.0
    max_risk_per_symbol_pct: float = 2.0
    max_correlated_exposure_pct: float = 3.0


class AllocationFirewallEngine:
    """
    Determine optimal capital allocation for each opportunity.

    Replaces veto-based risk logic with proportional allocation adjustments.
    """

    def __init__(
        self,
        config: AllocationFirewallConfig | None = None,
        correlation_groups: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.config = config or AllocationFirewallConfig()
        self.correlation_groups = correlation_groups or DEFAULT_CORRELATION_GROUPS

    def determine_allocation(
        self,
        opportunity: AllocationOpportunity,
        portfolio_state: PortfolioState,
    ) -> AllocationDecision:
        """Compute final risk allocation — execute=True unless catastrophic."""
        cfg = self.config
        symbol = opportunity.symbol.strip().upper()
        layers: dict[str, float] = {}
        notes: list[str] = []

        dd_pct = portfolio_state.drawdown_pct
        if dd_pct >= cfg.catastrophic_drawdown_pct:
            return AllocationDecision(
                execute=False,
                risk_percent=0.0,
                allocation_multiplier=0.0,
                explanation=(
                    f"Catastrophic drawdown ({dd_pct:.1f}% ≥ "
                    f"{cfg.catastrophic_drawdown_pct:.0f}%) — entries blocked"
                ),
                layer_multipliers={"drawdown": 0.0},
            )

        opp_mult = self._opportunity_multiplier(opportunity.harvest_score)
        layers["opportunity"] = opp_mult
        if opportunity.harvest_score is not None:
            notes.append(f"Harvest Score {opportunity.harvest_score:.0f}")

        open_count = len(portfolio_state.open_positions)
        port_mult = _tier_by_upper_bound(open_count, cfg.portfolio_capacity_tiers)
        layers["portfolio"] = port_mult
        if port_mult < 0.999:
            notes.append("Portfolio crowding reduced exposure")

        corr_mult, corr_note = self._correlation_multiplier(
            symbol,
            portfolio_state.open_positions,
            opportunity.estimated_trade_risk,
            portfolio_state.balance,
        )
        layers["correlation"] = corr_mult
        if corr_note:
            notes.append(corr_note)

        dd_mult = _tier_by_upper_bound(dd_pct, cfg.drawdown_tiers)
        layers["drawdown"] = dd_mult
        if dd_pct >= 3.0:
            notes.append(f"Drawdown {dd_pct:.1f}% reduced exposure")

        margin_pct = opportunity.margin_utilization_pct
        if margin_pct is None:
            margin_pct = getattr(portfolio_state, "margin_utilization_pct", 0.0) or 0.0
        margin_mult = _tier_by_upper_bound(margin_pct, cfg.margin_tiers)
        layers["margin"] = margin_mult
        if margin_pct >= 30.0:
            notes.append(f"Margin usage {margin_pct:.0f}% reduced exposure")

        daily_mult, daily_note = self._daily_loss_multiplier(portfolio_state)
        layers["daily_loss"] = daily_mult
        if daily_note:
            notes.append(daily_note)

        symbol_mult, symbol_note = self._symbol_exposure_multiplier(
            symbol,
            portfolio_state,
            opportunity.estimated_trade_risk,
        )
        layers["symbol_exposure"] = symbol_mult
        if symbol_note:
            notes.append(symbol_note)

        combined = 1.0
        for mult in layers.values():
            combined *= mult
        combined = max(cfg.minimum_risk_percent / max(opportunity.base_risk_percent, 0.01), combined)
        combined = min(1.0, combined)

        base = opportunity.base_risk_percent
        final_risk = max(cfg.minimum_risk_percent, base * combined)

        explanation_parts = notes.copy() if notes else ["Normal allocation posture"]
        explanation_parts.append(f"Final allocation: {final_risk:.2f}%")
        explanation = ". ".join(explanation_parts) + "."

        return AllocationDecision(
            execute=True,
            risk_percent=final_risk,
            allocation_multiplier=combined,
            explanation=explanation,
            layer_multipliers=layers,
        )

    def _opportunity_multiplier(self, harvest_score: float | None) -> float:
        if harvest_score is None:
            return self.config.neutral_harvest_multiplier
        score = float(harvest_score)
        for threshold, mult in self.config.opportunity_tiers:
            if score >= threshold:
                return mult
        return self.config.opportunity_tiers[-1][1]

    def _correlation_multiplier(
        self,
        symbol: str,
        positions: tuple[OpenPosition, ...],
        trade_risk: float,
        balance: float,
    ) -> tuple[float, str]:
        cfg = self.config
        for group_name, members in self.correlation_groups.items():
            if symbol not in members:
                continue
            member_set = set(members)
            cluster_count = sum(1 for pos in positions if pos.symbol in member_set)
            position_index = cluster_count + 1
            idx = min(position_index - 1, len(cfg.correlation_position_multipliers) - 1)
            mult = cfg.correlation_position_multipliers[idx]

            group_risk = sum(pos.risk_amount for pos in positions if pos.symbol in member_set)
            max_group = balance * (cfg.max_correlated_exposure_pct / 100.0)
            if max_group > 0:
                usage = (group_risk + trade_risk) / max_group
                if usage >= 1.0:
                    mult = min(mult, 0.25)
                elif usage >= 0.85:
                    mult = min(mult, 0.50)

            note = ""
            if position_index > 1 or mult < 0.999:
                note = f"{group_name} concentration reduced exposure"
            return mult, note
        return 1.0, ""

    def _daily_loss_multiplier(self, portfolio: PortfolioState) -> tuple[float, str]:
        day_start = portfolio.day_start_balance or portfolio.balance
        if day_start <= 0:
            return 1.0, ""
        max_loss = day_start * (self.config.max_daily_loss_pct / 100.0)
        if max_loss <= 0:
            return 1.0, ""
        used = max(0.0, -portfolio.daily_realized_pnl) / max_loss
        mult = _tier_by_upper_bound(used, self.config.daily_loss_tiers)
        if mult >= 0.999:
            return 1.0, ""
        return mult, f"Daily loss budget {used:.0%} reduced exposure"

    def _symbol_exposure_multiplier(
        self,
        symbol: str,
        portfolio: PortfolioState,
        trade_risk: float,
    ) -> tuple[float, str]:
        symbol_risk = sum(pos.risk_amount for pos in portfolio.open_positions if pos.symbol == symbol)
        max_risk = portfolio.balance * (self.config.max_risk_per_symbol_pct / 100.0)
        if max_risk <= 0:
            return 1.0, ""
        usage = (symbol_risk + trade_risk) / max_risk
        mult = _tier_by_upper_bound(usage, self.config.symbol_exposure_tiers)
        if mult >= 0.999:
            return 1.0, ""
        return mult, "Symbol exposure reduced allocation"


def _tier_by_upper_bound(
    value: float | int,
    tiers: Iterable[tuple[float | int, float]],
) -> float:
    """Return multiplier for the first tier whose upper bound meets or exceeds value."""
    for upper, mult in tiers:
        if value <= upper:
            return mult
    items = list(tiers)
    return items[-1][1] if items else 1.0
