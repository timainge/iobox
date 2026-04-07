# space

Manage iobox workspaces and service sessions.

See [Workspace Guide](../workspace-guide.md) for a conceptual overview and setup walkthrough.

## Subcommands

| Command | Description |
|---|---|
| [`create`](#create) | Create a new workspace |
| [`list`](#list) | List all workspaces |
| [`use`](#use) | Switch the active workspace |
| [`status`](#status) | Show service session status |
| [`add`](#add) | Add a service session and authenticate |
| [`login`](#login) | Re-authenticate a service session |
| [`logout`](#logout) | Revoke a service session token |
| [`remove`](#remove) | Remove a service session |

---

## create

Create a new workspace config at `~/.iobox/workspaces/NAME.toml`. The first workspace created becomes active automatically.

```
iobox space create NAME
```

```bash
iobox space create personal
iobox space create work
```

---

## list

List all available workspaces and mark the active one.

```
iobox space list
```

---

## use

Switch the active workspace.

```
iobox space use NAME
```

```bash
iobox space use work
```

---

## status

Show a table of all service sessions, their scopes, mode, and authentication status.

```
iobox space status
```

Example output:

```
#  service  account           scopes                    mode      status
1  gmail    you@gmail.com     messages,calendar,drive   readonly  ✓ authenticated
2  outlook  corp@company.com  messages,calendar         standard  ✓ authenticated
```

---

## add

Add a service session to the active workspace and trigger OAuth immediately.

```
iobox space add SERVICE ACCOUNT [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `SERVICE` | `gmail` or `outlook` |
| `ACCOUNT` | Account email address |
| `--messages` | Enable email access |
| `--calendar` | Enable calendar access |
| `--drive` | Enable file/drive access (Gmail only; OneDrive is included automatically with `--calendar` for Outlook) |
| `--read` | Use readonly scopes (omit for standard read+write) |

```bash
iobox space add gmail you@gmail.com --messages --calendar --drive --read
iobox space add gmail work@company.com --messages --calendar
iobox space add outlook corp@company.com --messages --calendar --read
```

!!! note
    Google OAuth requests all scopes in a single flow per account. To add a scope to an existing session, use `iobox space login N` to re-authenticate with updated scopes.

---

## login

Re-trigger OAuth for a service session. Useful when a token expires or when scopes need updating.

```
iobox space login N|SLUG
```

```bash
iobox space login 1        # by slot number
iobox space login corp     # by slug
```

---

## logout

Revoke and delete the token for a service session. The slot config is kept — use `iobox space login` to re-authenticate.

```
iobox space logout N|SLUG
```

```bash
iobox space logout 2
```

---

## remove

Remove a service session from the workspace entirely. Prompts for confirmation if the session is authenticated.

```
iobox space remove N|SLUG
```

```bash
iobox space remove corp
```
