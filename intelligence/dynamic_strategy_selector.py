"""Select the best strategy per asset based on trend state and historical fit."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from loguru import logger

from config.settings import TradeMode
from typing import TYPE_CHECKING

from intelligence.asset_strategy_memory import AssetStrategyMemory, DynamicStrategy
from intelligence.asset_trend_analyzer import AssetState, AssetTrendSnapshot

if TYPE_CHECKING:
    from council.opportunity_hunter_council import CouncilConsensus
    from intelligence.market_story_engine import MarketStoryResult
    from intelligence.narrative_forecast_engine import NarrativeForecastResult
    from intelligence.story_forecast_engine import StoryForecastResult

SWITCH_LOG_COLUMNS = [
    "symbol",
    "timestamp",
    "old_strategy",
    "new_strategy",
    "old_state",
    "new_state",
    "reason",
]

STATE_STRATEGY_MAP: dict[AssetState, dict[str, list[DynamicStrategy]]] = {
    "strong_uptrend": {
        "use": ["normal_trend", "harvest", "breakout_continuation"],
        "avoid": ["mean_reversion"],
    },
    "strong_downtrend": {
        "use": ["normal_trend", "harvest", "breakout_continuation"],
        "avoid": ["mean_reversion"],
    },
    "weak_trend": {
        "use": ["reduced_risk_harvest", "confirmation_heavy_trend"],
        "avoid": ["micro_scalp_reduced"],
    },
    "ranging": {
        "use": ["range_scalper", "mean_reversion"],
        "avoid": ["breakout"],
    },
    "volatile_breakout": {
        "use": ["breakout", "momentum_continuation"],
        "avoid": ["micro_scalp_reduced"],
    },
    "choppy_noise": {
        "use": ["range_scalper", "micro_scalp_reduced"],
        "avoid": ["breakout"],
    },
    "mean_reverting": {
        "use": ["mean_reversion", "range_scalper"],
        "avoid": ["harvest"],
    },
    "low_liquidity": {
        "use": ["no_trade"],
        "avoid": ["harvest", "range_scalper"],
    },
    "unsuitable_now": {
        "use": ["no_trade"],
        "avoid": ["harvest", "breakout", "range_scalper"],
    },
}


@dataclass(frozen=True)
class StrategySelection:
    """Runtime strategy decision for one symbol."""

    symbol: str
    asset_state: AssetState
    selected_strategy: DynamicStrategy
    trade_mode: TradeMode
    allow_harvest: bool
    allow_micro_scalp: bool
    risk_multiplier: float
    require_heavy_confirmation: bool
    reason: str
    switched: bool = False
    asset_status: str = "APPROVED"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_state": self.asset_state,
            "selected_strategy": self.selected_strategy,
            "trade_mode": self.trade_mode,
            "allow_harvest": self.allow_harvest,
            "allow_micro_scalp": self.allow_micro_scalp,
            "risk_multiplier": self.risk_multiplier,
            "require_heavy_confirmation": self.require_heavy_confirmation,
            "reason": self.reason,
            "switched": self.switched,
            "asset_status": self.asset_status,
        }


@dataclass
class _SymbolRuntimeState:
    current_strategy: DynamicStrategy = "no_trade"
    current_state: AssetState = "unsuitable_now"
    pending_strategy: DynamicStrategy | None = None
    pending_state: AssetState | None = None
    pending_count: int = 0
    last_m5_time: datetime | None = None
    last_switch_time: datetime | None = None
    last_selection: StrategySelection | None = None


@dataclass(frozen=True)
class DynamicStrategySelectorConfig:
    """Confirmation and cooldown rules."""

    confirmation_evaluations: int = 2
    switch_cooldown_minutes: int = 30
    reevaluate_on_m5_close: bool = True


class DynamicStrategySelector:
    """Choose and switch strategies based on asset trend and memory."""

    def __init__(
        self,
        project_root: Path,
        *,
        memory: AssetStrategyMemory | None = None,
        config: DynamicStrategySelectorConfig | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.memory = memory or AssetStrategyMemory(project_root)
        self.config = config or DynamicStrategySelectorConfig()
        self._runtime: dict[str, _SymbolRuntimeState] = {}
        self._switch_log_path = self.project_root / "logs" / "strategy_switch_log.csv"
        self._ensure_switch_log()

    def select(
        self,
        snapshot: AssetTrendSnapshot,
        *,
        evaluation_moment: datetime | None = None,
        m5_candle_time: datetime | None = None,
    ) -> StrategySelection:
        symbol = snapshot.symbol.strip().upper()
        runtime = self._runtime.setdefault(symbol, _SymbolRuntimeState())
        now = evaluation_moment or datetime.now(timezone.utc)
        if m5_candle_time is not None:
            runtime.last_m5_time = m5_candle_time

        proposed = self._propose_strategy(snapshot)
        final_strategy, final_state, switched, reason = self._apply_switch_rules(
            symbol,
            runtime,
            proposed_strategy=proposed,
            proposed_state=snapshot.state,
            now=now,
        )

        allowed, status_note, asset_status = self.memory.asset_allowed(symbol)
        status_multiplier = self.memory.risk_multiplier_for_status(symbol)
        selection = self._build_selection(
            snapshot=snapshot,
            strategy=final_strategy,
            state=final_state,
            asset_status=asset_status,
            risk_multiplier=status_multiplier,
            reason=f"{reason}; {status_note}".strip("; "),
            switched=switched,
            allowed=allowed,
        )
        runtime.last_selection = selection
        return selection

    def _propose_strategy(self, snapshot: AssetTrendSnapshot) -> DynamicStrategy:
        state = snapshot.state
        symbol = snapshot.symbol
        mapping = STATE_STRATEGY_MAP.get(state, {"use": ["no_trade"], "avoid": []})
        preferred = self.memory.preferred_strategy(symbol, state)
        candidates = list(mapping["use"])
        avoid = set(mapping.get("avoid", []))
        fit = self.memory.get(symbol)
        if fit is not None:
            avoid.update(fit.avoid_strategies)

        if preferred and preferred not in avoid:
            if preferred in candidates or preferred == "harvest":
                return preferred  # type: ignore[return-value]

        for candidate in candidates:
            if candidate not in avoid:
                return candidate
        return "no_trade"

    def _apply_switch_rules(
        self,
        symbol: str,
        runtime: _SymbolRuntimeState,
        *,
        proposed_strategy: DynamicStrategy,
        proposed_state: AssetState,
        now: datetime,
    ) -> tuple[DynamicStrategy, AssetState, bool, str]:
        if runtime.last_selection is None:
            runtime.current_strategy = proposed_strategy
            runtime.current_state = proposed_state
            return proposed_strategy, proposed_state, False, "Initial strategy selection"

        if (
            proposed_strategy == runtime.current_strategy
            and proposed_state == runtime.current_state
        ):
            runtime.pending_strategy = None
            runtime.pending_state = None
            runtime.pending_count = 0
            return runtime.current_strategy, runtime.current_state, False, "Strategy unchanged"

        if runtime.last_switch_time is not None:
            cooldown = timedelta(minutes=self.config.switch_cooldown_minutes)
            if now - runtime.last_switch_time < cooldown:
                return (
                    runtime.current_strategy,
                    runtime.current_state,
                    False,
                    "Cooldown active after prior strategy switch",
                )

        if (
            runtime.pending_strategy == proposed_strategy
            and runtime.pending_state == proposed_state
        ):
            runtime.pending_count += 1
        else:
            runtime.pending_strategy = proposed_strategy
            runtime.pending_state = proposed_state
            runtime.pending_count = 1

        if runtime.pending_count < self.config.confirmation_evaluations:
            return (
                runtime.current_strategy,
                runtime.current_state,
                False,
                (
                    f"Awaiting confirmation ({runtime.pending_count}/"
                    f"{self.config.confirmation_evaluations}) for {proposed_strategy}"
                ),
            )

        old_strategy = runtime.current_strategy
        old_state = runtime.current_state
        runtime.current_strategy = proposed_strategy
        runtime.current_state = proposed_state
        runtime.pending_strategy = None
        runtime.pending_state = None
        runtime.pending_count = 0
        runtime.last_switch_time = now
        self._log_switch(
            symbol=symbol,
            timestamp=now,
            old_strategy=old_strategy,
            new_strategy=proposed_strategy,
            old_state=old_state,
            new_state=proposed_state,
            reason=f"Confirmed switch after {self.config.confirmation_evaluations} evaluations",
        )
        logger.info(
            f"Strategy switch {symbol}: {old_strategy}/{old_state} -> "
            f"{proposed_strategy}/{proposed_state}"
        )
        return proposed_strategy, proposed_state, True, "Strategy switch confirmed"

    def _build_selection(
        self,
        *,
        snapshot: AssetTrendSnapshot,
        strategy: DynamicStrategy,
        state: AssetState,
        asset_status: str,
        risk_multiplier: float,
        reason: str,
        switched: bool,
        allowed: bool,
    ) -> StrategySelection:
        if not allowed:
            return StrategySelection(
                symbol=snapshot.symbol,
                asset_state=state,
                selected_strategy="no_trade",
                trade_mode="normal",
                allow_harvest=False,
                allow_micro_scalp=False,
                risk_multiplier=0.0,
                require_heavy_confirmation=False,
                reason=reason or "No trade strategy selected",
                switched=switched,
                asset_status=asset_status,
            )
        if strategy == "no_trade":
            return StrategySelection(
                symbol=snapshot.symbol,
                asset_state=state,
                selected_strategy="no_trade",
                trade_mode="normal",
                allow_harvest=False,
                allow_micro_scalp=False,
                risk_multiplier=0.15,
                require_heavy_confirmation=False,
                reason=reason or "Awaiting story opportunity",
                switched=switched,
                asset_status=asset_status,
            )

        trade_mode: TradeMode = "normal"
        allow_harvest = False
        allow_micro_scalp = False
        require_heavy = False
        multiplier = risk_multiplier

        if strategy in {
            "normal_trend",
            "harvest",
            "breakout_continuation",
            "breakout",
            "momentum_continuation",
        }:
            allow_harvest = True
            trade_mode = "harvest"
        elif strategy in {"reduced_risk_harvest"}:
            allow_harvest = True
            trade_mode = "harvest"
            multiplier = min(multiplier, 0.5)
        elif strategy in {"confirmation_heavy_trend"}:
            allow_harvest = True
            trade_mode = "harvest"
            require_heavy = True
        elif strategy in {"range_scalper", "mean_reversion"}:
            allow_micro_scalp = True
            trade_mode = "scalp"
        elif strategy == "micro_scalp_reduced":
            if snapshot.features.spread_to_target_ratio <= 0.25:
                allow_micro_scalp = True
                trade_mode = "scalp"
                multiplier = min(multiplier, 0.5)
            else:
                strategy = "no_trade"
                reason = "Micro scalp blocked: spread too wide for choppy conditions"

        if strategy == "no_trade":
            allow_harvest = False
            allow_micro_scalp = False
            multiplier = 0.0

        return StrategySelection(
            symbol=snapshot.symbol,
            asset_state=state,
            selected_strategy=strategy,
            trade_mode=trade_mode,
            allow_harvest=allow_harvest,
            allow_micro_scalp=allow_micro_scalp,
            risk_multiplier=multiplier,
            require_heavy_confirmation=require_heavy,
            reason=reason,
            switched=switched,
            asset_status=asset_status,
        )

    def _ensure_switch_log(self) -> None:
        self._switch_log_path.parent.mkdir(parents=True, exist_ok=True)
        if self._switch_log_path.exists():
            return
        with self._switch_log_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SWITCH_LOG_COLUMNS)
            writer.writeheader()

    def _log_switch(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        old_strategy: str,
        new_strategy: str,
        old_state: str,
        new_state: str,
        reason: str,
    ) -> None:
        with self._switch_log_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SWITCH_LOG_COLUMNS)
            writer.writerow(
                {
                    "symbol": symbol,
                    "timestamp": timestamp.isoformat(),
                    "old_strategy": old_strategy,
                    "new_strategy": new_strategy,
                    "old_state": old_state,
                    "new_state": new_state,
                    "reason": reason,
                }
            )

    @staticmethod
    def apply_story_forecast(
        selection: StrategySelection,
        *,
        market_story: MarketStoryResult | None = None,
        story_forecast: StoryForecastResult | None = None,
        council: CouncilConsensus | None = None,
        forecast: NarrativeForecastResult | None = None,
    ) -> StrategySelection:
        """Story-first unlock — observers note only, no vote gates."""
        story_clear = (
            market_story is not None
            and market_story.story_clear
            and market_story.opportunity_type is not None
        )
        if not story_clear:
            return selection

        allow_harvest = selection.allow_harvest
        allow_scalp = selection.allow_micro_scalp
        strategy = selection.selected_strategy
        trade_mode = selection.trade_mode
        reason = selection.reason
        risk_mult = max(selection.risk_multiplier, 0.25)

        strategy_map = {
            "pullback_harvest": "harvest",
            "trend_continuation": "normal_trend",
            "compression_breakout": "breakout_continuation",
            "liquidity_sweep_fade": "harvest",
            "mean_reversion_snapback": "mean_reversion",
            "session_momentum": "momentum_continuation",
            "range_scalp": "range_scalper",
            "micro_harvest": "micro_scalp_reduced",
        }
        rec = None
        if story_forecast is not None:
            rec = story_forecast.recommended_strategy
        elif forecast is not None:
            rec = forecast.recommended_strategy
        if rec:
            mapped = strategy_map.get(rec)
            if mapped and not allow_harvest and not allow_scalp:
                if mapped in {"mean_reversion", "range_scalper", "micro_scalp_reduced"}:
                    allow_scalp = True
                    trade_mode = "scalp"
                    strategy = mapped  # type: ignore[assignment]
                else:
                    allow_harvest = True
                    trade_mode = "harvest"
                    strategy = mapped  # type: ignore[assignment]
                edge = council.opportunity_edge if council else market_story.opportunity_type
                reason = f"Story forecast: {edge}; {rec}"

        micro_types = {
            "liquidity_sweep",
            "mean_reversion_snapback",
            "failed_breakout",
            "session_transition",
        }
        if market_story and market_story.opportunity_type in micro_types:
            if not allow_harvest and not allow_scalp:
                allow_scalp = True
                trade_mode = "scalp"
                strategy = "micro_scalp_reduced"
                reason = f"Story micro-edge: {market_story.opportunity_type}"
        elif story_clear and not allow_harvest and not allow_scalp:
            allow_harvest = True
            trade_mode = "harvest"
            strategy = "harvest"
            reason = f"Story opportunity: {market_story.opportunity_type}"

        if strategy == "no_trade" and (allow_harvest or allow_scalp):
            strategy = "micro_scalp_reduced" if allow_scalp else "harvest"
            risk_mult = max(risk_mult, 0.35)

        return StrategySelection(
            symbol=selection.symbol,
            asset_state=selection.asset_state,
            selected_strategy=strategy,
            trade_mode=trade_mode,
            allow_harvest=allow_harvest,
            allow_micro_scalp=allow_scalp,
            risk_multiplier=risk_mult,
            require_heavy_confirmation=False,
            reason=reason,
            switched=selection.switched,
            asset_status=selection.asset_status,
        )

    @staticmethod
    def apply_narrative_council(
        selection: StrategySelection,
        *,
        council: CouncilConsensus | None,
        forecast: NarrativeForecastResult | None,
    ) -> StrategySelection:
        """Backward-compatible alias for story-driven selection."""
        return DynamicStrategySelector.apply_story_forecast(
            selection,
            council=council,
            forecast=forecast,
        )

    def write_dynamic_strategy_report(
        self,
        snapshots: dict[str, AssetTrendSnapshot],
        selections: dict[str, StrategySelection],
    ) -> Path:
        lines = [
            "# Dynamic Strategy Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "| Symbol | Asset state | Selected strategy | Trade mode | Harvest | Scalp | Risk mult | Status | Reason |",
            "|--------|-------------|-------------------|------------|---------|-------|-----------|--------|--------|",
        ]
        for symbol in sorted(snapshots):
            snap = snapshots[symbol]
            sel = selections.get(symbol)
            if sel is None:
                continue
            lines.append(
                f"| {symbol} | {snap.state} | {sel.selected_strategy} | {sel.trade_mode} | "
                f"{'Y' if sel.allow_harvest else 'N'} | {'Y' if sel.allow_micro_scalp else 'N'} | "
                f"{sel.risk_multiplier:.0%} | {sel.asset_status} | {sel.reason[:60]} |"
            )
        path = self.project_root / "logs" / "dynamic_strategy_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
