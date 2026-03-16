---
id: task-011
title: "MCP server update with workspace.search()"
milestone: 1
status: done
priority: p1
depends_on: [task-007]
blocks: []
parallel_with: [task-010, task-014]
estimated_effort: XL
research_needed: false
research_questions: []
assigned_to: null
---

## Context

The MCP server (`mcp_server.py`) currently bypasses the provider layer entirely — it calls `email_search`, `email_retrieval`, and `email_sender` legacy modules directly. This makes it impossible to expose calendar and file tools through MCP without duplicating the provider logic.

This task rewrites `mcp_server.py` to use `Workspace` and providers. It also adds new tools for calendar events and files. This is larger than it looks because of the bypass issue discovered during codebase exploration.

## Scope

**Does:**
- Rewrite `mcp_server.py` to route through `Workspace` / provider layer
- Add new MCP tools: `list_events`, `get_event`, `list_files`, `get_file`, `get_file_content`, `search_workspace`
- Refactor existing tools (search_gmail, get_email, etc.) to use provider methods
- Update `MCP_TOOLS_BY_MODE` in `modes.py` with new tool names
- Update unit tests in `tests/unit/test_mcp_server.py`

**Does NOT:**
- Implement CLI commands (task-010)
- Break backward compat for existing tool names (keep old names, add new ones)
- Implement semantic search (task-016)
- Add write tools for events/files (task-018, task-019 first)

## Strategic Fit

The MCP server is how Claude and other LLM clients interact with iobox. Adding `search_workspace()` as an MCP tool is the primary value proposition for AI-assisted e-discovery. Without this task, the Workspace expansion is invisible to MCP users.

## Architecture Notes

- **Critical finding**: `mcp_server.py` calls `email_search.search_emails()`, `email_retrieval.get_email()` etc. directly — NOT through `GmailProvider`. The refactor must replace these with provider calls while preserving tool output format.
- MCP server builds a provider at startup (or lazily) using `get_provider()` factory from `providers/__init__.py`
- For workspace tools, build `Workspace` from the active space config using `Workspace.from_config()`
- Tool output format: existing tools return dicts — keep the same keys for backward compat
- `search_workspace` returns a list of `Resource` dicts with `resource_type` field for client dispatch
- Error handling: MCP tools should return `{"error": "message"}` dicts on failure, not raise exceptions

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/mcp_server.py` | Major rewrite: route through providers/workspace |
| Modify | `src/iobox/modes.py` | Add new tool names to MCP_TOOLS_BY_MODE |
| Modify | `tests/unit/test_mcp_server.py` | Update and add tests |

## Existing Tool Inventory

Before rewriting, read `mcp_server.py` and list all current tools. The expected set based on `modes.py`:

```python
# Readonly tools (expected)
"search_gmail"       # → workspace.search_messages() or provider.search()
"get_email"          # → provider.get_message()
"download_attachment" # → provider.download_attachment()

# Standard tools (expected)
"send_email"         # → provider.send()
"forward_email"      # → provider.forward()
"create_draft"       # → provider.create_draft()
"list_drafts"        # → provider.list_drafts()
"send_draft"         # → provider.send_draft()
"delete_draft"       # → provider.delete_draft()
"label_message"      # → provider.label()
"trash_message"      # → provider.trash()
"untrash_message"    # → provider.untrash()
```

## New Tools to Add

```python
# Readonly (new)
"search_workspace"   # workspace.search(text, types) → list[Resource]
"list_events"        # workspace.list_events(EventQuery) → list[Event]
"get_event"          # provider.get_event(id) → Event
"list_files"         # workspace.list_files(FileQuery) → list[File]
"get_file"           # provider.get_file(id) → File
"get_file_content"   # provider.get_file_content(id) → str
```

## Implementation Guide

### Step 1 — Read mcp_server.py completely

Read `src/iobox/mcp_server.py` before touching it. Document the exact legacy modules called and the tool output format for each.

### Step 2 — Read modes.py MCP_TOOLS_BY_MODE

Understand which tools are gated behind which mode. New tools follow the same pattern.

### Step 3 — Refactor workspace/provider initialization

Use injectable factory functions — not `lru_cache` on module-level singletons. This follows the multitool factory pattern and makes tools testable by injecting mock workspaces via the `_workspace_fn` DI hook.

```python
# mcp_server.py — provider/workspace setup
from iobox.providers import get_provider
from iobox.workspace import Workspace
from iobox.space_config import get_active_space, load_space, IOBOX_HOME
from typing import Callable

def _default_workspace_fn() -> Workspace | None:
    """Default factory: load active workspace from disk."""
    active = get_active_space()
    if not active:
        return None
    config = load_space(active)
    return Workspace.from_config(config, credentials_dir=str(IOBOX_HOME))

def create_mcp_server(*, _workspace_fn: Callable | None = None):
    """
    Factory that builds the FastMCP server.
    _workspace_fn: inject a mock workspace factory in tests.
    """
    get_workspace = _workspace_fn or _default_workspace_fn
    # ... register tools using get_workspace() inside each tool
```

Each tool calls `get_workspace()` (the injected factory) rather than a cached singleton. This means tests can pass `_workspace_fn=lambda: mock_workspace` and verify tool behavior without hitting disk or OAuth.


### Step 4 — Refactor existing search_gmail tool

```python
@mcp.tool()
def search_gmail(
    query: str,
    max_results: int = 10,
    days: int | None = None,
) -> list[dict]:
    """Search emails. Uses active workspace if configured, else legacy provider."""
    ws = _get_workspace()
    if ws:
        from iobox.providers.base import EmailQuery
        eq = EmailQuery(query=query, max_results=max_results)
        if days:
            from datetime import datetime, timedelta
            eq.after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
        results = ws.search_messages(eq)
    else:
        provider = _get_provider()
        from iobox.providers.base import EmailQuery
        results = provider.search(EmailQuery(query=query, max_results=max_results))

    return [_email_data_to_dict(r) for r in results]
```

### Step 5 — Add search_workspace tool

```python
@mcp.tool()
def search_workspace(
    query: str,
    types: list[str] | None = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Cross-type search across messages, calendar events, and files.
    types: list of "message", "event", "file" (defaults to all)
    Returns list of Resource dicts with resource_type field.
    """
    ws = _get_workspace()
    if not ws:
        return [{"error": "No active workspace configured. Run `iobox space create` first."}]
    try:
        results = ws.search(query, types=types, max_results_per_type=max_results)
        return [dict(r) for r in results]
    except Exception as e:
        return [{"error": str(e)}]
```

### Step 6 — Add calendar tools

```python
@mcp.tool()
def list_events(
    after: str | None = None,
    before: str | None = None,
    text: str | None = None,
    provider: str | None = None,
    max_results: int = 25,
) -> list[dict]:
    """List calendar events. Optionally filter by date range or text."""
    ws = _get_workspace()
    if not ws:
        return [{"error": "No active workspace."}]
    from iobox.providers.base import EventQuery
    query = EventQuery(text=text, after=after, before=before, max_results=max_results)
    providers = [provider] if provider else None
    try:
        events = ws.list_events(query, providers=providers)
        return [dict(e) for e in events]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def get_event(event_id: str, provider: str | None = None) -> dict:
    """Get a single calendar event by ID."""
    ws = _get_workspace()
    if not ws:
        return {"error": "No active workspace."}
    slot = _find_calendar_slot(ws, provider)
    if not slot:
        return {"error": f"No calendar provider '{provider}' in workspace."}
    try:
        return dict(slot.provider.get_event(event_id))
    except KeyError:
        return {"error": f"Event '{event_id}' not found."}
    except Exception as e:
        return {"error": str(e)}
```

### Step 7 — Add file tools

Same pattern as calendar tools. `get_file_content` returns `{"content": str}`.

### Step 8 — Update MCP_TOOLS_BY_MODE in modes.py

```python
# Add to MCP_TOOLS_BY_MODE["readonly"]
"search_workspace",
"list_events",
"get_event",
"list_files",
"get_file",
"get_file_content",
```

### Step 9 — Update tests

Read existing `tests/unit/test_mcp_server.py` and update tests to mock at the provider/workspace level rather than the legacy module level.

## Key Decisions

**Q: Should existing tool output format change?**
No — backward compat. `search_gmail` must return the same dict structure it does now. New tools have their own format.

**Q: Should `_get_workspace()` be cached?**
Yes (`lru_cache`) — workspace construction is expensive (instantiates multiple providers). But cache must be invalidated if active space changes. Use `lru_cache(maxsize=1)` for simplicity; if space changes, server restart is required (acceptable).

**Q: What happens if `search_workspace` is called but no workspace is configured?**
Return `[{"error": "..."}]` — don't raise. MCP clients should handle error dicts.

**Q: Should we remove the direct legacy module imports?**
Yes — after refactoring, `mcp_server.py` should not import `email_search`, `email_retrieval`, or `email_sender` directly. All calls go through provider methods.

## Test Strategy

```python
# tests/unit/test_mcp_server.py — updated
class TestSearchGmail:
    def test_uses_workspace_when_active(self, mock_workspace): ...
    def test_falls_back_to_provider_when_no_workspace(self, mock_provider): ...

class TestSearchWorkspace:
    def test_returns_cross_type_results(self, mock_workspace): ...
    def test_no_workspace_returns_error_dict(self): ...
    def test_type_filter(self, mock_workspace): ...

class TestListEvents:
    def test_basic(self, mock_workspace): ...
    def test_no_workspace_returns_error(self): ...

class TestGetEvent:
    def test_returns_event_dict(self, mock_workspace): ...
    def test_not_found_returns_error(self, mock_workspace): ...

class TestListFiles:
    def test_basic(self, mock_workspace): ...
```

## Verification

```bash
make test
python -c "from iobox.mcp_server import mcp"
# Check no legacy module imports remain:
grep -n "email_search\|email_retrieval\|email_sender" src/iobox/mcp_server.py
```

## Acceptance Criteria

- [ ] `mcp_server.py` does not import `email_search`, `email_retrieval`, or `email_sender` directly
- [ ] `search_gmail` tool routes through provider/workspace, preserving output format
- [ ] `search_workspace` tool returns cross-type `Resource` dicts
- [ ] `list_events`, `get_event` tools implemented
- [ ] `list_files`, `get_file`, `get_file_content` tools implemented
- [ ] All new tools added to `MCP_TOOLS_BY_MODE["readonly"]` in `modes.py`
- [ ] Workspace falls back gracefully to single-provider mode when no space configured
- [ ] All tools return `{"error": "..."}` dicts on failure (no exceptions raised to MCP framework)
- [ ] All unit tests pass
- [ ] `make type-check` passes
