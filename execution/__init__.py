"""Order routing and trade lifecycle management."""

from execution.models import (
    EntryConfirmation,
    EntryContext,
    EntryDecision,
    ExitContext,
    ExitDecision,
    OpenTrade,
    PaperAccountSnapshot,
    PaperTrade,
)

__all__ = [
    "EntryConfirmation",
    "EntryContext",
    "EntryDecision",
    "EntryEngine",
    "EntryEngineConfig",
    "EntryEngineError",
    "ExitContext",
    "ExitDecision",
    "ExitEngine",
    "ExitEngineConfig",
    "ExitEngineError",
    "OpenTrade",
    "PaperAccountSnapshot",
    "PaperTrade",
    "PaperTrader",
    "PaperTraderConfig",
    "PaperTraderError",
]

_LAZY_EXPORTS = {
    "EntryEngine": ("execution.entry_engine", "EntryEngine"),
    "EntryEngineConfig": ("execution.entry_engine", "EntryEngineConfig"),
    "EntryEngineError": ("execution.entry_engine", "EntryEngineError"),
    "ExitEngine": ("execution.exit_engine", "ExitEngine"),
    "ExitEngineConfig": ("execution.exit_engine", "ExitEngineConfig"),
    "ExitEngineError": ("execution.exit_engine", "ExitEngineError"),
    "PaperTrader": ("execution.paper_trader", "PaperTrader"),
    "PaperTraderConfig": ("execution.paper_trader", "PaperTraderConfig"),
    "PaperTraderError": ("execution.paper_trader", "PaperTraderError"),
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        import importlib

        module = importlib.import_module(module_name)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
