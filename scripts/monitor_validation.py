"""Poll validation process until completion."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PID = int(sys.argv[1]) if len(sys.argv) > 1 else 15948
ROOT = Path(__file__).resolve().parent.parent
PROGRESS = ROOT / "logs" / "validation_progress.json"
TIMEOUT_SEC = int(sys.argv[2]) if len(sys.argv) > 2 else 2400


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok and exit_code.value == 259)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    deadline = time.time() + TIMEOUT_SEC
    last = ""
    while time.time() < deadline:
        if not alive(PID):
            print("PROCESS_DONE")
            return 0
        if PROGRESS.exists():
            cur = PROGRESS.read_text(encoding="utf-8")
            if cur != last:
                data = json.loads(cur)
                print(
                    f"year={data.get('current_year')} "
                    f"symbol={data.get('current_symbol')} "
                    f"trades={data.get('closed_trades_so_far')} "
                    f"elapsed={data.get('elapsed_seconds')}"
                )
                last = cur
        time.sleep(60)
    print("TIMEOUT")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
