---
id: task-004
title: "iobox space command group"
milestone: 0
status: done
priority: p0
depends_on: [task-001, task-003]
blocks: []
parallel_with: [task-005, task-006, task-007, task-008]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Users need a way to create and manage spaces (named collections of service sessions) without hand-editing TOML files. The `iobox space` command group is the primary management surface: create spaces, add service sessions, check auth status, and re-auth individual sessions.

This is the first user-visible piece of the Workspace expansion. After this task, a user can run `iobox space create personal && iobox space add gmail tim@gmail.com --messages --calendar --drive --read` to set up a fully authenticated space.

## Scope

**Does:**
- New `space` Typer subcommand group in `cli.py`
- `space create NAME`
- `space list`
- `space use NAME`
- `space status` (rich table output)
- `space add SERVICE ACCOUNT [--messages] [--calendar] [--drive] [--read]`
- `space login N|ID|SLUG`
- `space logout N|ID|SLUG`
- `space remove N|ID|SLUG`
- Keep `iobox auth-status` for backward compat (delegates to `space status`)

**Does NOT:**
- Implement Workspace class (task-007)
- Implement cross-provider search
- Change existing top-level commands
- Implement calendar/file CLI commands (task-010)
- Implement `MicrosoftAuth` shared object (task-014)

## Strategic Fit

The `space` command group is the entry point for all new Workspace functionality. Without it, users can't configure spaces, and every downstream task (005–011) needs a usable space to test against.

## Architecture Notes

- `space` is a Typer app added to the main CLI app: `app.add_typer(space_app, name="space")`
- Auth triggers happen at `space add` time — call `GoogleAuth.get_credentials()` or Outlook equivalent immediately
- Slot resolution (by number, id, or slug) is a shared helper: `resolve_slot(config, ref) -> ServiceEntry`
- `space status` uses `rich.Table` for clean output — already a dependency
- For OAuth during `space add`, reuse `GoogleAuth` from task-003
- The `--read` flag in `space add` sets mode to `readonly`; without it, default is `standard`
- **Critical**: Google OAuth is all-or-nothing per account — requesting calendar scope for an existing mail-only token requires a fresh OAuth flow for all scopes combined

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/cli.py` | Add `space_app` Typer group with all subcommands |
| Create | `tests/unit/test_cli_space.py` | Unit tests for space commands |

## CLI Design

```bash
# Create a new space
$ iobox space create personal
Created space 'personal'. Use `iobox space add` to add service sessions.

# List spaces
$ iobox space list
  personal  (active)
  work

# Switch active space
$ iobox space use work
Active space set to 'work'.

# Add a Gmail service session (triggers OAuth immediately)
$ iobox space add gmail tim@gmail.com --messages --calendar --drive --read
Opening browser for OAuth... (scopes: gmail.readonly, calendar.readonly, drive.readonly)
Added service session #1 (gmail/tim@gmail.com) — authenticated ✓
  id:   gmail-timgmailcom
  slug: tim-gmail
  mode: readonly
  scopes: messages, calendar, drive

# Add Outlook (no drive scope, valid)
$ iobox space add outlook corp@company.com --messages --calendar --read
Added service session #2 (outlook/corp@company.com) — authenticated ✓

# Show status table
$ iobox space status
Space: personal (active)
#  service   account               scopes                    mode      status
1  gmail     tim@gmail.com         messages,calendar,drive   readonly  ✓ authenticated
2  outlook   corp@company.com      messages,calendar         readonly  ✗ token expired

# Re-authenticate by number, id, or slug
$ iobox space login 2
$ iobox space login corp
$ iobox space login outlook-corpmegacorpcom

# Revoke token (keep config)
$ iobox space logout 1

# Remove slot entirely
$ iobox space remove 2
Remove service session #2 (outlook/corp@company.com)? [y/N] y
Removed.
```

## Validation Rules

- `iobox space add outlook TIM@GMAIL.COM --drive` → error: "Drive is not supported for Outlook service sessions"
- `iobox space add BADSERVICE ...` → error: "Unknown service 'badservice'. Must be 'gmail' or 'outlook'."
- `iobox space add gmail tim@gmail.com` (no scope flags) → error: "Specify at least one scope: --messages, --calendar, --drive"
- `iobox space use NONEXISTENT` → error: "Space 'nonexistent' not found. Available: personal, work"
- `iobox space login 5` (no slot #5) → error: "No service session #5. Space has 2 sessions."

## Implementation Guide

### Step 1 — Read current cli.py

Read `src/iobox/cli.py` fully before making changes. Note how existing command groups are structured, how the main `app` is defined, and where `auth-status` lives.

### Step 2 — Create space_app Typer group

```python
# In cli.py
import typer
from iobox.space_config import (
    SpaceConfig, ServiceEntry, save_space, load_space,
    list_spaces, get_active_space, set_active_space,
    load_session, save_session, WORKSPACES_DIR
)
from iobox.providers.google_auth import GoogleAuth
from iobox.modes import get_google_scopes, _tier_for_mode

space_app = typer.Typer(help="Manage iobox spaces and service sessions.")
app.add_typer(space_app, name="space")
```

### Step 3 — Implement `space create`

```python
@space_app.command("create")
def space_create(name: str = typer.Argument(..., help="Space name")):
    if name in list_spaces():
        typer.echo(f"Space '{name}' already exists.", err=True)
        raise typer.Exit(1)
    config = SpaceConfig(name=name, services=[])
    save_space(config)
    if get_active_space() is None:
        set_active_space(name)
        typer.echo(f"Created space '{name}' and set as active.")
    else:
        typer.echo(f"Created space '{name}'. Use `iobox space use {name}` to switch.")
```

### Step 4 — Implement `space add`

```python
@space_app.command("add")
def space_add(
    service: str = typer.Argument(...),
    account: str = typer.Argument(...),
    messages: bool = typer.Option(False, "--messages"),
    calendar: bool = typer.Option(False, "--calendar"),
    drive: bool = typer.Option(False, "--drive"),
    read: bool = typer.Option(False, "--read", help="Use readonly mode"),
):
    # Validate service
    service = service.lower()
    if service not in ("gmail", "outlook"):
        typer.echo(f"Unknown service '{service}'. Must be 'gmail' or 'outlook'.", err=True)
        raise typer.Exit(1)

    # Validate scopes
    scopes = []
    if messages: scopes.append("messages")
    if calendar: scopes.append("calendar")
    if drive: scopes.append("drive")
    if not scopes:
        typer.echo("Specify at least one scope: --messages, --calendar, --drive", err=True)
        raise typer.Exit(1)

    if drive and service == "outlook":
        typer.echo("Drive is not supported for Outlook. Use OneDrive scope (--drive) only with Gmail.", err=True)
        raise typer.Exit(1)

    # Load active space
    active = get_active_space()
    if not active:
        typer.echo("No active space. Run `iobox space create NAME` first.", err=True)
        raise typer.Exit(1)
    config = load_space(active)

    # Build service entry
    mode = "readonly" if read else "standard"
    number = max((s.number for s in config.services), default=0) + 1
    entry = ServiceEntry(number=number, service=service, account=account, scopes=scopes, mode=mode)

    # Trigger OAuth
    typer.echo(f"Opening browser for OAuth...")
    _authenticate_service_entry(entry)

    config.services.append(entry)
    save_space(config)
    typer.echo(f"Added service session #{number} ({service}/{account}) — authenticated ✓")
    typer.echo(f"  id:     {entry.id}")
    typer.echo(f"  slug:   {entry.slug}")
    typer.echo(f"  mode:   {mode}")
    typer.echo(f"  scopes: {', '.join(scopes)}")
```

### Step 5 — Auth helper

```python
def _authenticate_service_entry(entry: ServiceEntry) -> None:
    """Trigger OAuth for a service entry. Raises on failure."""
    from iobox.space_config import TOKENS_DIR
    creds_dir = str(TOKENS_DIR.parent)  # ~/.iobox/

    if entry.service == "gmail":
        from iobox.modes import get_google_scopes, _tier_for_mode
        scopes = get_google_scopes(entry.scopes, entry.mode)
        tier = _tier_for_mode(entry.mode)
        auth = GoogleAuth(
            account=entry.account,
            scopes=scopes,
            credentials_dir=creds_dir,
            tier=tier,
        )
        auth.get_credentials()  # triggers flow if needed
    elif entry.service == "outlook":
        from iobox.providers.outlook_auth import OutlookAuth
        auth = OutlookAuth(account=entry.account, credentials_dir=creds_dir)
        auth.authenticate()
```

### Step 6 — Implement `space status`

```python
@space_app.command("status")
def space_status():
    from rich.table import Table
    from rich.console import Console

    active = get_active_space()
    if not active:
        typer.echo("No active space.")
        return
    config = load_space(active)
    session = load_session(active)

    console = Console()
    table = Table(title=f"Space: {active} (active)")
    table.add_column("#", style="dim")
    table.add_column("Service")
    table.add_column("Account")
    table.add_column("Scopes")
    table.add_column("Mode")
    table.add_column("Status")

    for svc in config.services:
        state = session.services.get(svc.id)
        if state and state.authenticated:
            status = "✓ authenticated"
        elif state and state.error:
            status = f"✗ {state.error[:30]}"
        else:
            status = "✗ not authenticated"
        table.add_row(
            str(svc.number),
            svc.service,
            svc.account,
            ",".join(svc.scopes),
            svc.mode,
            status,
        )
    console.print(table)
```

### Step 7 — Implement slot resolution helper

```python
def _resolve_slot(config: SpaceConfig, ref: str) -> ServiceEntry:
    """Resolve a slot by number string, id, or slug. Raises typer.Exit on failure."""
    # Try number
    if ref.isdigit():
        n = int(ref)
        for s in config.services:
            if s.number == n:
                return s
        typer.echo(f"No service session #{n}. Space has {len(config.services)} sessions.", err=True)
        raise typer.Exit(1)
    # Try id then slug
    for s in config.services:
        if s.id == ref or s.slug == ref:
            return s
    typer.echo(f"No service session matching '{ref}'.", err=True)
    raise typer.Exit(1)
```

### Step 8 — Implement login/logout/remove

Follow the pattern above. `login` calls `_authenticate_service_entry()`. `logout` deletes the token file and updates session state. `remove` prompts for confirmation, removes from config.

### Step 9 — Update auth-status

```python
@app.command("auth-status")
def auth_status():
    """[Deprecated] Use `iobox space status` instead."""
    typer.echo("Note: `auth-status` is deprecated. Use `iobox space status`.")
    space_status()
```

## Key Decisions

**Q: Should `space add` fail if OAuth fails?**
Yes — the slot should NOT be saved to TOML if OAuth fails. The user needs to re-run `space add` after fixing the issue.

**Q: What credentials file does `space add gmail` use for OAuth?**
It uses `GoogleAuth` from task-003, which reads `GOOGLE_APPLICATION_CREDENTIALS` env var or falls back to `credentials.json` in cwd. This is the existing behavior — no change needed here.

**Q: Should `space status` check token validity or just read session JSON?**
Read session JSON only — don't trigger token refresh during status. Users can run `space login` to refresh.

**Q: How to handle `space add` when the account already has a token with fewer scopes?**
Google requires re-auth with the full scope set. If a token exists but has fewer scopes, `GoogleAuth` will detect scope mismatch and trigger a new OAuth flow. This is by design.

## Test Strategy

```python
# tests/unit/test_cli_space.py
from typer.testing import CliRunner
from iobox.cli import app

runner = CliRunner()

class TestSpaceCreate:
    def test_create_new_space(self, tmp_path, monkeypatch): ...
    def test_create_sets_active_when_first(self, tmp_path, monkeypatch): ...
    def test_create_duplicate_fails(self, tmp_path, monkeypatch): ...

class TestSpaceAdd:
    def test_add_gmail_messages_only(self, tmp_path, monkeypatch, mock_google_auth): ...
    def test_add_outlook_with_drive_fails(self, tmp_path, monkeypatch): ...
    def test_add_no_scopes_fails(self, tmp_path, monkeypatch): ...
    def test_add_unknown_service_fails(self, tmp_path, monkeypatch): ...

class TestSpaceStatus:
    def test_status_shows_table(self, tmp_path, monkeypatch): ...
    def test_status_no_active_space(self, tmp_path, monkeypatch): ...

class TestSlotResolution:
    def test_resolve_by_number(self): ...
    def test_resolve_by_id(self): ...
    def test_resolve_by_slug(self): ...
    def test_resolve_missing_raises(self): ...
```

Mock `GoogleAuth.get_credentials()` and `OutlookAuth.authenticate()` in tests — don't trigger real OAuth.

## Verification

```bash
make test
iobox space --help
iobox space create test-space
iobox space list
iobox space status
```

## Acceptance Criteria

- [ ] `iobox space create NAME` creates TOML, sets as active if first
- [ ] `iobox space list` shows spaces with active marker
- [ ] `iobox space use NAME` updates `active_space` file
- [ ] `iobox space add gmail ACCOUNT --messages --calendar [--read]` triggers OAuth and saves slot
- [ ] `iobox space add outlook ACCOUNT --drive` fails with clear error
- [ ] `iobox space status` shows rich table with auth state
- [ ] `iobox space login N|ID|SLUG` re-triggers OAuth
- [ ] `iobox space logout N|ID|SLUG` deletes token, marks unauthenticated
- [ ] `iobox space remove N|ID|SLUG` prompts confirm, removes from TOML
- [ ] `iobox auth-status` shows deprecation note, delegates to space status
- [ ] All validation errors have clear human-readable messages
- [ ] All unit tests pass
