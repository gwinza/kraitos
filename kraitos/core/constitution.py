"""
Kraitos Constitution: Immutable Laws and Constraints

This module defines the foundational principles that govern Kraitos behavior.
All modules must operate within these constraints. No exceptions.

Core Principle:
    The market is a living conversation. Kraitos exists to understand it,
    not to predict it or command it.
"""


class ConstitutionViolation(Exception):
    """Raised when an action violates Kraitos constitutional law."""

    pass


KRAITOS_LAWS: tuple[str, ...] = (
    "The market is a living conversation, not a machine.",
    "Price is evidence, not truth.",
    "Indicators are summaries of the past, not predictors of the future.",
    "Liquidity is where decisions become transactions.",
    "Every participant has objectives.",
    "Every trade is a hypothesis.",
    "Understanding comes before action.",
    "Capital preservation comes before profit.",
    "The market owes Kraitos nothing.",
    "Reality is the final teacher.",
)

# Actions forbidden for councils and modules
FORBIDDEN_ACTIONS: tuple[str, ...] = (
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "ENTER",
    "EXIT",
    "VETO",
    "APPROVE",
    "REJECT",
    "BLOCK",
)


def get_laws() -> tuple[str, ...]:
    """
    Retrieve the immutable laws governing Kraitos.

    Returns
    -------
    tuple[str, ...]
        The complete set of Kraitos constitutional laws.
    """
    return KRAITOS_LAWS


def validate_action(action: str) -> bool:
    """
    Validate that an action does not violate the constitution.

    Councils may not output trading signals or gatekeeping decisions.
    They may only contribute evidence to the Shared World Model.

    Parameters
    ----------
    action : str
        The action to validate (case-insensitive).

    Returns
    -------
    bool
        True if the action is permitted.

    Raises
    ------
    ConstitutionViolation
        If the action is in the forbidden list.
    """
    normalized_action = action.strip().upper()

    if normalized_action in FORBIDDEN_ACTIONS:
        raise ConstitutionViolation(
            f"Action '{action}' violates the constitution. "
            f"Forbidden actions: {', '.join(FORBIDDEN_ACTIONS)}. "
            f"Councils may only contribute evidence, not trading decisions."
        )

    return True
