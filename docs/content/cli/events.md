# events

Calendar event operations across all providers in the active workspace.

## Subcommands

| Command | Description |
|---|---|
| [`list`](#list) | List events in a date range |
| [`get`](#get) | Print a single event as Markdown |
| [`save`](#save) | Save an event to a Markdown file |
| [`create`](#create) | Create a new event |
| [`delete`](#delete) | Delete an event |
| [`rsvp`](#rsvp) | Respond to an event invite |

---

## list

List calendar events from the active workspace.

```
iobox events list [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--after` | | TEXT | 30 days ago | Start date (`YYYY-MM-DD`) |
| `--before` | | TEXT | None | End date (`YYYY-MM-DD`) |
| `--max` | `-m` | INT | `25` | Maximum results |
| `--provider` | | TEXT | None | Target a specific provider slot by name |
| `--workspace` | `-w` | TEXT | None | Use a named workspace instead of the active one |

```bash
# Events from the last 30 days (default)
iobox events list

# Events in a specific range
iobox events list --after 2026-01-01 --before 2026-03-31

# From a specific provider slot
iobox events list --provider tim-gmail --after 2026-03-01
```

---

## get

Print a calendar event as Markdown.

```
iobox events get EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox events get abc123xyz
```

---

## save

Save a calendar event as a Markdown file.

```
iobox events save EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--output` | `-o` | PATH | `.` | Output directory |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox events save abc123xyz -o ./events
```

The file is saved as `{slugified-title}.md`.

---

## create

Create a new calendar event. Requires `--mode standard`.

```
iobox events create [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--title` | `-t` | TEXT | *(required)* | Event title |
| `--start` | | TEXT | *(required)* | Start datetime (ISO 8601, e.g. `2026-04-01T09:00`) |
| `--end` | | TEXT | *(required)* | End datetime (ISO 8601) |
| `--attendee` | `-a` | TEXT | None | Attendee email (repeatable) |
| `--description` | `-d` | TEXT | None | Event description |
| `--location` | `-l` | TEXT | None | Event location |
| `--all-day` | | FLAG | `False` | Create as an all-day event |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox events create \
  --title "Team Standup" \
  --start "2026-04-01T09:00" \
  --end "2026-04-01T09:30" \
  --attendee alice@example.com \
  --attendee bob@example.com
```

---

## delete

Delete a calendar event. Requires `--mode standard`.

```
iobox events delete EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--yes` | `-y` | FLAG | `False` | Skip confirmation prompt |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox events delete abc123xyz --yes
```

---

## rsvp

Respond to a calendar event invite. Requires `--mode standard`.

```
iobox events rsvp EVENT_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--response` | `-r` | TEXT | *(required)* | `accepted`, `declined`, or `tentative` |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox events rsvp abc123xyz --response accepted
iobox events rsvp abc123xyz --response declined
```
