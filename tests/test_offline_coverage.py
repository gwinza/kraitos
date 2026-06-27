"""
Offline coverage map for Kraitos.

Each test class maps to a core capability and runs without MetaTrader 5.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backtesting import BacktestConfig, Backtester, TradeSignal
from config import load_config
from core.orchestrator import KraitosOrchestrator
from core.runtime import KraitosRuntime
from data.market_data import MarketDataBundle
from execution import EntryEngine, ExitEngine, OpenTrade, PaperTrader, PaperTraderConfig
from logs.event_logger import KraitosEventLogger
from risk import RiskLimits, RiskManager
from strategies import (
    HarvestEngine,
    MarketStructureAnalyzer,
    RegimeDetector,
)
from strategies.models import (
    HarvestContext,
    MicroScalpSignal,
    MultiTimeframeBiasResult,
    RegimeResult,
    SwingPoint,
    TimeframeBiasDetail,
)
from tests import fixtures


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"


def _bias(direction: str = "bullish") -> MultiTimeframeBiasResult:
    layers = tuple(
        TimeframeBiasDetail(tf, direction, 0.7, role)  # type: ignore[arg-type]
        for tf, role in [
            ("H8", "macro"),
            ("H4", "macro"),
            ("H1", "structure"),
            ("M15", "setup"),
            ("M5", "setup"),
            ("M1", "precision_entry"),
        ]
    )
    return MultiTimeframeBiasResult(
        bias=direction,  # type: ignore[arg-type]
        confidence=0.75,
        explanation="offline test",
        layers=layers,
    )


def _swing(kind: str, price: float) -> SwingPoint:
    return SwingPoint(
        bar_index=10,
        time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=price,
        kind=kind,  # type: ignore[arg-type]
    )


@pytest.mark.offline
class TestConfigLoading:
    def test_project_config_loads(self):
        config = load_config(CONFIG_PATH)
        assert config.account.balance > 0
        assert config.trading.paper_enabled or config.trading.live_enabled
        assert len(config.trading.symbols) >= 1

    def test_temp_config_round_trip(self, write_config):
        path = write_config(fixtures.valid_config_data())
        config = load_config(path)
        assert config.trading.symbols == ("EURUSD", "GBPUSD")


@pytest.mark.offline
class TestRegimeDetection:
    def test_trending_regime(self, trending_candles):
        result = RegimeDetector().detect(trending_candles, spread_limit=2.0)
        assert result.regime == "trending"
        assert result.confidence > 0

    def test_ranging_regime(self, ranging_candles):
        result = RegimeDetector().detect(ranging_candles, spread_limit=2.0)
        assert result.regime == "ranging"


@pytest.mark.offline
class TestMarketStructureDetection:
    def test_bullish_structure(self, bullish_structure_candles):
        context = MarketStructureAnalyzer().analyze(
            bullish_structure_candles,
            symbol="EURUSD",
        )
        assert context.trend == "bullish"
        assert len(context.swing_highs) > 0
        assert len(context.swing_lows) > 0


@pytest.mark.offline
class TestHarvestRules:
    def test_blocks_without_directional_bias(self):
        from strategies.models import MarketContext

        structure = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            trend="bullish",
            higher_highs=True,
            higher_lows=True,
            lower_highs=False,
            lower_lows=False,
            swing_highs=(_swing("high", 1.12), _swing("high", 1.13)),
            swing_lows=(_swing("low", 1.10), _swing("low", 1.11)),
            structure_events=(),
            support_zones=(),
            resistance_zones=(),
            liquidity_zones=(),
            last_bos=None,
            last_choch=None,
        )
        decision = HarvestEngine().evaluate(
            HarvestContext(
                symbol="EURUSD",
                bias=_bias("neutral"),
                structure=structure,
                regime=RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
                current_spread=1.5,
                spread_limit=2.0,
            )
        )
        assert decision.allowed is False
        assert decision.mode == "none"


@pytest.mark.offline
class TestEntryRules:
    def test_rejects_wide_spread(self):
        from execution.models import EntryContext
        from risk.models import PortfolioState
        from strategies.models import MarketContext

        structure = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            trend="bullish",
            higher_highs=True,
            higher_lows=True,
            lower_highs=False,
            lower_lows=False,
            swing_highs=(_swing("high", 1.12), _swing("high", 1.13)),
            swing_lows=(_swing("low", 1.10), _swing("low", 1.11)),
            structure_events=(),
            support_zones=(),
            resistance_zones=(),
            liquidity_zones=(),
            last_bos=None,
            last_choch=None,
        )
        decision = EntryEngine().evaluate(
            EntryContext(
                symbol="EURUSD",
                bias=_bias("bullish"),
                structure=structure,
                regime=RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
                momentum=MicroScalpSignal(action="buy", reason="ok", target_pips=2.0),
                current_spread=5.0,
                spread_limit=2.0,
                entry_price=1.1000,
                stop_loss=1.0980,
                portfolio=PortfolioState(balance=10_000, day_start_balance=10_000),
                risk_manager=RiskManager(RiskLimits()),
            )
        )
        assert decision.action == "reject"


@pytest.mark.offline
class TestExitRules:
    def test_stop_loss_exit(self):
        from execution.models import ExitContext
        from strategies.models import MarketContext

        structure = MarketContext(
            symbol="EURUSD",
            timeframe="M5",
            trend="bullish",
            higher_highs=True,
            higher_lows=True,
            lower_highs=False,
            lower_lows=False,
            swing_highs=(_swing("high", 1.12),),
            swing_lows=(_swing("low", 1.10),),
            structure_events=(),
            support_zones=(),
            resistance_zones=(),
            liquidity_zones=(),
            last_bos=None,
            last_choch=None,
        )
        candles = fixtures.ohlcv_from_closes(np.linspace(1.1000, 1.0970, 60), freq="min")
        decision = ExitEngine().evaluate(
            ExitContext(
                trade=OpenTrade(
                    symbol="EURUSD",
                    side="buy",
                    entry_price=1.1000,
                    stop_loss=1.0980,
                    volume=0.1,
                    take_profit=1.1030,
                ),
                current_price=1.0975,
                candles=candles,
                structure=structure,
            )
        )
        assert decision.action == "cut_loss"


@pytest.mark.offline
class TestPaperTrading:
    def test_round_trip_updates_balance(self, tmp_path: Path):
        trader = PaperTrader(
            PaperTraderConfig(
                initial_balance=10_000.0,
                spread_pips=0.0,
                log_path=tmp_path / "paper_trades.csv",
            )
        )
        trade = trader.open_trade(
            symbol="EURUSD",
            side="buy",
            entry_price=1.1000,
            lot_size=0.1,
            stop_loss=1.0980,
        )
        trader.close_trade(trade.trade_id, 1.1020)
        snapshot = trader.snapshot()
        assert snapshot.balance == pytest.approx(10_020.0)
        assert len(snapshot.open_trades) == 0


@pytest.mark.offline
class TestBacktestCalculations:
    def test_net_profit_matches_closed_trades(self):
        candles = fixtures.ohlcv_from_closes(
            np.array([1.1000, 1.1040]),
            freq="h",
        )
        candles.loc[0, ["open", "high", "low"]] = [1.1000, 1.1010, 1.0990]
        candles.loc[1, ["open", "high", "low"]] = [1.1005, 1.1050, 1.1000]

        signals = [
            TradeSignal(
                bar_index=0,
                side="buy",
                volume=0.1,
                stop_loss=1.0950,
                take_profit=1.1040,
            )
        ]
        result = Backtester(BacktestConfig(initial_balance=10_000, spread_pips=0.0)).run(
            candles,
            signals,
        )
        assert result.metrics.total_trades == 1
        assert result.trades[0].pnl > 0
        assert result.metrics.final_balance == pytest.approx(
            result.metrics.initial_balance + result.trades[0].pnl
        )
        assert result.metrics.gross_profit == pytest.approx(result.trades[0].pnl)


@pytest.mark.offline
class TestOrchestratorWithoutMT5:
    def test_cycle_runs_with_mocked_connector(self, tmp_path: Path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_dir.joinpath("config.yaml").write_text(
            CONFIG_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (tmp_path / "logs").mkdir()

        config = load_config(config_dir / "config.yaml")
        event_logger = KraitosEventLogger(tmp_path / "logs")
        runtime = KraitosRuntime.build(
            project_root=tmp_path,
            config=config,
            event_logger=event_logger,
        )

        frame = fixtures.ohlcv_from_closes(fixtures.trending_closes())
        bundle_data = {
            symbol: {tf: frame for tf in ("M1", "M5", "M15", "H1", "H4", "H8")}
            for symbol in config.trading.symbols
        }
        quote = MagicMock(bid=1.1000, ask=1.10015, spread=0.00015)

        runtime.connector.connect = MagicMock()
        runtime.connector.disconnect = MagicMock()
        runtime.connector.get_quote = MagicMock(return_value=quote)

        with patch("core.orchestrator.fetch_market_data") as fetch_mock:
            fetch_mock.return_value = MarketDataBundle(data=bundle_data)
            summary = KraitosOrchestrator(runtime)._run_cycle(trace_id="offline-test")

        assert summary.symbols_processed == len(config.trading.symbols)
        assert (tmp_path / "logs" / "dashboard_state.json").exists()
        runtime.connector.get_quote.assert_called()
