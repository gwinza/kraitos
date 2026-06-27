"""Broker integration layer exceptions."""

from broker.exceptions import BrokerError, LiveTradingDisabledError

__all__ = ["BrokerError", "BrokerConnectionError", "BrokerDataError", "LiveTradingDisabledError", "LiveTradingGuardError"]


class BrokerConnectionError(BrokerError):
    """Raised when a broker connection cannot be established."""


class BrokerDataError(BrokerError):
    """Raised when broker market or account data is unavailable."""


class LiveTradingGuardError(BrokerError):
    """Raised when live-trading confirmation requirements are not met."""
