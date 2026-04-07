"""
Unit tests for the email search module.

This module tests the core functionality of the email_search.py module which is responsible
for searching and retrieving emails from Gmail API.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.google._retrieval import (
    download_attachment,
    get_email_content,
)
from iobox.providers.google._search import (
    batch_get_metadata,
    get_new_messages,
    search_emails,
    validate_date_format,
)
from tests.fixtures.mock_responses import (
    MOCK_ATTACHMENT_MESSAGE,
    MOCK_HTML_MESSAGE,
    MOCK_PLAIN_TEXT_MESSAGE,
    MOCK_PLAIN_TEXT_ONLY_MESSAGE,
)


def _setup_batch_mock(mock_service, responses):
    """
    Configure mock_service.new_batch_http_request so that batch.execute()
    triggers the registered callback with the given responses dict.

    responses: {message_id: response_dict}
    """
    mock_batch = MagicMock()
    ids_added = []

    def track_add(request, request_id=None):
        ids_added.append(request_id)

    mock_batch.add.side_effect = track_add

    def fake_execute():
        callback = mock_service.new_batch_http_request.call_args[1]["callback"]
        for mid in ids_added:
            if mid in responses:
                callback(mid, responses[mid], None)
            else:
                callback(mid, None, Exception(f"Not found: {mid}"))

    mock_batch.execute.side_effect = fake_execute
    mock_service.new_batch_http_request.return_value = mock_batch
    return mock_batch


class TestEmailSearch:
    """Test cases for the email search module."""

    def test_search_emails_basic(self, mock_gmail_service):
        """Test basic email search functionality."""
        # Setup mock message list response
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "messages": [
                {"id": "message-id-1", "threadId": "thread-id-1"},
                {"id": "message-id-2", "threadId": "thread-id-2"},
                {"id": "message-id-3", "threadId": "thread-id-3"},
            ],
            "resultSizeEstimate": 3,
        }
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)

        # Set up batch mock responses for metadata
        responses = {
            "message-id-1": {
                "id": "message-id-1",
                "threadId": "thread-id-1",
                "snippet": "Message 1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Subject 1"},
                        {"name": "From", "value": "sender1@example.com"},
                        {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"},
                    ]
                },
            },
            "message-id-2": {
                "id": "message-id-2",
                "threadId": "thread-id-2",
                "snippet": "Message 2",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Subject 2"},
                        {"name": "From", "value": "sender2@example.com"},
                        {"name": "Date", "value": "Tue, 02 Apr 2025 15:30:00 +0000"},
                    ]
                },
            },
            "message-id-3": {
                "id": "message-id-3",
                "threadId": "thread-id-3",
                "snippet": "Message 3",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Subject 3"},
                        {"name": "From", "value": "sender3@example.com"},
                        {"name": "Date", "value": "Wed, 03 Apr 2025 09:15:00 +0000"},
                    ]
                },
            },
        }
        _setup_batch_mock(mock_gmail_service, responses)

        # Patch datetime to return a fixed date for testing
        with patch("iobox.providers.google._search.datetime") as mock_datetime:
            mock_date = MagicMock()
            mock_date.now.return_value = mock_date
            mock_date.__sub__.return_value = mock_date
            mock_date.strftime.return_value = "2025/03/23"
            mock_datetime.now.return_value = mock_date
            mock_datetime.timedelta = MagicMock(return_value=mock_date)

            results = search_emails(
                service=mock_gmail_service, query="from:example.com", max_results=10
            )

        assert len(results) == 3
        assert results[0]["message_id"] == "message-id-1"
        assert results[1]["message_id"] == "message-id-2"
        assert results[2]["message_id"] == "message-id-3"

        mock_gmail_service.users().messages().list.assert_called_once()
        assert results[0]["subject"] == "Test Subject 1"
        assert results[1]["subject"] == "Test Subject 2"
        assert results[2]["subject"] == "Test Subject 3"

        # Verify batch was used (not individual gets)
        mock_gmail_service.new_batch_http_request.assert_called_once()

    def test_search_emails_empty_results(self, mock_gmail_service):
        """Test email search with no results."""
        # Setup mock empty response
        mock_list = MagicMock()
        mock_list.execute.return_value = {"resultSizeEstimate": 0}

        # Set up service method chain
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)

        # Call the search function
        results = search_emails(
            service=mock_gmail_service, query="from:nonexistent@example.com", max_results=10
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
        email_data = get_email_content(service=mock_gmail_service, message_id="message-id-1")

        # Verify correct parameters were used
        mock_gmail_service.users().messages().get.assert_called_with(
            userId="me", id="message-id-1", format="full"
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
            preferred_content_type="text/html",
        )

        # Verify correct parameters were used
        mock_gmail_service.users().messages().get.assert_called_with(
            userId="me", id="message-id-2", format="full"
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
            preferred_content_type="text/html",  # Request HTML but will fall back to plain text
        )

        # Verification of API call
        mock_gmail_service.users().messages().get.assert_called_once_with(
            userId="me", id="message-id-2", format="full"
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
        email_data = get_email_content(service=mock_gmail_service, message_id="message-id-3")

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
                {"id": "message-id-2", "threadId": "thread-id-2"},
            ],
            "resultSizeEstimate": 2,
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
                    {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"},
                ]
            },
        }

        msg2 = {
            "id": "message-id-2",
            "threadId": "thread-id-2",
            "snippet": "Message 2",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject 2"},
                    {"name": "From", "value": "sender2@example.com"},
                    {"name": "Date", "value": "Tue, 02 Apr 2025 15:30:00 +0000"},
                ]
            },
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
            end_date="2025/04/03",
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
        assert validate_date_format("2025/4/1") is False  # Missing leading zeros
        assert validate_date_format("not-a-date") is False  # Not a date at all

    # ------------------------------------------------------------------
    # Pagination tests
    # ------------------------------------------------------------------

    def _make_msg_get_side_effect(self, msg_ids):
        """Return a side_effect callable that yields metadata mocks by ID."""

        def side_effect(userId, id, format, metadataHeaders=None):
            return MagicMock(
                execute=MagicMock(
                    return_value={
                        "id": id,
                        "threadId": f"thread-{id}",
                        "snippet": f"Snippet for {id}",
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": f"Subject {id}"},
                                {"name": "From", "value": "sender@example.com"},
                                {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"},
                            ]
                        },
                    }
                )
            )

        return side_effect

    def test_search_pagination_two_pages(self, mock_gmail_service):
        """Both pages are fetched and their messages combined when nextPageToken present."""
        page1_response = {
            "messages": [
                {"id": "msg-1", "threadId": "thread-1"},
                {"id": "msg-2", "threadId": "thread-2"},
            ],
            "nextPageToken": "token-page-2",
            "resultSizeEstimate": 4,
        }
        page2_response = {
            "messages": [
                {"id": "msg-3", "threadId": "thread-3"},
                {"id": "msg-4", "threadId": "thread-4"},
            ],
            "resultSizeEstimate": 4,
        }

        mock_list1 = MagicMock()
        mock_list1.execute.return_value = page1_response
        mock_list2 = MagicMock()
        mock_list2.execute.return_value = page2_response

        list_mock = MagicMock(side_effect=[mock_list1, mock_list2])
        mock_gmail_service.users().messages().list = list_mock
        mock_gmail_service.users().messages().get = MagicMock(
            side_effect=self._make_msg_get_side_effect(["msg-1", "msg-2", "msg-3", "msg-4"])
        )

        results = search_emails(
            service=mock_gmail_service, query="from:example.com", max_results=10
        )

        assert len(results) == 4
        assert results[0]["message_id"] == "msg-1"
        assert results[3]["message_id"] == "msg-4"
        assert list_mock.call_count == 2

    def test_search_pagination_truncation(self, mock_gmail_service):
        """Total results are truncated to exactly max_results even if pages return more."""
        page1_response = {
            "messages": [
                {"id": "msg-1", "threadId": "thread-1"},
                {"id": "msg-2", "threadId": "thread-2"},
            ],
            "nextPageToken": "token-page-2",
            "resultSizeEstimate": 4,
        }
        page2_response = {
            "messages": [
                {"id": "msg-3", "threadId": "thread-3"},
                {"id": "msg-4", "threadId": "thread-4"},
            ],
            "resultSizeEstimate": 4,
        }

        mock_list1 = MagicMock()
        mock_list1.execute.return_value = page1_response
        mock_list2 = MagicMock()
        mock_list2.execute.return_value = page2_response

        list_mock = MagicMock(side_effect=[mock_list1, mock_list2])
        mock_gmail_service.users().messages().list = list_mock
        mock_gmail_service.users().messages().get = MagicMock(
            side_effect=self._make_msg_get_side_effect(["msg-1", "msg-2", "msg-3"])
        )

        results = search_emails(
            service=mock_gmail_service,
            query="from:example.com",
            max_results=3,  # Should truncate to exactly 3
        )

        assert len(results) == 3
        assert results[0]["message_id"] == "msg-1"
        assert results[2]["message_id"] == "msg-3"

    def test_search_pagination_single_page(self, mock_gmail_service):
        """Single-page behavior is unchanged when no nextPageToken is present."""
        single_page_response = {
            "messages": [
                {"id": "msg-1", "threadId": "thread-1"},
                {"id": "msg-2", "threadId": "thread-2"},
            ],
            "resultSizeEstimate": 2,
            # No nextPageToken
        }

        mock_list = MagicMock()
        mock_list.execute.return_value = single_page_response
        mock_gmail_service.users().messages().list = MagicMock(return_value=mock_list)
        mock_gmail_service.users().messages().get = MagicMock(
            side_effect=self._make_msg_get_side_effect(["msg-1", "msg-2"])
        )

        results = search_emails(
            service=mock_gmail_service, query="from:example.com", max_results=10
        )

        assert len(results) == 2
        assert results[0]["message_id"] == "msg-1"
        assert results[1]["message_id"] == "msg-2"
        mock_gmail_service.users().messages().list.assert_called_once()


class TestEmailContent:
    """Test cases for the email content retrieval functionality."""

    def test_download_attachment(self, mock_gmail_service):
        """Test downloading an attachment from an email."""
        # Prepare mock attachment response
        # base64 encoded "Hello, this is a test attachment"
        mock_attachment_data = "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IGF0dGFjaG1lbnQ="
        mock_attachment_response = {"data": mock_attachment_data, "size": 30}

        # Setup mock for attachment get method
        mock_get = MagicMock()
        mock_get.execute.return_value = mock_attachment_response
        mock_gmail_service.users().messages().attachments().get.return_value = mock_get

        # Call the function
        result = download_attachment(mock_gmail_service, "message-id", "attachment-id")

        # Verify the function made the correct API call
        mock_gmail_service.users().messages().attachments().get.assert_called_once_with(
            userId="me", messageId="message-id", id="attachment-id"
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
        assert result == b""


class TestSearchIncludeSpamTrash:
    """Tests for the include_spam_trash parameter in search_emails()."""

    def test_search_include_spam_trash_passed_to_api(self, mock_gmail_service):
        """includeSpamTrash=True is forwarded to the messages.list API call."""
        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": [], "resultSizeEstimate": 0}
        mock_gmail_service.users().messages().list.return_value = mock_list

        search_emails(
            service=mock_gmail_service,
            query="in:spam",
            max_results=5,
            include_spam_trash=True,
        )

        call_kwargs = mock_gmail_service.users().messages().list.call_args[1]
        assert call_kwargs.get("includeSpamTrash") is True

    def test_search_exclude_spam_trash_by_default(self, mock_gmail_service):
        """includeSpamTrash defaults to False when not specified."""
        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": [], "resultSizeEstimate": 0}
        mock_gmail_service.users().messages().list.return_value = mock_list

        search_emails(
            service=mock_gmail_service,
            query="subject:test",
            max_results=5,
        )

        call_kwargs = mock_gmail_service.users().messages().list.call_args[1]
        assert call_kwargs.get("includeSpamTrash") is False


class TestBatchGetMetadata:
    """Tests for batch_get_metadata()."""

    def _make_metadata_response(self, msg_id, subject="Sub", sender="a@b.com"):
        return {
            "id": msg_id,
            "threadId": f"thread-{msg_id}",
            "labelIds": ["INBOX"],
            "snippet": f"snippet-{msg_id}",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": sender},
                    {"name": "Date", "value": "Mon, 01 Jan 2024 00:00:00 +0000"},
                ]
            },
        }

    def test_batch_get_metadata_success(self, mock_gmail_service):
        """All metadata is fetched and returned in input order."""
        msg_ids = ["m1", "m2", "m3"]
        responses = {mid: self._make_metadata_response(mid) for mid in msg_ids}

        mock_batch = MagicMock()
        mock_gmail_service.new_batch_http_request.return_value = mock_batch

        def fake_execute():
            callback = mock_gmail_service.new_batch_http_request.call_args[1]["callback"]
            for req_id, resp in responses.items():
                callback(req_id, resp, None)

        mock_batch.execute.side_effect = fake_execute

        result = batch_get_metadata(mock_gmail_service, msg_ids)

        assert len(result) == 3
        assert result[0]["message_id"] == "m1"
        assert result[1]["message_id"] == "m2"
        assert result[2]["message_id"] == "m3"
        assert result[0]["subject"] == "Sub"
        assert "error" not in result[0]

    def test_batch_get_metadata_with_label_map(self, mock_gmail_service):
        """Label IDs are resolved when label_map is provided."""
        msg_ids = ["m1"]
        responses = {"m1": self._make_metadata_response("m1")}
        responses["m1"]["labelIds"] = ["INBOX", "Label_12345"]

        mock_batch = MagicMock()
        mock_gmail_service.new_batch_http_request.return_value = mock_batch

        def fake_execute():
            callback = mock_gmail_service.new_batch_http_request.call_args[1]["callback"]
            callback("m1", responses["m1"], None)

        mock_batch.execute.side_effect = fake_execute

        label_map = {"INBOX": "INBOX", "Label_12345": "Newsletter"}
        result = batch_get_metadata(mock_gmail_service, msg_ids, label_map=label_map)

        assert "Newsletter" in result[0]["labels"]
        assert "Label_12345" not in result[0]["labels"]

    def test_batch_get_metadata_partial_failure(self, mock_gmail_service):
        """Failed fetches return dict with 'error' key."""
        msg_ids = ["m1", "m2"]
        responses = {"m1": self._make_metadata_response("m1")}

        mock_batch = MagicMock()
        mock_gmail_service.new_batch_http_request.return_value = mock_batch

        def fake_execute():
            callback = mock_gmail_service.new_batch_http_request.call_args[1]["callback"]
            callback("m1", responses["m1"], None)
            callback("m2", None, Exception("fetch failed"))

        mock_batch.execute.side_effect = fake_execute

        result = batch_get_metadata(mock_gmail_service, msg_ids)

        assert len(result) == 2
        assert "error" not in result[0]
        assert result[1]["message_id"] == "m2"
        assert "error" in result[1]


class TestGetNewMessages:
    """Tests for get_new_messages()."""

    def test_get_new_messages_returns_ids(self, mock_gmail_service):
        """Returns list of message IDs from messagesAdded records."""
        history_response = {
            "history": [
                {"messagesAdded": [{"message": {"id": "msg-new-1"}}]},
                {"messagesAdded": [{"message": {"id": "msg-new-2"}}]},
            ]
        }

        mock_hist = MagicMock()
        mock_hist.execute.return_value = history_response
        mock_gmail_service.users().history().list.return_value = mock_hist

        result = get_new_messages(mock_gmail_service, "history-123")

        assert result == ["msg-new-1", "msg-new-2"]

    def test_get_new_messages_paginated(self, mock_gmail_service):
        """Follows nextPageToken to collect all new message IDs."""
        page1 = {
            "history": [{"messagesAdded": [{"message": {"id": "msg-1"}}]}],
            "nextPageToken": "token-p2",
        }
        page2 = {
            "history": [{"messagesAdded": [{"message": {"id": "msg-2"}}]}],
        }

        mock_h1 = MagicMock()
        mock_h1.execute.return_value = page1
        mock_h2 = MagicMock()
        mock_h2.execute.return_value = page2

        mock_gmail_service.users().history().list.side_effect = [mock_h1, mock_h2]

        result = get_new_messages(mock_gmail_service, "hist-abc")

        assert result == ["msg-1", "msg-2"]

    def test_get_new_messages_empty(self, mock_gmail_service):
        """Returns empty list when no new messages since historyId."""
        mock_hist = MagicMock()
        mock_hist.execute.return_value = {"history": []}
        mock_gmail_service.users().history().list.return_value = mock_hist

        result = get_new_messages(mock_gmail_service, "hist-old")

        assert result == []

    def test_get_new_messages_expired_returns_none(self, mock_gmail_service):
        """Returns None when history is expired (404 error)."""
        mock_gmail_service.users().history().list.side_effect = Exception(
            "404 historyId not found: notFound"
        )

        result = get_new_messages(mock_gmail_service, "hist-expired")

        assert result is None

    def test_get_new_messages_reraises_non_404(self, mock_gmail_service):
        """Non-404 exceptions are re-raised."""
        mock_gmail_service.users().history().list.side_effect = Exception("500 internal error")

        with pytest.raises(Exception, match="500 internal error"):
            get_new_messages(mock_gmail_service, "hist-123")
