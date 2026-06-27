"""Tests for the configuration loader and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.offline

from config import ConfigLoadError, ConfigValidationError, load_config
from config.validator import validate_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle)
    return path


def test_load_default_config():
    config = load_config(CONFIG_PATH)
    assert config.account.balance == 10000.0
    assert config.risk.per_trade_pct == 1.0
    assert config.risk.max_daily_drawdown_pct == 3.0
    assert config.risk.max_open_trades == 5
    assert config.trading.symbols == ("EURUSD", "GBPUSD", "USDJPY")
    assert config.trading.paper_enabled is True
    assert config.trading.live_enabled is False
    assert config.pipeline.execution_mode == "simulation"
    assert config.trading.news_filter_enabled is True


def test_validate_valid_config(valid_config_data):
    config = validate_config(valid_config_data)
    assert config.trading.symbols == ("EURUSD", "GBPUSD")
    assert len(config.trading.sessions) == 1


@pytest.mark.parametrize(
    ("mutator", "expected_field"),
    [
        (lambda d: d.pop("account"), "account"),
        (lambda d: d["account"].update({"balance": -100}), "account.balance"),
        (lambda d: d["account"].update({"balance": 0}), "account.balance"),
        (lambda d: d["risk"].update({"per_trade_pct": 0}), "risk.per_trade_pct"),
        (lambda d: d["risk"].update({"per_trade_pct": 15}), "risk.per_trade_pct"),
        (lambda d: d["risk"].update({"max_daily_drawdown_pct": 0}), "risk.max_daily_drawdown_pct"),
        (lambda d: d["risk"].update({"max_open_trades": 0}), "risk.max_open_trades"),
        (lambda d: d["risk"].update({"max_open_trades": 1.5}), "risk.max_open_trades"),
        (lambda d: d["trading"].update({"symbols": []}), "trading.symbols"),
        (lambda d: d["trading"].update({"symbols": ["EURO"]}), "trading.symbols[0]"),
        (lambda d: d["trading"].update({"symbols": ["EURUSD", "EURUSD"]}), "trading.symbols[1]"),
        (lambda d: d["trading"].update({"timeframes": ["INVALID"]}), "trading.timeframes[0]"),
        (lambda d: d["trading"].update({"spread_limits": {}}), "trading.spread_limits"),
        (lambda d: d["trading"].update({"spread_limits": {"EURUSD": -1}}), "trading.spread_limits.EURUSD"),
        (lambda d: d["trading"].update({"sessions": []}), "trading.sessions"),
        (
            lambda d: d["trading"]["sessions"][0].update({"start": "25:00"}),
            "trading.sessions[0].start",
        ),
        (
            lambda d: d["trading"]["sessions"][0].update({"timezone": "Not/AZone"}),
            "trading.sessions[0].timezone",
        ),
        (lambda d: d["trading"].update({"live_enabled": True, "paper_enabled": True}), "trading"),
        (lambda d: d["trading"].update({"live_enabled": False, "paper_enabled": False}), "trading"),
        (lambda d: d["trading"].update({"news_filter_enabled": "yes"}), "trading.news_filter_enabled"),
    ],
)
def test_rejects_invalid_values(valid_config_data, mutator, expected_field):
    data = valid_config_data.copy()
    data["account"] = dict(data["account"])
    data["risk"] = dict(data["risk"])
    data["trading"] = dict(data["trading"])
    data["trading"]["sessions"] = [dict(data["trading"]["sessions"][0])]
    mutator(data)

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert exc_info.value.field == expected_field


def test_missing_spread_limit_without_default(valid_config_data):
    data = valid_config_data.copy()
    data["trading"] = dict(data["trading"])
    data["trading"]["spread_limits"] = {"EURUSD": 1.5}

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert exc_info.value.field == "trading.spread_limits"


def test_load_missing_file(tmp_path):
    with pytest.raises(ConfigLoadError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_load_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("account: [\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="invalid YAML"):
        load_config(path)


def test_load_from_temp_file(tmp_path, valid_config_data):
    path = _write_config(tmp_path, valid_config_data)
    config = load_config(path)
    assert config.account.balance == 10000.0
    assert config.trading.news_filter_enabled is True
