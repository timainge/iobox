"""
Unit tests for CalendarProvider write operations.

Tests GoogleCalendarProvider and OutlookCalendarProvider write methods
using the _service_fn= injection pattern (no real API calls).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

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
    def test_create_timed_event(self) -> None:
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
        assert body["start"]["dateTime"] == "2026-04-01T10:00:00"
        assert body["end"]["dateTime"] == "2026-04-01T11:00:00"

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
        event = provider.update_event("evt1", {"summary": "Updated Title"}, _service_fn=svc)
        svc.events.return_value.patch.assert_called_once()
        assert event["id"] == "evt1"

    def test_update_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.update_event("evt1", {"summary": "X"})


# ── GoogleCalendarProvider: delete_event ─────────────────────────────────────


class TestGoogleCalendarDeleteEvent:
    def test_delete_event(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.delete_event("evt1", _service_fn=svc)
        svc.events.return_value.delete.assert_called_once()

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

    def test_rsvp_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.rsvp("evt1", "accepted")


# ── OutlookCalendarProvider write ops ────────────────────────────────────────


class TestOutlookCalendarWriteOps:
    """Smoke tests for OutlookCalendarProvider write methods using HAS_O365 patch."""

    _MODULE = "iobox.providers.o365.calendar"

    def _make_provider(self, mode: str = "standard") -> Any:  # type: ignore[name-defined]
        from iobox.providers.o365.calendar import OutlookCalendarProvider

        auth = MagicMock()
        account = MagicMock()
        auth.get_account.return_value = account
        with patch(f"{self._MODULE}.HAS_O365", True):
            provider = OutlookCalendarProvider.__new__(OutlookCalendarProvider)
            provider.account_email = "user@example.com"
            provider.credentials_dir = None
            provider.mode = mode
            provider._microsoft_auth = auth
            provider._account = None
        return provider

    def _make_o365_event(self) -> MagicMock:
        ev = MagicMock()
        ev.subject = "Test Event"
        ev.object_id = "evt-o365-1"
        ev.is_all_day = False
        ev.start = MagicMock()
        ev.start.isoformat.return_value = "2026-04-01T10:00:00"
        ev.end = MagicMock()
        ev.end.isoformat.return_value = "2026-04-01T11:00:00"
        ev.attendees = []
        ev.organizer = None
        ev.online_meeting_url = None
        ev.body = MagicMock()
        ev.body.content = ""
        ev.location = None
        ev.created = None
        ev.modified = None
        ev.web_link = None
        return ev

    def test_check_write_mode_raises_in_readonly(self) -> None:
        from iobox.providers.o365.calendar import OutlookCalendarProvider

        with patch(f"{self._MODULE}.HAS_O365", True):
            provider = OutlookCalendarProvider.__new__(OutlookCalendarProvider)
            provider.mode = "readonly"
        with pytest.raises(PermissionError):
            provider._check_write_mode()

    def test_create_event(self) -> None:
        provider = self._make_provider()
        o365_ev = self._make_o365_event()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_default_calendar().new_event.return_value = o365_ev
        event = provider.create_event("Test Event", "2026-04-01T10:00:00", "2026-04-01T11:00:00")
        assert event["title"] == "Test Event"
        o365_ev.save.assert_called_once()

    def test_delete_event(self) -> None:
        provider = self._make_provider()
        o365_ev = self._make_o365_event()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_event.return_value = o365_ev
        provider.delete_event("evt-o365-1")
        o365_ev.delete.assert_called_once()

    def test_rsvp_accepted(self) -> None:
        provider = self._make_provider()
        o365_ev = self._make_o365_event()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_event.return_value = o365_ev
        event = provider.rsvp("evt-o365-1", "accepted")
        o365_ev.accept.assert_called_once()
        assert event["id"] == "evt-o365-1"

    def test_rsvp_declined(self) -> None:
        provider = self._make_provider()
        o365_ev = self._make_o365_event()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_event.return_value = o365_ev
        provider.rsvp("evt-o365-1", "declined")
        o365_ev.decline.assert_called_once()

    def test_rsvp_tentative(self) -> None:
        provider = self._make_provider()
        o365_ev = self._make_o365_event()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_event.return_value = o365_ev
        provider.rsvp("evt-o365-1", "tentative")
        o365_ev.tentatively_accept.assert_called_once()

    def test_rsvp_invalid_response_raises(self) -> None:
        provider = self._make_provider()
        o365_ev = self._make_o365_event()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_event.return_value = o365_ev
        with pytest.raises(ValueError, match="Unknown RSVP"):
            provider.rsvp("evt-o365-1", "maybe")

    def test_rsvp_not_found_raises(self) -> None:
        provider = self._make_provider()
        account = provider._microsoft_auth.get_account.return_value
        account.schedule().get_event.return_value = None
        with pytest.raises(KeyError, match="not found"):
            provider.rsvp("missing-id", "accepted")

    def test_create_blocked_in_readonly(self) -> None:
        provider = self._make_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.create_event("X", "2026-04-01T10:00:00", "2026-04-01T11:00:00")
