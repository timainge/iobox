"""
Unit tests for the utils module.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from iobox.utils import create_markdown_filename, parse_email_date, slugify_text


class TestSlugifyText:
    """Test cases for slugify_text."""

    def test_basic_slugify(self):
        text = "Hello World"
        assert slugify_text(text) == "hello-world"

    def test_special_characters_removed(self):
        text = "Test: Email Subject with Special Characters!"
        result = slugify_text(text)
        assert ":" not in result
        assert "!" not in result

    def test_max_length(self):
        text = "a" * 100
        result = slugify_text(text, max_length=50)
        assert len(result) == 50

    def test_multiple_spaces(self):
        text = "hello   world   test"
        result = slugify_text(text)
        assert result == "hello-world-test"

    def test_empty_string(self):
        assert slugify_text("") == ""

    def test_strips_whitespace(self):
        assert slugify_text("  hello  ") == "hello"


class TestCreateMarkdownFilename:
    """Test cases for create_markdown_filename."""

    def test_filename_with_subject(self):
        email_data = {
            "subject": "Test Email Subject",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
        }

        with patch("iobox.utils.datetime") as mock_dt:
            mock_dt.strptime.return_value = datetime(2025, 3, 23, 10, 0, 0)
            mock_dt.now.return_value = datetime(2025, 3, 23, 10, 0, 0)

            filename = create_markdown_filename(email_data)

            assert filename.endswith(".md")
            assert "test-email-subject" in filename
            assert " " not in filename

    def test_filename_without_subject(self):
        email_data = {
            "message_id": "abc123",
            "subject": "Test",
        }
        filename = create_markdown_filename(email_data, use_subject=False)
        assert filename == "abc123.md"

    def test_missing_id_uses_subject_hash(self):
        email_data = {"subject": "Test Subject", "date": "Mon, 23 Mar 2025 10:00:00 +1100"}
        with patch("iobox.utils.datetime") as mock_dt:
            mock_dt.strptime.return_value = datetime(2025, 3, 23, 10, 0, 0)
            mock_dt.now.return_value = datetime(2025, 3, 23, 10, 0, 0)

            filename = create_markdown_filename(email_data)
            assert filename.endswith(".md")

    def test_missing_id_and_subject_raises(self):
        with pytest.raises(ValueError, match="missing message_id"):
            create_markdown_filename({})

    def test_date_parsing_fallback(self):
        email_data = {"message_id": "msg1", "subject": "Test", "date": "not-a-date"}
        with patch("iobox.utils.datetime", wraps=datetime) as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
            mock_dt.fromisoformat.side_effect = ValueError("bad date")

            filename = create_markdown_filename(email_data)
            assert filename == "2025-01-01-test.md"


class TestDatePrefix:
    """DATA-06: the date prefix comes from the email's own date in common formats."""

    @pytest.mark.parametrize(
        "date_str",
        [
            "Mon, 23 Mar 2025 10:00:00 +1100",
            "Sun, 2 Mar 2025 10:00:00 +0000",  # one-digit day
            "2 Mar 2025 10:00:00 +0000",  # no weekday
            "Sun, 2 Mar 2025 10:00:00 +0000 (UTC)",  # trailing comment
        ],
    )
    def test_rfc2822_dates(self, date_str):
        filename = create_markdown_filename({"message_id": "m", "subject": "Hi", "date": date_str})
        expected_day = "23" if "23 Mar" in date_str else "02"
        assert filename == f"2025-03-{expected_day}-hi.md"

    @pytest.mark.parametrize(
        "date_str",
        [
            "2025-03-02T10:00:00Z",
            "2025-03-02T10:00:00+00:00",
            "2025-03-02T10:00:00.0000000Z",  # Graph-style 7-digit fraction
            "2025-03-02",
        ],
    )
    def test_iso_dates(self, date_str):
        filename = create_markdown_filename({"message_id": "m", "subject": "Hi", "date": date_str})
        assert filename == "2025-03-02-hi.md"

    @pytest.mark.parametrize("date_str", ["", None, "garbage", "2025-13-45"])
    def test_unparseable_falls_back_to_today(self, date_str):
        filename = create_markdown_filename({"message_id": "m", "subject": "Hi", "date": date_str})
        assert filename == f"{datetime.now().strftime('%Y-%m-%d')}-hi.md"

    def test_parse_email_date_none(self):
        assert parse_email_date(None) is None
        assert parse_email_date("nope") is None


class TestSubjectFallback:
    """DATA-13: missing/empty/symbol-only subjects fall back to the message ID."""

    @pytest.mark.parametrize("subject", [None, "", "   ", "!!!", "???:::"])
    def test_uses_message_id(self, subject):
        filename = create_markdown_filename(
            {"message_id": "abc123", "subject": subject, "date": "2025-03-02"}
        )
        assert filename == "2025-03-02-abc123.md"

    def test_missing_subject_key(self):
        filename = create_markdown_filename({"message_id": "abc123", "date": "2025-03-02"})
        assert filename == "2025-03-02-abc123.md"

    def test_message_id_is_sanitised(self):
        filename = create_markdown_filename(
            {"message_id": "AAMk/a+b=../x", "subject": None, "date": "2025-03-02"}
        )
        assert filename == "2025-03-02-AAMk_a_b____x.md"
        assert "/" not in filename

    def test_message_id_only_filename_is_sanitised(self):
        filename = create_markdown_filename({"message_id": "a/b"}, use_subject=False)
        assert filename == "a_b.md"

    def test_none_subject_no_id_raises(self):
        with pytest.raises(ValueError):
            create_markdown_filename({"subject": None})

    def test_slugify_none(self):
        assert slugify_text(None) == ""
