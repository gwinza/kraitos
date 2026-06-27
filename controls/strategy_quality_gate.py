"""Runtime strategy quality filters derived from conservative validation."""



from __future__ import annotations



import json

from dataclasses import dataclass, field

from pathlib import Path

from typing import Any



FILTERS_PATH = "strategy_quality_filters.json"

PF_QUARANTINE = 1.1

DRAWDOWN_STRICT_PCT = 10.0





def load_strategy_quality_filters(project_root: Path) -> dict[str, Any] | None:

    """Load filters JSON if present."""

    path = project_root / "logs" / FILTERS_PATH

    if not path.exists():

        return None

    with path.open(encoding="utf-8") as handle:

        return json.load(handle)





@dataclass

class StrategyQualityGate:

    """Apply symbol/regime/mode filters and adaptive risk multipliers."""



    disabled_symbols: frozenset[str] = field(default_factory=frozenset)

    quarantined_symbol_modes: frozenset[str] = field(default_factory=frozenset)

    disabled_regimes: frozenset[str] = field(default_factory=frozenset)

    symbol_risk_multipliers: dict[str, float] = field(default_factory=dict)

    drawdown_strict_pct: float = DRAWDOWN_STRICT_PCT

    pf_quarantine: float = PF_QUARANTINE

    enabled: bool = False



    @classmethod

    def from_project(cls, project_root: Path) -> StrategyQualityGate:

        raw = load_strategy_quality_filters(project_root)

        if not raw:

            return cls(enabled=False)

        return cls.from_dict(raw)



    @classmethod

    def from_dict(cls, raw: dict[str, Any]) -> StrategyQualityGate:

        thresholds = raw.get("thresholds", {})

        return cls(

            disabled_symbols=frozenset(str(s).upper() for s in raw.get("disabled_symbols", [])),

            quarantined_symbol_modes=frozenset(raw.get("quarantined_symbol_modes", [])),

            disabled_regimes=frozenset(str(r).lower() for r in raw.get("disabled_regimes", [])),

            symbol_risk_multipliers={

                str(k).upper(): float(v) for k, v in raw.get("symbol_risk_multipliers", {}).items()

            },

            drawdown_strict_pct=float(thresholds.get("drawdown_strict_pct", DRAWDOWN_STRICT_PCT)),

            pf_quarantine=float(thresholds.get("pf_quarantine", PF_QUARANTINE)),

            enabled=True,

        )



    def symbol_allowed(self, symbol: str) -> tuple[bool, str]:

        if not self.enabled:

            return True, "Strategy quality filters disabled"

        key = symbol.strip().upper()

        if key in self.disabled_symbols:

            return False, f"Symbol {key} disabled (negative expectancy or PF < {self.pf_quarantine})"

        multiplier = self.symbol_risk_multipliers.get(key, 1.0)

        if multiplier <= 0:

            return False, f"Symbol {key} quarantined (adaptive risk zero)"

        return True, "Symbol allowed"



    def symbol_mode_allowed(self, symbol: str, mode: str) -> tuple[bool, str]:

        if not self.enabled:

            return True, "ok"

        key = f"{symbol.strip().upper()}:{mode.strip().lower()}"

        if key in self.quarantined_symbol_modes:

            return False, f"Quarantined {key} (PF < {self.pf_quarantine})"

        return True, "ok"



    def regime_allowed(self, regime: str) -> tuple[bool, str]:

        if not self.enabled:

            return True, "ok"

        label = regime.strip().lower()

        if label in self.disabled_regimes:

            return False, f"Regime {label} disabled (negative expectancy)"

        return True, "ok"



    def risk_multiplier(self, symbol: str) -> float:

        if not self.enabled:

            return 1.0

        key = symbol.strip().upper()

        if key in self.disabled_symbols:

            return 0.0

        return max(0.0, min(1.0, self.symbol_risk_multipliers.get(key, 1.0)))



    def strict_confirmation(self, portfolio_drawdown_pct: float) -> bool:

        return self.enabled and portfolio_drawdown_pct >= self.drawdown_strict_pct



    def min_bias_confidence(self, base: float, portfolio_drawdown_pct: float) -> float:

        if self.strict_confirmation(portfolio_drawdown_pct):

            return min(0.95, base + 0.15)

        return base



    def min_structure_swings(self, base: int, portfolio_drawdown_pct: float) -> int:

        if self.strict_confirmation(portfolio_drawdown_pct):

            return base + 1

        return base



    @property

    def filters_path(self) -> str:

        return FILTERS_PATH


