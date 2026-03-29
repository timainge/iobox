"""
Microsoft 365 authentication for iobox — OAuth credential manager and helpers.

``MicrosoftAuth`` manages one OAuth token per (account, scope_set) pair and is
shared across Outlook, Calendar, and OneDrive providers for the same account.

The lower-level functions (``get_outlook_account``, ``check_outlook_auth_status``)
wrap the legacy single-account behaviour used by the CLI and MCP server.

Usage::

    from iobox.providers.o365.auth import MicrosoftAuth

    auth = MicrosoftAuth(account="corp@megacorp.com", scopes=["Mail.Read"])
    account = auth.get_account()

Token path: ``{credentials_dir}/tokens/{account}/microsoft_token.txt``
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from O365 import Account, FileSystemTokenBackend

    HAS_O365 = True
except ImportError:
    Account = None
    FileSystemTokenBackend = None
    HAS_O365 = False

# ---------------------------------------------------------------------------
# Module-level constants (kept for backward compatibility)
# ---------------------------------------------------------------------------

OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET: str = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_TENANT_ID: str = os.getenv("OUTLOOK_TENANT_ID", "common")
CREDENTIALS_DIR: str = os.getenv("CREDENTIALS_DIR", os.getcwd())

OUTLOOK_TOKEN_DIR: str = os.path.join(CREDENTIALS_DIR, "tokens", "outlook")

_TOKEN_FILENAME = "microsoft_token.txt"
_LEGACY_TOKEN_FILENAME = "o365_token.txt"
_LEGACY_TOKEN_RELPATH = os.path.join("tokens", "outlook", _LEGACY_TOKEN_FILENAME)

# Delegated Graph permissions required by iobox.
OUTLOOK_SCOPES: list[str] = ["Mail.ReadWrite", "Mail.Send"]


# ---------------------------------------------------------------------------
# Scope builder
# ---------------------------------------------------------------------------


def get_microsoft_scopes(services: list[str], mode: str) -> list[str]:
    """Build combined Microsoft scope list for given services and mode.

    Args:
        services: Subset of ``["email", "calendar", "drive"]``.
        mode: ``"readonly"`` or ``"standard"`` (dangerous treated as standard).

    Returns:
        Deduplicated list of Microsoft Graph scope strings.
    """
    scopes: list[str] = ["basic"]
    if "email" in services:
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


# ---------------------------------------------------------------------------
# MicrosoftAuth — shared credential manager
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Config helper — called lazily so patches applied after import work
# ---------------------------------------------------------------------------


def _get_config(account: str = "default") -> dict[str, str]:
    """Return a dict of resolved configuration values.

    Reads environment variables at call time so that tests can patch
    ``os.getenv`` (or this function) without needing to reload the module.

    Args:
        account: Account identifier used to derive the token directory.
            Defaults to ``"default"``.
    """
    credentials_dir = os.getenv("CREDENTIALS_DIR", os.getcwd())
    return {
        "client_id": os.getenv("OUTLOOK_CLIENT_ID", ""),
        "client_secret": os.getenv("OUTLOOK_CLIENT_SECRET", ""),
        "tenant_id": os.getenv("OUTLOOK_TENANT_ID", "common"),
        "credentials_dir": credentials_dir,
        # Account-namespaced token dir (replaces hardcoded "tokens/outlook").
        "token_dir": os.path.join(credentials_dir, "tokens", account),
    }


# ---------------------------------------------------------------------------
# Public API — legacy helpers
# ---------------------------------------------------------------------------


def get_outlook_account(
    *,
    account: str = "default",
    device_code: bool = False,
) -> Any:
    """Return an authenticated python-o365 ``Account`` object.

    On the first call the user is directed through the OAuth consent flow.
    Subsequent calls reuse the cached token (refreshing automatically when
    expired).

    The token is stored at ``$CREDENTIALS_DIR/tokens/{account}/o365_token.txt``.
    If an existing token exists at the old hardcoded path
    (``tokens/outlook/o365_token.txt``) and no token exists at the new path,
    it is automatically migrated.

    Args:
        account: Account identifier for token namespacing.  Defaults to
            ``"default"``.
        device_code: When ``True``, use the device-code flow instead of
            launching a local browser.  Useful for headless / SSH environments.

    Returns:
        An authenticated ``O365.Account`` instance.

    Raises:
        ValueError: If ``OUTLOOK_CLIENT_ID`` is not set.
        RuntimeError: If the authentication flow fails.
        ImportError: If the ``O365`` package is not installed.
    """
    try:
        from O365 import Account as _Account
        from O365 import FileSystemTokenBackend as _FSTB
    except ImportError as exc:
        raise ImportError(
            "The 'O365' package is required for Outlook support. "
            "Install it with: pip install 'iobox[outlook]'  "
            "or: pip install O365>=2.1.8"
        ) from exc

    cfg = _get_config(account=account)

    if not cfg["client_id"]:
        raise ValueError(
            "OUTLOOK_CLIENT_ID environment variable is required. "
            "Register an app at https://entra.microsoft.com and set the "
            "Application (client) ID in your .env file."
        )

    credentials = (cfg["client_id"], cfg["client_secret"])
    token_dir = cfg["token_dir"]
    os.makedirs(token_dir, exist_ok=True)

    # Migration: copy old hardcoded token to new account-namespaced path.
    _maybe_migrate_outlook_token(
        credentials_dir=cfg["credentials_dir"],
        token_dir=token_dir,
    )

    token_backend = _FSTB(token_path=token_dir, token_filename=_LEGACY_TOKEN_FILENAME)

    o365_account = _Account(
        credentials,
        tenant_id=cfg["tenant_id"],
        token_backend=token_backend,
    )

    if not o365_account.is_authenticated:
        if device_code:
            result = o365_account.authenticate(
                scopes=OUTLOOK_SCOPES,
                grant_type="device_code",
            )
        else:
            result = o365_account.authenticate(scopes=OUTLOOK_SCOPES)

        if not result:
            raise RuntimeError(
                "Outlook authentication failed. "
                "Check your OUTLOOK_CLIENT_ID and OUTLOOK_TENANT_ID settings."
            )
        logger.info("Successfully authenticated with Microsoft 365")

    return o365_account


def _maybe_migrate_outlook_token(credentials_dir: str, token_dir: str) -> None:
    """Copy legacy Outlook token to account-namespaced path if needed.

    Migrates ``$CREDENTIALS_DIR/tokens/outlook/o365_token.txt`` →
    ``{token_dir}/o365_token.txt`` on first use of the new path.
    Does nothing if the new token already exists.

    Args:
        credentials_dir: Base credentials directory.
        token_dir: New account-namespaced token directory.
    """
    old_path = os.path.join(credentials_dir, "tokens", "outlook", _LEGACY_TOKEN_FILENAME)
    new_path = os.path.join(token_dir, _LEGACY_TOKEN_FILENAME)
    if os.path.exists(old_path) and not os.path.exists(new_path):
        shutil.copy(old_path, new_path)
        logger.info(f"Migrated Outlook token: {old_path} → {new_path}")


def check_outlook_auth_status(account: str = "default") -> dict[str, Any]:
    """Return Outlook authentication status without triggering an auth flow.

    Inspects the token file and, if present, instantiates ``Account`` to check
    whether the cached token is valid.  Never opens a browser or prompts the
    user.

    Args:
        account: Account identifier for token namespacing.  Defaults to
            ``"default"``.

    Returns:
        A dict with the following keys:

        ``authenticated`` (bool)
            ``True`` if a valid (or auto-refreshable) token exists.
        ``client_id_configured`` (bool)
            ``True`` if ``OUTLOOK_CLIENT_ID`` is set.
        ``tenant_id`` (str)
            The effective tenant ID.
        ``token_file_exists`` (bool)
            ``True`` if the token file is present on disk.
        ``token_path`` (str)
            Full path where the token file is (or would be) stored.
        ``error`` (str, optional)
            Present only if an exception occurred while reading the token.
    """
    cfg = _get_config(account=account)
    token_dir = cfg["token_dir"]
    token_path = os.path.join(token_dir, _LEGACY_TOKEN_FILENAME)
    status: dict[str, Any] = {
        "authenticated": False,
        "client_id_configured": bool(cfg["client_id"]),
        "tenant_id": cfg["tenant_id"],
        "token_file_exists": os.path.exists(token_path),
        "token_path": token_path,
    }

    if not status["client_id_configured"] or not status["token_file_exists"]:
        return status

    try:
        from O365 import Account as _Account
        from O365 import FileSystemTokenBackend as _FSTB

        credentials = (cfg["client_id"], cfg["client_secret"])
        token_backend = _FSTB(token_path=token_dir, token_filename=_LEGACY_TOKEN_FILENAME)
        o365_account = _Account(
            credentials,
            tenant_id=cfg["tenant_id"],
            token_backend=token_backend,
        )
        status["authenticated"] = o365_account.is_authenticated
    except ImportError:
        status["error"] = (
            "O365 package not installed. Install it with: pip install 'iobox[outlook]'"
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status
