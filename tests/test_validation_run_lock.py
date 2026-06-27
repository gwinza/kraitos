"""Tests for validation run lock acquire/refuse/stale cleanup."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from validation.run_lock import (
    LockHeldError,
    LockInfo,
    ValidationRunLock,
    cleanup_stale_lock,
    is_stale,
    lock_path,
    read_lock,
    remove_lock,
    write_lock,
)

pytestmark = pytest.mark.offline


def _stale_info() -> LockInfo:
    old = datetime.now(timezone.utc) - timedelta(hours=7)
    return LockInfo(pid=99999, start_time=old.isoformat(), command="stale-run")


def test_acquire_writes_lock(tmp_path: Path):
    with ValidationRunLock(tmp_path, command="test acquire", force=False) as info:
        assert info.command == "test acquire"
        path = lock_path(tmp_path)
        assert path.exists()
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["pid"] == info.pid
        assert stored["start_time"] == info.start_time

    assert not lock_path(tmp_path).exists()


def test_refuse_when_lock_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    held_pid = 424242
    write_lock(
        tmp_path,
        LockInfo(pid=held_pid, start_time=datetime.now(timezone.utc).isoformat(), command="other"),
    )
    monkeypatch.setattr("validation.run_lock._process_alive", lambda pid: pid == held_pid)

    with pytest.raises(LockHeldError):
        with ValidationRunLock(tmp_path, command="blocked", force=False):
            pass


def test_stale_cleanup_with_force(tmp_path: Path):
    write_lock(tmp_path, _stale_info())
    assert read_lock(tmp_path) is not None
    assert is_stale(_stale_info())

    removed = cleanup_stale_lock(tmp_path, force=True)
    assert removed is True
    assert read_lock(tmp_path) is None


def test_stale_lock_not_removed_without_force(tmp_path: Path):
    write_lock(tmp_path, _stale_info())
    removed = cleanup_stale_lock(tmp_path, force=False)
    assert removed is False
    assert read_lock(tmp_path) is not None
    remove_lock(tmp_path)


def test_force_acquire_after_stale_lock(tmp_path: Path):
    write_lock(tmp_path, _stale_info())

    with ValidationRunLock(tmp_path, command="forced", force=True) as info:
        assert info.command == "forced"
        assert read_lock(tmp_path).pid == info.pid

    assert not lock_path(tmp_path).exists()
