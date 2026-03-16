# Workspace Setup & Space Commands

A **workspace** is the primary user-facing abstraction in iobox. Instead of targeting a single provider directly, you configure a named workspace (e.g. "personal", "work") that fans out across multiple accounts and services.

## Concepts

| Term | Description |
|---|---|
| **Space** | A named workspace config file (`~/.iobox/workspaces/NAME.toml`) |
| **Service session** | One account + service within a space (e.g. Gmail for `tim@gmail.com`) |
| **Slot** | A named provider instance within a workspace, identified by number, ID, or slug |
| **Scopes** | Which resource types are enabled: `--messages`, `--calendar`, `--drive` |
| **Mode** | `--read` for readonly; omit for standard (read+write) |

## Initial Setup

```bash
# 1. Create your first workspace
iobox space create personal

# 2. Add Gmail with all scopes in readonly mode
iobox space add gmail you@gmail.com --messages --calendar --drive --read
# This triggers an OAuth flow in your browser immediately.

# 3. Verify
iobox space status
```

Example status output:
```
#  service  account           scopes                    mode      status
1  gmail    you@gmail.com     messages,calendar,drive   readonly  ✓ authenticated
```

## Adding Multiple Accounts

```bash
# Work Gmail in standard mode (can send/write)
iobox space add gmail work@company.com --messages --calendar

# Microsoft 365 Outlook (requires iobox[outlook])
iobox space add outlook corp@company.com --messages --calendar --read
```

## Space Commands

### `iobox space create NAME`

Creates a new space config at `~/.iobox/workspaces/NAME.toml`. If this is the first space, it becomes the active space automatically.

### `iobox space list`

Lists all available spaces and marks the active one.

### `iobox space use NAME`

Switches the active space. Equivalent to `iobox workspace use NAME`.

### `iobox space status`

Rich table showing all service sessions, their scopes, mode, and authentication status.

### `iobox space add SERVICE ACCOUNT [--messages] [--calendar] [--drive] [--read]`

Adds a service session to the active space and triggers OAuth immediately.

- `SERVICE`: `gmail` or `outlook`
- `ACCOUNT`: the account email address
- `--messages`: enable email access
- `--calendar`: enable calendar access
- `--drive`: enable file/drive access (Gmail only; Outlook uses OneDrive)
- `--read`: use readonly scopes (omit for standard read+write)

```bash
# Examples
iobox space add gmail tim@gmail.com --messages --calendar --drive --read
iobox space add gmail work@company.com --messages
iobox space add outlook corp@company.com --messages --calendar --read
```

!!! note
    Google OAuth requires all scopes to be requested in a **single OAuth flow** per account. You cannot add calendar scope to an existing mail-only token. Use `iobox space login N` to re-authenticate with updated scopes.

### `iobox space login N|SLUG`

Re-triggers OAuth for a service session, requesting the same scopes as configured. Useful when a token expires.

```bash
iobox space login 1        # by slot number
iobox space login corp     # by slug
```

### `iobox space logout N|SLUG`

Revokes and deletes the token for a service session. The slot config is kept — use `iobox space login` to re-authenticate later.

### `iobox space remove N|SLUG`

Removes a service session from the space entirely (prompts for confirmation if authenticated).

## Using a Workspace in Commands

All resource commands (`events`, `files`, `messages`) automatically use the active space:

```bash
# Uses active space, all calendar providers
iobox events list --after 2026-01-01

# Target a specific provider slot by name
iobox events list --provider tim-gmail

# Use a different workspace
iobox events list --workspace work
```

## Config File Format

Space configs live at `~/.iobox/workspaces/NAME.toml`:

```toml
name = "personal"

[[services]]
service = "gmail"
account = "you@gmail.com"
scopes = ["messages", "calendar", "drive"]
mode = "readonly"
slug = "you-gmail"
```

Tokens are stored at `~/.iobox/tokens/ACCOUNT/`:

```
~/.iobox/
  workspaces/
    personal.toml
    work.toml
  tokens/
    you@gmail.com/
      token_readonly.json
    corp@company.com/
      microsoft_token.txt
```
