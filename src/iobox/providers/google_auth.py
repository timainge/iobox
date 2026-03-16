"""
Shared Google OAuth credential manager for iobox.

``GoogleAuth`` is a single credential/token manager for all Google services
(Gmail, Calendar, Drive) using one OAuth token file per (account, tier) pair.

This lets ``GoogleCalendarProvider`` and ``GoogleDriveProvider`` share the same
token as ``GmailProvider`` for the same account, which is required by Google
(all scopes must be requested in one OAuth flow).

Usage::

    from iobox.providers.google_auth import GoogleAuth
    from iobox.modes import get_google_scopes

    scopes = get_google_scopes(["messages", "calendar", "drive"], "readonly")
    auth = GoogleAuth(account="tim@gmail.com", scopes=scopes, tier="readonly")
    calendar_service = auth.get_service("calendar", "v3")
    drive_service = auth.get_service("drive", "v3")
    gmail_service = auth.get_service("gmail", "v1")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


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
        """Return valid OAuth credentials, refreshing or re-authenticating as needed.

        Token loading order:

        1. In-memory cache (``self._credentials``) if still valid.
        2. Token file on disk for this account and tier.
        3. Attempt token refresh if expired.
        4. Full OAuth browser flow if no usable token exists.

        The refreshed or newly-obtained token is written to :attr:`token_path`.

        Raises:
            FileNotFoundError: If no credentials JSON file is found and a new
                OAuth flow needs to be started.
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Check for the GMAIL_TOKEN_FILE override (legacy single-file mode).
        # Only applied when the override differs from the default value.
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

        Returns:
            An authenticated ``googleapiclient.discovery.Resource`` instance.
        """
        creds = self.get_credentials()
        return build(api, version, credentials=creds)
