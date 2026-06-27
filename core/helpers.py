"""Shared helpers for the orchestration pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config.settings import KraitosConfig, TradingSession
from risk.risk_manager import PIP_SIZE_BY_SYMBOL
from strategies.models import HarvestDecision, MarketContext, MicroScalpSignal

REQUIRED_TIMEFRAMES: tuple[str, ...] = ("M1", "M5", "M15", "H1", "H4", "H8")
SUPPORTED_ORCHESTRATOR_TIMEFRAMES = frozenset(REQUIRED_TIMEFRAMES)


def resolve_timeframes(config: KraitosConfig) -> tuple[str, ...]:
    """Return the candle timeframes required for a full orchestration cycle."""
    requested = {tf.strip().upper() for tf in config.trading.timeframes}
    merged = set(REQUIRED_TIMEFRAMES) | {
        tf for tf in requested if tf in SUPPORTED_ORCHESTRATOR_TIMEFRAMES
    }
    return tuple(sorted(merged))


def resolve_spread_limit(config: KraitosConfig, symbol: str) -> float:
    """Resolve the per-symbol spread limit in pips."""
    limits = config.trading.spread_limits
    symbol_key = symbol.strip().upper()
    if symbol_key in limits:
        return float(limits[symbol_key])
    if "default" in limits:
        return float(limits["default"])
    return 2.0


def pip_size_for_symbol(symbol: str) -> float:
    """Return pip size for a symbol."""
    return PIP_SIZE_BY_SYMBOL.get(symbol.strip().upper(), 0.0001)


def pip_value_per_lot(
    symbol: str,
    entry_price: float,
    *,
    contract_size: float = 100_000.0,
) -> float:
    """Return pip value in account currency for one standard lot."""
    pip_size = pip_size_for_symbol(symbol)
    value = contract_size * pip_size
    symbol_key = symbol.strip().upper()
    if symbol_key.endswith("JPY") and entry_price > 0:
        return value / entry_price
    return value


def trade_pnl(
    *,
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    contract_size: float = 100_000.0,
) -> float:
    """Calculate closed trade P/L using symbol-aware pip sizing."""
    pip_size = pip_size_for_symbol(symbol)
    if side == "buy":
        pips = (exit_price - entry_price) / pip_size
    else:
        pips = (entry_price - exit_price) / pip_size
    pip_value = pip_value_per_lot(symbol, entry_price, contract_size=contract_size)
    return pips * pip_value * lot_size


def spread_price_to_pips(spread_price: float, symbol: str) -> float:
    """Convert a price spread to pips."""
    pip_size = pip_size_for_symbol(symbol)
    if pip_size <= 0:
        return spread_price
    return spread_price / pip_size


def is_in_trading_session(
    config: KraitosConfig,
    moment: datetime | None = None,
) -> bool:
    """Return True when the current time falls inside a configured session."""
    now = moment or datetime.now(timezone.utc)
    sessions = config.trading.sessions
    if not sessions:
        return True

    for session in sessions:
        if _moment_in_session(now, session):
            return True
    return False


def _moment_in_session(moment: datetime, session: TradingSession) -> bool:
    weekday = moment.astimezone(timezone.utc).strftime("%a").lower()[:3]
    if weekday not in {day.lower()[:3] for day in session.days}:
        return False

    try:
        tz = ZoneInfo(session.timezone)
    except Exception:
        tz = timezone.utc

    local = moment.astimezone(tz)
    start_hour, start_minute = _parse_hhmm(session.start)
    end_hour, end_minute = _parse_hhmm(session.end)
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    current_minutes = local.hour * 60 + local.minute

    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes or current_minutes <= end_minutes


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text), int(minute_text)


def compute_stop_loss(
    *,
    side: str,
    entry_price: float,
    structure: MarketContext,
    pip_size: float,
    buffer_pips: float = 5.0,
    atr: float | None = None,
    symbol: str = "",
) -> float:
    """Derive a protective stop beyond structure (delegates to stop placement)."""
    from risk.stop_placement import StopPlacementConfig, place_structural_stop

    effective_atr = atr if atr is not None and atr > 0 else pip_size * 15.0
    sym = symbol or getattr(structure, "symbol", "EURUSD")
    cfg = StopPlacementConfig(structure_buffer_pips=buffer_pips)
    return place_structural_stop(
        side=side,  # type: ignore[arg-type]
        entry_price=entry_price,
        structure=structure,
        symbol=sym,
        atr=effective_atr,
        config=cfg,
    )


def _nearest_swing_price(
    swings: tuple[object, ...] | list[object],
    entry_price: float,
    *,
    side: str,
) -> float:
    """Return the most recent swing on the protective side of entry."""
    if not swings:
        raise ValueError("swings must not be empty")

    if side == "below":
        candidates = [point.price for point in swings if point.price < entry_price]
    else:
        candidates = [point.price for point in swings if point.price > entry_price]

    if candidates:
        return candidates[-1]
    return swings[-1].price


def compute_take_profit(
    *,
    side: str,
    entry_price: float,
    pip_size: float,
    harvest: HarvestDecision | None,
    micro_scalp: MicroScalpSignal | None,
    target_multiplier: float = 1.0,
) -> float | None:
    """Derive a take-profit level from harvest or micro-scalp targets."""
    target_pips = 0.0
    if harvest is not None and harvest.allowed and harvest.target_pips > 0:
        target_pips = harvest.target_pips
    elif micro_scalp is not None and micro_scalp.target_pips > 0:
        target_pips = micro_scalp.target_pips

    if target_pips <= 0:
        return None

    target_pips *= max(1.0, target_multiplier)
    distance = target_pips * pip_size
    if side == "buy":
        return entry_price + distance
    return entry_price - distance
