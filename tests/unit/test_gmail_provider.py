"""
Unit tests for the GmailProvider class.

Verifies that each abstract method correctly delegates to the underlying
Gmail module functions, and covers _build_gmail_query() and _to_email_data()
field-by-field.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.base import EmailQuery
from iobox.providers.google.email import GmailProvider


@pytest.fixture
def provider():
    """Return a GmailProvider with a pre-injected mock service."""
    p = GmailProvider()
    p._service = MagicMock(name="gmail_service")
    return p


# ------------------------------------------------------------------
# _build_gmail_query — field-by-field coverage
# ------------------------------------------------------------------


class TestBuildGmailQuery:
    """Test _build_gmail_query translates every EmailQuery field correctly."""

    def test_empty_query(self, provider):
        q = EmailQuery()
        assert provider._build_gmail_query(q) == ""

    def test_raw_query_passthrough(self, provider):
        q = EmailQuery(raw_query="in:anywhere has:attachment filename:pdf")
        assert provider._build_gmail_query(q) == "in:anywhere has:attachment filename:pdf"

    def test_raw_query_overrides_other_fields(self, provider):
        q = EmailQuery(raw_query="raw", text="ignored", from_addr="x@y.com")
        assert provider._build_gmail_query(q) == "raw"

    def test_text(self, provider):
        q = EmailQuery(text="hello world")
        assert provider._build_gmail_query(q) == "hello world"

    def test_from_addr(self, provider):
        q = EmailQuery(from_addr="alice@example.com")
        assert provider._build_gmail_query(q) == "from:alice@example.com"

    def test_to_addr(self, provider):
        q = EmailQuery(to_addr="bob@example.com")
        assert provider._build_gmail_query(q) == "to:bob@example.com"

    def test_subject(self, provider):
        q = EmailQuery(subject="Meeting notes")
        assert provider._build_gmail_query(q) == "subject:Meeting notes"

    def test_after_date(self, provider):
        q = EmailQuery(after=date(2024, 3, 15))
        assert provider._build_gmail_query(q) == "after:2024/03/15"

    def test_before_date(self, provider):
        q = EmailQuery(before=date(2024, 6, 1))
        assert provider._build_gmail_query(q) == "before:2024/06/01"

    def test_has_attachment_true(self, provider):
        q = EmailQuery(has_attachment=True)
        assert provider._build_gmail_query(q) == "has:attachment"

    def test_has_attachment_false(self, provider):
        q = EmailQuery(has_attachment=False)
        assert provider._build_gmail_query(q) == "-has:attachment"

    def test_has_attachment_none(self, provider):
        q = EmailQuery(has_attachment=None)
        assert provider._build_gmail_query(q) == ""

    def test_is_unread_true(self, provider):
        q = EmailQuery(is_unread=True)
        assert provider._build_gmail_query(q) == "is:unread"

    def test_is_unread_false(self, provider):
        q = EmailQuery(is_unread=False)
        assert provider._build_gmail_query(q) == "is:read"

    def test_label(self, provider):
        q = EmailQuery(label="important")
        assert provider._build_gmail_query(q) == "label:important"

    def test_all_fields_combined(self, provider):
        q = EmailQuery(
            text="quarterly",
            from_addr="cfo@corp.com",
            to_addr="team@corp.com",
            subject="Q4 Report",
            after=date(2024, 1, 1),
            before=date(2024, 12, 31),
            has_attachment=True,
            is_unread=True,
            label="finance",
        )
        result = provider._build_gmail_query(q)
        assert result == (
            "quarterly from:cfo@corp.com to:team@corp.com subject:Q4 Report "
            "after:2024/01/01 before:2024/12/31 has:attachment is:unread label:finance"
        )


# ------------------------------------------------------------------
# _to_email_data — field-by-field coverage
# ------------------------------------------------------------------


class TestToEmailData:
    """Test _to_email_data normalises Gmail dicts into EmailData."""

    def test_minimal_metadata(self, provider):
        raw = {
            "message_id": "abc123",
            "subject": "Hello",
            "from": "Alice <alice@x.com>",
            "date": "2024-01-15",
            "snippet": "Preview text",
            "labels": ["INBOX", "UNREAD"],
            "thread_id": "t001",
        }
        data = provider._to_email_data(raw)
        assert data["message_id"] == "abc123"
        assert data["subject"] == "Hello"
        assert data["from_"] == "Alice <alice@x.com>"
        assert data["date"] == "2024-01-15"
        assert data["snippet"] == "Preview text"
        assert data["labels"] == ["INBOX", "UNREAD"]
        assert data["thread_id"] == "t001"

    def test_from_keyword_rename(self, provider):
        """Gmail uses 'from' (Python keyword); EmailData uses 'from_'."""
        raw = {"from": "Bob <bob@y.com>"}
        data = provider._to_email_data(raw)
        assert data["from_"] == "Bob <bob@y.com>"

    def test_from_underscore_fallback(self, provider):
        """If raw already uses 'from_' (some code paths), it should work."""
        raw = {"from_": "Carol <carol@z.com>"}
        data = provider._to_email_data(raw)
        assert data["from_"] == "Carol <carol@z.com>"

    def test_defaults_for_missing_keys(self, provider):
        data = provider._to_email_data({})
        assert data["message_id"] == ""
        assert data["subject"] == ""
        assert data["from_"] == ""
        assert data["date"] == ""
        assert data["snippet"] == ""
        assert data["labels"] == []
        assert data["thread_id"] == ""

    def test_labels_are_copied_not_shared(self, provider):
        original_labels = ["INBOX"]
        raw = {"labels": original_labels}
        data = provider._to_email_data(raw)
        data["labels"].append("STARRED")
        assert original_labels == ["INBOX"]  # Not mutated

    def test_full_retrieval_fields(self, provider):
        raw = {
            "message_id": "m1",
            "body": "<p>Hello</p>",
            "content_type": "text/html",
            "attachments": [
                {
                    "id": "att1",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "size": 12345,
                },
            ],
        }
        data = provider._to_email_data(raw)
        assert data["body"] == "<p>Hello</p>"
        assert data["content_type"] == "text/html"
        assert len(data["attachments"]) == 1
        att = data["attachments"][0]
        assert att["id"] == "att1"
        assert att["filename"] == "report.pdf"
        assert att["mime_type"] == "application/pdf"
        assert att["size"] == 12345

    def test_full_retrieval_fields_absent_in_search(self, provider):
        raw = {"message_id": "m2", "subject": "Search result"}
        data = provider._to_email_data(raw)
        assert "body" not in data
        assert "content_type" not in data
        assert "attachments" not in data

    def test_attachment_defaults(self, provider):
        raw = {"attachments": [{}]}
        data = provider._to_email_data(raw)
        att = data["attachments"][0]
        assert att["id"] == ""
        assert att["filename"] == ""
        assert att["mime_type"] == "application/octet-stream"
        assert att["size"] == 0


# ------------------------------------------------------------------
# Authentication & profile delegation
# ------------------------------------------------------------------


class TestAuthentication:
    @patch("iobox.providers.google.auth.get_gmail_service")
    def test_authenticate(self, mock_get_svc, provider):
        sentinel = MagicMock()
        mock_get_svc.return_value = sentinel
        provider.authenticate()
        mock_get_svc.assert_called_once()
        assert provider._service is sentinel

    @patch("iobox.providers.google.auth.get_gmail_profile")
    def test_get_profile(self, mock_profile, provider):
        mock_profile.return_value = {"emailAddress": "me@gmail.com"}
        result = provider.get_profile()
        mock_profile.assert_called_once_with(provider._service)
        assert result == {"emailAddress": "me@gmail.com"}


# ------------------------------------------------------------------
# Search & read delegation
# ------------------------------------------------------------------


class TestSearchAndRead:
    @patch("iobox.providers.google._retrieval.get_label_map")
    @patch("iobox.providers.google._search.search_emails")
    def test_search_emails(self, mock_search, mock_label_map, provider):
        mock_label_map.return_value = {"INBOX": "INBOX"}
        mock_search.return_value = [{"message_id": "m1", "from": "a@b.com", "subject": "Hi"}]
        query = EmailQuery(text="test", max_results=5)
        results = provider.search_emails(query)

        mock_label_map.assert_called_once_with(provider._service)
        mock_search.assert_called_once_with(
            provider._service,
            query="test",
            max_results=5,
            start_date="2000/01/01",
            end_date=None,
            label_map={"INBOX": "INBOX"},
            include_spam_trash=False,
        )
        assert len(results) == 1
        assert results[0]["message_id"] == "m1"

    @patch("iobox.providers.google._retrieval.get_label_map")
    @patch("iobox.providers.google._search.search_emails")
    def test_search_emails_with_dates(self, mock_search, mock_label_map, provider):
        mock_label_map.return_value = {}
        mock_search.return_value = []
        query = EmailQuery(after=date(2024, 3, 1), before=date(2024, 3, 31))
        provider.search_emails(query)

        mock_search.assert_called_once()
        kwargs = mock_search.call_args
        assert kwargs.kwargs["start_date"] == "2024/03/01"
        assert kwargs.kwargs["end_date"] == "2024/03/31"

    @patch("iobox.providers.google._retrieval.get_label_map")
    @patch("iobox.providers.google._retrieval.get_email_content")
    def test_get_email_content(self, mock_get, mock_label_map, provider):
        mock_label_map.return_value = {}
        mock_get.return_value = {
            "message_id": "m1",
            "body": "text body",
            "content_type": "text/plain",
        }
        result = provider.get_email_content("m1", preferred_content_type="text/html")
        mock_get.assert_called_once_with(
            provider._service,
            message_id="m1",
            preferred_content_type="text/html",
            label_map={},
        )
        assert result["message_id"] == "m1"
        assert result["body"] == "text body"

    @patch("iobox.providers.google._retrieval.get_label_map")
    @patch("iobox.providers.google._retrieval.batch_get_emails")
    def test_batch_get_emails(self, mock_batch, mock_label_map, provider):
        mock_label_map.return_value = {}
        mock_batch.return_value = [
            {"message_id": "m1"},
            {"message_id": "m2"},
        ]
        results = provider.batch_get_emails(["m1", "m2"])
        mock_batch.assert_called_once_with(
            provider._service,
            message_ids=["m1", "m2"],
            preferred_content_type="text/plain",
            label_map={},
        )
        assert len(results) == 2

    @patch("iobox.providers.google._retrieval.get_thread_content")
    def test_get_thread(self, mock_thread, provider):
        mock_thread.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        results = provider.get_thread("t001")
        mock_thread.assert_called_once_with(provider._service, thread_id="t001")
        assert len(results) == 2

    @patch("iobox.providers.google._retrieval.download_attachment")
    def test_download_attachment(self, mock_dl, provider):
        mock_dl.return_value = b"\x89PNG"
        result = provider.download_attachment("m1", "att1")
        mock_dl.assert_called_once_with(provider._service, "m1", "att1")
        assert result == b"\x89PNG"


# ------------------------------------------------------------------
# Send, forward & drafts delegation
# ------------------------------------------------------------------


class TestSendForwardDrafts:
    @patch("iobox.providers.google._sender.send_message")
    @patch("iobox.providers.google._sender.compose_message")
    def test_send_message(self, mock_compose, mock_send, provider):
        mock_compose.return_value = {"raw": "encoded"}
        mock_send.return_value = {"id": "sent1"}
        result = provider.send_message(
            to="bob@x.com",
            subject="Hi",
            body="Hello",
            cc="cc@x.com",
            bcc="bcc@x.com",
            content_type="html",
            attachments=["/tmp/file.pdf"],
        )
        mock_compose.assert_called_once_with(
            to="bob@x.com",
            subject="Hi",
            body="Hello",
            cc="cc@x.com",
            bcc="bcc@x.com",
            content_type="html",
            attachments=["/tmp/file.pdf"],
        )
        mock_send.assert_called_once_with(provider._service, {"raw": "encoded"})
        assert result == {"id": "sent1"}

    @patch("iobox.providers.google._sender.forward_email")
    def test_forward_message(self, mock_fwd, provider):
        mock_fwd.return_value = {"id": "fwd1"}
        result = provider.forward_message("m1", to="fwd@x.com", comment="FYI")
        mock_fwd.assert_called_once_with(
            provider._service,
            message_id="m1",
            to="fwd@x.com",
            additional_text="FYI",
        )
        assert result == {"id": "fwd1"}

    @patch("iobox.providers.google._sender.create_draft")
    @patch("iobox.providers.google._sender.compose_message")
    def test_create_draft(self, mock_compose, mock_create, provider):
        mock_compose.return_value = {"raw": "encoded"}
        mock_create.return_value = {"id": "draft1"}
        result = provider.create_draft(to="a@b.com", subject="Draft", body="body", cc="c@d.com")
        mock_compose.assert_called_once_with(
            to="a@b.com",
            subject="Draft",
            body="body",
            cc="c@d.com",
            bcc=None,
            content_type="plain",
        )
        mock_create.assert_called_once_with(provider._service, {"raw": "encoded"})
        assert result == {"id": "draft1"}

    @patch("iobox.providers.google._sender.list_drafts")
    def test_list_drafts(self, mock_list, provider):
        mock_list.return_value = [{"id": "d1"}, {"id": "d2"}]
        result = provider.list_drafts(max_results=5)
        mock_list.assert_called_once_with(provider._service, max_results=5)
        assert len(result) == 2

    @patch("iobox.providers.google._sender.send_draft")
    def test_send_draft(self, mock_send, provider):
        mock_send.return_value = {"id": "sent_draft"}
        result = provider.send_draft("d1")
        mock_send.assert_called_once_with(provider._service, "d1")
        assert result == {"id": "sent_draft"}

    @patch("iobox.providers.google._sender.delete_draft")
    def test_delete_draft(self, mock_del, provider):
        mock_del.return_value = {"status": "deleted"}
        result = provider.delete_draft("d1")
        mock_del.assert_called_once_with(provider._service, "d1")
        assert result == {"status": "deleted"}


# ------------------------------------------------------------------
# System operations delegation
# ------------------------------------------------------------------


class TestSystemOperations:
    @patch("iobox.providers.google._retrieval.modify_message_labels")
    def test_mark_read(self, mock_modify, provider):
        provider.mark_read("m1", read=True)
        mock_modify.assert_called_once_with(provider._service, "m1", remove_labels=["UNREAD"])

    @patch("iobox.providers.google._retrieval.modify_message_labels")
    def test_mark_unread(self, mock_modify, provider):
        provider.mark_read("m1", read=False)
        mock_modify.assert_called_once_with(provider._service, "m1", add_labels=["UNREAD"])

    @patch("iobox.providers.google._retrieval.modify_message_labels")
    def test_set_star_true(self, mock_modify, provider):
        provider.set_star("m1", starred=True)
        mock_modify.assert_called_once_with(provider._service, "m1", add_labels=["STARRED"])

    @patch("iobox.providers.google._retrieval.modify_message_labels")
    def test_set_star_false(self, mock_modify, provider):
        provider.set_star("m1", starred=False)
        mock_modify.assert_called_once_with(provider._service, "m1", remove_labels=["STARRED"])

    @patch("iobox.providers.google._retrieval.modify_message_labels")
    def test_archive(self, mock_modify, provider):
        provider.archive("m1")
        mock_modify.assert_called_once_with(provider._service, "m1", remove_labels=["INBOX"])

    @patch("iobox.providers.google._retrieval.trash_message")
    def test_trash(self, mock_trash, provider):
        provider.trash("m1")
        mock_trash.assert_called_once_with(provider._service, "m1")

    @patch("iobox.providers.google._retrieval.untrash_message")
    def test_untrash(self, mock_untrash, provider):
        provider.untrash("m1")
        mock_untrash.assert_called_once_with(provider._service, "m1")


# ------------------------------------------------------------------
# Tag operations delegation
# ------------------------------------------------------------------


class TestTagOperations:
    @patch("iobox.providers.google._retrieval.modify_message_labels")
    @patch("iobox.providers.google._retrieval.resolve_label_name")
    def test_add_tag(self, mock_resolve, mock_modify, provider):
        mock_resolve.return_value = "Label_123"
        provider.add_tag("m1", "Projects")
        mock_resolve.assert_called_once_with(provider._service, "Projects")
        mock_modify.assert_called_once_with(provider._service, "m1", add_labels=["Label_123"])

    @patch("iobox.providers.google._retrieval.modify_message_labels")
    @patch("iobox.providers.google._retrieval.resolve_label_name")
    def test_remove_tag(self, mock_resolve, mock_modify, provider):
        mock_resolve.return_value = "Label_456"
        provider.remove_tag("m1", "Archive")
        mock_resolve.assert_called_once_with(provider._service, "Archive")
        mock_modify.assert_called_once_with(provider._service, "m1", remove_labels=["Label_456"])

    @patch("iobox.providers.google._retrieval.get_label_map")
    def test_list_tags(self, mock_label_map, provider):
        mock_label_map.return_value = {"INBOX": "INBOX", "Label_1": "Work"}
        result = provider.list_tags()
        mock_label_map.assert_called_once_with(provider._service)
        assert result == {"INBOX": "INBOX", "Label_1": "Work"}


# ------------------------------------------------------------------
# Sync delegation
# ------------------------------------------------------------------


class TestSync:
    @patch("iobox.providers.google.auth.get_gmail_profile")
    def test_get_sync_state(self, mock_profile, provider):
        mock_profile.return_value = {"historyId": "99999"}
        result = provider.get_sync_state()
        mock_profile.assert_called_once_with(provider._service)
        assert result == "99999"

    @patch("iobox.providers.google.auth.get_gmail_profile")
    def test_get_sync_state_missing_history_id(self, mock_profile, provider):
        mock_profile.return_value = {}
        result = provider.get_sync_state()
        assert result == ""

    @patch("iobox.providers.google._search.get_new_messages")
    def test_get_new_messages(self, mock_new, provider):
        mock_new.return_value = ["m1", "m2", "m3"]
        result = provider.get_new_messages("12345")
        mock_new.assert_called_once_with(provider._service, "12345")
        assert result == ["m1", "m2", "m3"]

    @patch("iobox.providers.google._search.get_new_messages")
    def test_get_new_messages_expired(self, mock_new, provider):
        mock_new.return_value = None
        result = provider.get_new_messages("old_token")
        assert result is None


# ------------------------------------------------------------------
# Lazy service initialization
# ------------------------------------------------------------------


class TestLazyService:
    @patch("iobox.providers.google.auth.get_gmail_service")
    @patch("iobox.providers.google.auth.get_gmail_profile")
    def test_svc_lazy_init(self, mock_profile, mock_get_svc):
        """Accessing _svc auto-authenticates when _service is None."""
        sentinel = MagicMock()
        mock_get_svc.return_value = sentinel
        mock_profile.return_value = {"emailAddress": "test@gmail.com"}

        p = GmailProvider()
        assert p._service is None

        p.get_profile()

        mock_get_svc.assert_called_once()
        assert p._service is sentinel
