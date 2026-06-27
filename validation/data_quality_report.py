"""Write logs/data_quality_report.md from validation payload."""

from __future__ import annotations

from pathlib import Path


def write_data_quality_report(project_root: Path, payload: dict) -> Path:
    """Persist a human-readable data quality summary."""
    path = project_root / "logs" / "data_quality_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = payload.get("summary", {})
    errors = payload.get("errors", {})
    walk_forward = payload.get("walk_forward", {})
    conservative = payload.get("conservative_metrics", {})

    lines = [
        "# Kraitos Data Quality Report",
        "",
        f"**Generated:** {payload.get('generated_at', 'unknown')}",
        f"**Validation engine:** {payload.get('validation_engine', 'unknown')}",
        f"**Data source:** `{payload.get('data_source', 'unknown')}`",
        f"**Trust verdict:** `{payload.get('trust_verdict', 'unknown')}`",
        f"**Data quality score:** {payload.get('data_quality_score', 0.0)}",
        "",
        "## Coverage",
        "",
        f"- Walk-forward years: **{', '.join(str(y) for y in walk_forward.get('years_covered', []))}**",
        f"- Symbols: **{', '.join(walk_forward.get('symbols_covered', []))}**",
        f"- Conservative closed trades: **{conservative.get('total_trades', 0)}**",
        f"- Paper closed trades: **{summary.get('paper_trades', 0)}**",
        "",
        "## Conservative metrics",
        "",
        f"- Win rate: **{float(conservative.get('win_rate', 0.0)):.1%}**",
        f"- Profit factor: **{conservative.get('profit_factor', 0)}**",
        f"- Max drawdown: **{float(conservative.get('max_drawdown_pct', 0.0)):.2f}%**",
        f"- Average R: **{float(conservative.get('average_r', 0.0)):+.2f}R**",
        "",
        "## Error classification",
        "",
        f"- Expected test errors: **{errors.get('expected_test_count', 0)}**",
        f"- Real runtime errors: **{errors.get('real_runtime_count', 0)}**",
        f"- Critical runtime errors: **{errors.get('critical_runtime_count', 0)}**",
        "",
    ]

    for label, key in (
        ("Expected test errors", "expected_test_errors"),
        ("Real runtime errors", "real_runtime_errors"),
        ("Critical runtime errors", "critical_runtime_errors"),
    ):
        items = errors.get(key, [])
        if items:
            lines.append(f"### {label}")
            lines.append("")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    by_symbol = walk_forward.get("by_symbol", {})
    if by_symbol:
        lines.append("## Per-symbol conservative trades")
        lines.append("")
        for symbol, metrics in sorted(by_symbol.items()):
            lines.append(
                f"- **{symbol}**: {metrics.get('total_trades', 0)} trades, "
                f"PF {metrics.get('profit_factor', 0)}, "
                f"avg R {float(metrics.get('average_r', 0.0)):+.2f}"
            )
        lines.append("")

    if payload.get("data_source") == "synthetic":
        lines.extend(
            [
                "## Synthetic data notice",
                "",
                "Walk-forward validation used **synthetic** candles. "
                "Trust verdict is capped at `QUESTIONABLE` until broker or imported "
                "historical data is available.",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
