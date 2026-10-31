# events

Calendar event operations on the calendar slots of a workspace.

Unlike the top-level email commands, `events` uses the active workspace (set with [`iobox space use`](space.md#use)), or the one named with `--workspace/-w`. Each session added with `--calendar` contributes a calendar slot named `<slug>-cal`, where the slug comes from the account email (`you@gmail.com` → `you-gmail`, so the slot is `you-gmail-cal`). Run `iobox space status` to see your sessions. See [Concepts](../get-started/concepts.md) for workspaces and slots.

**Access mode:** `list`, `get`, and `save` work in every global `--mode`; `create` and `rsvp` need `--mode standard` (the default) or higher; `delete` needs `--mode dangerous`. Write subcommands also need the calendar session to have been added without `--read`.

!!! note "`--provider` here is a slot name"
    The `--provider` option after `events <subcommand>` selects a workspace slot (e.g. `you-gmail-cal`). It is different from the global `iobox --provider gmail|outlook` option, which goes before `events` and must still be `gmail` or `outlook`.

## Subcommands

| Command | Description |
|---|---|
| [`list`](#list) | List events across calendar slots |
| [`get`](#get) | Print a single event as Markdown |
| [`save`](#save) | Save an event to a Markdown file |
| [`create`](#create) | Create a new event |
| [`delete`](#delete) | Delete an event |
| [`rsvp`](#rsvp) | Respond to an event invite |

`list` queries every calendar slot unless `--provider` is given. The other subcommands act on one slot: the one named by `--provider`, or the workspace's first calendar slot.

---

## list

```
iobox events list [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--after` | | TEXT | 30 days ago | Start date (`YYYY-MM-DD`) |
| `--before` | | TEXT | `None` | End date (`YYYY-MM-DD`); no upper bound if omitted |
| `--provider` | | TEXT | `None` | Only query this calendar slot (e.g. `you-gmail-cal`) |
| `--max` | `-m` | INT | `25` | Maximum results |
| `--workspace` | `-w` | TEXT | `None` | Use this workspace instead of the active one |

An unknown `--provider` slot name returns `No events found.` rather than an error.

```bash
# From 30 days ago onward (default)
iobox events list

# A specific range
iobox events list --after 2026-01-01 --before 2026-03-31

# Only one calendar slot
iobox events list --provider you-gmail-cal --after 2026-03-01
```

Output is a table with `Title`, `Start`, `End`, and `Provider` columns; the provider column shows the backend (`google_calendar` or `outlook_calendar`), not the slot name.

---

## get

Print a calendar event as Markdown.

```
iobox events get EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--provider` | | TEXT | first calendar slot | Calendar slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox events get abc123xyz --provider you-gmail-cal
```

---

## save

Save a calendar event as a Markdown file named `{slugified-title}.md`. An existing file with the same name is overwritten.

```
iobox events save EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--output` | `-o` | TEXT | `.` | Output directory (created if missing) |
| `--provider` | | TEXT | first calendar slot | Calendar slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox events save abc123xyz -o ./events
```

See [Output format](../reference/output-format.md).

---

## create

Create a new calendar event.

```
iobox events create --title TITLE --start DATETIME --end DATETIME [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--title` | `-t` | TEXT | *(required)* | Event title |
| `--start` | | TEXT | *(required)* | Start datetime, ISO 8601 (e.g. `2026-04-01T09:00:00+10:00`) |
| `--end` | | TEXT | *(required)* | End datetime, ISO 8601 |
| `--attendee` | `-a` | TEXT | `None` | Attendee email (repeatable) |
| `--description` | `-d` | TEXT | `None` | Event description |
| `--location` | `-l` | TEXT | `None` | Event location |
| `--all-day` | | FLAG | `False` | All-day event; only the date part of `--start`/`--end` is used |
| `--provider` | | TEXT | first calendar slot | Calendar slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

Google Calendar treats a datetime without a UTC offset as UTC, so include the offset.

```bash
iobox events create \
  --title "Team Standup" \
  --start "2026-04-01T09:00:00+10:00" \
  --end "2026-04-01T09:30:00+10:00" \
  --attendee alice@example.com \
  --attendee bob@example.com
```

---

## delete

Delete a calendar event. Asks for confirmation unless `--yes` is given. Requires `--mode dangerous`.

```
iobox events delete EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--yes` | `-y` | FLAG | `False` | Skip the confirmation prompt |
| `--provider` | | TEXT | first calendar slot | Calendar slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox --mode dangerous events delete abc123xyz --yes
```

---

## rsvp

Respond to a calendar event invite.

```
iobox events rsvp EVENT_ID --response RESPONSE [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--response` | `-r` | TEXT | *(required)* | `accepted`, `declined`, or `tentative` (exact values) |
| `--provider` | | TEXT | first calendar slot | Calendar slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox events rsvp abc123xyz --response accepted
iobox events rsvp abc123xyz -r declined --provider corp-company-cal
```
