"""Tests for thesis projection self-learning engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from intelligence.thesis_projection_learning_engine import (
    reset_thesis_projection_learning_engine,
)


def test_learning_adapts_from_journal(tmp_path: Path) -> None:
    engine = reset_thesis_projection_learning_engine(tmp_path)
    journal = tmp_path / "journal.csv"
    journal.write_text(
        "trade_id,result,r_multiple,net_pl\n",
        encoding="utf-8",
    )
    for i in range(9):
        tid = f"t{i}"
        engine.record_pending_entry(
            trade_id=tid,
            personality="LIQUIDITY_SWEEP_REVERSAL",
            side="buy",
            in_active_session=True,
            thesis_confidence=70.0,
            projected_reward_r=1.5,
        )
        pd.DataFrame(
            [{"trade_id": tid, "result": "loss", "r_multiple": -0.5, "net_pl": -50}]
        ).to_csv(journal, mode="a", header=False, index=False)

    engine.refresh_from_journal(journal)
    adj = engine.get_adjustments(
        personality="LIQUIDITY_SWEEP_REVERSAL",
        side="buy",
        in_active_session=True,
    )
    assert adj.size_multiplier_delta <= 0
