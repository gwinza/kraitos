"""Rolling strategy fitness scores from trade journal history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from validation.r_metrics import CLOSED_RESULTS

RecommendedAction = Literal[
    "APPROVED",
    "CONDITIONAL",
    "REDUCED_RISK",
    "QUARANTINED",
    "DISABLED",
]

WINDOWS = (50, 100, 250)
MIN_TRADES_FOR_ACTION = 8
FITNESS_FILENAME = "strategy_fitness_memory.json"


@dataclass
class WindowFitness:
    """Fitness metrics for one rolling window."""

    trades: int
    win_rate: float
    profit_factor: float
    average_r: float
    max_drawdown_pct: float
    expectancy: float
    fitness_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trades": self.trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "average_r": round(self.average_r, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "expectancy": round(self.expectancy, 4),
            "fitness_score": round(self.fitness_score, 4),
        }


@dataclass
class StrategyFitnessRecord:
    """Rolling fitness for one symbol/strategy bucket."""

    symbol: str
    strategy: str
    trend_state: str = "any"
    regime: str = "any"
    session: str = "any"
    windows: dict[str, WindowFitness] = field(default_factory=dict)
    deterioration: bool = False
    fitness_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "trend_state": self.trend_state,
            "regime": self.regime,
            "session": self.session,
            "windows": {k: v.to_dict() for k, v in self.windows.items()},
            "deterioration": self.deterioration,
            "fitness_score": round(self.fitness_score, 4),
        }


@dataclass
class SymbolFitnessProfile:
    """Aggregated fitness and recommendations per symbol."""

    symbol: str
    best_strategy_overall: str = "harvest"
    best_by_trend_state: dict[str, str] = field(default_factory=dict)
    best_by_regime: dict[str, str] = field(default_factory=dict)
    best_session: str = "any"
    worst_strategy: str = "no_trade"
    deterioration_warning: bool = False
    recommended_action: RecommendedAction = "APPROVED"
    strategy_records: dict[str, StrategyFitnessRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "best_strategy_overall": self.best_strategy_overall,
            "best_by_trend_state": self.best_by_trend_state,
            "best_by_regime": self.best_by_regime,
            "best_session": self.best_session,
            "worst_strategy": self.worst_strategy,
            "deterioration_warning": self.deterioration_warning,
            "recommended_action": self.recommended_action,
            "strategy_records": {
                k: v.to_dict() for k, v in self.strategy_records.items()
            },
        }


class RollingFitnessMemory:
    """Persist and query rolling strategy fitness."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / "logs" / FITNESS_FILENAME
        self._profiles: dict[str, SymbolFitnessProfile] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        for symbol, entry in raw.get("symbols", {}).items():
            profile = SymbolFitnessProfile(symbol=str(symbol).upper())
            profile.best_strategy_overall = str(entry.get("best_strategy_overall", "harvest"))
            profile.best_by_trend_state = {
                str(k): str(v) for k, v in entry.get("best_by_trend_state", {}).items()
            }
            profile.best_by_regime = {
                str(k): str(v) for k, v in entry.get("best_by_regime", {}).items()
            }
            profile.best_session = str(entry.get("best_session", "any"))
            profile.worst_strategy = str(entry.get("worst_strategy", "no_trade"))
            profile.deterioration_warning = bool(entry.get("deterioration_warning", False))
            profile.recommended_action = entry.get("recommended_action", "APPROVED")  # type: ignore[assignment]
            for key, rec in entry.get("strategy_records", {}).items():
                windows = {
                    wk: WindowFitness(
                        trades=int(wv.get("trades", 0)),
                        win_rate=float(wv.get("win_rate", 0)),
                        profit_factor=float(wv.get("profit_factor", 0)),
                        average_r=float(wv.get("average_r", 0)),
                        max_drawdown_pct=float(wv.get("max_drawdown_pct", 0)),
                        expectancy=float(wv.get("expectancy", 0)),
                        fitness_score=float(wv.get("fitness_score", 0)),
                    )
                    for wk, wv in rec.get("windows", {}).items()
                }
                profile.strategy_records[key] = StrategyFitnessRecord(
                    symbol=profile.symbol,
                    strategy=str(rec.get("strategy", key)),
                    trend_state=str(rec.get("trend_state", "any")),
                    regime=str(rec.get("regime", "any")),
                    session=str(rec.get("session", "any")),
                    windows=windows,
                    deterioration=bool(rec.get("deterioration", False)),
                    fitness_score=float(rec.get("fitness_score", 0)),
                )
            self._profiles[profile.symbol] = profile

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": {k: v.to_dict() for k, v in sorted(self._profiles.items())},
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return self.path

    def get(self, symbol: str) -> SymbolFitnessProfile | None:
        return self._profiles.get(symbol.strip().upper())

    def get_or_create(self, symbol: str) -> SymbolFitnessProfile:
        key = symbol.strip().upper()
        if key not in self._profiles:
            self._profiles[key] = SymbolFitnessProfile(symbol=key)
        return self._profiles[key]

    def refresh_from_journal(
        self,
        journal_path: Path | None = None,
        *,
        initial_balance: float = 10_000.0,
    ) -> dict[str, SymbolFitnessProfile]:
        path = journal_path or self.project_root / "logs" / "conservative_trade_journal.csv"
        if not path.exists():
            return {}
        frame = pd.read_csv(path)
        closed = frame[frame["result"].astype(str).str.lower().isin(CLOSED_RESULTS)].copy()
        if closed.empty:
            return {}

        closed["event_time"] = pd.to_datetime(closed["event_time"], utc=True, errors="coerce")
        closed["session"] = closed["event_time"].dt.hour.astype(str)
        closed["strategy"] = closed["mode"].map(_map_mode_to_strategy)

        for symbol, sym_frame in closed.groupby("symbol"):
            profile = self._build_symbol_profile(
                str(symbol).upper(),
                sym_frame,
                initial_balance,
            )
            self._profiles[profile.symbol] = profile
        self.save()
        return dict(self._profiles)

    def _build_symbol_profile(
        self,
        symbol: str,
        frame: pd.DataFrame,
        initial_balance: float,
    ) -> SymbolFitnessProfile:
        profile = SymbolFitnessProfile(symbol=symbol)
        strategy_scores: dict[str, float] = {}

        for strategy, subset in frame.groupby("strategy"):
            key = str(strategy)
            record = _fitness_record(symbol, key, subset, initial_balance)
            profile.strategy_records[key] = record
            strategy_scores[key] = record.fitness_score

        if strategy_scores:
            profile.best_strategy_overall = max(strategy_scores, key=strategy_scores.get)
            profile.worst_strategy = min(strategy_scores, key=strategy_scores.get)

        positive = [s for s, sc in strategy_scores.items() if sc > 0.3]
        all_negative = strategy_scores and not positive

        if all_negative and len(strategy_scores) >= 2:
            profile.recommended_action = "QUARANTINED"
        elif all_negative:
            profile.recommended_action = "REDUCED_RISK"
        elif profile.worst_strategy and strategy_scores.get(profile.worst_strategy, 0) < -0.2:
            profile.recommended_action = "CONDITIONAL"
        else:
            profile.recommended_action = "APPROVED"

        short = _window_fitness(frame.tail(50), initial_balance)
        long_ = _window_fitness(frame.tail(250), initial_balance) if len(frame) >= 100 else short
        if short.trades >= 10 and long_.trades >= 20:
            profile.deterioration_warning = (
                short.profit_factor < long_.profit_factor * 0.7
                and short.average_r < long_.average_r - 0.05
            )

        if profile.deterioration_warning and profile.recommended_action == "APPROVED":
            profile.recommended_action = "CONDITIONAL"

        only_disable = (
            all_negative
            and profile.deterioration_warning
            and short.max_drawdown_pct > 12.0
            and len(strategy_scores) >= 2
        )
        if only_disable:
            profile.recommended_action = "DISABLED"

        return profile

    def fitness_for(self, symbol: str, strategy: str) -> float:
        profile = self.get(symbol)
        if profile is None:
            return 0.5
        record = profile.strategy_records.get(strategy)
        return record.fitness_score if record else 0.5

    def all_profiles(self) -> dict[str, SymbolFitnessProfile]:
        return dict(self._profiles)


def _fitness_record(
    symbol: str,
    strategy: str,
    frame: pd.DataFrame,
    initial_balance: float,
) -> StrategyFitnessRecord:
    windows: dict[str, WindowFitness] = {}
    for size in WINDOWS:
        subset = frame.tail(size)
        windows[str(size)] = _window_fitness(subset, initial_balance)

    w50 = windows.get("50", _window_fitness(frame, initial_balance))
    w100 = windows.get("100", w50)
    w250 = windows.get("250", w100)
    deterioration = (
        w50.trades >= 5
        and w250.trades >= 15
        and w50.fitness_score < w250.fitness_score * 0.65
    )
    composite = (
        w50.fitness_score * 0.5
        + w100.fitness_score * 0.3
        + w250.fitness_score * 0.2
    )
    if deterioration:
        composite *= 0.7

    return StrategyFitnessRecord(
        symbol=symbol,
        strategy=strategy,
        windows=windows,
        deterioration=deterioration,
        fitness_score=composite,
    )


def _window_fitness(frame: pd.DataFrame, initial_balance: float) -> WindowFitness:
    if frame.empty:
        return WindowFitness(0, 0, 0, 0, 0, 0, 0)

    pnls = pd.to_numeric(frame["profit_loss"], errors="coerce").fillna(0.0)
    winners = pnls[pnls > 0]
    losers = pnls[pnls < 0]
    gross_profit = float(winners.sum())
    gross_loss = abs(float(losers.sum()))
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = 3.0
    else:
        pf = 0.0

    win_rate = len(winners) / len(pnls) if len(pnls) else 0.0
    r_vals = pd.to_numeric(frame.get("r_multiple"), errors="coerce").dropna()
    avg_r = float(r_vals.mean()) if not r_vals.empty else 0.0
    expectancy = float(pnls.mean())

    balances = pd.to_numeric(frame.get("balance"), errors="coerce").fillna(initial_balance)
    peak = float(balances.cummax().iloc[-1]) if not balances.empty else initial_balance
    trough = float(balances.min()) if not balances.empty else initial_balance
    dd = max(0.0, (peak - trough) / peak * 100) if peak > 0 else 0.0

    pf_score = min(1.0, pf / 2.0) if pf < 999 else 1.0
    wr_score = min(1.0, win_rate / 0.7)
    r_score = min(1.0, max(0.0, (avg_r + 0.2) / 0.5))
    dd_penalty = min(0.4, dd / 30.0)
    fitness = max(0.0, pf_score * 0.35 + wr_score * 0.25 + r_score * 0.3 - dd_penalty)

    return WindowFitness(
        trades=len(frame),
        win_rate=win_rate,
        profit_factor=pf,
        average_r=avg_r,
        max_drawdown_pct=dd,
        expectancy=expectancy,
        fitness_score=fitness,
    )


def _map_mode_to_strategy(mode: str) -> str:
    mapping = {
        "harvest": "harvest",
        "scalp": "micro_scalp",
        "normal": "normal_trend",
    }
    return mapping.get(str(mode).strip().lower(), str(mode))
