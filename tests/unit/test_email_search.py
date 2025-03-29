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
    MOCK_PLAIN_TEXT_MESSAGE,
    MOCK_HTML_MESSAGE,
    MOCK_ATTACHMENT_MESSAGE,
    MOCK_PLAIN_TEXT_ONLY_MESSAGE
)


class TestEmailSearch:
    """Test cases for the email search module."""
    
    def test_search_emails_basic(self, mock_gmail_service):
        """Test basic email search functionality."""
        # Setup mock message list response with properly structured data
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "messages": [
                {"id": "message-id-1", "threadId": "thread-id-1"},
                {"id": "message-id-2", "threadId": "thread-id-2"},
                {"id": "message-id-3", "threadId": "thread-id-3"}
            ],
            "resultSizeEstimate": 3
        }
        
        # Set up service method chain for the initial search
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)
        
        # Mock the get message details calls with proper return values
        msg1 = {"id": "message-id-1", "threadId": "thread-id-1", "snippet": "Message 1"}
        msg2 = {"id": "message-id-2", "threadId": "thread-id-2", "snippet": "Message 2"}
        msg3 = {"id": "message-id-3", "threadId": "thread-id-3", "snippet": "Message 3"}
        
        mock_get1 = MagicMock()
        mock_get1.execute.return_value = msg1
        
        mock_get2 = MagicMock()
        mock_get2.execute.return_value = msg2
        
        mock_get3 = MagicMock()
        mock_get3.execute.return_value = msg3
        
        # Setup the message.get method to return appropriate mocks based on message ID
        def get_side_effect(userId, id, format, metadataHeaders=None):
            if id == "message-id-1":
                return mock_get1
            elif id == "message-id-2":
                return mock_get2
            elif id == "message-id-3":
                return mock_get3
            else:
                raise ValueError(f"Unexpected ID: {id}")
                
        mock_get = MagicMock()
        mock_get.side_effect = get_side_effect
        mock_gmail_service.users().messages().get = mock_get
        
        # Patch datetime to return a fixed date for testing
        with patch('iobox.email_search.datetime') as mock_datetime:
            # Set up the mock to return a specific date
            mock_date = MagicMock()
            mock_date.now.return_value = mock_date
            mock_date.__sub__.return_value = mock_date
            mock_date.strftime.return_value = '2025/03/23'
            mock_datetime.now.return_value = mock_date
            mock_datetime.timedelta = MagicMock(return_value=mock_date)
            
            # Call the search function
            results = search_emails(
                service=mock_gmail_service,
                query="from:example.com",
                max_results=10
            )
            
            # Verify results
            assert len(results) == 3
            assert results[0]["id"] == "message-id-1"
            assert results[1]["id"] == "message-id-2"
            assert results[2]["id"] == "message-id-3"
            
            # Verify that message.get was called for each message
            assert mock_get.call_count == 3
    
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
        
        # Verify email data
        assert email_data["message_id"] == "message-id-1"
        assert email_data["subject"] == "Test Email Subject"
        assert email_data["from"] == "sender@example.com"
        assert email_data["content"] == "This is the plain text body of the email.\n"
        assert email_data["content_type"] == "text/plain"
    
    def test_get_email_content_html(self, mock_gmail_service):
        """Test retrieving an HTML email."""
        # Setup mock message response
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_HTML_MESSAGE
        
        # Set up service method chain
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Call the get email content function, requesting HTML
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
        
        # Verify HTML content was preferred
        expected_html = "<html><body><p>This is the HTML version of the email.</p></body></html>"
        assert email_data["message_id"] == "message-id-2"
        assert email_data["subject"] == "HTML Email Subject"
        assert email_data["content"] == expected_html
        assert email_data["content_type"] == "text/html"
    
    def test_get_email_content_plaintext_fallback(self, mock_gmail_service):
        """Test fallback to plain text when HTML is preferred but unavailable."""
        # Setup mock message response
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_PLAIN_TEXT_ONLY_MESSAGE
        
        # Set up service method chain
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Call the get email content function, requesting HTML
        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-2",
            preferred_content_type="text/html"  # Request HTML but will fall back to plain text
        )
        
        # Verification of API call
        mock_gmail_service.users().messages().get.assert_called_once_with(
            userId='me',
            id="message-id-2",
            format="full"
        )
        
        # Verify fallback to plain text
        expected_plain = "This is the plain text version of the HTML email."
        assert email_data["message_id"] == "message-id-2"
        assert email_data["subject"] == "HTML Email Subject"
        assert email_data["content"] == expected_plain
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
        assert email_data["attachments"][0]["id"] == "attachment-id-1"
