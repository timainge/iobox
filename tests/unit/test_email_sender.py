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
    create_draft,
    list_drafts,
    send_draft,
    delete_draft,
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


class TestComposeHtmlMessage:
    """Test cases for HTML email composition."""

    def test_compose_html_message(self):
        result = compose_message(
            to="bob@example.com",
            subject="Hello HTML",
            body="<b>Hi there</b>",
            content_type='html',
        )

        assert "raw" in result
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg["to"] == "bob@example.com"
        assert msg["subject"] == "Hello HTML"
        assert msg.get_content_type() == "text/html"

    def test_compose_plain_is_default(self):
        result = compose_message(to="bob@example.com", subject="Test", body="plain body")
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg.get_content_type() == "text/plain"


class TestComposeWithAttachment:
    """Test cases for email composition with attachments."""

    def test_compose_with_attachment(self, tmp_path):
        attach_file = tmp_path / "test.txt"
        attach_file.write_text("attachment content")

        result = compose_message(
            to="bob@example.com",
            subject="With Attachment",
            body="See attached",
            attachments=[str(attach_file)],
        )

        assert "raw" in result
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg.get_content_type() == "multipart/mixed"
        payloads = msg.get_payload()
        assert len(payloads) == 2
        # First part is text body
        assert payloads[0].get_content_type() == "text/plain"
        # Second part is the attachment
        assert payloads[1].get_filename() == "test.txt"

    def test_compose_html_with_attachment(self, tmp_path):
        attach_file = tmp_path / "report.pdf"
        attach_file.write_bytes(b"%PDF-fake-content")

        result = compose_message(
            to="bob@example.com",
            subject="HTML with Attachment",
            body="<p>See attached</p>",
            content_type='html',
            attachments=[str(attach_file)],
        )

        assert "raw" in result
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        # Outer message is mixed
        assert msg.get_content_type() == "multipart/mixed"
        payloads = msg.get_payload()
        assert len(payloads) == 2
        # First part is multipart/alternative
        assert payloads[0].get_content_type() == "multipart/alternative"
        # Second part is the attachment
        assert payloads[1].get_filename() == "report.pdf"


class TestDraftFunctions:
    """Test cases for draft management functions."""

    def test_create_draft(self):
        mock_service = MagicMock()
        expected = {"id": "draft-1", "message": {"id": "msg-1"}}
        mock_service.users().drafts().create.return_value.execute.return_value = expected

        message = {"raw": "dGVzdA=="}
        result = create_draft(mock_service, message)

        mock_service.users().drafts().create.assert_called_once_with(
            userId='me', body={'message': message}
        )
        assert result["id"] == "draft-1"

    def test_list_drafts(self):
        mock_service = MagicMock()

        # list returns draft stubs
        mock_service.users().drafts().list.return_value.execute.return_value = {
            'drafts': [{'id': 'draft-1'}, {'id': 'draft-2'}]
        }

        # get returns draft detail for each
        def mock_get_execute():
            return MagicMock(execute=MagicMock(side_effect=[
                {
                    'message': {
                        'snippet': 'First draft snippet',
                        'payload': {
                            'headers': [{'name': 'Subject', 'value': 'First Draft'}]
                        }
                    }
                },
                {
                    'message': {
                        'snippet': 'Second draft snippet',
                        'payload': {
                            'headers': [{'name': 'Subject', 'value': 'Second Draft'}]
                        }
                    }
                },
            ]))

        draft_get_results = [
            {
                'message': {
                    'snippet': 'First draft snippet',
                    'payload': {'headers': [{'name': 'Subject', 'value': 'First Draft'}]}
                }
            },
            {
                'message': {
                    'snippet': 'Second draft snippet',
                    'payload': {'headers': [{'name': 'Subject', 'value': 'Second Draft'}]}
                }
            },
        ]
        mock_service.users().drafts().get.return_value.execute.side_effect = draft_get_results

        result = list_drafts(mock_service, max_results=10)

        assert len(result) == 2
        assert result[0]['id'] == 'draft-1'
        assert result[0]['subject'] == 'First Draft'
        assert result[0]['snippet'] == 'First draft snippet'
        assert result[1]['id'] == 'draft-2'
        assert result[1]['subject'] == 'Second Draft'

    def test_send_draft(self):
        mock_service = MagicMock()
        expected = {"id": "sent-msg-1", "labelIds": ["SENT"]}
        mock_service.users().drafts().send.return_value.execute.return_value = expected

        result = send_draft(mock_service, "draft-1")

        mock_service.users().drafts().send.assert_called_once_with(
            userId='me', body={'id': 'draft-1'}
        )
        assert result["id"] == "sent-msg-1"

    def test_delete_draft(self):
        mock_service = MagicMock()
        mock_service.users().drafts().delete.return_value.execute.return_value = None

        result = delete_draft(mock_service, "draft-1")

        mock_service.users().drafts().delete.assert_called_once_with(
            userId='me', id='draft-1'
        )
        assert result == {'status': 'deleted', 'draft_id': 'draft-1'}
