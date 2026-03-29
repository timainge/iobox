"""
iobox provider package.

Exports the EmailProvider ABC, EmailQuery, EmailData, and the
get_provider() factory. Provider implementations are loaded lazily
so that optional dependencies (e.g. O365) are never imported unless
the corresponding provider is actually requested.

Also exports the workspace resource type hierarchy (Resource, Email, Event, File)
and the CalendarProvider / FileProvider ABCs added in the workspace expansion.
"""

import importlib
from typing import Any

from iobox.providers.base import (
    AttachmentInfo,
    AttendeeInfo,
    CalendarProvider,
    Email,
    EmailData,
    EmailMetadata,
    EmailProvider,
    EmailQuery,
    Event,
    EventQuery,
    File,
    FileProvider,
    FileQuery,
    Resource,
    ResourceQuery,
)

__all__ = [
    # Original email types — unchanged
    "AttachmentInfo",
    "EmailData",
    "EmailMetadata",
    "EmailProvider",
    "EmailQuery",
    "get_provider",
    # Workspace resource hierarchy
    "Resource",
    "Email",
    "Event",
    "File",
    "AttendeeInfo",
    # Query types
    "ResourceQuery",
    "EventQuery",
    "FileQuery",
    # Provider ABCs
    "CalendarProvider",
    "FileProvider",
]

_PROVIDERS: dict[str, str] = {
    "gmail": "iobox.providers.google.email.GmailProvider",
    "outlook": "iobox.providers.o365.email.OutlookProvider",
    "google_calendar": "iobox.providers.google.calendar.GoogleCalendarProvider",
    "google_drive": "iobox.providers.google.files.GoogleDriveProvider",
    "outlook_calendar": "iobox.providers.o365.calendar.OutlookCalendarProvider",
    "onedrive": "iobox.providers.o365.files.OneDriveProvider",
}

_INSTALL_HINTS: dict[str, str] = {
    "outlook": "pip install 'iobox[outlook]'  # or: pip install O365>=2.1.8",
}


def get_provider(name: str = "gmail", **kwargs: Any) -> EmailProvider:
    """Instantiate an email provider by name.

    Uses lazy importlib import so Outlook dependencies are never
    required for Gmail-only users.

    Args:
        name: Provider name — 'gmail' or 'outlook'.
        **kwargs: Passed through to the provider constructor.

    Raises:
        ValueError: If the provider name is not recognised.
        ImportError: If the provider's optional dependency is not installed.
    """
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {', '.join(_PROVIDERS)}")

    module_path, class_name = _PROVIDERS[name].rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        hint = _INSTALL_HINTS.get(name)
        if hint:
            raise ImportError(
                f"Provider '{name}' requires additional dependencies. Install them with: {hint}"
            ) from exc
        raise

    cls = getattr(module, class_name)
    instance: EmailProvider = cls(**kwargs)
    return instance
