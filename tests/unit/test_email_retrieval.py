"""
Unit tests for the email_retrieval module.

Verifies that the canonical imports work and that functions
behave identically whether imported from email_retrieval or email_search.
"""

import pytest
from unittest.mock import MagicMock
import base64

from iobox.email_retrieval import (
    get_email_content,
    download_attachment,
    _find_attachments,
    _extract_content_from_payload,
    _extract_content_from_parts,
)
from tests.fixtures.mock_responses import MOCK_PLAIN_TEXT_MESSAGE, MOCK_ATTACHMENT_MESSAGE


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

        assert es_get is get_email_content
        assert es_dl is download_attachment
