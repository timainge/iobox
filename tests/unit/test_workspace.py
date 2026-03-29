"""
Unit tests for the Workspace compositor.

Uses mock providers — no real API calls, no auth, no filesystem I/O.
Providers are injected directly into ProviderSlot objects, bypassing
from_config() for most tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from iobox.providers.base import (
    EmailData,
    EmailQuery,
    Event,
    EventQuery,
    File,
    FileQuery,
)
from iobox.workspace import (
    ProviderSession,
    ProviderSlot,
    Workspace,
    WorkspaceSession,
    _email_data_to_resource,
)

# ── Mock data helpers ─────────────────────────────────────────────────────────


def _email(message_id: str, date: str = "2026-03-10") -> EmailData:
    return EmailData(
        message_id=message_id,
        subject=f"Subject {message_id}",
        from_="sender@example.com",
        date=date,
        snippet="...",
        labels=[],
        thread_id="thread_1",
    )


def _event(event_id: str, start: str = "2026-03-10T10:00:00") -> Event:
    return Event(
        id=event_id,
        provider_id="google_calendar",
        resource_type="event",
        title=f"Event {event_id}",
        created_at="2026-01-01",
        modified_at="2026-01-01",
        url=None,
        start=start,
        end=start,
        all_day=False,
        organizer=None,
        attendees=[],
        location=None,
        description=None,
        meeting_url=None,
        status="confirmed",
        recurrence=None,
    )


def _file(file_id: str, modified_at: str = "2026-03-10") -> File:
    return File(
        id=file_id,
        provider_id="google_drive",
        resource_type="file",
        title=f"File {file_id}",
        created_at="2026-01-01",
        modified_at=modified_at,
        url=None,
        name=f"file_{file_id}.txt",
        mime_type="text/plain",
        size=100,
        path=None,
        parent_id=None,
        is_folder=False,
        download_url=None,
        content=None,
    )


def _mock_email_provider(results: list[EmailData]) -> MagicMock:
    p = MagicMock()
    p.search_emails.return_value = results
    return p


def _mock_calendar_provider(results: list[Event]) -> MagicMock:
    p = MagicMock()
    p.list_events.return_value = results
    return p


def _mock_file_provider(results: list[File]) -> MagicMock:
    p = MagicMock()
    p.list_files.return_value = results
    return p


def _ws_with_messages(*providers: Any, tags: list[str] | None = None) -> Workspace:
    slots = [
        ProviderSlot(name=f"slot_{i}", provider=p, tags=tags or []) for i, p in enumerate(providers)
    ]
    return Workspace(
        name="test",
        email_providers=slots,
        session=WorkspaceSession(workspace_name="test"),
    )


def _ws_with_calendar(*providers: Any) -> Workspace:
    slots = [ProviderSlot(name=f"cal_{i}", provider=p) for i, p in enumerate(providers)]
    return Workspace(
        name="test",
        calendar_providers=slots,
        session=WorkspaceSession(workspace_name="test"),
    )


def _ws_with_files(*providers: Any) -> Workspace:
    slots = [ProviderSlot(name=f"drv_{i}", provider=p) for i, p in enumerate(providers)]
    return Workspace(
        name="test",
        file_providers=slots,
        session=WorkspaceSession(workspace_name="test"),
    )


# ── TestFanOut ────────────────────────────────────────────────────────────────


class TestFanOut:
    def test_calls_all_slots(self) -> None:
        p1 = _mock_email_provider([_email("e1")])
        p2 = _mock_email_provider([_email("e2")])
        ws = _ws_with_messages(p1, p2)
        results = ws.search_emails(EmailQuery(text="x"))
        assert len(results) == 2
        p1.search_emails.assert_called_once()
        p2.search_emails.assert_called_once()

    def test_partial_failure_continues(self) -> None:
        good = _mock_email_provider([_email("ok")])
        bad = MagicMock()
        bad.search_emails.side_effect = RuntimeError("API error")
        ws = _ws_with_messages(good, bad)
        results = ws.search_emails(EmailQuery(text="x"))
        # One result from good provider, bad provider error is swallowed
        assert len(results) == 1
        assert results[0]["message_id"] == "ok"

    def test_partial_failure_records_error_in_session(self) -> None:
        good = _mock_email_provider([])
        bad = MagicMock()
        bad.search_emails.side_effect = RuntimeError("network timeout")
        ws = _ws_with_messages(good, bad)
        ws.search_emails(EmailQuery())
        # Find the slot that errored
        errored = [
            s
            for s in ws.email_providers
            if ws.session.providers.get(s.name, ProviderSession("x")).error
        ]
        assert len(errored) == 1

    def test_provider_filter(self) -> None:
        p1 = _mock_email_provider([_email("e1")])
        p2 = _mock_email_provider([_email("e2")])
        ws = Workspace(
            name="test",
            email_providers=[
                ProviderSlot(name="primary", provider=p1),
                ProviderSlot(name="secondary", provider=p2),
            ],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search_emails(EmailQuery(), providers=["primary"])
        assert len(results) == 1
        p2.search_emails.assert_not_called()

    def test_tag_filter(self) -> None:
        p1 = _mock_email_provider([_email("e1")])
        p2 = _mock_email_provider([_email("e2")])
        ws = Workspace(
            name="test",
            email_providers=[
                ProviderSlot(name="work", provider=p1, tags=["work"]),
                ProviderSlot(name="personal", provider=p2, tags=["personal"]),
            ],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search_emails(EmailQuery(), tags=["work"])
        assert len(results) == 1
        p2.search_emails.assert_not_called()

    def test_empty_slots_returns_empty(self) -> None:
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        results = ws.search_emails(EmailQuery())
        assert results == []

    def test_no_matching_provider_filter_returns_empty(self) -> None:
        p = _mock_email_provider([_email("e1")])
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="slot_0", provider=p)],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search_emails(EmailQuery(), providers=["nonexistent"])
        assert results == []
        p.search_emails.assert_not_called()

    def test_success_clears_previous_error(self) -> None:
        p = _mock_email_provider([_email("e1")])
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="slot_0", provider=p)],
            session=WorkspaceSession(workspace_name="test"),
        )
        ws.session.providers["slot_0"] = ProviderSession(
            provider_name="slot_0", error="previous error"
        )
        ws.search_emails(EmailQuery())
        assert ws.session.providers["slot_0"].error is None


# ── TestSearchMessages ────────────────────────────────────────────────────────


class TestSearchEmails:
    def test_sorted_by_date_descending(self) -> None:
        emails = [
            _email("e1", date="2026-01-01"),
            _email("e2", date="2026-03-15"),
            _email("e3", date="2026-02-10"),
        ]
        p = _mock_email_provider(emails)
        ws = _ws_with_messages(p)
        results = ws.search_emails(EmailQuery())
        dates = [r["date"] for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_merges_results_from_multiple_providers(self) -> None:
        p1 = _mock_email_provider([_email("e1"), _email("e2")])
        p2 = _mock_email_provider([_email("e3")])
        ws = _ws_with_messages(p1, p2)
        results = ws.search_emails(EmailQuery())
        assert len(results) == 3

    def test_returns_list(self) -> None:
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        assert isinstance(ws.search_emails(EmailQuery()), list)


# ── TestListEvents ────────────────────────────────────────────────────────────


class TestListEvents:
    def test_sorted_by_start_ascending(self) -> None:
        events = [
            _event("ev1", start="2026-03-15T10:00:00"),
            _event("ev2", start="2026-03-10T09:00:00"),
            _event("ev3", start="2026-03-20T14:00:00"),
        ]
        p = _mock_calendar_provider(events)
        ws = _ws_with_calendar(p)
        results = ws.list_events(EventQuery())
        starts = [r["start"] for r in results]
        assert starts == sorted(starts)

    def test_merges_results_from_multiple_providers(self) -> None:
        p1 = _mock_calendar_provider([_event("ev1")])
        p2 = _mock_calendar_provider([_event("ev2"), _event("ev3")])
        ws = _ws_with_calendar(p1, p2)
        results = ws.list_events(EventQuery())
        assert len(results) == 3


# ── TestListFiles ─────────────────────────────────────────────────────────────


class TestListFiles:
    def test_sorted_by_modified_at_descending(self) -> None:
        files = [
            _file("f1", modified_at="2026-01-01"),
            _file("f2", modified_at="2026-03-15"),
            _file("f3", modified_at="2026-02-10"),
        ]
        p = _mock_file_provider(files)
        ws = _ws_with_files(p)
        results = ws.list_files(FileQuery())
        mods = [r["modified_at"] for r in results]
        assert mods == sorted(mods, reverse=True)

    def test_merges_from_multiple_providers(self) -> None:
        p1 = _mock_file_provider([_file("f1")])
        p2 = _mock_file_provider([_file("f2")])
        ws = _ws_with_files(p1, p2)
        results = ws.list_files(FileQuery())
        assert len(results) == 2


# ── TestSearch ────────────────────────────────────────────────────────────────


class TestSearch:
    def test_cross_type_returns_all_resource_types(self) -> None:
        email_p = _mock_email_provider([_email("e1")])
        cal_p = _mock_calendar_provider([_event("ev1")])
        file_p = _mock_file_provider([_file("f1")])
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="msg", provider=email_p)],
            calendar_providers=[ProviderSlot(name="cal", provider=cal_p)],
            file_providers=[ProviderSlot(name="drv", provider=file_p)],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search("planning")
        resource_types = {r["resource_type"] for r in results}
        assert resource_types == {"email", "event", "file"}

    def test_type_filter_limits_queries(self) -> None:
        email_p = _mock_email_provider([_email("e1")])
        cal_p = _mock_calendar_provider([_event("ev1")])
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="msg", provider=email_p)],
            calendar_providers=[ProviderSlot(name="cal", provider=cal_p)],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search("planning", types=["email"])
        assert all(r["resource_type"] == "email" for r in results)
        cal_p.list_events.assert_not_called()

    def test_partial_failure_in_one_type_continues(self) -> None:
        email_p = _mock_email_provider([_email("e1")])
        cal_p = MagicMock()
        cal_p.list_events.side_effect = RuntimeError("calendar down")
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="msg", provider=email_p)],
            calendar_providers=[ProviderSlot(name="cal", provider=cal_p)],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search("test", types=["email", "event"])
        # Email results still returned despite calendar failure
        assert any(r["resource_type"] == "email" for r in results)

    def test_empty_workspace_returns_empty(self) -> None:
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        assert ws.search("anything") == []

    def test_results_sorted_by_created_at_descending(self) -> None:
        email_p = _mock_email_provider(
            [_email("e1", date="2026-01-01"), _email("e2", date="2026-03-15")]
        )
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="msg", provider=email_p)],
            session=WorkspaceSession(workspace_name="test"),
        )
        results = ws.search("x", types=["email"])
        dates = [r["created_at"] for r in results]
        assert dates == sorted(dates, reverse=True)


# ── TestAuthStatus ────────────────────────────────────────────────────────────


class TestAuthStatus:
    def test_returns_dict(self) -> None:
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        assert isinstance(ws.auth_status(), dict)

    def test_reflects_session_providers(self) -> None:
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        ws.session.providers["slot_0"] = ProviderSession(provider_name="slot_0", authenticated=True)
        status = ws.auth_status()
        assert "slot_0" in status
        assert status["slot_0"].authenticated is True


# ── TestEmailDataToResource ───────────────────────────────────────────────────


class TestEmailDataToResource:
    def test_basic_fields_mapped(self) -> None:
        email = _email("msg_001", date="2026-03-10")
        result = _email_data_to_resource(email)
        assert result["id"] == "msg_001"
        assert result["title"] == "Subject msg_001"
        assert result["resource_type"] == "email"
        assert result["created_at"] == "2026-03-10"

    def test_from_field_mapped(self) -> None:
        email = _email("e1")
        result = _email_data_to_resource(email)
        assert result["from_"] == "sender@example.com"

    def test_missing_optional_fields_default_to_empty(self) -> None:
        email = _email("e1")
        result = _email_data_to_resource(email)
        assert result["to"] == []
        assert result["cc"] == []
        assert result["body"] is None
        assert result["url"] is None


# ── TestFromConfig ────────────────────────────────────────────────────────────


class TestFromConfig:
    def test_creates_gmail_message_slot(self) -> None:
        from iobox.space_config import ServiceEntry, SpaceConfig

        config = SpaceConfig(
            name="test",
            services=[
                ServiceEntry(
                    number=1,
                    service="google",
                    account="tim@gmail.com",
                    scopes=["email"],
                    mode="readonly",
                )
            ],
        )
        with (
            patch("iobox.providers.google.email.GmailProvider.__init__", return_value=None),
            patch("iobox.providers.google.auth.GoogleAuth.__init__", return_value=None),
            patch(
                "iobox.providers.google.auth.GoogleAuth.get_service",
                return_value=MagicMock(),
            ),
        ):
            ws = Workspace.from_config(config)
        assert len(ws.email_providers) == 1
        assert ws.email_providers[0].name == "tim-gmail"

    def test_creates_calendar_slot_when_calendar_in_scopes(self) -> None:
        from iobox.space_config import ServiceEntry, SpaceConfig

        config = SpaceConfig(
            name="test",
            services=[
                ServiceEntry(
                    number=1,
                    service="google",
                    account="tim@gmail.com",
                    scopes=["calendar"],
                    mode="readonly",
                )
            ],
        )
        with (
            patch("iobox.providers.google.auth.GoogleAuth.__init__", return_value=None),
            patch(
                "iobox.providers.google.calendar.GoogleCalendarProvider.__init__",
                return_value=None,
            ),
        ):
            ws = Workspace.from_config(config)
        assert len(ws.calendar_providers) == 1

    def test_creates_drive_slot_when_drive_in_scopes(self) -> None:
        from iobox.space_config import ServiceEntry, SpaceConfig

        config = SpaceConfig(
            name="test",
            services=[
                ServiceEntry(
                    number=1,
                    service="google",
                    account="tim@gmail.com",
                    scopes=["drive"],
                    mode="readonly",
                )
            ],
        )
        with (
            patch("iobox.providers.google.auth.GoogleAuth.__init__", return_value=None),
            patch(
                "iobox.providers.google.files.GoogleDriveProvider.__init__",
                return_value=None,
            ),
        ):
            ws = Workspace.from_config(config)
        assert len(ws.file_providers) == 1

    def test_workspace_name_from_config(self) -> None:
        from iobox.space_config import SpaceConfig

        config = SpaceConfig(name="personal", services=[])
        ws = Workspace.from_config(config)
        assert ws.name == "personal"

    def test_empty_services_creates_empty_workspace(self) -> None:
        from iobox.space_config import SpaceConfig

        config = SpaceConfig(name="empty", services=[])
        ws = Workspace.from_config(config)
        assert ws.email_providers == []
        assert ws.calendar_providers == []
        assert ws.file_providers == []
