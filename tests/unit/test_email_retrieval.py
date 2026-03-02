"""
Unit tests for the email_retrieval module.

Verifies that the canonical imports work and that functions
behave identically whether imported from email_retrieval or email_search.
"""

import pytest
from unittest.mock import MagicMock
import base64

import iobox.email_retrieval as er
from iobox.email_retrieval import (
    get_email_content,
    get_label_map,
    download_attachment,
    _find_attachments,
    _extract_content_from_payload,
    _extract_content_from_parts,
)
from tests.fixtures.mock_responses import MOCK_PLAIN_TEXT_MESSAGE, MOCK_ATTACHMENT_MESSAGE

# Mock labels.list response used across label-related tests
MOCK_LABELS_RESPONSE = {
    "labels": [
        {"id": "INBOX", "name": "INBOX"},
        {"id": "UNREAD", "name": "UNREAD"},
        {"id": "IMPORTANT", "name": "IMPORTANT"},
        {"id": "CATEGORY_PERSONAL", "name": "CATEGORY_PERSONAL"},
        {"id": "Label_12345", "name": "Newsletter"},
        {"id": "Label_67890", "name": "Work"},
    ]
}


class TestEmailRetrieval:
    """Test canonical import paths for email retrieval functions."""

    def test_get_email_content_plain(self, mock_gmail_service):
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_PLAIN_TEXT_MESSAGE
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)

        email_data = get_email_content(service=mock_gmail_service, message_id="message-id-1")

        assert email_data["message_id"] == "message-id-1"
        assert email_data["subject"] == "Test Email Subject"
        assert email_data["content_type"] == "text/plain"

    def test_get_email_content_with_attachments(self, mock_gmail_service):
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_ATTACHMENT_MESSAGE
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)

        email_data = get_email_content(service=mock_gmail_service, message_id="message-id-3")

        assert len(email_data["attachments"]) == 1
        assert email_data["attachments"][0]["filename"] == "document.pdf"

    def test_download_attachment(self, mock_gmail_service):
        mock_data = "SGVsbG8gV29ybGQ="
        mock_get = MagicMock()
        mock_get.execute.return_value = {"data": mock_data, "size": 11}
        mock_gmail_service.users().messages().attachments().get.return_value = mock_get

        result = download_attachment(mock_gmail_service, "msg-1", "att-1")

        assert result == base64.urlsafe_b64decode(mock_data)

    def test_backward_compat_import_from_email_search(self):
        """Ensure importing from email_search still works."""
        from iobox.email_search import get_email_content as es_get
        from iobox.email_search import download_attachment as es_dl
        from iobox.email_search import get_label_map as es_glm

        assert es_get is get_email_content
        assert es_dl is download_attachment
        assert es_glm is get_label_map


class TestGetLabelMap:
    """Tests for the get_label_map() function."""

    def test_get_label_map(self, mock_gmail_service, mocker):
        """Mock labels.list and verify returned dict maps IDs to names."""
        mocker.patch.dict(er._label_cache, {}, clear=True)

        mock_result = MagicMock()
        mock_result.execute.return_value = MOCK_LABELS_RESPONSE
        mock_gmail_service.users().labels().list.return_value = mock_result

        label_map = get_label_map(mock_gmail_service)

        assert label_map["INBOX"] == "INBOX"
        assert label_map["Label_12345"] == "Newsletter"
        assert label_map["Label_67890"] == "Work"
        assert label_map["CATEGORY_PERSONAL"] == "CATEGORY_PERSONAL"
        mock_gmail_service.users().labels().list.assert_called_once_with(userId='me')

    def test_get_label_map_error_fallback(self, mock_gmail_service, mocker):
        """If labels.list raises, get_label_map returns an empty dict."""
        mocker.patch.dict(er._label_cache, {}, clear=True)

        mock_gmail_service.users().labels().list.side_effect = Exception("API error")

        label_map = get_label_map(mock_gmail_service)

        assert label_map == {}

    def test_get_label_map_uses_cache(self, mock_gmail_service, mocker):
        """Subsequent calls within a session re-use the cached map."""
        mocker.patch.dict(er._label_cache, {}, clear=True)

        mock_result = MagicMock()
        mock_result.execute.return_value = MOCK_LABELS_RESPONSE
        mock_gmail_service.users().labels().list.return_value = mock_result

        get_label_map(mock_gmail_service)
        get_label_map(mock_gmail_service)

        # API should only be called once despite two get_label_map calls
        mock_gmail_service.users().labels().list.assert_called_once()


class TestLabelResolution:
    """Tests for label ID resolution in get_email_content()."""

    def test_label_resolution_in_get_email_content(self, mock_gmail_service):
        """Labels in returned data are resolved when label_map is provided."""
        # Build a message with a custom label ID
        message_with_custom_label = {
            "id": "message-id-1",
            "threadId": "thread-id-1",
            "labelIds": ["INBOX", "Label_12345"],
            "snippet": "Test snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"}
                ],
                "body": {
                    "data": "SGVsbG8gd29ybGQ=",
                    "size": 11
                }
            }
        }

        mock_get = MagicMock()
        mock_get.execute.return_value = message_with_custom_label
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)

        label_map = {"INBOX": "INBOX", "Label_12345": "Newsletter"}
        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-1",
            label_map=label_map
        )

        assert "INBOX" in email_data["labels"]
        assert "Newsletter" in email_data["labels"]
        assert "Label_12345" not in email_data["labels"]

    def test_label_resolution_without_map(self, mock_gmail_service):
        """Raw label IDs are returned when label_map is not provided (backward compatible)."""
        message_with_custom_label = {
            "id": "message-id-1",
            "threadId": "thread-id-1",
            "labelIds": ["INBOX", "Label_12345"],
            "snippet": "Test snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "Date", "value": "Mon, 01 Apr 2025 10:00:00 +0000"}
                ],
                "body": {
                    "data": "SGVsbG8gd29ybGQ=",
                    "size": 11
                }
            }
        }

        mock_get = MagicMock()
        mock_get.execute.return_value = message_with_custom_label
        mock_gmail_service.users().messages().get = MagicMock(return_value=mock_get)

        email_data = get_email_content(
            service=mock_gmail_service,
            message_id="message-id-1"
            # no label_map
        )

        assert "INBOX" in email_data["labels"]
        assert "Label_12345" in email_data["labels"]
        assert "Newsletter" not in email_data["labels"]
