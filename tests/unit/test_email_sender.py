"""
Unit tests for the email_sender module.
"""

import base64
from email import message_from_bytes
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.google._sender import (
    compose_forward_message,
    compose_message,
    create_draft,
    delete_draft,
    forward_email,
    list_drafts,
    send_draft,
    send_message,
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

        mock_service.users().messages().send.assert_called_once_with(userId="me", body=message)
        assert result["id"] == "sent-msg-1"

    def test_send_http_error(self):

        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        resp = MagicMock()
        resp.status = 403
        mock_service.users().messages().send.return_value.execute.side_effect = HttpError(
            resp, b"forbidden"
        )

        with pytest.raises(HttpError):
            send_message(mock_service, {"raw": "dGVzdA=="})


class TestForwardEmail:
    """Test cases for forward_email convenience function."""

    @patch("iobox.providers.google._sender.send_message")
    @patch("iobox.providers.google._sender.get_email_content")
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

        mock_get.assert_called_once_with(
            mock_service, message_id="orig-1", preferred_content_type="text/html"
        )
        mock_send.assert_called_once()
        assert result["id"] == "fwd-1"

    @patch("iobox.providers.google._sender.send_message")
    @patch("iobox.providers.google._sender.get_email_content")
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


class TestForwardPreservesAttachments:
    """Forwarding must carry over the original message's attachments (P0 bug)."""

    def test_compose_forward_reattaches_blobs(self):
        original = {
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Receipt",
            "body": "See attached receipt",
        }
        blobs = [{"filename": "receipt.pdf", "mime_type": "application/pdf", "data": b"%PDF-fake"}]

        result = compose_forward_message(original, to="hubdoc@example.com", attachment_blobs=blobs)

        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg.get_content_type() == "multipart/mixed"
        filenames = [p.get_filename() for p in msg.get_payload()]
        assert "receipt.pdf" in filenames

    def test_compose_forward_html_body(self):
        original = {
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "HTML Receipt",
            "body": "<p>See attached</p>",
            "content_type": "text/html",
        }
        result = compose_forward_message(original, to="bob@example.com")
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        # HTML-only forward (no attachments): plain + html alternatives.
        assert msg.get_content_type() == "multipart/alternative"
        plain, html_part = msg.get_payload()
        assert plain.get_content_type() == "text/plain"
        assert html_part.get_content_type() == "text/html"
        assert "Forwarded message" in html_part.get_payload()
        assert "Forwarded message" in plain.get_payload()

    @patch("iobox.providers.google._sender.send_message")
    @patch("iobox.providers.google._sender.download_attachment")
    @patch("iobox.providers.google._sender.get_email_content")
    def test_forward_email_downloads_and_reattaches(self, mock_get, mock_dl, mock_send):
        mock_get.return_value = {
            "message_id": "orig-1",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Receipt",
            "body": "Body",
            "attachments": [
                {"id": "att-1", "filename": "receipt.pdf", "mime_type": "application/pdf"}
            ],
        }
        mock_dl.return_value = b"%PDF-fake"
        mock_send.return_value = {"id": "fwd-1"}

        mock_service = MagicMock()
        forward_email(mock_service, message_id="orig-1", to="hubdoc@example.com")

        mock_dl.assert_called_once_with(mock_service, "orig-1", "att-1")
        raw = mock_send.call_args[0][1]["raw"]
        msg = message_from_bytes(base64.urlsafe_b64decode(raw))
        filenames = [p.get_filename() for p in msg.get_payload()]
        assert "receipt.pdf" in filenames

    @patch("iobox.providers.google._sender.send_message")
    @patch("iobox.providers.google._sender.download_attachment")
    @patch("iobox.providers.google._sender.get_email_content")
    def test_forward_email_skips_failed_attachment(self, mock_get, mock_dl, mock_send):
        mock_get.return_value = {
            "message_id": "orig-1",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025",
            "subject": "Receipt",
            "body": "Body",
            "attachments": [
                {"id": "att-1", "filename": "receipt.pdf", "mime_type": "application/pdf"}
            ],
        }
        mock_dl.side_effect = RuntimeError("download failed")
        mock_send.return_value = {"id": "fwd-1"}

        mock_service = MagicMock()
        # Must not raise — a failed attachment download is logged and skipped.
        result = forward_email(mock_service, message_id="orig-1", to="bob@example.com")
        assert result["id"] == "fwd-1"


class TestComposeHtmlMessage:
    """Test cases for HTML email composition."""

    def test_compose_html_message(self):
        result = compose_message(
            to="bob@example.com",
            subject="Hello HTML",
            body="<b>Hi there</b>",
            content_type="html",
        )

        assert "raw" in result
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)

        assert msg["to"] == "bob@example.com"
        assert msg["subject"] == "Hello HTML"
        assert msg.get_content_type() == "multipart/alternative"

    def test_compose_plain_is_default(self):
        result = compose_message(to="bob@example.com", subject="Test", body="plain body")
        raw_bytes = base64.urlsafe_b64decode(result["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg.get_content_type() == "text/plain"


_HTML_BODY = '<p>Hello <b>Bob</b>,</p><p>See <a href="https://x.example">the link</a>.</p>'


def _alternative_parts(msg) -> tuple[str, str]:
    """Return decoded (text/plain, text/html) bodies of the multipart/alternative."""
    alt = next(p for p in msg.walk() if p.get_content_type() == "multipart/alternative")
    plain, html_part = alt.get_payload()
    assert plain.get_content_type() == "text/plain"
    assert html_part.get_content_type() == "text/html"
    return (
        plain.get_payload(decode=True).decode(plain.get_content_charset() or "utf-8"),
        html_part.get_payload(decode=True).decode(html_part.get_content_charset() or "utf-8"),
    )


class TestHtmlPlainAlternative:
    """FU-05: the text/plain alternative of an HTML email is text, not raw HTML."""

    def _assert_alternatives(self, msg) -> None:
        plain, html_body = _alternative_parts(msg)
        assert "<" not in plain and ">" not in plain
        assert "Hello Bob" in plain
        assert "See the link" in plain
        assert html_body == _HTML_BODY

    def test_html_with_attachment(self, tmp_path):
        attach_file = tmp_path / "report.pdf"
        attach_file.write_bytes(b"%PDF-fake")
        result = compose_message(
            to="bob@example.com",
            subject="s",
            body=_HTML_BODY,
            content_type="html",
            attachments=[str(attach_file)],
        )
        msg = message_from_bytes(base64.urlsafe_b64decode(result["raw"]))
        assert msg.get_content_type() == "multipart/mixed"
        self._assert_alternatives(msg)

    def test_html_without_attachment(self):
        result = compose_message(
            to="bob@example.com", subject="s", body=_HTML_BODY, content_type="html"
        )
        msg = message_from_bytes(base64.urlsafe_b64decode(result["raw"]))
        assert msg.get_content_type() == "multipart/alternative"
        self._assert_alternatives(msg)

    def test_html_with_inline_related_image(self):
        blobs = [
            {
                "filename": "logo.png",
                "mime_type": "image/png",
                "data": b"\x89PNG",
                "inline": True,
                "content_id": "logo1",
            }
        ]
        result = compose_message(
            to="bob@example.com",
            subject="s",
            body=_HTML_BODY,
            content_type="html",
            attachment_blobs=blobs,
        )
        msg = message_from_bytes(base64.urlsafe_b64decode(result["raw"]))
        assert msg.get_content_type() == "multipart/alternative"
        alt_children = [p.get_content_type() for p in msg.get_payload()]
        assert alt_children == ["text/plain", "multipart/related"]
        plain = msg.get_payload()[0].get_payload(decode=True).decode()
        assert "<" not in plain
        related_html = msg.get_payload()[1].get_payload()[0]
        assert related_html.get_payload(decode=True).decode() == _HTML_BODY

    def test_plain_body_unchanged(self):
        result = compose_message(to="bob@example.com", subject="s", body="a <b> c")
        msg = message_from_bytes(base64.urlsafe_b64decode(result["raw"]))
        assert msg.get_content_type() == "text/plain"
        assert msg.get_payload(decode=True).decode() == "a <b> c"


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
            content_type="html",
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
            userId="me", body={"message": message}
        )
        assert result["id"] == "draft-1"

    def test_list_drafts(self):
        mock_service = MagicMock()

        # list returns draft stubs
        mock_service.users().drafts().list.return_value.execute.return_value = {
            "drafts": [{"id": "draft-1"}, {"id": "draft-2"}]
        }

        # get returns draft detail for each
        def mock_get_execute():
            return MagicMock(
                execute=MagicMock(
                    side_effect=[
                        {
                            "message": {
                                "snippet": "First draft snippet",
                                "payload": {
                                    "headers": [{"name": "Subject", "value": "First Draft"}]
                                },
                            }
                        },
                        {
                            "message": {
                                "snippet": "Second draft snippet",
                                "payload": {
                                    "headers": [{"name": "Subject", "value": "Second Draft"}]
                                },
                            }
                        },
                    ]
                )
            )

        draft_get_results = [
            {
                "message": {
                    "snippet": "First draft snippet",
                    "payload": {"headers": [{"name": "Subject", "value": "First Draft"}]},
                }
            },
            {
                "message": {
                    "snippet": "Second draft snippet",
                    "payload": {"headers": [{"name": "Subject", "value": "Second Draft"}]},
                }
            },
        ]
        mock_service.users().drafts().get.return_value.execute.side_effect = draft_get_results

        result = list_drafts(mock_service, max_results=10)

        assert len(result) == 2
        assert result[0]["id"] == "draft-1"
        assert result[0]["subject"] == "First Draft"
        assert result[0]["snippet"] == "First draft snippet"
        assert result[1]["id"] == "draft-2"
        assert result[1]["subject"] == "Second Draft"

    def test_send_draft(self):
        mock_service = MagicMock()
        expected = {"id": "sent-msg-1", "labelIds": ["SENT"]}
        mock_service.users().drafts().send.return_value.execute.return_value = expected

        result = send_draft(mock_service, "draft-1")

        mock_service.users().drafts().send.assert_called_once_with(
            userId="me", body={"id": "draft-1"}
        )
        assert result["id"] == "sent-msg-1"

    def test_delete_draft(self):
        mock_service = MagicMock()
        mock_service.users().drafts().delete.return_value.execute.return_value = None

        result = delete_draft(mock_service, "draft-1")

        mock_service.users().drafts().delete.assert_called_once_with(userId="me", id="draft-1")
        assert result == {"status": "deleted", "draft_id": "draft-1"}


def _parse(result: dict) -> object:
    from email import policy

    return message_from_bytes(base64.urlsafe_b64decode(result["raw"]), policy=policy.default)


class TestNonAsciiEncoding:
    """DATA-10: non-ASCII filenames, display names and subjects round-trip."""

    def test_non_ascii_attachment_filename(self):
        result = compose_message(
            to="bob@example.com",
            subject="s",
            body="b",
            attachment_blobs=[
                {"filename": "Résumé — 2026.pdf", "mime_type": "application/pdf", "data": b"x"}
            ],
        )
        msg = _parse(result)
        names = [p.get_filename() for p in msg.iter_attachments()]
        assert names == ["Résumé — 2026.pdf"]

    def test_filename_with_quote_is_escaped(self):
        result = compose_message(
            to="bob@example.com",
            subject="s",
            body="b",
            attachment_blobs=[{"filename": 'a"b.txt', "mime_type": "text/plain", "data": b"x"}],
        )
        msg = _parse(result)
        assert [p.get_filename() for p in msg.iter_attachments()] == ['a"b.txt']

    def test_non_ascii_display_names(self):
        result = compose_message(
            to="José Núñez <jose@example.com>, Zoë <zoe@example.com>",
            subject="Grüße",
            body="b",
            cc='"Smith, John" <john@example.com>',
        )
        raw = base64.urlsafe_b64decode(result["raw"])
        assert b"unknown-8bit" not in raw
        msg = _parse(result)
        to = msg["to"].addresses
        assert [(a.display_name, a.addr_spec) for a in to] == [
            ("José Núñez", "jose@example.com"),
            ("Zoë", "zoe@example.com"),
        ]
        assert msg["subject"] == "Grüße"
        assert [(a.display_name, a.addr_spec) for a in msg["cc"].addresses] == [
            ("Smith, John", "john@example.com")
        ]


class TestForwardEscapingAndInline:
    """DATA-11: forwarded headers/plain bodies escaped in HTML; inline parts keep CID."""

    def test_html_forward_escapes_header_values(self):
        original = {
            "from": "Alice <alice@example.com>",
            "date": "Mon, 1 Jan 2026",
            "subject": "<script>x</script>",
            "body": "<p>hi</p>",
            "content_type": "text/html",
        }
        msg = _parse(compose_forward_message(original, to="bob@example.com"))
        body = msg.get_body(("html",)).get_content()
        assert "From: Alice &lt;alice@example.com&gt;" in body
        assert "<script>" not in body
        assert "<p>hi</p>" in body  # original HTML body untouched

    def test_plain_original_escaped_inside_pre_when_comment_is_html(self):
        original = {
            "from": "a@example.com",
            "subject": "s",
            "body": "x < y & <b>not bold</b>",
            "content_type": "text/plain",
        }
        msg = _parse(
            compose_forward_message(original, to="bob@example.com", additional_text="<b>FYI</b>")
        )
        body = msg.get_body(("html",)).get_content()
        assert "<pre>x &lt; y &amp; &lt;b&gt;not bold&lt;/b&gt;</pre>" in body
        assert body.startswith("<b>FYI</b>")

    def test_inline_image_keeps_content_id_in_related(self):
        original = {
            "from": "a@example.com",
            "subject": "s",
            "body": '<img src="cid:logo123">',
            "content_type": "text/html",
        }
        blobs = [
            {
                "filename": "logo.png",
                "mime_type": "image/png",
                "data": b"\x89PNG",
                "inline": True,
                "content_id": "logo123",
            },
            {"filename": "doc.pdf", "mime_type": "application/pdf", "data": b"%PDF"},
        ]
        msg = _parse(compose_forward_message(original, "bob@example.com", attachment_blobs=blobs))
        parts = {p.get_filename(): p for p in msg.walk() if p.get_filename()}
        logo = parts["logo.png"]
        assert logo["Content-ID"] == "<logo123>"
        assert logo.get_content_disposition() == "inline"
        assert parts["doc.pdf"].get_content_disposition() == "attachment"
        related = [p for p in msg.walk() if p.get_content_type() == "multipart/related"]
        assert len(related) == 1
        assert logo in related[0].get_payload()

    @patch("iobox.providers.google._sender.send_message")
    @patch("iobox.providers.google._sender.download_attachment", return_value=b"\x89PNG")
    @patch("iobox.providers.google._sender.get_email_content")
    def test_forward_email_passes_inline_metadata(self, mock_get, mock_dl, mock_send):
        mock_get.return_value = {
            "from": "a@example.com",
            "subject": "s",
            "body": '<img src="cid:c1">',
            "content_type": "text/html",
            "attachments": [
                {
                    "id": "att-1",
                    "filename": "logo.png",
                    "mime_type": "image/png",
                    "inline": True,
                    "content_id": "c1",
                }
            ],
        }
        forward_email(MagicMock(), "orig-1", "bob@example.com")
        msg = _parse(mock_send.call_args.args[1])
        logo = next(p for p in msg.walk() if p.get_filename() == "logo.png")
        assert logo["Content-ID"] == "<c1>"
