"""
Pair specialisation analytics for Kraitos.

Classifies symbols by historical performance and assigns risk treatment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from analytics.models import (
    ClosedTradeRecord,
    PairSpecialisationEntry,
    PairSpecialisationResult,
    SymbolPerformance,
)
from analytics.performance import PerformanceAnalyzer

DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "logs" / "pair_specialisation.json"
)

CLASSIFICATION_STRONG = "strong"
CLASSIFICATION_NORMAL = "normal"
CLASSIFICATION_WEAK = "weak"
CLASSIFICATION_QUARANTINED = "quarantined"

RISK_MULTIPLIERS = {
    CLASSIFICATION_STRONG: 1.0,
    CLASSIFICATION_NORMAL: 1.0,
    CLASSIFICATION_WEAK: 0.5,
    CLASSIFICATION_QUARANTINED: 0.0,
}


@dataclass(frozen=True)
class PairSpecialisationConfig:
    """Thresholds for pair classification."""

    min_trades_for_rating: int = 3
    min_trades_for_quarantine: int = 5
    strong_win_rate: float = 0.55
    strong_profit_factor: float = 1.3
    weak_win_rate: float = 0.45
    weak_profit_factor: float = 1.0
    quarantine_win_rate: float = 0.35
    quarantine_profit_factor: float = 0.7
    quarantine_max_net_loss: float = -100.0


class PairSpecialisationError(Exception):
    """Raised when pair specialisation input or output fails."""


class PairSpecialisationAnalyzer:
    """Analyse per-symbol performance and assign trading classifications."""

    def __init__(self, config: PairSpecialisationConfig | None = None) -> None:
        self.config = config or PairSpecialisationConfig()
        self._performance = PerformanceAnalyzer()

    def analyze(
        self,
        trades: list[ClosedTradeRecord],
        *,
        symbols: list[str] | None = None,
    ) -> PairSpecialisationResult:
        """Classify symbols from closed trade history."""
        unique_trades = self._dedupe_trades(trades)
        grouped = self._group_by_symbol(unique_trades)
        target_symbols = symbols or sorted(grouped.keys())

        entries: list[PairSpecialisationEntry] = []
        for symbol in sorted(set(target_symbols)):
            symbol_trades = grouped.get(symbol, [])
            performance = self._symbol_performance(symbol, symbol_trades)
            classification, reason = self._classify(performance)
            entries.append(
                PairSpecialisationEntry(
                    symbol=symbol,
                    classification=classification,
                    risk_multiplier=RISK_MULTIPLIERS[classification],
                    trading_allowed=classification != CLASSIFICATION_QUARANTINED,
                    performance=performance,
                    reason=reason,
                )
            )

        result = PairSpecialisationResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            pairs=tuple(entries),
        )
        logger.info(
            f"Pair specialisation complete for {len(entries)} symbol(s)"
        )
        return result

    def from_log_paths(
        self,
        *paths: Path | str,
        symbols: list[str] | None = None,
    ) -> PairSpecialisationResult:
        """Load trade logs and classify symbols."""
        trades: list[ClosedTradeRecord] = []
        for path in paths:
            trades.extend(self._performance.load_trades(path))
        return self.analyze(trades, symbols=symbols)

    def from_default_logs(
        self,
        symbols: list[str] | None = None,
    ) -> PairSpecialisationResult:
        """Load default trade logs and classify symbols."""
        from analytics.performance import (
            DEFAULT_EXECUTED_CSV,
            DEFAULT_EXECUTED_JSONL,
            DEFAULT_PAPER_LOG,
        )

        paths = [DEFAULT_PAPER_LOG, DEFAULT_EXECUTED_CSV, DEFAULT_EXECUTED_JSONL]
        existing = [path for path in paths if path.exists()]
        if not existing:
            if not symbols:
                raise PairSpecialisationError("No trade logs found and no symbols provided")
            return self.analyze([], symbols=symbols)
        return self.from_log_paths(*existing, symbols=symbols)

    def analyze_and_save(
        self,
        trades: list[ClosedTradeRecord],
        *,
        symbols: list[str] | None = None,
        output_path: Path | str = DEFAULT_OUTPUT_PATH,
    ) -> PairSpecialisationResult:
        """Analyze symbols and persist results to JSON."""
        result = self.analyze(trades, symbols=symbols)
        self.save(result, output_path)
        return result

    def save(
        self,
        result: PairSpecialisationResult,
        output_path: Path | str = DEFAULT_OUTPUT_PATH,
    ) -> Path:
        """Save pair specialisation results to JSON."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._to_dict(result)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        logger.info(f"Pair specialisation saved to {path}")
        return path

    def load(self, path: Path | str = DEFAULT_OUTPUT_PATH) -> PairSpecialisationResult:
        """Load pair specialisation results from JSON."""
        file_path = Path(path)
        if not file_path.exists():
            raise PairSpecialisationError(f"Pair specialisation file not found: {file_path}")

        with file_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        pairs: list[PairSpecialisationEntry] = []
        for symbol, entry in payload.get("symbols", {}).items():
            perf = entry.get("performance", {})
            pairs.append(
                PairSpecialisationEntry(
                    symbol=symbol,
                    classification=entry["classification"],
                    risk_multiplier=float(entry["risk_multiplier"]),
                    trading_allowed=bool(entry["trading_allowed"]),
                    performance=SymbolPerformance(
                        symbol=symbol,
                        total_trades=int(perf.get("total_trades", 0)),
                        win_rate=float(perf.get("win_rate", 0)),
                        profit_factor=float(perf.get("profit_factor", 0)),
                        net_profit=float(perf.get("net_profit", 0)),
                        average_win=float(perf.get("average_win", 0)),
                        average_loss=float(perf.get("average_loss", 0)),
                    ),
                    reason=entry.get("reason", ""),
                )
            )

        return PairSpecialisationResult(
            generated_at=payload.get("generated_at", ""),
            pairs=tuple(pairs),
        )

    def _symbol_performance(
        self,
        symbol: str,
        trades: list[ClosedTradeRecord],
    ) -> SymbolPerformance:
        if not trades:
            return SymbolPerformance(
                symbol=symbol,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                net_profit=0.0,
                average_win=0.0,
                average_loss=0.0,
            )

        pnls = [trade.pnl for trade in trades]
        winners = [pnl for pnl in pnls if pnl > 0]
        losers = [pnl for pnl in pnls if pnl < 0]
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))

        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        return SymbolPerformance(
            symbol=symbol,
            total_trades=len(trades),
            win_rate=len(winners) / len(trades),
            profit_factor=profit_factor,
            net_profit=sum(pnls),
            average_win=sum(winners) / len(winners) if winners else 0.0,
            average_loss=abs(sum(losers) / len(losers)) if losers else 0.0,
        )

    def _classify(self, performance: SymbolPerformance) -> tuple[str, str]:
        cfg = self.config

        if performance.total_trades < cfg.min_trades_for_rating:
            return (
                CLASSIFICATION_NORMAL,
                f"Insufficient trade history ({performance.total_trades} trades); defaulting to normal risk",
            )

        pf = performance.profit_factor
        pf_display = "inf" if pf == float("inf") else f"{pf:.2f}"

        if (
            performance.total_trades >= cfg.min_trades_for_quarantine
            and performance.net_profit <= cfg.quarantine_max_net_loss
            and performance.win_rate <= cfg.quarantine_win_rate
        ) or (
            performance.total_trades >= cfg.min_trades_for_quarantine
            and pf != float("inf")
            and pf < cfg.quarantine_profit_factor
            and performance.net_profit < 0
        ):
            return (
                CLASSIFICATION_QUARANTINED,
                f"Blocked: net P/L {performance.net_profit:.2f}, "
                f"win rate {performance.win_rate:.1%}, profit factor {pf_display}",
            )

        if (
            performance.net_profit > 0
            and performance.win_rate >= cfg.strong_win_rate
            and (pf == float("inf") or pf >= cfg.strong_profit_factor)
        ):
            return (
                CLASSIFICATION_STRONG,
                f"Strong performer: net P/L {performance.net_profit:.2f}, "
                f"win rate {performance.win_rate:.1%}, profit factor {pf_display}",
            )

        if (
            performance.net_profit <= 0
            or performance.win_rate < cfg.weak_win_rate
            or (pf != float("inf") and pf < cfg.weak_profit_factor)
        ):
            return (
                CLASSIFICATION_WEAK,
                f"Reduced risk: net P/L {performance.net_profit:.2f}, "
                f"win rate {performance.win_rate:.1%}, profit factor {pf_display}",
            )

        return (
            CLASSIFICATION_NORMAL,
            f"Normal risk: net P/L {performance.net_profit:.2f}, "
            f"win rate {performance.win_rate:.1%}, profit factor {pf_display}",
        )

    @staticmethod
    def _group_by_symbol(
        trades: list[ClosedTradeRecord],
    ) -> dict[str, list[ClosedTradeRecord]]:
        grouped: dict[str, list[ClosedTradeRecord]] = {}
        for trade in trades:
            grouped.setdefault(trade.symbol, []).append(trade)
        return grouped

    @staticmethod
    def _dedupe_trades(trades: list[ClosedTradeRecord]) -> list[ClosedTradeRecord]:
        seen: set[tuple[str, str, float, str]] = set()
        unique: list[ClosedTradeRecord] = []
        for trade in trades:
            key = (
                trade.trade_id,
                trade.exit_time.isoformat(),
                trade.pnl,
                trade.event_type,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(trade)
        return unique

    @staticmethod
    def _to_dict(result: PairSpecialisationResult) -> dict:
        symbols: dict[str, dict] = {}
        for entry in result.pairs:
            pf = entry.performance.profit_factor
            symbols[entry.symbol] = {
                "classification": entry.classification,
                "risk_multiplier": entry.risk_multiplier,
                "trading_allowed": entry.trading_allowed,
                "reason": entry.reason,
                "performance": {
                    "total_trades": entry.performance.total_trades,
                    "win_rate": round(entry.performance.win_rate, 4),
                    "profit_factor": pf if pf == float("inf") else round(pf, 4),
                    "net_profit": round(entry.performance.net_profit, 2),
                    "average_win": round(entry.performance.average_win, 2),
                    "average_loss": round(entry.performance.average_loss, 2),
                },
            }

        return {
            "generated_at": result.generated_at,
            "rules": {
                "strong": "normal risk (multiplier 1.0)",
                "normal": "normal risk (multiplier 1.0)",
                "weak": "reduced risk (multiplier 0.5)",
                "quarantined": "blocked (multiplier 0.0)",
            },
            "symbols": symbols,
        }
