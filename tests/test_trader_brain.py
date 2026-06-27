"""Tests for Trader Brain — no conservative execution imports, indicators don't veto."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from brains.models import TraderContext
from brains.trader_brain import TraderBrain
from config import load_config
from core.runtime import KraitosRuntime
from intelligence.indicator_confirmation import IndicatorConfirmationEngine
from logs.event_logger import KraitosEventLogger

pytestmark = pytest.mark.offline

FORBIDDEN_TRADER_IMPORTS = frozenset({
    "backtesting.execution_model",
    "backtesting.conservative_backtest_engine",
    "validation.conservative_validation",
    "validation.strategy_validator",
    "controls.strategy_quality_gate",
})


def _project_root(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    config_dir.joinpath("config.yaml").write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir()
    return tmp_path


def _candle_frame(rows: int = 120) -> pd.DataFrame:
    times = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series([1.10 + (index * 0.0001) for index in range(rows)])
    return pd.DataFrame(
        {
            "time": times,
            "open": close - 0.0002,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": 1000,
            "spread": 1.0,
        }
    )


def test_trader_brain_module_has_no_forbidden_imports():
    source = Path(__file__).resolve().parent.parent / "brains" / "trader_brain.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    violations = imported & FORBIDDEN_TRADER_IMPORTS
    assert not violations, f"Trader brain imports forbidden modules: {violations}"


def test_trader_brain_evaluate_returns_candidate(tmp_path: Path):
    root = _project_root(tmp_path)
    config = load_config(root / "config" / "config.yaml")
    event_logger = KraitosEventLogger(root / "logs")
    runtime = KraitosRuntime.build(
        project_root=root,
        config=config,
        event_logger=event_logger,
    )
    from core.risk_controller import RiskController

    risk_controller = RiskController(
        config=config,
        risk_manager=runtime.risk_manager,
        paper_trader=runtime.paper_trader,
        project_root=root,
    )
    brain = TraderBrain(
        config=config,
        regime_detector=runtime.regime_detector,
        bias_analyzer=runtime.bias_analyzer,
        structure_analyzer=runtime.structure_analyzer,
        harvest_engine=runtime.harvest_engine,
        micro_scalper=runtime.micro_scalper,
        entry_engine=runtime.entry_engine,
        risk_controller=risk_controller,
        news_filter=runtime.news_filter,
        pair_analyzer=runtime.pair_analyzer,
        project_root=root,
    )
    frame = _candle_frame()
    candles = {tf: frame for tf in ("M1", "M5", "M15", "H1", "H4", "H8")}
    context = TraderContext(
        symbol="EURUSD",
        candles=candles,
        bid=1.1000,
        ask=1.10012,
        spread_pips=1.2,
        spread_limit=3.0,
        trace_id="test-trace",
    )
    candidate = brain.evaluate(context)
    assert candidate.symbol == "EURUSD"
    assert candidate.regime is not None
    assert candidate.bias is not None
    assert candidate.structure is not None
    assert brain.stats.symbols_scanned == 1


def test_indicators_interpret_only_never_veto():
    """Indicators never block — worst case is zero insight."""
    from intelligence.indicator_interpretation_engine import IndicatorInterpretationEngine

    engine = IndicatorInterpretationEngine()
    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

    structure = MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(),
        swing_lows=(),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )
    bias = MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.7,
        explanation="test bias",
        layers=(),
    )
    result = engine.interpret(
        symbol="EURUSD",
        candles={},
        structure=structure,
        bias=bias,
        regime=RegimeResult("trending", 0.6, "t"),
        narrative_direction="bullish",
    )
    assert result.insight_score >= 0.0
    blob = result.market_explanation_contribution.lower()
    assert "veto" not in blob
    assert "reject" not in blob


def test_indicators_boost_only_never_veto():
    """Legacy confirmation API — boost only via interpretation."""
    engine = IndicatorConfirmationEngine()
    from strategies.models import MarketContext, MultiTimeframeBiasResult

    structure = MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        trend="bullish",
        higher_highs=True,
        higher_lows=True,
        lower_highs=False,
        lower_lows=False,
        swing_highs=(),
        swing_lows=(),
        structure_events=(),
        support_zones=(),
        resistance_zones=(),
        liquidity_zones=(),
        last_bos=None,
        last_choch=None,
    )
    bias = MultiTimeframeBiasResult(
        bias="bullish",
        confidence=0.7,
        explanation="test bias",
        layers=(),
    )
    result = engine.confirm(
        features=None,
        structure=structure,
        bias=bias,
        narrative_direction="bullish",
    )
    assert result.boost >= 0.0
    assert "veto" not in result.reason.lower()


def test_pipeline_delegates_to_trader_brain(tmp_path: Path):
    root = _project_root(tmp_path)
    config = load_config(root / "config" / "config.yaml")
    event_logger = KraitosEventLogger(root / "logs")
    runtime = KraitosRuntime.build(
        project_root=root,
        config=config,
        event_logger=event_logger,
    )
    from core.pipeline import TradingPipeline
    from core.risk_controller import RiskController

    risk_controller = RiskController(
        config=config,
        risk_manager=runtime.risk_manager,
        paper_trader=runtime.paper_trader,
        project_root=root,
    )
    pipeline = TradingPipeline(
        config=config,
        regime_detector=runtime.regime_detector,
        bias_analyzer=runtime.bias_analyzer,
        structure_analyzer=runtime.structure_analyzer,
        harvest_engine=runtime.harvest_engine,
        micro_scalper=runtime.micro_scalper,
        entry_engine=runtime.entry_engine,
        risk_controller=risk_controller,
        news_filter=runtime.news_filter,
        pair_analyzer=runtime.pair_analyzer,
        project_root=root,
    )
    assert pipeline.trader_brain is not None
    assert isinstance(pipeline.trader_brain, TraderBrain)


def test_dna_statement_exported():
    from brains import DNA_STATEMENT

    assert "Trader hunts" in DNA_STATEMENT
    assert "Auditor verifies" in DNA_STATEMENT
