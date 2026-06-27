"""Configuration-related exceptions."""


class ConfigError(Exception):
    """Base exception for configuration failures."""


class ConfigLoadError(ConfigError):
    """Raised when the configuration file cannot be read or parsed."""


class ConfigValidationError(ConfigError):
    """Raised when configuration values fail validation."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        if field:
            super().__init__(f"{field}: {message}")
        else:
            super().__init__(message)
