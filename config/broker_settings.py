"""Broker integration settings loaded from environment and config."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

SUPPORTED_BROKERS = frozenset({"mt5", "deriv", "iqoption"})


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BrokerSettings:
    """Configuration for the multi-broker integration layer."""

    broker_name: str | None = None
    account_id: str | None = None
    live_trading: bool = False
    enable_live_trading: bool = False
    max_risk_per_trade_pct: float = 1.0
    daily_drawdown_limit_pct: float = 5.0
    sandbox: bool = True
    api_key: str | None = None
    api_secret: str | None = None
    base_url: str | None = None

    @property
    def live_allowed(self) -> bool:
        """True only when both live trading switches are enabled."""
        return self.live_trading and self.enable_live_trading

    @classmethod
    def from_env(cls, *, config_raw: dict[str, Any] | None = None) -> BrokerSettings:
        """Build broker settings from environment variables and optional YAML broker section."""
        broker_raw = (config_raw or {}).get("broker", {})
        if not isinstance(broker_raw, dict):
            broker_raw = {}

        provider = os.getenv("BROKER_NAME") or broker_raw.get("provider")
        broker_name = str(provider).strip().lower() if provider else None
        if broker_name in {"null", "none", ""}:
            broker_name = None

        account_id = (
            os.getenv("BROKER_ACCOUNT_ID")
            or os.getenv("account_id")
            or broker_raw.get("account_id")
        )
        if account_id is not None:
            account_id = str(account_id).strip() or None

        risk_raw = (config_raw or {}).get("risk", {})
        max_risk = float(
            broker_raw.get(
                "max_risk_per_trade_pct",
                risk_raw.get("per_trade_pct", 1.0) if isinstance(risk_raw, dict) else 1.0,
            )
        )
        daily_limit = float(
            broker_raw.get(
                "daily_drawdown_limit_pct",
                risk_raw.get("max_daily_drawdown_pct", 5.0)
                if isinstance(risk_raw, dict)
                else 5.0,
            )
        )

        return cls(
            broker_name=broker_name,
            account_id=account_id,
            live_trading=_env_bool("LIVE_TRADING", default=False),
            enable_live_trading=_env_bool("ENABLE_LIVE_TRADING", default=False),
            max_risk_per_trade_pct=max_risk,
            daily_drawdown_limit_pct=daily_limit,
            sandbox=_env_bool("BROKER_SANDBOX", default=bool(broker_raw.get("sandbox", True))),
            api_key=os.getenv("BROKER_API_KEY") or None,
            api_secret=os.getenv("BROKER_API_SECRET") or None,
            base_url=os.getenv("BROKER_BASE_URL") or broker_raw.get("base_url"),
        )
