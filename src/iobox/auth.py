"""
Authentication Module for Gmail API access.

This module handles the OAuth 2.0 authentication flow for the Gmail API.
Supports multi-profile token storage with per-account, per-scope-tier token files.
"""

import logging
import os
import shutil
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from iobox.accounts import get_active_account
from iobox.modes import SCOPE_IMPLIES, SCOPES_BY_MODE, AccessMode, get_mode_from_env

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Active mode – set via set_active_mode() before first auth call.
_active_mode: AccessMode | None = None


def set_active_mode(mode: AccessMode) -> None:
    """Set the active access mode (called early by CLI / MCP entry-point)."""
    global _active_mode
    _active_mode = mode


def get_active_scopes() -> list[str]:
    """Return the Gmail API scopes for the currently active mode."""
    mode = _active_mode if _active_mode is not None else get_mode_from_env()
    return SCOPES_BY_MODE[mode]


def _expand_scopes(scopes: set[str]) -> set[str]:
    """Expand a set of scopes with any implied scopes (e.g. modify implies readonly)."""
    expanded = set(scopes)
    for scope in scopes:
        expanded |= SCOPE_IMPLIES.get(scope, set())
    return expanded


# Keep SCOPES as a module-level alias for backward compatibility in tests.
SCOPES = SCOPES_BY_MODE[AccessMode.standard]

# Get credential paths from environment variables or use defaults
CREDENTIALS_DIR = os.getenv("CREDENTIALS_DIR", os.getcwd())
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")

# Create full paths
CREDENTIALS_PATH = os.path.join(CREDENTIALS_DIR, CREDENTIALS_FILE)
TOKEN_PATH = os.path.join(CREDENTIALS_DIR, TOKEN_FILE)

# ---------------------------------------------------------------------------
# Multi-profile token helpers
# ---------------------------------------------------------------------------

# Only two distinct scope tiers: readonly and standard (dangerous reuses standard scopes).
_SCOPE_TIER_MAP: dict[AccessMode, str] = {
    AccessMode.readonly: "readonly",
    AccessMode.standard: "standard",
    AccessMode.dangerous: "standard",
}


def _scope_tier_for_mode(mode: AccessMode) -> str:
    """Return the scope tier name ('readonly' or 'standard') for a given mode."""
    return _SCOPE_TIER_MAP[mode]


def _get_token_dir(account: str) -> str:
    """Return the directory path for an account's tokens: $CREDENTIALS_DIR/tokens/{account}/."""
    return os.path.join(CREDENTIALS_DIR, "tokens", account)


def _get_token_path(account: str, scope_tier: str) -> str:
    """Return the full path to a token file: tokens/{account}/token_{tier}.json."""
    return os.path.join(_get_token_dir(account), f"token_{scope_tier}.json")


def _is_custom_token_file() -> bool:
    """Check whether the user has explicitly overridden GMAIL_TOKEN_FILE to a non-default value."""
    return os.getenv("GMAIL_TOKEN_FILE", "token.json") != "token.json"


def _maybe_migrate_legacy_token(account: str) -> None:
    """One-time migration: copy legacy token.json into the appropriate tier file.

    Only runs for the 'default' account. Does not delete the legacy file.
    """
    if account != "default":
        return

    legacy_path = os.path.join(CREDENTIALS_DIR, "token.json")
    if not os.path.exists(legacy_path):
        return

    token_dir = _get_token_dir(account)
    # Skip migration if any token file already exists in the directory
    if os.path.isdir(token_dir) and any(f.startswith("token_") for f in os.listdir(token_dir)):
        return

    # Read the legacy token to determine its scope tier
    try:
        creds = Credentials.from_authorized_user_file(legacy_path)  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Could not read legacy token.json for migration; skipping.")
        return

    # Determine tier from token scopes
    tier = "standard"  # default assumption
    if creds.scopes:
        has_modify = any("gmail.modify" in s for s in creds.scopes)
        has_compose = any("gmail.compose" in s for s in creds.scopes)
        if not has_modify and not has_compose:
            tier = "readonly"

    os.makedirs(token_dir, exist_ok=True)
    dest = _get_token_path(account, tier)
    shutil.copy2(legacy_path, dest)
    logger.info(f"Migrated legacy token.json → {dest}")


def _resolve_token(account: str, mode: AccessMode) -> tuple[str | None, str]:
    """Determine which token file to load and where to save a new one.

    Returns:
        (load_path, save_path): load_path is the path to an existing token file
        that satisfies the required scopes, or None if no suitable token exists.
        save_path is where a newly-obtained token should be written.
    """
    tier = _scope_tier_for_mode(mode)
    save_path = _get_token_path(account, tier)

    # 1. Exact match
    exact = _get_token_path(account, tier)
    if os.path.exists(exact):
        return exact, save_path

    # 2. If readonly mode, a standard token can serve (modify implies readonly)
    if tier == "readonly":
        broader = _get_token_path(account, "standard")
        if os.path.exists(broader):
            return broader, save_path

    return None, save_path


def get_gmail_service() -> Any:
    """
    Authenticate with Gmail API and return a service object.

    Uses multi-profile token storage when GMAIL_TOKEN_FILE is not explicitly set.
    Each account gets its own directory under $CREDENTIALS_DIR/tokens/{account}/,
    and each scope tier gets its own token file (token_readonly.json, token_standard.json).
    """
    scopes = get_active_scopes()
    mode = _active_mode if _active_mode is not None else get_mode_from_env()

    # If GMAIL_TOKEN_FILE is explicitly overridden, use legacy single-file behavior.
    if _is_custom_token_file():
        return _get_service_legacy(scopes)

    account = get_active_account()

    # Attempt legacy migration on first use
    _maybe_migrate_legacy_token(account)

    load_path, save_path = _resolve_token(account, mode)

    creds = None
    if load_path is not None:
        logger.info(f"Loading existing credentials from {load_path}")
        creds = Credentials.from_authorized_user_file(load_path, scopes)  # type: ignore[no-untyped-call]

        # Validate scopes — on mismatch, set creds to None (never delete the file).
        if creds and creds.valid and hasattr(creds, "scopes") and creds.scopes:
            required = set(scopes)
            current = _expand_scopes(set(creds.scopes))
            if not required.issubset(current):
                logger.warning("Scope upgrade required. Creating new token file...")
                creds = None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            creds.refresh(Request())
        else:
            logger.info(f"Initiating OAuth flow with credentials from {CREDENTIALS_PATH}")

            if not os.path.exists(CREDENTIALS_PATH):
                logger.error(f"Credentials file not found at {CREDENTIALS_PATH}")
                raise FileNotFoundError(
                    f"Credentials file not found at {CREDENTIALS_PATH}. "
                    f"Please download OAuth 2.0 Client ID JSON from Google Cloud Console."
                )

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        # Save the credentials to the appropriate tier file
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        logger.info(f"Saving credentials to {save_path}")
        with open(save_path, "w") as token:
            token.write(creds.to_json())

    # Build and return the Gmail service
    logger.info("Successfully authenticated with Gmail API")
    service = build("gmail", "v1", credentials=creds)
    return service


def _get_service_legacy(scopes: list[str]) -> Any:
    """Legacy single-file token behavior when GMAIL_TOKEN_FILE is explicitly set."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        logger.info(f"Loading existing credentials from {TOKEN_PATH}")
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)  # type: ignore[no-untyped-call]

        if creds and creds.valid and hasattr(creds, "scopes") and creds.scopes:
            required = set(scopes)
            current = _expand_scopes(set(creds.scopes))
            if not required.issubset(current):
                logger.warning("Scope upgrade required. Re-authenticating...")
                os.remove(TOKEN_PATH)
                creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            creds.refresh(Request())
        else:
            logger.info(f"Initiating OAuth flow with credentials from {CREDENTIALS_PATH}")

            if not os.path.exists(CREDENTIALS_PATH):
                logger.error(f"Credentials file not found at {CREDENTIALS_PATH}")
                raise FileNotFoundError(
                    f"Credentials file not found at {CREDENTIALS_PATH}. "
                    f"Please download OAuth 2.0 Client ID JSON from Google Cloud Console."
                )

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        logger.info(f"Saving credentials to {TOKEN_PATH}")
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    logger.info("Successfully authenticated with Gmail API")
    service = build("gmail", "v1", credentials=creds)
    return service


def get_gmail_credentials(
    account: str = "default",
    mode: str = "standard",
    credentials_dir: str | None = None,
) -> Credentials:
    """Return valid Gmail OAuth credentials via ``GoogleAuth``.

    Convenience wrapper for code that needs ``Credentials`` directly (e.g.
    building a service with custom options).  Most callers should use
    :func:`get_authenticated_service` or :func:`get_gmail_service` instead.

    Args:
        account: Account identifier for token namespacing.
        mode: Access mode string — ``"readonly"``, ``"standard"``, or
            ``"dangerous"``.
        credentials_dir: Base directory for credential files.  Defaults to
            ``CREDENTIALS_DIR`` env var.

    Returns:
        Valid :class:`google.oauth2.credentials.Credentials` instance.
    """
    from iobox.modes import _tier_for_mode, get_google_scopes
    from iobox.providers.google_auth import GoogleAuth

    scopes = get_google_scopes(["messages"], mode)
    tier = _tier_for_mode(mode)
    auth = GoogleAuth(
        account=account,
        scopes=scopes,
        credentials_dir=credentials_dir or CREDENTIALS_DIR,
        tier=tier,
    )
    return auth.get_credentials()


def get_authenticated_service(
    account: str = "default",
    mode: str = "standard",
    credentials_dir: str | None = None,
) -> Any:
    """Return an authenticated Gmail API service via ``GoogleAuth``.

    Thin wrapper around :class:`~iobox.providers.google_auth.GoogleAuth` that
    mirrors the signature of :func:`get_gmail_service` but accepts explicit
    ``account`` and ``mode`` parameters.

    Args:
        account: Account identifier for token namespacing.
        mode: Access mode string — ``"readonly"``, ``"standard"``, or
            ``"dangerous"``.
        credentials_dir: Base directory for credential files.

    Returns:
        Authenticated ``googleapiclient`` Gmail service object.
    """
    from iobox.modes import _tier_for_mode, get_google_scopes
    from iobox.providers.google_auth import GoogleAuth

    scopes = get_google_scopes(["messages"], mode)
    tier = _tier_for_mode(mode)
    auth = GoogleAuth(
        account=account,
        scopes=scopes,
        credentials_dir=credentials_dir or CREDENTIALS_DIR,
        tier=tier,
    )
    return auth.get_service("gmail", "v1")


def get_gmail_profile(service: Any) -> dict[str, Any]:
    """
    Get Gmail profile info including email address and mailbox stats.

    Args:
        service: Authenticated Gmail API service

    Returns:
        dict: Profile data with emailAddress, messagesTotal, threadsTotal
    """
    result: dict[str, Any] = service.users().getProfile(userId="me").execute()
    return result


def check_auth_status() -> dict[str, Any]:
    """
    Check the status of Gmail API authentication.

    Uses multi-profile resolution when GMAIL_TOKEN_FILE is not explicitly set.

    Returns:
        dict: Authentication status information
    """
    mode = _active_mode if _active_mode is not None else get_mode_from_env()
    scopes = get_active_scopes()

    # Determine the effective token path
    if _is_custom_token_file():
        effective_token_path = TOKEN_PATH
    else:
        account = get_active_account()
        _maybe_migrate_legacy_token(account)
        load_path, _ = _resolve_token(account, mode)
        effective_token_path = load_path or ""  # _resolve_token may return None

    status = {
        "authenticated": False,
        "credentials_file_exists": os.path.exists(CREDENTIALS_PATH),
        "token_file_exists": effective_token_path is not None
        and os.path.exists(effective_token_path),
        "credentials_path": CREDENTIALS_PATH,
        "token_path": effective_token_path
        or _get_token_path(get_active_account(), _scope_tier_for_mode(mode)),
    }

    if status["token_file_exists"]:
        try:
            assert effective_token_path is not None  # guaranteed by token_file_exists check above
            creds = Credentials.from_authorized_user_file(effective_token_path, scopes)  # type: ignore[no-untyped-call]
            status["authenticated"] = creds.valid
            status["expired"] = creds.expired if hasattr(creds, "expired") else False
            status["has_refresh_token"] = (
                bool(creds.refresh_token) if hasattr(creds, "refresh_token") else False
            )

        except Exception as e:
            logger.error(f"Error checking token file: {e}")
            status["error"] = str(e)

    return status
