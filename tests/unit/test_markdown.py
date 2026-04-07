"""
Unit tests for the markdown conversion module.

This module tests the functionality of the markdown.py module which is responsible
for converting email content to markdown with YAML frontmatter.
"""

from datetime import datetime
from unittest.mock import patch

from iobox.processing.markdown_converter import (
    _clean_email_markdown,
    convert_email_to_markdown,
    convert_html_to_markdown,
    convert_thread_to_markdown,
    generate_yaml_frontmatter,
    strip_html_tags,
)
from iobox.utils import create_markdown_filename


class TestMarkdownConversion:
    """Test cases for the markdown conversion module."""

    def test_strip_html_tags(self):
        """Test stripping HTML tags from content."""
        html_content = (
            "<html><body><h1>Hello</h1><p>This is a <strong>test</strong>.</p></body></html>"
        )
        plain_text = strip_html_tags(html_content)

        assert "<html>" not in plain_text
        assert "<body>" not in plain_text
        assert "<h1>" not in plain_text
        assert "<p>" not in plain_text
        assert "<strong>" not in plain_text
        assert "Hello" in plain_text
        assert "This is a test." in plain_text

    def test_generate_yaml_frontmatter(self):
        """Test generating YAML frontmatter from email data."""
        email_data = {
            "id": "message-id-1",
            "thread_id": "thread-id-1",
            "subject": "Test Email Subject",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "labels": ["INBOX", "CATEGORY_PERSONAL"],
            "attachments": [{"filename": "document.pdf", "mime_type": "application/pdf"}],
        }

        frontmatter = generate_yaml_frontmatter(email_data)

        # Verify all key email data is included in the frontmatter
        assert "---" in frontmatter
        assert "message_id: message-id-1" in frontmatter
        assert "thread_id: thread-id-1" in frontmatter
        assert "subject: Test Email Subject" in frontmatter
        assert "from: sender@example.com" in frontmatter
        assert "to: recipient@example.com" in frontmatter
        assert "date: Mon, 23 Mar 2025 10:00:00 +1100" in frontmatter
        assert "labels:" in frontmatter
        assert "  - INBOX" in frontmatter
        assert "  - CATEGORY_PERSONAL" in frontmatter
        assert "attachments:" in frontmatter
        assert "  - filename: document.pdf" in frontmatter
        assert "    mime_type: application/pdf" in frontmatter

    def test_create_markdown_filename(self):
        """Test creating a valid markdown filename from email data."""
        email_data = {
            "subject": "Test: Email Subject with Special Characters!",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
        }

        # Mock datetime to ensure consistent test results
        with patch("iobox.utils.datetime") as mock_datetime:
            mock_datetime.strptime.return_value = datetime(2025, 3, 23, 10, 0, 0)
            mock_datetime.now.return_value = datetime(2025, 3, 23, 10, 0, 0)

            filename = create_markdown_filename(email_data)

            # Verify filename format and sanitization
            assert filename.endswith(".md")
            assert "test-email-subject" in filename
            assert "!" not in filename  # Special characters should be removed
            assert ":" not in filename  # Special characters should be removed
            assert " " not in filename  # Spaces should be replaced with hyphens

    def test_convert_email_to_markdown_plain_text(self):
        """Test converting a plain text email to markdown."""
        email_data = {
            "id": "message-id-1",
            "thread_id": "thread-id-1",
            "subject": "Test Email Subject",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "body": "This is a plain text email.\n\nWith multiple paragraphs.",
            "content_type": "text/plain",
            "labels": ["INBOX"],
        }

        markdown_content = convert_email_to_markdown(email_data)

        # Verify frontmatter is included
        assert "---" in markdown_content
        assert "subject: Test Email Subject" in markdown_content

        # Verify email body is preserved and properly formatted
        assert "This is a plain text email." in markdown_content
        assert "With multiple paragraphs." in markdown_content

    def test_convert_email_to_markdown_html(self):
        """Test converting an HTML email to markdown."""
        email_data = {
            "id": "message-id-1",
            "thread_id": "thread-id-1",
            "subject": "Test Email Subject",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "body": "<html><body><h1>Hello</h1><p>This is an HTML email.</p></body></html>",
            "content_type": "text/html",
            "labels": ["INBOX"],
        }

        markdown_content = convert_email_to_markdown(email_data)

        # Verify frontmatter is included
        assert "---" in markdown_content
        assert "subject: Test Email Subject" in markdown_content

        # Verify HTML content is converted to markdown syntax
        assert "# Hello" in markdown_content or "Hello" in markdown_content
        assert "This is an HTML email." in markdown_content


class TestHtmlToMarkdownConversion:
    """Test cases for HTML to markdown conversion functionality."""

    def test_convert_html_to_markdown_basic(self):
        """Test basic HTML to markdown conversion."""
        html_content = "<h1>Hello World</h1><p>This is a <strong>test</strong> email.</p>"
        markdown = convert_html_to_markdown(html_content)

        assert "# Hello World" in markdown
        assert "**test**" in markdown
        assert "This is a" in markdown
        assert "email." in markdown

    def test_convert_html_to_markdown_with_links(self):
        """Test HTML with links conversion."""
        html_content = '<p>Visit <a href="https://example.com">our website</a> for more info.</p>'
        markdown = convert_html_to_markdown(html_content)

        assert "[our website](https://example.com)" in markdown
        assert "Visit" in markdown
        assert "for more info." in markdown

    def test_convert_html_to_markdown_with_images(self):
        """Test HTML with images conversion."""
        html_content = '<img src="https://example.com/image.jpg" alt="Test Image">'
        markdown = convert_html_to_markdown(html_content)

        assert "![Test Image](https://example.com/image.jpg)" in markdown

    def test_convert_html_to_markdown_with_lists(self):
        """Test HTML lists conversion."""
        html_content = """
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
        </ul>
        """
        markdown = convert_html_to_markdown(html_content)

        assert "* Item 1" in markdown or "- Item 1" in markdown
        assert "* Item 2" in markdown or "- Item 2" in markdown
        assert "* Item 3" in markdown or "- Item 3" in markdown

    def test_convert_html_to_markdown_with_table(self):
        """Test HTML table conversion."""
        html_content = """
        <table>
            <tr><th>Name</th><th>Email</th></tr>
            <tr><td>John</td><td>john@example.com</td></tr>
            <tr><td>Jane</td><td>jane@example.com</td></tr>
        </table>
        """
        markdown = convert_html_to_markdown(html_content)

        # Should contain table formatting
        assert "Name" in markdown
        assert "Email" in markdown
        assert "John" in markdown
        assert "john@example.com" in markdown

    def test_convert_html_to_markdown_complex_email(self):
        """Test conversion of complex email HTML."""
        html_content = """
        <html>
        <body>
            <h2>Newsletter Update</h2>
            <p>Dear subscriber,</p>
            <p>Here are the latest updates:</p>
            <ul>
                <li><a href="https://example.com/article1">New Article Published</a></li>
                <li><strong>Important:</strong> Policy Changes</li>
            </ul>
            <p>Best regards,<br/>The Team</p>
            <hr/>
            <small>Unsubscribe at <a href="https://example.com/unsubscribe">this link</a></small>
        </body>
        </html>
        """
        markdown = convert_html_to_markdown(html_content)

        assert "## Newsletter Update" in markdown
        assert "Dear subscriber" in markdown
        assert "[New Article Published](https://example.com/article1)" in markdown
        assert "**Important:**" in markdown
        assert "The Team" in markdown
        assert "[this link](https://example.com/unsubscribe)" in markdown

    def test_convert_html_to_markdown_error_handling(self):
        """Test error handling with malformed HTML."""
        malformed_html = "<html><body><p>Unclosed tag<strong>Bold text</body></html>"

        # Should not raise an exception
        markdown = convert_html_to_markdown(malformed_html)
        assert "Bold text" in markdown
        assert "Unclosed tag" in markdown

    def test_clean_email_markdown(self):
        """Test cleaning email-specific markdown artifacts."""
        messy_markdown = """
        # Title



        Some content.

        ![]()

        [  ](https://tracker.example.com)

        Some more content.
        ==================

        Final paragraph.
        """

        cleaned = _clean_email_markdown(messy_markdown)

        # Should have reduced blank lines
        assert "\n\n\n" not in cleaned
        # Should remove empty images
        assert "![]()" not in cleaned
        # Should remove empty links
        assert "[  ]" not in cleaned
        # Should normalize signature lines
        assert "---" in cleaned
        # Should not have trailing spaces
        assert "content.   " not in cleaned

    def test_convert_email_to_markdown_html_with_body_field(self):
        """Test email conversion using the body field with HTML content."""
        email_data = {
            "message_id": "test-message-1",
            "subject": "HTML Email Test",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "body": "<h1>Welcome</h1><p>This is an <em>HTML</em> email with <a href='https://example.com'>links</a>.</p>",
            "content_type": "text/html",
            "labels": ["INBOX"],
        }

        markdown_content = convert_email_to_markdown(email_data)

        # Should have frontmatter
        assert "---" in markdown_content
        assert "subject: HTML Email Test" in markdown_content

        # Should have converted HTML to markdown
        assert "# Welcome" in markdown_content
        assert "*HTML*" in markdown_content or "_HTML_" in markdown_content
        assert "[links](https://example.com)" in markdown_content

    def test_convert_email_to_markdown_fallback_to_content_field(self):
        """Test that conversion falls back to content field if body is missing."""
        email_data = {
            "message_id": "test-message-2",
            "subject": "Fallback Test",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "content": "<p>This content is in the <strong>content</strong> field.</p>",
            "content_type": "text/html",
            "labels": ["INBOX"],
        }

        markdown_content = convert_email_to_markdown(email_data)

        # Should still work with content field
        assert "**content**" in markdown_content
        assert "This content is in" in markdown_content


class TestConvertThreadToMarkdown:
    """Tests for convert_thread_to_markdown()."""

    def _make_message(self, msg_id, sender, date, body, labels=None):
        return {
            "message_id": msg_id,
            "thread_id": "thread-123",
            "subject": "Test Thread",
            "from": sender,
            "to": "me@example.com",
            "date": date,
            "labels": labels or ["INBOX"],
            "body": body,
            "content_type": "text/plain",
        }

    def test_convert_thread_to_markdown_frontmatter(self):
        """YAML frontmatter contains thread_id, message_count, and subject."""
        messages = [
            self._make_message(
                "msg-1", "a@example.com", "Mon, 01 Jan 2024 00:00:00 +0000", "Hello"
            ),
            self._make_message(
                "msg-2", "b@example.com", "Tue, 02 Jan 2024 00:00:00 +0000", "Reply"
            ),
        ]
        result = convert_thread_to_markdown(messages)

        assert "thread_id: thread-123" in result
        assert "message_count: 2" in result
        assert "subject: Test Thread" in result

    def test_convert_thread_to_markdown_sections(self):
        """Each message becomes a section with a From/date header."""
        messages = [
            self._make_message("msg-1", "a@example.com", "Mon", "First message body"),
            self._make_message("msg-2", "b@example.com", "Tue", "Second message body"),
        ]
        result = convert_thread_to_markdown(messages)

        assert "## From: a@example.com — Mon" in result
        assert "First message body" in result
        assert "## From: b@example.com — Tue" in result
        assert "Second message body" in result

    def test_convert_thread_to_markdown_separator(self):
        """Messages are separated by horizontal rules."""
        messages = [
            self._make_message("msg-1", "a@example.com", "Mon", "Msg 1"),
            self._make_message("msg-2", "b@example.com", "Tue", "Msg 2"),
        ]
        result = convert_thread_to_markdown(messages)

        assert "---" in result

    def test_convert_thread_to_markdown_empty(self):
        """Empty message list returns empty string."""
        result = convert_thread_to_markdown([])
        assert result == ""

    def test_convert_thread_to_markdown_unique_labels(self):
        """Labels from all messages are deduplicated in frontmatter."""
        messages = [
            self._make_message(
                "msg-1", "a@example.com", "Mon", "Msg 1", labels=["INBOX", "UNREAD"]
            ),
            self._make_message(
                "msg-2", "b@example.com", "Tue", "Msg 2", labels=["INBOX", "STARRED"]
            ),
        ]
        result = convert_thread_to_markdown(messages)

        # INBOX should appear exactly once
        label_lines = [line for line in result.split("\n") if "- INBOX" in line]
        assert len(label_lines) == 1
        assert "- STARRED" in result
        assert "- UNREAD" in result
