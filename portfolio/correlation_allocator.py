"""Correlation-aware risk scaling — scale instead of blind block."""



from __future__ import annotations



from dataclasses import dataclass

from datetime import datetime, timezone

from pathlib import Path



from portfolio.exposure_netting import ExposureNetting

from risk.models import DEFAULT_CORRELATION_GROUPS, PortfolioState, TradeSide



AUDUSD_STRICT_UNTIL_PF = 1.5



# Nth correlated position in cluster: 1st 100%, 2nd 80%, 3rd 60%, 4th 40%, 5th 20%

CORRELATION_POSITION_SCALES = (1.0, 0.8, 0.6, 0.4, 0.2)





@dataclass(frozen=True)

class CorrelationScale:

    """Correlation scaling decision for one entry."""



    symbol: str

    side: TradeSide

    cluster_name: str | None

    cluster_count: int

    same_direction_count: int

    scale_multiplier: float

    allow_trade: bool

    reason: str



    def to_dict(self) -> dict:

        return {

            "symbol": self.symbol,

            "side": self.side,

            "cluster_name": self.cluster_name,

            "cluster_count": self.cluster_count,

            "same_direction_count": self.same_direction_count,

            "scale_multiplier": round(self.scale_multiplier, 3),

            "allow_trade": self.allow_trade,

            "reason": self.reason,

        }





class CorrelationAllocator:

    """Scale correlated exposure — never reject solely for correlation."""



    AUDUSD_EXTRA_PENALTY = 0.6

    SAME_DIR_MILD_SCALE = 0.95



    def __init__(self, project_root: Path | None = None) -> None:

        self.project_root = project_root.resolve() if project_root else None

        self._netting = ExposureNetting()

        self._decisions: dict[str, CorrelationScale] = {}

        self._symbol_pf: dict[str, float] = {}

        self._scaled_count = 0



    @property

    def scaled_count(self) -> int:

        return self._scaled_count



    def set_symbol_pf(self, symbol_pf: dict[str, float]) -> None:

        self._symbol_pf = dict(symbol_pf)



    def scale(

        self,

        *,

        symbol: str,

        side: TradeSide,

        portfolio: PortfolioState,

        drawdown_pct: float | None = None,

    ) -> CorrelationScale:

        normalized = symbol.strip().upper()

        _ = drawdown_pct if drawdown_pct is not None else portfolio.drawdown_pct



        cluster_name: str | None = None

        for name, members in DEFAULT_CORRELATION_GROUPS.items():

            if normalized in members:

                cluster_name = name

                break



        cluster_count = self._netting.cluster_exposure(portfolio, normalized)

        same_dir = self._netting.same_direction_in_cluster(

            portfolio, symbol=normalized, side=side

        )



        position_index = cluster_count + 1

        scale_idx = min(position_index - 1, len(CORRELATION_POSITION_SCALES) - 1)

        multiplier = CORRELATION_POSITION_SCALES[scale_idx]

        reasons: list[str] = [

            f"Cluster position {position_index} → {multiplier:.0%}",

        ]



        if same_dir > 0:

            multiplier *= self.SAME_DIR_MILD_SCALE

            reasons.append(

                f"Same-direction correlated ({same_dir}) → mild {self.SAME_DIR_MILD_SCALE:.0%}"

            )



        net_scale, net_reason = self._netting.soft_scale(

            portfolio, symbol=normalized, side=side

        )

        if net_scale < 0.999:

            multiplier *= net_scale

            reasons.append(net_reason)



        if normalized == "AUDUSD":

            pf = self._symbol_pf.get("AUDUSD", 1.0)

            if pf < AUDUSD_STRICT_UNTIL_PF:

                multiplier *= self.AUDUSD_EXTRA_PENALTY

                reasons.append(f"AUDUSD strict (PF {pf:.2f}) → {self.AUDUSD_EXTRA_PENALTY:.0%}")



        multiplier = max(0.20, min(1.0, multiplier))

        if multiplier < 0.999:

            self._scaled_count += 1



        result = CorrelationScale(

            symbol=normalized,

            side=side,

            cluster_name=cluster_name,

            cluster_count=cluster_count,

            same_direction_count=same_dir,

            scale_multiplier=multiplier,

            allow_trade=True,

            reason="; ".join(reasons),

        )

        self._decisions[normalized] = result

        return result



    def write_report(self) -> Path | None:

        if self.project_root is None:

            return None

        logs = self.project_root / "logs"

        logs.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()

        lines = [

            "# Correlation Allocation Report",

            "",

            f"**Generated:** {now}",

            "",

            "Scaling not rejection — 1st 100%, 2nd 80%, 3rd 60%, 4th 40%, 5th 20%.",

            "",

            "| Symbol | Cluster | Count | Same-dir | Scale | Reason |",

            "|--------|---------|-------|----------|-------|--------|",

        ]

        for symbol, d in sorted(self._decisions.items()):

            lines.append(

                f"| {symbol} | {d.cluster_name or '-'} | {d.cluster_count} | "

                f"{d.same_direction_count} | {d.scale_multiplier:.0%} | {d.reason[:50]} |"

            )

        path = logs / "correlation_allocation_report.md"

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return path


