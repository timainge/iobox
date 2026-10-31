"""
Microsoft 365 authentication for iobox — OAuth credential manager and helpers.

``MicrosoftAuth`` manages one OAuth token per (account, tier) pair, where tier
is ``"readonly"`` or ``"standard"``. It is shared across the Outlook, Calendar
and OneDrive providers for the same account.

The lower-level functions (``get_outlook_account``, ``check_outlook_auth_status``)
wrap the legacy single-provider behaviour used by the CLI (``--provider
outlook``) and delegate to ``MicrosoftAuth``.

Usage::

    from iobox.providers.o365.auth import MicrosoftAuth

    auth = MicrosoftAuth(account="corp@megacorp.com", scopes=["basic", "Mail.Read"])
    account = auth.get_account()

Token path: ``{credentials_dir}/tokens/{account}/microsoft_token_{tier}.txt``
(file mode 0600, directory mode 0700).

Legacy token files — ``microsoft_token.txt`` and ``o365_token.txt`` in the
account directory, and ``tokens/outlook/o365_token.txt`` — were all requested
with write scopes, so they are migrated to the ``standard`` tier on first use.

Library notes (python-o365 2.1.x, verified against the source):

* ``Account.authenticate(requested_scopes=...)`` — an unknown ``scopes=`` kwarg
  is silently swallowed and *every* default scope is requested.
* MSAL adds ``offline_access``/``openid``/``profile`` itself and rejects them
  if passed explicitly; ``"basic"`` is the library alias for ``User.Read``.
* Without a client secret the app must use ``auth_flow_type="public"``
  (``PublicClientApplication``); ``"authorization"`` builds a confidential
  client and needs a secret to redeem the auth code.
* ``Connection.default_headers`` is merged into every Graph request (a
  caller-supplied ``Prefer`` header is joined with ``", "``), so it is the
  place to set ``Prefer: IdType="ImmutableId"``.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from iobox.auth_policy import require_interactive_auth
from iobox.providers.token_store import FilesystemTokenStore, TokenStore

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from O365 import Account, FileSystemTokenBackend
    from O365.utils.token import BaseTokenBackend

    HAS_O365 = True
except ImportError:
    Account = None
    FileSystemTokenBackend = object
    BaseTokenBackend = object
    HAS_O365 = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET: str = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_TENANT_ID: str = os.getenv("OUTLOOK_TENANT_ID", "common")
CREDENTIALS_DIR: str = os.getenv("CREDENTIALS_DIR", os.getcwd())

OUTLOOK_TOKEN_DIR: str = os.path.join(CREDENTIALS_DIR, "tokens", "outlook")

TIERS: tuple[str, ...] = ("readonly", "standard")

_TOKEN_FILENAME_TEMPLATE = "microsoft_token_{tier}.txt"
# Pre-tier MicrosoftAuth token (always requested with write scopes).
_LEGACY_TOKEN_FILENAME = "microsoft_token.txt"
# Pre-MicrosoftAuth get_outlook_account() token (Mail.ReadWrite + Mail.Send).
_LEGACY_O365_TOKEN_FILENAME = "o365_token.txt"
_LEGACY_TOKEN_RELPATH = os.path.join("tokens", "outlook", _LEGACY_O365_TOKEN_FILENAME)

# Delegated Graph permissions for the legacy single-provider Outlook path.
OUTLOOK_SCOPES: list[str] = ["Mail.ReadWrite", "Mail.Send"]

# Graph scope prefix added by MSGraphProtocol.get_scopes_for().
_GRAPH_SCOPE_PREFIX = "https://graph.microsoft.com/"
# Scopes MSAL adds on its own — never part of a coverage comparison.
_RESERVED_SCOPES = {"offline_access", "openid", "profile", "email"}

#: ``Prefer`` value that makes Graph return (and accept) immutable item IDs.
IMMUTABLE_ID_PREFER = 'IdType="ImmutableId"'

_TOKEN_FILE_MODE = 0o600
_TOKEN_DIR_MODE = 0o700


# ---------------------------------------------------------------------------
# ImmutableId preference
# ---------------------------------------------------------------------------


def ensure_immutable_ids(account: Any) -> None:
    """Make every Graph request made through *account* ask for immutable IDs.

    python-o365's ``Connection._internal_request`` merges
    ``con.default_headers`` into every request — mail, calendar and drive
    alike — and joins it with any per-request ``Prefer`` header (for example
    the ``outlook.timezone`` preference used by calendar calls). This must be
    set on ``default_headers``, not ``con.session``: the session is created
    lazily on the first request and is ``None`` right after authentication.

    Idempotent; preserves any existing ``Prefer`` value.
    """
    con = account.con
    headers = getattr(con, "default_headers", None)
    if not isinstance(headers, dict):
        headers = {}
        con.default_headers = headers
    prefer = headers.get("Prefer")
    if not prefer:
        headers["Prefer"] = IMMUTABLE_ID_PREFER
    elif "immutableid" not in str(prefer).lower():
        headers["Prefer"] = f"{prefer}, {IMMUTABLE_ID_PREFER}"


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def get_microsoft_scopes(services: list[str], mode: str) -> list[str]:
    """Build combined Microsoft scope list for given services and mode.

    Args:
        services: Subset of ``["email", "calendar", "drive"]``.
        mode: ``"readonly"`` or ``"standard"`` (dangerous treated as standard).

    Returns:
        Deduplicated list of Microsoft Graph scope strings (``"basic"`` is the
        python-o365 alias for ``User.Read``). Readonly mode never includes a
        write scope.
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


def tier_for_mode(mode: str | None) -> str:
    """Map an access mode to a token tier (dangerous reuses standard)."""
    return "readonly" if mode == "readonly" else "standard"


def tier_for_scopes(scopes: Iterable[str]) -> str:
    """Infer the token tier from a scope list: any write scope → ``standard``."""
    for scope in scopes:
        s = scope.lower()
        if "readwrite" in s or s.endswith(".send") or ".send." in s:
            return "standard"
    return "readonly"


def _normalize_scope(scope: str) -> str:
    s = scope.strip()
    if s.lower().startswith(_GRAPH_SCOPE_PREFIX):
        s = s[len(_GRAPH_SCOPE_PREFIX) :]
    return s.lower()


def scopes_cover(granted: Iterable[str], requested: Iterable[str]) -> bool:
    """Return True if *granted* scopes satisfy every *requested* scope.

    Comparison ignores the Graph URL prefix, case and MSAL's reserved scopes.
    A ``X.ReadWrite[.Y]`` grant satisfies a ``X.Read[.Y]`` request.
    """
    have = {_normalize_scope(s) for s in granted if s}
    for raw in requested:
        want = _normalize_scope(raw)
        if not want or want in _RESERVED_SCOPES or want in have:
            continue
        parts = want.split(".")
        if len(parts) >= 2 and parts[1] == "read":
            broader = ".".join([parts[0], "readwrite", *parts[2:]])
            if broader in have:
                continue
        return False
    return True


# ---------------------------------------------------------------------------
# Token backends
# ---------------------------------------------------------------------------


def _secure_dir(path: Path) -> None:
    """Create *path* (and parents) and restrict the leaf to the owner (0700)."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, _TOKEN_DIR_MODE)
    except OSError as exc:  # pragma: no cover - e.g. not the owner
        logger.debug("Could not chmod token dir %s: %s", path, exc)


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, _TOKEN_FILE_MODE)
    except OSError as exc:  # pragma: no cover
        logger.debug("Could not chmod token file %s: %s", path, exc)


def _write_private(path: Path, data: str | bytes) -> None:
    """Write *data* to *path* so the file is never readable by group/other."""
    _secure_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _TOKEN_FILE_MODE)
    try:
        # O_CREAT's mode is ignored for a pre-existing file — tighten it too.
        os.fchmod(fd, _TOKEN_FILE_MODE)
        payload = data.encode("utf-8") if isinstance(data, str) else data
        os.write(fd, payload)
    finally:
        os.close(fd)


class SecureFileSystemTokenBackend(FileSystemTokenBackend):  # type: ignore[misc]
    """``FileSystemTokenBackend`` that writes the token file 0600 in a 0700 dir.

    The upstream backend uses ``Path.open("w")`` (umask-dependent, usually
    0644), exposing refresh tokens to other local users (SEC-07).
    """

    def save_token(self, force: bool = False) -> bool:
        if not self._cache:
            return False
        if force is False and self._has_state_changed is False:
            return True
        try:
            _write_private(Path(self.token_path), self.serialize())
        except OSError as exc:
            logger.error("Token could not be saved: %s", exc)
            return False
        return True


class TokenStoreTokenBackend(BaseTokenBackend):  # type: ignore[misc]
    """Adapter: route O365's token cache through an iobox ``TokenStore``.

    O365's ``BaseTokenBackend`` works in two halves: ``self._cache`` (a
    dict-like cache that the rest of O365 reads/writes) plus
    ``load_token`` / ``save_token`` / ``delete_token`` / ``check_token``
    for persistence. This adapter persists by serializing the cache
    through the parent class' ``serialize``/``deserialize`` and storing
    the resulting JSON string under a single key in a TokenStore dict.

    Use case: nexus-api injects a ``PostgresTokenStore`` so each user's
    Microsoft tokens land encrypted in their own row instead of in a
    per-process file.

    ``fallback_tiers`` are read (never written) when ``tier`` has no payload,
    so tokens stored under an older tier name keep working.

    Construction fails loud if O365 is not installed.
    """

    _PAYLOAD_KEY = "_o365"

    def __init__(
        self,
        token_store: TokenStore,
        account: str,
        tier: str = "default",
        fallback_tiers: Iterable[str] = (),
    ) -> None:
        if not HAS_O365:
            raise ImportError(
                "O365 package required to use TokenStoreTokenBackend. "
                "Install with: pip install 'iobox[outlook]'"
            )
        super().__init__()
        self._token_store = token_store
        self._account = account
        self._tier = tier
        self._fallback_tiers = tuple(fallback_tiers)
        # Re-affirm the parent's flag in our scope so static analyzers see
        # the type.
        self._has_state_changed: bool = False

    def _load_payload(self) -> dict[str, Any] | None:
        for tier in (self._tier, *self._fallback_tiers):
            payload = self._token_store.load(self._account, tier)
            if payload and self._PAYLOAD_KEY in payload:
                return payload
        return None

    def load_token(self) -> bool:
        payload = self._load_payload()
        if payload is None:
            return False
        try:
            self._cache = self.deserialize(payload[self._PAYLOAD_KEY])
        except (ValueError, TypeError):
            logger.warning("o365 token cache failed to deserialize; re-auth needed")
            return False
        return True

    def save_token(self, force: bool = False) -> bool:
        if not self._cache:
            return False
        if force is False and self._has_state_changed is False:
            return True
        self._token_store.save(self._account, self._tier, {self._PAYLOAD_KEY: self.serialize()})
        self._has_state_changed = False
        return True

    def delete_token(self) -> bool:
        self._token_store.delete(self._account, self._tier)
        return True

    def check_token(self) -> bool:
        return self._load_payload() is not None


# ---------------------------------------------------------------------------
# MicrosoftAuth — shared credential manager
# ---------------------------------------------------------------------------


class MicrosoftAuth:
    """Shared auth for all Microsoft 365 services (Outlook, Calendar, OneDrive).

    One instance per (account, tier) handles a single OAuth token.
    Auth is lazy: the OAuth flow runs on the first call to ``get_account()``.

    Args:
        account: Account identifier used for token namespacing (e.g. an email
            address or ``"default"``).
        scopes: Microsoft Graph scopes to request (e.g. ``["basic", "Mail.Read"]``).
        credentials_dir: Base directory for credential files.  Defaults to
            ``~/.iobox``.
        client_id: Azure app client ID.  Reads ``OUTLOOK_CLIENT_ID`` if omitted.
        tenant_id: Azure tenant ID.  Reads ``OUTLOOK_TENANT_ID`` or ``"common"``.
        token_store: Optional custom ``TokenStore`` (e.g. Postgres-backed).
        tier: ``"readonly"`` or ``"standard"`` — selects the token file.
        mode: Access mode; used to derive ``tier`` when ``tier`` is omitted.
            When both are omitted the tier is inferred from ``scopes``.
        client_secret: Azure app client secret.  Reads
            ``OUTLOOK_CLIENT_SECRET`` if omitted.  Without a secret the
            public-client (PKCE) flow is used.
        device_code: Use the OAuth device-code flow instead of the
            paste-the-redirect-URL flow (headless / SSH environments).
            Always uses the public-client flow.
    """

    def __init__(
        self,
        account: str = "default",
        scopes: list[str] | None = None,
        credentials_dir: str | None = None,
        client_id: str | None = None,
        tenant_id: str | None = None,
        token_store: TokenStore | None = None,
        *,
        tier: str | None = None,
        mode: str | None = None,
        client_secret: str | None = None,
        device_code: bool = False,
    ) -> None:
        if not HAS_O365:
            raise ImportError(
                "O365 package required for Outlook support. "
                "Install with: pip install 'iobox[outlook]'"
            )
        from iobox.space_config import validate_account

        # The account names a directory under tokens/; reject path-like values.
        self.account = validate_account(account)
        self.scopes: list[str] = list(scopes) if scopes else ["basic", "Mail.Read"]
        self._credentials_dir = Path(credentials_dir or Path.home() / ".iobox")
        self.client_id: str = client_id or os.environ.get("OUTLOOK_CLIENT_ID") or ""
        self.client_secret: str = (
            client_secret
            if client_secret is not None
            else os.environ.get("OUTLOOK_CLIENT_SECRET", "")
        )
        self.tenant_id: str = tenant_id or os.environ.get("OUTLOOK_TENANT_ID") or "common"
        if tier is None:
            tier = tier_for_mode(mode) if mode is not None else tier_for_scopes(self.scopes)
        if tier not in TIERS:
            raise ValueError(f"Invalid token tier {tier!r}; expected one of {TIERS}")
        self.tier: str = tier
        self.device_code = device_code
        # Default store keeps tokens in per-tier files under credentials_dir
        # (via SecureFileSystemTokenBackend). Server callers inject a
        # Postgres-backed store scoped to the request's authenticated user.
        self.token_store: TokenStore = token_store or FilesystemTokenStore(self._credentials_dir)
        self._o365_account: Any | None = None

    # ── Path helpers ───────────────────────────────────────────────────────────

    @property
    def token_dir(self) -> Path:
        """Account-namespaced token directory (created 0700 on demand)."""
        d = self._credentials_dir / "tokens" / self.account
        _secure_dir(d)
        return d

    @property
    def token_file(self) -> Path:
        """Full path to this tier's token file."""
        return self.token_dir / _TOKEN_FILENAME_TEMPLATE.format(tier=self.tier)

    @property
    def _uses_filesystem(self) -> bool:
        return isinstance(self.token_store, FilesystemTokenStore)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def get_account(self) -> Any:
        """Return an authenticated O365 Account, triggering OAuth if needed.

        On first call this may run the interactive consent flow. If a cached
        token exists but does not cover the requested scopes it is discarded
        and the consent flow runs again. Subsequent calls return the cached
        (and auto-refreshed) account.

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

        if self._uses_filesystem:
            self._maybe_migrate_token()

        o365_account = self._build_account()
        request_scopes = list(self.scopes)

        if self._has_usable_token(o365_account) and not self._scopes_covered(o365_account):
            logger.info(
                "Cached Microsoft token for %s (%s) lacks requested scopes %s; re-authenticating",
                self.account,
                self.tier,
                self.scopes,
            )
            # Ask for the union so a provider needing fewer scopes later
            # (e.g. mail-only after calendar+mail) does not force another
            # consent round-trip. Never widen a readonly token.
            for scope in self._granted_scopes(o365_account) or []:
                short = _normalize_scope(scope)
                if (
                    short in _RESERVED_SCOPES
                    or self.tier == "readonly"
                    and (tier_for_scopes([short]) != "readonly")
                ):
                    continue
                if short not in {_normalize_scope(s) for s in request_scopes}:
                    request_scopes.append(scope)
            o365_account.con.token_backend.delete_token()
            o365_account = self._build_account()

        if not self._has_usable_token(o365_account):
            if not self._run_auth_flow(o365_account, request_scopes):
                raise RuntimeError(
                    "Microsoft 365 authentication failed. "
                    "Check your OUTLOOK_CLIENT_ID and OUTLOOK_TENANT_ID settings."
                )
            logger.info("Authenticated with Microsoft 365 as %s", self.account)

        self._o365_account = o365_account
        return o365_account

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_token_backend(self) -> Any:
        if self._uses_filesystem:
            return SecureFileSystemTokenBackend(
                token_path=str(self.token_dir),
                token_filename=_TOKEN_FILENAME_TEMPLATE.format(tier=self.tier),
            )
        # Custom store: namespace by provider so Microsoft and Google tokens
        # for the same account never collide. Tokens written before tiers
        # existed live under "default" and were requested with write scopes.
        fallback = ("default",) if self.tier == "standard" else ()
        return TokenStoreTokenBackend(
            self.token_store,
            self.account,
            tier=f"microsoft_{self.tier}",
            fallback_tiers=fallback,
        )

    def _build_account(self) -> Any:
        token_backend = self._make_token_backend()
        if self.client_secret and not self.device_code:
            credentials: Any = (self.client_id, self.client_secret)
            flow_type = "authorization"
        else:
            credentials = (self.client_id,)
            flow_type = "public"
        o365_account = Account(
            credentials,
            auth_flow_type=flow_type,
            tenant_id=self.tenant_id,
            token_backend=token_backend,
        )
        ensure_immutable_ids(o365_account)
        return o365_account

    @staticmethod
    def _has_usable_token(o365_account: Any) -> bool:
        try:
            return bool(o365_account.is_authenticated)
        except ValueError as exc:
            # FileSystemTokenBackend refuses pre-2.1 token formats.
            logger.warning("Ignoring unreadable Microsoft token: %s", exc)
            return False

    @staticmethod
    def _granted_scopes(o365_account: Any) -> list[str] | None:
        """Scopes recorded on the cached refresh/access token, if readable."""
        con = o365_account.con
        try:
            granted = con.token_backend.get_token_scopes(
                username=con.username, remove_reserved=True
            )
        except Exception as exc:  # defensive: unknown backend shape
            logger.debug("Could not read granted scopes: %s", exc)
            return None
        return list(granted) if granted else None

    def _scopes_covered(self, o365_account: Any) -> bool:
        """True unless the cached token's granted scopes are known to fall short."""
        granted = self._granted_scopes(o365_account)
        if not granted:
            return True  # unknown — trust the token
        requested = o365_account.protocol.get_scopes_for(self.scopes)
        return scopes_cover(granted, requested)

    def _run_auth_flow(self, o365_account: Any, scopes: list[str] | None = None) -> bool:
        require_interactive_auth(self.account)
        requested = scopes or self.scopes
        if self.device_code:
            return _device_code_flow(o365_account, requested)
        return bool(o365_account.authenticate(requested_scopes=requested))

    def _maybe_migrate_token(self) -> None:
        """Seed the standard-tier token from a legacy single-file token.

        Every legacy token was requested with write scopes, so only the
        ``standard`` tier migrates; readonly always gets a fresh, read-only
        consent. The legacy file is copied (not moved) and both copies are
        restricted to 0600.
        """
        if self.tier != "standard":
            return
        new_path = self.token_file
        if new_path.exists():
            return
        account_dir = self.token_dir
        candidates = [
            account_dir / _LEGACY_TOKEN_FILENAME,
            account_dir / _LEGACY_O365_TOKEN_FILENAME,
            self._credentials_dir / _LEGACY_TOKEN_RELPATH,
        ]
        for legacy in candidates:
            if legacy.exists():
                _write_private(new_path, legacy.read_bytes())
                _secure_file(legacy)
                logger.info("Migrated Microsoft token: %s → %s", legacy, new_path)
                return


def _device_code_flow(o365_account: Any, scopes: list[str]) -> bool:
    """Run the MSAL device-code flow and store the token in the account backend.

    python-o365 has no device-code wrapper, but its ``Connection.msal_client``
    is an MSAL ``PublicClientApplication`` (for ``auth_flow_type="public"``)
    whose token cache *is* the O365 token backend, so the acquired token is
    immediately visible to the account.
    """
    con = o365_account.con
    requested = o365_account.protocol.get_scopes_for(scopes)
    client = con.msal_client
    flow = client.initiate_device_flow(scopes=requested)
    if "user_code" not in flow:
        logger.error("Device-code flow could not start: %s", flow.get("error_description"))
        return False
    print(flow.get("message", ""), file=sys.stderr, flush=True)
    result = client.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        logger.error(
            "Device-code authentication failed: %s | %s",
            result.get("error"),
            result.get("error_description"),
        )
        return False
    claims = result.get("id_token_claims") or {}
    username = claims.get("preferred_username")
    if username:
        con.username = username
    con.token_backend.save_token(force=True)
    return True


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
    mode: str = "standard",
) -> Any:
    """Return an authenticated python-o365 ``Account`` for the Outlook provider.

    Thin wrapper over :class:`MicrosoftAuth` using ``$CREDENTIALS_DIR``
    (default: cwd) and email-only scopes for *mode*. The token lives at
    ``$CREDENTIALS_DIR/tokens/{account}/microsoft_token_{tier}.txt``; legacy
    ``o365_token.txt`` files are migrated to the standard tier.

    Args:
        account: Account identifier for token namespacing.
        device_code: Use the device-code flow (headless / SSH environments).
        mode: Access mode — ``"readonly"`` requests only ``Mail.Read``.

    Raises:
        ValueError: If ``OUTLOOK_CLIENT_ID`` is not set.
        RuntimeError: If the authentication flow fails.
        ImportError: If the ``O365`` package is not installed.
    """
    if not HAS_O365:
        raise ImportError(
            "The 'O365' package is required for Outlook support. "
            "Install it with: pip install 'iobox[outlook]'  "
            "or: pip install O365>=2.1.8"
        )

    cfg = _get_config(account=account)
    if not cfg["client_id"]:
        raise ValueError(
            "OUTLOOK_CLIENT_ID environment variable is required. "
            "Register an app at https://entra.microsoft.com and set the "
            "Application (client) ID in your .env file."
        )

    auth = MicrosoftAuth(
        account=account,
        scopes=get_microsoft_scopes(["email"], mode),
        credentials_dir=cfg["credentials_dir"],
        client_id=cfg["client_id"],
        tenant_id=cfg["tenant_id"],
        client_secret=cfg["client_secret"],
        mode=mode,
        device_code=device_code,
    )
    return auth.get_account()


def check_outlook_auth_status(account: str = "default", mode: str = "standard") -> dict[str, Any]:
    """Return Outlook authentication status without triggering an auth flow.

    Inspects the tier's token file (or a legacy token that would be migrated)
    and, if present, instantiates ``Account`` to check whether the cached
    token is valid.  Never opens a browser, prompts, or makes a network call.

    Returns:
        A dict with ``authenticated``, ``client_id_configured``, ``tenant_id``,
        ``token_file_exists``, ``token_path`` and, on failure, ``error``.
    """
    cfg = _get_config(account=account)
    tier = tier_for_mode(mode)
    token_dir = Path(cfg["token_dir"])
    token_path = token_dir / _TOKEN_FILENAME_TEMPLATE.format(tier=tier)

    existing: Path | None = token_path if token_path.exists() else None
    if existing is None and tier == "standard":
        for legacy in (
            token_dir / _LEGACY_TOKEN_FILENAME,
            token_dir / _LEGACY_O365_TOKEN_FILENAME,
            Path(cfg["credentials_dir"]) / _LEGACY_TOKEN_RELPATH,
        ):
            if legacy.exists():
                existing = legacy
                break

    status: dict[str, Any] = {
        "authenticated": False,
        "client_id_configured": bool(cfg["client_id"]),
        "tenant_id": cfg["tenant_id"],
        "token_file_exists": existing is not None,
        "token_path": str(token_path),
    }

    if not status["client_id_configured"] or existing is None:
        return status

    if not HAS_O365:
        status["error"] = (
            "O365 package not installed. Install it with: pip install 'iobox[outlook]'"
        )
        return status

    try:
        backend = SecureFileSystemTokenBackend(
            token_path=str(existing.parent), token_filename=existing.name
        )
        o365_account = Account(
            (cfg["client_id"],),
            auth_flow_type="public",
            tenant_id=cfg["tenant_id"],
            token_backend=backend,
        )
        status["authenticated"] = bool(o365_account.is_authenticated)
    except Exception as exc:
        status["error"] = str(exc)

    return status


__all__ = [
    "HAS_O365",
    "IMMUTABLE_ID_PREFER",
    "MicrosoftAuth",
    "OUTLOOK_SCOPES",
    "SecureFileSystemTokenBackend",
    "TIERS",
    "TokenStoreTokenBackend",
    "check_outlook_auth_status",
    "ensure_immutable_ids",
    "get_microsoft_scopes",
    "get_outlook_account",
    "scopes_cover",
    "tier_for_mode",
    "tier_for_scopes",
]
