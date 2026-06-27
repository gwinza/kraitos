from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from analytics.pair_specialisation import PairSpecialisationAnalyzer
from analytics.performance import PerformanceAnalyzer
from broker.mt5_connector import MT5Connector
from config.settings import KraitosConfig
from data.market_data import MarketDataService
from execution.entry_engine import EntryEngine
from execution.exit_engine import ExitEngine
from execution.paper_trader import PaperTrader, PaperTraderConfig
from logs.event_logger import KraitosEventLogger
from risk.models import RiskLimits
from risk.risk_manager import RiskManager

if TYPE_CHECKING:
    from core.expectancy_learning import ExpectancyLearningLoop

from strategies.harvest_engine import HarvestEngine
from strategies.market_structure import MarketStructureAnalyzer
from strategies.micro_scalper import MicroScalper
from strategies.multitimeframe_bias import MultiTimeframeBiasAnalyzer
from strategies.news_filter import NewsFilter
from strategies.regime_detector import RegimeDetector


@dataclass
class KraitosRuntime:
    """Shared services used across orchestration steps."""

    project_root: Path
    config: KraitosConfig
    event_logger: KraitosEventLogger
    connector: MT5Connector
    market_data: MarketDataService
    regime_detector: RegimeDetector
    bias_analyzer: MultiTimeframeBiasAnalyzer
    structure_analyzer: MarketStructureAnalyzer
    harvest_engine: HarvestEngine
    micro_scalper: MicroScalper
    entry_engine: EntryEngine
    exit_engine: ExitEngine
    risk_manager: RiskManager
    paper_trader: PaperTrader
    news_filter: NewsFilter
    performance_analyzer: PerformanceAnalyzer
    pair_analyzer: PairSpecialisationAnalyzer
    broker_balance: float | None = None
    expectancy_learning: ExpectancyLearningLoop | None = None

    @classmethod
    def build(
        cls,
        *,
        project_root: Path,
        config: KraitosConfig,
        event_logger: KraitosEventLogger,
    ) -> KraitosRuntime:
        """Construct all orchestration services from configuration."""
        history_bars = int(config.raw.get("data", {}).get("history_bars", 500))
        limits = RiskLimits(
            per_trade_pct=config.risk.per_trade_pct,
            max_daily_loss_pct=config.risk.max_daily_drawdown_pct,
            max_open_trades=config.risk.max_open_trades,
            max_risk_per_symbol_pct=config.risk.max_risk_per_symbol_pct,
            max_correlated_exposure_pct=config.risk.max_correlated_exposure_pct,
        )

        broker_raw = config.raw.get("broker", {})
        execution_raw = config.raw.get("execution", {})
        backtest_raw = config.raw.get("backtesting", {})
        spread_pips = float(
            backtest_raw.get("spread_pips", execution_raw.get("slippage_pips", 1.0))
        )

        connector = MT5Connector.from_env(
            reconnect_attempts=int(broker_raw.get("reconnect_attempts", 3)),
            reconnect_delay_seconds=float(
                broker_raw.get("reconnect_delay_seconds", 5.0)
            ),
        )
        return cls(
            project_root=project_root,
            config=config,
            event_logger=event_logger,
            connector=connector,
            market_data=MarketDataService(connector, default_count=history_bars),
            regime_detector=RegimeDetector(),
            bias_analyzer=MultiTimeframeBiasAnalyzer(),
            structure_analyzer=MarketStructureAnalyzer(),
            harvest_engine=HarvestEngine(),
            micro_scalper=MicroScalper(),
            entry_engine=EntryEngine(event_logger=event_logger),
            exit_engine=ExitEngine(),
            risk_manager=RiskManager(limits, event_logger=event_logger),
            paper_trader=PaperTrader(
                config=PaperTraderConfig(
                    initial_balance=config.account.balance,
                    spread_pips=spread_pips,
                ),
                event_logger=event_logger,
            ),
            news_filter=NewsFilter(known_symbols=config.trading.symbols),
            performance_analyzer=PerformanceAnalyzer(),
            pair_analyzer=PairSpecialisationAnalyzer(),
        )
