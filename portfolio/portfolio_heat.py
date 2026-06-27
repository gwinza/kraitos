"""Portfolio heat monitor — open risk + correlation + concentration."""



from __future__ import annotations



from dataclasses import dataclass

from datetime import datetime, timezone

from pathlib import Path

from typing import Literal



from portfolio.exposure_netting import ExposureNetting

from risk.models import PortfolioState



HeatBand = Literal["low", "moderate", "high", "extreme", "catastrophic"]

HeatAction = Literal[
    "proceed",
    "scale_moderate",
    "scale_high",
    "scale_extreme",
    "scale_catastrophic",
]





@dataclass(frozen=True)

class HeatAssessment:

    """Portfolio heat evaluation."""



    total_heat_pct: float

    open_risk_pct: float

    correlation_heat_pct: float

    concentration_heat_pct: float

    band: HeatBand

    action: HeatAction

    scale_multiplier: float

    reason: str



    def to_dict(self) -> dict:

        return {

            "total_heat_pct": round(self.total_heat_pct, 3),

            "open_risk_pct": round(self.open_risk_pct, 3),

            "correlation_heat_pct": round(self.correlation_heat_pct, 3),

            "concentration_heat_pct": round(self.concentration_heat_pct, 3),

            "band": self.band,

            "action": self.action,

            "scale_multiplier": round(self.scale_multiplier, 3),

            "reason": self.reason,

        }





class PortfolioHeatMonitor:

    """Monitor total portfolio heat — scale sizing, suppress only at catastrophic."""



    def __init__(self, project_root: Path | None = None) -> None:

        self.project_root = project_root.resolve() if project_root else None

        self._netting = ExposureNetting()

        self._latest: HeatAssessment | None = None

        self._scaled_count = 0



    @property

    def scaled_count(self) -> int:

        return self._scaled_count



    def assess(self, portfolio: PortfolioState) -> HeatAssessment:

        exposure = self._netting.compute(portfolio)

        open_risk = exposure.total_open_risk_pct



        max_cluster = max(exposure.cluster_counts.values()) if exposure.cluster_counts else 0

        correlation_heat = max_cluster * 1.5



        max_symbol = (

            max(exposure.symbol_concentration.values())

            if exposure.symbol_concentration

            else 0.0

        )

        concentration_heat = max_symbol * 100.0



        total = open_risk + correlation_heat * 0.5 + concentration_heat * 0.3



        band, action, scale = self._classify(total, open_risk)



        if scale < 0.999:

            self._scaled_count += 1



        assessment = HeatAssessment(

            total_heat_pct=total,

            open_risk_pct=open_risk,

            correlation_heat_pct=correlation_heat,

            concentration_heat_pct=concentration_heat,

            band=band,

            action=action,

            scale_multiplier=scale,

            reason=f"Heat {total:.1f}% ({band}) — {action} {scale:.0%}",

        )

        self._latest = assessment

        return assessment



    @staticmethod

    def _classify(

        total: float,

        open_risk: float,

    ) -> tuple[HeatBand, HeatAction, float]:

        if total >= 14.0 or open_risk >= 12.0:

            return "catastrophic", "scale_catastrophic", 0.10

        if total >= 11.0:

            return "extreme", "scale_extreme", 0.25

        if total >= 9.0:

            return "high", "scale_high", 0.50

        if total >= 7.0:

            return "moderate", "scale_moderate", 0.75

        return "low", "proceed", 1.0



    @property

    def latest(self) -> HeatAssessment | None:

        return self._latest



    def write_report(self) -> Path | None:

        if self.project_root is None:

            return None

        logs = self.project_root / "logs"

        logs.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()

        lines = [

            "# Portfolio Heat Report",

            "",

            f"**Generated:** {now}",

            "",

        ]

        if self._latest is not None:

            h = self._latest

            lines.extend([

                f"- **Total heat:** {h.total_heat_pct:.1f}%",

                f"- **Open risk:** {h.open_risk_pct:.1f}%",

                f"- **Correlation heat:** {h.correlation_heat_pct:.1f}%",

                f"- **Concentration heat:** {h.concentration_heat_pct:.1f}%",

                f"- **Band:** {h.band}",

                f"- **Action:** {h.action}",

                f"- **Scale:** {h.scale_multiplier:.0%}",

                "",

            ])

        lines.extend([

            "## Heat bands",

            "",

            "| Band | Threshold | Scale |",

            "|------|-----------|-------|",

            "| low | <7% | 100% |",

            "| moderate | 7-9% | 75% |",

            "| high | 9-11% | 50% |",

            "| extreme | 11-14% | 25% |",

            "| catastrophic | >14% or open >12% | 10% |",

        ])

        path = logs / "portfolio_heat_report.md"

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return path


