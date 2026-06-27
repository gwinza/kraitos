"""Checkpoint validation progress to logs/validation_progress.json."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from validation.r_metrics import CLOSED_RESULTS

MIN_UPDATE_INTERVAL_SECONDS = 120


class ValidationProgressTracker:
    """Write throttled progress snapshots during a validation run."""

    def __init__(
        self,
        project_root: Path,
        *,
        journal_path: Path,
        min_interval_seconds: int = MIN_UPDATE_INTERVAL_SECONDS,
    ) -> None:
        self.project_root = project_root.resolve()
        self.journal_path = journal_path
        self.path = self.project_root / "logs" / "validation_progress.json"
        self.min_interval_seconds = max(30, min_interval_seconds)
        self._started_at = time.monotonic()
        self._last_write = 0.0
        self.current_year: int | None = None
        self.current_symbol: str | None = None

    def on_timeline(self, moment: datetime, symbol: str) -> None:
        """Hook from backtest engine — update position and maybe checkpoint."""
        self.current_year = moment.year
        self.current_symbol = symbol
        self.maybe_write()

    def maybe_write(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_write) < self.min_interval_seconds:
            return
        self._write()
        self._last_write = now

    def finalize(self) -> None:
        self._write()

    def _journal_counts(self) -> tuple[int, int]:
        if not self.journal_path.exists():
            return 0, 0
        try:
            frame = pd.read_csv(self.journal_path)
        except (OSError, ValueError, pd.errors.EmptyDataError):
            return 0, 0
        if frame.empty or "result" not in frame.columns:
            return 0, 0
        results = frame["result"].astype(str).str.lower()
        closed_trades = int(results.isin(CLOSED_RESULTS).sum())
        enter_events = int((results == "open").sum())
        return closed_trades, enter_events

    def _write(self) -> None:
        closed_trades, enter_events = self._journal_counts()
        payload = {
            "current_year": self.current_year,
            "current_symbol": self.current_symbol,
            "closed_trades_so_far": closed_trades,
            "enter_events_so_far": enter_events,
            "elapsed_seconds": round(time.monotonic() - self._started_at, 1),
            "last_update_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
