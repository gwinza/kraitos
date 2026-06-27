"""
News filter placeholder for Kraitos.

Accepts manually supplied economic events and blocks trading on affected
currency pairs during configurable restriction windows. No paid news API
integration is included.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from loguru import logger

from strategies.models import NewsEvent, NewsFilterResult, NewsImpactLevel

DEFAULT_RESTRICTION_WINDOWS: dict[NewsImpactLevel, tuple[int, int]] = {
    "low": (5, 5),
    "medium": (15, 10),
    "high": (30, 15),
}


@dataclass(frozen=True)
class NewsFilterConfig:
    """Default restriction windows by impact level (before, after minutes)."""

    restriction_windows: dict[NewsImpactLevel, tuple[int, int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.restriction_windows is None:
            object.__setattr__(self, "restriction_windows", dict(DEFAULT_RESTRICTION_WINDOWS))


class NewsFilterError(Exception):
    """Raised when news filter input is invalid."""


class NewsFilter:
    """Block trading on pairs affected by scheduled news events."""

    def __init__(
        self,
        events: list[NewsEvent] | None = None,
        config: NewsFilterConfig | None = None,
        *,
        known_symbols: tuple[str, ...] | None = None,
    ) -> None:
        self.config = config or NewsFilterConfig()
        self._events: list[NewsEvent] = []
        self._known_symbols = known_symbols
        if events:
            for event in events:
                self.add_event(event)

    def add_event(self, event: NewsEvent) -> None:
        """Register a manual news event."""
        self._validate_event(event)
        self._events.append(event)
        logger.debug(
            f"News event added: {event.currency} {event.impact_level} "
            f"at {self._parse_time(event.news_time).isoformat()}"
        )

    def clear_events(self) -> None:
        """Remove all registered events."""
        self._events.clear()

    def check_symbol(
        self,
        symbol: str,
        *,
        at_time: datetime | None = None,
    ) -> NewsFilterResult:
        """
        Check whether trading is allowed for a symbol at a given time.

        Returns:
            NewsFilterResult with allowed flag and explanation.
        """
        symbol_key = self._normalize_symbol(symbol)
        moment = self._ensure_utc(at_time or datetime.now(timezone.utc))

        for event in self._events:
            if not self._symbol_affected_by_currency(symbol_key, event.currency):
                continue

            if self._is_within_restriction_window(event, moment):
                before, after = self._restriction_window(event)
                affected = tuple(
                    sorted(
                        pair
                        for pair in self._symbols_for_currency(event.currency)
                        if self._symbol_affected_by_currency(pair, event.currency)
                    )
                )
                title = f" ({event.title})" if event.title else ""
                reason = (
                    f"Trading blocked for {symbol_key}: {event.currency} "
                    f"{event.impact_level} impact news{title} at "
                    f"{self._parse_time(event.news_time).isoformat()} "
                    f"(restriction -{before}m / +{after}m)"
                )
                return NewsFilterResult(
                    allowed=False,
                    reason=reason,
                    blocking_event=event,
                    affected_pairs=affected,
                )

        return NewsFilterResult(
            allowed=True,
            reason=f"No active news restriction for {symbol_key}",
        )

    def get_restricted_pairs(
        self,
        *,
        at_time: datetime | None = None,
    ) -> tuple[str, ...]:
        """Return all symbols blocked at the given time."""
        moment = self._ensure_utc(at_time or datetime.now(timezone.utc))
        symbols = set(self._all_symbols())

        blocked = [
            symbol
            for symbol in symbols
            if not self.check_symbol(symbol, at_time=moment).allowed
        ]
        return tuple(sorted(blocked))

    def is_news_risk_active(
        self,
        symbol: str,
        *,
        at_time: datetime | None = None,
    ) -> bool:
        """Return True when the symbol is inside a news restriction window."""
        return not self.check_symbol(symbol, at_time=at_time).allowed

    def symbols_for_currency(self, currency: str) -> tuple[str, ...]:
        """Return known symbols containing the given currency."""
        return tuple(sorted(self._symbols_for_currency(currency)))

    def _is_within_restriction_window(self, event: NewsEvent, moment: datetime) -> bool:
        news_time = self._parse_time(event.news_time)
        before_minutes, after_minutes = self._restriction_window(event)
        window_start = news_time - timedelta(minutes=before_minutes)
        window_end = news_time + timedelta(minutes=after_minutes)
        return window_start <= moment <= window_end

    def _restriction_window(self, event: NewsEvent) -> tuple[int, int]:
        default_before, default_after = self.config.restriction_windows[event.impact_level]
        before = (
            event.restriction_before_minutes
            if event.restriction_before_minutes is not None
            else default_before
        )
        after = (
            event.restriction_after_minutes
            if event.restriction_after_minutes is not None
            else default_after
        )
        return before, after

    def _symbols_for_currency(self, currency: str) -> list[str]:
        currency_key = self._normalize_currency(currency)
        if self._known_symbols:
            return [
                symbol
                for symbol in self._known_symbols
                if self._symbol_affected_by_currency(symbol, currency_key)
            ]

        # Placeholder fallback when no symbol universe is configured.
        majors = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD")
        pairs: list[str] = []
        for base in majors:
            for quote in majors:
                if base == quote:
                    continue
                pair = f"{base}{quote}"
                if self._symbol_affected_by_currency(pair, currency_key):
                    pairs.append(pair)
        return pairs

    def _all_symbols(self) -> list[str]:
        if self._known_symbols:
            return list(self._known_symbols)

        symbols: set[str] = set()
        for event in self._events:
            symbols.update(self._symbols_for_currency(event.currency))
        return sorted(symbols)

    @staticmethod
    def _symbol_affected_by_currency(symbol: str, currency: str) -> bool:
        symbol_key = symbol.strip().upper()
        currency_key = currency.strip().upper()
        if len(symbol_key) < 6:
            return currency_key in symbol_key
        base = symbol_key[:3]
        quote = symbol_key[3:6]
        return currency_key in {base, quote}

    def _validate_event(self, event: NewsEvent) -> None:
        self._normalize_currency(event.currency)
        if event.impact_level not in DEFAULT_RESTRICTION_WINDOWS:
            raise NewsFilterError(f"Invalid impact level: {event.impact_level}")
        self._parse_time(event.news_time)

        for minutes, label in (
            (event.restriction_before_minutes, "restriction_before_minutes"),
            (event.restriction_after_minutes, "restriction_after_minutes"),
        ):
            if minutes is not None and minutes < 0:
                raise NewsFilterError(f"{label} cannot be negative")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise NewsFilterError("symbol is required")
        return normalized

    @staticmethod
    def _normalize_currency(currency: str) -> str:
        normalized = currency.strip().upper()
        if len(normalized) != 3:
            raise NewsFilterError(f"Invalid currency code: {currency}")
        return normalized

    @staticmethod
    def _parse_time(value: object) -> datetime:
        if isinstance(value, datetime):
            return NewsFilter._ensure_utc(value)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return NewsFilter._ensure_utc(parsed)
        raise NewsFilterError("news_time must be a datetime or ISO-8601 string")

    @staticmethod
    def _ensure_utc(moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)
