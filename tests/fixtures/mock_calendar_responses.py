"""
Mock Google Calendar API responses for unit tests.
"""

from __future__ import annotations

MOCK_EVENT_TIMED: dict = {
    "id": "evt001",
    "summary": "Team standup",
    "status": "confirmed",
    "htmlLink": "https://calendar.google.com/event?eid=evt001",
    "created": "2026-01-01T10:00:00.000Z",
    "updated": "2026-03-01T09:00:00.000Z",
    "start": {"dateTime": "2026-03-15T09:00:00-07:00"},
    "end": {"dateTime": "2026-03-15T09:30:00-07:00"},
    "organizer": {"email": "boss@example.com", "displayName": "Boss"},
    "attendees": [
        {"email": "tim@gmail.com", "responseStatus": "accepted"},
        {"email": "alice@gmail.com", "displayName": "Alice", "responseStatus": "tentative"},
    ],
    "description": "Daily standup meeting",
    "location": "Zoom",
    "hangoutLink": "https://meet.google.com/abc-defg",
    "recurrence": ["RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"],
}

MOCK_EVENT_ALL_DAY: dict = {
    "id": "evt002",
    "summary": "Company holiday",
    "status": "confirmed",
    "htmlLink": "https://calendar.google.com/event?eid=evt002",
    "created": "2026-01-01T00:00:00.000Z",
    "updated": "2026-01-01T00:00:00.000Z",
    "start": {"date": "2026-03-17"},
    "end": {"date": "2026-03-18"},
}

MOCK_EVENT_CONFERENCE_DATA: dict = {
    "id": "evt003",
    "summary": "Zoom call",
    "status": "confirmed",
    "created": "2026-02-01T00:00:00.000Z",
    "updated": "2026-02-01T00:00:00.000Z",
    "start": {"dateTime": "2026-03-20T14:00:00Z"},
    "end": {"dateTime": "2026-03-20T15:00:00Z"},
    "conferenceData": {
        "entryPoints": [
            {"entryPointType": "video", "uri": "https://zoom.us/j/12345"},
            {"entryPointType": "phone", "uri": "tel:+1234567890"},
        ]
    },
}

MOCK_LIST_RESPONSE: dict = {
    "items": [MOCK_EVENT_TIMED, MOCK_EVENT_ALL_DAY],
    "nextSyncToken": "sync_abc123",
}

MOCK_LIST_RESPONSE_PAGINATED_PAGE1: dict = {
    "items": [MOCK_EVENT_TIMED],
    "nextPageToken": "page_token_2",
}

MOCK_LIST_RESPONSE_PAGINATED_PAGE2: dict = {
    "items": [MOCK_EVENT_ALL_DAY],
    "nextSyncToken": "sync_abc456",
}

MOCK_SYNC_RESPONSE: dict = {
    "items": [MOCK_EVENT_TIMED],
    "nextSyncToken": "sync_new_token",
}
