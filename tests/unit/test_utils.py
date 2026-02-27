"""
Unit tests for the utils module.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from iobox.utils import slugify_text, create_markdown_filename


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
            "date": "Mon, 23 Mar 2025 10:00:00 +1100"
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
        email_data = {
            "subject": "Test Subject",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100"
        }
        with patch("iobox.utils.datetime") as mock_dt:
            mock_dt.strptime.return_value = datetime(2025, 3, 23, 10, 0, 0)
            mock_dt.now.return_value = datetime(2025, 3, 23, 10, 0, 0)

            filename = create_markdown_filename(email_data)
            assert filename.endswith(".md")

    def test_missing_id_and_subject_raises(self):
        with pytest.raises(ValueError, match="missing message_id"):
            create_markdown_filename({})

    def test_date_parsing_fallback(self):
        email_data = {
            "message_id": "msg1",
            "subject": "Test",
            "date": "not-a-date"
        }
        with patch("iobox.utils.datetime") as mock_dt:
            mock_dt.strptime.side_effect = ValueError("bad date")
            mock_now = MagicMock()
            mock_now.strftime.return_value = "2025-01-01"
            mock_dt.now.return_value = mock_now

            filename = create_markdown_filename(email_data)
            assert filename.endswith(".md")
            assert filename.startswith("2025-01-01")
