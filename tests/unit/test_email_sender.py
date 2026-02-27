"""
Unit tests for the email_sender module.
"""

import base64
import pytest
from email import message_from_bytes
from unittest.mock import patch, MagicMock

from iobox.email_sender import (
    compose_message,
    compose_forward_message,
    send_message,
    forward_email,
)


class TestComposeMessage:
    """Test cases for compose_message."""

    def test_basic_compose(self):
        result = compose_message(to="bob@example.com", subject="Hello", body="Hi there")

        assert "raw" in result
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg["to"] == "bob@example.com"
        assert msg["subject"] == "Hello"
        assert msg.get_payload() == "Hi there"

    def test_compose_with_cc_bcc(self):
        result = compose_message(
            to="bob@example.com",
            subject="Test",
            body="Body",
            cc="cc@example.com",
            bcc="bcc@example.com",
        )

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg["cc"] == "cc@example.com"
        assert msg["bcc"] == "bcc@example.com"

    def test_compose_with_from(self):
        result = compose_message(
            to="bob@example.com",
            subject="Test",
            body="Body",
            from_addr="alice@example.com",
        )

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg["from"] == "alice@example.com"

    def test_compose_without_optional_fields(self):
        result = compose_message(to="bob@example.com", subject="Test", body="Body")

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg["from"] is None
        assert msg["cc"] is None
        assert msg["bcc"] is None


class TestComposeForwardMessage:
    """Test cases for compose_forward_message."""

    def test_basic_forward(self):
        original = {
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "subject": "Original Subject",
            "body": "Original body text",
        }

        result = compose_forward_message(original, to="recipient@example.com")

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg["to"] == "recipient@example.com"
        assert msg["subject"] == "Fwd: Original Subject"
        body = msg.get_payload()
        assert "---------- Forwarded message ----------" in body
        assert "From: sender@example.com" in body
        assert "Original body text" in body

    def test_forward_with_note(self):
        original = {
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Test",
            "body": "Body",
        }

        result = compose_forward_message(
            original, to="bob@example.com", additional_text="FYI see below"
        )

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        body = msg.get_payload()

        assert body.startswith("FYI see below")

    def test_forward_uses_content_fallback(self):
        original = {
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Test",
            "content": "Fallback content",
        }

        result = compose_forward_message(original, to="bob@example.com")

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        assert "Fallback content" in msg.get_payload()


class TestSendMessage:
    """Test cases for send_message."""

    def test_send_success(self):
        mock_service = MagicMock()
        mock_send = MagicMock()
        mock_send.execute.return_value = {"id": "sent-msg-1", "labelIds": ["SENT"]}
        mock_service.users().messages().send.return_value = mock_send

        message = {"raw": "dGVzdA=="}
        result = send_message(mock_service, message)

        mock_service.users().messages().send.assert_called_once_with(
            userId="me", body=message
        )
        assert result["id"] == "sent-msg-1"

    def test_send_http_error(self):
        from googleapiclient.errors import HttpError
        from unittest.mock import PropertyMock

        mock_service = MagicMock()
        resp = MagicMock()
        resp.status = 403
        mock_service.users().messages().send.return_value.execute.side_effect = (
            HttpError(resp, b"forbidden")
        )

        with pytest.raises(HttpError):
            send_message(mock_service, {"raw": "dGVzdA=="})


class TestForwardEmail:
    """Test cases for forward_email convenience function."""

    @patch("iobox.email_sender.send_message")
    @patch("iobox.email_sender.get_email_content")
    def test_forward_email(self, mock_get, mock_send):
        mock_get.return_value = {
            "message_id": "orig-1",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Original",
            "body": "Hello",
        }
        mock_send.return_value = {"id": "fwd-1"}

        mock_service = MagicMock()
        result = forward_email(mock_service, message_id="orig-1", to="bob@example.com")

        mock_get.assert_called_once_with(mock_service, message_id="orig-1")
        mock_send.assert_called_once()
        assert result["id"] == "fwd-1"

    @patch("iobox.email_sender.send_message")
    @patch("iobox.email_sender.get_email_content")
    def test_forward_with_note(self, mock_get, mock_send):
        mock_get.return_value = {
            "message_id": "orig-1",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Original",
            "body": "Hello",
        }
        mock_send.return_value = {"id": "fwd-2"}

        mock_service = MagicMock()
        forward_email(
            mock_service,
            message_id="orig-1",
            to="bob@example.com",
            additional_text="Please review",
        )

        # Verify the composed message contains the note
        call_args = mock_send.call_args
        raw = call_args[0][1]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw)
        msg = message_from_bytes(raw_bytes)
        assert "Please review" in msg.get_payload()
