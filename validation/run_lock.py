"""Exclusive lock for validation runs — prevents competing validation processes."""

from __future__ import annotations

import atexit
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from loguru import logger

STALE_LOCK_HOURS = 6
LOCK_FILENAME = "validation.lock"

VALIDATION_CMD_MARKERS = (
    "conservative_validation",
    "run_validation",
    "run_single_validation",
    "kraitos validation",
)


class ValidationLockError(Exception):
    """Base error for validation lock operations."""


class LockHeldError(ValidationLockError):
    """Another validation run holds the lock."""


@dataclass(frozen=True)
class LockInfo:
    """Contents of logs/validation.lock."""

    pid: int
    start_time: str
    command: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LockInfo:
        return cls(
            pid=int(raw["pid"]),
            start_time=str(raw["start_time"]),
            command=str(raw.get("command", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "start_time": self.start_time,
            "command": self.command,
        }


def lock_path(project_root: Path) -> Path:
    return project_root.resolve() / "logs" / LOCK_FILENAME


def read_lock(project_root: Path) -> LockInfo | None:
    path = lock_path(project_root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return LockInfo.from_dict(raw)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def is_stale(lock_info: LockInfo, *, now: datetime | None = None) -> bool:
    moment = now or datetime.now(timezone.utc)
    try:
        started = datetime.fromisoformat(lock_info.start_time.replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return moment - started > timedelta(hours=STALE_LOCK_HOURS)


def remove_lock(project_root: Path) -> None:
    path = lock_path(project_root)
    if path.exists():
        path.unlink()


def write_lock(project_root: Path, info: LockInfo) -> Path:
    path = lock_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info.to_dict(), indent=2), encoding="utf-8")
    return path


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        alive = bool(
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            and exit_code.value == 259
        )
        ctypes.windll.kernel32.CloseHandle(handle)
        return alive
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _iter_python_processes() -> list[tuple[int, str]]:
    import subprocess

    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match 'python' } | "
            "Select-Object ProcessId, CommandLine | "
            "ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        payload = json.loads(result.stdout)
        if isinstance(payload, dict):
            payload = [payload]
        rows: list[tuple[int, str]] = []
        for item in payload:
            pid = int(item.get("ProcessId", 0))
            cmd = str(item.get("CommandLine") or "")
            if pid > 0:
                rows.append((pid, cmd))
        return rows

    result = subprocess.run(
        ["ps", "-ax", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid = int(parts[0])
        rows.append((pid, parts[1]))
    return rows


def _matches_validation_command(command_line: str) -> bool:
    lowered = command_line.lower()
    return any(marker in lowered for marker in VALIDATION_CMD_MARKERS)


def terminate_duplicate_validation_processes(*, exclude_pid: int | None = None) -> list[int]:
    """Stop other validation Python processes. Returns terminated PIDs."""
    current = exclude_pid if exclude_pid is not None else os.getpid()
    terminated: list[int] = []
    for pid, command_line in _iter_python_processes():
        if pid == current:
            continue
        if not _matches_validation_command(command_line):
            continue
        try:
            if sys.platform == "win32":
                import subprocess

                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                import signal

                os.kill(pid, signal.SIGTERM)
            terminated.append(pid)
            logger.warning("Terminated duplicate validation process pid={} cmd={}", pid, command_line)
        except OSError as exc:
            logger.warning("Failed to terminate pid={}: {}", pid, exc)
    return terminated


def cleanup_stale_lock(project_root: Path, *, force: bool) -> bool:
    """
    Remove a stale lock when force=True.

    Returns True when a stale lock was removed.
    """
    info = read_lock(project_root)
    if info is None:
        return False
    if not is_stale(info):
        return False
    if not force:
        return False
    logger.warning(
        "Removing stale validation lock (older than {}h): pid={} started={}",
        STALE_LOCK_HOURS,
        info.pid,
        info.start_time,
    )
    remove_lock(project_root)
    return True


class ValidationRunLock:
    """Context manager that owns the validation lock lifecycle."""

    def __init__(
        self,
        project_root: Path,
        *,
        command: str,
        force: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.command = command
        self.force = force
        self._acquired = False
        self._info: LockInfo | None = None
        self._atexit_registered = False

    def prepare(self) -> None:
        """Pre-run setup: kill duplicates and optionally clear stale lock."""
        if self.force:
            terminate_duplicate_validation_processes(exclude_pid=os.getpid())
            cleanup_stale_lock(self.project_root, force=True)

    def acquire(self) -> LockInfo:
        existing = read_lock(self.project_root)
        if existing is not None:
            if self.force and is_stale(existing):
                logger.warning(
                    "Removing stale validation lock before acquire: pid={} started={}",
                    existing.pid,
                    existing.start_time,
                )
                remove_lock(self.project_root)
                existing = None
            elif existing.pid == os.getpid():
                existing = None
            elif _process_alive(existing.pid):
                raise LockHeldError(
                    f"Validation lock held by pid={existing.pid} since {existing.start_time}"
                )
            else:
                logger.warning(
                    "Removing orphan validation lock for dead pid={}",
                    existing.pid,
                )
                remove_lock(self.project_root)
                existing = None

        if existing is not None:
            raise LockHeldError(
                f"Validation lock exists (pid={existing.pid}, started={existing.start_time})"
            )

        self._info = LockInfo(
            pid=os.getpid(),
            start_time=datetime.now(timezone.utc).isoformat(),
            command=self.command,
        )
        write_lock(self.project_root, self._info)
        self._acquired = True
        if not self._atexit_registered:
            atexit.register(self.release)
            self._atexit_registered = True
        return self._info

    def release(self) -> None:
        if not self._acquired:
            return
        current = read_lock(self.project_root)
        if current is not None and current.pid == os.getpid():
            remove_lock(self.project_root)
        self._acquired = False

    def __enter__(self) -> LockInfo:
        self.prepare()
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
