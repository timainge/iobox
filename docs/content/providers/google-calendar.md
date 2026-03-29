# Google Calendar Provider

The `GoogleCalendarProvider` connects iobox to your Google Calendar via the Calendar API v3. It shares OAuth tokens with Gmail for the same account — no separate login required if you already have Gmail access with the `--calendar` scope.

## Prerequisites

- A Google Cloud project with the **Google Calendar API** enabled
- OAuth credentials (`credentials.json`) in your project root or `CREDENTIALS_DIR`
- The `calendar` scope included when adding your Gmail service session

## Setup

```bash
# Add Gmail with calendar access (readonly)
iobox space add gmail you@gmail.com --messages --calendar --read

# Or with write access (standard mode)
iobox space add gmail you@gmail.com --messages --calendar
```

If you already have a Gmail session but without calendar scope, you need to re-authenticate:

```bash
# Re-authenticate to add calendar scope
iobox space login 1
```

!!! note
    Google OAuth issues tokens for a fixed scope set. You cannot add calendar scope to an existing mail-only token without re-authenticating. The `iobox space login` command re-requests all configured scopes.

## Scopes

| Mode | Scope |
|---|---|
| `readonly` | `https://www.googleapis.com/auth/calendar.readonly` |
| `standard` | `https://www.googleapis.com/auth/calendar` |

## CLI Commands

### List events

```bash
iobox events list
iobox events list --after 2026-01-01
iobox events list --after 2026-01-01 --before 2026-04-01
iobox events list --query "budget review"
iobox events list --max 50
```

| Option | Description |
|---|---|
| `--after DATE` | ISO 8601 date or datetime (e.g. `2026-01-01`) |
| `--before DATE` | ISO 8601 date or datetime |
| `--query TEXT` | Free-text search |
| `--max N` | Maximum results (default: 20) |
| `--provider NAME` | Target a specific workspace slot |

### Get a single event

```bash
iobox events get EVENT_ID
```

### Save event as Markdown

```bash
iobox events save EVENT_ID -o ./events
```

Produces a Markdown file with YAML frontmatter including start/end times, organizer, attendees, location, and meeting URL.

### Create event (requires standard mode)

```bash
iobox events create \
  --title "Team Meeting" \
  --start "2026-04-01T10:00:00" \
  --end "2026-04-01T11:00:00" \
  --attendee alice@example.com \
  --attendee bob@example.com \
  --location "Conference Room A" \
  --description "Quarterly planning"
```

```bash
# All-day event
iobox events create --title "Company Holiday" --start 2026-04-01 --end 2026-04-02 --all-day
```

### RSVP (requires standard mode)

```bash
iobox events rsvp EVENT_ID --response accepted
iobox events rsvp EVENT_ID --response declined
iobox events rsvp EVENT_ID --response tentative
```

### Delete event (requires standard mode)

```bash
iobox events delete EVENT_ID          # prompts for confirmation
iobox events delete EVENT_ID --yes    # skip confirmation
```

## Event Markdown Format

```markdown
---
id: abc123
provider_id: google_calendar
resource_type: event
title: Q4 Planning Session
start: 2026-03-16T10:00:00+11:00
end: 2026-03-16T12:00:00+11:00
all_day: false
organizer: boss@example.com
attendees:
  - email: alice@example.com
    name: Alice
    response_status: accepted
  - email: bob@example.com
    name: Bob
    response_status: tentative
location: Conference Room A
meeting_url: https://meet.google.com/abc-defg-hij
status: confirmed
saved_date: 2026-03-24T21:30:00
---

Review Q4 plans and finalize budget allocations.
```

## API Notes

- Events are fetched from the **primary calendar** (`calendarId='primary'`)
- All-day events use `date` format in the API; timed events use `dateTime`
- Meeting URLs are extracted from `hangoutLink` (Google Meet) or `conferenceData.entryPoints`
- Incremental sync is supported via `get_sync_state()` / `get_new_events(sync_token)`
