"""
Unit tests for GoogleCalendarProvider.

Uses _service_fn= injection so no real OAuth or googleapiclient calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iobox.providers.base import EventQuery
from iobox.providers.google_calendar import GoogleCalendarProvider, _to_rfc3339
from tests.fixtures.mock_calendar_responses import (
    MOCK_EVENT_ALL_DAY,
    MOCK_EVENT_CONFERENCE_DATA,
    MOCK_EVENT_TIMED,
    MOCK_LIST_RESPONSE,
    MOCK_LIST_RESPONSE_PAGINATED_PAGE1,
    MOCK_LIST_RESPONSE_PAGINATED_PAGE2,
    MOCK_SYNC_RESPONSE,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return auth


@pytest.fixture
def provider(mock_auth: MagicMock) -> GoogleCalendarProvider:
    return GoogleCalendarProvider(auth=mock_auth)


@pytest.fixture
def mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.events().list().execute.return_value = MOCK_LIST_RESPONSE
    return svc


# ── TestToRfc3339 ──────────────────────────────────────────────────────────────


class TestToRfc3339:
    def test_date_only_appends_time(self) -> None:
        assert _to_rfc3339("2026-03-15") == "2026-03-15T00:00:00Z"

    def test_datetime_passthrough(self) -> None:
        dt = "2026-03-15T09:00:00Z"
        assert _to_rfc3339(dt) == dt


# ── TestGoogleCalendarProviderInit ────────────────────────────────────────────


class TestGoogleCalendarProviderInit:
    def test_accepts_auth_directly(self, mock_auth: MagicMock) -> None:
        p = GoogleCalendarProvider(auth=mock_auth)
        assert p._auth is mock_auth

    def test_creates_auth_from_account_params(self, tmp_path: object) -> None:

        from iobox.providers.google_auth import GoogleAuth

        p = GoogleCalendarProvider(
            account="test@gmail.com",
            credentials_dir=str(tmp_path),  # type: ignore[arg-type]
            mode="readonly",
        )
        assert isinstance(p._auth, GoogleAuth)
        assert p._auth.account == "test@gmail.com"

    def test_provider_id(self, provider: GoogleCalendarProvider) -> None:
        assert provider.PROVIDER_ID == "google_calendar"


# ── TestAuthenticate ──────────────────────────────────────────────────────────


class TestAuthenticate:
    def test_authenticate_calls_get_credentials(
        self, provider: GoogleCalendarProvider, mock_auth: MagicMock
    ) -> None:
        provider.authenticate()
        mock_auth.get_credentials.assert_called_once()


# ── TestGetProfile ────────────────────────────────────────────────────────────


class TestGetProfile:
    def test_get_profile_returns_email_and_name(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.calendarList().get().execute.return_value = {
            "id": "tim@gmail.com",
            "summary": "Tim's Calendar",
        }
        result = provider.get_profile(_service_fn=svc)
        assert result["email"] == "tim@gmail.com"
        assert result["display_name"] == "Tim's Calendar"

    def test_get_profile_calls_calendar_list_get(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        provider.get_profile(_service_fn=svc)
        svc.calendarList().get.assert_called_once_with(calendarId="primary")


# ── TestListEvents ────────────────────────────────────────────────────────────


class TestListEvents:
    def test_list_events_basic(self, provider: GoogleCalendarProvider, mock_svc: MagicMock) -> None:
        events = provider.list_events(EventQuery(max_results=10), _service_fn=mock_svc)
        assert len(events) == 2

    def test_list_events_resource_type(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        events = provider.list_events(EventQuery(max_results=10), _service_fn=mock_svc)
        assert all(e["resource_type"] == "event" for e in events)

    def test_list_events_provider_id(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        events = provider.list_events(EventQuery(max_results=10), _service_fn=mock_svc)
        assert all(e["provider_id"] == "google_calendar" for e in events)

    def test_list_events_passes_text_to_q_param(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_events(EventQuery(text="standup", max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert call_kwargs["q"] == "standup"

    def test_list_events_no_text_omits_q(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_events(EventQuery(max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert "q" not in call_kwargs

    def test_list_events_passes_after_as_time_min(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_events(EventQuery(after="2026-03-01", max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert call_kwargs["timeMin"] == "2026-03-01T00:00:00Z"

    def test_list_events_passes_before_as_time_max(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_events(EventQuery(before="2026-03-31", max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert call_kwargs["timeMax"] == "2026-03-31T00:00:00Z"

    def test_list_events_respects_max_results(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        # Return more items than max_results
        svc.events().list().execute.return_value = {
            "items": [MOCK_EVENT_TIMED, MOCK_EVENT_ALL_DAY],
        }
        events = provider.list_events(EventQuery(max_results=1), _service_fn=svc)
        assert len(events) == 1

    def test_list_events_single_events_true(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_events(EventQuery(max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert call_kwargs["singleEvents"] is True

    def test_list_events_pagination(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        # First call returns page1, second returns page2
        svc.events().list().execute.side_effect = [
            MOCK_LIST_RESPONSE_PAGINATED_PAGE1,
            MOCK_LIST_RESPONSE_PAGINATED_PAGE2,
        ]
        events = provider.list_events(EventQuery(max_results=10), _service_fn=svc)
        assert len(events) == 2
        assert svc.events().list().execute.call_count == 2

    def test_list_events_calendar_id_from_query(
        self, provider: GoogleCalendarProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_events(EventQuery(calendar_id="primary", max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.events().list.call_args.kwargs
        assert call_kwargs["calendarId"] == "primary"


# ── TestGetEvent ──────────────────────────────────────────────────────────────


class TestGetEvent:
    def test_get_event_returns_event(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.events().get().execute.return_value = MOCK_EVENT_TIMED
        event = provider.get_event("evt001", _service_fn=svc)
        assert event["id"] == "evt001"
        assert event["title"] == "Team standup"

    def test_get_event_calls_correct_api(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        provider.get_event("evt001", _service_fn=svc)
        svc.events().get.assert_called_once_with(calendarId="primary", eventId="evt001")


# ── TestGetSyncState ──────────────────────────────────────────────────────────


class TestGetSyncState:
    def test_get_sync_state_returns_dict_with_token(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = {"nextSyncToken": "tok_abc"}
        result = provider.get_sync_state(_service_fn=svc)
        assert isinstance(result, dict)
        assert result["sync_token"] == "tok_abc"

    def test_get_sync_state_empty_token_fallback(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = {}
        result = provider.get_sync_state(_service_fn=svc)
        assert result["sync_token"] == ""


# ── TestGetNewEvents ──────────────────────────────────────────────────────────


class TestGetNewEvents:
    def test_get_new_events_returns_tuple(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = MOCK_SYNC_RESPONSE
        events, token = provider.get_new_events("old_token", _service_fn=svc)
        assert isinstance(events, list)
        assert isinstance(token, str)
        assert token == "sync_new_token"

    def test_get_new_events_maps_events(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = MOCK_SYNC_RESPONSE
        events, _ = provider.get_new_events("old_token", _service_fn=svc)
        assert len(events) == 1
        assert events[0]["id"] == "evt001"

    def test_get_new_events_fallback_token(self, provider: GoogleCalendarProvider) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = {"items": []}
        _, token = provider.get_new_events("my_token", _service_fn=svc)
        assert token == "my_token"


# ── TestEventNormalization ────────────────────────────────────────────────────


class TestEventNormalization:
    def _norm(self, raw: dict) -> dict:
        p = GoogleCalendarProvider(auth=MagicMock())
        return p._google_event_to_event(raw)

    def test_timed_event_not_all_day(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["all_day"] is False
        assert "2026-03-15T09:00:00" in event["start"]

    def test_all_day_event(self) -> None:
        event = self._norm(MOCK_EVENT_ALL_DAY)
        assert event["all_day"] is True
        assert event["start"] == "2026-03-17"
        assert event["end"] == "2026-03-18"

    def test_title_from_summary(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["title"] == "Team standup"

    def test_no_title_fallback(self) -> None:
        event = self._norm({})
        assert event["title"] == "(no title)"

    def test_meeting_url_from_hangout_link(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["meeting_url"] == "https://meet.google.com/abc-defg"

    def test_meeting_url_from_conference_data(self) -> None:
        event = self._norm(MOCK_EVENT_CONFERENCE_DATA)
        assert event["meeting_url"] == "https://zoom.us/j/12345"

    def test_meeting_url_none_when_absent(self) -> None:
        event = self._norm(MOCK_EVENT_ALL_DAY)
        assert event["meeting_url"] is None

    def test_hangout_link_takes_priority_over_conference_data(self) -> None:
        raw = {**MOCK_EVENT_TIMED, "conferenceData": MOCK_EVENT_CONFERENCE_DATA["conferenceData"]}
        event = self._norm(raw)
        assert event["meeting_url"] == "https://meet.google.com/abc-defg"

    def test_attendees_mapped_correctly(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert len(event["attendees"]) == 2
        tim = event["attendees"][0]
        assert tim["email"] == "tim@gmail.com"
        assert tim["response_status"] == "accepted"
        alice = event["attendees"][1]
        assert alice["email"] == "alice@gmail.com"
        assert alice["name"] == "Alice"
        assert alice["response_status"] == "tentative"

    def test_attendees_empty_when_absent(self) -> None:
        event = self._norm(MOCK_EVENT_ALL_DAY)
        assert event["attendees"] == []

    def test_organizer_email(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["organizer"] == "boss@example.com"

    def test_organizer_none_when_absent(self) -> None:
        event = self._norm(MOCK_EVENT_ALL_DAY)
        assert event["organizer"] is None

    def test_recurrence_rule_extracted(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["recurrence"] == "RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"

    def test_recurrence_none_when_absent(self) -> None:
        event = self._norm(MOCK_EVENT_ALL_DAY)
        assert event["recurrence"] is None

    def test_status_field(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["status"] == "confirmed"

    def test_url_from_html_link(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["url"] == "https://calendar.google.com/event?eid=evt001"

    def test_resource_type_is_event(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["resource_type"] == "event"

    def test_provider_id(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["provider_id"] == "google_calendar"

    def test_created_at_and_modified_at(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["created_at"] == "2026-01-01T10:00:00.000Z"
        assert event["modified_at"] == "2026-03-01T09:00:00.000Z"

    def test_location(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["location"] == "Zoom"

    def test_description(self) -> None:
        event = self._norm(MOCK_EVENT_TIMED)
        assert event["description"] == "Daily standup meeting"
