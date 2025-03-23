"""
Unit tests for the email search module.

This module tests the core functionality of the email_search.py module which is responsible
for searching and retrieving emails from Gmail API.
"""

import pytest
from unittest.mock import patch, MagicMock
import base64

from iobox.email_search import search_emails, get_email_content
from tests.fixtures.mock_responses import (
    MOCK_MESSAGE_LIST,
    MOCK_PLAIN_TEXT_MESSAGE,
    MOCK_HTML_MESSAGE,
    MOCK_ATTACHMENT_MESSAGE
)


class TestEmailSearch:
    """Test cases for the email search module."""
    
    def test_search_emails_basic(self, mock_gmail_service):
        """Test basic email search functionality."""
        # Setup mock message list response
        mock_list = MagicMock()
        mock_list.execute.return_value = MOCK_MESSAGE_LIST
        
        # Set up service method chain
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)
        
        # Call the search function
        results = search_emails(
            service=mock_gmail_service,
            query="from:example.com",
            max_results=10
        )
        
        # Verify correct parameters were used
        mock_gmail_service.users().messages().list.assert_called_with(
            userId="me",
            q="from:example.com",
            maxResults=10
        )
        
        # Verify results
        assert len(results) == 3
        assert results[0]["id"] == "message-id-1"
        assert results[1]["id"] == "message-id-2"
        assert results[2]["id"] == "message-id-3"
    
    def test_search_emails_empty_results(self, mock_gmail_service):
        """Test email search with no results."""
        # Setup mock empty response
        mock_list = MagicMock()
        mock_list.execute.return_value = {"resultSizeEstimate": 0}
        
        # Set up service method chain
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)
        
        # Call the search function
        results = search_emails(
            service=mock_gmail_service,
            query="from:nonexistent@example.com",
            max_results=10
        )
        
        # Verify results are empty
        assert len(results) == 0
    
    def test_get_email_content_plain_text(self, mock_gmail_service):
        """Test retrieving a plain text email."""
        # Setup mock message response
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_PLAIN_TEXT_MESSAGE
        
        # Set up service method chain
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Call the get email content function
        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-1"
        )
        
        # Verify correct parameters were used
        mock_gmail_service.users().messages().get.assert_called_with(
            userId="me",
            id="message-id-1",
            format="full"
        )
        
        # Verify returned email data
        assert email_data["id"] == "message-id-1"
        assert email_data["subject"] == "Test Email Subject"
        assert email_data["from"] == "sender@example.com"
        assert email_data["to"] == "recipient@example.com"
        assert email_data["date"] == "Mon, 23 Mar 2025 10:00:00 +1100"
        
        # Verify body is decoded from base64
        expected_body = "This is the plain text body of the email.\n"
        assert email_data["body"] == expected_body
        assert email_data["content_type"] == "text/plain"
    
    def test_get_email_content_html(self, mock_gmail_service):
        """Test retrieving an HTML email."""
        # Setup mock message response
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_HTML_MESSAGE
        
        # Set up service method chain
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Call the get email content function
        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-2",
            preferred_content_type="text/html"
        )
        
        # Verify correct parameters were used
        mock_gmail_service.users().messages().get.assert_called_with(
            userId="me",
            id="message-id-2",
            format="full"
        )
        
        # Verify returned email data
        assert email_data["id"] == "message-id-2"
        assert email_data["subject"] == "HTML Email Subject"
        
        # Verify HTML content is returned when preferred
        expected_html = "<html><body><p>This is the HTML version of the email.</p></body></html>"
        assert email_data["body"] == expected_html
        assert email_data["content_type"] == "text/html"
    
    def test_get_email_content_plaintext_fallback(self, mock_gmail_service):
        """Test fallback to plain text when HTML is preferred but unavailable."""
        # Create a message with only plain text
        plain_text_only = dict(MOCK_HTML_MESSAGE)
        # Remove the HTML part from the multipart message
        plain_text_only["payload"]["parts"] = [plain_text_only["payload"]["parts"][0]]
        
        # Setup mock message response
        mock_get = MagicMock()
        mock_get.execute.return_value = plain_text_only
        
        # Set up service method chain
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Call the get email content function, requesting HTML
        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-2",
            preferred_content_type="text/html"  # Request HTML but will fall back to plain text
        )
        
        # Verify fallback to plain text
        expected_plain = "This is the plain text version of the HTML email."
        assert email_data["body"] == expected_plain
        assert email_data["content_type"] == "text/plain"
    
    def test_get_email_with_attachment(self, mock_gmail_service):
        """Test retrieving an email with attachment metadata."""
        # Setup mock message response
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_ATTACHMENT_MESSAGE
        
        # Set up service method chain
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Call the get email content function
        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-3"
        )
        
        # Verify attachments are properly extracted
        assert len(email_data["attachments"]) == 1
        assert email_data["attachments"][0]["filename"] == "document.pdf"
        assert email_data["attachments"][0]["mime_type"] == "application/pdf"
        assert email_data["attachments"][0]["size"] == 789
        assert email_data["attachments"][0]["attachment_id"] == "attachment-id-1"
