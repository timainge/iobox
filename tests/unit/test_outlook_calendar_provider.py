"""
Unit tests for OutlookCalendarProvider.

The provider runs on the **real** python-o365 ``Schedule`` / ``Calendar`` /
``Event`` classes over a fake Graph session
(:func:`tests.fixtures.mock_outlook_responses.make_calendar_provider`), so a
call to a method python-o365 does not have — ``Schedule.search_events``,
``Schedule.get_event``, ``Event.accept`` … — fails here as it would live.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from iobox.providers.base import EventQuery
from iobox.providers.o365.calendar import OutlookCalendarProvider, _strip_html
from tests.fixtures.mock_outlook_responses import graph_event, make_calendar_provider

CAL_VIEW = r"/me/calendars/cal-default/calendarView"


class TestStripHtml:
    def test_removes_tags(self) -> None:
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self) -> None:
        assert _strip_html("<p>a</p>\n\n<p>b</p>") == "a b"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""


class TestInit:
    def test_provider_id(self) -> None:
        assert OutlookCalendarProvider.PROVIDER_ID == "outlook_calendar"

    def test_raises_import_error_without_o365(self) -> None:
        with (
            patch("iobox.providers.o365.calendar.HAS_O365", False),
            pytest.raises(ImportError, match="O365"),
        ):
            OutlookCalendarProvider()

    def test_legacy_path_requests_calendar_scopes_for_mode(self, tmp_path) -> None:
        pytest.importorskip("O365")
        p = OutlookCalendarProvider(account_email="a@b.com", credentials_dir=str(tmp_path))
        with patch("iobox.providers.o365.auth.MicrosoftAuth") as auth_cls:
            p.authenticate()
        kwargs = auth_cls.call_args.kwargs
        assert kwargs["scopes"] == ["basic", "Calendars.Read"]
        assert kwargs["mode"] == "readonly"
        assert kwargs["credentials_dir"] == str(tmp_path)


# ---------------------------------------------------------------------------
# list_events (O365-02)
# ---------------------------------------------------------------------------


class TestListEvents:
    def test_uses_calendar_view_with_required_window(self) -> None:
        """The old call passed start=/end= (unknown kwargs); python-o365's
        include_recurring=True requires start_recurring/end_recurring and
        raised ValueError on every call."""
        p = make_calendar_provider([graph_event()])
        events = p.list_events(EventQuery(after="2026-03-01", before="2026-04-01", max_results=5))
        assert [e["title"] for e in events] == ["Team standup"]
        call = p.graph.last("GET", CAL_VIEW)
        assert call.params["startDateTime"].startswith("2026-03-01T00:00:00")
        assert call.params["endDateTime"].startswith("2026-04-01T00:00:00")
        assert call.params["$top"] == 5
        assert call.params["$orderby"] == "start/dateTime"

    def test_default_window_when_unbounded(self) -> None:
        from datetime import datetime

        p = make_calendar_provider([])
        p.list_events(EventQuery())
        params = p.graph.last("GET", CAL_VIEW).params
        start = datetime.fromisoformat(params["startDateTime"])
        end = datetime.fromisoformat(params["endDateTime"])
        assert 364 <= (end - start).days <= 366

    def test_only_before(self) -> None:
        p = make_calendar_provider([])
        p.list_events(EventQuery(before="2026-06-01"))
        params = p.graph.last("GET", CAL_VIEW).params
        assert params["startDateTime"].startswith("2025-06-01")

    def test_text_is_filtered_client_side(self) -> None:
        """Graph events have no $search and Schedule.search_events does not exist."""
        p = make_calendar_provider(
            [
                graph_event("e1", subject="Budget review"),
                graph_event("e2", subject="Lunch", location="Budget café"),
                graph_event("e3", subject="Standup"),
            ]
        )
        events = p.list_events(EventQuery(text="budget", max_results=10))
        assert [e["id"] for e in events] == ["e1", "e2"]
        call = p.graph.last("GET", CAL_VIEW)
        assert "$search" not in call.params and "$filter" not in call.params

    def test_text_respects_max_results(self) -> None:
        p = make_calendar_provider([graph_event(f"e{i}", subject="x") for i in range(5)])
        assert len(p.list_events(EventQuery(text="x", max_results=2))) == 2

    def test_requests_carry_immutable_id_and_timezone_prefer(self) -> None:
        p = make_calendar_provider([graph_event()])
        p.list_events(EventQuery(after="2026-03-01", before="2026-04-01"))
        for call in p.graph.calls:
            assert 'IdType="ImmutableId"' in call.headers["Prefer"]


class TestGetEvent:
    def test_get_event_fetches_me_events(self) -> None:
        """O365-03: Schedule.get_event does not exist."""
        p = make_calendar_provider([graph_event("evt-9", subject="Planning")])
        ev = p.get_event("evt-9")
        assert ev["id"] == "evt-9"
        assert ev["title"] == "Planning"
        p.graph.last("GET", r"/me/events/evt-9")

    def test_not_found_raises_key_error(self) -> None:
        p = make_calendar_provider([])
        with pytest.raises(KeyError):
            p.get_event("missing")


# ---------------------------------------------------------------------------
# Normalisation (O365-10)
# ---------------------------------------------------------------------------


class TestNormalization:
    def _one(self, **kw) -> dict:
        p = make_calendar_provider([graph_event("e", **kw)])
        return dict(p.get_event("e"))

    def test_basic_fields(self) -> None:
        ev = self._one()
        assert ev["provider_id"] == "outlook_calendar"
        assert ev["resource_type"] == "event"
        assert ev["start"] == "2026-03-15T09:00:00+00:00"
        assert ev["end"] == "2026-03-15T09:30:00+00:00"
        assert ev["all_day"] is False
        assert ev["organizer"] == "org@example.com"
        assert ev["created_at"].startswith("2026-01-01")
        assert ev["url"].endswith("itemid=e")
        assert ev["status"] == "confirmed"

    def test_all_day_uses_dates(self) -> None:
        ev = self._one(
            start="2026-03-15T00:00:00.0000000", end="2026-03-16T00:00:00.0000000", is_all_day=True
        )
        assert (ev["start"], ev["end"], ev["all_day"]) == ("2026-03-15", "2026-03-16", True)

    def test_location_from_dict(self) -> None:
        """Event.location is the Graph dict; the old code read .display_name → always None."""
        assert self._one(location="Room 4")["location"] == "Room 4"
        assert self._one()["location"] is None

    def test_description_from_string_body(self) -> None:
        """Event.body is a str; the old code read body.content → always None."""
        assert self._one(body="<p>Agenda: <b>roadmap</b></p>")["description"] == "Agenda: roadmap"
        assert self._one(body="plain\ntext", content_type="text")["description"] == "plain\ntext"
        assert self._one(body="")["description"] is None

    def test_attendee_response_status(self) -> None:
        """Attendee.response_status.status is an EventResponse enum; the old
        code read .value on the ResponseStatus object → always None."""
        ev = self._one(
            attendees=[
                ("Ann", "ann@x.com", "accepted"),
                ("Bob", "bob@x.com", "tentativelyAccepted"),
                ("Cy", "cy@x.com", "declined"),
                ("Di", "di@x.com", "notResponded"),
                ("Ed", "ed@x.com", "none"),
            ]
        )
        assert [(a["email"], a["response_status"]) for a in ev["attendees"]] == [
            ("ann@x.com", "accepted"),
            ("bob@x.com", "tentative"),
            ("cy@x.com", "declined"),
            ("di@x.com", "needsAction"),
            ("ed@x.com", None),
        ]
        assert ev["attendees"][0]["name"] == "Ann"

    def test_teams_url_from_body(self) -> None:
        ev = self._one(body='<a href="https://teams.microsoft.com/l/meetup-join/abc">Join</a>')
        assert ev["meeting_url"] == "https://teams.microsoft.com/l/meetup-join/abc"

    def test_online_meeting_url_preferred(self) -> None:
        assert self._one(online_meeting_url="https://x/meet")["meeting_url"] == "https://x/meet"

    def test_cancelled(self) -> None:
        assert self._one(is_cancelled=True)["status"] == "cancelled"

    def test_no_subject(self) -> None:
        assert self._one(subject="")["title"] == "(no title)"


# ---------------------------------------------------------------------------
# Sync stubs
# ---------------------------------------------------------------------------


class TestSyncStubs:
    def test_get_sync_state_returns_dict(self) -> None:
        assert make_calendar_provider([]).get_sync_state() == {}

    def test_get_new_events_returns_tuple(self) -> None:
        assert make_calendar_provider([]).get_new_events("tok") == ([], "tok")
