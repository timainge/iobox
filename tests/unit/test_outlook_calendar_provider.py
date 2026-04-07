"""
Unit tests for OutlookCalendarProvider.

Uses lightweight mock O365 objects — no real O365 package calls.
The _get_account() method is monkeypatched so no real auth occurs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.base import EventQuery
from iobox.providers.o365.calendar import OutlookCalendarProvider, _strip_html

# ── Mock O365 helpers ─────────────────────────────────────────────────────────


class MockResponseStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class MockAttendee:
    def __init__(self, address: str, name: str | None = None, rs: str = "accepted") -> None:
        self.address = address
        self.name = name
        self.response_status = MockResponseStatus(rs)


class MockOrganizer:
    def __init__(self, address: str) -> None:
        self.address = address


class MockBody:
    def __init__(self, content: str) -> None:
        self.content = content


class MockLocation:
    def __init__(self, display_name: str) -> None:
        self.display_name = display_name


class MockO365Event:
    """Minimal mock of a python-o365 Event object."""

    def __init__(
        self,
        object_id: str = "evt_abc123",
        subject: str = "Team standup",
        is_all_day: bool = False,
        start: Any = None,
        end: Any = None,
        attendees: list[Any] | None = None,
        organizer: Any = None,
        body: Any = None,
        location: Any = None,
        online_meeting_url: str | None = None,
        web_link: str | None = "https://outlook.live.com/calendar/event/evt_abc123",
        created: datetime | None = None,
        modified: datetime | None = None,
    ) -> None:
        self.object_id = object_id
        self.subject = subject
        self.is_all_day = is_all_day
        self.start = start or datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        self.end = end or datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
        self.attendees = attendees or []
        self.organizer = organizer
        self.body = body or MockBody("")
        self.location = location
        self.online_meeting_url = online_meeting_url
        self.web_link = web_link
        self.created = created or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.modified = modified or datetime(2026, 3, 1, tzinfo=timezone.utc)


def _make_provider_with_account(mock_account: Any) -> OutlookCalendarProvider:
    """Build provider and bypass auth by injecting a mock account."""
    p = OutlookCalendarProvider.__new__(OutlookCalendarProvider)
    p.account_email = "user@company.com"
    p.credentials_dir = None
    p.mode = "readonly"
    p._account = mock_account
    return p


def _make_mock_account(events: list[Any]) -> MagicMock:
    """Build a minimal mock O365 Account that returns given events."""
    account = MagicMock()
    calendar = MagicMock()
    calendar.get_events.return_value = iter(events)
    schedule = MagicMock()
    schedule.get_default_calendar.return_value = calendar
    schedule.search_events.return_value = iter(events)
    account.schedule.return_value = schedule
    return account


# ── TestStripHtml ─────────────────────────────────────────────────────────────


class TestStripHtml:
    def test_removes_tags(self) -> None:
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self) -> None:
        assert _strip_html("<p>  Hello   world  </p>") == "Hello world"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""

    def test_no_tags(self) -> None:
        assert _strip_html("Plain text") == "Plain text"

    def test_nested_tags(self) -> None:
        result = _strip_html("<div><p><span>Nested</span></p></div>")
        assert result == "Nested"


# ── TestOutlookCalendarProviderInit ───────────────────────────────────────────


class TestOutlookCalendarProviderInit:
    def test_provider_id(self) -> None:
        p = OutlookCalendarProvider.__new__(OutlookCalendarProvider)
        p._account = MagicMock()
        assert OutlookCalendarProvider.PROVIDER_ID == "outlook_calendar"

    def test_raises_import_error_without_o365(self) -> None:
        with patch("iobox.providers.o365.calendar.HAS_O365", False):
            with pytest.raises(ImportError, match="pip install 'iobox\\[outlook\\]'"):
                OutlookCalendarProvider()


# ── TestListEvents ────────────────────────────────────────────────────────────


class TestListEvents:
    def test_list_events_basic(self) -> None:
        ev = MockO365Event()
        account = _make_mock_account([ev])
        p = _make_provider_with_account(account)
        events = p.list_events(EventQuery(max_results=10))
        assert len(events) == 1
        assert events[0]["resource_type"] == "event"
        assert events[0]["provider_id"] == "outlook_calendar"

    def test_list_events_title(self) -> None:
        ev = MockO365Event(subject="Project review")
        account = _make_mock_account([ev])
        p = _make_provider_with_account(account)
        events = p.list_events(EventQuery(max_results=10))
        assert events[0]["title"] == "Project review"

    def test_list_events_passes_limit(self) -> None:
        account = _make_mock_account([])
        p = _make_provider_with_account(account)
        p.list_events(EventQuery(max_results=5))
        schedule = account.schedule()
        schedule.get_default_calendar().get_events.assert_called_once()
        call_kwargs = schedule.get_default_calendar().get_events.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_list_events_with_after_passes_start(self) -> None:
        account = _make_mock_account([])
        p = _make_provider_with_account(account)
        p.list_events(EventQuery(after="2026-03-01", max_results=5))
        schedule = account.schedule()
        kwargs = schedule.get_default_calendar().get_events.call_args.kwargs
        assert "start" in kwargs
        assert kwargs["start"] == datetime(2026, 3, 1)

    def test_list_events_with_before_passes_end(self) -> None:
        account = _make_mock_account([])
        p = _make_provider_with_account(account)
        p.list_events(EventQuery(before="2026-03-31", max_results=5))
        schedule = account.schedule()
        kwargs = schedule.get_default_calendar().get_events.call_args.kwargs
        assert "end" in kwargs

    def test_list_events_text_uses_search_events(self) -> None:
        ev = MockO365Event(subject="Q4 planning")
        account = _make_mock_account([ev])
        p = _make_provider_with_account(account)
        events = p.list_events(EventQuery(text="Q4", max_results=10))
        schedule = account.schedule()
        schedule.search_events.assert_called_once()
        assert len(events) == 1

    def test_list_events_empty(self) -> None:
        account = _make_mock_account([])
        p = _make_provider_with_account(account)
        events = p.list_events(EventQuery(max_results=10))
        assert events == []

    def test_list_events_text_fallback_on_exception(self) -> None:
        """If search_events raises, fall back to get_events."""
        ev = MockO365Event()
        account = MagicMock()
        calendar = MagicMock()
        calendar.get_events.return_value = iter([ev])
        schedule = MagicMock()
        schedule.get_default_calendar.return_value = calendar
        schedule.search_events.side_effect = NotImplementedError("not supported")
        account.schedule.return_value = schedule
        p = _make_provider_with_account(account)
        events = p.list_events(EventQuery(text="test", max_results=5))
        assert len(events) == 1


# ── TestGetEvent ──────────────────────────────────────────────────────────────


class TestGetEvent:
    def test_get_event_by_id(self) -> None:
        ev = MockO365Event(object_id="evt_xyz", subject="Board meeting")
        account = MagicMock()
        schedule = MagicMock()
        schedule.get_event.return_value = ev
        account.schedule.return_value = schedule
        p = _make_provider_with_account(account)
        result = p.get_event("evt_xyz")
        assert result["id"] == "evt_xyz"
        assert result["title"] == "Board meeting"
        schedule.get_event.assert_called_once_with(object_id="evt_xyz")

    def test_get_event_not_found_raises(self) -> None:
        account = MagicMock()
        schedule = MagicMock()
        schedule.get_event.return_value = None
        account.schedule.return_value = schedule
        p = _make_provider_with_account(account)
        with pytest.raises(KeyError, match="evt_missing"):
            p.get_event("evt_missing")


# ── TestGetSyncState ──────────────────────────────────────────────────────────


class TestGetSyncState:
    def test_get_sync_state_returns_dict(self) -> None:
        p = _make_provider_with_account(MagicMock())
        result = p.get_sync_state()
        assert isinstance(result, dict)

    def test_get_new_events_returns_tuple(self) -> None:
        p = _make_provider_with_account(MagicMock())
        events, token = p.get_new_events("tok")
        assert events == []
        assert token == "tok"


# ── TestO365EventNormalization ────────────────────────────────────────────────


class TestO365EventNormalization:
    def _norm(self, ev: MockO365Event) -> dict:
        p = _make_provider_with_account(MagicMock())
        return p._o365_event_to_event(ev)

    def test_basic_fields(self) -> None:
        ev = MockO365Event(
            object_id="id1",
            subject="My event",
            web_link="https://outlook.live.com/ev1",
        )
        result = self._norm(ev)
        assert result["id"] == "id1"
        assert result["title"] == "My event"
        assert result["url"] == "https://outlook.live.com/ev1"
        assert result["provider_id"] == "outlook_calendar"
        assert result["resource_type"] == "event"

    def test_timed_event_uses_isoformat(self) -> None:
        dt = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        ev = MockO365Event(start=dt, end=dt, is_all_day=False)
        result = self._norm(ev)
        assert result["all_day"] is False
        assert "2026-03-15" in result["start"]

    def test_all_day_event_uses_date_format(self) -> None:
        class AllDayDatetime:
            def date(self) -> object:
                from datetime import date

                return date(2026, 3, 17)

            def isoformat(self) -> str:
                return "2026-03-17T00:00:00"

        ev = MockO365Event(
            is_all_day=True,
            start=AllDayDatetime(),
            end=AllDayDatetime(),
        )
        result = self._norm(ev)
        assert result["all_day"] is True
        assert result["start"] == "2026-03-17"

    def test_attendees_mapped(self) -> None:
        att1 = MockAttendee("tim@gmail.com", "Tim", "accepted")
        att2 = MockAttendee("alice@corp.com", "Alice", "tentative")
        ev = MockO365Event(attendees=[att1, att2])
        result = self._norm(ev)
        assert len(result["attendees"]) == 2
        assert result["attendees"][0]["email"] == "tim@gmail.com"
        assert result["attendees"][0]["response_status"] == "accepted"
        assert result["attendees"][1]["name"] == "Alice"

    def test_attendees_empty_list_when_none(self) -> None:
        ev = MockO365Event(attendees=None)
        result = self._norm(ev)
        assert result["attendees"] == []

    def test_organizer_email(self) -> None:
        ev = MockO365Event(organizer=MockOrganizer("boss@corp.com"))
        result = self._norm(ev)
        assert result["organizer"] == "boss@corp.com"

    def test_organizer_none_when_absent(self) -> None:
        ev = MockO365Event(organizer=None)
        result = self._norm(ev)
        assert result["organizer"] is None

    def test_html_stripped_from_description(self) -> None:
        ev = MockO365Event(body=MockBody("<p>Hello <b>world</b></p>"))
        result = self._norm(ev)
        assert result["description"] == "Hello world"

    def test_description_none_for_empty_body(self) -> None:
        ev = MockO365Event(body=MockBody(""))
        result = self._norm(ev)
        assert result["description"] is None

    def test_location_display_name(self) -> None:
        ev = MockO365Event(location=MockLocation("Conference room A"))
        result = self._norm(ev)
        assert result["location"] == "Conference room A"

    def test_location_none_when_absent(self) -> None:
        ev = MockO365Event(location=None)
        result = self._norm(ev)
        assert result["location"] is None

    def test_online_meeting_url_direct(self) -> None:
        ev = MockO365Event(online_meeting_url="https://teams.microsoft.com/l/meetup/123")
        result = self._norm(ev)
        assert result["meeting_url"] == "https://teams.microsoft.com/l/meetup/123"

    def test_teams_url_extracted_from_body(self) -> None:
        body_html = (
            '<p>Join: <a href="https://teams.microsoft.com/l/meetup/abc123">Click here</a></p>'
        )
        ev = MockO365Event(online_meeting_url=None, body=MockBody(body_html))
        result = self._norm(ev)
        assert result["meeting_url"] == "https://teams.microsoft.com/l/meetup/abc123"

    def test_meeting_url_none_when_no_teams_link(self) -> None:
        ev = MockO365Event(online_meeting_url=None, body=MockBody("<p>No meeting</p>"))
        result = self._norm(ev)
        assert result["meeting_url"] is None

    def test_status_always_confirmed(self) -> None:
        result = self._norm(MockO365Event())
        assert result["status"] == "confirmed"

    def test_recurrence_always_none(self) -> None:
        result = self._norm(MockO365Event())
        assert result["recurrence"] is None

    def test_created_at_and_modified_at(self) -> None:
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ev = MockO365Event(created=dt, modified=dt)
        result = self._norm(ev)
        assert "2026-01-01" in result["created_at"]
        assert "2026-01-01" in result["modified_at"]

    def test_no_subject_falls_back_to_no_title(self) -> None:
        ev = MockO365Event(subject="")
        result = self._norm(ev)
        assert result["title"] == "(no title)"
