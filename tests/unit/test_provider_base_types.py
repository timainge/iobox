"""Tests for the workspace resource type hierarchy added to providers/base.py.

Verifies structure of Resource, Email, Event, File TypedDicts, the new
query dataclasses, and that CalendarProvider/FileProvider ABCs cannot
be instantiated directly.
"""

from __future__ import annotations

from typing import get_type_hints

import pytest

from iobox.providers import (
    AttachmentInfo,
    EmailData,
    EmailProvider,
    EmailQuery,
)
from iobox.providers.base import (
    AttendeeInfo,
    CalendarProvider,
    Email,
    Event,
    EventQuery,
    File,
    FileProvider,
    FileQuery,
    Resource,
    ResourceQuery,
)

# ── Existing types unchanged ──────────────────────────────────────────────────


class TestExistingTypesUnchanged:
    """Regression: EmailProvider, EmailData, EmailQuery must be completely untouched."""

    def test_emaildata_has_message_id(self) -> None:
        hints = get_type_hints(EmailData)
        assert "message_id" in hints

    def test_emaildata_has_from_underscore(self) -> None:
        hints = get_type_hints(EmailData)
        assert "from_" in hints

    def test_emailquery_has_text_field(self) -> None:
        q = EmailQuery()
        assert hasattr(q, "text")

    def test_emailquery_has_max_results(self) -> None:
        q = EmailQuery()
        assert q.max_results == 100

    def test_attachmentinfo_fields(self) -> None:
        hints = get_type_hints(AttachmentInfo)
        assert {"id", "filename", "mime_type", "size"} <= hints.keys()

    def test_emailprovider_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            EmailProvider()  # type: ignore[abstract]


# ── Resource TypedDict ────────────────────────────────────────────────────────


class TestResourceTypeDict:
    def test_has_required_fields(self) -> None:
        hints = get_type_hints(Resource)
        expected = {
            "id",
            "provider_id",
            "resource_type",
            "title",
            "created_at",
            "modified_at",
            "url",
        }
        assert expected <= hints.keys()

    def test_construct_minimal(self) -> None:
        r: Resource = {
            "id": "r1",
            "provider_id": "gmail",
            "resource_type": "email",
            "title": "Hello",
            "created_at": "2026-03-01T10:00:00Z",
            "modified_at": "2026-03-01T10:00:00Z",
            "url": None,
        }
        assert r["resource_type"] == "email"


# ── AttendeeInfo TypedDict ────────────────────────────────────────────────────


class TestAttendeeInfo:
    def test_has_required_fields(self) -> None:
        hints = get_type_hints(AttendeeInfo)
        assert {"email", "name", "response_status"} <= hints.keys()

    def test_construct(self) -> None:
        att: AttendeeInfo = {
            "email": "alice@example.com",
            "name": "Alice",
            "response_status": "accepted",
        }
        assert att["email"] == "alice@example.com"


# ── Email TypedDict ───────────────────────────────────────────────────────────


class TestEmailTypeDict:
    def test_inherits_resource_fields(self) -> None:
        hints = get_type_hints(Email)
        assert "id" in hints
        assert "resource_type" in hints

    def test_has_email_specific_fields(self) -> None:
        hints = get_type_hints(Email)
        assert {
            "from_",
            "to",
            "cc",
            "labels",
            "body",
            "content_type",
            "attachments",
        } <= hints.keys()

    def test_construct(self) -> None:
        e: Email = {
            "id": "msg1",
            "provider_id": "gmail",
            "resource_type": "email",
            "title": "Hello",
            "created_at": "2026-03-01T10:00:00Z",
            "modified_at": "2026-03-01T10:00:00Z",
            "url": None,
            "from_": "bob@example.com",
            "to": ["alice@example.com"],
            "cc": [],
            "thread_id": "thread1",
            "snippet": "Hello there",
            "labels": ["INBOX"],
            "body": "Hello there",
            "content_type": "text/plain",
            "attachments": [],
        }
        assert e["resource_type"] == "email"
        assert e["from_"] == "bob@example.com"


# ── Event TypedDict ───────────────────────────────────────────────────────────


class TestEventTypeDict:
    def test_inherits_resource_fields(self) -> None:
        hints = get_type_hints(Event)
        assert "id" in hints
        assert "title" in hints

    def test_has_event_specific_fields(self) -> None:
        hints = get_type_hints(Event)
        assert {
            "start",
            "end",
            "all_day",
            "organizer",
            "attendees",
            "location",
            "description",
            "meeting_url",
            "status",
            "recurrence",
        } <= hints.keys()

    def test_construct(self) -> None:
        e: Event = {
            "id": "evt1",
            "provider_id": "google_calendar",
            "resource_type": "event",
            "title": "Team standup",
            "created_at": "2026-03-01T00:00:00Z",
            "modified_at": "2026-03-01T00:00:00Z",
            "url": "https://calendar.google.com/...",
            "start": "2026-03-15T09:00:00-07:00",
            "end": "2026-03-15T09:30:00-07:00",
            "all_day": False,
            "organizer": "boss@example.com",
            "attendees": [],
            "location": None,
            "description": "Daily standup",
            "meeting_url": "https://meet.google.com/abc",
            "status": "confirmed",
            "recurrence": None,
        }
        assert e["resource_type"] == "event"
        assert e["all_day"] is False


# ── File TypedDict ────────────────────────────────────────────────────────────


class TestFileTypeDict:
    def test_inherits_resource_fields(self) -> None:
        hints = get_type_hints(File)
        assert "id" in hints
        assert "url" in hints

    def test_has_file_specific_fields(self) -> None:
        hints = get_type_hints(File)
        assert {
            "name",
            "mime_type",
            "size",
            "path",
            "parent_id",
            "is_folder",
            "download_url",
            "content",
        } <= hints.keys()

    def test_construct(self) -> None:
        f: File = {
            "id": "file1",
            "provider_id": "google_drive",
            "resource_type": "file",
            "title": "Q4 Report",
            "created_at": "2026-01-10T10:00:00Z",
            "modified_at": "2026-03-10T15:00:00Z",
            "url": "https://docs.google.com/...",
            "name": "Q4 Report.gdoc",
            "mime_type": "application/vnd.google-apps.document",
            "size": 0,
            "path": None,
            "parent_id": "folder_abc",
            "is_folder": False,
            "download_url": None,
            "content": None,
        }
        assert f["resource_type"] == "file"
        assert f["is_folder"] is False


# ── ResourceQuery dataclass ───────────────────────────────────────────────────


class TestResourceQuery:
    def test_defaults(self) -> None:
        q = ResourceQuery()
        assert q.text is None
        assert q.after is None
        assert q.before is None
        assert q.max_results == 25

    def test_custom_values(self) -> None:
        q = ResourceQuery(text="Q4", max_results=50)
        assert q.text == "Q4"
        assert q.max_results == 50


# ── EventQuery dataclass ──────────────────────────────────────────────────────


class TestEventQuery:
    def test_inherits_resource_query_defaults(self) -> None:
        q = EventQuery()
        assert q.text is None
        assert q.max_results == 25

    def test_calendar_id_default(self) -> None:
        q = EventQuery()
        assert q.calendar_id == "primary"

    def test_custom_calendar_id(self) -> None:
        q = EventQuery(calendar_id="work@group.calendar.google.com")
        assert q.calendar_id == "work@group.calendar.google.com"

    def test_inherits_text_field(self) -> None:
        q = EventQuery(text="standup")
        assert q.text == "standup"


# ── FileQuery dataclass ───────────────────────────────────────────────────────


class TestFileQuery:
    def test_defaults(self) -> None:
        q = FileQuery()
        assert q.mime_type is None
        assert q.folder_id is None
        assert q.shared_with_me is False
        assert q.max_results == 25

    def test_custom_values(self) -> None:
        q = FileQuery(text="report", mime_type="application/pdf", shared_with_me=True)
        assert q.text == "report"
        assert q.mime_type == "application/pdf"
        assert q.shared_with_me is True


# ── CalendarProvider ABC ──────────────────────────────────────────────────────


class TestCalendarProviderABC:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            CalendarProvider()  # type: ignore[abstract]

    def test_has_required_abstract_methods(self) -> None:
        abstract_methods = {
            name
            for name, val in vars(CalendarProvider).items()
            if getattr(val, "__isabstractmethod__", False)
        }
        expected = {
            "authenticate",
            "get_profile",
            "list_events",
            "get_event",
            "get_sync_state",
            "get_new_events",
            "create_event",
            "update_event",
            "delete_event",
            "rsvp",
        }
        assert expected == abstract_methods

    def test_concrete_subclass_must_implement_all(self) -> None:
        from typing import Any as _Any

        class PartialCalendar(CalendarProvider):
            def authenticate(self) -> None: ...
            def get_profile(self) -> dict[str, _Any]:
                return {}  # type: ignore[override]

            # Missing: list_events, get_event, get_sync_state, get_new_events

        with pytest.raises(TypeError):
            PartialCalendar()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self) -> None:
        from typing import Any

        class ConcreteCalendar(CalendarProvider):
            def authenticate(self) -> None: ...
            def get_profile(self) -> dict[str, Any]:
                return {}

            def list_events(self, query: EventQuery) -> list[Event]:
                return []

            def get_event(self, event_id: str) -> Event:
                raise KeyError(event_id)

            def get_sync_state(self) -> dict[str, Any]:
                return {}

            def get_new_events(self, sync_token: str) -> tuple[list[Event], str]:
                return [], sync_token

            def create_event(self, title: str, start: str, end: str, **kwargs: Any) -> Event:
                raise NotImplementedError

            def update_event(self, event_id: str, updates: dict[str, Any]) -> Event:
                raise NotImplementedError

            def delete_event(self, event_id: str) -> None: ...

            def rsvp(self, event_id: str, response: str) -> Event:
                raise NotImplementedError

        # Should not raise
        provider = ConcreteCalendar()
        assert provider.list_events(EventQuery()) == []


# ── FileProvider ABC ──────────────────────────────────────────────────────────


class TestFileProviderABC:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            FileProvider()  # type: ignore[abstract]

    def test_has_required_abstract_methods(self) -> None:
        abstract_methods = {
            name
            for name, val in vars(FileProvider).items()
            if getattr(val, "__isabstractmethod__", False)
        }
        expected = {
            "authenticate",
            "get_profile",
            "list_files",
            "get_file",
            "get_file_content",
            "download_file",
            "upload_file",
            "update_file",
            "delete_file",
            "create_folder",
        }
        assert expected == abstract_methods

    def test_complete_subclass_instantiates(self) -> None:
        from typing import Any

        class ConcreteFiles(FileProvider):
            def authenticate(self) -> None: ...
            def get_profile(self) -> dict[str, Any]:
                return {}

            def list_files(self, query: FileQuery) -> list[File]:
                return []

            def get_file(self, file_id: str) -> File:
                raise KeyError(file_id)

            def get_file_content(self, file_id: str) -> str:
                return ""

            def download_file(self, file_id: str) -> bytes:
                return b""

            def upload_file(self, local_path: str, **kwargs: Any) -> File:
                raise NotImplementedError

            def update_file(self, file_id: str, local_path: str) -> File:
                raise NotImplementedError

            def delete_file(self, file_id: str, *, permanent: bool = False) -> None: ...

            def create_folder(self, name: str, **kwargs: Any) -> File:
                raise NotImplementedError

        provider = ConcreteFiles()
        assert provider.list_files(FileQuery()) == []


# ── Import via providers package ──────────────────────────────────────────────


class TestPackageExports:
    def test_all_new_types_importable_from_package(self) -> None:
        from iobox.providers import (  # noqa: F401
            AttendeeInfo,
            CalendarProvider,
            Email,
            Event,
            EventQuery,
            File,
            FileProvider,
            FileQuery,
            Resource,
            ResourceQuery,
        )

    def test_existing_exports_still_present(self) -> None:
        from iobox.providers import (  # noqa: F401
            AttachmentInfo,
            EmailData,
            EmailMetadata,
            EmailProvider,
            EmailQuery,
            get_provider,
        )
