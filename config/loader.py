"""YAML configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config.exceptions import ConfigLoadError, ConfigValidationError
from config.settings import KraitosConfig
from config.validator import validate_config

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    """Read and parse a YAML file."""
    if not path.exists():
        raise ConfigLoadError(f"configuration file not found: {path}")

    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigLoadError(f"unable to read {path}: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigLoadError(f"configuration root must be a mapping: {path}")
    return data


def load_config(path: Path | str | None = None) -> KraitosConfig:
    """
    Load, parse, and validate Kraitos configuration.

    Args:
        path: Optional path to config.yaml. Defaults to config/config.yaml.

    Returns:
        Validated KraitosConfig instance.

    Raises:
        ConfigLoadError: File missing, unreadable, or malformed YAML.
        ConfigValidationError: Values fail validation rules.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH

    try:
        raw = load_yaml(config_path)
        return validate_config(raw)
    except ConfigValidationError:
        raise
    except ConfigLoadError:
        raise
    except Exception as exc:
        raise ConfigLoadError(f"unexpected error loading {config_path}: {exc}") from exc
