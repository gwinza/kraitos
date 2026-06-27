"""Story-Aware Participation Doctrine — validation and runtime reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from intelligence.participation_tracker import get_participation_tracker
from intelligence.story_aware_participation_doctrine import (
    MARKET_STORY_QUESTIONS,
    STORY_AWARE_PARTICIPATION_DNA,
)


def write_story_aware_participation_doctrine_report(project_root: Path) -> Path:
    """Permanent DNA checkpoint for Story-Aware Participation Edition."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Story-Aware Participation Doctrine Report",
        "",
        f"**Generated:** {now}",
        "",
        "## DNA",
        "",
        STORY_AWARE_PARTICIPATION_DNA,
        "",
        "## Market story questions (single coherent explanation)",
        "",
    ]
    for idx, question in enumerate(MARKET_STORY_QUESTIONS, 1):
        lines.append(f"{idx}. {question}")
    lines.extend([
        "",
        "## Forbidden mechanisms",
        "",
        "No new filters, vetoes, consensus thresholds, indicator gates, trade caps, or rank-and-drop.",
        "",
    ])
    path = logs / "story_aware_participation_doctrine_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_participation_activity_report(
    project_root: Path,
    *,
    harvest_stats: dict | None = None,
    synthesis_stats: dict | None = None,
    reasoning_stats: dict | None = None,
    psychology_stats: dict | None = None,
) -> Path:
    """Report opportunities seen, taken, missed, and harvest windows."""
    project_root = project_root.resolve()
    logs = project_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    tracker = get_participation_tracker()
    summary = tracker.summary()
    harvest = harvest_stats or {}
    synthesis = synthesis_stats or {}
    reasoning = reasoning_stats or {}
    psychology = psychology_stats or {}

    lines = [
        "# Story-Aware Participation Activity Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Story explanations",
        "",
        f"- Synthesis story-clear: **{synthesis.get('story_clear', 0)}**",
        f"- Synthesis story-unclear: **{synthesis.get('story_unclear', 0)}**",
        f"- Human reasoning explained: **{reasoning.get('explained', 0)}**",
        f"- Psychology inferences: **{psychology.get('inferences', 0)}**",
        "",
        "## Harvest windows (1–5 pip story-aware)",
        "",
        f"- Candles probed: **{harvest.get('candles_probed', 0)}**",
        f"- Windows detected: **{harvest.get('windows_detected', 0)}**",
        f"- Micro harvests approved: **{harvest.get('micro_harvests_approved', 0)}**",
        f"- Story participation overrides: **{harvest.get('story_overrides', 0)}**",
        "",
        "## Opportunities",
        "",
        f"- Seen: **{summary['opportunities_seen']}**",
        f"- Taken: **{summary['opportunities_taken']}**",
        f"- Missed: **{summary['opportunities_missed']}**",
        f"- Max simultaneous open: **{summary['simultaneous_trades_max']}**",
        "",
        "## Pips",
        "",
        f"- Average pips targeted: **{summary['avg_pips_targeted']}**",
        f"- Average pips captured: **{summary['avg_pips_captured']}**",
        "",
        "## Trades by class",
        "",
        "| Class | Count |",
        "|-------|-------|",
    ]
    for tier in ("MICRO_HARVEST", "HARVEST", "PROPER", "ELITE", "SCOUT"):
        count = summary.get("trades_by_class", {}).get(tier, 0)
        lines.append(f"| {tier} | {count} |")

    lines.extend(["", "## Trades by asset", "", "| Symbol | Count |", "|--------|-------|"])
    for symbol, count in sorted(
        summary.get("trades_by_asset", {}).items(),
        key=lambda x: x[1],
        reverse=True,
    )[:15]:
        lines.append(f"| {symbol} | {count} |")

    lines.extend(["", "## Harvest patterns detected", ""])
    patterns = harvest.get("patterns") or summary.get("harvest_patterns", {})
    if patterns:
        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {pattern}: {count}")
    else:
        lines.append("- (none recorded)")

    lines.extend(["", "## Top missed harvest reasons", ""])
    missed = harvest.get("missed_reasons") or dict(summary.get("top_missed_reasons", []))
    if missed:
        items = missed.items() if hasattr(missed, "items") else missed
        for reason, count in sorted(items, key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- (none recorded)")

    path = logs / "participation_activity_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_all_participation_reports(
    project_root: Path,
    *,
    quality_stats: dict | None = None,
    harvest_stats: dict | None = None,
) -> list[Path]:
    """Write full participation report suite."""
    stats = quality_stats or {}
    paths = [
        write_story_aware_participation_doctrine_report(project_root),
        write_participation_activity_report(
            project_root,
            harvest_stats=harvest_stats,
            synthesis_stats=stats.get("synthesis"),
            reasoning_stats=stats.get("reasoning"),
            psychology_stats=stats.get("psychology"),
        ),
    ]
    return paths
