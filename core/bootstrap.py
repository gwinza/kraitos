"""Application bootstrap helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from config import ConfigError, load_config
from config.settings import KraitosConfig
from logs import init_event_logger
from logs.event_logger import KraitosEventLogger


def setup_logging(log_dir: Path) -> None:
    """Configure application logging."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kraitos.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>"
        ),
    )
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} - {message}",
    )


def load_application_config(project_root: Path) -> KraitosConfig:
    """Load and validate Kraitos configuration."""
    return load_config(project_root / "config" / "config.yaml")


def initialize_runtime(
    project_root: Path,
) -> tuple[KraitosConfig, KraitosEventLogger, Path]:
    """Load environment, logging, config, and structured event logger."""
    load_dotenv(project_root / ".env")
    log_dir = project_root / "logs"
    setup_logging(log_dir)
    event_logger = init_event_logger(log_dir)

    try:
        config = load_application_config(project_root)
    except ConfigError as exc:
        logger.error(f"Configuration error: {exc}")
        event_logger.error(f"Configuration error: {exc}", exc=exc)
        raise

    return config, event_logger, log_dir
