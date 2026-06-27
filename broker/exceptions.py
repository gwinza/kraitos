"""Broker-related exceptions."""


class BrokerError(Exception):
    """Base exception for broker operations."""


class MT5ConnectionError(BrokerError):
    """Raised when MetaTrader 5 cannot be initialized or connected."""


class MT5DataError(BrokerError):
    """Raised when market or account data cannot be retrieved."""


class LiveTradingDisabledError(BrokerError):
    """Raised when a live trade is attempted while live trading is disabled."""


class MT5OrderError(BrokerError):
    """Raised when MetaTrader 5 rejects or fails an order request."""
