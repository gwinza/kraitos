"""Export demo opportunities JSON for mobile offline mode."""

from __future__ import annotations

import json
from pathlib import Path

from brains.sports_brain import SportsBrain


def main() -> None:
    brain = SportsBrain()
    analyses = brain.scan_and_analyze()
    payload = [a.to_dict() for a in analyses]
    out = Path(__file__).resolve().parents[1] / "mobile" / "kraitos-sports" / "src" / "api" / "demo_opportunities.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Exported {len(payload)} opportunities to {out}")


if __name__ == "__main__":
    main()
