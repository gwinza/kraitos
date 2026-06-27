"""Catastrophic drawdown protection and diagnostic loss-streak tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from risk.models import DEFAULT_CORRELATION_GROUPS, OpenPosition, PortfolioState, TradeSide

DrawdownTierName = Literal["normal", "defensive", "critical"]


@dataclass(frozen=True)
class DrawdownTier:
    """Risk posture for a drawdown band (diagnostic / advisory only)."""

    name: DrawdownTierName
    risk_multiplier: float
    block_new_entries: bool
    advisory: bool


def tier_for_drawdown(drawdown_pct: float) -> DrawdownTier:
    """Map portfolio drawdown to posture (catastrophic protection only)."""
    if drawdown_pct >= 50.0:
        return DrawdownTier(
            name="critical",
            risk_multiplier=0.0,
            block_new_entries=True,
            advisory=False,
        )
    if drawdown_pct >= 40.0:
        return DrawdownTier(
            name="defensive",
            risk_multiplier=0.10,
            block_new_entries=False,
            advisory=True,
        )
    if drawdown_pct >= 25.0:
        return DrawdownTier(
            name="defensive",
            risk_multiplier=0.50,
            block_new_entries=False,
            advisory=True,
        )
    if drawdown_pct >= 15.0:
        return DrawdownTier(
            name="defensive",
            risk_multiplier=0.75,
            block_new_entries=False,
            advisory=True,
        )
    return DrawdownTier(
        name="normal",
        risk_multiplier=1.0,
        block_new_entries=False,
        advisory=False,
    )


@dataclass
class LossStreakState:
    """Per symbol/mode loss streak tracking (diagnostic only)."""

    consecutive_losses: int = 0
    last_loss_at: datetime | None = None


@dataclass
class DrawdownRiskController:
    """Catastrophic drawdown guard with diagnostic loss-streak tracking."""

    correlation_groups: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_CORRELATION_GROUPS)
    )
    portfolio_scaling_mode: bool = False
    _loss_streaks: dict[tuple[str, str], LossStreakState] = field(
        default_factory=dict, repr=False
    )

    def tier(self, drawdown_pct: float) -> DrawdownTier:
        return tier_for_drawdown(drawdown_pct)

    def drawdown_multiplier(self, drawdown_pct: float) -> float:
        return tier_for_drawdown(drawdown_pct).risk_multiplier

    def clusters_for_symbol(self, symbol: str) -> list[str]:
        normalized = symbol.strip().upper()
        return [
            name
            for name, members in self.correlation_groups.items()
            if normalized in members
        ]

    def cluster_open_count(
        self,
        portfolio: PortfolioState,
        cluster_name: str,
    ) -> int:
        members = set(self.correlation_groups.get(cluster_name, ()))
        return sum(1 for pos in portfolio.open_positions if pos.symbol in members)

    def usd_same_direction_count(
        self,
        portfolio: PortfolioState,
        side: TradeSide,
    ) -> int:
        usd_majors = set(self.correlation_groups.get("usd_majors", ()))
        return sum(
            1
            for pos in portfolio.open_positions
            if pos.symbol in usd_majors and pos.side == side
        )

    def has_correlated_same_direction(
        self,
        portfolio: PortfolioState,
        *,
        symbol: str,
        side: TradeSide,
    ) -> tuple[bool, str | None]:
        normalized = symbol.strip().upper()
        for cluster_name, members in self.correlation_groups.items():
            if normalized not in members:
                continue
            member_set = set(members)
            for pos in portfolio.open_positions:
                if pos.symbol in member_set and pos.symbol != normalized and pos.side == side:
                    return True, (
                        f"Correlated same-direction stacking in '{cluster_name}' "
                        f"({pos.symbol} {pos.side} + {normalized} {side})"
                    )
        return False, None

    def loss_streak_count(self, symbol: str, mode: str) -> int:
        key = (symbol.strip().upper(), mode.strip().lower())
        state = self._loss_streaks.get(key)
        return state.consecutive_losses if state else 0

    def is_paused(
        self,
        symbol: str,
        mode: str,
        evaluation_moment: datetime | None,
    ) -> tuple[bool, str | None]:
        """Loss streaks are logged only — never pause trading."""
        return False, None

    def loss_streak_multiplier(self, symbol: str, mode: str) -> float:
        """Scale risk down on loss streaks — report, don't suppress."""
        streak = self.loss_streak_count(symbol, mode)
        if streak >= 5:
            return 0.50
        if streak >= 3:
            return 0.75
        return 1.0

    def record_trade_result(
        self,
        *,
        symbol: str,
        mode: str,
        result: str,
        evaluation_moment: datetime | None = None,
    ) -> None:
        """Track loss streaks for diagnostics (no enforcement)."""
        if result not in {"win", "loss", "breakeven"}:
            return
        key = (symbol.strip().upper(), mode.strip().lower())
        state = self._loss_streaks.setdefault(key, LossStreakState())
        if result == "loss":
            state.consecutive_losses += 1
            moment = evaluation_moment or datetime.now(timezone.utc)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            state.last_loss_at = moment
        else:
            state.consecutive_losses = 0
            state.last_loss_at = None

    def evaluate_entry(
        self,
        *,
        symbol: str,
        side: TradeSide,
        mode: str,
        portfolio: PortfolioState,
        trend_score: float | None = None,
        trend_quality: str | None = None,
        is_addon: bool = False,
        evaluation_moment: datetime | None = None,
    ) -> tuple[bool, str, float]:
        """
        Evaluate catastrophic drawdown entry constraints.

        Returns (allowed, reason, combined_risk_multiplier).
        """
        drawdown_pct = portfolio.drawdown_pct
        tier = self.tier(drawdown_pct)
        streak_mult = self.loss_streak_multiplier(symbol, mode)

        if tier.block_new_entries:
            return (
                False,
                f"Catastrophic drawdown ({drawdown_pct:.1f}% ≥ 50%) — new entries blocked",
                0.0,
            )

        streak_mult = self.loss_streak_multiplier(symbol, mode)
        combined = max(0.05, min(1.0, streak_mult))

        if streak_mult < 0.999:
            return True, f"Loss streak scale {streak_mult:.0%}", combined

        return True, "Normal risk posture", combined
