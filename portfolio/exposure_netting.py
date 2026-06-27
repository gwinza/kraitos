"""Net currency and correlation exposure across open positions."""



from __future__ import annotations



from dataclasses import dataclass, field



from risk.models import DEFAULT_CORRELATION_GROUPS, OpenPosition, PortfolioState, TradeSide





@dataclass(frozen=True)

class NetExposure:

    """Aggregated exposure snapshot."""



    currency_net: dict[str, float]

    cluster_counts: dict[str, int]

    same_direction_counts: dict[str, int]

    total_open_risk_pct: float

    symbol_concentration: dict[str, float]



    def to_dict(self) -> dict:

        return {

            "currency_net": {k: round(v, 3) for k, v in self.currency_net.items()},

            "cluster_counts": self.cluster_counts,

            "same_direction_counts": self.same_direction_counts,

            "total_open_risk_pct": round(self.total_open_risk_pct, 3),

            "symbol_concentration": {

                k: round(v, 3) for k, v in self.symbol_concentration.items()

            },

        }





class ExposureNetting:

    """Compute net exposures for correlation-aware allocation."""



    def compute(

        self,

        portfolio: PortfolioState,

        *,

        balance: float | None = None,

    ) -> NetExposure:

        bal = balance if balance is not None else portfolio.balance

        currency_net: dict[str, float] = {}

        symbol_risk: dict[str, float] = {}

        cluster_counts: dict[str, int] = {name: 0 for name in DEFAULT_CORRELATION_GROUPS}

        same_dir: dict[str, int] = {"buy": 0, "sell": 0}



        for pos in portfolio.open_positions:

            sign = 1.0 if pos.side == "buy" else -1.0

            base = pos.symbol[:3]

            quote = pos.symbol[3:6]

            weight = pos.risk_amount / max(bal, 1.0)

            currency_net[base] = currency_net.get(base, 0.0) + sign * weight

            currency_net[quote] = currency_net.get(quote, 0.0) - sign * weight

            symbol_risk[pos.symbol] = symbol_risk.get(pos.symbol, 0.0) + weight

            same_dir[pos.side] = same_dir.get(pos.side, 0) + 1

            for name, members in DEFAULT_CORRELATION_GROUPS.items():

                if pos.symbol in members:

                    cluster_counts[name] = cluster_counts.get(name, 0) + 1



        total_risk = sum(pos.risk_amount for pos in portfolio.open_positions)

        total_pct = total_risk / max(bal, 1.0) * 100.0



        return NetExposure(

            currency_net=currency_net,

            cluster_counts=cluster_counts,

            same_direction_counts=same_dir,

            total_open_risk_pct=total_pct,

            symbol_concentration=symbol_risk,

        )



    def soft_scale(

        self,

        portfolio: PortfolioState,

        *,

        symbol: str,

        side: TradeSide,

    ) -> tuple[float, str]:

        """Soft exposure scaling — never hard-reject from netting alone."""

        normalized = symbol.strip().upper()

        exposure = self.compute(portfolio)

        multiplier = 1.0

        reasons: list[str] = []



        base = normalized[:3]

        quote = normalized[3:6]

        sign = 1.0 if side == "buy" else -1.0

        projected_base = exposure.currency_net.get(base, 0.0) + sign * 0.01

        projected_quote = exposure.currency_net.get(quote, 0.0) - sign * 0.01

        max_net = max(abs(projected_base), abs(projected_quote))



        if max_net >= 0.08:

            multiplier *= 0.55

            reasons.append(f"Currency net {max_net:.1%} → 55%")

        elif max_net >= 0.05:

            multiplier *= 0.75

            reasons.append(f"Currency net {max_net:.1%} → 75%")

        elif max_net >= 0.03:

            multiplier *= 0.90

            reasons.append(f"Currency net {max_net:.1%} → 90%")



        symbol_weight = exposure.symbol_concentration.get(normalized, 0.0)

        if symbol_weight >= 0.04:

            multiplier *= 0.70

            reasons.append(f"Symbol concentration {symbol_weight:.1%} → 70%")



        multiplier = max(0.20, min(1.0, multiplier))

        reason = "; ".join(reasons) if reasons else "Net exposure within budget"

        return multiplier, reason



    def cluster_exposure(

        self,

        portfolio: PortfolioState,

        symbol: str,

    ) -> int:

        normalized = symbol.strip().upper()

        for name, members in DEFAULT_CORRELATION_GROUPS.items():

            if normalized in members:

                member_set = set(members)

                return sum(

                    1 for p in portfolio.open_positions if p.symbol in member_set

                )

        return 0



    def same_direction_in_cluster(

        self,

        portfolio: PortfolioState,

        *,

        symbol: str,

        side: TradeSide,

    ) -> int:

        normalized = symbol.strip().upper()

        for members in DEFAULT_CORRELATION_GROUPS.values():

            if normalized not in members:

                continue

            member_set = set(members)

            return sum(

                1 for p in portfolio.open_positions

                if p.symbol in member_set and p.side == side

            )

        return 0


