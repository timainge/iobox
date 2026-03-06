"""
Outlook / Microsoft 365 authentication for iobox.

Handles OAuth 2.0 authentication via the python-o365 library (MSAL internally).
Supports both the interactive browser flow (default) and the device-code flow
for headless / CI environments.

Token storage
-------------
Tokens are persisted by python-o365's ``FileSystemTokenBackend`` at:

    $CREDENTIALS_DIR/tokens/outlook/o365_token.txt

Environment variables
---------------------
OUTLOOK_CLIENT_ID      Required. Azure App Registration Application (client) ID.
OUTLOOK_CLIENT_SECRET  Optional. Leave empty for public-client (desktop) apps.
OUTLOOK_TENANT_ID      Defaults to ``common`` (multi-tenant / personal accounts).
CREDENTIALS_DIR        Base directory for all iobox credential files.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — resolved once at module import time.
# ---------------------------------------------------------------------------

OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET: str = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_TENANT_ID: str = os.getenv("OUTLOOK_TENANT_ID", "common")
CREDENTIALS_DIR: str = os.getenv("CREDENTIALS_DIR", os.getcwd())

OUTLOOK_TOKEN_DIR: str = os.path.join(CREDENTIALS_DIR, "tokens", "outlook")

# Delegated Graph permissions required by iobox.
OUTLOOK_SCOPES: list[str] = ["Mail.ReadWrite", "Mail.Send"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_outlook_account(*, device_code: bool = False) -> "Account":  # type: ignore[name-defined]  # noqa: F821
    """Return an authenticated python-o365 ``Account`` object.

    On the first call the user is directed through the OAuth consent flow.
    Subsequent calls reuse the cached token (refreshing automatically when
    expired).

    Args:
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

    if not OUTLOOK_CLIENT_ID:
        raise ValueError(
            "OUTLOOK_CLIENT_ID environment variable is required. "
            "Register an app at https://entra.microsoft.com and set the "
            "Application (client) ID in your .env file."
        )

    credentials = (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET)
    os.makedirs(OUTLOOK_TOKEN_DIR, exist_ok=True)
    token_backend = FileSystemTokenBackend(
        token_path=OUTLOOK_TOKEN_DIR, token_filename="o365_token.txt"
    )

    account = Account(
        credentials,
        tenant_id=OUTLOOK_TENANT_ID,
        token_backend=token_backend,
    )

    if not account.is_authenticated:
        if device_code:
            result = account.authenticate(
                scopes=OUTLOOK_SCOPES,
                grant_type="device_code",
            )
        else:
            result = account.authenticate(scopes=OUTLOOK_SCOPES)

        if not result:
            raise RuntimeError(
                "Outlook authentication failed. "
                "Check your OUTLOOK_CLIENT_ID and OUTLOOK_TENANT_ID settings."
            )
        logger.info("Successfully authenticated with Microsoft 365")

    return account


def check_outlook_auth_status() -> dict:
    """Return Outlook authentication status without triggering an auth flow.

    Inspects the token file and, if present, instantiates ``Account`` to check
    whether the cached token is valid.  Never opens a browser or prompts the
    user.

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
    token_path = os.path.join(OUTLOOK_TOKEN_DIR, "o365_token.txt")
    status: dict = {
        "authenticated": False,
        "client_id_configured": bool(OUTLOOK_CLIENT_ID),
        "tenant_id": OUTLOOK_TENANT_ID,
        "token_file_exists": os.path.exists(token_path),
        "token_path": token_path,
    }

    if not status["client_id_configured"] or not status["token_file_exists"]:
        return status

    try:
        from O365 import Account, FileSystemTokenBackend

        credentials = (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET)
        token_backend = FileSystemTokenBackend(
            token_path=OUTLOOK_TOKEN_DIR, token_filename="o365_token.txt"
        )
        account = Account(
            credentials,
            tenant_id=OUTLOOK_TENANT_ID,
            token_backend=token_backend,
        )
        status["authenticated"] = account.is_authenticated
    except ImportError:
        status["error"] = (
            "O365 package not installed. "
            "Install it with: pip install 'iobox[outlook]'"
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status
