---
id: task-017
title: "Email write ops under Workspace"
milestone: 4
status: done
priority: p2
depends_on: [task-010]
blocks: []
parallel_with: [task-018, task-019]
estimated_effort: M
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Email write operations (send, forward, draft management, label, trash) are already implemented in `GmailProvider` and `OutlookProvider`. After task-010 adds workspace-centric CLI commands, this task ensures all write operations route through the Workspace layer correctly and that mode gating is enforced at the Workspace level.

This is primarily a validation and wiring task — not a net-new feature.

## Scope

**Does:**
- Verify all write operations work correctly through `Workspace` / `MessageProvider` abstractions
- Update `cli.py` write commands to route through `workspace.message_providers` instead of direct provider access
- Enforce mode gating (`--mode standard/dangerous`) at the Workspace level
- Update MCP write tools to use Workspace
- Regression testing: verify all existing live tests pass

**Does NOT:**
- Implement new write operations
- Change write operation behavior or output format
- Add write operations for calendar or files (task-018, task-019)

## Strategic Fit

After the workspace-centric CLI lands (task-010), the existing write commands (`send`, `forward`, `draft-*`, `label`, `trash`) still use the old direct-provider path. This task closes that gap so the workspace is the single point of entry for all operations.

## Architecture Notes

- `Workspace` currently only fans out read operations — write ops need to target a specific slot by name
- Write operations are NOT fan-out — they target one specific provider (the user must specify which one, or default to the first)
- Mode gating: the CLI currently checks mode at the top level (`get_provider()` rejects if mode is wrong). After this task, mode is checked per-slot in the Workspace.
- MCP write tools: same pattern — after task-011 routes reads through Workspace, writes should follow

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/cli.py` | Update write commands to use workspace slot |
| Modify | `src/iobox/workspace.py` | Add write method stubs delegating to specific slot |
| Modify | `src/iobox/mcp_server.py` | Update write tools if needed |
| Create | `tests/unit/test_workspace_writes.py` | Verify write routing |

## Write Operation Routing

```python
# workspace.py additions

def get_message_provider(self, slot_name: str | None = None) -> EmailProvider:
    """Get a specific message provider slot. Defaults to first slot."""
    if not self.message_providers:
        raise ValueError("No message providers in workspace.")
    if slot_name is None:
        return self.message_providers[0].provider
    for slot in self.message_providers:
        if slot.name == slot_name:
            return slot.provider
    raise ValueError(f"No message provider slot '{slot_name}'.")

def send(self, slot_name: str | None = None, **kwargs) -> dict:
    return self.get_message_provider(slot_name).send(**kwargs)

def forward(self, slot_name: str | None = None, **kwargs) -> dict:
    return self.get_message_provider(slot_name).forward(**kwargs)

# etc. for draft_create, draft_send, draft_delete, label, trash, untrash
```

## Mode Gating at Workspace Level

```python
# Check before executing write ops
def _check_write_mode(self, slot_name: str | None = None) -> None:
    """Raise if the targeted slot is in readonly mode."""
    for slot in self.message_providers:
        if slot_name is None or slot.name == slot_name:
            # Check mode from space config
            if hasattr(slot.provider, "mode") and slot.provider.mode == "readonly":
                raise PermissionError(
                    f"Provider slot '{slot.name}' is in readonly mode. "
                    "Use --mode standard to enable write operations."
                )
            break
```

## Implementation Guide

### Step 1 — Read all write commands in cli.py

List every write command: `send`, `forward`, `draft-create`, `draft-list`, `draft-send`, `draft-delete`, `label`, `trash`. Note their current provider access pattern.

### Step 2 — Add get_message_provider + write methods to Workspace

Implement `get_message_provider()` and write delegation methods in `workspace.py`.

### Step 3 — Update CLI write commands

For each write command, add workspace-aware path:
```python
@app.command("send")
def send_cmd(
    ...
    provider: str | None = typer.Option(None, "--provider"),
    workspace_name: str | None = typer.Option(None, "--workspace"),
):
    if workspace_name or get_active_space():
        ws = _get_workspace(workspace_name)
        result = ws.send(slot_name=provider, to=to, subject=subject, body=body)
    else:
        # Legacy path — single provider
        provider_obj = get_provider()
        result = provider_obj.send(to=to, subject=subject, body=body)
```

### Step 4 — Regression test

Run all existing tests. All write operations should pass without changes to their behavior.

### Step 5 — Live test validation

If live test credentials are available:
```bash
python tests/live/run_tests.py
```

## Key Decisions

**Q: Should write ops require explicit `--provider` when workspace has multiple message providers?**
Default to first slot — consistent with existing behavior. If user wants to target a specific account, they use `--provider SLUG`.

**Q: Should mode gating be enforced in the CLI or the Workspace layer?**
Both — CLI validates mode before calling workspace, workspace also validates. Defense in depth.

## Test Strategy

```python
# tests/unit/test_workspace_writes.py
class TestWorkspaceWriteRouting:
    def test_send_routes_to_first_slot_when_no_name(self, mock_providers): ...
    def test_send_routes_to_named_slot(self, mock_providers): ...
    def test_send_raises_for_unknown_slot(self, mock_providers): ...
    def test_mode_gate_blocks_readonly_slot(self, mock_providers): ...
    def test_mode_gate_allows_standard_slot(self, mock_providers): ...
```

## Verification

```bash
make test
# With real credentials:
iobox send --to test@example.com --subject "Test" --body "Hello"
iobox draft-create --to test@example.com --subject "Draft" --body "Test"
iobox draft-list
```

## Acceptance Criteria

- [ ] `Workspace.get_message_provider(slot_name)` returns correct provider
- [ ] All write methods on `Workspace` delegate to the correct slot
- [ ] CLI write commands have workspace-aware path
- [ ] Mode gating enforced at Workspace level
- [ ] Legacy (non-workspace) path still works
- [ ] All existing tests pass
- [ ] Live tests pass (if credentials available)
