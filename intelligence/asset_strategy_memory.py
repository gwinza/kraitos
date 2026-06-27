"""Persist historical strategy fit and asset status per symbol."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from intelligence.asset_trend_analyzer import AssetState

AssetStatus = Literal["APPROVED", "CONDITIONAL", "QUARANTINED", "DISABLED"]
DynamicStrategy = Literal[
    "normal_trend",
    "harvest",
    "breakout_continuation",
    "reduced_risk_harvest",
    "confirmation_heavy_trend",
    "range_scalper",
    "mean_reversion",
    "breakout",
    "momentum_continuation",
    "no_trade",
    "micro_scalp_reduced",
]

MEMORY_FILENAME = "asset_strategy_memory.json"


@dataclass
class SymbolStrategyFit:
    """Historical strategy fit for one symbol."""

    symbol: str
    status: AssetStatus = "APPROVED"
    best_strategy_overall: str = "harvest"
    best_state: AssetState | None = None
    best_strategies_by_state: dict[str, str] = field(default_factory=dict)
    avoid_strategies: list[str] = field(default_factory=list)
    fit_scores: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    last_researched_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "best_strategy_overall": self.best_strategy_overall,
            "best_state": self.best_state,
            "best_strategies_by_state": self.best_strategies_by_state,
            "avoid_strategies": self.avoid_strategies,
            "fit_scores": {k: round(v, 4) for k, v in self.fit_scores.items()},
            "notes": self.notes,
            "last_researched_at": self.last_researched_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SymbolStrategyFit:
        return cls(
            symbol=str(raw.get("symbol", "")),
            status=raw.get("status", "APPROVED"),  # type: ignore[arg-type]
            best_strategy_overall=str(raw.get("best_strategy_overall", "harvest")),
            best_state=raw.get("best_state"),  # type: ignore[arg-type]
            best_strategies_by_state={
                str(k): str(v) for k, v in raw.get("best_strategies_by_state", {}).items()
            },
            avoid_strategies=[str(s) for s in raw.get("avoid_strategies", [])],
            fit_scores={str(k): float(v) for k, v in raw.get("fit_scores", {}).items()},
            notes=str(raw.get("notes", "")),
            last_researched_at=raw.get("last_researched_at"),
        )


class AssetStrategyMemory:
    """Load/save strategy fit memory and provide lookup helpers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / "logs" / MEMORY_FILENAME
        self._symbols: dict[str, SymbolStrategyFit] = {}
        self._generated_at: str | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._symbols = {}
            return
        with self.path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        self._generated_at = raw.get("generated_at")
        self._symbols = {
            str(symbol).upper(): SymbolStrategyFit.from_dict(entry)
            for symbol, entry in raw.get("symbols", {}).items()
        }

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": {key: fit.to_dict() for key, fit in sorted(self._symbols.items())},
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        self._generated_at = payload["generated_at"]
        return self.path

    def get(self, symbol: str) -> SymbolStrategyFit | None:
        return self._symbols.get(symbol.strip().upper())

    def get_or_create(self, symbol: str) -> SymbolStrategyFit:
        key = symbol.strip().upper()
        if key not in self._symbols:
            self._symbols[key] = SymbolStrategyFit(symbol=key)
        return self._symbols[key]

    def update(self, fit: SymbolStrategyFit) -> None:
        self._symbols[fit.symbol.strip().upper()] = fit

    def preferred_strategy(self, symbol: str, state: AssetState) -> str | None:
        fit = self.get(symbol)
        if fit is None:
            return None
        return fit.best_strategies_by_state.get(state) or fit.best_strategy_overall

    def asset_allowed(self, symbol: str) -> tuple[bool, str, AssetStatus]:
        fit = self.get(symbol)
        if fit is None:
            return True, "No historical fit data", "APPROVED"
        if fit.status == "DISABLED":
            return False, fit.notes or "Asset disabled after strategy-fit review", fit.status
        if fit.status == "QUARANTINED":
            return False, fit.notes or "Asset quarantined pending review", fit.status
        return True, fit.notes or "Asset allowed", fit.status

    def risk_multiplier_for_status(self, symbol: str) -> float:
        fit = self.get(symbol)
        if fit is None:
            return 1.0
        return {
            "APPROVED": 1.0,
            "CONDITIONAL": 0.5,
            "QUARANTINED": 0.0,
            "DISABLED": 0.0,
        }[fit.status]

    def all_symbols(self) -> dict[str, SymbolStrategyFit]:
        return dict(self._symbols)
