"""
Account management for multi-profile token storage.

Tracks the active account name used to namespace token files.
"""

import os

_active_account: str = "default"


def set_active_account(account: str) -> None:
    """Set the active account name (called early by CLI / MCP entry-point)."""
    global _active_account
    _active_account = account


def get_active_account() -> str:
    """Return the currently active account name."""
    return _active_account


def get_account_from_env() -> str:
    """Read IOBOX_ACCOUNT from the environment, defaulting to 'default'."""
    return os.environ.get("IOBOX_ACCOUNT", "default").strip() or "default"
