"""
Outlook / Microsoft 365 authentication for iobox.

Handles OAuth 2.0 authentication via the python-o365 library (MSAL internally).
Supports both the interactive browser flow (default) and the device-code flow
for headless / CI environments.

Token storage
-------------
Tokens are persisted by python-o365's ``FileSystemTokenBackend`` at:

    $CREDENTIALS_DIR/tokens/{account}/o365_token.txt

where ``{account}`` defaults to ``"default"``.  This mirrors the per-account
namespacing used by ``GoogleAuth`` and fixes the previous hardcoded path
(``tokens/outlook/o365_token.txt``).

Migration
---------
On first use with a non-default account, ``get_outlook_account()`` will
automatically copy an existing token from the old hardcoded path
(``tokens/outlook/o365_token.txt``) to the new account-namespaced path so that
users do not need to re-authenticate.

Environment variables
---------------------
OUTLOOK_CLIENT_ID      Required. Azure App Registration Application (client) ID.
OUTLOOK_CLIENT_SECRET  Optional. Leave empty for public-client (desktop) apps.
OUTLOOK_TENANT_ID      Defaults to ``common`` (multi-tenant / personal accounts).
CREDENTIALS_DIR        Base directory for all iobox credential files.
"""

import logging
import os
import shutil
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — module-level constants kept for backward compatibility.
# Actual resolution happens lazily in _get_config() so that tests can patch
# os.getenv (or _get_config itself) after import without ordering constraints.
# ---------------------------------------------------------------------------

OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET: str = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_TENANT_ID: str = os.getenv("OUTLOOK_TENANT_ID", "common")
CREDENTIALS_DIR: str = os.getenv("CREDENTIALS_DIR", os.getcwd())

OUTLOOK_TOKEN_DIR: str = os.path.join(CREDENTIALS_DIR, "tokens", "outlook")

# Token filename — kept stable so existing token files are not invalidated.
_TOKEN_FILENAME = "o365_token.txt"

# Delegated Graph permissions required by iobox.
OUTLOOK_SCOPES: list[str] = ["Mail.ReadWrite", "Mail.Send"]


# ---------------------------------------------------------------------------
# Internal config helper — called lazily so patches applied after import work.
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
# Public API
# ---------------------------------------------------------------------------


def get_outlook_account(
    *,
    account: str = "default",
    device_code: bool = False,
) -> "Account":  # type: ignore[name-defined]  # noqa: F821
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
        from O365 import Account, FileSystemTokenBackend
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

    token_backend = FileSystemTokenBackend(token_path=token_dir, token_filename=_TOKEN_FILENAME)

    o365_account = Account(
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
    old_path = os.path.join(credentials_dir, "tokens", "outlook", _TOKEN_FILENAME)
    new_path = os.path.join(token_dir, _TOKEN_FILENAME)
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
    token_path = os.path.join(token_dir, _TOKEN_FILENAME)
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
        from O365 import Account, FileSystemTokenBackend

        credentials = (cfg["client_id"], cfg["client_secret"])
        token_backend = FileSystemTokenBackend(token_path=token_dir, token_filename=_TOKEN_FILENAME)
        o365_account = Account(
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
