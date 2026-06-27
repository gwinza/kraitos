"""Tests for the news filter placeholder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from strategies import NewsEvent, NewsFilter, NewsFilterError


def _event(
    *,
    currency: str = "USD",
    impact: str = "high",
    news_time: datetime | None = None,
    before: int | None = None,
    after: int | None = None,
) -> NewsEvent:
    return NewsEvent(
        news_time=news_time or datetime(2025, 6, 6, 13, 30, tzinfo=timezone.utc),
        currency=currency,
        impact_level=impact,  # type: ignore[arg-type]
        restriction_before_minutes=before,
        restriction_after_minutes=after,
        title="NFP Release",
    )


def test_blocks_affected_pair_during_restriction_window():
    news_filter = NewsFilter(
        events=[_event(currency="USD", impact="high")],
        known_symbols=("EURUSD", "GBPUSD", "USDJPY"),
    )
    during = datetime(2025, 6, 6, 13, 25, tzinfo=timezone.utc)

    result = news_filter.check_symbol("EURUSD", at_time=during)

    assert result.allowed is False
    assert "blocked" in result.reason.lower()
    assert "EURUSD" in result.affected_pairs or "USD" in result.reason


def test_allows_trading_outside_restriction_window():
    news_filter = NewsFilter(
        events=[_event(currency="USD", impact="high")],
        known_symbols=("EURUSD",),
    )
    after_window = datetime(2025, 6, 6, 14, 0, tzinfo=timezone.utc)

    result = news_filter.check_symbol("EURUSD", at_time=after_window)

    assert result.allowed is True


def test_does_not_block_unrelated_pair():
    news_filter = NewsFilter(
        events=[_event(currency="USD", impact="high")],
        known_symbols=("EURUSD", "EURGBP"),
    )
    during = datetime(2025, 6, 6, 13, 29, tzinfo=timezone.utc)

    result = news_filter.check_symbol("EURGBP", at_time=during)

    assert result.allowed is True


def test_custom_restriction_windows():
    news_time = datetime(2025, 6, 6, 12, 0, tzinfo=timezone.utc)
    news_filter = NewsFilter(
        events=[_event(currency="EUR", before=10, after=5, news_time=news_time)],
        known_symbols=("EURUSD",),
    )

    blocked = news_filter.check_symbol(
        "EURUSD",
        at_time=news_time - timedelta(minutes=8),
    )
    allowed = news_filter.check_symbol(
        "EURUSD",
        at_time=news_time - timedelta(minutes=15),
    )

    assert blocked.allowed is False
    assert allowed.allowed is True


def test_get_restricted_pairs():
    news_filter = NewsFilter(
        events=[_event(currency="USD")],
        known_symbols=("EURUSD", "GBPUSD", "EURGBP"),
    )
    during = datetime(2025, 6, 6, 13, 30, tzinfo=timezone.utc)

    restricted = news_filter.get_restricted_pairs(at_time=during)

    assert "EURUSD" in restricted
    assert "GBPUSD" in restricted
    assert "EURGBP" not in restricted


def test_is_news_risk_active_helper():
    news_filter = NewsFilter(events=[_event(currency="JPY")], known_symbols=("USDJPY",))
    during = datetime(2025, 6, 6, 13, 20, tzinfo=timezone.utc)

    assert news_filter.is_news_risk_active("USDJPY", at_time=during) is True


def test_rejects_invalid_currency():
    with pytest.raises(NewsFilterError, match="Invalid currency"):
        NewsFilter().add_event(
            NewsEvent(
                news_time=datetime.now(timezone.utc),
                currency="US",
                impact_level="low",
            )
        )
