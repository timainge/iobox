"""
Unit tests for the email search module.

This module tests the core functionality of the email_search.py module which is responsible
for searching and retrieving emails from Gmail API.
"""

import pytest
from unittest.mock import patch, MagicMock
import base64

from iobox.email_search import search_emails, get_email_content, download_attachment, validate_date_format
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
        msg1 = {
            "id": "message-id-1", 
            "threadId": "thread-id-1", 
            "snippet": "Message 1",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject 1"},
                    {"name": "From", "value": "sender1@example.com"},
                    {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"}
                ]
            }
        }
        
        msg2 = {
            "id": "message-id-2", 
            "threadId": "thread-id-2", 
            "snippet": "Message 2",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject 2"},
                    {"name": "From", "value": "sender2@example.com"},
                    {"name": "Date", "value": "Tue, 02 Apr 2025 15:30:00 +0000"}
                ]
            }
        }
        
        msg3 = {
            "id": "message-id-3", 
            "threadId": "thread-id-3", 
            "snippet": "Message 3",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject 3"},
                    {"name": "From", "value": "sender3@example.com"},
                    {"name": "Date", "value": "Wed, 03 Apr 2025 09:15:00 +0000"}
                ]
            }
        }
        
        # Setup the message.get method to return appropriate mocks based on message ID
        def get_side_effect(userId, id, format, metadataHeaders=None):
            if id == "message-id-1":
                return MagicMock(execute=MagicMock(return_value=msg1))
            elif id == "message-id-2":
                return MagicMock(execute=MagicMock(return_value=msg2))
            elif id == "message-id-3":
                return MagicMock(execute=MagicMock(return_value=msg3))
            else:
                raise ValueError(f"Unexpected ID: {id}")
                
        mock_gmail_service.users().messages().get = MagicMock(side_effect=get_side_effect)
        
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
            assert results[0]["message_id"] == "message-id-1"
            assert results[1]["message_id"] == "message-id-2"
            assert results[2]["message_id"] == "message-id-3"
            
            # Verify API call
            mock_gmail_service.users().messages().list.assert_called_once()
            # Verify we get the subject extracted from the headers
            assert results[0]["subject"] == "Test Subject 1"
            assert results[1]["subject"] == "Test Subject 2"
            assert results[2]["subject"] == "Test Subject 3"
            
            # Verify that message.get was called for each message
            assert mock_gmail_service.users().messages().get.call_count == 3
    
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
    
    def test_search_emails_with_date_range(self, mock_gmail_service):
        """Test searching for emails with a specific date range."""
        # Setup mock message list response
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "messages": [
                {"id": "message-id-1", "threadId": "thread-id-1"},
                {"id": "message-id-2", "threadId": "thread-id-2"}
            ],
            "resultSizeEstimate": 2
        }
        
        # Set up service method chain for the search
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)
        
        # Setup mock message data
        msg1 = {
            "id": "message-id-1", 
            "threadId": "thread-id-1", 
            "snippet": "Message 1",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject 1"},
                    {"name": "From", "value": "sender1@example.com"},
                    {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"}
                ]
            }
        }
        
        msg2 = {
            "id": "message-id-2", 
            "threadId": "thread-id-2", 
            "snippet": "Message 2",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject 2"},
                    {"name": "From", "value": "sender2@example.com"},
                    {"name": "Date", "value": "Tue, 02 Apr 2025 15:30:00 +0000"}
                ]
            }
        }
        
        # Setup message.get mocks
        mock_get1 = MagicMock()
        mock_get1.execute.return_value = msg1
        
        mock_get2 = MagicMock()
        mock_get2.execute.return_value = msg2
        
        def get_side_effect(userId, id, format, metadataHeaders=None):
            if id == "message-id-1":
                return mock_get1
            elif id == "message-id-2":
                return mock_get2
            else:
                raise ValueError(f"Unexpected ID: {id}")
                
        mock_get = MagicMock()
        mock_get.side_effect = get_side_effect
        mock_gmail_service.users().messages().get = mock_get
        
        # Call the function with date range parameters
        results = search_emails(
            mock_gmail_service, 
            "from:example.com", 
            max_results=10, 
            days_back=7,  # Should be ignored when start_date is provided
            start_date="2025/04/01", 
            end_date="2025/04/03"
        )
        
        # Verify the results
        assert len(results) == 2
        assert results[0]["message_id"] == "message-id-1"
        assert results[1]["message_id"] == "message-id-2"
        
        # Verify Gmail API was called with correct query parameters
        mock_gmail_service.users().messages().list.assert_called_once()
        call_args = mock_gmail_service.users().messages().list.call_args[1]
        assert "q" in call_args
        assert "after:2025/04/01 before:2025/04/03" in call_args["q"]
    
    def test_validate_date_format(self):
        """Test the date format validation function."""
        # Test with valid date format
        assert validate_date_format("2025/04/01") is True
        
        # Test with invalid formats
        assert validate_date_format("2025-04-01") is False  # Wrong separator
        assert validate_date_format("01/04/2025") is False  # Wrong order
        assert validate_date_format("2025/4/1") is False    # Missing leading zeros
        assert validate_date_format("not-a-date") is False  # Not a date at all


class TestEmailContent:
    """Test cases for the email content retrieval functionality."""
    
    def test_download_attachment(self, mock_gmail_service):
        """Test downloading an attachment from an email."""
        # Prepare mock attachment response
        mock_attachment_data = "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IGF0dGFjaG1lbnQ="  # base64 encoded "Hello, this is a test attachment"
        mock_attachment_response = {
            "data": mock_attachment_data,
            "size": 30
        }
        
        # Setup mock for attachment get method
        mock_get = MagicMock()
        mock_get.execute.return_value = mock_attachment_response
        mock_gmail_service.users().messages().attachments().get.return_value = mock_get
        
        # Call the function
        result = download_attachment(mock_gmail_service, "message-id", "attachment-id")
        
        # Verify the function made the correct API call
        mock_gmail_service.users().messages().attachments().get.assert_called_once_with(
            userId='me',
            messageId='message-id',
            id='attachment-id'
        )
        
        # Verify the result is correct - decoded attachment data
        expected_data = base64.urlsafe_b64decode(mock_attachment_data)
        assert result == expected_data
        
    def test_download_attachment_no_data(self, mock_gmail_service):
        """Test downloading an attachment that doesn't have data field."""
        # Prepare mock attachment response without data
        mock_attachment_response = {
            "size": 30
            # No data field
        }
        
        # Setup mock for attachment get method
        mock_get = MagicMock()
        mock_get.execute.return_value = mock_attachment_response
        mock_gmail_service.users().messages().attachments().get.return_value = mock_get
        
        # Call the function
        result = download_attachment(mock_gmail_service, "message-id", "attachment-id")
        
        # Verify empty bytes returned
        assert result == b''
