# MCP Server

iobox ships with a Model Context Protocol (MCP) server that exposes the **full workspace surface** — email, calendar events, files, and cross-type search — to Claude Desktop, Cursor, VS Code, and any other MCP-compatible host.

The server is workspace-aware: a single Claude Desktop session can search across multiple Gmail accounts, multiple Outlook accounts, or any mix, in parallel. What's available depends on `IOBOX_MODE`.

## Overview

| Aspect | Details |
|---|---|
| Source | `src/iobox/mcp_server.py` |
| Entry point | `iobox-mcp` console script (registered in `pyproject.toml`) |
| Transport | stdio (Claude Desktop spawns the process) |
| Tool gating | `IOBOX_MODE` — `readonly`, `standard`, `dangerous` |
| Resolution | Active workspace first; falls back to single-account Gmail when no workspace exists |

## Prerequisites

1. **Install the MCP extras**:

    ```bash
    pip install 'iobox[mcp]'
    ```

2. **Place Google OAuth credentials** as `credentials.json` in your `CREDENTIALS_DIR` (defaults to the current working directory). See [Authentication](getting-started/authentication.md).

3. **Configure at least one workspace** — without one, the server falls back to legacy single-account Gmail and only the `*_gmail` tools work usefully.

    ```bash
    iobox space create personal
    iobox space add google you@gmail.com --email --calendar --drive --read
    iobox space status
    ```

For background on workspaces and slot naming, see the [Workspace guide](workspace-guide.md).

## Two-Account Walkthrough

The headline use case: search both your personal and work Gmail (plus their calendars and Drives) from a single Claude Desktop conversation.

### 1. Create a workspace and add both accounts

```bash
# Create the workspace
iobox space create personal

# Add personal Gmail (browser OAuth flow opens immediately)
iobox space add google personal@gmail.com --email --calendar --drive

# Add work Gmail (second browser OAuth flow — separate token)
iobox space add google work@gmail.com --email --calendar --drive

# Confirm both slots are authenticated
iobox space status
```

Expected `space status` output:

```
#  service  account              scopes                 mode      status
1  google   personal@gmail.com   email,calendar,drive   standard  authenticated
2  google   work@gmail.com       email,calendar,drive   standard  authenticated
```

Each slot gets a generated slug (typically `personal-gmail`, `work-gmail`) — you'll use these as the `provider` argument when targeting one account from a tool call.

### 2. Configure Claude Desktop

Open Claude Desktop → Settings → Developer → Edit Config (or edit the file directly — see paths below) and add:

```json
{
  "mcpServers": {
    "iobox": {
      "command": "iobox-mcp",
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

Quit Claude Desktop fully (Cmd-Q on macOS, not just close the window) and relaunch. When the server is running you'll see the **MCP indicator** (slider icon) at the bottom-right of the input box.

### 4. Verify with prompts that exercise both accounts

Ask Claude:

- *"List my workspaces."* — calls `list_workspaces`; should return `personal` as active.
- *"List the provider slots in my workspace."* — calls `list_provider_slots`; should show two email slots, two calendar slots, two file slots.
- *"Search both my Gmail accounts for emails from accountant@example.com in the last 30 days."* — calls `search_workspace` (or `search_gmail` with no `provider`) and fans out across both Gmail accounts.
- *"List all my calendar events for next week."* — calls `list_events` with no `provider`, fanning out across both calendars.
- *"Show events for next week on my work calendar only."* — Claude should pass `provider="work-gmail"` to `list_events`.

If Claude can't see the tools, see [Verification & troubleshooting](#verification--troubleshooting).

## Claude Desktop Configuration

### Config file locations

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

The easiest way to open it: **Claude Desktop → Settings → Developer → Edit Config**. Always restart Claude Desktop fully after editing.

### Read-only example

Default config — exposes search, retrieval, and save tools across email/calendar/files; no writes:

```json
{
  "mcpServers": {
    "iobox": {
      "command": "iobox-mcp",
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

### Read-write (`standard`) example

Adds drafts, label changes, calendar create/update, file uploads. Stops short of `send_email`, `trash_*`, `delete_event`:

```json
{
  "mcpServers": {
    "iobox": {
      "command": "iobox-mcp",
      "env": {
        "IOBOX_MODE": "standard",
        "IOBOX_ACCOUNT": "default"
      }
    }
  }
}
```

### Optional environment variables

| Variable | Purpose |
|---|---|
| `IOBOX_MODE` | `readonly` (default), `standard`, or `dangerous` — gates the tool registry |
| `IOBOX_ACCOUNT` | Account profile name for token namespacing (default `default`) |
| `CREDENTIALS_DIR` | Directory containing `credentials.json` and the `tokens/` tree |

## Access Modes

`IOBOX_MODE` controls which tools the server exposes. Modes are additive — `standard` includes everything in `readonly`; `dangerous` includes everything in `standard`.

| Mode | What it adds | Tools available |
|---|---|---|
| `readonly` | Reads and saves only — never modifies remote state | `search_gmail`, `get_email`, `save_email`, `save_thread`, `save_emails_by_query`, `list_gmail_drafts`, `check_auth`, `search_workspace`, `semantic_search_workspace`, `list_events`, `get_event`, `save_event`, `list_files`, `get_file`, `get_file_content`, `save_file`, `download_file`, `list_workspaces`, `get_active_workspace`, `list_provider_slots`, `workspace_auth_status` |
| `standard` | Drafts, label changes, calendar create/update, file uploads, workspace mutation | All of the above, plus: `create_gmail_draft`, `send_gmail_draft`, `delete_gmail_draft`, `modify_labels`, `batch_modify_gmail_labels`, `create_event`, `update_event`, `rsvp_event`, `upload_file`, `create_folder`, `delete_file`, `set_active_workspace` |
| `dangerous` | Outbound email and irreversible operations | All of the above, plus: `send_email`, `forward_gmail`, `batch_forward_gmail`, `trash_gmail`, `untrash_gmail`, `batch_trash_gmail`, `delete_event` |

The exact allowlists live in `src/iobox/modes.py` (`_READONLY_MCP`, `_STANDARD_MCP`, `_DANGEROUS_MCP`).

## Tool Reference

Every workspace-routed tool accepts two optional kwargs in addition to the ones listed below: `provider` (slot name) and `workspace` (workspace name, default = active). See [Multi-account targeting](#multi-account-targeting).

### Email

| Tool | Description | Signature highlights |
|---|---|---|
| `search_gmail` | Search email; fans out across email slots when no `provider` | `query, max_results=10, days=7, start_date, end_date, include_spam_trash=False` |
| `get_email` | Retrieve full email content by message ID | `message_id, prefer_html=True` |
| `save_email` | Save one message as Markdown | `message_id, output_dir='.', prefer_html=True, download_attachments=False, attachment_types` |
| `save_thread` | Save an entire thread as one Markdown file | `thread_id, output_dir='.', prefer_html=True` |
| `save_emails_by_query` | Batch save matching emails; optional incremental sync (Gmail only) | `query, output_dir='.', max_results=10, days=7, sync=False` |
| `send_email` | Send an email via the active slot | `to, subject, body, cc, bcc, html=False, attachments` |
| `forward_gmail` | Forward a single message | `message_id, to, note` |
| `batch_forward_gmail` | Forward every message matching a query | `query, to, max_results=10, days=7, note` |
| `create_gmail_draft` | Create a draft | `to, subject, body, cc, bcc, html=False, attachments` |
| `list_gmail_drafts` | List drafts | `max_results=10` |
| `send_gmail_draft` | Send an existing draft | `draft_id` |
| `delete_gmail_draft` | Permanently delete a draft | `draft_id` |
| `modify_labels` | Read/star/archive/add/remove on a single message | `message_id, mark_read, mark_unread, star, unstar, archive, add_label, remove_label` |
| `batch_modify_gmail_labels` | Same actions across a query | `query, max_results=10, days=7, ...same flags` |
| `trash_gmail` | Move to trash | `message_id` |
| `untrash_gmail` | Restore from trash | `message_id` |
| `batch_trash_gmail` | Trash everything matching a query | `query, max_results=10, days=7` |

### Calendar

| Tool | Description | Signature highlights |
|---|---|---|
| `list_events` | List events; fans out across calendar slots when no `provider` | `after, before, text, max_results=25` |
| `get_event` | Get a single event by ID | `event_id` |
| `save_event` | Save event as Markdown | `event_id, output_dir='.'` |
| `create_event` | Create a calendar event | `title, start, end, description, location, attendees, all_day=False` |
| `update_event` | Update fields on an existing event | `event_id, updates: dict` |
| `delete_event` | Delete an event | `event_id` |
| `rsvp_event` | RSVP to an invite | `event_id, response` (`"accepted"`/`"declined"`/`"tentative"`) |

### Files

| Tool | Description | Signature highlights |
|---|---|---|
| `list_files` | Search files; fans out across file slots when no `provider` | `query, max_results=20` |
| `get_file` | Get file metadata | `file_id` |
| `get_file_content` | Get extracted text content | `file_id` → `{content}` |
| `save_file` | Save metadata + extracted text as Markdown | `file_id, output_dir='.'` |
| `download_file` | Download binary content to disk | `file_id, output_path` |
| `upload_file` | Upload a local file | `local_path, name, parent_id` |
| `delete_file` | Trash or permanently delete a file | `file_id, permanent=False` |
| `create_folder` | Create a folder/directory | `name, parent_id` |

### Cross-type

| Tool | Description | Signature highlights |
|---|---|---|
| `search_workspace` | Cross-type search across email, events, and files in parallel | `query, types=['email','event','file'], max_results=10` |
| `semantic_search_workspace` | Vector search across indexed resources (requires `iobox[semantic]`) | `query, types, top_k=10, backend='openai'` |

### Discovery

| Tool | Description |
|---|---|
| `list_workspaces` | List all workspaces and the active one |
| `get_active_workspace` | Return the active workspace name |
| `set_active_workspace` | Switch the active workspace (`standard`+) |
| `list_provider_slots` | Enumerate every email/calendar/file slot in a workspace, with names and tags |
| `workspace_auth_status` | Per-slot auth status (calls `get_profile` against each provider) |

### Auth

| Tool | Description |
|---|---|
| `check_auth` | Legacy Gmail-only auth check (single-account fallback path) |

For full docstrings with every parameter described, see `src/iobox/mcp_server.py` — Claude Desktop also surfaces these via the MCP protocol when listing tools.

## Multi-Account Targeting

Every workspace tool accepts `provider="<slot-name>"` to target a single account. Omit it to fan out across every slot of that resource type.

### Discovering slot names

```text
User → "What provider slots are configured?"
Claude → calls list_provider_slots() → returns:
{
  "workspace": "personal",
  "email":    [{"name": "personal-gmail", "tags": [], "provider_class": "GmailProvider"},
               {"name": "work-gmail",     "tags": [], "provider_class": "GmailProvider"}],
  "calendar": [{"name": "personal-gmail", ...}, {"name": "work-gmail", ...}],
  "file":     [{"name": "personal-gmail", ...}, {"name": "work-gmail", ...}]
}
```

### Targeting a single account

```text
User → "Search work@gmail.com for invoices from last week."
Claude → calls search_gmail(query="invoices", days=7, provider="work-gmail")
```

### Cross-account fan-out (default)

```text
User → "Find every email from accountant@example.com across both accounts."
Claude → calls search_workspace(query="from:accountant@example.com", types=["email"])
   ↳ runs in parallel against personal-gmail and work-gmail
```

If a slot fails (expired token, network error), the workspace logs the error and continues with the remaining slots — one bad provider never breaks the whole query.

## Local Development

To test changes against your in-development checkout instead of the pip-installed version, point Claude Desktop at the project's editable install. Three options, ranked by ergonomics:

### Option A — editable install (recommended)

```bash
cd /Users/tim/Projects/iobox
uv sync --extra mcp
```

`uv sync` installs the project in editable mode by default, so `.venv/bin/iobox-mcp` resolves to live source under `src/iobox/`. Edits take effect on the next Claude Desktop relaunch — no reinstall needed.

Point Claude Desktop at the venv binary by absolute path so PATH resolution doesn't bite you:

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/Users/tim/Projects/iobox/.venv/bin/iobox-mcp",
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

Verify the binary is the editable one:

```bash
ls -la /Users/tim/Projects/iobox/.venv/bin/iobox-mcp
head -1 /Users/tim/Projects/iobox/.venv/bin/iobox-mcp   # shebang should be .venv/bin/python
```

### Option B — `uv run` (always uses the current lockfile)

```json
{
  "mcpServers": {
    "iobox": {
      "command": "uv",
      "args": ["--directory", "/Users/tim/Projects/iobox", "run", "iobox-mcp"],
      "env": {
        "IOBOX_MODE": "readonly",
        "PATH": "/Users/tim/.local/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

`uv` must be discoverable at spawn time. Claude Desktop on macOS does not inherit your shell's `PATH`, so set it explicitly in `env` (use `which uv` to find the right prefix).

### Option C — explicit python + module

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/Users/tim/Projects/iobox/.venv/bin/python",
      "args": ["-m", "iobox.mcp_server"],
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

Equivalent to Option A but skips the console-script entry point. Useful when you're iterating on `pyproject.toml`'s `[project.scripts]` block itself.

### Switching back to the pip-installed version

Change `command` back to plain `"iobox-mcp"` (resolved via `PATH`) and restart. The two installs can coexist — pip puts `iobox-mcp` in your global Python's bin dir, the editable install puts one in `.venv/bin/`.

### Iteration loop

Code changes are picked up on Claude Desktop **process restart only** (Cmd-Q + relaunch, not just closing the window) — the MCP subprocess is long-lived for the session. Tail the log while iterating:

```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-iobox.log
```

A quick way to confirm the server is on local code: add a temporary `print("LOCAL DEV BUILD", file=sys.stderr)` to `main()` in `src/iobox/mcp_server.py` — it'll appear in the log on next launch.

## Verification & Troubleshooting

### Confirm the server is running

1. Look for the **slider icon** (MCP indicator) at the bottom-right of the Claude Desktop input box.
2. Ask Claude: *"List my workspaces."* — should return your configured workspace and the active one.
3. Ask Claude: *"What's the auth status of each provider slot?"* — calls `workspace_auth_status` and returns per-slot OK/error.

### Reading logs

| OS | Log directory |
|---|---|
| macOS | `~/Library/Logs/Claude/` |
| Windows | `%APPDATA%\Claude\logs\` |

Two files matter:

- `mcp.log` — Claude Desktop's own MCP client log
- `mcp-server-iobox.log` — stdout/stderr of the `iobox-mcp` process

Tail both on macOS:

```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
```

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Slider icon missing | Claude Desktop didn't spawn the server | Check `mcp.log` for spawn errors; verify `iobox-mcp` is on `PATH` (`which iobox-mcp`); ensure `pip install 'iobox[mcp]'` ran in the same Python that owns `iobox-mcp` |
| Tools list is empty | `IOBOX_MODE` set to a value with few tools, or workspace not configured | Set `IOBOX_MODE=standard`; run `iobox space status` to confirm slots exist |
| `"No active workspace configured"` | Server can't find a workspace | Run `iobox space create NAME` then `iobox space add gmail ...`; confirm with `iobox space list` |
| `"Email provider 'X' not found"` | `provider` arg doesn't match any slot | Call `list_provider_slots` to see valid names |
| Tool returns `{"error": "..."}` mentioning auth | Token expired or revoked | Run `iobox space login N` from the CLI to re-authenticate |
| Server keeps restarting | Crashing on startup | Check `mcp-server-iobox.log` for the traceback; common cause is missing `credentials.json` |

## Authentication

The MCP server uses the same OAuth tokens as the CLI — they're stored under `~/.iobox/tokens/<account>/`. See [Authentication](getting-started/authentication.md) for setup.

> **Important:** interactive OAuth flows (those triggered by `iobox space add` and `iobox space login`) **cannot run from inside Claude Desktop** — the browser handoff doesn't work in the spawned MCP subprocess. Always run those commands from a normal terminal first. Once tokens exist on disk the MCP server picks them up on next launch.
