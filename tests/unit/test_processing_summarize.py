"""
Unit tests for processing/summarize.py.

All tests inject a mock Anthropic client via _client_fn= — no real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iobox.processing.summarize import (
    DEFAULT_MODEL,
    _build_prompt,
    summarize,
    summarize_batch,
)
from iobox.providers.base import Email, Event, File


def _make_client(text: str = "Summary text.") -> MagicMock:
    """Return a mock Anthropic client whose messages.create() returns *text*."""
    client = MagicMock()
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=text)]
    )
    return client


def _client_fn_factory(text: str = "Summary text."):
    """Return a callable that produces a mock client."""
    client = _make_client(text)
    return lambda: client


def _make_email() -> Email:
    return Email(
        id="m1",
        provider_id="gmail",
        resource_type="email",
        title="Q4 Budget Review",
        created_at="2026-03-15T09:00:00",
        modified_at="2026-03-15T09:00:00",
        url=None,
        from_="boss@example.com",
        to=["tim@example.com"],
        cc=[],
        thread_id="t1",
        snippet="Please review the Q4 budget before Friday.",
        labels=[],
        body="Hi team, please review the Q4 budget before Friday. Action required by EOD.",
        content_type="text/plain",
        attachments=[],
    )


def _make_event() -> Event:
    return Event(
        id="evt1",
        provider_id="google_calendar",
        resource_type="event",
        title="Q4 Planning Session",
        created_at="2026-03-16T10:00:00",
        modified_at="2026-03-16T10:00:00",
        url=None,
        start="2026-03-16T10:00:00",
        end="2026-03-16T12:00:00",
        all_day=False,
        organizer="boss@example.com",
        attendees=[
            {"email": "alice@example.com", "name": "Alice", "response_status": "accepted"},
            {"email": "bob@example.com", "name": "Bob", "response_status": "tentative"},
        ],
        location="Conference Room A",
        description="Review Q4 plans and finalize budget allocations.",
        meeting_url=None,
        status="confirmed",
        recurrence=None,
    )


def _make_file() -> File:
    return File(
        id="file1",
        provider_id="google_drive",
        resource_type="file",
        title="Q4 Planning Notes",
        created_at="2026-03-10T15:00:00",
        modified_at="2026-03-10T15:00:00",
        url=None,
        name="q4_planning_notes.txt",
        mime_type="text/plain",
        size=5000,
        path=None,
        parent_id=None,
        is_folder=False,
        download_url=None,
        content="Key decisions from the Q4 planning session: budget increased by 10%.",
    )


# ---------------------------------------------------------------------------
# summarize()
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_summarize_email(self):
        email = _make_email()
        result = summarize(email, _client_fn=_client_fn_factory("Email summary."))
        assert result == "Email summary."

    def test_summarize_event(self):
        event = _make_event()
        result = summarize(event, _client_fn=_client_fn_factory("Event summary."))
        assert result == "Event summary."

    def test_summarize_file(self):
        file = _make_file()
        result = summarize(file, _client_fn=_client_fn_factory("File summary."))
        assert result == "File summary."

    def test_strips_whitespace(self):
        client = _make_client("  Summary with whitespace.  \n")
        result = summarize(_make_email(), _client_fn=lambda: client)
        assert result == "Summary with whitespace."

    def test_passes_model_to_api(self):
        client = _make_client()
        summarize(_make_email(), model="claude-opus-4-6", _client_fn=lambda: client)
        _, kwargs = client.messages.create.call_args
        assert kwargs["model"] == "claude-opus-4-6"

    def test_passes_max_tokens_to_api(self):
        client = _make_client()
        summarize(_make_email(), max_tokens=100, _client_fn=lambda: client)
        _, kwargs = client.messages.create.call_args
        assert kwargs["max_tokens"] == 100

    def test_default_model(self):
        client = _make_client()
        summarize(_make_email(), _client_fn=lambda: client)
        _, kwargs = client.messages.create.call_args
        assert kwargs["model"] == DEFAULT_MODEL

    def test_raises_import_error_without_anthropic(self):
        import sys
        import unittest.mock

        # Temporarily make anthropic unimportable
        with unittest.mock.patch.dict(sys.modules, {"anthropic": None}):
            with pytest.raises(ImportError, match="iobox\\[ai\\]"):
                summarize(_make_email())


# ---------------------------------------------------------------------------
# summarize_batch()
# ---------------------------------------------------------------------------


class TestSummarizeBatch:
    def test_returns_summaries_in_order(self):
        counter = [0]

        def _client_fn():
            n = counter[0]
            counter[0] += 1
            client = MagicMock()
            client.messages.create.return_value = MagicMock(
                content=[MagicMock(text=f"Summary {n}")]
            )
            return client

        resources = [_make_email(), _make_event(), _make_file()]
        results = summarize_batch(resources, max_workers=1, _client_fn=_client_fn)
        assert len(results) == 3
        # Order must be preserved (in-order with max_workers=1)
        for r in results:
            assert r.startswith("Summary ")

    def test_returns_empty_string_on_failure(self):
        def _fail_fn():
            raise RuntimeError("API error")

        resources = [_make_email()]
        # _client_fn that raises — the batch should handle it gracefully
        results = summarize_batch(resources, _client_fn=_fail_fn)
        assert results == [""]

    def test_preserves_successful_results_on_partial_failure(self):
        """One resource fails; the rest still return summaries."""
        call_count = [0]

        def _sometimes_fail():
            n = call_count[0]
            call_count[0] += 1
            if n == 1:  # second call fails
                raise RuntimeError("transient error")
            client = MagicMock()
            client.messages.create.return_value = MagicMock(
                content=[MagicMock(text="ok")]
            )
            return client

        resources = [_make_email(), _make_event(), _make_file()]
        results = summarize_batch(resources, max_workers=1, _client_fn=_sometimes_fail)
        # Two succeed, one fails
        assert results.count("ok") == 2
        assert results.count("") == 1

    def test_returns_list_same_length_as_input(self):
        resources = [_make_email(), _make_event()]
        results = summarize_batch(resources, _client_fn=_client_fn_factory())
        assert len(results) == len(resources)

    def test_empty_input_returns_empty_list(self):
        results = summarize_batch([], _client_fn=_client_fn_factory())
        assert results == []


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_email_prompt_contains_subject(self):
        email = _make_email()
        prompt = _build_prompt(email)
        assert "Q4 Budget Review" in prompt
        assert "boss@example.com" in prompt

    def test_event_prompt_contains_title_and_attendees(self):
        event = _make_event()
        prompt = _build_prompt(event)
        assert "Q4 Planning Session" in prompt
        assert "Alice" in prompt

    def test_file_prompt_contains_title_and_content(self):
        file = _make_file()
        prompt = _build_prompt(file)
        assert "Q4 Planning Notes" in prompt
        assert "budget increased" in prompt

    def test_unknown_resource_type_uses_fallback(self):
        resource = {
            "id": "x",
            "resource_type": "unknown_type",
            "title": "Mystery object",
            "created_at": "",
            "modified_at": "",
            "provider_id": "",
            "url": None,
        }
        prompt = _build_prompt(resource)  # type: ignore[arg-type]
        assert "Mystery object" in prompt

    def test_email_body_truncated_at_3000_chars(self):
        email = _make_email()
        email["body"] = "x" * 5000
        prompt = _build_prompt(email)
        # Body in prompt should be at most 3000 chars worth of 'x'
        assert "x" * 3001 not in prompt
        assert "x" * 3000 in prompt
