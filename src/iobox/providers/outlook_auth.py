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
# Configuration — module-level constants kept for backward compatibility.
# Actual resolution happens lazily in _get_config() so that tests can patch
# os.getenv (or _get_config itself) after import without ordering constraints.
# ---------------------------------------------------------------------------

OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET: str = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_TENANT_ID: str = os.getenv("OUTLOOK_TENANT_ID", "common")
CREDENTIALS_DIR: str = os.getenv("CREDENTIALS_DIR", os.getcwd())

OUTLOOK_TOKEN_DIR: str = os.path.join(CREDENTIALS_DIR, "tokens", "outlook")

# Delegated Graph permissions required by iobox.
OUTLOOK_SCOPES: list[str] = ["Mail.ReadWrite", "Mail.Send"]


# ---------------------------------------------------------------------------
# Internal config helper — called lazily so patches applied after import work.
# ---------------------------------------------------------------------------


def _get_config() -> dict:
    """Return a dict of resolved configuration values.

    Reads environment variables at call time so that tests can patch
    ``os.getenv`` (or this function) without needing to reload the module.
    """
    credentials_dir = os.getenv("CREDENTIALS_DIR", os.getcwd())
    return {
        "client_id": os.getenv("OUTLOOK_CLIENT_ID", ""),
        "client_secret": os.getenv("OUTLOOK_CLIENT_SECRET", ""),
        "tenant_id": os.getenv("OUTLOOK_TENANT_ID", "common"),
        "credentials_dir": credentials_dir,
        "token_dir": os.path.join(credentials_dir, "tokens", "outlook"),
    }


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

    cfg = _get_config()

    if not cfg["client_id"]:
        raise ValueError(
            "OUTLOOK_CLIENT_ID environment variable is required. "
            "Register an app at https://entra.microsoft.com and set the "
            "Application (client) ID in your .env file."
        )

    credentials = (cfg["client_id"], cfg["client_secret"])
    token_dir = cfg["token_dir"]
    os.makedirs(token_dir, exist_ok=True)
    token_backend = FileSystemTokenBackend(
        token_path=token_dir, token_filename="o365_token.txt"
    )

    account = Account(
        credentials,
        tenant_id=cfg["tenant_id"],
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
    cfg = _get_config()
    token_dir = cfg["token_dir"]
    token_path = os.path.join(token_dir, "o365_token.txt")
    status: dict = {
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
        token_backend = FileSystemTokenBackend(
            token_path=token_dir, token_filename="o365_token.txt"
        )
        account = Account(
            credentials,
            tenant_id=cfg["tenant_id"],
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
