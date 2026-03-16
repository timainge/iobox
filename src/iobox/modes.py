"""
Access mode definitions for iobox.

Defines readonly, standard, and dangerous modes that control which Gmail API
scopes are requested and which CLI commands / MCP tools are available.

Also provides scope constants and aggregation helpers for Google Calendar and
Drive, used by GoogleCalendarProvider and GoogleDriveProvider (tasks 005/006).
"""

import os
from enum import Enum


class AccessMode(str, Enum):
    readonly = "readonly"
    standard = "standard"
    dangerous = "dangerous"


SCOPES_BY_MODE: dict[AccessMode, list[str]] = {
    AccessMode.readonly: [
        "https://www.googleapis.com/auth/gmail.readonly",
    ],
    AccessMode.standard: [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
    ],
    AccessMode.dangerous: [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
    ],
}

# gmail.modify is a superset of gmail.readonly, so a token with modify
# scope is acceptable when running in readonly mode.
SCOPE_IMPLIES: dict[str, set[str]] = {
    "https://www.googleapis.com/auth/gmail.modify": {
        "https://www.googleapis.com/auth/gmail.readonly",
    },
}

# ── Per-service scope constants ────────────────────────────────────────────────

GMAIL_SCOPES_READONLY: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_SCOPES_STANDARD: list[str] = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]

CALENDAR_SCOPES_READONLY: list[str] = ["https://www.googleapis.com/auth/calendar.readonly"]
CALENDAR_SCOPES_STANDARD: list[str] = ["https://www.googleapis.com/auth/calendar"]

DRIVE_SCOPES_READONLY: list[str] = ["https://www.googleapis.com/auth/drive.readonly"]
DRIVE_SCOPES_STANDARD: list[str] = ["https://www.googleapis.com/auth/drive"]


def get_google_scopes(services: list[str], mode: str) -> list[str]:
    """Build combined Google OAuth scope list for the given services and mode.

    Args:
        services: Subset of ``["messages", "calendar", "drive"]``.
        mode: ``"readonly"`` or ``"standard"`` (dangerous treated as standard).

    Returns:
        Deduplicated list of OAuth scope strings suitable for passing to
        ``InstalledAppFlow`` or ``GoogleAuth``.
    """
    scopes: list[str] = []
    if "messages" in services:
        if mode == "readonly":
            scopes.extend(GMAIL_SCOPES_READONLY)
        else:
            scopes.extend(GMAIL_SCOPES_STANDARD)
    if "calendar" in services:
        if mode == "readonly":
            scopes.extend(CALENDAR_SCOPES_READONLY)
        else:
            scopes.extend(CALENDAR_SCOPES_STANDARD)
    if "drive" in services:
        if mode == "readonly":
            scopes.extend(DRIVE_SCOPES_READONLY)
        else:
            scopes.extend(DRIVE_SCOPES_STANDARD)
    # Preserve order, remove exact duplicates.
    seen: set[str] = set()
    result: list[str] = []
    for s in scopes:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _tier_for_mode(mode: str) -> str:
    """Return the token-file tier name for a mode string.

    Maps ``"readonly"`` → ``"readonly"`` and everything else →
    ``"standard"``.  Dangerous mode reuses standard-tier tokens.
    """
    return "readonly" if mode == "readonly" else "standard"


# CLI command names allowed per mode (typer subcommand names).
# "space" is always allowed — space management doesn't require an active mode.
_READONLY_CLI = {
    "search",
    "save",
    "auth-status",
    "version",
    "draft-list",
    "space",
    "events",
    "files",
    "workspace",
}
_STANDARD_CLI = _READONLY_CLI | {"draft-create", "draft-send", "draft-delete", "label"}
_DANGEROUS_CLI = _STANDARD_CLI | {"send", "forward", "trash"}

CLI_COMMANDS_BY_MODE: dict[AccessMode, set[str]] = {
    AccessMode.readonly: _READONLY_CLI,
    AccessMode.standard: _STANDARD_CLI,
    AccessMode.dangerous: _DANGEROUS_CLI,
}

# MCP tool function names allowed per mode.
_READONLY_MCP = {
    "search_gmail",
    "get_email",
    "save_email",
    "save_thread",
    "save_emails_by_query",
    "list_gmail_drafts",
    "check_auth",
    # Workspace tools
    "search_workspace",
    "list_events",
    "get_event",
    "list_files",
    "get_file",
    "get_file_content",
    # Semantic search
    "semantic_search_workspace",
}
_STANDARD_MCP = _READONLY_MCP | {
    "create_gmail_draft",
    "send_gmail_draft",
    "delete_gmail_draft",
    "modify_labels",
    "batch_modify_gmail_labels",
}
_DANGEROUS_MCP = _STANDARD_MCP | {
    "send_email",
    "forward_gmail",
    "batch_forward_gmail",
    "trash_gmail",
    "untrash_gmail",
    "batch_trash_gmail",
}

MCP_TOOLS_BY_MODE: dict[AccessMode, set[str]] = {
    AccessMode.readonly: _READONLY_MCP,
    AccessMode.standard: _STANDARD_MCP,
    AccessMode.dangerous: _DANGEROUS_MCP,
}


def get_mode_from_env() -> AccessMode:
    """Read IOBOX_MODE from the environment, defaulting to 'standard'."""
    raw = os.environ.get("IOBOX_MODE", "standard").lower().strip()
    try:
        return AccessMode(raw)
    except ValueError:
        valid = ", ".join(m.value for m in AccessMode)
        raise ValueError(f"Invalid IOBOX_MODE={raw!r}. Must be one of: {valid}") from None
