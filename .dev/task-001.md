---
id: task-001
title: "Space config schema + directory structure"
milestone: 0
status: done
priority: p0
depends_on: []
blocks: [task-007]
parallel_with: [task-002, task-003]
estimated_effort: M
research_needed: false
research_questions: []
assigned_to: null
---

## Context

The Workspace expansion requires a persistent, user-level config location. Currently iobox uses env vars and per-project credential files. For multi-account, multi-service workspaces, we need a structured home directory (`~/.iobox/`) with TOML config files per space, JSON session state, and token subdirectories.

This task creates the config schema and I/O layer only — no Workspace class, no provider instantiation. Those come in task-007.

## Scope

**Does:**
- Define `~/.iobox/` directory structure
- Define TOML schema for space config (services, accounts, scopes, mode, slug)
- Define session JSON schema (per-service auth state, last_sync, error)
- Implement `src/iobox/space_config.py` with dataclasses and I/O functions
- Track active space in `~/.iobox/active_space`

**Does NOT:**
- Implement Workspace class (task-007)
- Trigger OAuth flows (task-003/004)
- Implement provider instantiation from config
- Migrate existing token files to new paths

## Strategic Fit

Every other task in Wave 2 and beyond needs a place to read/write workspace config. This is pure infrastructure with no external deps — ideal to run first in parallel with task-002 and task-003.

## Architecture Notes

- Use Python `tomllib` (stdlib, Python 3.11+) for reading; `tomli-w` or manual TOML writing for writing
- `~/.iobox/` is always the config home — not `CREDENTIALS_DIR` (which is a legacy env var for the old per-project token storage)
- `active_space` is a plain text file containing just the space name (no JSON, easy to `cat`)
- Session JSON is separate from TOML config — config is user-edited, session is machine-written
- `SpaceConfig` and `ServiceSession` are dataclasses, not TypedDicts — they have behavior (validation, serialization)

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/space_config.py` | All dataclasses and I/O functions |
| Create | `tests/unit/test_space_config.py` | Unit tests using tmp_path fixture |

## Directory Structure

```
~/.iobox/
  workspaces/
    personal.toml           # space config (user-editable)
    personal.session.json   # machine-written session state
    work.toml
    work.session.json
  tokens/
    tim@gmail.com/
      token_readonly.json
      token_standard.json
    corp@company.com/
      microsoft_token.txt
  indexes/                  # future: embeddings (task-016)
    personal/
      index.db
  active_space              # plain text: "personal"
```

## TOML Schema

```toml
# ~/.iobox/workspaces/personal.toml
[workspace]
name = "personal"

[[services]]
number = 1
id = "gmail-timgmailcom"      # auto-derived from account email
slug = "tim-personal"          # user-visible shortname (can be set explicitly)
service = "gmail"
account = "tim@gmail.com"
scopes = ["messages", "calendar", "drive"]
mode = "readonly"

[[services]]
number = 2
id = "gmail-timworkcom"
slug = "tim-work"
service = "gmail"
account = "tim@work.com"
scopes = ["messages"]
mode = "standard"

[[services]]
number = 3
id = "outlook-corpmegacorpcom"
slug = "corp"
service = "outlook"
account = "corp@megacorp.com"
scopes = ["messages", "calendar"]
mode = "readonly"
```

## Session JSON Schema

```json
// ~/.iobox/workspaces/personal.session.json
{
  "workspace": "personal",
  "updated_at": "2026-03-13T10:00:00Z",
  "services": {
    "gmail-timgmailcom": {
      "authenticated": true,
      "scopes": ["messages", "calendar", "drive"],
      "token_path": "~/.iobox/tokens/tim@gmail.com/token_readonly.json",
      "last_sync": "2026-03-13T09:55:00Z",
      "error": null
    },
    "outlook-corpmegacorpcom": {
      "authenticated": false,
      "scopes": ["messages", "calendar"],
      "token_path": "~/.iobox/tokens/corp@megacorp.com/microsoft_token.txt",
      "last_sync": null,
      "error": "TokenExpiredError: token expired at 2026-02-01"
    }
  }
}
```

## Implementation Guide

### Step 1 — Define dataclasses

```python
# src/iobox/space_config.py
from __future__ import annotations
import json
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

IOBOX_HOME = Path.home() / ".iobox"
WORKSPACES_DIR = IOBOX_HOME / "workspaces"
TOKENS_DIR = IOBOX_HOME / "tokens"
INDEXES_DIR = IOBOX_HOME / "indexes"
ACTIVE_SPACE_FILE = IOBOX_HOME / "active_space"

@dataclass
class ServiceEntry:
    number: int
    service: Literal["gmail", "outlook"]
    account: str
    scopes: list[str]           # ["messages", "calendar", "drive"]
    mode: Literal["readonly", "standard", "dangerous"] = "standard"
    slug: str = ""              # auto-derived if empty
    id: str = ""                # auto-derived if empty

    def __post_init__(self):
        if not self.id:
            self.id = _derive_id(self.service, self.account)
        if not self.slug:
            self.slug = _derive_slug(self.account)

@dataclass
class SpaceConfig:
    name: str
    services: list[ServiceEntry] = field(default_factory=list)

@dataclass
class ServiceSessionState:
    authenticated: bool = False
    scopes: list[str] = field(default_factory=list)
    token_path: str = ""
    last_sync: str | None = None
    error: str | None = None

@dataclass
class SpaceSession:
    workspace: str
    updated_at: str = ""
    services: dict[str, ServiceSessionState] = field(default_factory=dict)
```

### Step 2 — Derive helpers

```python
def _derive_id(service: str, account: str) -> str:
    """gmail + tim@gmail.com → gmail-timgmailcom"""
    clean = account.replace("@", "").replace(".", "").lower()
    return f"{service}-{clean}"

def _derive_slug(account: str) -> str:
    """tim@gmail.com → tim-gmail"""
    local, domain = account.split("@", 1)
    domain_part = domain.split(".")[0]  # gmail, outlook, megacorp
    return f"{local}-{domain_part}".lower()
```

### Step 3 — I/O functions

```python
def ensure_iobox_home() -> None:
    """Create ~/.iobox/ directory structure if it doesn't exist."""
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)

def load_space(name: str) -> SpaceConfig:
    """Load space config from ~/.iobox/workspaces/{name}.toml"""
    path = WORKSPACES_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"Space '{name}' not found at {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return _parse_space_config(data)

def save_space(config: SpaceConfig) -> None:
    """Write space config to ~/.iobox/workspaces/{name}.toml"""
    ensure_iobox_home()
    path = WORKSPACES_DIR / f"{config.name}.toml"
    path.write_text(_serialize_space_config(config))

def list_spaces() -> list[str]:
    """Return sorted list of space names from ~/.iobox/workspaces/"""
    if not WORKSPACES_DIR.exists():
        return []
    return sorted(p.stem for p in WORKSPACES_DIR.glob("*.toml"))

def get_active_space() -> str | None:
    """Return name of active space, or None if not set."""
    if not ACTIVE_SPACE_FILE.exists():
        return None
    name = ACTIVE_SPACE_FILE.read_text().strip()
    return name or None

def set_active_space(name: str) -> None:
    """Set active space name in ~/.iobox/active_space"""
    ensure_iobox_home()
    ACTIVE_SPACE_FILE.write_text(name)

def load_session(name: str) -> SpaceSession:
    """Load session state from ~/.iobox/workspaces/{name}.session.json"""
    path = WORKSPACES_DIR / f"{name}.session.json"
    if not path.exists():
        return SpaceSession(workspace=name)
    with open(path) as f:
        data = json.load(f)
    return _parse_session(data)

def save_session(session: SpaceSession) -> None:
    """Write session state to ~/.iobox/workspaces/{name}.session.json"""
    ensure_iobox_home()
    path = WORKSPACES_DIR / f"{session.workspace}.session.json"
    path.write_text(json.dumps(_serialize_session(session), indent=2))
```

### Step 4 — TOML serialization

Use `tomli-w` if available, otherwise generate TOML manually. Add `tomli-w` as a dependency in `pyproject.toml`.

```python
def _serialize_space_config(config: SpaceConfig) -> str:
    import tomli_w
    data: dict = {"workspace": {"name": config.name}, "services": []}
    for svc in config.services:
        data["services"].append({
            "number": svc.number,
            "id": svc.id,
            "slug": svc.slug,
            "service": svc.service,
            "account": svc.account,
            "scopes": svc.scopes,
            "mode": svc.mode,
        })
    return tomli_w.dumps(data)
```

### Step 5 — Parse helpers

```python
def _parse_space_config(data: dict) -> SpaceConfig:
    name = data["workspace"]["name"]
    services = []
    for s in data.get("services", []):
        services.append(ServiceEntry(
            number=s["number"],
            service=s["service"],
            account=s["account"],
            scopes=s["scopes"],
            mode=s.get("mode", "standard"),
            slug=s.get("slug", ""),
            id=s.get("id", ""),
        ))
    return SpaceConfig(name=name, services=services)
```

### Step 6 — Add `tomli-w` dependency

In `pyproject.toml`, add to `[project.dependencies]`:
```
"tomli-w>=1.0",
```

## Key Decisions

**Q: Should `slug` be user-overridable in TOML?**
Yes — `space add` derives it automatically, but power users editing TOML directly can set a custom slug. The field is always written to TOML so it's stable.

**Q: Should `id` be stable across renames?**
Yes — `id` is auto-derived from `service + account` and never changes. `slug` and `number` are user-facing references. Internal cross-session references use `id`.

**Q: What Python version for `tomllib`?**
`tomllib` is in stdlib since Python 3.11. If we need 3.10 support, fall back to `tomli` (third-party). Check `pyproject.toml` for current `requires-python`.

## Test Strategy

Use `pytest` with `tmp_path` fixture to avoid touching real `~/.iobox/`.

```python
# tests/unit/test_space_config.py
import pytest
from iobox.space_config import SpaceConfig, ServiceEntry, save_space, load_space, ...

@pytest.fixture(autouse=True)
def isolated_iobox_home(tmp_path, monkeypatch):
    monkeypatch.setattr("iobox.space_config.IOBOX_HOME", tmp_path / ".iobox")
    monkeypatch.setattr("iobox.space_config.WORKSPACES_DIR", tmp_path / ".iobox" / "workspaces")
    # etc.

class TestSpaceConfig:
    def test_save_and_load_roundtrip(self, isolated_iobox_home): ...
    def test_derive_id(self): ...
    def test_derive_slug(self): ...
    def test_list_spaces_empty(self): ...
    def test_list_spaces_returns_sorted(self): ...

class TestActiveSpace:
    def test_get_active_space_none_when_no_file(self): ...
    def test_set_and_get_active_space(self): ...

class TestSessionIO:
    def test_load_session_default_when_missing(self): ...
    def test_save_and_load_session_roundtrip(self): ...
```

## Verification

```bash
make test  # all unit tests pass
python -c "from iobox.space_config import ensure_iobox_home, save_space, load_space, SpaceConfig, ServiceEntry"
```

## Acceptance Criteria

- [ ] `~/.iobox/` directory structure documented in code and matches the schema above
- [ ] `SpaceConfig`, `ServiceEntry`, `SpaceSession`, `ServiceSessionState` dataclasses defined
- [ ] `load_space()`, `save_space()`, `list_spaces()` work correctly with TOML
- [ ] `get_active_space()`, `set_active_space()` work with plain text file
- [ ] `load_session()`, `save_session()` work with JSON
- [ ] `ensure_iobox_home()` creates all subdirs idempotently
- [ ] `_derive_id()` and `_derive_slug()` produce stable, correct values
- [ ] `tomli-w` added to dependencies
- [ ] All unit tests pass with `make test`
- [ ] No changes to existing token storage paths (backward compat preserved)
