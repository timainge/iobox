"""
Space configuration — schema, I/O, and path constants for ~/.iobox/.

A *space* is a named collection of service sessions (google, o365) that
form a user's workspace. This module owns the TOML config schema and the
JSON session-state schema, but knows nothing about providers or OAuth.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args

# tomllib is stdlib on Python 3.11+; fall back to tomli on 3.10.
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[import-not-found,no-reuse-imports]
    except ImportError as exc:
        raise ImportError("Python < 3.11 requires the 'tomli' package: pip install tomli") from exc

import tomli_w  # for writing TOML

logger = logging.getLogger(__name__)

# ── Path constants (module-level so tests can monkeypatch) ────────────────────

IOBOX_HOME: Path = Path.home() / ".iobox"
WORKSPACES_DIR: Path = IOBOX_HOME / "workspaces"
TOKENS_DIR: Path = IOBOX_HOME / "tokens"
INDEXES_DIR: Path = IOBOX_HOME / "indexes"
ACTIVE_SPACE_FILE: Path = IOBOX_HOME / "active_space"


# ── Validation ────────────────────────────────────────────────────────────────

ServiceType = Literal["google", "o365"]
ModeType = Literal["readonly", "standard", "dangerous"]

VALID_SERVICES: frozenset[str] = frozenset(get_args(ServiceType))
VALID_MODES: frozenset[str] = frozenset(get_args(ModeType))

_SPACE_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def validate_space_name(name: str) -> str:
    """Return *name* unchanged if it is a safe workspace name, else raise ValueError.

    Workspace names become file names under ``~/.iobox/workspaces/``, so only
    letters, digits, ``_`` and ``-`` are allowed (1–64 characters).
    """
    if not isinstance(name, str) or not _SPACE_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid workspace name {name!r}: use 1-64 letters, digits, '_' or '-'.")
    return name


def validate_account(account: str) -> str:
    """Return *account* unchanged if it is safe to use as a directory name.

    Account strings (usually email addresses) name per-account token and index
    directories. Rejects empty strings, path separators, NUL and a leading
    ``.`` (which also covers ``.`` and ``..``). Without separators the value is
    a single path component, so ``a..b@x.com`` is safe. Case is preserved —
    existing directories are not renamed.
    """
    if not isinstance(account, str) or not account.strip():
        raise ValueError("Invalid account: must be a non-empty string.")
    if "/" in account or "\\" in account or "\x00" in account or account.startswith("."):
        raise ValueError(
            f"Invalid account {account!r}: must not contain '/', '\\' or NUL, or start with '.'."
        )
    return account


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class ServiceEntry:
    """One service session within a space (e.g. google/tim@gmail.com)."""

    number: int
    service: ServiceType
    account: str
    scopes: list[str]  # ["email", "calendar", "drive"]
    mode: ModeType = "standard"
    slug: str = ""  # auto-derived from account if empty
    id: str = ""  # auto-derived from service+account if empty

    def __post_init__(self) -> None:
        validate_account(self.account)
        if not self.id:
            self.id = _derive_id(self.service, self.account)
        if not self.slug:
            self.slug = _derive_slug(self.account)


@dataclass
class SpaceConfig:
    """Contents of ~/.iobox/workspaces/{name}.toml."""

    name: str
    services: list[ServiceEntry] = field(default_factory=list)


@dataclass
class ServiceSessionState:
    """Auth state for one service session — written by the CLI, not by the user."""

    authenticated: bool = False
    scopes: list[str] = field(default_factory=list)
    token_path: str = ""
    last_sync: str | None = None
    error: str | None = None


@dataclass
class SpaceSession:
    """Contents of ~/.iobox/workspaces/{name}.session.json."""

    workspace: str
    updated_at: str = ""
    services: dict[str, ServiceSessionState] = field(default_factory=dict)


# ── Derive helpers ────────────────────────────────────────────────────────────


def _derive_id(service: str, account: str) -> str:
    """gmail + tim@gmail.com → gmail-timgmailcom"""
    clean = account.replace("@", "").replace(".", "").lower()
    return f"{service}-{clean}"


def _derive_slug(account: str) -> str:
    """tim@gmail.com → tim-gmail"""
    if "@" not in account:
        return account.lower()
    local, domain = account.split("@", 1)
    domain_part = domain.split(".")[0]  # gmail, outlook, megacorp, …
    return f"{local}-{domain_part}".lower()


def unique_slug(config: SpaceConfig, account: str) -> str:
    """Derive a slug for *account* that is unique within *config*.

    Starts from the usual ``local-domain`` slug (``tim@gmail.com`` → ``tim-gmail``)
    and appends ``-2``, ``-3``, … if another service in the space already uses
    it (e.g. ``tim@gmail.co.uk`` → ``tim-gmail-2``). Slugs already stored in a
    config are never changed — pass the result as ``ServiceEntry(slug=...)``
    when adding a new entry.
    """
    base = _derive_slug(account)
    taken = {s.slug for s in config.services}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def find_service(config: SpaceConfig, service: str, account: str) -> ServiceEntry | None:
    """Return the entry in *config* for ``(service, account)``, or None.

    Accounts compare case-insensitively and legacy service names (``gmail``,
    ``outlook``) are normalised, so callers can reject duplicate ``space add``
    requests before running OAuth.
    """
    svc = _SERVICE_MIGRATION.get(service.lower(), service.lower())
    acct = account.strip().lower()
    for entry in config.services:
        if entry.service == svc and entry.account.lower() == acct:
            return entry
    return None


# ── Directory management ──────────────────────────────────────────────────────


def ensure_iobox_home() -> None:
    """Create ~/.iobox/ directory structure if it doesn't already exist."""
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)


# ── TOML I/O ──────────────────────────────────────────────────────────────────


def load_space(name: str) -> SpaceConfig:
    """Load a space config from ~/.iobox/workspaces/{name}.toml.

    Raises:
        ValueError: If *name* is not a valid workspace name or the file is
            malformed (missing keys, unknown ``service`` or ``mode``).
        FileNotFoundError: If the space does not exist.
    """
    validate_space_name(name)
    path = WORKSPACES_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"Space '{name}' not found at {path}")
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: invalid TOML: {exc}") from exc
    config = _parse_space_config(data, source=str(path))
    # The file name is authoritative: a copied or renamed file must save back
    # to itself, not to whatever ``[workspace] name`` it still contains.
    config.name = name
    return config


def save_space(config: SpaceConfig) -> None:
    """Write a space config to ~/.iobox/workspaces/{name}.toml."""
    validate_space_name(config.name)
    ensure_iobox_home()
    path = WORKSPACES_DIR / f"{config.name}.toml"
    _atomic_write_text(path, _serialize_space_config(config))


def list_spaces() -> list[str]:
    """Return sorted list of space names (stems of .toml files)."""
    if not WORKSPACES_DIR.exists():
        return []
    return sorted(p.stem for p in WORKSPACES_DIR.glob("*.toml") if _SPACE_NAME_RE.fullmatch(p.stem))


# ── Active space ──────────────────────────────────────────────────────────────


def get_active_space() -> str | None:
    """Return the active space name, or None if not set.

    Also returns None (and logs a warning) when the active-space file names a
    space that is invalid or no longer exists, so callers can prompt the user
    instead of crashing on ``load_space``.
    """
    if not ACTIVE_SPACE_FILE.exists():
        return None
    name = ACTIVE_SPACE_FILE.read_text().strip()
    if not name:
        return None
    if not _SPACE_NAME_RE.fullmatch(name):
        logger.warning("Ignoring invalid active space name %r in %s", name, ACTIVE_SPACE_FILE)
        return None
    if not (WORKSPACES_DIR / f"{name}.toml").exists():
        logger.warning(
            "Active space '%s' no longer exists; run `iobox space use NAME` to pick another.",
            name,
        )
        return None
    return name


def set_active_space(name: str) -> None:
    """Persist the active space name to ~/.iobox/active_space."""
    validate_space_name(name)
    ensure_iobox_home()
    _atomic_write_text(ACTIVE_SPACE_FILE, name)


# ── Token-file probes ─────────────────────────────────────────────────────────


def token_file_for(entry: ServiceEntry) -> Path:
    """Return the canonical token-file path for a service session.

    The auth flow writes here on successful OAuth; the file's existence is
    treated as the source of truth for "is this session authenticated".
    """
    base = IOBOX_HOME / "tokens" / validate_account(entry.account)
    if entry.service == "google":
        tier = "readonly" if entry.mode == "readonly" else "standard"
        return base / f"token_{tier}.json"
    if entry.service == "o365":
        tier = "readonly" if entry.mode == "readonly" else "standard"
        return base / f"microsoft_token_{tier}.txt"
    return base / "unknown"


def is_authenticated(entry: ServiceEntry) -> bool:
    """Whether a token file exists on disk for this service session.

    For Google in ``readonly`` mode, a broader ``standard``-tier token also
    counts (matches ``GoogleAuth._resolve_token``'s fallback). For O365 in
    ``standard``/``dangerous`` mode, the pre-tier ``microsoft_token.txt`` and
    ``o365_token.txt`` files also count — ``MicrosoftAuth`` migrates them into
    the standard tier on first use (readonly never inherits a write token).
    """
    path = token_file_for(entry)
    if path.exists():
        return True
    if entry.service == "google" and entry.mode == "readonly":
        broader = path.parent / "token_standard.json"
        if broader.exists():
            return True
    if entry.service == "o365" and entry.mode != "readonly":
        for legacy in ("microsoft_token.txt", "o365_token.txt"):
            if (path.parent / legacy).exists():
                return True
    return False


# ── Session JSON I/O ──────────────────────────────────────────────────────────


def load_session(name: str) -> SpaceSession:
    """Load session state from ~/.iobox/workspaces/{name}.session.json."""
    validate_space_name(name)
    path = WORKSPACES_DIR / f"{name}.session.json"
    if not path.exists():
        return SpaceSession(workspace=name)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.warning("Ignoring corrupt session file %s: %s", path, exc)
        return SpaceSession(workspace=name)
    return _parse_session(data)


def save_session(session: SpaceSession) -> None:
    """Write session state to ~/.iobox/workspaces/{name}.session.json."""
    validate_space_name(session.workspace)
    ensure_iobox_home()
    path = WORKSPACES_DIR / f"{session.workspace}.session.json"
    _atomic_write_text(path, json.dumps(_serialize_session(session), indent=2))


# ── Internal parse/serialize ──────────────────────────────────────────────────


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically (temp file in the same dir + ``os.replace``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _require(table: Any, key: str, source: str, where: str) -> Any:
    """Return ``table[key]`` or raise ValueError naming the missing key and file."""
    if not isinstance(table, dict) or key not in table:
        raise ValueError(f"{source}: missing required key '{key}' in {where}")
    return table[key]


_SERVICE_MIGRATION = {"gmail": "google", "outlook": "o365"}


def _parse_space_config(data: dict, source: str = "<config>") -> SpaceConfig:  # type: ignore[type-arg]
    """Build a SpaceConfig from parsed TOML, validating service and mode values."""
    workspace = _require(data, "workspace", source, "the file")
    name = str(_require(workspace, "name", source, "[workspace]"))
    services = []
    for i, s in enumerate(data.get("services", []), start=1):
        where = f"[[services]] entry #{i}"
        raw_scopes = _require(s, "scopes", source, where)
        raw_service = str(_require(s, "service", source, where))
        account = _require(s, "account", source, where)
        number = _require(s, "number", source, where)
        # Migrate legacy scope value "messages" → "email"
        scopes = ["email" if sc == "messages" else sc for sc in raw_scopes]
        # Migrate legacy service type names: "gmail" → "google", "outlook" → "o365"
        service_type = _SERVICE_MIGRATION.get(raw_service, raw_service)
        if service_type not in VALID_SERVICES:
            raise ValueError(
                f"{source}: invalid service {raw_service!r} "
                f"(expected one of: {', '.join(sorted(VALID_SERVICES))})"
            )
        mode = s.get("mode", "standard")
        if mode not in VALID_MODES:
            raise ValueError(
                f"{source}: invalid mode {mode!r} for account {s.get('account')!r} "
                f"(expected one of: {', '.join(sorted(VALID_MODES))})"
            )
        try:
            entry = ServiceEntry(
                number=number,
                service=service_type,  # type: ignore[arg-type]
                account=account,
                scopes=scopes,
                mode=mode,  # type: ignore[arg-type]
                slug=s.get("slug", ""),
                id=s.get("id", ""),
            )
        except ValueError as exc:
            raise ValueError(f"{source}: {exc}") from exc
        services.append(entry)
    return SpaceConfig(name=name, services=services)


def _serialize_space_config(config: SpaceConfig) -> str:
    data: dict = {"workspace": {"name": config.name}, "services": []}  # type: ignore[type-arg]
    for svc in config.services:
        data["services"].append(
            {
                "number": svc.number,
                "id": svc.id,
                "slug": svc.slug,
                "service": svc.service,
                "account": svc.account,
                "scopes": svc.scopes,
                "mode": svc.mode,
            }
        )
    return tomli_w.dumps(data)  # type: ignore[no-any-return]


def _parse_session(data: dict) -> SpaceSession:  # type: ignore[type-arg]
    services = {}
    for svc_id, s in data.get("services", {}).items():
        services[svc_id] = ServiceSessionState(
            authenticated=s.get("authenticated", False),
            scopes=list(s.get("scopes", [])),
            token_path=s.get("token_path", ""),
            last_sync=s.get("last_sync"),
            error=s.get("error"),
        )
    return SpaceSession(
        workspace=data.get("workspace", ""),
        updated_at=data.get("updated_at", ""),
        services=services,
    )


def _serialize_session(session: SpaceSession) -> dict:  # type: ignore[type-arg]
    return {
        "workspace": session.workspace,
        "updated_at": session.updated_at,
        "services": {
            svc_id: {
                "authenticated": state.authenticated,
                "scopes": state.scopes,
                "token_path": state.token_path,
                "last_sync": state.last_sync,
                "error": state.error,
            }
            for svc_id, state in session.services.items()
        },
    }
