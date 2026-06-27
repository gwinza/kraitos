import json, time, subprocess
from pathlib import Path
root = Path(r"C:/Users/Asus/kraitos")
pid = 19852
deadline = time.time() + 40 * 60
def alive(p):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {p}"], capture_output=True, text=True)
    return str(p) in r.stdout
while time.time() < deadline:
    if not alive(pid):
        print("PROCESS_ENDED")
        break
    report = root / "logs" / "market_story_validation_report.md"
    if report.exists():
        print("REPORT_READY")
        break
    prog = root / "logs" / "validation_progress.json"
    if prog.exists():
        print(prog.read_text().strip())
    time.sleep(120)
else:
    print("TIMEOUT_WAIT")
