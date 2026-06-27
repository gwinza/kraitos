"""Pair specialisation gating helpers."""

from __future__ import annotations

from pathlib import Path

from analytics.pair_specialisation import (
    DEFAULT_OUTPUT_PATH,
    PairSpecialisationAnalyzer,
    PairSpecialisationError,
)


def pair_trading_allowed(
    symbol: str,
    *,
    analyzer: PairSpecialisationAnalyzer,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
) -> tuple[bool, str]:
    """Return whether a symbol is allowed to trade based on pair specialisation."""
    path = Path(output_path)
    if not path.exists():
        return True, "Pair specialisation not available; default allow"

    try:
        result = analyzer.load(path)
    except PairSpecialisationError:
        return True, "Pair specialisation unreadable; default allow"

    for entry in result.pairs:
        if entry.symbol == symbol.strip().upper():
            if entry.trading_allowed:
                return True, entry.reason
            return False, entry.reason
    return True, "Symbol not classified yet; default allow"
