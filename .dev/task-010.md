---
id: task-010
title: "Workspace-centric CLI commands"
milestone: 1
status: done
priority: p1
depends_on: [task-007]
blocks: [task-017]
parallel_with: [task-011, task-014]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

After task-007 (Workspace) is complete, the CLI needs commands to exercise the new types. This task adds `iobox events`, `iobox files`, and `iobox workspace` command groups, and connects them to `Workspace.list_events()`, `Workspace.list_files()`, and `Workspace.search()`.

Existing top-level commands (`iobox search`, `iobox save`, etc.) are preserved and marked as deprecated.

## Scope

**Does:**
- Add `events` command group: `list`, `get`, `save`
- Add `files` command group: `list`, `get`, `save`
- Add `workspace` command group: `use`, `status`
- Add top-level `iobox search` cross-type command (replaces old email-only search in future)
- Connect all new commands through `Workspace.from_config()`
- Mark existing top-level commands (`iobox search`, `iobox save`) as deprecated in help text

**Does NOT:**
- Remove existing commands (backward compat)
- Implement `iobox messages` namespace (can follow later)
- Implement write ops for events/files (task-018, task-019)
- Update MCP server (task-011)

## Strategic Fit

This is the user-facing output of the entire PoC milestone. The demo script runs `iobox search "Q4 planning"` and gets back emails + events + files in one call.

## Architecture Notes

- CLI callback loads workspace via `_get_workspace()` helper — reads active space config, calls `Workspace.from_config()`
- `--workspace NAME` global option overrides active space for all workspace commands
- `--provider NAME` in subcommands refers to a slot name within the workspace, not a provider type
- Output: rich table for `list` commands, markdown text for `get`/`save`
- `save` commands write markdown files using `processing/markdown.py` converters
- Event `list` default: last 30 days unless `--after`/`--before` specified
- File `list` requires `--query` text (no blank file listing by default — too many results)

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/cli.py` | Add events_app, files_app, workspace_app Typer groups |
| Create | `tests/unit/test_cli_workspace_commands.py` | Unit tests |

## CLI Surface

```bash
# Cross-type workspace search
iobox search "Q4 planning" [--type message] [--type event] [--type file] [--max 20]

# Events
iobox events list [--after 2026-03-01] [--before 2026-03-31] [--provider gcal-personal] [--max 25]
iobox events get EVENT_ID [--provider gcal-personal]
iobox events save EVENT_ID -o ./events [--provider gcal-personal]

# Files
iobox files list --query "Q4 report" [--provider gdrive-personal] [--max 20]
iobox files get FILE_ID [--provider gdrive-personal]
iobox files save FILE_ID -o ./docs [--provider gdrive-personal]

# Workspace management (aliases for iobox space commands)
iobox workspace use personal
iobox workspace status
```

## Output Format: events list

```
Title                    Start                    End                      Provider
─────────────────────────────────────────────────────────────────────────────────────
Team standup             2026-03-15 09:00 PDT     2026-03-15 09:30 PDT     gcal-personal
Company all-hands        2026-03-15 14:00 PDT     2026-03-15 16:00 PDT     gcal-personal
Q4 planning session      2026-03-16 10:00 PDT     2026-03-16 12:00 PDT     gcal-work
```

## Output Format: files list

```
Name                         Modified              MIME                    Provider
────────────────────────────────────────────────────────────────────────────────────
Q4 Planning Notes            2026-03-10 15:00      application/vnd.g...    gdrive-personal
budget.pdf                   2026-02-15 11:00      application/pdf         gdrive-personal
```

## Implementation Guide

### Step 1 — Read current cli.py structure

Before modifying, read the whole `cli.py`. Note how `app` is defined, where `@app.callback` is, how existing command groups work.

### Step 2 — Add workspace loading helper

```python
# In cli.py
def _get_workspace(workspace_name: str | None = None) -> "Workspace":
    from iobox.workspace import Workspace
    from iobox.space_config import get_active_space, load_space, IOBOX_HOME

    name = workspace_name or get_active_space()
    if not name:
        typer.echo("No active space. Run `iobox space create NAME` first.", err=True)
        raise typer.Exit(1)

    config = load_space(name)
    return Workspace.from_config(config, credentials_dir=str(IOBOX_HOME))
```

### Step 3 — Add events command group

```python
events_app = typer.Typer(help="Calendar event operations.")
app.add_typer(events_app, name="events")

@events_app.command("list")
def events_list(
    after: str | None = typer.Option(None, "--after", help="Start date (YYYY-MM-DD)"),
    before: str | None = typer.Option(None, "--before", help="End date (YYYY-MM-DD)"),
    provider: str | None = typer.Option(None, "--provider", help="Slot name to query"),
    max_results: int = typer.Option(25, "--max", "-m"),
    workspace_name: str | None = typer.Option(None, "--workspace", "-w"),
):
    from iobox.providers.base import EventQuery
    from rich.table import Table
    from rich.console import Console

    ws = _get_workspace(workspace_name)
    query = EventQuery(after=after, before=before, max_results=max_results)
    providers = [provider] if provider else None
    events = ws.list_events(query, providers=providers)

    if not events:
        typer.echo("No events found.")
        return

    console = Console()
    table = Table()
    table.add_column("Title", max_width=40)
    table.add_column("Start")
    table.add_column("End")
    table.add_column("Provider", style="dim")

    for event in events:
        table.add_row(
            event["title"],
            _format_datetime(event["start"]),
            _format_datetime(event["end"]),
            event.get("provider_id", ""),
        )
    console.print(table)
```

### Step 4 — Add events get and save

```python
@events_app.command("get")
def events_get(
    event_id: str = typer.Argument(...),
    provider: str | None = typer.Option(None),
    workspace_name: str | None = typer.Option(None, "--workspace"),
):
    from iobox.processing.markdown import convert_event_to_markdown
    ws = _get_workspace(workspace_name)
    # Find the provider slot
    slot = _find_calendar_slot(ws, provider)
    event = slot.provider.get_event(event_id)
    typer.echo(convert_event_to_markdown(event))

@events_app.command("save")
def events_save(
    event_id: str = typer.Argument(...),
    output: str = typer.Option(".", "--output", "-o"),
    provider: str | None = typer.Option(None),
    workspace_name: str | None = typer.Option(None, "--workspace"),
):
    from pathlib import Path
    from iobox.processing.markdown import convert_event_to_markdown
    ws = _get_workspace(workspace_name)
    slot = _find_calendar_slot(ws, provider)
    event = slot.provider.get_event(event_id)
    md = convert_event_to_markdown(event)
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = _slugify(event["title"]) + ".md"
    (out_dir / filename).write_text(md)
    typer.echo(f"Saved to {out_dir / filename}")
```

### Step 5 — Add files command group (same pattern)

Follow the same pattern as events. `files list` requires `--query` (raise if not provided).

### Step 6 — Add workspace command group

```python
workspace_app = typer.Typer(help="Workspace management.")
app.add_typer(workspace_app, name="workspace")

@workspace_app.command("use")
def workspace_use(name: str = typer.Argument(...)):
    from iobox.space_config import set_active_space, list_spaces
    if name not in list_spaces():
        typer.echo(f"Space '{name}' not found. Available: {', '.join(list_spaces())}", err=True)
        raise typer.Exit(1)
    set_active_space(name)
    typer.echo(f"Active workspace set to '{name}'.")

@workspace_app.command("status")
def workspace_status(workspace_name: str | None = typer.Option(None)):
    # Delegate to space status
    from iobox.cli import space_status
    space_status()
```

### Step 7 — Update top-level iobox search to cross-type

```python
# Rename existing 'search' command or add --type flag
@app.command("search")
def search_cmd(
    query: str = typer.Option(..., "--query", "-q"),
    max_results: int = typer.Option(10, "--max", "-m"),
    type_filter: list[str] | None = typer.Option(None, "--type"),
    use_workspace: bool = typer.Option(False, "--workspace", help="Use active workspace for cross-type search"),
    # existing flags preserved:
    days: int | None = typer.Option(None, "--days", "-d"),
    provider_name: str | None = typer.Option(None, "--provider"),
    ...
):
    if use_workspace:
        ws = _get_workspace()
        results = ws.search(query, types=type_filter, max_results_per_type=max_results)
        _print_resource_table(results)
    else:
        # existing email-only search path unchanged
        ...
```

### Step 8 — Helper: datetime formatting

```python
def _format_datetime(iso_str: str | None) -> str:
    if not iso_str:
        return ""
    # Strip timezone for display, show date + time
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return iso_str[:16]  # truncate
```

## Key Decisions

**Q: Should `iobox events list` require `--after`/`--before`?**
Default to last 30 days (from today) if not specified. An unconstrained list of all events is too slow.

**Q: Should `iobox files list` require `--query`?**
Yes — listing all files with no filter is impractical. Raise a clear error: "Specify a search query with --query".

**Q: How to handle `--provider` in events/files when workspace has multiple calendar slots?**
If `--provider` is omitted, fan out to all slots. If specified, find the matching slot by name. If the named slot doesn't exist, raise with a helpful error.

**Q: Where does `_slugify` come from?**
Import from `src/iobox/utils.py` — already exists.

## Test Strategy

```python
# tests/unit/test_cli_workspace_commands.py
from typer.testing import CliRunner
from iobox.cli import app

runner = CliRunner()

class TestEventsListCommand:
    def test_events_list_basic(self, mock_workspace): ...
    def test_events_list_empty(self, mock_workspace): ...
    def test_events_list_provider_filter(self, mock_workspace): ...

class TestFilesListCommand:
    def test_files_list_requires_query(self, mock_workspace): ...
    def test_files_list_with_query(self, mock_workspace): ...

class TestWorkspaceSearch:
    def test_search_with_workspace_flag(self, mock_workspace): ...
    def test_search_type_filter(self, mock_workspace): ...
```

## Verification

```bash
make test
iobox events --help
iobox files --help
iobox workspace --help
iobox search --help
```

## Acceptance Criteria

- [ ] `iobox events list [--after] [--before] [--provider] [--max]` works
- [ ] `iobox events get EVENT_ID` prints markdown
- [ ] `iobox events save EVENT_ID -o ./dir` writes markdown file
- [ ] `iobox files list --query TEXT [--provider] [--max]` works
- [ ] `iobox files get FILE_ID` prints metadata
- [ ] `iobox files save FILE_ID -o ./dir` writes markdown file
- [ ] `iobox workspace use NAME` switches active space
- [ ] `iobox workspace status` shows provider table
- [ ] `iobox search` with `--workspace` flag does cross-type search
- [ ] Existing `iobox search` (email-only) still works
- [ ] `iobox events list` defaults to last 30 days when no date flags
- [ ] `iobox files list` without `--query` gives helpful error
- [ ] All unit tests pass
