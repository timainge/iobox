---
id: task-012
title: "OutlookCalendarProvider (read-only)"
milestone: 2
status: done
priority: p1
depends_on: [task-002]
blocks: [task-014]
parallel_with: [task-005, task-006, task-013]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Milestone 2 brings O365 parity with Google. `OutlookCalendarProvider` uses the O365 Python library (`python-o365`) to read calendar events from Microsoft 365, implementing the same `CalendarProvider` ABC as `GoogleCalendarProvider`.

## Scope

**Does:**
- `src/iobox/providers/outlook_calendar.py` — `OutlookCalendarProvider(CalendarProvider)`
- `list_events(EventQuery)` — date range, text search
- `get_event(id)` — single event by ID
- `get_sync_state()` / `get_new_events(sync_token)` — stub implementations
- `_o365_event_to_event()` normalizer
- Register as `"outlook_calendar"` in `providers/__init__.py`
- Unit tests with mocked O365 objects

**Does NOT:**
- Implement write operations (task-018)
- Implement `MicrosoftAuth` shared object (task-014) — uses `OutlookAuth` directly for now
- Implement non-primary calendar support

## Architecture Notes

- Use `O365.Account.schedule()` to get the `Schedule` object
- `schedule.get_default_calendar()` returns the primary calendar
- `calendar.get_events(limit=N, start=start, end=end)` returns events in range
- Text search: O365 library may use `$search` header; check `schedule.search_events(query=text)`
- `all_day` from `event.is_all_day` property
- Online meeting URL from `event.online_meeting_url` or scan body for Teams links
- Attendees from `event.attendees` — list of O365 Attendee objects
- `event.body.content` for description (HTML — strip tags for plain text)
- O365 event IDs are stable (immutable IDs already used by OutlookProvider)
- Import guard: `OutlookCalendarProvider` is in an optional-dependency module; wrap import of `O365` in try/except with clear error message

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/providers/outlook_calendar.py` | `OutlookCalendarProvider` |
| Modify | `src/iobox/providers/__init__.py` | Register `"outlook_calendar"` |
| Create | `tests/unit/test_outlook_calendar_provider.py` | Unit tests |
| Modify | `tests/unit/test_provider_contract.py` | Add contract tests |

## O365 Library API

```python
# Basic usage
from O365 import Account
account = Account(credentials=(client_id, client_secret), auth_flow_type='credentials')
account.authenticate(scopes=['basic', 'calendar'])

schedule = account.schedule()
calendar = schedule.get_default_calendar()

# Get events in range
start = datetime(2026, 3, 1)
end = datetime(2026, 3, 31)
events = calendar.get_events(limit=50, start=start, end=end, include_recurring=True)
for event in events:
    event.fetch_full_event()  # required for body/attendees in some versions

# Search (via OData filter / $search)
events = schedule.search_events(query="Q4 planning", limit=20)

# Event properties
event.subject           # title
event.start.date()      # all-day start
event.start.datetime    # timed start
event.end.datetime
event.is_all_day        # bool
event.body.content      # HTML body
event.location.display_name
event.organizer.address
event.attendees         # list of Attendee objects
event.online_meeting_url
event.object_id         # ID
event.web_link          # URL
event.created           # datetime
event.modified          # datetime
```

## Implementation Guide

### Step 1 — Scaffold with import guard

```python
# src/iobox/providers/outlook_calendar.py
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from iobox.providers.base import CalendarProvider, Event, EventQuery, AttendeeInfo

try:
    from O365 import Account
    HAS_O365 = True
except ImportError:
    HAS_O365 = False

logger = logging.getLogger(__name__)

class OutlookCalendarProvider(CalendarProvider):

    PROVIDER_ID = "outlook_calendar"

    def __init__(
        self,
        account_email: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
    ):
        if not HAS_O365:
            raise ImportError(
                "O365 package required for Outlook support. "
                "Install with: pip install 'iobox[outlook]'"
            )
        self.account_email = account_email
        self.credentials_dir = credentials_dir
        self.mode = mode
        self._account = None
        self._schedule = None

    def _get_account(self):
        if self._account is None:
            from iobox.providers.outlook_auth import OutlookAuth
            auth = OutlookAuth(account=self.account_email, credentials_dir=self.credentials_dir)
            self._account = auth.get_account()
        return self._account

    def authenticate(self) -> None:
        self._get_account()  # triggers auth if needed
```

### Step 2 — Implement list_events

```python
    def list_events(self, query: EventQuery) -> list[Event]:
        account = self._get_account()
        schedule = account.schedule()
        calendar = schedule.get_default_calendar()

        kwargs = {"limit": query.max_results, "include_recurring": True}

        if query.after or query.before:
            from datetime import datetime
            if query.after:
                kwargs["start"] = datetime.fromisoformat(query.after)
            if query.before:
                kwargs["end"] = datetime.fromisoformat(query.before)

        if query.text:
            # Use search if text query provided
            try:
                raw_events = list(schedule.search_events(query=query.text, limit=query.max_results))
            except Exception:
                # Fallback to get_events with no text filter
                raw_events = list(calendar.get_events(**kwargs))
        else:
            raw_events = list(calendar.get_events(**kwargs))

        return [self._o365_event_to_event(e) for e in raw_events]
```

### Step 3 — Implement normalizer

```python
    def _o365_event_to_event(self, ev) -> Event:
        # Title
        title = getattr(ev, "subject", "") or "(no title)"

        # Start/end
        start_obj = getattr(ev, "start", None)
        end_obj = getattr(ev, "end", None)
        all_day = getattr(ev, "is_all_day", False)

        if all_day:
            start = str(start_obj.date()) if start_obj else ""
            end = str(end_obj.date()) if end_obj else ""
        else:
            start = start_obj.isoformat() if start_obj else ""
            end = end_obj.isoformat() if end_obj else ""

        # Attendees
        attendees: list[AttendeeInfo] = []
        for att in (getattr(ev, "attendees", None) or []):
            attendees.append(AttendeeInfo(
                email=getattr(att, "address", "") or "",
                name=getattr(att, "name", None),
                response_status=str(getattr(att.response_status, "value", "")) if hasattr(att, "response_status") else None,
            ))

        # Organizer
        organizer_obj = getattr(ev, "organizer", None)
        organizer = getattr(organizer_obj, "address", None) if organizer_obj else None

        # Meeting URL
        meeting_url = getattr(ev, "online_meeting_url", None)
        if not meeting_url:
            # Scan body for Teams link
            body_content = getattr(getattr(ev, "body", None), "content", "") or ""
            if "teams.microsoft.com" in body_content:
                import re
                m = re.search(r"https://teams\.microsoft\.com/[^\s\"'<>]+", body_content)
                if m:
                    meeting_url = m.group(0)

        # Description (strip HTML)
        description = _strip_html(getattr(getattr(ev, "body", None), "content", "") or "")

        # Location
        location_obj = getattr(ev, "location", None)
        location = getattr(location_obj, "display_name", None) if location_obj else None

        created = getattr(ev, "created", None)
        modified = getattr(ev, "modified", None)

        return Event(
            id=str(getattr(ev, "object_id", "") or ""),
            provider_id=self.PROVIDER_ID,
            resource_type="event",
            title=title,
            created_at=created.isoformat() if created else "",
            modified_at=modified.isoformat() if modified else "",
            url=getattr(ev, "web_link", None),
            start=start,
            end=end,
            all_day=all_day,
            organizer=organizer,
            attendees=attendees,
            location=location,
            description=description or None,
            meeting_url=meeting_url,
            status="confirmed",  # O365 doesn't expose status the same way
            recurrence=None,  # O365 recurrence is complex — skip for MVP
        )
```

### Step 4 — HTML stripping helper

```python
def _strip_html(html: str) -> str:
    """Simple HTML tag removal for event descriptions."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text
```

### Step 5 — Implement get_event and sync stubs

```python
    def get_event(self, event_id: str) -> Event:
        account = self._get_account()
        schedule = account.schedule()
        # O365 library: get event by object_id
        ev = schedule.get_event(object_id=event_id)
        if ev is None:
            raise KeyError(f"Event '{event_id}' not found")
        return self._o365_event_to_event(ev)

    def get_sync_state(self) -> dict:
        return {}  # O365 sync tokens are complex — stub for MVP

    def get_new_events(self, sync_token: str) -> tuple[list[Event], str]:
        return [], sync_token  # stub
```

### Step 6 — Register in providers/__init__.py

Add `"outlook_calendar"` to the lazy import registry.

### Step 7 — Unit tests

Mock O365 `Account`, `Schedule`, `Calendar`, `Event` objects. Build minimal mock objects with the required properties.

```python
# tests/unit/test_outlook_calendar_provider.py
class MockO365Event:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    subject = "Team standup"
    is_all_day = False
    object_id = "evt_abc123"
    web_link = "https://outlook.live.com/calendar/..."
    # etc.

class TestOutlookCalendarProviderListEvents:
    def test_list_events_basic(self, mock_account): ...
    def test_all_day_event_uses_date_format(self, mock_account): ...
    def test_teams_url_extracted_from_body(self, mock_account): ...

class TestEventNormalization:
    def test_attendees_mapped(self): ...
    def test_html_stripped_from_description(self): ...
```

## Key Decisions

**Q: Should `list_events` use `search_events` or `get_events` when text is provided?**
Try `search_events` first for text queries; fall back to `get_events` if unsupported. Some O365 tenants restrict `$search`.

**Q: How to handle recurrence?**
Skip for MVP — set `recurrence=None`. The O365 library's recurrence handling is complex and not needed for read-only display.

**Q: What response_status values does O365 use?**
`ResponseStatus.accepted`, `ResponseStatus.declined`, `ResponseStatus.tentative`, `ResponseStatus.not_responded`. Map to lowercase strings.

## Verification

```bash
make test
python -c "from iobox.providers.outlook_calendar import OutlookCalendarProvider"
```

## Acceptance Criteria

- [ ] `OutlookCalendarProvider` in `src/iobox/providers/outlook_calendar.py`
- [ ] Import guard for O365 with clear error message
- [ ] `list_events()` with date range and text search
- [ ] `get_event()` by ID
- [ ] `_o365_event_to_event()` maps all fields correctly
- [ ] Teams meeting URL extracted from body when `online_meeting_url` absent
- [ ] HTML stripped from event descriptions
- [ ] Registered as `"outlook_calendar"` in `providers/__init__.py`
- [ ] Unit tests pass
- [ ] Contract tests added
