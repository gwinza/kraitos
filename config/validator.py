"""Configuration validation helpers."""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.exceptions import ConfigValidationError
from config.settings import (
    AccountSettings,
    ExecutionMode,
    KraitosConfig,
    PipelineSettings,
    RiskSettings,
    TradingSession,
    TradingSettings,
)

SYMBOL_PATTERN = re.compile(r"^[A-Z]{6}$")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
VALID_TIMEFRAMES = frozenset({"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"})
VALID_WEEKDAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})


def _require_section(data: dict[str, Any], section: str) -> dict[str, Any]:
    value = data.get(section)
    if not isinstance(value, dict):
        raise ConfigValidationError(f"missing or invalid '{section}' section", section)
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigValidationError("must be a boolean", field)
    return value


def _require_positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigValidationError("must be a number", field)
    number = float(value)
    if number <= 0:
        raise ConfigValidationError("must be greater than zero", field)
    return number


def _require_percentage(value: Any, field: str, *, max_value: float = 100.0) -> float:
    number = _require_positive_number(value, field)
    if number > max_value:
        raise ConfigValidationError(f"must be at most {max_value}", field)
    return number


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigValidationError("must be a positive integer", field)
    if value <= 0:
        raise ConfigValidationError("must be greater than zero", field)
    return value


def _validate_symbols(symbols: Any) -> tuple[str, ...]:
    field = "trading.symbols"
    if not isinstance(symbols, list) or not symbols:
        raise ConfigValidationError("must be a non-empty list", field)

    validated: list[str] = []
    seen: set[str] = set()
    for index, symbol in enumerate(symbols):
        item_field = f"{field}[{index}]"
        if not isinstance(symbol, str):
            raise ConfigValidationError("must be a string", item_field)
        normalized = symbol.strip().upper()
        if not SYMBOL_PATTERN.match(normalized):
            raise ConfigValidationError(
                "must be a 6-letter uppercase forex symbol (e.g. EURUSD)",
                item_field,
            )
        if normalized in seen:
            raise ConfigValidationError(f"duplicate symbol '{normalized}'", item_field)
        seen.add(normalized)
        validated.append(normalized)
    return tuple(validated)


def _validate_timeframes(timeframes: Any) -> tuple[str, ...]:
    field = "trading.timeframes"
    if not isinstance(timeframes, list) or not timeframes:
        raise ConfigValidationError("must be a non-empty list", field)

    validated: list[str] = []
    seen: set[str] = set()
    for index, timeframe in enumerate(timeframes):
        item_field = f"{field}[{index}]"
        if not isinstance(timeframe, str):
            raise ConfigValidationError("must be a string", item_field)
        normalized = timeframe.strip().upper()
        if normalized not in VALID_TIMEFRAMES:
            allowed = ", ".join(sorted(VALID_TIMEFRAMES))
            raise ConfigValidationError(f"must be one of: {allowed}", item_field)
        if normalized in seen:
            raise ConfigValidationError(f"duplicate timeframe '{normalized}'", item_field)
        seen.add(normalized)
        validated.append(normalized)
    return tuple(validated)


def _validate_spread_limits(spread_limits: Any, symbols: tuple[str, ...]) -> dict[str, float]:
    field = "trading.spread_limits"
    if not isinstance(spread_limits, dict) or not spread_limits:
        raise ConfigValidationError("must be a non-empty mapping", field)

    validated: dict[str, float] = {}
    for key, value in spread_limits.items():
        item_field = f"{field}.{key}"
        if not isinstance(key, str):
            raise ConfigValidationError("keys must be strings", item_field)
        normalized_key = key.strip().upper()
        if normalized_key != "DEFAULT" and not SYMBOL_PATTERN.match(normalized_key):
            raise ConfigValidationError(
                "keys must be 'default' or a 6-letter symbol",
                item_field,
            )
        validated[normalized_key] = _require_positive_number(value, item_field)

    if "DEFAULT" not in validated:
        missing = [symbol for symbol in symbols if symbol not in validated]
        if missing:
            raise ConfigValidationError(
                f"missing spread limit for symbols: {', '.join(missing)} "
                "(provide per-symbol limits or a 'default' entry)",
                field,
            )
    return validated


def _validate_session(raw: Any, index: int) -> TradingSession:
    field = f"trading.sessions[{index}]"
    if not isinstance(raw, dict):
        raise ConfigValidationError("must be an object", field)

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigValidationError("name must be a non-empty string", f"{field}.name")

    start = raw.get("start")
    end = raw.get("end")
    if not isinstance(start, str) or not TIME_PATTERN.match(start):
        raise ConfigValidationError("start must use HH:MM format (24-hour)", f"{field}.start")
    if not isinstance(end, str) or not TIME_PATTERN.match(end):
        raise ConfigValidationError("end must use HH:MM format (24-hour)", f"{field}.end")

    timezone = raw.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone.strip():
        raise ConfigValidationError("timezone must be a non-empty string", f"{field}.timezone")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigValidationError(f"unknown timezone '{timezone}'", f"{field}.timezone") from exc

    days_raw = raw.get("days", ["mon", "tue", "wed", "thu", "fri"])
    if not isinstance(days_raw, list) or not days_raw:
        raise ConfigValidationError("days must be a non-empty list", f"{field}.days")

    days: list[str] = []
    for day_index, day in enumerate(days_raw):
        day_field = f"{field}.days[{day_index}]"
        if not isinstance(day, str):
            raise ConfigValidationError("must be a string", day_field)
        normalized_day = day.strip().lower()[:3]
        if normalized_day not in VALID_WEEKDAYS:
            allowed = ", ".join(sorted(VALID_WEEKDAYS))
            raise ConfigValidationError(f"must be one of: {allowed}", day_field)
        if normalized_day not in days:
            days.append(normalized_day)

    return TradingSession(
        name=name.strip(),
        start=start,
        end=end,
        timezone=timezone,
        days=tuple(days),
    )


def _validate_sessions(sessions: Any) -> tuple[TradingSession, ...]:
    field = "trading.sessions"
    if not isinstance(sessions, list) or not sessions:
        raise ConfigValidationError("must be a non-empty list", field)
    return tuple(_validate_session(session, index) for index, session in enumerate(sessions))


def validate_config(data: dict[str, Any]) -> KraitosConfig:
    """Validate raw YAML data and return a typed configuration object."""
    if not isinstance(data, dict):
        raise ConfigValidationError("root config must be a mapping")

    account_raw = _require_section(data, "account")
    risk_raw = _require_section(data, "risk")
    trading_raw = _require_section(data, "trading")

    account = AccountSettings(
        balance=_require_positive_number(account_raw.get("balance"), "account.balance"),
    )

    risk = RiskSettings(
        per_trade_pct=_require_percentage(
            risk_raw.get("per_trade_pct"),
            "risk.per_trade_pct",
            max_value=10.0,
        ),
        max_daily_drawdown_pct=_require_percentage(
            risk_raw.get("max_daily_drawdown_pct"),
            "risk.max_daily_drawdown_pct",
            max_value=50.0,
        ),
        max_open_trades=_require_positive_int(
            risk_raw.get("max_open_trades"),
            "risk.max_open_trades",
        ),
        max_risk_per_symbol_pct=_require_percentage(
            risk_raw.get("max_risk_per_symbol_pct", 2.0),
            "risk.max_risk_per_symbol_pct",
            max_value=20.0,
        ),
        max_correlated_exposure_pct=_require_percentage(
            risk_raw.get("max_correlated_exposure_pct", 3.0),
            "risk.max_correlated_exposure_pct",
            max_value=30.0,
        ),
    )

    symbols = _validate_symbols(trading_raw.get("symbols"))
    timeframes = _validate_timeframes(trading_raw.get("timeframes"))
    spread_limits = _validate_spread_limits(trading_raw.get("spread_limits"), symbols)
    sessions = _validate_sessions(trading_raw.get("sessions"))

    live_enabled = _require_bool(trading_raw.get("live_enabled"), "trading.live_enabled")
    paper_enabled = _require_bool(trading_raw.get("paper_enabled"), "trading.paper_enabled")
    news_filter_enabled = _require_bool(
        trading_raw.get("news_filter_enabled"),
        "trading.news_filter_enabled",
    )

    if live_enabled and paper_enabled:
        raise ConfigValidationError(
            "live_enabled and paper_enabled cannot both be true",
            "trading",
        )
    if not live_enabled and not paper_enabled:
        raise ConfigValidationError(
            "at least one of live_enabled or paper_enabled must be true",
            "trading",
        )

    trading = TradingSettings(
        symbols=symbols,
        timeframes=timeframes,
        spread_limits=spread_limits,
        sessions=sessions,
        live_enabled=live_enabled,
        paper_enabled=paper_enabled,
        news_filter_enabled=news_filter_enabled,
    )

    pipeline_raw = data.get("pipeline", {})
    if pipeline_raw is not None and not isinstance(pipeline_raw, dict):
        raise ConfigValidationError("must be a mapping", "pipeline")

    execution_mode_raw = (
        str(pipeline_raw.get("execution_mode", "simulation")).strip().lower()
        if isinstance(pipeline_raw, dict)
        else "simulation"
    )
    if execution_mode_raw not in {"simulation", "live"}:
        raise ConfigValidationError(
            "must be 'simulation' or 'live'",
            "pipeline.execution_mode",
        )
    execution_mode: ExecutionMode = execution_mode_raw  # type: ignore[assignment]

    execute_trades = False
    output_json = False
    structure_timeframe = "H1"
    precision_timeframes: tuple[str, ...] = ("M1", "M5")
    if isinstance(pipeline_raw, dict):
        if "execute_trades" in pipeline_raw:
            execute_trades = _require_bool(
                pipeline_raw.get("execute_trades"),
                "pipeline.execute_trades",
            )
        if "output_json" in pipeline_raw:
            output_json = _require_bool(
                pipeline_raw.get("output_json"),
                "pipeline.output_json",
            )
        if "structure_timeframe" in pipeline_raw:
            structure_timeframe = str(pipeline_raw.get("structure_timeframe")).strip().upper()
        if "precision_timeframes" in pipeline_raw:
            precision_timeframes = _validate_timeframes(
                pipeline_raw.get("precision_timeframes")
            )

    pipeline = PipelineSettings(
        execution_mode=execution_mode,
        execute_trades=execute_trades,
        structure_timeframe=structure_timeframe,
        precision_timeframes=precision_timeframes,
        output_json=output_json,
    )

    return KraitosConfig(
        account=account,
        risk=risk,
        trading=trading,
        pipeline=pipeline,
        raw=data,
    )
