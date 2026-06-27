"""Factory for constructing broker adapters."""

from __future__ import annotations

from typing import Any

from brokers.base_broker import BaseBroker
from brokers.deriv_broker import DerivBroker
from brokers.exceptions import BrokerConnectionError
from brokers.iqoption_broker import IQOptionBroker
from brokers.mt5_broker import MT5Broker
from config.broker_settings import SUPPORTED_BROKERS, BrokerSettings

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from broker.mt5_connector import MT5Connector
    from paper_trading.paper_executor import PaperExecutor


class BrokerFactory:
    """Create broker adapters by name with shared safety settings."""

    _registry: dict[str, type[BaseBroker]] = {
        "mt5": MT5Broker,
        "deriv": DerivBroker,
        "iqoption": IQOptionBroker,
    }

    @classmethod
    def supported_brokers(cls) -> frozenset[str]:
        return SUPPORTED_BROKERS

    @classmethod
    def create(
        cls,
        broker_name: str | None = None,
        *,
        settings: BrokerSettings | None = None,
        config_raw: dict[str, Any] | None = None,
        paper_executor: PaperExecutor | None = None,
        connector: MT5Connector | None = None,
        symbols: tuple[str, ...] | None = None,
    ) -> BaseBroker:
        """
        Build a broker adapter.

        Args:
            broker_name: Broker identifier (mt5, deriv, iqoption).
            settings: Pre-built broker settings; loaded from env if omitted.
            config_raw: Optional Kraitos config dict for settings resolution.
            paper_executor: Optional executor for paper redirection.
            connector: Optional MT5 connector injection (testing).
            symbols: Optional symbol list override.
        """
        resolved_settings = settings or BrokerSettings.from_env(config_raw=config_raw)
        name = (broker_name or resolved_settings.broker_name or "mt5").strip().lower()

        if name not in cls._registry:
            supported = ", ".join(sorted(cls._registry))
            raise BrokerConnectionError(
                f"Unsupported broker '{name}'. Supported brokers: {supported}"
            )

        if name == "mt5":
            return MT5Broker(
                resolved_settings,
                connector=connector,
                symbols=symbols,
                paper_executor=paper_executor,
            )
        if name == "deriv":
            return DerivBroker(
                resolved_settings,
                symbols=symbols,
                paper_executor=paper_executor,
            )
        return IQOptionBroker(
            resolved_settings,
            symbols=symbols,
            paper_executor=paper_executor,
        )

    @classmethod
    def from_env(
        cls,
        *,
        config_raw: dict[str, Any] | None = None,
        paper_executor: PaperExecutor | None = None,
    ) -> BaseBroker:
        """Create a broker using environment-driven settings."""
        settings = BrokerSettings.from_env(config_raw=config_raw)
        return cls.create(
            settings.broker_name,
            settings=settings,
            paper_executor=paper_executor,
        )
