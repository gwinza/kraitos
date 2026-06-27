"""Auditor Brain — orchestrates verification ONLY.

Must NOT participate in story/opportunity/scoring decisions.
Conservative execution, validation gates, and trust verdicts live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

from backtesting.execution_model import (
    ExecutionCostConfig,
    PositionExitEvent,
    commission_cost,
    entry_fill_price,
    exit_fill_price,
    next_bar_open,
    resolve_position_exit,
    slice_closed_candles,
)
from backtesting.performance_report import PerformanceMetrics
from controls.strategy_quality_gate import StrategyQualityGate
from paper_trading.virtual_account import OpenVirtualPosition
from validation.backtest_red_team import RedTeamComparison, assess_trustworthiness, audit_known_biases
from validation.conservative_validation import (
    ConservativeValidationResult,
    WalkForwardConfig,
    _build_splits,
    _compute_trust_verdict,
    _metrics_from_conservative_journal,
    _reset_journal,
    compute_data_quality_score,
)
from validation.data_universe import build_walk_forward_universe
from validation.strategy_validator import (
    StrategyValidationInput,
    StrategyValidator,
)


@dataclass(frozen=True)
class ConservativeFillResult:
    """Result of auditor conservative fill simulation."""

    fill_price: float
    commission: float


@dataclass
class ValidationGateReport:
    """Diagnostic gate results — reporting only, never feeds trader."""

    gates: dict[str, str] = field(default_factory=dict)
    passed: int = 0
    failed: int = 0
    diagnostic_only: bool = True


@dataclass
class AuditorBrainStats:
    """Accumulated verification statistics."""

    validation_runs: int = 0
    trust_verdict: str = "UNKNOWN"
    last_verification_at: str = ""
    conservative_trades: int = 0


class AuditorBrain:
    """Validates outcomes using conservative assumptions — never dictates discovery."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._stats = AuditorBrainStats()
        self._quality_gate = StrategyQualityGate.from_project(self.project_root)
        self._violations_fixed: list[str] = []
        self._last_pipeline: object | None = None

    @property
    def last_pipeline(self) -> object | None:
        return self._last_pipeline

    @property
    def stats(self) -> AuditorBrainStats:
        return self._stats

    @property
    def violations_fixed(self) -> list[str]:
        return list(self._violations_fixed)

    def verify_run(
        self,
        *,
        config: WalkForwardConfig | None = None,
        progress_callback: Callable[[datetime, str], None] | None = None,
        reset_journal: bool = True,
    ) -> ConservativeValidationResult:
        """Run conservative walk-forward validation under auditor ownership."""
        from backtesting.backtest_engine import BacktestEngineConfig
        from backtesting.conservative_backtest_engine import (
            ConservativeBacktestConfig,
            ConservativeBacktestEngine,
        )
        from backtesting.execution_model import ExecutionCostConfig as CostConfig
        from backtesting.run_validation_backtest import build_backtest_stack
        from intelligence.opportunity_allocator import OpportunityAllocator
        from paper_trading.virtual_account import ValidationConfig
        from validation.strategy_quality import refresh_strategy_quality_from_journal

        cfg = config or WalkForwardConfig()
        logs = self.project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)

        conservative_journal = logs / "conservative_trade_journal.csv"
        if conservative_journal.exists():
            try:
                refresh_strategy_quality_from_journal(self.project_root)
            except (FileNotFoundError, ValueError):
                pass

        allocator = OpportunityAllocator(self.project_root)
        if conservative_journal.exists():
            allocator.refresh_fitness(conservative_journal)

        stack_config, pipeline, risk_controller = build_backtest_stack(
            self.project_root,
            apply_strategy_quality=False,
        )
        candles, data_source = build_walk_forward_universe(
            self.project_root,
            years=cfg.years,
            symbols=cfg.symbols,
            m1_bars_per_year=cfg.m1_bars_per_year,
        )

        validation = ValidationConfig(
            initial_balance=float(stack_config.account.balance),
            risk_per_trade_pct=float(stack_config.risk.per_trade_pct),
            spread_pips=0.5,
        )

        if reset_journal:
            _reset_journal(conservative_journal)

        conservative_engine = ConservativeBacktestEngine(
            config=stack_config,
            pipeline=pipeline,
            risk_controller=risk_controller,
            conservative_config=ConservativeBacktestConfig(
                engine=BacktestEngineConfig(
                    driver_timeframe="M5",
                    step=cfg.step,
                    min_warmup_bars=0,
                    validation=validation,
                ),
                costs=CostConfig(
                    spread_pips=1.2,
                    commission_per_lot_round_turn=7.0,
                    slippage_pips=0.3,
                ),
            ),
            journal_path=conservative_journal,
            on_timeline_progress=progress_callback,
            auditor=self,
        )
        conservative_engine.risk_controller.set_portfolio_builder(
            lambda: conservative_engine.account.portfolio_state(risk_controller.risk_manager)
        )
        self._last_pipeline = pipeline
        conservative_result = conservative_engine.run(candles, symbols=cfg.symbols)
        initial_balance = float(stack_config.account.balance)
        from backtesting.performance_report import PerformanceReport

        conservative_metrics = _metrics_from_conservative_journal(
            conservative_journal,
            initial_balance,
            fallback=PerformanceReport(conservative_result.account).metrics(),
        )

        optimistic_metrics = None
        optimistic_journal = None
        if cfg.include_optimistic_demo:
            from backtesting.backtest_engine import BacktestEngine

            optimistic_journal = logs / "research_demo_trade_journal.csv"
            _reset_journal(optimistic_journal)
            optimistic_engine = BacktestEngine(
                config=stack_config,
                pipeline=pipeline,
                risk_controller=risk_controller,
                engine_config=BacktestEngineConfig(
                    driver_timeframe="M5",
                    step=cfg.step,
                    min_warmup_bars=0,
                    validation=validation,
                ),
                journal_path=optimistic_journal,
            )
            optimistic_engine.risk_controller.set_portfolio_builder(
                lambda: optimistic_engine.account.portfolio_state(risk_controller.risk_manager)
            )
            optimistic_result = optimistic_engine.run(candles, symbols=cfg.symbols)
            optimistic_metrics = PerformanceReport(optimistic_result.account).metrics()

        splits = _build_splits(conservative_journal, years=cfg.years)
        trust_verdict = _compute_trust_verdict(
            conservative_metrics,
            optimistic_metrics,
            data_source=data_source,
        )
        data_quality_score = compute_data_quality_score(
            years_covered=len(cfg.years),
            conservative_trades=conservative_metrics.total_trades,
            trust_verdict=trust_verdict,
            splits=splits,
            data_source=data_source,
            symbol_count=len(cfg.symbols),
        )

        try:
            refresh_strategy_quality_from_journal(
                self.project_root,
                initial_balance=initial_balance,
            )
            from intelligence.asset_strategy_researcher import AssetStrategyResearcher

            AssetStrategyResearcher(self.project_root).research_journal(conservative_journal)
            allocator.refresh_fitness(conservative_journal)
        except (FileNotFoundError, ValueError):
            pass

        self._stats.validation_runs += 1
        self._stats.trust_verdict = trust_verdict
        self._stats.conservative_trades = conservative_metrics.total_trades
        self._stats.last_verification_at = datetime.now(timezone.utc).isoformat()

        return ConservativeValidationResult(
            conservative_metrics=conservative_metrics,
            optimistic_metrics=optimistic_metrics,
            trust_verdict=trust_verdict,
            data_quality_score=data_quality_score,
            data_source=data_source,
            splits=splits,
            years_covered=tuple(cfg.years),
            symbols_covered=tuple(cfg.symbols),
            conservative_journal_path=conservative_journal,
            optimistic_journal_path=optimistic_journal,
        )

    def apply_conservative_execution(
        self,
        *,
        direction: str,
        open_price: float,
        symbol: str,
        costs: ExecutionCostConfig,
        lot_size: float = 0.01,
    ) -> ConservativeFillResult:
        """Simulate next-bar entry with spread, slippage, and commission."""
        fill = entry_fill_price(
            direction=direction,
            open_price=open_price,
            symbol=symbol,
            costs=costs,
        )
        return ConservativeFillResult(
            fill_price=fill,
            commission=commission_cost(lot_size, costs),
        )

    def apply_conservative_exit(
        self,
        *,
        direction: str,
        raw_price: float,
        symbol: str,
        costs: ExecutionCostConfig,
        lot_size: float = 0.01,
    ) -> ConservativeFillResult:
        """Simulate exit with spread, slippage, and commission."""
        fill = exit_fill_price(
            direction=direction,
            raw_price=raw_price,
            symbol=symbol,
            costs=costs,
        )
        return ConservativeFillResult(
            fill_price=fill,
            commission=commission_cost(lot_size, costs),
        )

    def resolve_position_exit(
        self,
        position: OpenVirtualPosition,
        *,
        high: float,
        low: float,
        costs: ExecutionCostConfig,
    ) -> PositionExitEvent | None:
        """Resolve TP/SL with worst-case (SL-first) assumptions."""
        return resolve_position_exit(
            position,
            high=high,
            low=low,
            sl_first=costs.sl_first_on_ambiguity,
        )

    def slice_closed_candles(
        self,
        candles: dict[str, pd.DataFrame],
        moment: datetime,
    ) -> dict[str, pd.DataFrame]:
        """Return only fully closed candles — auditor anti-lookahead."""
        return slice_closed_candles(candles, moment)

    def next_bar_open(self, moment: datetime, timeframe: str) -> datetime:
        """Return next-bar open time for conservative entry delay."""
        return next_bar_open(moment, timeframe)

    def check_validation_gates(
        self,
        metrics: PerformanceMetrics,
        *,
        paper_metrics: PerformanceMetrics | None = None,
    ) -> ValidationGateReport:
        """Evaluate validation gates for diagnostic reporting only."""
        validator = StrategyValidator()
        paper = paper_metrics or metrics
        result = validator.validate(
            StrategyValidationInput(
                backtest=metrics,
                paper=paper,
                trust_verdict=self._stats.trust_verdict,
            )
        )
        report = ValidationGateReport(diagnostic_only=True)
        for criterion in result.criteria:
            status = "PASS" if criterion.passed else "FAIL"
            report.gates[criterion.name] = status
            if criterion.passed:
                report.passed += 1
            else:
                report.failed += 1
        return report

    def assess_trust(
        self,
        conservative: PerformanceMetrics,
        optimistic: PerformanceMetrics | None,
    ) -> str:
        """Compute trust verdict from conservative vs optimistic comparison."""
        comparison = None
        if optimistic is not None:
            comparison = RedTeamComparison(
                optimistic=optimistic,
                conservative=conservative,
                optimistic_trades=optimistic.total_trades,
                conservative_trades=conservative.total_trades,
                test_bars_m1=0,
                test_symbols=(),
            )
        verdict = assess_trustworthiness(audit_known_biases(), comparison)
        return verdict.rating

    def record_violation_fixed(self, description: str) -> None:
        """Record a separation violation that was remediated."""
        self._violations_fixed.append(description)
