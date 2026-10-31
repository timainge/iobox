# space

Manage workspaces ("spaces") and the service sessions inside them.

A space is a named config at `~/.iobox/workspaces/NAME.toml` listing service sessions (one account plus the services enabled for it). The [`events`](events.md) and [`files`](files.md) commands and the MCP server use the active space; the top-level email commands (`search`, `save`, `send`, ...) do not. See [Concepts](../get-started/concepts.md) for workspaces, slots, and access modes.

**Access mode:** `space` is allowed in every global `--mode`. A session's own read/write level is set with `--read` on [`add`](#add).

## Subcommands

| Command | Description |
|---|---|
| [`create`](#create) | Create a new space |
| [`list`](#list) | List all spaces |
| [`use`](#use) | Switch the active space |
| [`status`](#status) | Show sessions in the active space and their auth status |
| [`add`](#add) | Add a service session and authenticate |
| [`login`](#login) | Re-authenticate a service session |
| [`logout`](#logout) | Delete a service session's local token |
| [`remove`](#remove) | Remove a service session |

`add`, `login`, `logout`, `remove`, and `status` act on the active space only.

---

## create

Create `~/.iobox/workspaces/NAME.toml`. If no space is active yet, the new one becomes active. Fails if the name already exists.

```
iobox space create NAME
```

```bash
iobox space create personal
iobox space create work
```

---

## list

List all spaces and mark the active one.

```
iobox space list
```

```
  personal (active)
  work
```

---

## use

Switch the active space.

```
iobox space use NAME
```

```bash
iobox space use work
```

---

## status

Show a table of the active space's sessions: number, service, account, scopes, mode, and whether a token file exists.

```
iobox space status
```

```
                                 Space: personal (active)
┏━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ Service ┃ Account          ┃ Scopes               ┃ Mode     ┃ Status              ┃
┡━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ google  │ you@gmail.com    │ email,calendar,drive │ readonly │ ✓ authenticated     │
│ 2 │ o365    │ corp@company.com │ email,calendar       │ standard │ ✗ not authenticated │
└───┴─────────┴──────────────────┴──────────────────────┴──────────┴─────────────────────┘
```

---

## add

Add a service session to the active space and start the OAuth flow in your browser immediately.

```
iobox space add SERVICE ACCOUNT [OPTIONS]
```

| Argument / Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `SERVICE` | | TEXT | *(required)* | `google` or `o365` |
| `ACCOUNT` | | TEXT | *(required)* | Account email address |
| `--email` | | FLAG | `False` | Enable email (Gmail / Outlook) |
| `--calendar` | | FLAG | `False` | Enable calendar (Google Calendar / Outlook Calendar) |
| `--drive` | | FLAG | `False` | Enable Google Drive. Rejected for `o365` |
| `--read` | | FLAG | `False` | Read-only session; omit for `standard` (read + write) |

At least one of `--email`, `--calendar`, `--drive` is required. After sign-in, iobox checks that the signed-in account matches `ACCOUNT` (case-insensitive); on a mismatch the token is discarded and the session is not added.

The session's slug is derived from the account (`you@gmail.com` → `you-gmail`) and names its workspace slots: the email slot is `you-gmail`, the calendar slot `you-gmail-cal`, and the drive slot `you-gmail-drive`. Use these with `--provider` on [`events`](events.md) and [`files`](files.md).

```bash
iobox space add google you@gmail.com --email --calendar --drive --read
iobox space add google work@company.com --email --calendar
iobox space add o365 corp@company.com --email --calendar
```

```
Opening browser for OAuth... (service: google, account: you@gmail.com)
Added service session #1 (google/you@gmail.com) — authenticated ✓
  id:     google-yougmailcom
  slug:   you-gmail
  mode:   readonly
  scopes: email, calendar, drive
```

Google tokens are stored at `~/.iobox/tokens/ACCOUNT/token_{readonly|standard}.json`; the Google OAuth client is read from `GOOGLE_APPLICATION_CREDENTIALS` or `~/.iobox/credentials.json`. `o365` needs `OUTLOOK_CLIENT_ID` set; its token is stored at `~/.iobox/tokens/ACCOUNT/microsoft_token.txt`. See [Connect Google](../get-started/connect-google.md) and [Connect Microsoft](../get-started/connect-microsoft.md).

To change a session's services or mode, [`remove`](#remove) it and `add` it again; `login` reuses the existing settings.

---

## login

Re-run OAuth for an existing session, with its existing services and mode. Useful when a token has expired or been revoked.

```
iobox space login REF
```

`REF` is the session number, id, or slug (as shown by `add` / `status`).

```bash
iobox space login 1
iobox space login corp-company
```

---

## logout

Delete the local token file for a session. The session stays in the space config, and the token is not revoked with the provider. Run `iobox space login REF` to authenticate again.

```
iobox space logout REF
```

```bash
iobox space logout 2
```

---

## remove

Remove a session from the active space. Its token file is left on disk.

```
iobox space remove REF [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--yes` | `-y` | FLAG | `False` | Skip the confirmation prompt |

```bash
iobox space remove corp-company --yes
```

---

## workspace use / workspace status

`iobox workspace` is a shortcut group:

| Command | Equivalent |
|---|---|
| `iobox workspace use NAME` | Same as `iobox space use NAME` |
| `iobox workspace status [--workspace/-w NAME]` | Plain-text list of a space's sessions (number, service, account, scopes, mode). Unlike `space status`, it does not show auth status, but it can target a space other than the active one with `-w` |

```bash
iobox workspace status -w work
```
