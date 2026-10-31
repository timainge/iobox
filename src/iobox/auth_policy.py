"""
Process-wide policy for interactive (browser) OAuth flows.

The CLI may open a browser to authorise an account. Long-running servers such
as the MCP server must not: a consent flow there blocks the tool call, and the
browser hand-off doesn't work from a spawned subprocess. Servers call
``set_interactive_auth(False)`` at start-up; auth code calls
``require_interactive_auth()`` before starting a flow.
"""

from __future__ import annotations

_interactive_allowed = True


class InteractiveAuthRequired(RuntimeError):
    """Raised when an account needs a browser sign-in but interactive auth is disabled."""


def set_interactive_auth(allowed: bool) -> None:
    """Allow or forbid interactive OAuth flows for this process."""
    global _interactive_allowed
    _interactive_allowed = allowed


def interactive_auth_allowed() -> bool:
    """Whether this process may start an interactive OAuth flow."""
    return _interactive_allowed


def require_interactive_auth(account: str) -> None:
    """Raise :class:`InteractiveAuthRequired` if interactive auth is disabled."""
    if not _interactive_allowed:
        raise InteractiveAuthRequired(
            f"Account {account!r} needs to sign in, which can't happen from this process. "
            "Run `iobox space login` in a terminal, then retry."
        )
