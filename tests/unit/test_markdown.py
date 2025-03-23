"""
Unit tests for the markdown conversion module.

This module tests the functionality of the markdown.py module which is responsible
for converting email content to markdown with YAML frontmatter.
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from iobox.markdown import (
    convert_email_to_markdown,
    generate_yaml_frontmatter,
    create_markdown_filename,
    strip_html_tags
)


class TestMarkdownConversion:
    """Test cases for the markdown conversion module."""
    
    def test_strip_html_tags(self):
        """Test stripping HTML tags from content."""
        html_content = "<html><body><h1>Hello</h1><p>This is a <strong>test</strong>.</p></body></html>"
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
            "attachments": [
                {"filename": "document.pdf", "mime_type": "application/pdf"}
            ]
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
            "date": "Mon, 23 Mar 2025 10:00:00 +1100"
        }
        
        # Mock datetime to ensure consistent test results
        with patch("iobox.markdown.datetime") as mock_datetime:
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
            "labels": ["INBOX"]
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
            "labels": ["INBOX"]
        }
        
        markdown_content = convert_email_to_markdown(email_data)
        
        # Verify frontmatter is included
        assert "---" in markdown_content
        assert "subject: Test Email Subject" in markdown_content
        
        # Verify HTML content is converted to markdown syntax
        assert "# Hello" in markdown_content or "Hello" in markdown_content
        assert "This is an HTML email." in markdown_content
