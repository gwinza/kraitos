"""Tests for Kraitos V8 Reality Engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

from reality.division_investigator import DivisionInvestigator
from reality.elimination_engine import ConvergenceEngine, EliminationEngine
from reality.reality_adapter import reality_as_entry_proxy
from reality.reality_engine import RealityEngine
from reality.reality_models import REALITY_FIRST_LAW, WorldModel
from reality.world_model_catalog import world_models_for_event
from strategies.models import RegimeResult
from tests.test_entry_engine import _bias, _structure


def _candidate(**kwargs):
    from brains.models import TradeCandidate

    candidate = TradeCandidate(
        symbol=kwargs.get("symbol", "EURUSD"),
        trace_id=kwargs.get("trace", "test"),
        bid=kwargs.get("bid", 1.10),
        ask=kwargs.get("ask", 1.1002),
        spread_pips=kwargs.get("spread_pips", 1.5),
        spread_limit=kwargs.get("spread_limit", 3.0),
    )
    candidate.bias = kwargs.get("bias", _bias("bearish"))
    candidate.structure = kwargs.get("structure", _structure("bearish"))
    candidate.regime = kwargs.get(
        "regime",
        RegimeResult(regime="trending", confidence=0.7, reason="ok"),  # type: ignore[arg-type]
    )
    candidate.pair_allowed = True
    candidate.news_allowed = True
    return candidate


def test_world_models_generated_for_bullish_sweep():
    models = world_models_for_event(
        event_signature="liquidity sweep below support with bullish reclaim",
        direction_hint="bullish",
    )
    ids = {m.model_id for m in models}
    assert "liquidity_sweep_low" in ids
    assert "bull_trap" in ids
    assert "institutional_accumulation" in ids
    assert len(models) >= 4


def test_elimination_weakens_model_on_contrary_evidence():
    models = world_models_for_event(
        event_signature="bearish breakdown",
        direction_hint="bearish",
    )
    target = next((m for m in models if m.model_id == "bear_trap"), models[0])
    investigations = DivisionInvestigator().investigate_all(
        models=(target,),
        departments=(),
        council_observations=(),
    )
    from reality.reality_models import DivisionInvestigation

    invs = investigations + (
        DivisionInvestigation(
            division="trend",
            world_model_id=target.model_id,
            strengthens=False,
            weakens=True,
            evidence=("Weakens: bearish breakdown",),
            confidence=80.0,
        ),
    )
    result = EliminationEngine().eliminate((target,), invs)
    assert result[0].explanatory_power < target.explanatory_power


def test_convergence_selects_dominant_model():
    models = (
        WorldModel(
            model_id="a",
            name="A",
            description="",
            direction="bullish",
            assumptions=(),
            expected_events=(),
            falsification_events=(),
            explanatory_power=72.0,
            status="active",
        ),
        WorldModel(
            model_id="b",
            name="B",
            description="",
            direction="bearish",
            assumptions=(),
            expected_events=(),
            falsification_events=(),
            explanatory_power=45.0,
            status="active",
        ),
    )
    converged = ConvergenceEngine().converge(models)
    dominant = next(m for m in converged if m.status == "dominant")
    assert dominant.model_id == "a"


def test_reality_engine_full_cycle(tmp_path: Path):
    decision = RealityEngine(tmp_path).evaluate(_candidate())
    assert decision.symbol == "EURUSD"
    assert len(decision.world_models) >= 4
    assert decision.investigations
    assert decision.convergence.summary
    assert decision.thesis.reality_narrative
    assert REALITY_FIRST_LAW in decision.to_dict()["first_law"]


def test_reality_adapter_for_entry_proxy(tmp_path: Path):
    decision = RealityEngine(tmp_path).evaluate(_candidate())
    proxy = reality_as_entry_proxy(decision)
    assert hasattr(proxy, "participation")
    assert hasattr(proxy.thesis, "thesis_clear")
    assert proxy.mind_state in {"converged", "converging", "uncertain", "investigating"}


def test_reality_snapshot_v8_json(tmp_path: Path):
    from reality.reality_reports import reality_journal_fields

    decision = RealityEngine(tmp_path).evaluate(_candidate())
    fields = reality_journal_fields(decision)
    payload = json.loads(fields["reality_snapshot"])
    assert payload["version"] == "v8"
    assert "world_models" in payload
