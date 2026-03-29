"""
Google authentication for iobox — OAuth credential manager and Gmail helpers.

``GoogleAuth`` manages one OAuth token per (account, tier) pair and is shared
across Gmail, Calendar, and Drive providers for the same account.

The higher-level functions (``get_gmail_service``, ``check_auth_status``, etc.)
wrap ``GoogleAuth`` with the legacy single-account behaviour used by the CLI and
MCP server.

Usage::

    from iobox.providers.google.auth import GoogleAuth
    from iobox.modes import get_google_scopes

    scopes = get_google_scopes(["email", "calendar", "drive"], "readonly")
    auth = GoogleAuth(account="tim@gmail.com", scopes=scopes, tier="readonly")
    calendar_service = auth.get_service("calendar", "v3")
    drive_service = auth.get_service("drive", "v3")
    gmail_service = auth.get_service("gmail", "v1")
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from iobox.accounts import get_active_account
from iobox.modes import SCOPE_IMPLIES, SCOPES_BY_MODE, AccessMode, get_mode_from_env

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ── GoogleAuth ────────────────────────────────────────────────────────────────


class GoogleAuth:
    """Shared OAuth credential manager for all Google services.

    One instance per ``(account, tier)`` — handles Gmail, Calendar, and Drive
    with a single token file.  Providers call :meth:`get_service` to obtain an
    authenticated ``googleapiclient`` service without managing credentials
    themselves.

    Args:
        account: Account identifier used for token namespacing (e.g.
            ``"tim@gmail.com"``).  Defaults to ``"default"`` for backward
            compatibility.
        scopes: OAuth scope strings to request.  Build with
            :func:`iobox.modes.get_google_scopes`.
        credentials_dir: Base directory for credential and token files.
            Defaults to the current working directory.
        tier: Token-file tier — ``"readonly"`` or ``"standard"``.  Determines
            the filename ``token_{tier}.json``.  Defaults to ``"readonly"``.
    """

    def __init__(
        self,
        account: str = "default",
        scopes: list[str] | None = None,
        credentials_dir: str | None = None,
        tier: str = "readonly",
    ) -> None:
        self.account = account
        self.scopes: list[str] = scopes or []
        self.tier = tier
        self.credentials_dir = Path(credentials_dir or os.getcwd())
        self._credentials: Credentials | None = None

    # ── Path properties ───────────────────────────────────────────────────────

    @property
    def token_path(self) -> Path:
        """Full path to the token file for this (account, tier) pair."""
        token_dir = self.credentials_dir / "tokens" / self.account
        token_dir.mkdir(parents=True, exist_ok=True)
        return token_dir / f"token_{self.tier}.json"

    @property
    def credentials_file(self) -> Path:
        """Path to the Google OAuth client credentials JSON file.

        Respects the ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable;
        falls back to ``credentials.json`` in :attr:`credentials_dir`.
        """
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if env_path:
            return Path(env_path)
        return self.credentials_dir / "credentials.json"

    # ── Core auth methods ─────────────────────────────────────────────────────

    def get_credentials(self) -> Credentials:
        """Return valid OAuth credentials, refreshing or re-authenticating as needed."""
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Check for the GMAIL_TOKEN_FILE override (legacy single-file mode).
        legacy_token = os.environ.get("GMAIL_TOKEN_FILE", "token.json")
        if legacy_token != "token.json":
            token_path_str = (
                legacy_token
                if os.path.isabs(legacy_token)
                else str(self.credentials_dir / legacy_token)
            )
            if os.path.exists(token_path_str):
                creds: Credentials | None = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                    token_path_str, self.scopes
                )
                if creds and creds.valid:
                    self._credentials = creds
                    return creds

        creds = None
        token_path = self.token_path
        if token_path.exists():
            logger.info(f"Loading existing credentials from {token_path}")
            creds = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(token_path), self.scopes
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired credentials")
                creds.refresh(Request())
            else:
                creds_file = self.credentials_file
                if not creds_file.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found at {creds_file}. "
                        "Please download OAuth 2.0 Client ID JSON from Google Cloud Console."
                    )
                logger.info(f"Initiating OAuth flow with credentials from {creds_file}")
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), self.scopes)
                creds = flow.run_local_server(port=0)

            logger.info(f"Saving credentials to {token_path}")
            token_path.write_text(creds.to_json())

        self._credentials = creds
        return creds

    def get_service(self, api: str, version: str) -> Any:
        """Return an authenticated ``googleapiclient`` service.

        Args:
            api: Google API name, e.g. ``"gmail"``, ``"calendar"``, ``"drive"``.
            version: API version string, e.g. ``"v1"``, ``"v3"``.
        """
        creds = self.get_credentials()
        return build(api, version, credentials=creds)


# ── Legacy module-level state (used by get_gmail_service / check_auth_status) ─

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
    """Expand a set of scopes with any implied scopes."""
    expanded = set(scopes)
    for scope in scopes:
        expanded |= SCOPE_IMPLIES.get(scope, set())
    return expanded


# Keep SCOPES as a module-level alias for backward compatibility in tests.
SCOPES = SCOPES_BY_MODE[AccessMode.standard]

# Credential paths from environment variables or defaults.
CREDENTIALS_DIR = os.getenv("CREDENTIALS_DIR", os.getcwd())
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")

CREDENTIALS_PATH = os.path.join(CREDENTIALS_DIR, CREDENTIALS_FILE)
TOKEN_PATH = os.path.join(CREDENTIALS_DIR, TOKEN_FILE)

# ---------------------------------------------------------------------------
# Multi-profile token helpers
# ---------------------------------------------------------------------------

_SCOPE_TIER_MAP: dict[AccessMode, str] = {
    AccessMode.readonly: "readonly",
    AccessMode.standard: "standard",
    AccessMode.dangerous: "standard",
}


def _scope_tier_for_mode(mode: AccessMode) -> str:
    """Return the scope tier name ('readonly' or 'standard') for a given mode."""
    return _SCOPE_TIER_MAP[mode]


def _get_token_dir(account: str) -> str:
    """Return the directory path for an account's tokens."""
    return os.path.join(CREDENTIALS_DIR, "tokens", account)


def _get_token_path(account: str, scope_tier: str) -> str:
    """Return the full path to a token file: tokens/{account}/token_{tier}.json."""
    return os.path.join(_get_token_dir(account), f"token_{scope_tier}.json")


def _is_custom_token_file() -> bool:
    """Check whether the user has explicitly overridden GMAIL_TOKEN_FILE."""
    return os.getenv("GMAIL_TOKEN_FILE", "token.json") != "token.json"


def _maybe_migrate_legacy_token(account: str) -> None:
    """One-time migration: copy legacy token.json into the appropriate tier file."""
    if account != "default":
        return

    legacy_path = os.path.join(CREDENTIALS_DIR, "token.json")
    if not os.path.exists(legacy_path):
        return

    token_dir = _get_token_dir(account)
    if os.path.isdir(token_dir) and any(f.startswith("token_") for f in os.listdir(token_dir)):
        return

    try:
        creds = Credentials.from_authorized_user_file(legacy_path)  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Could not read legacy token.json for migration; skipping.")
        return

    tier = "standard"
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
    """Determine which token file to load and where to save a new one."""
    tier = _scope_tier_for_mode(mode)
    save_path = _get_token_path(account, tier)

    exact = _get_token_path(account, tier)
    if os.path.exists(exact):
        return exact, save_path

    if tier == "readonly":
        broader = _get_token_path(account, "standard")
        if os.path.exists(broader):
            return broader, save_path

    return None, save_path


def get_gmail_service() -> Any:
    """Authenticate with Gmail API and return a service object."""
    scopes = get_active_scopes()
    mode = _active_mode if _active_mode is not None else get_mode_from_env()

    if _is_custom_token_file():
        return _get_service_legacy(scopes)

    account = get_active_account()
    _maybe_migrate_legacy_token(account)
    load_path, save_path = _resolve_token(account, mode)

    creds = None
    if load_path is not None:
        logger.info(f"Loading existing credentials from {load_path}")
        creds = Credentials.from_authorized_user_file(load_path, scopes)  # type: ignore[no-untyped-call]

        if creds and creds.valid and hasattr(creds, "scopes") and creds.scopes:
            required = set(scopes)
            current = _expand_scopes(set(creds.scopes))
            if not required.issubset(current):
                logger.warning("Scope upgrade required. Creating new token file...")
                creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            creds.refresh(Request())
        else:
            logger.info(f"Initiating OAuth flow with credentials from {CREDENTIALS_PATH}")
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Credentials file not found at {CREDENTIALS_PATH}. "
                    "Please download OAuth 2.0 Client ID JSON from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        logger.info(f"Saving credentials to {save_path}")
        with open(save_path, "w") as token:
            token.write(creds.to_json())

    logger.info("Successfully authenticated with Gmail API")
    return build("gmail", "v1", credentials=creds)


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
                raise FileNotFoundError(
                    f"Credentials file not found at {CREDENTIALS_PATH}. "
                    "Please download OAuth 2.0 Client ID JSON from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        logger.info(f"Saving credentials to {TOKEN_PATH}")
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    logger.info("Successfully authenticated with Gmail API")
    return build("gmail", "v1", credentials=creds)


def get_gmail_credentials(
    account: str = "default",
    mode: str = "standard",
    credentials_dir: str | None = None,
) -> Credentials:
    """Return valid Gmail OAuth credentials via ``GoogleAuth``."""
    from iobox.modes import _tier_for_mode, get_google_scopes

    scopes = get_google_scopes(["email"], mode)
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
    """Return an authenticated Gmail API service via ``GoogleAuth``."""
    from iobox.modes import _tier_for_mode, get_google_scopes

    scopes = get_google_scopes(["email"], mode)
    tier = _tier_for_mode(mode)
    auth = GoogleAuth(
        account=account,
        scopes=scopes,
        credentials_dir=credentials_dir or CREDENTIALS_DIR,
        tier=tier,
    )
    return auth.get_service("gmail", "v1")


def get_gmail_profile(service: Any) -> dict[str, Any]:
    """Get Gmail profile info including email address and mailbox stats."""
    result: dict[str, Any] = service.users().getProfile(userId="me").execute()
    return result


def check_auth_status() -> dict[str, Any]:
    """Check the status of Gmail API authentication."""
    mode = _active_mode if _active_mode is not None else get_mode_from_env()
    scopes = get_active_scopes()

    if _is_custom_token_file():
        effective_token_path = TOKEN_PATH
    else:
        account = get_active_account()
        _maybe_migrate_legacy_token(account)
        load_path, _ = _resolve_token(account, mode)
        effective_token_path = load_path or ""

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
            assert effective_token_path is not None
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
