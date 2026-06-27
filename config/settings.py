"""Typed configuration models for Kraitos."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExecutionMode = Literal["simulation", "live"]
TradeMode = Literal["scalp", "harvest", "normal"]
SignalDecision = Literal["TRADE", "NO_TRADE"]


@dataclass(frozen=True)
class TradingSession:
    """A time window during which trading is permitted."""

    name: str
    start: str  # HH:MM (24-hour)
    end: str  # HH:MM (24-hour)
    timezone: str = "UTC"
    days: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri")


@dataclass(frozen=True)
class AccountSettings:
    """Account-level settings."""

    balance: float


@dataclass(frozen=True)
class RiskSettings:
    """Risk management limits."""

    per_trade_pct: float
    max_daily_drawdown_pct: float
    max_open_trades: int
    max_risk_per_symbol_pct: float = 2.0
    max_correlated_exposure_pct: float = 3.0


@dataclass(frozen=True)
class TradingSettings:
    """Trading environment and instrument settings."""

    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    spread_limits: dict[str, float]
    sessions: tuple[TradingSession, ...]
    live_enabled: bool
    paper_enabled: bool
    news_filter_enabled: bool


@dataclass(frozen=True)
class PipelineSettings:
    """Integrated pipeline execution settings."""

    execution_mode: ExecutionMode = "simulation"
    execute_trades: bool = False
    structure_timeframe: str = "H1"
    precision_timeframes: tuple[str, ...] = ("M1", "M5")
    output_json: bool = False
    council_expansion_mode: bool = True
    cognitive_council_mode: bool = True
    picture_theory_mode: bool = True
    market_mind_mode: bool = True
    reality_engine_mode: bool = True


@dataclass(frozen=True)
class KraitosConfig:
    """Root configuration object returned by the loader."""

    account: AccountSettings
    risk: RiskSettings
    trading: TradingSettings
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def simulation_only(self) -> bool:
        """True when the integrated pipeline must not place live orders."""
        return self.pipeline.execution_mode == "simulation" or self.trading.paper_enabled
