"""
Unit tests for CalendarProvider write operations.

Tests GoogleCalendarProvider and OutlookCalendarProvider write methods
using the _service_fn= injection pattern (no real API calls).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from iobox.providers.google.calendar import GoogleCalendarProvider

# ── Helpers ───────────────────────────────────────────────────────────────────

_GCal_MODULE = "iobox.providers.google.calendar"
_OutlookCal_MODULE = "iobox.providers.o365.calendar"


def _make_google_event_raw(
    event_id: str = "evt1",
    title: str = "Team Meeting",
    attendees: list[dict] | None = None,
) -> dict:
    return {
        "id": event_id,
        "summary": title,
        "start": {"dateTime": "2026-04-01T10:00:00Z"},
        "end": {"dateTime": "2026-04-01T11:00:00Z"},
        "attendees": attendees or [],
        "created": "2026-03-01T00:00:00Z",
        "updated": "2026-03-01T00:00:00Z",
        "status": "confirmed",
    }


@pytest.fixture
def sydney_tz(monkeypatch: pytest.MonkeyPatch):
    """Pin the process local timezone (AEDT +11 / AEST +10) for offset tests."""
    import time

    monkeypatch.setenv("TZ", "Australia/Sydney")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _http_error(status: int) -> Exception:
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = status
    resp.reason = "err"
    return HttpError(resp, b"{}")


def _make_google_provider(mode: str = "standard") -> GoogleCalendarProvider:
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return GoogleCalendarProvider(auth=auth, mode=mode)


def _make_service(raw_event: dict | None = None) -> MagicMock:
    svc = MagicMock()
    raw = raw_event or _make_google_event_raw()
    # Configure return values without pre-calling the method (avoids inflating call counts)
    svc.events.return_value.insert.return_value.execute.return_value = raw
    svc.events.return_value.patch.return_value.execute.return_value = raw
    svc.events.return_value.get.return_value.execute.return_value = raw
    svc.events.return_value.delete.return_value.execute.return_value = None
    svc.calendarList.return_value.get.return_value.execute.return_value = {
        "id": "me@example.com",
        "summary": "Me",
    }
    return svc


# ── GoogleCalendarProvider: _check_write_mode ─────────────────────────────────


class TestGoogleCalendarWriteMode:
    def test_write_raises_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError, match="mode='standard'"):
            provider._check_write_mode()

    def test_write_allowed_in_standard(self) -> None:
        provider = _make_google_provider(mode="standard")
        provider._check_write_mode()  # should not raise


# ── GoogleCalendarProvider: create_event ─────────────────────────────────────


class TestGoogleCalendarCreateEvent:
    def test_create_timed_event(self, sydney_tz: None) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        event = provider.create_event(
            "Team Meeting",
            "2026-04-01T10:00:00",
            "2026-04-01T11:00:00",
            _service_fn=svc,
        )
        assert event["title"] == "Team Meeting"
        svc.events.return_value.insert.assert_called_once()
        call_kwargs = svc.events.return_value.insert.call_args[1]
        body = call_kwargs["body"]
        # TIME-02: offset-less times are local (AEDT on 1 April 2026), not UTC.
        assert body["start"] == {"dateTime": "2026-04-01T10:00:00+11:00"}
        assert body["end"] == {"dateTime": "2026-04-01T11:00:00+11:00"}

    def test_create_timed_event_uses_local_dst_offset(self, sydney_tz: None) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.create_event("Winter", "2026-07-01T09:00", "2026-07-01T10:00", _service_fn=svc)
        body = svc.events.return_value.insert.call_args[1]["body"]
        assert body["start"]["dateTime"] == "2026-07-01T09:00:00+10:00"
        assert "timeZone" not in body["start"]

    def test_create_timed_event_keeps_explicit_offset(self, sydney_tz: None) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.create_event(
            "UTC", "2026-04-01T10:00:00Z", "2026-04-01T11:00:00-05:00", _service_fn=svc
        )
        body = svc.events.return_value.insert.call_args[1]["body"]
        assert body["start"]["dateTime"] == "2026-04-01T10:00:00+00:00"
        assert body["end"]["dateTime"] == "2026-04-01T11:00:00-05:00"

    def test_create_on_named_calendar(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.create_event(
            "X", "2026-04-01", "2026-04-02", all_day=True, calendar_id="team@x", _service_fn=svc
        )
        assert svc.events.return_value.insert.call_args[1]["calendarId"] == "team@x"

    def test_create_all_day_event(self) -> None:
        provider = _make_google_provider()
        svc = _make_service(_make_google_event_raw(title="All Day"))
        provider.create_event(
            "All Day",
            "2026-04-01",
            "2026-04-02",
            all_day=True,
            _service_fn=svc,
        )
        call_kwargs = svc.events.return_value.insert.call_args[1]
        body = call_kwargs["body"]
        assert "date" in body["start"]
        assert "dateTime" not in body["start"]

    def test_create_with_attendees(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.create_event(
            "Meeting",
            "2026-04-01T10:00:00",
            "2026-04-01T11:00:00",
            attendees=["alice@example.com", "bob@example.com"],
            _service_fn=svc,
        )
        call_kwargs = svc.events.return_value.insert.call_args[1]
        body = call_kwargs["body"]
        assert {"email": "alice@example.com"} in body["attendees"]

    def test_create_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.create_event("X", "2026-04-01T10:00:00", "2026-04-01T11:00:00")

    def test_create_with_description_and_location(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.create_event(
            "All Hands",
            "2026-04-01T09:00:00",
            "2026-04-01T10:00:00",
            description="Quarterly review",
            location="Conference Room A",
            _service_fn=svc,
        )
        body = svc.events.return_value.insert.call_args[1]["body"]
        assert body["description"] == "Quarterly review"
        assert body["location"] == "Conference Room A"


# ── GoogleCalendarProvider: update_event ─────────────────────────────────────


class TestGoogleCalendarUpdateEvent:
    def test_update_event(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        event = provider.update_event("evt1", {"title": "Updated Title"}, _service_fn=svc)
        svc.events.return_value.patch.assert_called_once()
        assert svc.events.return_value.patch.call_args[1]["body"] == {"summary": "Updated Title"}
        assert event["id"] == "evt1"

    def test_update_maps_normalised_keys(self, sydney_tz: None) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.update_event(
            "evt1",
            {
                "title": "T",
                "start": "2026-04-01T09:00",
                "end": "2026-04-01T10:00:00Z",
                "description": "D",
                "location": "L",
                "attendees": ["a@x.com", "b@x.com"],
            },
            _service_fn=svc,
        )
        body = svc.events.return_value.patch.call_args[1]["body"]
        assert body == {
            "summary": "T",
            "start": {"dateTime": "2026-04-01T09:00:00+11:00", "date": None},
            "end": {"dateTime": "2026-04-01T10:00:00+00:00", "date": None},
            "description": "D",
            "location": "L",
            "attendees": [{"email": "a@x.com"}, {"email": "b@x.com"}],
        }

    def test_update_date_only_becomes_all_day(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.update_event("evt1", {"start": "2026-04-01", "end": "2026-04-02"}, _service_fn=svc)
        body = svc.events.return_value.patch.call_args[1]["body"]
        assert body["start"] == {"date": "2026-04-01", "dateTime": None}
        assert body["end"] == {"date": "2026-04-02", "dateTime": None}

    def test_update_unknown_key_raises(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        with pytest.raises(ValueError, match="summary"):
            provider.update_event("evt1", {"summary": "raw google key"}, _service_fn=svc)
        svc.events.return_value.patch.assert_not_called()

    def test_update_named_calendar(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.update_event("evt1", {"title": "x"}, calendar_id="team@x", _service_fn=svc)
        assert svc.events.return_value.patch.call_args[1]["calendarId"] == "team@x"

    def test_update_missing_event_raises_key_error(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        svc.events.return_value.patch.return_value.execute.side_effect = _http_error(404)
        with pytest.raises(KeyError):
            provider.update_event("nope", {"title": "x"}, _service_fn=svc)

    def test_update_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.update_event("evt1", {"title": "X"})


# ── GoogleCalendarProvider: delete_event ─────────────────────────────────────


class TestGoogleCalendarDeleteEvent:
    def test_delete_event(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.delete_event("evt1", _service_fn=svc)
        svc.events.return_value.delete.assert_called_once()

    def test_delete_named_calendar(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.delete_event("evt1", calendar_id="team@x", _service_fn=svc)
        svc.events.return_value.delete.assert_called_once_with(calendarId="team@x", eventId="evt1")

    def test_delete_missing_event_raises_key_error(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        svc.events.return_value.delete.return_value.execute.side_effect = _http_error(404)
        with pytest.raises(KeyError):
            provider.delete_event("nope", _service_fn=svc)

    def test_delete_other_http_error_propagates(self) -> None:
        from googleapiclient.errors import HttpError

        provider = _make_google_provider()
        svc = _make_service()
        svc.events.return_value.delete.return_value.execute.side_effect = _http_error(403)
        with pytest.raises(HttpError):
            provider.delete_event("evt1", _service_fn=svc)

    def test_delete_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.delete_event("evt1")


# ── GoogleCalendarProvider: rsvp ─────────────────────────────────────────────


class TestGoogleCalendarRsvp:
    def _provider_and_service(self, my_email: str = "me@example.com") -> tuple:
        provider = _make_google_provider()
        raw = _make_google_event_raw(
            attendees=[{"email": my_email, "responseStatus": "needsAction"}]
        )
        svc = _make_service(raw)
        # profile call returns my_email
        svc.calendarList.return_value.get.return_value.execute.return_value = {
            "id": my_email,
            "summary": "Me",
        }
        return provider, svc

    def test_accept(self) -> None:
        provider, svc = self._provider_and_service()
        provider.rsvp("evt1", "accepted", _service_fn=svc)
        patch_body = svc.events.return_value.patch.call_args[1]["body"]
        assert patch_body["attendees"][0]["responseStatus"] == "accepted"

    def test_declined(self) -> None:
        provider, svc = self._provider_and_service()
        provider.rsvp("evt1", "declined", _service_fn=svc)
        patch_body = svc.events.return_value.patch.call_args[1]["body"]
        assert patch_body["attendees"][0]["responseStatus"] == "declined"

    def test_tentative(self) -> None:
        provider, svc = self._provider_and_service()
        provider.rsvp("evt1", "tentative", _service_fn=svc)
        patch_body = svc.events.return_value.patch.call_args[1]["body"]
        assert patch_body["attendees"][0]["responseStatus"] == "tentative"

    def test_user_not_attendee_raises(self) -> None:
        provider = _make_google_provider()
        raw = _make_google_event_raw(
            attendees=[{"email": "other@example.com", "responseStatus": "accepted"}]
        )
        svc = _make_service(raw)
        svc.calendarList.return_value.get.return_value.execute.return_value = {
            "id": "me@example.com",
            "summary": "Me",
        }
        with pytest.raises(ValueError, match="not an attendee"):
            provider.rsvp("evt1", "accepted", _service_fn=svc)

    def test_rsvp_named_calendar_and_missing_event(self) -> None:
        provider, svc = self._provider_and_service()
        provider.rsvp("evt1", "accepted", calendar_id="team@x", _service_fn=svc)
        assert svc.events.return_value.get.call_args[1]["calendarId"] == "team@x"
        assert svc.events.return_value.patch.call_args[1]["calendarId"] == "team@x"
        svc.events.return_value.get.return_value.execute.side_effect = _http_error(404)
        with pytest.raises(KeyError):
            provider.rsvp("gone", "accepted", _service_fn=svc)

    def test_rsvp_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.rsvp("evt1", "accepted")


# ── OutlookCalendarProvider write ops ────────────────────────────────────────


class TestOutlookCalendarWriteOps:
    """OutlookCalendarProvider writes on real python-o365 Event objects over a
    fake Graph session (skipped without the outlook extra)."""

    @staticmethod
    def _provider(events: list[dict] | None = None, mode: str = "standard") -> Any:
        from tests.fixtures.mock_outlook_responses import graph_event, make_calendar_provider

        return make_calendar_provider(
            events if events is not None else [graph_event("evt-o365-1", subject="Test Event")],
            mode=mode,
        )

    def test_create_event(self) -> None:
        p = self._provider([])
        event = p.create_event(
            "Planning",
            "2026-04-01T10:00:00+11:00",  # fixed offset: python-o365 only accepts ZoneInfo
            "2026-04-01T11:00:00+11:00",
            description="Agenda",
            location="Room 1",
            attendees=["a@x.com", "b@x.com"],
        )
        body = p.graph.last("POST", r"/me/calendars/cal-default/events").body
        assert body["subject"] == "Planning"
        assert body["start"] == {"dateTime": "2026-03-31T23:00:00", "timeZone": "UTC"}
        assert body["end"] == {"dateTime": "2026-04-01T00:00:00", "timeZone": "UTC"}
        assert body["body"] == {"contentType": "text", "content": "Agenda"}
        assert body["location"] == {"displayName": "Room 1"}
        assert [a["emailAddress"]["address"] for a in body["attendees"]] == ["a@x.com", "b@x.com"]
        assert event["title"] == "Planning"
        assert event["id"] == "new-evt-1"

    def test_create_all_day_event(self) -> None:
        p = self._provider([])
        p.create_event("Holiday", "2026-04-01", "2026-04-02", all_day=True)
        body = p.graph.last("POST", r"/me/calendars/cal-default/events").body
        assert body["isAllDay"] is True
        assert body["start"]["dateTime"] == "2026-04-01T00:00:00"
        assert body["end"]["dateTime"] == "2026-04-02T00:00:00"

    def test_update_event_maps_iobox_fields(self) -> None:
        """O365-14: the old code setattr'd raw keys ("title" is not an Event attribute)."""
        p = self._provider()
        result = p.update_event(
            "evt-o365-1",
            {"title": "Renamed", "description": "New notes", "location": "Room 9"},
        )
        body = p.graph.last("PATCH", r"/me/events/evt-o365-1").body
        assert body["subject"] == "Renamed"
        assert body["body"] == {"contentType": "text", "content": "New notes"}
        assert body["location"] == {"displayName": "Room 9"}
        assert "start" not in body  # only changed fields are patched
        assert result["title"] == "Renamed"

    def test_update_event_times(self) -> None:
        p = self._provider()
        p.update_event("evt-o365-1", {"start": "2026-05-01T09:00:00", "end": "2026-05-01T10:00:00"})
        body = p.graph.last("PATCH", r"/me/events/evt-o365-1").body
        assert body["start"]["dateTime"] == "2026-05-01T09:00:00"
        assert body["end"]["dateTime"] == "2026-05-01T10:00:00"

    def test_update_event_rejects_unknown_fields(self) -> None:
        p = self._provider()
        with pytest.raises(ValueError, match="colorId"):
            p.update_event("evt-o365-1", {"colorId": "5"})
        assert not p.graph.find("PATCH", r"/me/events/.*")

    def test_delete_event(self) -> None:
        p = self._provider()
        p.delete_event("evt-o365-1")
        p.graph.last("DELETE", r"/me/events/evt-o365-1")

    def test_delete_missing_event_is_noop(self) -> None:
        p = self._provider([])
        p.delete_event("missing")
        assert not p.graph.find("DELETE", r".*")

    @pytest.mark.parametrize(
        ("response", "endpoint", "status"),
        [
            ("accepted", "accept", "accepted"),
            ("declined", "decline", "declined"),
            ("tentative", "tentativelyAccept", "tentativelyAccepted"),
        ],
    )
    def test_rsvp(self, response: str, endpoint: str, status: str) -> None:
        """O365-03: Event.accept/decline/tentatively_accept do not exist."""
        p = self._provider()
        event = p.rsvp("evt-o365-1", response)
        p.graph.last("POST", rf"/me/events/evt-o365-1/{endpoint}")
        assert p.events["evt-o365-1"]["responseStatus"]["response"] == status
        assert event["id"] == "evt-o365-1"

    def test_rsvp_invalid_response_raises(self) -> None:
        p = self._provider()
        with pytest.raises(ValueError, match="Unknown RSVP"):
            p.rsvp("evt-o365-1", "maybe")

    def test_rsvp_not_found_raises(self) -> None:
        p = self._provider([])
        with pytest.raises(KeyError, match="not found"):
            p.rsvp("missing-id", "accepted")

    def test_writes_blocked_in_readonly(self) -> None:
        p = self._provider(mode="readonly")
        with pytest.raises(PermissionError):
            p.create_event("X", "2026-04-01T10:00:00", "2026-04-01T11:00:00")
        with pytest.raises(PermissionError):
            p.update_event("evt-o365-1", {"title": "x"})
        with pytest.raises(PermissionError):
            p.rsvp("evt-o365-1", "accepted")
        assert not p.graph.calls
