"""Arbitrage engine — cross-bookmaker surebet detection."""

from __future__ import annotations

from sports.models import ArbitrageResult, BookmakerOdds, MatchContext, RiskLevel


class ArbitrageEngine:
    """Compare odds across bookmakers and identify profitable coverage."""

    MIN_PROFIT_PCT = 0.5

    def analyze(self, context: MatchContext) -> ArbitrageResult:
        odds_list = context.bookmaker_odds
        if len(odds_list) < 2:
            return ArbitrageResult(
                detected=False,
                profit_pct=0.0,
                summary="Insufficient bookmaker coverage for arbitrage scan.",
            )

        best_home = max(o.home for o in odds_list)
        best_draw = max((o.draw for o in odds_list if o.draw), default=0.0)
        best_away = max((o.away for o in odds_list if o.away), default=0.0)

        if context.sport.value in ("basketball", "tennis", "mma", "cricket", "american_football"):
            return self._two_way_arbitrage(odds_list, best_home, best_away)

        return self._three_way_arbitrage(odds_list, best_home, best_draw, best_away)

    def _two_way_arbitrage(
        self,
        odds_list: tuple[BookmakerOdds, ...],
        best_home: float,
        best_away: float,
    ) -> ArbitrageResult:
        implied = (1 / best_home) + (1 / best_away)
        if implied >= 1.0:
            return ArbitrageResult(
                detected=False,
                profit_pct=0.0,
                summary="No two-way arbitrage detected.",
            )

        profit_pct = ((1 / implied) - 1) * 100
        if profit_pct < self.MIN_PROFIT_PCT:
            return ArbitrageResult(
                detected=False,
                profit_pct=profit_pct,
                summary=f"Margin too thin ({profit_pct:.2f}%) — below threshold.",
            )

        home_bk = next(o for o in odds_list if o.home == best_home)
        away_bk = next(o for o in odds_list if o.away == best_away)
        total = 100.0
        home_stake = total / (best_home * implied)
        away_stake = total / (best_away * implied)

        return ArbitrageResult(
            detected=True,
            profit_pct=profit_pct,
            stake_allocation={
                f"{home_bk.bookmaker} Home": home_stake,
                f"{away_bk.bookmaker} Away": away_stake,
            },
            bookmakers=(home_bk.bookmaker, away_bk.bookmaker),
            risk_level=RiskLevel.LOW if profit_pct > 2 else RiskLevel.MEDIUM,
            execution_speed="Immediate" if profit_pct > 3 else "Fast",
            summary=f"Two-way arbitrage: {profit_pct:.2f}% guaranteed margin.",
        )

    def _three_way_arbitrage(
        self,
        odds_list: tuple[BookmakerOdds, ...],
        best_home: float,
        best_draw: float,
        best_away: float,
    ) -> ArbitrageResult:
        if not best_draw or not best_away:
            return ArbitrageResult(detected=False, profit_pct=0.0)

        implied = (1 / best_home) + (1 / best_draw) + (1 / best_away)
        if implied >= 1.0:
            return ArbitrageResult(
                detected=False,
                profit_pct=0.0,
                summary="No three-way arbitrage detected.",
            )

        profit_pct = ((1 / implied) - 1) * 100
        if profit_pct < self.MIN_PROFIT_PCT:
            return ArbitrageResult(
                detected=False,
                profit_pct=profit_pct,
                summary=f"Margin too thin ({profit_pct:.2f}%) — below threshold.",
            )

        home_bk = next(o for o in odds_list if o.home == best_home)
        draw_bk = next(o for o in odds_list if o.draw == best_draw)
        away_bk = next(o for o in odds_list if o.away == best_away)
        total = 100.0

        return ArbitrageResult(
            detected=True,
            profit_pct=profit_pct,
            stake_allocation={
                f"{home_bk.bookmaker} Home": total / (best_home * implied),
                f"{draw_bk.bookmaker} Draw": total / (best_draw * implied),
                f"{away_bk.bookmaker} Away": total / (best_away * implied),
            },
            bookmakers=(home_bk.bookmaker, draw_bk.bookmaker, away_bk.bookmaker),
            risk_level=RiskLevel.LOW if profit_pct > 1.5 else RiskLevel.MEDIUM,
            execution_speed="Immediate" if profit_pct > 2.5 else "Fast",
            summary=f"Three-way arbitrage: {profit_pct:.2f}% guaranteed margin.",
        )
