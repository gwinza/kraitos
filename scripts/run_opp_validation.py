"""Run conservative validation and persist summary metrics."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validation.conservative_validation import WalkForwardConfig, run_conservative_validation


def main() -> None:
    project_root = PROJECT_ROOT
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    try:
        cfg = WalkForwardConfig(include_optimistic_demo=False)
        result = run_conservative_validation(project_root, config=cfg)
        metrics = result.conservative_metrics
        (logs / "validation_run_result.txt").write_text(
            "\n".join(
                [
                    f"trades={metrics.total_trades}",
                    f"wr={metrics.win_rate}",
                    f"pf={metrics.profit_factor}",
                    f"dd={metrics.max_drawdown_pct}",
                    f"avg_r={metrics.average_r}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        (logs / "validation_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
