"""
MarketObservation: Raw facts from the market.

This class represents a single observation of market activity.
It contains only facts: price, volume, time, events.

No opinions. No signals. No trading logic.

This is what the market did. Not what Kraitos thinks about it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MarketObservation:
    """
    A single factual observation of market activity.

    This class records what happened in the market during a specific timeframe.
    It contains only observable facts: prices, volume, time, and events.

    This is NOT a trading signal. Councils will interpret these facts.
    The Shared World Model will assemble interpretations into understanding.

    Attributes
    ----------
    symbol : str
        The market instrument (e.g., "EURUSD", "BTC/USD").
    timeframe : str
        The time period of this candle/bar (e.g., "1H", "4H", "1D").
    timestamp : datetime
        When this observation period ended.
    open : float
        Opening price for this period.
    high : float
        Highest price during this period.
    low : float
        Lowest price during this period.
    close : float
        Closing price for this period.
    volume : float
        Total volume traded during this period.
    spread : float
        Average spread (ask - bid) during this period.
    session : str
        Market session (e.g., "European", "Asian", "US").
    bid : Optional[float]
        Current bid price at observation time.
    ask : Optional[float]
        Current ask price at observation time.
    tick_count : Optional[int]
        Number of ticks/trades during this period.
    news_events : list[str]
        News or announcements during this period.
    macro_events : list[str]
        Macro events (economic data, central bank decisions, etc.).
    raw_context : dict
        Arbitrary additional context for later analysis.
    """

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float = 0.0
    session: str = "Unknown"
    bid: Optional[float] = None
    ask: Optional[float] = None
    tick_count: Optional[int] = None
    news_events: list[str] = field(default_factory=list)
    macro_events: list[str] = field(default_factory=list)
    raw_context: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Validate observation on creation.

        Raises
        ------
        ValueError
            If symbol or timeframe are empty.
        ValueError
            If high < low or high/low not contain open/close.
        ValueError
            If volume is negative.
        """
        # Validate symbol and timeframe
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty.")

        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty.")

        # Validate high/low logic
        if self.high < self.low:
            raise ValueError(
                f"high ({self.high}) cannot be less than low ({self.low})."
            )

        # Validate that open/close are within high/low range
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"open ({self.open}) must be between low ({self.low}) "
                f"and high ({self.high})."
            )

        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"close ({self.close}) must be between low ({self.low}) "
                f"and high ({self.high})."
            )

        # Validate volume is non-negative
        if self.volume < 0:
            raise ValueError(f"volume cannot be negative, got {self.volume}.")

    def mid_price(self) -> float:
        """
        Calculate the midpoint price at the end of this observation.

        If bid/ask are available, uses them. Otherwise uses close price.

        Returns
        -------
        float
            The mid price.
        """
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0

        return self.close

    def range(self) -> float:
        """
        Calculate the total price range for this observation.

        Returns
        -------
        float
            high - low
        """
        return self.high - self.low

    def body(self) -> float:
        """
        Calculate the size of the candle body (open to close).

        Returns
        -------
        float
            abs(close - open)
        """
        return abs(self.close - self.open)

    def upper_wick(self) -> float:
        """
        Calculate the size of the upper wick (high to body top).

        Returns
        -------
        float
            Distance from high to the maximum of open/close.
        """
        body_top = max(self.open, self.close)
        return self.high - body_top

    def lower_wick(self) -> float:
        """
        Calculate the size of the lower wick (low to body bottom).

        Returns
        -------
        float
            Distance from low to the minimum of open/close.
        """
        body_bottom = min(self.open, self.close)
        return body_bottom - self.low

    def direction(self) -> int:
        """
        Return the direction of this candle.

        Returns
        -------
        int
            1 if close > open (bullish)
            -1 if close < open (bearish)
            0 if close == open (doji/neutral)
        """
        if self.close > self.open:
            return 1
        elif self.close < self.open:
            return -1
        else:
            return 0

    def is_bullish(self) -> bool:
        """
        Check if this observation is bullish (close > open).

        Returns
        -------
        bool
            True if close > open.
        """
        return self.close > self.open

    def is_bearish(self) -> bool:
        """
        Check if this observation is bearish (close < open).

        Returns
        -------
        bool
            True if close < open.
        """
        return self.close < self.open

    def __str__(self) -> str:
        """Return a human-readable representation of this observation."""
        direction_symbol = "📈" if self.is_bullish() else "📉" if self.is_bearish() else "➡️"
        return (
            f"MarketObservation({self.symbol} {self.timeframe} {direction_symbol} "
            f"O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume})"
        )
