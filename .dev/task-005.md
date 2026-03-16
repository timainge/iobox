---
id: task-005
title: "GoogleCalendarProvider (read-only)"
milestone: 0
status: done
priority: p0
depends_on: [task-002, task-003]
blocks: [task-007]
parallel_with: [task-006, task-008, task-009, task-012, task-013]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

The e-discovery PoC requires listing and searching calendar events from Gmail accounts. `GoogleCalendarProvider` is the first `CalendarProvider` implementation — it wraps the Google Calendar API v3, shares auth with `GmailProvider` via `GoogleAuth`, and maps Google Event objects to the `Event` TypedDict from task-002.

## Scope

**Does:**
- `src/iobox/providers/google_calendar.py` — `GoogleCalendarProvider(CalendarProvider)`
- `list_events(EventQuery)` — pagination-aware
- `get_event(id)` — single event retrieval
- `get_sync_state()` / `get_new_events(sync_token)` — incremental sync
- `_google_event_to_event()` normalizer — handles all-day vs timed, attendees, meeting URLs
- Register as `"google_calendar"` in `providers/__init__.py`
- Unit tests with mocked googleapiclient responses

**Does NOT:**
- Implement write operations (create/update/delete/rsvp — task-018)
- Implement Workspace (task-007)
- Implement CLI commands (task-010)
- Implement non-primary calendars (just `calendarId='primary'` for now)

## Strategic Fit

This is one of three providers needed for the PoC demo (Gmail + GCal + GDrive). Combined with task-006 and task-007, it enables the cross-type `workspace.search()` call that's the demo's centrepiece.

## Architecture Notes

- `GoogleCalendarProvider` accepts either a `GoogleAuth` instance or `(account, credentials_dir, mode)` to construct one
- Use `GoogleAuth.get_service("calendar", "v3")` — same token as GmailProvider for the same account
- Required scope: `https://www.googleapis.com/auth/calendar.readonly`
- Pagination: Calendar API uses `pageToken` — loop until `nextPageToken` is absent
- All-day events: `start.date` (not `start.dateTime`); parse accordingly
- Meeting URLs: check `hangoutLink` first, then `conferenceData.entryPoints` for Teams/Zoom entries
- Attendee response status maps: `"accepted"`, `"declined"`, `"tentative"`, `"needsAction"`
- Event `status` field: `"confirmed"`, `"tentative"`, `"cancelled"`
- `title` in `Resource` = event `summary`
- `created_at` / `modified_at` = `created` / `updated` from Google response
- `url` = `htmlLink`

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/providers/google_calendar.py` | `GoogleCalendarProvider` implementation |
| Modify | `src/iobox/providers/__init__.py` | Register `"google_calendar"` provider |
| Create | `tests/unit/test_google_calendar_provider.py` | Unit tests |
| Modify | `tests/unit/test_provider_contract.py` | Add GoogleCalendarProvider contract tests |
| Create | `tests/fixtures/mock_calendar_responses.py` | Mock Google Calendar API responses |

## Google Calendar API Notes

### events().list() response structure

```python
{
    "items": [
        {
            "id": "abc123",
            "summary": "Team standup",
            "status": "confirmed",
            "htmlLink": "https://calendar.google.com/...",
            "created": "2026-01-01T10:00:00.000Z",
            "updated": "2026-01-02T09:00:00.000Z",
            "start": {
                "dateTime": "2026-03-15T09:00:00-07:00",
                "timeZone": "America/Los_Angeles"
            },
            "end": {
                "dateTime": "2026-03-15T09:30:00-07:00",
                "timeZone": "America/Los_Angeles"
            },
            "organizer": {"email": "boss@example.com", "displayName": "Boss"},
            "attendees": [
                {"email": "tim@gmail.com", "responseStatus": "accepted"},
                {"email": "alice@gmail.com", "responseStatus": "tentative"}
            ],
            "description": "Daily standup meeting",
            "location": "Zoom",
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
                ]
            },
            "recurrence": ["RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"]
        }
    ],
    "nextPageToken": "tokenXYZ",
    "nextSyncToken": "syncTokenABC"
}
```

### All-day event start/end

```python
# Timed event
"start": {"dateTime": "2026-03-15T09:00:00-07:00"}
# All-day event
"start": {"date": "2026-03-15"}
```

## Implementation Guide

### Step 1 — Scaffold the provider

Follow the multitool DI pattern: every method that makes an external call accepts a `_service_fn=None` injection point. This lets unit tests pass a mock service directly without needing to patch `googleapiclient.discovery.build`.

```python
# src/iobox/providers/google_calendar.py
from __future__ import annotations
from typing import Any, Callable
from iobox.providers.base import CalendarProvider, Event, EventQuery, AttendeeInfo
from iobox.providers.google_auth import GoogleAuth

class GoogleCalendarProvider(CalendarProvider):

    SCOPES_READONLY = ["https://www.googleapis.com/auth/calendar.readonly"]
    PROVIDER_ID = "google_calendar"

    def __init__(
        self,
        auth: GoogleAuth | None = None,
        account: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
    ):
        if auth is not None:
            self._auth = auth
        else:
            from iobox.modes import get_google_scopes, _tier_for_mode
            scopes = get_google_scopes(["calendar"], mode)
            tier = _tier_for_mode(mode)
            self._auth = GoogleAuth(
                account=account,
                scopes=scopes,
                credentials_dir=credentials_dir,
                tier=tier,
            )
        self._service = None

    def authenticate(self) -> None:
        self._auth.get_credentials()

    def get_profile(self, *, _service_fn: Callable | None = None) -> dict:
        svc = _service_fn or self._get_service()
        result = svc.calendarList().get(calendarId="primary").execute()
        return {
            "email": result.get("id"),
            "display_name": result.get("summary"),
        }

    def _get_service(self):
        if self._service is None:
            self._service = self._auth.get_service("calendar", "v3")
        return self._service
```

### Step 2 — Implement list_events

```python
    def list_events(self, query: EventQuery, *, _service_fn: Callable | None = None) -> list[Event]:
        svc = _service_fn or self._get_service()
        params: dict[str, Any] = {
            "calendarId": query.calendar_id,
            "maxResults": min(query.max_results, 250),  # API max is 2500
            "singleEvents": True,   # expand recurring events
            "orderBy": "startTime",
        }
        if query.text:
            params["q"] = query.text
        if query.after:
            params["timeMin"] = _to_rfc3339(query.after)
        if query.before:
            params["timeMax"] = _to_rfc3339(query.before)

        events: list[Event] = []
        page_token = None
        while len(events) < query.max_results:
            if page_token:
                params["pageToken"] = page_token
            resp = svc.events().list(**params).execute()
            for item in resp.get("items", []):
                events.append(self._google_event_to_event(item))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return events[:query.max_results]
```

### Step 3 — Implement normalizer

```python
    def _google_event_to_event(self, raw: dict) -> Event:
        start_raw = raw.get("start", {})
        end_raw = raw.get("end", {})
        all_day = "date" in start_raw and "dateTime" not in start_raw
        start = start_raw.get("dateTime") or start_raw.get("date", "")
        end = end_raw.get("dateTime") or end_raw.get("date", "")

        # Attendees
        attendees: list[AttendeeInfo] = []
        for att in raw.get("attendees", []):
            attendees.append(AttendeeInfo(
                email=att.get("email", ""),
                name=att.get("displayName"),
                response_status=att.get("responseStatus"),
            ))

        # Meeting URL: hangoutLink first, then conferenceData entryPoints
        meeting_url = raw.get("hangoutLink")
        if not meeting_url:
            conf = raw.get("conferenceData", {})
            for ep in conf.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meeting_url = ep.get("uri")
                    break

        organizer_raw = raw.get("organizer", {})
        organizer = organizer_raw.get("email")

        recurrence = None
        rec_list = raw.get("recurrence", [])
        if rec_list:
            recurrence = rec_list[0]  # take first RRULE

        return Event(
            id=raw.get("id", ""),
            provider_id=self.PROVIDER_ID,
            resource_type="event",
            title=raw.get("summary", "(no title)"),
            created_at=raw.get("created", ""),
            modified_at=raw.get("updated", ""),
            url=raw.get("htmlLink"),
            start=start,
            end=end,
            all_day=all_day,
            organizer=organizer,
            attendees=attendees,
            location=raw.get("location"),
            description=raw.get("description"),
            meeting_url=meeting_url,
            status=raw.get("status"),
            recurrence=recurrence,
        )
```

### Step 4 — Implement get_event, sync methods

```python
    def get_event(self, event_id: str) -> Event:
        svc = self._get_service()
        raw = svc.events().get(calendarId="primary", eventId=event_id).execute()
        return self._google_event_to_event(raw)

    def get_sync_state(self) -> dict:
        # Return a sync token from a full sync
        svc = self._get_service()
        resp = svc.events().list(calendarId="primary", maxResults=1).execute()
        return {"sync_token": resp.get("nextSyncToken", "")}

    def get_new_events(self, sync_token: str) -> tuple[list[Event], str]:
        svc = self._get_service()
        resp = svc.events().list(
            calendarId="primary", syncToken=sync_token
        ).execute()
        events = [self._google_event_to_event(item) for item in resp.get("items", [])]
        next_token = resp.get("nextSyncToken", sync_token)
        return events, next_token
```

### Step 5 — Helper: RFC 3339 date conversion

```python
def _to_rfc3339(date_str: str) -> str:
    """Convert YYYY-MM-DD to RFC 3339 (append T00:00:00Z if needed)."""
    if "T" in date_str:
        return date_str  # already datetime
    return f"{date_str}T00:00:00Z"
```

### Step 6 — Register in providers/__init__.py

Add `"google_calendar"` to the provider registry alongside existing providers.

### Step 7 — Mock fixtures

```python
# tests/fixtures/mock_calendar_responses.py
MOCK_EVENT_TIMED = {
    "id": "evt001",
    "summary": "Team standup",
    "status": "confirmed",
    "htmlLink": "https://calendar.google.com/event?eid=evt001",
    "created": "2026-01-01T10:00:00.000Z",
    "updated": "2026-03-01T09:00:00.000Z",
    "start": {"dateTime": "2026-03-15T09:00:00-07:00"},
    "end": {"dateTime": "2026-03-15T09:30:00-07:00"},
    "organizer": {"email": "boss@example.com"},
    "attendees": [
        {"email": "tim@gmail.com", "responseStatus": "accepted"},
    ],
    "hangoutLink": "https://meet.google.com/abc-defg",
}

MOCK_EVENT_ALL_DAY = {
    "id": "evt002",
    "summary": "Company holiday",
    "status": "confirmed",
    "created": "2026-01-01T00:00:00.000Z",
    "updated": "2026-01-01T00:00:00.000Z",
    "start": {"date": "2026-03-17"},
    "end": {"date": "2026-03-18"},
}

MOCK_LIST_RESPONSE = {
    "items": [MOCK_EVENT_TIMED, MOCK_EVENT_ALL_DAY],
    "nextSyncToken": "sync_abc123",
}
```

### Step 8 — Unit tests

Use `_service_fn=` injection directly — no need for `unittest.mock.patch`. This is simpler and catches the real integration point (the query params passed to the service).

```python
# tests/unit/test_google_calendar_provider.py
import pytest
from unittest.mock import MagicMock
from iobox.providers.google_calendar import GoogleCalendarProvider
from iobox.providers.base import EventQuery
from tests.fixtures.mock_calendar_responses import MOCK_LIST_RESPONSE, MOCK_EVENT_TIMED

@pytest.fixture
def mock_svc():
    svc = MagicMock()
    svc.events().list().execute.return_value = MOCK_LIST_RESPONSE
    return svc

@pytest.fixture
def provider(mock_google_auth):
    return GoogleCalendarProvider(auth=mock_google_auth)

class TestGoogleCalendarProviderListEvents:
    def test_list_events_basic(self, provider, mock_svc):
        events = provider.list_events(EventQuery(max_results=10), _service_fn=mock_svc)
        assert len(events) == 2
        assert events[0]["resource_type"] == "event"
        assert events[0]["provider_id"] == "google_calendar"

    def test_list_events_passes_text_to_q_param(self, provider, mock_svc):
        provider.list_events(EventQuery(text="standup", max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert call_kwargs["q"] == "standup"

    def test_list_events_pagination(self, provider, mock_svc): ...

class TestEventNormalization:
    def test_timed_event_not_all_day(self): ...
    def test_all_day_event(self): ...
    def test_meeting_url_from_hangout_link(self): ...
    def test_meeting_url_from_conference_data(self): ...
    def test_attendees_mapped_correctly(self): ...
    def test_recurrence_rule_extracted(self): ...
```

## Verification

```bash
make test
python -c "from iobox.providers.google_calendar import GoogleCalendarProvider"
# With real credentials:
# iobox events list --after 2026-03-01 --before 2026-03-31
```

## Acceptance Criteria

- [ ] `GoogleCalendarProvider` in `src/iobox/providers/google_calendar.py`
- [ ] `list_events()` handles pagination, text search, date range filters
- [ ] `get_event()` returns single event
- [ ] `get_sync_state()` / `get_new_events()` implemented
- [ ] `_google_event_to_event()` correctly maps all-day events, meeting URLs, attendees
- [ ] Registered as `"google_calendar"` in `providers/__init__.py`
- [ ] Mock fixtures in `tests/fixtures/mock_calendar_responses.py`
- [ ] All unit tests pass
- [ ] Contract tests added in `test_provider_contract.py`
- [ ] `make type-check` passes
