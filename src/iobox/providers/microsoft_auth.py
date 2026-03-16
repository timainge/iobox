"""
MicrosoftAuth — shared Microsoft 365 authentication for all O365 services.

One ``MicrosoftAuth`` instance per (account, scope_set) handles Outlook,
Calendar, and OneDrive with a single OAuth token file, mirroring the
``GoogleAuth`` pattern from ``google_auth.py``.

Token path: ``{credentials_dir}/tokens/{account}/microsoft_token.txt``

This replaces the old hardcoded ``tokens/outlook/o365_token.txt`` path and
fixes the multi-account namespacing bug.  Existing tokens at the old path are
automatically migrated on first use.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from O365 import Account, FileSystemTokenBackend

    HAS_O365 = True
except ImportError:
    Account = None
    FileSystemTokenBackend = None
    HAS_O365 = False

_TOKEN_FILENAME = "microsoft_token.txt"
_LEGACY_TOKEN_RELPATH = os.path.join("tokens", "outlook", "o365_token.txt")


def get_microsoft_scopes(services: list[str], mode: str) -> list[str]:
    """Build combined Microsoft scope list for given services and mode.

    Args:
        services: Subset of ``["messages", "calendar", "drive"]``.
        mode: ``"readonly"`` or ``"standard"`` (dangerous treated as standard).

    Returns:
        Deduplicated list of Microsoft Graph scope strings.
    """
    scopes: list[str] = ["basic"]
    if "messages" in services:
        if mode == "readonly":
            scopes.append("Mail.Read")
        else:
            scopes.extend(["Mail.ReadWrite", "Mail.Send"])
    if "calendar" in services:
        if mode == "readonly":
            scopes.append("Calendars.Read")
        else:
            scopes.append("Calendars.ReadWrite")
    if "drive" in services:
        if mode == "readonly":
            scopes.append("Files.Read.All")
        else:
            scopes.append("Files.ReadWrite.All")
    # Preserve order, remove duplicates
    seen: set[str] = set()
    result: list[str] = []
    for s in scopes:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


class MicrosoftAuth:
    """Shared auth for all Microsoft 365 services (Outlook, Calendar, OneDrive).

    One instance per (account, scope_set) handles a single OAuth token file.
    Auth is lazy: the OAuth flow runs on the first call to ``get_account()``.

    Args:
        account: Account identifier used for token namespacing (e.g. an email
            address or ``"default"``).
        scopes: Microsoft Graph scopes to request (e.g. ``["Mail.Read"]``).
        credentials_dir: Base directory for credential files.  Defaults to
            ``~/.iobox``.
        client_id: Azure app client ID.  Reads ``OUTLOOK_CLIENT_ID`` if omitted.
        tenant_id: Azure tenant ID.  Reads ``OUTLOOK_TENANT_ID`` or ``"common"``.
    """

    def __init__(
        self,
        account: str = "default",
        scopes: list[str] | None = None,
        credentials_dir: str | None = None,
        client_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        if not HAS_O365:
            raise ImportError(
                "O365 package required for Outlook support. "
                "Install with: pip install 'iobox[outlook]'"
            )
        self.account = account
        self.scopes: list[str] = scopes or ["basic", "Mail.Read"]
        self._credentials_dir = Path(credentials_dir or Path.home() / ".iobox")
        self.client_id: str = client_id or os.environ.get("OUTLOOK_CLIENT_ID", "")
        self.tenant_id: str = tenant_id or os.environ.get("OUTLOOK_TENANT_ID", "common")
        self._o365_account: Any | None = None

    # ── Path helpers ───────────────────────────────────────────────────────────

    @property
    def token_dir(self) -> Path:
        """Account-namespaced token directory (created on demand)."""
        d = self._credentials_dir / "tokens" / self.account
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def token_file(self) -> Path:
        """Full path to the token file."""
        return self.token_dir / _TOKEN_FILENAME

    # ── Auth ──────────────────────────────────────────────────────────────────

    def get_account(self) -> Any:
        """Return an authenticated O365 Account, triggering OAuth if needed.

        On first call this may open a browser for the OAuth consent flow.
        Subsequent calls return the cached (and auto-refreshed) account.

        Raises:
            ValueError: If ``OUTLOOK_CLIENT_ID`` is not set.
            RuntimeError: If the OAuth flow fails.
        """
        if self._o365_account is not None:
            return self._o365_account

        if not self.client_id:
            raise ValueError(
                "OUTLOOK_CLIENT_ID environment variable is required. "
                "Register an app at https://entra.microsoft.com and set the "
                "Application (client) ID in your .env file."
            )

        # Migrate legacy token from old hardcoded path if needed.
        self._maybe_migrate_token()

        token_backend = FileSystemTokenBackend(
            token_path=str(self.token_dir),
            token_filename=_TOKEN_FILENAME,
        )
        o365_account = Account(
            credentials=(self.client_id, ""),
            auth_flow_type="authorization",
            tenant_id=self.tenant_id,
            token_backend=token_backend,
        )

        if not o365_account.is_authenticated:
            result = o365_account.authenticate(scopes=self.scopes)
            if not result:
                raise RuntimeError(
                    "Microsoft 365 authentication failed. "
                    "Check your OUTLOOK_CLIENT_ID and OUTLOOK_TENANT_ID settings."
                )
            logger.info("Authenticated with Microsoft 365 as %s", self.account)

        self._o365_account = o365_account
        return o365_account

    # ── Internal ──────────────────────────────────────────────────────────────

    def _maybe_migrate_token(self) -> None:
        """Copy legacy o365_token.txt to account-namespaced path if needed."""
        legacy = self._credentials_dir / _LEGACY_TOKEN_RELPATH
        new_path = self.token_file
        if legacy.exists() and not new_path.exists():
            shutil.copy(legacy, new_path)
            logger.info("Migrated Microsoft token: %s → %s", legacy, new_path)
