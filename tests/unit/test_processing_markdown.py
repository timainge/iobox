"""
Unit tests for src/iobox/processing/markdown.py

Tests cover:
- convert_event_to_markdown: frontmatter, body, None-omission, all_day
- convert_file_to_markdown: frontmatter, body, content truncation
- convert_resource_to_markdown: dispatch by resource_type
- convert_message_to_markdown: delegates to existing converter
"""

from __future__ import annotations

import pytest
import yaml

from iobox.processing.markdown import (
    MAX_FILE_CONTENT_CHARS,
    convert_event_to_markdown,
    convert_file_to_markdown,
    convert_message_to_markdown,
    convert_resource_to_markdown,
)
from iobox.providers.base import AttendeeInfo, Event, File

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_event() -> Event:
    return Event(
        id="evt001",
        provider_id="google_calendar",
        resource_type="event",
        title="Team standup",
        created_at="2026-01-01T10:00:00Z",
        modified_at="2026-03-01T09:00:00Z",
        url="https://calendar.google.com/event?eid=evt001",
        start="2026-03-15T09:00:00-07:00",
        end="2026-03-15T09:30:00-07:00",
        all_day=False,
        organizer="boss@example.com",
        attendees=[
            AttendeeInfo(email="tim@gmail.com", name=None, response_status="accepted"),
            AttendeeInfo(email="alice@gmail.com", name="Alice Smith", response_status="tentative"),
        ],
        location="Zoom",
        description="Daily standup meeting",
        meeting_url="https://meet.google.com/abc-defg",
        status="confirmed",
        recurrence="RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR",
    )


@pytest.fixture
def minimal_event() -> Event:
    """Event with only required fields — most optional fields are None."""
    return Event(
        id="evt002",
        provider_id="google_calendar",
        resource_type="event",
        title="All-day holiday",
        created_at="2026-01-01T00:00:00Z",
        modified_at="2026-01-01T00:00:00Z",
        url=None,
        start="2026-03-17",
        end="2026-03-18",
        all_day=True,
        organizer=None,
        attendees=[],
        location=None,
        description=None,
        meeting_url=None,
        status="confirmed",
        recurrence=None,
    )


@pytest.fixture
def sample_file() -> File:
    return File(
        id="doc_001",
        provider_id="google_drive",
        resource_type="file",
        title="Q4 Planning Notes",
        created_at="2026-01-10T10:00:00Z",
        modified_at="2026-03-10T15:00:00Z",
        url="https://docs.google.com/document/d/doc_001",
        name="Q4 Planning Notes",
        mime_type="application/vnd.google-apps.document",
        size=0,
        path=None,
        parent_id="folder_abc",
        is_folder=False,
        download_url=None,
        content="This is the document content.",
    )


@pytest.fixture
def file_no_content() -> File:
    return File(
        id="pdf_002",
        provider_id="google_drive",
        resource_type="file",
        title="budget.pdf",
        created_at="2026-02-01T09:00:00Z",
        modified_at="2026-02-15T11:00:00Z",
        url="https://drive.google.com/file/d/pdf_002/view",
        name="budget.pdf",
        mime_type="application/pdf",
        size=204800,
        path=None,
        parent_id="folder_abc",
        is_folder=False,
        download_url=None,
        content=None,
    )


def _parse_frontmatter(md: str) -> dict:
    """Extract and parse the YAML frontmatter from a markdown string."""
    assert md.startswith("---\n"), "Expected frontmatter to start with ---"
    end = md.index("\n---\n", 4)
    return yaml.safe_load(md[4:end])


# ── TestConvertEventToMarkdown ────────────────────────────────────────────────


class TestConvertEventToMarkdown:
    def test_returns_string(self, sample_event: Event) -> None:
        result = convert_event_to_markdown(sample_event)
        assert isinstance(result, str)

    def test_starts_with_frontmatter_delimiter(self, sample_event: Event) -> None:
        result = convert_event_to_markdown(sample_event)
        assert result.startswith("---\n")

    def test_contains_yaml_frontmatter(self, sample_event: Event) -> None:
        result = convert_event_to_markdown(sample_event)
        fm = _parse_frontmatter(result)
        assert fm["id"] == "evt001"
        assert fm["title"] == "Team standup"
        assert fm["start"] == "2026-03-15T09:00:00-07:00"
        assert fm["end"] == "2026-03-15T09:30:00-07:00"

    def test_title_as_h1(self, sample_event: Event) -> None:
        result = convert_event_to_markdown(sample_event)
        assert "# Team standup" in result

    def test_description_in_body(self, sample_event: Event) -> None:
        result = convert_event_to_markdown(sample_event)
        assert "Daily standup meeting" in result

    def test_no_description_when_none(self, minimal_event: Event) -> None:
        result = convert_event_to_markdown(minimal_event)
        # Body should just be the h1, no extra content
        after_fm = result.split("---\n", 2)[-1]
        assert "None" not in after_fm

    def test_attendees_in_frontmatter(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert len(fm["attendees"]) == 2
        assert fm["attendees"][0]["email"] == "tim@gmail.com"
        assert fm["attendees"][0]["response_status"] == "accepted"
        assert fm["attendees"][1]["name"] == "Alice Smith"

    def test_attendees_empty_list_when_none(self, minimal_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(minimal_event))
        assert fm["attendees"] == []

    def test_meeting_url_in_frontmatter(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert fm["meeting_url"] == "https://meet.google.com/abc-defg"

    def test_all_day_false_in_frontmatter(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert fm["all_day"] is False

    def test_all_day_true_in_frontmatter(self, minimal_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(minimal_event))
        assert fm["all_day"] is True

    def test_none_optional_fields_omitted(self, minimal_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(minimal_event))
        # These are None in minimal_event and should not appear
        assert "organizer" not in fm
        assert "meeting_url" not in fm
        assert "location" not in fm
        assert "recurrence" not in fm
        assert "url" not in fm

    def test_all_day_always_present_even_when_false(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert "all_day" in fm

    def test_resource_type_is_event(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert fm["resource_type"] == "event"

    def test_provider_id_in_frontmatter(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert fm["provider_id"] == "google_calendar"

    def test_saved_date_today(self, sample_event: Event) -> None:
        from datetime import date

        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert fm["saved_date"] == date.today().isoformat()

    def test_recurrence_in_frontmatter(self, sample_event: Event) -> None:
        fm = _parse_frontmatter(convert_event_to_markdown(sample_event))
        assert fm["recurrence"] == "RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"

    def test_ends_with_newline(self, sample_event: Event) -> None:
        result = convert_event_to_markdown(sample_event)
        assert result.endswith("\n")


# ── TestConvertFileToMarkdown ─────────────────────────────────────────────────


class TestConvertFileToMarkdown:
    def test_returns_string(self, sample_file: File) -> None:
        result = convert_file_to_markdown(sample_file)
        assert isinstance(result, str)

    def test_starts_with_frontmatter_delimiter(self, sample_file: File) -> None:
        result = convert_file_to_markdown(sample_file)
        assert result.startswith("---\n")

    def test_contains_yaml_frontmatter(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert fm["id"] == "doc_001"
        assert fm["title"] == "Q4 Planning Notes"
        assert fm["mime_type"] == "application/vnd.google-apps.document"

    def test_title_as_h1(self, sample_file: File) -> None:
        result = convert_file_to_markdown(sample_file)
        assert "# Q4 Planning Notes" in result

    def test_content_included_when_present(self, sample_file: File) -> None:
        result = convert_file_to_markdown(sample_file)
        assert "This is the document content." in result

    def test_no_content_section_when_none(self, file_no_content: File) -> None:
        result = convert_file_to_markdown(file_no_content)
        after_h1 = result.split("# budget.pdf", 1)[-1]
        assert after_h1.strip() == ""

    def test_content_truncated_at_10k(self, sample_file: File) -> None:
        long_content = "x" * (MAX_FILE_CONTENT_CHARS + 500)
        sample_file["content"] = long_content  # type: ignore[typeddict-item]
        result = convert_file_to_markdown(sample_file)
        assert "*[Content truncated at 10,000 characters]*" in result
        # The actual content portion should be exactly MAX_FILE_CONTENT_CHARS chars
        content_start = result.index("# Q4 Planning Notes\n\n") + len("# Q4 Planning Notes\n\n")
        content_end = result.index("\n\n*[Content truncated")
        assert len(result[content_start:content_end]) == MAX_FILE_CONTENT_CHARS

    def test_no_truncation_notice_for_short_content(self, sample_file: File) -> None:
        result = convert_file_to_markdown(sample_file)
        assert "truncated" not in result

    def test_size_always_in_frontmatter(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert "size" in fm
        assert fm["size"] == 0

    def test_is_folder_always_in_frontmatter(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert "is_folder" in fm
        assert fm["is_folder"] is False

    def test_none_path_omitted(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert "path" not in fm

    def test_parent_id_in_frontmatter(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert fm["parent_id"] == "folder_abc"

    def test_resource_type_is_file(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert fm["resource_type"] == "file"

    def test_provider_id_in_frontmatter(self, sample_file: File) -> None:
        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert fm["provider_id"] == "google_drive"

    def test_saved_date_today(self, sample_file: File) -> None:
        from datetime import date

        fm = _parse_frontmatter(convert_file_to_markdown(sample_file))
        assert fm["saved_date"] == date.today().isoformat()

    def test_ends_with_newline(self, sample_file: File) -> None:
        result = convert_file_to_markdown(sample_file)
        assert result.endswith("\n")


# ── TestConvertResourceToMarkdown ─────────────────────────────────────────────


class TestConvertResourceToMarkdown:
    def test_dispatches_event(self, sample_event: Event) -> None:
        result = convert_resource_to_markdown(sample_event)
        fm = _parse_frontmatter(result)
        assert fm["resource_type"] == "event"

    def test_dispatches_file(self, sample_file: File) -> None:
        result = convert_resource_to_markdown(sample_file)
        fm = _parse_frontmatter(result)
        assert fm["resource_type"] == "file"

    def test_unknown_type_raises_value_error(self) -> None:
        from iobox.providers.base import Resource

        bad: Resource = Resource(
            id="x",
            provider_id="unknown",
            resource_type="widget",
            title="oops",
            created_at="",
            modified_at="",
            url=None,
        )
        with pytest.raises(ValueError, match="Unknown resource_type"):
            convert_resource_to_markdown(bad)

    def test_none_type_raises_value_error(self) -> None:
        from iobox.providers.base import Resource

        bad: Resource = Resource(
            id="x",
            provider_id="unknown",
            resource_type=None,  # type: ignore[typeddict-item]
            title="oops",
            created_at="",
            modified_at="",
            url=None,
        )
        with pytest.raises(ValueError, match="Unknown resource_type"):
            convert_resource_to_markdown(bad)


# ── TestConvertMessageToMarkdown ──────────────────────────────────────────────


class TestConvertMessageToMarkdown:
    def test_delegates_to_existing_converter(self) -> None:
        from unittest.mock import patch

        # The import is lazy, so patch at the source module
        with patch("iobox.processing.markdown_converter.convert_email_to_markdown") as mock_conv:
            mock_conv.return_value = "# Subject\n\nbody"
            msg: dict = {
                "message_id": "m1",
                "subject": "Hello",
                "from_": "alice@x.com",
                "date": "2026-01-01",
                "snippet": "",
                "labels": [],
                "thread_id": "t1",
            }
            result = convert_message_to_markdown(msg)  # type: ignore[arg-type]

        mock_conv.assert_called_once_with(msg)
        assert result == "# Subject\n\nbody"
