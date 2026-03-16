"""
Space configuration — schema, I/O, and path constants for ~/.iobox/.

A *space* is a named collection of service sessions (gmail, outlook) that
form a user's workspace. This module owns the TOML config schema and the
JSON session-state schema, but knows nothing about providers or OAuth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# tomllib is stdlib on Python 3.11+; fall back to tomli on 3.10.
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[import-not-found,no-reuse-imports]
    except ImportError as exc:
        raise ImportError("Python < 3.11 requires the 'tomli' package: pip install tomli") from exc

import tomli_w  # for writing TOML

# ── Path constants (module-level so tests can monkeypatch) ────────────────────

IOBOX_HOME: Path = Path.home() / ".iobox"
WORKSPACES_DIR: Path = IOBOX_HOME / "workspaces"
TOKENS_DIR: Path = IOBOX_HOME / "tokens"
INDEXES_DIR: Path = IOBOX_HOME / "indexes"
ACTIVE_SPACE_FILE: Path = IOBOX_HOME / "active_space"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class ServiceEntry:
    """One service session within a space (e.g. gmail/tim@gmail.com)."""

    number: int
    service: Literal["gmail", "outlook"]
    account: str
    scopes: list[str]  # ["messages", "calendar", "drive"]
    mode: Literal["readonly", "standard", "dangerous"] = "standard"
    slug: str = ""  # auto-derived from account if empty
    id: str = ""  # auto-derived from service+account if empty

    def __post_init__(self) -> None:
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


# ── Directory management ──────────────────────────────────────────────────────


def ensure_iobox_home() -> None:
    """Create ~/.iobox/ directory structure if it doesn't already exist."""
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)


# ── TOML I/O ──────────────────────────────────────────────────────────────────


def load_space(name: str) -> SpaceConfig:
    """Load a space config from ~/.iobox/workspaces/{name}.toml."""
    path = WORKSPACES_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"Space '{name}' not found at {path}")
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return _parse_space_config(data)


def save_space(config: SpaceConfig) -> None:
    """Write a space config to ~/.iobox/workspaces/{name}.toml."""
    ensure_iobox_home()
    path = WORKSPACES_DIR / f"{config.name}.toml"
    path.write_text(_serialize_space_config(config))


def list_spaces() -> list[str]:
    """Return sorted list of space names (stems of .toml files)."""
    if not WORKSPACES_DIR.exists():
        return []
    return sorted(p.stem for p in WORKSPACES_DIR.glob("*.toml"))


# ── Active space ──────────────────────────────────────────────────────────────


def get_active_space() -> str | None:
    """Return the active space name, or None if not set."""
    if not ACTIVE_SPACE_FILE.exists():
        return None
    name = ACTIVE_SPACE_FILE.read_text().strip()
    return name or None


def set_active_space(name: str) -> None:
    """Persist the active space name to ~/.iobox/active_space."""
    ensure_iobox_home()
    ACTIVE_SPACE_FILE.write_text(name)


# ── Session JSON I/O ──────────────────────────────────────────────────────────


def load_session(name: str) -> SpaceSession:
    """Load session state from ~/.iobox/workspaces/{name}.session.json."""
    path = WORKSPACES_DIR / f"{name}.session.json"
    if not path.exists():
        return SpaceSession(workspace=name)
    with open(path) as fh:
        data = json.load(fh)
    return _parse_session(data)


def save_session(session: SpaceSession) -> None:
    """Write session state to ~/.iobox/workspaces/{name}.session.json."""
    ensure_iobox_home()
    path = WORKSPACES_DIR / f"{session.workspace}.session.json"
    path.write_text(json.dumps(_serialize_session(session), indent=2))


# ── Internal parse/serialize ──────────────────────────────────────────────────


def _parse_space_config(data: dict) -> SpaceConfig:  # type: ignore[type-arg]
    name = data["workspace"]["name"]
    services = []
    for s in data.get("services", []):
        services.append(
            ServiceEntry(
                number=s["number"],
                service=s["service"],
                account=s["account"],
                scopes=list(s["scopes"]),
                mode=s.get("mode", "standard"),
                slug=s.get("slug", ""),
                id=s.get("id", ""),
            )
        )
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
    return tomli_w.dumps(data)


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
