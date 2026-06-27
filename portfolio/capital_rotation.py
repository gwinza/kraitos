"""Capital rotation — shift preferences toward improving archetypes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

RotationBias = Literal["favor", "neutral", "reduce", "avoid"]


@dataclass(frozen=True)
class ArchetypeRotation:
    """Rotation preference for one symbol/mode."""

    symbol: str
    mode: str
    bias: RotationBias
    risk_multiplier: float
    rolling_pf: float
    rolling_avg_r: float
    recent_dd_pct: float
    trade_count: int
    reason: str


class CapitalRotationEngine:
    """Rotate capital every 50-100 trades toward high-PF archetypes."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        rotation_interval: int = 75,
        min_trades_for_rotation: int = 50,
    ) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self.rotation_interval = rotation_interval
        self.min_trades_for_rotation = min_trades_for_rotation
        self._trade_counter = 0
        self._last_rotation_at = 0
        self._preferences: dict[tuple[str, str], ArchetypeRotation] = {}
        self._rolling_stats: dict[tuple[str, str], dict] = defaultdict(dict)

    def record_trade(
        self,
        *,
        symbol: str,
        mode: str,
        result: str,
        r_multiple: float,
        drawdown_pct: float,
    ) -> None:
        key = (symbol.strip().upper(), mode.strip().lower())
        stats = self._rolling_stats.setdefault(
            key,
            {"wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0, "r_sum": 0.0, "count": 0, "max_dd": 0.0},
        )
        stats["count"] += 1
        stats["r_sum"] += r_multiple
        stats["max_dd"] = max(stats["max_dd"], drawdown_pct)
        if result == "win":
            stats["wins"] += 1
            stats["gross_win"] += abs(r_multiple)
        elif result == "loss":
            stats["losses"] += 1
            stats["gross_loss"] += abs(r_multiple)

        self._trade_counter += 1
        if self._trade_counter - self._last_rotation_at >= self.rotation_interval:
            self.rotate()

    def rotate(self) -> dict[tuple[str, str], ArchetypeRotation]:
        """Recompute rotation preferences from rolling stats."""
        self._last_rotation_at = self._trade_counter
        preferences: dict[tuple[str, str], ArchetypeRotation] = {}

        for key, stats in self._rolling_stats.items():
            symbol, mode = key
            count = stats["count"]
            if count < 5:
                preferences[key] = ArchetypeRotation(
                    symbol=symbol,
                    mode=mode,
                    bias="neutral",
                    risk_multiplier=1.0,
                    rolling_pf=1.0,
                    rolling_avg_r=0.0,
                    recent_dd_pct=stats["max_dd"],
                    trade_count=count,
                    reason="Insufficient sample",
                )
                continue

            gross_loss = stats["gross_loss"] if stats["gross_loss"] > 0 else 0.01
            pf = stats["gross_win"] / gross_loss
            avg_r = stats["r_sum"] / count
            dd = stats["max_dd"]

            if pf >= 2.0 and avg_r >= 0.15 and dd < 8.0:
                bias: RotationBias = "favor"
                mult = 1.15
                reason = f"High PF {pf:.2f}, avg R {avg_r:+.2f}"
            elif pf >= 1.5 and avg_r >= 0.05:
                bias = "neutral"
                mult = 1.0
                reason = f"Stable PF {pf:.2f}"
            elif pf < 1.0 or avg_r < -0.05:
                bias = "reduce"
                mult = 0.6
                reason = f"Deteriorating PF {pf:.2f}, avg R {avg_r:+.2f}"
            elif dd > 12.0:
                bias = "reduce"
                mult = 0.5
                reason = f"High DD {dd:.1f}%"
            else:
                bias = "neutral"
                mult = 0.85
                reason = f"Marginal PF {pf:.2f}"

            if pf < 0.8 and count >= 20 and avg_r < -0.1:
                bias = "avoid"
                mult = 0.25
                reason = f"All modes failing PF {pf:.2f}"

            preferences[key] = ArchetypeRotation(
                symbol=symbol,
                mode=mode,
                bias=bias,
                risk_multiplier=mult,
                rolling_pf=pf,
                rolling_avg_r=avg_r,
                recent_dd_pct=dd,
                trade_count=count,
                reason=reason,
            )

        self._preferences = preferences
        return preferences

    def risk_multiplier(self, symbol: str, mode: str) -> float:
        key = (symbol.strip().upper(), mode.strip().lower())
        pref = self._preferences.get(key)
        if pref is None:
            return 1.0
        if pref.bias == "avoid":
            return pref.risk_multiplier
        return pref.risk_multiplier

    def preferences(self) -> dict[tuple[str, str], ArchetypeRotation]:
        return dict(self._preferences)

    def write_report(self) -> Path | None:
        if self.project_root is None:
            return None
        logs = self.project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Capital Rotation Report",
            "",
            f"**Generated:** {now}",
            f"**Trade counter:** {self._trade_counter}",
            f"**Last rotation at:** {self._last_rotation_at}",
            "",
            "| Symbol | Mode | Bias | PF | Avg R | DD | Mult | Reason |",
            "|--------|------|------|-----|-------|-----|------|--------|",
        ]
        for (symbol, mode), pref in sorted(self._preferences.items()):
            lines.append(
                f"| {symbol} | {mode} | {pref.bias} | {pref.rolling_pf:.2f} | "
                f"{pref.rolling_avg_r:+.2f} | {pref.recent_dd_pct:.1f}% | "
                f"{pref.risk_multiplier:.0%} | {pref.reason[:40]} |"
            )
        path = logs / "capital_rotation_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
