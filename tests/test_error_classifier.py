"""Tests for validation error classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.error_classifier import classify_errors

pytestmark = pytest.mark.offline


def _write_errors(path: Path, messages: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event_type, message in messages:
            handle.write(
                json.dumps({"event_type": event_type, "message": message, "category": "errors"})
                + "\n"
            )


def test_emergency_stop_is_expected_test_error(tmp_path: Path):
    errors_path = tmp_path / "logs" / "json" / "errors.jsonl"
    _write_errors(
        errors_path,
        [("error", "Emergency stop activated: Operator emergency stop")],
    )
    result = classify_errors(errors_path)
    assert result.expected_test_count == 1
    assert result.critical_count == 0


def test_fatal_error_is_critical_runtime(tmp_path: Path):
    errors_path = tmp_path / "logs" / "json" / "errors.jsonl"
    _write_errors(errors_path, [("error", "Fatal broker connection failed")])
    result = classify_errors(errors_path)
    assert result.critical_count == 1
    assert result.expected_test_count == 0
