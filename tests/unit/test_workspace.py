"""
Unit tests for the Workspace compositor.

Uses mock providers — no real API calls, no auth, no filesystem I/O.
Providers are injected directly into ProviderSlot objects, bypassing
from_config() for most tests.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.base import (
    EmailData,
    EmailQuery,
    Event,
    EventQuery,
    File,
    FileQuery,
)
from iobox.workspace import (
    ProviderSlot,
    Workspace,
    _email_data_to_resource,
    to_utc_datetime,
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
    )


def _ws_with_calendar(*providers: Any) -> Workspace:
    slots = [ProviderSlot(name=f"cal_{i}", provider=p) for i, p in enumerate(providers)]
    return Workspace(
        name="test",
        calendar_providers=slots,
    )


def _ws_with_files(*providers: Any) -> Workspace:
    slots = [ProviderSlot(name=f"drv_{i}", provider=p) for i, p in enumerate(providers)]
    return Workspace(
        name="test",
        file_providers=slots,
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

    def test_partial_failure_reported_in_last_errors(self) -> None:
        good = _mock_email_provider([])
        bad = MagicMock()
        bad.search_emails.side_effect = RuntimeError("network timeout")
        ws = _ws_with_messages(good, bad)
        ws.search_emails(EmailQuery())
        assert ws.last_errors == {"slot_1": "network timeout"}

    def test_error_without_message_uses_exception_type(self) -> None:
        bad = MagicMock()
        bad.search_emails.side_effect = TimeoutError()
        ws = _ws_with_messages(bad)
        assert ws.search_emails(EmailQuery()) == []
        assert ws.last_errors == {"slot_0": "TimeoutError"}

    def test_provider_filter(self) -> None:
        p1 = _mock_email_provider([_email("e1")])
        p2 = _mock_email_provider([_email("e2")])
        ws = Workspace(
            name="test",
            email_providers=[
                ProviderSlot(name="primary", provider=p1),
                ProviderSlot(name="secondary", provider=p2),
            ],
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
        )
        results = ws.search_emails(EmailQuery(), tags=["work"])
        assert len(results) == 1
        p2.search_emails.assert_not_called()

    def test_empty_slots_returns_empty(self) -> None:
        ws = Workspace(name="test")
        results = ws.search_emails(EmailQuery())
        assert results == []

    def test_no_matching_provider_filter_returns_empty(self) -> None:
        p = _mock_email_provider([_email("e1")])
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="slot_0", provider=p)],
        )
        results = ws.search_emails(EmailQuery(), providers=["nonexistent"])
        assert results == []
        p.search_emails.assert_not_called()

    def test_last_errors_reset_on_next_call(self) -> None:
        p = MagicMock()
        p.search_emails.side_effect = [RuntimeError("boom"), [_email("e1")]]
        ws = _ws_with_messages(p)
        ws.search_emails(EmailQuery())
        assert ws.last_errors == {"slot_0": "boom"}
        ws.search_emails(EmailQuery())
        assert ws.last_errors == {}

    def test_last_errors_reset_across_methods(self) -> None:
        bad = MagicMock()
        bad.search_emails.side_effect = RuntimeError("boom")
        ws = _ws_with_messages(bad)
        ws.search_emails(EmailQuery())
        assert ws.last_errors
        ws.list_files(FileQuery())
        assert ws.last_errors == {}


# ── Slot tagging (WS-02 / WS-07) ──────────────────────────────────────────────


class _FakeGmail:
    """Stand-in whose class name maps to provider_id 'gmail'."""

    def __init__(self, results: list[EmailData]) -> None:
        self._results = results

    def search_emails(self, query: EmailQuery) -> list[EmailData]:
        return self._results


_FakeGmail.__name__ = "GmailProvider"


class TestSlotTagging:
    def test_email_results_tagged_with_slot(self) -> None:
        ws = Workspace(
            name="test",
            email_providers=[
                ProviderSlot(name="personal", provider=_mock_email_provider([_email("p1")])),
                ProviderSlot(name="work", provider=_mock_email_provider([_email("w1")])),
            ],
        )
        by_id = {r["message_id"]: r["slot"] for r in ws.search_emails(EmailQuery())}
        assert by_id == {"p1": "personal", "w1": "work"}

    def test_provider_dicts_not_mutated(self) -> None:
        original = _email("p1")
        ws = _ws_with_messages(_mock_email_provider([original]))
        ws.search_emails(EmailQuery())
        assert "slot" not in original

    def test_events_and_files_tagged(self) -> None:
        ws = Workspace(
            name="test",
            calendar_providers=[
                ProviderSlot(name="me-cal", provider=_mock_calendar_provider([_event("ev")]))
            ],
            file_providers=[
                ProviderSlot(name="me-drive", provider=_mock_file_provider([_file("f")]))
            ],
        )
        assert ws.list_events(EventQuery())[0]["slot"] == "me-cal"
        assert ws.list_files(FileQuery())[0]["slot"] == "me-drive"
        # Provider-supplied provider_id is preserved.
        assert ws.list_files(FileQuery())[0]["provider_id"] == "google_drive"

    def test_email_provider_id_from_provider_class(self) -> None:
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="me", provider=_FakeGmail([_email("e1")]))],
        )
        result = ws.search_emails(EmailQuery())[0]
        assert result["provider_id"] == "gmail"
        resource = ws.search("x", types=["email"])[0]
        assert resource["provider_id"] == "gmail"
        assert resource["slot"] == "me"

    def test_search_results_carry_slot_for_every_type(self) -> None:
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="m", provider=_mock_email_provider([_email("e")]))],
            calendar_providers=[
                ProviderSlot(name="c", provider=_mock_calendar_provider([_event("ev")]))
            ],
            file_providers=[ProviderSlot(name="d", provider=_mock_file_provider([_file("f")]))],
        )
        assert {r["resource_type"]: r["slot"] for r in ws.search("x")} == {
            "email": "m",
            "event": "c",
            "file": "d",
        }


# ── Result caps (WS-03) ───────────────────────────────────────────────────────


class TestResultCaps:
    def test_search_emails_capped_to_max_results_after_merge(self) -> None:
        p1 = _mock_email_provider([_email(f"a{i}", date=f"2026-03-{i + 1:02d}") for i in range(3)])
        p2 = _mock_email_provider([_email(f"b{i}", date=f"2026-04-{i + 1:02d}") for i in range(3)])
        ws = _ws_with_messages(p1, p2)
        results = ws.search_emails(EmailQuery(max_results=3))
        # The three newest overall — all from p2.
        assert [r["message_id"] for r in results] == ["b2", "b1", "b0"]

    def test_list_events_capped_keeps_earliest(self) -> None:
        p1 = _mock_calendar_provider([_event("late", start="2026-05-01T00:00:00Z")])
        p2 = _mock_calendar_provider([_event("early", start="2026-04-01T00:00:00Z")])
        ws = _ws_with_calendar(p1, p2)
        assert [r["id"] for r in ws.list_events(EventQuery(max_results=1))] == ["early"]

    def test_list_files_capped(self) -> None:
        p1 = _mock_file_provider([_file("f1"), _file("f2")])
        p2 = _mock_file_provider([_file("f3"), _file("f4")])
        ws = _ws_with_files(p1, p2)
        assert len(ws.list_files(FileQuery(max_results=3))) == 3

    def test_zero_max_results_means_uncapped(self) -> None:
        ws = _ws_with_messages(_mock_email_provider([_email("a"), _email("b")]))
        assert len(ws.search_emails(EmailQuery(max_results=0))) == 2

    def test_search_caps_each_type(self) -> None:
        ws = Workspace(
            name="test",
            email_providers=[
                ProviderSlot(name="m1", provider=_mock_email_provider([_email("a"), _email("b")])),
                ProviderSlot(name="m2", provider=_mock_email_provider([_email("c"), _email("d")])),
            ],
            file_providers=[
                ProviderSlot(name="d1", provider=_mock_file_provider([_file("x"), _file("y")])),
                ProviderSlot(name="d2", provider=_mock_file_provider([_file("z")])),
            ],
        )
        results = ws.search("q", types=["email", "file"], max_results_per_type=2)
        counts = {t: sum(r["resource_type"] == t for r in results) for t in ("email", "file")}
        assert counts == {"email": 2, "file": 2}


# ── Date parsing / sorting (DATA-02) ─────────────────────────────────────────


class TestToUtcDatetime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Tue, 10 Mar 2026 10:00:00 +0000", datetime(2026, 3, 10, 10, tzinfo=timezone.utc)),
            (
                "Tue, 10 Mar 2026 10:00:00 +0000 (UTC)",
                datetime(2026, 3, 10, 10, tzinfo=timezone.utc),
            ),
            ("10 Mar 2026 21:00:00 +1100", datetime(2026, 3, 10, 10, tzinfo=timezone.utc)),
            ("2026-03-10T10:00:00Z", datetime(2026, 3, 10, 10, tzinfo=timezone.utc)),
            ("2026-03-10T21:00:00+11:00", datetime(2026, 3, 10, 10, tzinfo=timezone.utc)),
            ("2026-03-10T05:00:00-0500", datetime(2026, 3, 10, 10, tzinfo=timezone.utc)),
            (
                "2026-03-10T10:00:00.1234567Z",
                datetime(2026, 3, 10, 10, 0, 0, 123456, tzinfo=timezone.utc),
            ),
            (
                datetime(2026, 3, 10, 10, tzinfo=timezone.utc),
                datetime(2026, 3, 10, 10, tzinfo=timezone.utc),
            ),
        ],
    )
    def test_aware_values(self, value: object, expected: datetime) -> None:
        assert to_utc_datetime(value) == expected

    def test_naive_and_date_only_are_local(self) -> None:
        local_midnight = datetime(2026, 3, 10).astimezone()
        assert to_utc_datetime("2026-03-10") == local_midnight
        assert to_utc_datetime(date(2026, 3, 10)) == local_midnight
        assert to_utc_datetime("2026-03-10T09:30:00") == datetime(2026, 3, 10, 9, 30).astimezone()

    @pytest.mark.parametrize("value", [None, "", "  ", "Unknown Date", "garbage", 42])
    def test_unparsable_returns_none(self, value: object) -> None:
        assert to_utc_datetime(value) is None

    def test_result_is_utc(self) -> None:
        dt = to_utc_datetime("Tue, 10 Mar 2026 10:00:00 -0800")
        assert dt is not None and dt.utcoffset() == timedelta(0)


class TestDateSorting:
    def test_emails_mixed_formats_sorted_chronologically(self) -> None:
        # Raw string sort would put "Wed..." first and the ISO date last.
        emails = [
            _email("mid", date="Wed, 11 Mar 2026 09:00:00 +0000"),
            _email("newest", date="2026-03-12T08:00:00Z"),
            _email("oldest", date="Thu, 01 Jan 2026 09:00:00 +0000"),
            # Later wall-clock but earlier instant because of the offset:
            _email("mid_minus", date="Wed, 11 Mar 2026 18:00:00 +1100"),
        ]
        ws = _ws_with_messages(_mock_email_provider(emails))
        ids = [r["message_id"] for r in ws.search_emails(EmailQuery())]
        assert ids == ["newest", "mid", "mid_minus", "oldest"]

    def test_unparsable_dates_sort_last(self) -> None:
        emails = [
            _email("bad", date="Unknown Date"),
            _email("old", date="2026-01-01T00:00:00Z"),
            _email("missing", date=""),
            _email("new", date="2026-02-01T00:00:00Z"),
        ]
        ws = _ws_with_messages(_mock_email_provider(emails))
        ids = [r["message_id"] for r in ws.search_emails(EmailQuery())]
        assert ids == ["new", "old", "bad", "missing"]

    def test_events_with_offsets_sorted_chronologically(self) -> None:
        events = [
            _event("utc_9am", start="2026-03-10T09:00:00Z"),
            _event("sydney_7pm_prev", start="2026-03-10T07:00:00+11:00"),  # 20:00Z on the 9th
            _event("no_start", start=""),
        ]
        ws = _ws_with_calendar(_mock_calendar_provider(events))
        ids = [r["id"] for r in ws.list_events(EventQuery())]
        assert ids == ["sydney_7pm_prev", "utc_9am", "no_start"]

    def test_files_sorted_by_parsed_modified_at(self) -> None:
        files = [
            _file("a", modified_at="2026-03-10T10:00:00+05:00"),  # 05:00Z
            _file("b", modified_at="2026-03-10T06:00:00Z"),
        ]
        ws = _ws_with_files(_mock_file_provider(files))
        assert [r["id"] for r in ws.list_files(FileQuery())] == ["b", "a"]

    def test_search_merges_rfc2822_and_iso(self) -> None:
        email_p = _mock_email_provider([_email("e1", date="Tue, 10 Mar 2026 10:00:00 +0000")])
        file_p = _mock_file_provider([])
        f = _file("f1")
        f["created_at"] = "2026-03-11T00:00:00Z"
        file_p.list_files.return_value = [f]
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="msg", provider=email_p)],
            file_providers=[ProviderSlot(name="drv", provider=file_p)],
        )
        assert [r["id"] for r in ws.search("x", types=["email", "file"])] == ["f1", "e1"]


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
        ws = Workspace(name="test")
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
        )
        results = ws.search("test", types=["email", "event"])
        # Email results still returned despite calendar failure
        assert any(r["resource_type"] == "email" for r in results)
        assert ws.last_errors == {"cal": "calendar down"}

    def test_event_search_defaults_after_to_90_days_ago(self) -> None:
        cal_p = _mock_calendar_provider([])
        ws = Workspace(name="test", calendar_providers=[ProviderSlot(name="c", provider=cal_p)])
        ws.search("standup", types=["event"])
        query = cal_p.list_events.call_args.args[0]
        assert query.text == "standup"
        assert query.after == (date.today() - timedelta(days=90)).isoformat()
        assert query.before is None

    def test_empty_workspace_returns_empty(self) -> None:
        ws = Workspace(name="test")
        assert ws.search("anything") == []

    def test_results_sorted_by_created_at_descending(self) -> None:
        email_p = _mock_email_provider(
            [_email("e1", date="2026-01-01"), _email("e2", date="2026-03-15")]
        )
        ws = Workspace(
            name="test",
            email_providers=[ProviderSlot(name="msg", provider=email_p)],
        )
        results = ws.search("x", types=["email"])
        dates = [r["created_at"] for r in results]
        assert dates == sorted(dates, reverse=True)


# ── Dead session plumbing removed (WS-08) ───────────────────────────────────


class TestDeadSessionCodeRemoved:
    def test_no_auth_status(self) -> None:
        assert not hasattr(Workspace, "auth_status")

    def test_workspace_session_removed(self) -> None:
        import iobox.workspace as workspace_module

        assert not hasattr(workspace_module, "WorkspaceSession")
        assert Workspace(name="t").last_errors == {}


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

    def test_to_and_cc_header_strings_split_into_lists(self) -> None:
        email: Any = _email("e1")
        email["to"] = 'Alice <alice@example.com>, "Smith, Bob" <bob@example.com>'
        email["cc"] = "carol@example.com"
        result = _email_data_to_resource(email)
        assert result["to"] == ["Alice <alice@example.com>", '"Smith, Bob" <bob@example.com>']
        assert result["cc"] == ["carol@example.com"]

    def test_to_already_a_list_is_kept(self) -> None:
        email: Any = _email("e1")
        email["to"] = ["a@x.com", "b@x.com"]
        assert _email_data_to_resource(email)["to"] == ["a@x.com", "b@x.com"]

    def test_slot_and_provider_id_carried(self) -> None:
        email: Any = _email("e1")
        email["slot"] = "work"
        email["provider_id"] = "outlook"
        result = _email_data_to_resource(email)
        assert result["slot"] == "work"
        assert result["provider_id"] == "outlook"

    def test_no_slot_key_when_absent(self) -> None:
        assert "slot" not in _email_data_to_resource(_email("e1"))


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

    def test_google_calendar_and_drive_inherit_entry_mode(self) -> None:
        from iobox.space_config import ServiceEntry, SpaceConfig

        config = SpaceConfig(
            name="test",
            services=[
                ServiceEntry(
                    number=1,
                    service="google",
                    account="tim@gmail.com",
                    scopes=["calendar", "drive"],
                    mode="standard",
                )
            ],
        )
        with patch("iobox.providers.google.auth.GoogleAuth.__init__", return_value=None):
            ws = Workspace.from_config(config)
        assert ws.calendar_providers[0].provider.mode == "standard"
        assert ws.file_providers[0].provider.mode == "standard"

    def test_duplicate_slugs_in_legacy_config_get_unique_slot_names(self) -> None:
        from iobox.space_config import ServiceEntry, SpaceConfig

        config = SpaceConfig(
            name="test",
            services=[
                ServiceEntry(number=1, service="google", account="tim@gmail.com", scopes=["email"]),
                ServiceEntry(
                    number=2,
                    service="google",
                    account="tim@gmail.co.uk",
                    scopes=["email"],
                    slug="tim-gmail",
                ),
            ],
        )
        with (
            patch("iobox.providers.google.email.GmailProvider.__init__", return_value=None),
            patch("iobox.providers.google.auth.GoogleAuth.__init__", return_value=None),
        ):
            ws = Workspace.from_config(config)
        assert [s.name for s in ws.email_providers] == ["tim-gmail", "tim-gmail-2"]

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
