"""Global portfolio risk budget with heat zones and daily loss scaling."""



from __future__ import annotations



from dataclasses import dataclass

from datetime import datetime, timezone

from pathlib import Path

from typing import Literal



from portfolio.opportunity_score import OpportunityAllocationScore

from risk.models import OpenPosition, PortfolioState



HeatZone = Literal["normal", "elevated", "max", "over_limit"]

DailyLossZone = Literal["normal", "warning", "elevated", "severe", "catastrophic"]





@dataclass(frozen=True)

class RiskBudgetDecision:

    """Risk budget allocation for one opportunity."""



    symbol: str

    heat_zone: HeatZone

    daily_loss_zone: DailyLossZone

    portfolio_heat_pct: float

    oas_tier: str

    oas_multiplier: float

    heat_multiplier: float

    daily_loss_multiplier: float

    combined_multiplier: float

    allocated_risk_pct: float

    allow_trade: bool

    reason: str



    def to_dict(self) -> dict:

        return {

            "symbol": self.symbol,

            "heat_zone": self.heat_zone,

            "daily_loss_zone": self.daily_loss_zone,

            "portfolio_heat_pct": round(self.portfolio_heat_pct, 3),

            "oas_tier": self.oas_tier,

            "oas_multiplier": round(self.oas_multiplier, 3),

            "heat_multiplier": round(self.heat_multiplier, 3),

            "daily_loss_multiplier": round(self.daily_loss_multiplier, 3),

            "combined_multiplier": round(self.combined_multiplier, 3),

            "allocated_risk_pct": round(self.allocated_risk_pct, 3),

            "allow_trade": self.allow_trade,

            "reason": self.reason,

        }





def _open_risk_pct(portfolio: PortfolioState) -> float:

    if portfolio.balance <= 0:

        return 0.0

    total_risk = sum(pos.risk_amount for pos in portfolio.open_positions)

    return total_risk / portfolio.balance * 100.0





def _heat_zone(heat_pct: float) -> HeatZone:

    if heat_pct >= 12.0:

        return "over_limit"

    if heat_pct >= 10.0:

        return "max"

    if heat_pct >= 8.0:

        return "elevated"

    return "normal"





def _heat_multiplier(zone: HeatZone) -> float:

    return {

        "normal": 1.0,

        "elevated": 0.75,

        "max": 0.50,

        "over_limit": 0.25,

    }[zone]





def _daily_loss_zone(

    portfolio: PortfolioState,

    max_daily_loss_pct: float = 3.0,

) -> tuple[DailyLossZone, float]:

    """Daily loss: scale don't stop until catastrophic."""

    day_start = portfolio.day_start_balance or portfolio.balance

    if day_start <= 0:

        return "normal", 1.0



    max_daily_loss = day_start * (max_daily_loss_pct / 100.0)

    current_loss = max(0.0, -portfolio.daily_realized_pnl)

    if max_daily_loss <= 0:

        return "normal", 1.0



    used = current_loss / max_daily_loss

    if used >= 1.0:

        return "severe", 0.25

    if used >= 0.85:

        return "severe", 0.25

    if used >= 0.65:

        return "elevated", 0.50

    if used >= 0.40:

        return "warning", 0.75

    return "normal", 1.0





class RiskBudgetAllocator:

    """Allocate capital within portfolio heat zones — scale, don't deny."""



    NORMAL_HEAT_MIN = 6.0

    NORMAL_HEAT_MAX = 8.0

    ELEVATED_HEAT_MAX = 10.0

    MAX_HEAT = 12.0

    BASE_RISK_PCT = 1.0

    MAX_DAILY_LOSS_PCT = 3.0



    def __init__(self, project_root: Path | None = None) -> None:

        self.project_root = project_root.resolve() if project_root else None

        self._decisions: dict[str, RiskBudgetDecision] = {}

        self._daily_scaled_count = 0



    @property

    def daily_scaled_count(self) -> int:

        return self._daily_scaled_count



    def allocate(

        self,

        *,

        oas: OpportunityAllocationScore,

        portfolio: PortfolioState,

        base_risk_pct: float | None = None,

        additional_risk_pct: float = 0.0,

    ) -> RiskBudgetDecision:

        base = base_risk_pct if base_risk_pct is not None else self.BASE_RISK_PCT

        current_heat = _open_risk_pct(portfolio) + additional_risk_pct

        zone = _heat_zone(current_heat)

        heat_mult = _heat_multiplier(zone)

        daily_zone, daily_mult = _daily_loss_zone(

            portfolio, max_daily_loss_pct=self.MAX_DAILY_LOSS_PCT

        )



        if daily_mult < 0.999:

            self._daily_scaled_count += 1



        combined = oas.risk_multiplier * heat_mult * daily_mult

        allocated = base * combined



        if zone == "over_limit":

            combined = min(combined, 0.25)

            allocated = base * combined



        allow = combined > 0.0



        decision = RiskBudgetDecision(

            symbol=oas.symbol,

            heat_zone=zone,

            daily_loss_zone=daily_zone,

            portfolio_heat_pct=current_heat,

            oas_tier=oas.tier,

            oas_multiplier=oas.risk_multiplier,

            heat_multiplier=heat_mult,

            daily_loss_multiplier=daily_mult,

            combined_multiplier=combined,

            allocated_risk_pct=allocated,

            allow_trade=allow,

            reason=(

                f"Heat {current_heat:.1f}% ({zone}), daily {daily_zone} "

                f"{daily_mult:.0%}, OAS tier {oas.tier} → {combined:.0%} ({allocated:.2f}%)"

            ),

        )

        self._decisions[oas.symbol] = decision

        return decision



    def portfolio_heat(self, portfolio: PortfolioState) -> float:

        return _open_risk_pct(portfolio)



    def write_report(self) -> Path | None:

        if self.project_root is None:

            return None

        logs = self.project_root / "logs"

        logs.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()

        lines = [

            "# Risk Budget Report",

            "",

            f"**Generated:** {now}",

            "",

            "## Heat zones",

            "",

            "| Zone | Range | Multiplier |",

            "|------|-------|------------|",

            f"| Normal | {self.NORMAL_HEAT_MIN}-{self.NORMAL_HEAT_MAX}% | 1.0x |",

            f"| Elevated | {self.NORMAL_HEAT_MAX}-{self.ELEVATED_HEAT_MAX}% | 0.75x |",

            f"| Max | {self.ELEVATED_HEAT_MAX}-{self.MAX_HEAT}% | 0.50x |",

            f"| Over limit | >{self.MAX_HEAT}% | 0.25x |",

            "",

            "## Daily loss scaling",

            "",

            "| Zone | Usage | Multiplier |",

            "|------|-------|------------|",

            "| Normal | <40% | 100% |",

            "| Warning | 40-65% | 75% |",

            "| Elevated | 65-85% | 50% |",

            "| Severe | 85-100% | 25% |",

            "| Severe | ≥100% | 25% |",

            "",

            "## OAS tiers",

            "",

            "| OAS | Tier | Multiplier |",

            "|-----|------|------------|",

            "| 85-100 | premium | 1.0x |",

            "| 75-84 | standard | 0.75x |",

            "| 65-74 | reduced | 0.50x |",

            "| 50-64 | watchlist | 0.25x |",

            "| <50 | defer | 0.15x |",

            "",

            "## Recent allocations",

            "",

            "| Symbol | Heat | Zone | Daily | Combined | Alloc % |",

            "|--------|------|------|-------|----------|---------|",

        ]

        for symbol, d in sorted(self._decisions.items()):

            lines.append(

                f"| {symbol} | {d.portfolio_heat_pct:.1f}% | {d.heat_zone} | "

                f"{d.daily_loss_zone} | {d.combined_multiplier:.0%} | "

                f"{d.allocated_risk_pct:.2f}% |"

            )

        path = logs / "risk_budget_report.md"

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return path


