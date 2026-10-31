# CLI

The `iobox` command searches, exports, and acts on your email, calendar, and files from the terminal. It's also how you set up workspaces and authenticate accounts for the [MCP server](../mcp/index.md) and [SDK](../sdk/index.md).

## Command groups

| Group | Commands | Operates on |
|---|---|---|
| **Workspaces** | [`space`](space.md) `create` · `list` · `use` · `status` · `add` · `login` · `logout` · `remove` | `~/.iobox/workspaces/` |
| **Calendar** | [`events`](events.md) `list` · `get` · `save` · `create` · `delete` · `rsvp` | Active workspace, all calendar slots |
| **Files** | [`files`](files.md) `list` · `get` · `save` · `upload` · `delete` · `mkdir` | Active workspace, all file slots |
| **Email** | [`search`](search.md) · [`save`](save.md) · [`send`](send.md) · [`forward`](forward.md) · [drafts](drafts.md) · [`label`](label.md) · [`trash`](trash.md) | One mailbox (see below) |
| **Utility** | [`auth-status`](auth-status.md) · `version` | |

## Workspace commands vs email commands

`events` and `files` go through the [workspace](../get-started/concepts.md#workspace): they fan out across every slot by default, take `--workspace/-w NAME` to use a non-active workspace, and `--provider SLOT` to target one account.

The email commands are older and act on **one mailbox at a time**, selected by global options:

```bash
iobox --provider gmail --account you@gmail.com search -q "is:unread"
```

They look for tokens in `$CREDENTIALS_DIR/tokens/ACCOUNT/` (default: current directory). To reuse the tokens created by `iobox space add`, point them at `~/.iobox`:

```bash
export CREDENTIALS_DIR=~/.iobox
export IOBOX_ACCOUNT=you@gmail.com
```

For cross-account email search, use the [MCP server](../mcp/multi-account.md) or [`Workspace.search_emails`](../sdk/workspace.md) in the SDK.

## Global options

Global options go **before** the command name.

| Option | Env var | Default | Description |
|---|---|---|---|
| `--mode` | `IOBOX_MODE` | `standard` | Access mode: `readonly`, `standard`, `dangerous` |
| `--account` | `IOBOX_ACCOUNT` | `default` | Mailbox for email commands (token directory name) |
| `--provider` | `IOBOX_PROVIDER` | `gmail` | Email provider for email commands: `gmail` or `outlook` |
| `--version` | | | Print version and exit |

Not to be confused with the `--provider SLOT` option on `events` and `files` subcommands, which selects a workspace slot.

## Access modes

`--mode` decides which top-level commands are allowed:

| Mode | Commands |
|---|---|
| `readonly` | `search`, `save`, `draft-list`, `auth-status`, `version`, `space`, `workspace`, `events`, `files` |
| `standard` | + `draft-create`, `draft-send`, `draft-delete`, `label` |
| `dangerous` | + `send`, `forward`, `trash` |

```bash
iobox --mode dangerous send --to someone@example.com --subject "Hi" --body "Hello"
```

`events` and `files` writes are not gated by `--mode`; they're blocked only when the account was added with `--read`. See [access modes](../get-started/concepts.md#access-modes).

## Common recipes

```bash
# Export a newsletter archive, then keep it up to date
iobox save -q "from:digest@example.com" -d 365 -o ./newsletters
iobox save -q "from:digest@example.com" --sync -o ./newsletters

# This week's events across every calendar
iobox events list --after 2026-11-02 --before 2026-11-09

# Save a calendar event as Markdown
iobox events save EVENT_ID -o ./meetings

# Find a document across all drives
iobox files list --query "lease agreement"

# Switch workspaces
iobox space use work
```
