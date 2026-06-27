"""Step 2: Connect to MetaTrader 5."""

from __future__ import annotations

from loguru import logger

from broker.exceptions import MT5ConnectionError
from core.runtime import KraitosRuntime
from logs.event_logger import KraitosEventLogger


def connect_mt5(runtime: KraitosRuntime, *, trace_id: str) -> None:
    """Establish a connection to the MetaTrader 5 terminal."""
    event_logger: KraitosEventLogger = runtime.event_logger
    try:
        runtime.connector.connect()
        account = runtime.connector.get_account_info()
        runtime.broker_balance = account.balance
        logger.info(
            f"Connected to MT5 account {account.login} "
            f"({account.server}) balance={account.balance:,.2f}"
        )
        event_logger.system_event(
            f"Connected to MT5 account {account.login}",
            event_type="mt5_connected",
            trace_id=trace_id,
            data={
                "login": account.login,
                "server": account.server,
                "balance": account.balance,
                "equity": account.equity,
            },
        )
    except MT5ConnectionError as exc:
        event_logger.error("Failed to connect to MetaTrader 5", trace_id=trace_id, exc=exc)
        raise
