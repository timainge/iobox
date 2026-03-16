---
id: task-018
title: "CalendarProvider write methods"
milestone: 5
status: done
priority: p3
depends_on: [task-005, task-012]
blocks: []
parallel_with: [task-019]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

After read-only calendar support is proven in the PoC (tasks 005, 012), write operations become useful: creating meetings, updating events, responding to invites. This task adds write methods to the `CalendarProvider` ABC and implements them in both `GoogleCalendarProvider` and `OutlookCalendarProvider`.

Write operations are gated behind `--mode standard`.

## Scope

**Does:**
- Add write methods to `CalendarProvider` ABC: `create_event`, `update_event`, `delete_event`, `rsvp`
- Implement in `GoogleCalendarProvider`
- Implement in `OutlookCalendarProvider`
- Mode gate: writes require `mode="standard"`, reads remain `mode="readonly"`
- Update `SCOPES_BY_MODE` in `modes.py`: calendar writes need `calendar` scope (not just `calendar.readonly`)
- Add CLI commands: `iobox events create`, `iobox events delete`, `iobox events rsvp`

**Does NOT:**
- Implement file write operations (task-019)
- Implement RSVP for Outlook (complex — separate ticket if needed)
- Handle recurring event series editing (just single instances for MVP)

## Architecture Notes

- `create_event` input: title, start, end, attendees list, description, location, all_day
- `update_event` input: event_id + partial update dict (only fields to change)
- `delete_event` input: event_id; deletes from primary calendar
- `rsvp` input: event_id, response (`"accepted"` | `"declined"` | `"tentative"`)
- Google: `rsvp` updates the authenticated user's `responseStatus` in the attendees list
- Outlook: use `event.accept()`, `event.decline()`, `event.tentatively_accept()`
- All write methods check `self.mode != "readonly"` before executing

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/providers/base.py` | Add write abstract methods to CalendarProvider |
| Modify | `src/iobox/providers/google_calendar.py` | Implement write methods |
| Modify | `src/iobox/providers/outlook_calendar.py` | Implement write methods |
| Modify | `src/iobox/modes.py` | Update calendar scopes for standard mode |
| Modify | `src/iobox/cli.py` | Add events write commands |
| Create | `tests/unit/test_calendar_write_ops.py` | Unit tests |

## CalendarProvider ABC additions

```python
# providers/base.py additions to CalendarProvider
@abstractmethod
def create_event(
    self,
    title: str,
    start: str,
    end: str,
    *,
    all_day: bool = False,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,  # list of email addresses
) -> Event:
    """Create a new calendar event. Returns the created event."""
    ...

@abstractmethod
def update_event(self, event_id: str, updates: dict) -> Event:
    """Update fields of an existing event. Returns the updated event."""
    ...

@abstractmethod
def delete_event(self, event_id: str) -> None:
    """Delete an event from the calendar."""
    ...

@abstractmethod
def rsvp(self, event_id: str, response: str) -> Event:
    """
    Respond to a calendar invite.
    response: "accepted" | "declined" | "tentative"
    """
    ...
```

## GoogleCalendarProvider write implementations

```python
def create_event(self, title, start, end, *, all_day=False, description=None,
                 location=None, attendees=None) -> Event:
    self._check_write_mode()
    svc = self._get_service()

    if all_day:
        start_dict = {"date": start[:10]}
        end_dict = {"date": end[:10]}
    else:
        start_dict = {"dateTime": start, "timeZone": "UTC"}
        end_dict = {"dateTime": end, "timeZone": "UTC"}

    body = {
        "summary": title,
        "start": start_dict,
        "end": end_dict,
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]

    result = svc.events().insert(calendarId="primary", body=body).execute()
    return self._google_event_to_event(result)

def update_event(self, event_id: str, updates: dict) -> Event:
    self._check_write_mode()
    svc = self._get_service()
    result = svc.events().patch(
        calendarId="primary", eventId=event_id, body=updates
    ).execute()
    return self._google_event_to_event(result)

def delete_event(self, event_id: str) -> None:
    self._check_write_mode()
    svc = self._get_service()
    svc.events().delete(calendarId="primary", eventId=event_id).execute()

def rsvp(self, event_id: str, response: str) -> Event:
    self._check_write_mode()
    svc = self._get_service()
    # Get current event to find self in attendees
    event_raw = svc.events().get(calendarId="primary", eventId=event_id).execute()
    # Find the authenticated user's attendee entry and update it
    profile = self.get_profile()
    my_email = profile.get("email", "")
    attendees = event_raw.get("attendees", [])
    updated = False
    for att in attendees:
        if att.get("email", "").lower() == my_email.lower():
            att["responseStatus"] = response
            updated = True
            break
    if not updated:
        raise ValueError(f"Authenticated user {my_email} is not an attendee of event {event_id}")
    updated_raw = svc.events().patch(
        calendarId="primary",
        eventId=event_id,
        body={"attendees": attendees}
    ).execute()
    return self._google_event_to_event(updated_raw)

def _check_write_mode(self) -> None:
    if self.mode == "readonly":
        raise PermissionError("Calendar write operations require mode='standard'.")
```

## OutlookCalendarProvider write implementations

```python
def create_event(self, title, start, end, *, all_day=False, description=None,
                 location=None, attendees=None) -> Event:
    self._check_write_mode()
    calendar = self._get_account().schedule().get_default_calendar()
    from datetime import datetime
    event = calendar.new_event()
    event.subject = title
    event.start = datetime.fromisoformat(start)
    event.end = datetime.fromisoformat(end)
    event.is_all_day = all_day
    if description:
        event.body = description
    if location:
        event.location = location
    if attendees:
        for email in attendees:
            event.attendees.add(email)
    event.save()
    return self._o365_event_to_event(event)

def delete_event(self, event_id: str) -> None:
    self._check_write_mode()
    event = self._get_account().schedule().get_event(object_id=event_id)
    if event:
        event.delete()

def rsvp(self, event_id: str, response: str) -> Event:
    self._check_write_mode()
    event = self._get_account().schedule().get_event(object_id=event_id)
    if not event:
        raise KeyError(f"Event '{event_id}' not found")
    if response == "accepted":
        event.accept()
    elif response == "declined":
        event.decline()
    elif response == "tentative":
        event.tentatively_accept()
    else:
        raise ValueError(f"Unknown RSVP response: {response}")
    return self._o365_event_to_event(event)
```

## CLI additions

```bash
# Create event
iobox events create --title "Team meeting" --start "2026-04-01T10:00:00" \
    --end "2026-04-01T11:00:00" --attendee alice@company.com --attendee bob@company.com

# Delete event
iobox events delete EVENT_ID

# RSVP
iobox events rsvp EVENT_ID --response accepted
iobox events rsvp EVENT_ID --response declined
iobox events rsvp EVENT_ID --response tentative
```

## Key Decisions

**Q: Should `update_event` take a full Event TypedDict or a partial dict?**
Partial dict (just the fields to change) — simpler for callers. Google Calendar's `patch` API takes a partial body.

**Q: Should `rsvp` be in the ABC even if Outlook implements it differently?**
Yes — same interface, different implementation. It's the right abstraction.

**Q: What mode is required for calendar writes?**
`standard` mode. Update `get_google_scopes(["calendar"], "standard")` to return `calendar` scope (not `calendar.readonly`).

## Test Strategy

```python
# tests/unit/test_calendar_write_ops.py
class TestGoogleCalendarCreateEvent:
    def test_create_timed_event(self, mock_service): ...
    def test_create_all_day_event(self, mock_service): ...
    def test_create_with_attendees(self, mock_service): ...
    def test_blocked_in_readonly_mode(self): ...

class TestGoogleCalendarRsvp:
    def test_accept(self, mock_service): ...
    def test_user_not_attendee_raises(self, mock_service): ...
```

## Verification

```bash
make test
# With real credentials and --mode standard:
iobox events create --title "Test" --start "2026-04-01T10:00" --end "2026-04-01T11:00"
iobox events rsvp EVENT_ID --response accepted
```

## Acceptance Criteria

- [ ] `CalendarProvider` ABC has `create_event`, `update_event`, `delete_event`, `rsvp`
- [ ] `GoogleCalendarProvider` implements all four methods
- [ ] `OutlookCalendarProvider` implements create, delete, rsvp (update is optional for MVP)
- [ ] All write methods raise `PermissionError` in readonly mode
- [ ] Calendar scopes updated in `SCOPES_BY_MODE` for standard mode
- [ ] CLI commands `events create`, `events delete`, `events rsvp` added
- [ ] Unit tests pass
