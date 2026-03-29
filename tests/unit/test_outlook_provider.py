"""
Unit tests for ``OutlookProvider``.

Tests all abstract methods with mocked python-o365 objects from
``tests.fixtures.mock_outlook_responses``.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.base import EmailQuery
from iobox.providers.o365.email import OutlookProvider
from tests.fixtures.mock_outlook_responses import (
    MOCK_ATTACHMENT_MESSAGE,
    MOCK_HTML_MESSAGE,
    MOCK_MULTI_ATTACHMENT_MESSAGE,
    MOCK_PLAIN_TEXT_MESSAGE,
    MockAccount,
    MockHttpResponse,
    make_full_mock_account,
    make_mock_account,
    make_mock_message,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> OutlookProvider:
    """Return an OutlookProvider pre-wired with a full mock account."""
    p = OutlookProvider()
    account = make_full_mock_account()
    p._account = account
    p._mailbox = account.mailbox()
    return p


@pytest.fixture
def single_msg_provider() -> OutlookProvider:
    """Provider with a single plain-text message."""
    p = OutlookProvider()
    msg = make_mock_message()
    account = make_mock_account(messages=[msg])
    p._account = account
    p._mailbox = account.mailbox()
    return p


# ---------------------------------------------------------------------------
# _message_to_email_data
# ---------------------------------------------------------------------------


class TestMessageToEmailData:
    def test_basic_fields(self, provider):
        msg = MOCK_PLAIN_TEXT_MESSAGE
        data = provider._message_to_email_data(msg, include_body=True)
        assert data["message_id"] == "outlook-msg-id-1"
        assert data["thread_id"] == "outlook-conv-id-1"
        assert data["subject"] == "Plain Text Email"
        assert "Bob Sender" in data["from_"]
        assert "bob@example.com" in data["from_"]
        assert data["snippet"] == "This is a plain text email."
        assert data["labels"] == ["Work"]

    def test_html_content_type(self, provider):
        data = provider._message_to_email_data(MOCK_HTML_MESSAGE, include_body=True)
        assert data["content_type"] == "text/html"

    def test_plain_text_content_type(self, provider):
        data = provider._message_to_email_data(MOCK_PLAIN_TEXT_MESSAGE, include_body=True)
        assert data["content_type"] == "text/plain"

    def test_body_included(self, provider):
        data = provider._message_to_email_data(MOCK_PLAIN_TEXT_MESSAGE, include_body=True)
        assert "body" in data
        assert data["body"] == "This is a plain text email."

    def test_body_excluded(self, provider):
        data = provider._message_to_email_data(MOCK_PLAIN_TEXT_MESSAGE, include_body=False)
        assert "body" not in data
        assert "content_type" not in data
        assert "attachments" not in data

    def test_attachments_present(self, provider):
        data = provider._message_to_email_data(MOCK_ATTACHMENT_MESSAGE, include_body=True)
        assert len(data["attachments"]) == 1
        att = data["attachments"][0]
        assert att["id"] == "outlook-attach-id-1"
        assert att["filename"] == "document.pdf"
        assert att["mime_type"] == "application/pdf"
        assert att["size"] == 1024

    def test_multiple_attachments(self, provider):
        data = provider._message_to_email_data(MOCK_MULTI_ATTACHMENT_MESSAGE, include_body=True)
        assert len(data["attachments"]) == 2

    def test_no_attachments(self, provider):
        data = provider._message_to_email_data(MOCK_HTML_MESSAGE, include_body=True)
        assert data["attachments"] == []

    def test_date_iso_format(self, provider):
        data = provider._message_to_email_data(MOCK_PLAIN_TEXT_MESSAGE, include_body=False)
        assert "2026-03-06" in data["date"]

    def test_sender_with_no_name(self, provider):
        msg = make_mock_message(sender_name="", sender_address="anon@example.com")
        data = provider._message_to_email_data(msg, include_body=False)
        assert data["from_"] == "anon@example.com"

    def test_empty_categories(self, provider):
        data = provider._message_to_email_data(MOCK_HTML_MESSAGE, include_body=False)
        assert data["labels"] == []


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    @patch("iobox.providers.o365.auth.get_outlook_account")
    def test_authenticate_sets_account_and_mailbox(self, mock_get_acct):
        mock_account = make_mock_account()
        mock_get_acct.return_value = mock_account

        p = OutlookProvider()
        p.authenticate()

        mock_get_acct.assert_called_once()
        assert p._account is mock_account
        assert p._mailbox is not None

    @patch("iobox.providers.o365.auth.get_outlook_account")
    def test_authenticate_sets_immutable_id_header(self, mock_get_acct):
        mock_account = make_mock_account()
        mock_get_acct.return_value = mock_account

        p = OutlookProvider()
        p.authenticate()

        assert p._account.con.session.headers.get("Prefer") == 'IdType="ImmutableId"'


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    def test_returns_provider_and_auth_status(self, provider):
        result = provider.get_profile()
        assert result["provider"] == "outlook"
        assert result["authenticated"] is True

    def test_unauthenticated_profile(self):
        p = OutlookProvider()
        account = MockAccount(is_authenticated=False)
        p._account = account
        p._mailbox = account.mailbox()
        result = p.get_profile()
        assert result["authenticated"] is False


# ---------------------------------------------------------------------------
# search_emails
# ---------------------------------------------------------------------------


class TestSearchEmails:
    def test_search_returns_metadata_only(self, provider):
        query = EmailQuery(max_results=10)
        results = provider.search_emails(query)
        # Should return results without body
        assert isinstance(results, list)
        for r in results:
            assert "body" not in r

    def test_search_with_raw_query(self, provider):
        query = EmailQuery(raw_query="from:alice@example.com", max_results=5)
        results = provider.search_emails(query)
        assert isinstance(results, list)

    def test_search_with_text_uses_search_path(self, provider):
        query = EmailQuery(text="important meeting", max_results=5)
        results = provider.search_emails(query)
        assert isinstance(results, list)

    def test_search_with_structured_filter(self, provider):
        query = EmailQuery(from_addr="bob@example.com", max_results=5)
        results = provider.search_emails(query)
        assert isinstance(results, list)

    def test_search_respects_max_results(self, provider):
        query = EmailQuery(max_results=2)
        results = provider.search_emails(query)
        assert len(results) <= 2

    def test_search_returns_messages_from_all_folders(self, provider):
        """search_emails must find messages outside the Inbox (all-mail search).

        ``MOCK_DRAFT_MESSAGE`` is stored in ``_messages_by_id`` but placed in
        the Drafts folder — NOT the Inbox.  The old ``inbox_folder()``-based
        implementation would miss it; the new ``self._mb.get_messages()`` path
        should return it.
        """
        query = EmailQuery(max_results=100)
        results = provider.search_emails(query)
        result_ids = {r["message_id"] for r in results}
        assert "outlook-draft-id-1" in result_ids, (
            "Draft message (non-inbox) should be found by search_emails"
        )


# ---------------------------------------------------------------------------
# get_email_content
# ---------------------------------------------------------------------------


class TestGetEmailContent:
    def test_returns_full_email_data(self, provider):
        data = provider.get_email_content("outlook-msg-id-1")
        assert data["message_id"] == "outlook-msg-id-1"
        assert "body" in data
        assert "content_type" in data

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.get_email_content("nonexistent-id")


# ---------------------------------------------------------------------------
# batch_get_emails
# ---------------------------------------------------------------------------


class TestBatchGetEmails:
    def test_returns_multiple(self, provider):
        results = provider.batch_get_emails(["outlook-msg-id-1", "outlook-msg-id-2"])
        assert len(results) == 2
        ids = {r["message_id"] for r in results}
        assert "outlook-msg-id-1" in ids
        assert "outlook-msg-id-2" in ids

    def test_skips_missing_messages(self, provider):
        results = provider.batch_get_emails(["outlook-msg-id-1", "does-not-exist"])
        assert len(results) == 1

    def test_empty_list(self, provider):
        results = provider.batch_get_emails([])
        assert results == []


# ---------------------------------------------------------------------------
# get_thread
# ---------------------------------------------------------------------------


class TestGetThread:
    def test_returns_thread_messages(self, provider):
        results = provider.get_thread("outlook-conv-thread-1")
        assert isinstance(results, list)
        for r in results:
            assert "body" in r

    def test_empty_thread(self, provider):
        results = provider.get_thread("nonexistent-conv-id")
        assert isinstance(results, list)

    def test_get_thread_finds_messages_across_all_folders(self, provider):
        """get_thread must find thread messages outside the Inbox.

        Adds a message with the target ``conversationId`` to ``_messages_by_id``
        without placing it in the inbox.  The new ``self._mb.get_messages()``
        implementation should surface it; the old ``inbox_folder()`` path
        would not.
        """
        extra_msg = make_mock_message(
            object_id="thread-sent-msg",
            conversation_id="outlook-conv-thread-1",
            subject="Re: Thread Email (sent copy)",
        )
        # Register in the global lookup only — not in the inbox folder.
        provider._mailbox._messages_by_id["thread-sent-msg"] = extra_msg

        results = provider.get_thread("outlook-conv-thread-1")
        result_ids = {r["message_id"] for r in results}
        assert "thread-sent-msg" in result_ids, (
            "Non-inbox thread message should be returned by get_thread"
        )


# ---------------------------------------------------------------------------
# download_attachment
# ---------------------------------------------------------------------------


class TestDownloadAttachment:
    def test_download_returns_bytes(self, provider):
        content = provider.download_attachment("outlook-msg-id-3", "outlook-attach-id-1")
        assert isinstance(content, bytes)
        assert content == b"%PDF-1.4 mock pdf content"

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.download_attachment("nonexistent", "att-id")

    def test_raises_on_missing_attachment(self, provider):
        with pytest.raises(ValueError, match="Attachment.*not found"):
            provider.download_attachment("outlook-msg-id-3", "nonexistent-att")


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_send_basic(self, provider):
        result = provider.send_message(
            to="recipient@example.com",
            subject="Test",
            body="Hello",
        )
        assert result["status"] == "sent"
        assert "message_id" in result

    def test_send_with_cc_bcc(self, provider):
        result = provider.send_message(
            to="recipient@example.com",
            subject="Test",
            body="Hello",
            cc="cc@example.com",
            bcc="bcc@example.com",
        )
        assert result["status"] == "sent"

    def test_send_html_body(self, provider):
        result = provider.send_message(
            to="recipient@example.com",
            subject="Test",
            body="<p>Hello</p>",
            content_type="html",
        )
        assert result["status"] == "sent"
        # Verify the new message had body_type set to HTML
        new_msg = provider._mailbox._new_messages[-1]
        assert new_msg.body_type == "HTML"

    def test_send_with_attachments(self, provider):
        result = provider.send_message(
            to="recipient@example.com",
            subject="Test",
            body="Hello",
            attachments=["/tmp/file.pdf"],
        )
        assert result["status"] == "sent"

    def test_send_marks_message_as_sent(self, provider):
        provider.send_message(to="recipient@example.com", subject="Test", body="Hello")
        new_msg = provider._mailbox._new_messages[-1]
        assert new_msg._sent is True

    def test_send_raises_runtime_error_on_failure(self, provider):
        """send() returning False must raise RuntimeError."""
        # Patch new_message() to return a message whose send() returns False.
        failing_msg = make_mock_message(object_id="fail-send-id")
        failing_msg.send = lambda: False  # type: ignore[method-assign]
        provider._mailbox.new_message = lambda: failing_msg  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="Failed to send message"):
            provider.send_message(to="recipient@example.com", subject="Test", body="Hello")


# ---------------------------------------------------------------------------
# forward_message
# ---------------------------------------------------------------------------


class TestForwardMessage:
    def test_forward_basic(self, provider):
        result = provider.forward_message("outlook-msg-id-1", to="fwd@example.com")
        assert result["status"] == "sent"
        assert "message_id" in result

    def test_forward_with_comment(self, provider):
        result = provider.forward_message("outlook-msg-id-1", to="fwd@example.com", comment="FYI")
        assert result["status"] == "sent"

    def test_forward_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.forward_message("nonexistent", to="fwd@example.com")

    def test_forward_raises_runtime_error_on_failure(self, provider):
        """fwd.send() returning False must raise RuntimeError."""
        # Make the forwarded stub's send() return False.
        original_msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        fwd_stub = make_mock_message(object_id="fwd-fail-id")
        fwd_stub.send = lambda: False  # type: ignore[method-assign]
        original_msg.forward = lambda: fwd_stub  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="Failed to forward message"):
            provider.forward_message("outlook-msg-id-1", to="fwd@example.com")


# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------


class TestCreateDraft:
    def test_create_basic_draft(self, provider):
        result = provider.create_draft(
            to="recipient@example.com",
            subject="Draft Test",
            body="Draft body",
        )
        assert result["status"] == "draft"
        assert "message_id" in result

    def test_create_draft_with_cc_bcc(self, provider):
        result = provider.create_draft(
            to="recipient@example.com",
            subject="Draft",
            body="body",
            cc="cc@example.com",
            bcc="bcc@example.com",
        )
        assert result["status"] == "draft"

    def test_create_html_draft(self, provider):
        provider.create_draft(
            to="r@example.com",
            subject="HTML Draft",
            body="<p>Hi</p>",
            content_type="html",
        )
        new_msg = provider._mailbox._new_messages[-1]
        assert new_msg.body_type == "HTML"

    def test_draft_saved(self, provider):
        provider.create_draft(to="r@example.com", subject="Draft", body="body")
        new_msg = provider._mailbox._new_messages[-1]
        assert new_msg._draft_saved is True

    def test_create_draft_raises_runtime_error_on_failure(self, provider):
        """save_draft() returning False must raise RuntimeError."""
        failing_msg = make_mock_message(object_id="fail-draft-id")
        failing_msg.save_draft = lambda: False  # type: ignore[method-assign]
        provider._mailbox.new_message = lambda: failing_msg  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="Failed to save draft"):
            provider.create_draft(to="r@example.com", subject="Draft", body="body")


# ---------------------------------------------------------------------------
# list_drafts
# ---------------------------------------------------------------------------


class TestListDrafts:
    def test_list_drafts_returns_summaries(self, provider):
        # Add a draft to the drafts folder
        results = provider.list_drafts(max_results=10)
        assert isinstance(results, list)
        for d in results:
            assert "message_id" in d
            assert "subject" in d
            assert "snippet" in d


# ---------------------------------------------------------------------------
# send_draft
# ---------------------------------------------------------------------------


class TestSendDraft:
    def test_send_existing_draft(self, provider):
        result = provider.send_draft("outlook-draft-id-1")
        assert result["status"] == "sent"
        assert result["message_id"] == "outlook-draft-id-1"

    def test_send_draft_raises_on_missing(self, provider):
        with pytest.raises(ValueError, match="Draft not found"):
            provider.send_draft("nonexistent-draft")

    def test_send_draft_raises_runtime_error_on_failure(self, provider):
        """send() returning False on an existing draft must raise RuntimeError."""
        draft_msg = provider._mailbox.get_message(object_id="outlook-draft-id-1")
        draft_msg.send = lambda: False  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="Failed to send draft"):
            provider.send_draft("outlook-draft-id-1")


# ---------------------------------------------------------------------------
# delete_draft
# ---------------------------------------------------------------------------


class TestDeleteDraft:
    def test_delete_existing_draft(self, provider):
        result = provider.delete_draft("outlook-draft-id-1")
        assert result["status"] == "deleted"
        assert result["message_id"] == "outlook-draft-id-1"

    def test_delete_draft_raises_on_missing(self, provider):
        with pytest.raises(ValueError, match="Draft not found"):
            provider.delete_draft("nonexistent-draft")

    def test_delete_draft_raises_runtime_error_on_failure(self, provider):
        """delete() returning False on an existing draft must raise RuntimeError."""
        draft_msg = provider._mailbox.get_message(object_id="outlook-draft-id-1")
        draft_msg.delete = lambda: False  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="Failed to delete draft"):
            provider.delete_draft("outlook-draft-id-1")


# ---------------------------------------------------------------------------
# mark_read
# ---------------------------------------------------------------------------


class TestMarkRead:
    def test_mark_read(self, provider):
        provider.mark_read("outlook-msg-id-6", read=True)
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-6")
        assert msg.is_read is True
        assert msg._read_marked is True

    def test_mark_unread(self, provider):
        provider.mark_read("outlook-msg-id-1", read=False)
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        assert msg.is_read is False
        assert msg._read_marked is False

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.mark_read("nonexistent", read=True)


# ---------------------------------------------------------------------------
# set_star
# ---------------------------------------------------------------------------


class TestSetStar:
    def test_star_message(self, provider):
        provider.set_star("outlook-msg-id-1", starred=True)
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        assert msg.flag == {"flagStatus": "flagged"}
        assert msg._message_saved is True

    def test_unstar_message(self, provider):
        provider.set_star("outlook-msg-id-5", starred=False)
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-5")
        assert msg.flag == {"flagStatus": "notFlagged"}

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.set_star("nonexistent", starred=True)


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


class TestArchive:
    def test_archive_message(self, provider):
        provider.archive("outlook-msg-id-1")
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        assert msg._moved_to is not None
        assert msg._moved_to.name == "Archive"

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.archive("nonexistent")


# ---------------------------------------------------------------------------
# trash / untrash
# ---------------------------------------------------------------------------


class TestTrash:
    def test_trash_message(self, provider):
        provider.trash("outlook-msg-id-1")
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        assert msg._deleted is True

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.trash("nonexistent")


class TestUntrash:
    def test_untrash_message(self, provider):
        provider.untrash("outlook-msg-id-1")
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        assert msg._moved_to is not None
        assert msg._moved_to.name == "Inbox"

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.untrash("nonexistent")


# ---------------------------------------------------------------------------
# add_tag / remove_tag
# ---------------------------------------------------------------------------


class TestAddTag:
    def test_add_new_category(self, provider):
        provider.add_tag("outlook-msg-id-2", "NewTag")
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-2")
        assert "NewTag" in msg.categories
        assert msg._message_saved is True

    def test_add_existing_category_is_noop(self, provider):
        # Use a fresh message to avoid shared state from other tests
        msg = make_mock_message(object_id="noop-add-tag", categories=["Work"])
        provider._mailbox._messages_by_id["noop-add-tag"] = msg
        provider.add_tag("noop-add-tag", "Work")
        assert msg.categories.count("Work") == 1
        # save_message should NOT be called for no-op
        assert msg._message_saved is False

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.add_tag("nonexistent", "Tag")


class TestRemoveTag:
    def test_remove_existing_category(self, provider):
        provider.remove_tag("outlook-msg-id-1", "Work")
        msg = provider._mailbox.get_message(object_id="outlook-msg-id-1")
        assert "Work" not in msg.categories
        assert msg._message_saved is True

    def test_remove_nonexistent_category_is_noop(self, provider):
        msg = make_mock_message(object_id="noop-remove-tag", categories=[])
        provider._mailbox._messages_by_id["noop-remove-tag"] = msg
        provider.remove_tag("noop-remove-tag", "NonExistent")
        assert msg._message_saved is False

    def test_raises_on_missing_message(self, provider):
        with pytest.raises(ValueError, match="Message not found"):
            provider.remove_tag("nonexistent", "Tag")


# ---------------------------------------------------------------------------
# list_tags
# ---------------------------------------------------------------------------


class TestListTags:
    def test_list_tags_returns_category_mapping(self, provider):
        # We need to mock con.get and con.protocol for list_tags
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [
                {"displayName": "Work", "color": "preset0"},
                {"displayName": "Personal", "color": "preset1"},
            ]
        }
        provider._account.con.get = MagicMock(return_value=mock_resp)
        provider._account.con.protocol = MagicMock()
        provider._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"

        result = provider.list_tags()
        assert result == {"Work": "Work", "Personal": "Personal"}

    def test_list_tags_empty(self, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"value": []}
        provider._account.con.get = MagicMock(return_value=mock_resp)
        provider._account.con.protocol = MagicMock()
        provider._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"

        result = provider.list_tags()
        assert result == {}


# ---------------------------------------------------------------------------
# _build_outlook_filter
# ---------------------------------------------------------------------------


class TestBuildOutlookFilter:
    def test_empty_query(self, provider):
        q = EmailQuery()
        result = provider._build_outlook_filter(q)
        assert result._filters == []

    def test_from_addr(self, provider):
        q = EmailQuery(from_addr="alice@example.com")
        result = provider._build_outlook_filter(q)
        assert any(
            "from/emailAddress/address" in f[0] and f[2] == "alice@example.com"
            for f in result._filters
        )

    def test_to_addr(self, provider):
        q = EmailQuery(to_addr="bob@example.com")
        result = provider._build_outlook_filter(q)
        assert any("toRecipients" in f[0] and f[2] == "bob@example.com" for f in result._filters)

    def test_subject(self, provider):
        q = EmailQuery(subject="Report")
        result = provider._build_outlook_filter(q)
        assert any(
            f[0] == "subject" and f[1] == "contains" and f[2] == "Report" for f in result._filters
        )

    def test_after_date(self, provider):
        q = EmailQuery(after=date(2024, 3, 15))
        result = provider._build_outlook_filter(q)
        assert any("receivedDateTime" in f[0] and f[1] == "ge" for f in result._filters)

    def test_before_date(self, provider):
        q = EmailQuery(before=date(2024, 6, 1))
        result = provider._build_outlook_filter(q)
        assert any("receivedDateTime" in f[0] and f[1] == "lt" for f in result._filters)

    def test_has_attachment_true(self, provider):
        q = EmailQuery(has_attachment=True)
        result = provider._build_outlook_filter(q)
        assert any("hasAttachments" in f[0] and f[2] is True for f in result._filters)

    def test_has_attachment_false(self, provider):
        q = EmailQuery(has_attachment=False)
        result = provider._build_outlook_filter(q)
        assert any("hasAttachments" in f[0] and f[2] is False for f in result._filters)

    def test_is_unread_true(self, provider):
        q = EmailQuery(is_unread=True)
        result = provider._build_outlook_filter(q)
        assert any("isRead" in f[0] and f[2] is False for f in result._filters)

    def test_is_unread_false(self, provider):
        q = EmailQuery(is_unread=False)
        result = provider._build_outlook_filter(q)
        assert any("isRead" in f[0] and f[2] is True for f in result._filters)

    def test_label(self, provider):
        q = EmailQuery(label="Important")
        result = provider._build_outlook_filter(q)
        assert any("categories" in f[0] for f in result._filters)


# ---------------------------------------------------------------------------
# _build_outlook_search
# ---------------------------------------------------------------------------


class TestBuildOutlookSearch:
    def test_empty_query(self, provider):
        q = EmailQuery()
        result = provider._build_outlook_search(q)
        assert result == ""

    def test_from_addr(self, provider):
        q = EmailQuery(from_addr="alice@example.com")
        assert "from:alice@example.com" in provider._build_outlook_search(q)

    def test_to_addr(self, provider):
        q = EmailQuery(to_addr="bob@example.com")
        assert "to:bob@example.com" in provider._build_outlook_search(q)

    def test_subject(self, provider):
        q = EmailQuery(subject="Report")
        assert "subject:Report" in provider._build_outlook_search(q)

    def test_after(self, provider):
        q = EmailQuery(after=date(2024, 3, 15))
        assert "received>=2024-03-15" in provider._build_outlook_search(q)

    def test_before(self, provider):
        q = EmailQuery(before=date(2024, 6, 1))
        assert "received<2024-06-01" in provider._build_outlook_search(q)

    def test_has_attachment_true(self, provider):
        q = EmailQuery(has_attachment=True)
        assert "hasAttachments:true" in provider._build_outlook_search(q)

    def test_has_attachment_false(self, provider):
        q = EmailQuery(has_attachment=False)
        assert "hasAttachments:false" in provider._build_outlook_search(q)

    def test_is_unread_true(self, provider):
        q = EmailQuery(is_unread=True)
        assert "isRead:false" in provider._build_outlook_search(q)

    def test_is_unread_false(self, provider):
        q = EmailQuery(is_unread=False)
        assert "isRead:true" in provider._build_outlook_search(q)

    def test_label(self, provider):
        q = EmailQuery(label="Work")
        assert "category:Work" in provider._build_outlook_search(q)

    def test_text(self, provider):
        q = EmailQuery(text="quarterly report")
        assert '"quarterly report"' in provider._build_outlook_search(q)

    def test_all_fields_combined(self, provider):
        q = EmailQuery(
            text="important",
            from_addr="cfo@corp.com",
            to_addr="team@corp.com",
            subject="Q4",
            after=date(2024, 1, 1),
            before=date(2024, 12, 31),
            has_attachment=True,
            is_unread=True,
            label="finance",
        )
        result = provider._build_outlook_search(q)
        assert "from:cfo@corp.com" in result
        assert "to:team@corp.com" in result
        assert "subject:Q4" in result
        assert "received>=2024-01-01" in result
        assert "received<2024-12-31" in result
        assert "hasAttachments:true" in result
        assert "isRead:false" in result
        assert "category:finance" in result
        assert '"important"' in result


# ---------------------------------------------------------------------------
# _batch_graph_requests
# ---------------------------------------------------------------------------


class TestBatchGraphRequests:
    def test_batch_posts_to_batch_endpoint(self, provider):
        provider._account.con.protocol = MagicMock()
        provider._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"responses": [{"id": "1", "status": 200, "body": {}}]}
        provider._account.con.post = MagicMock(return_value=mock_resp)

        requests = [{"id": "1", "method": "PATCH", "url": "/me/messages/m1"}]
        results = provider._batch_graph_requests(requests)
        assert len(results) == 1

    def test_batch_chunks_at_20(self, provider):
        provider._account.con.protocol = MagicMock()
        provider._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "responses": [{"id": str(i), "status": 200} for i in range(20)]
        }
        provider._account.con.post = MagicMock(return_value=mock_resp)

        requests = [
            {"id": str(i), "method": "PATCH", "url": f"/me/messages/m{i}"} for i in range(25)
        ]
        provider._batch_graph_requests(requests)
        # Should make 2 POST calls (20 + 5)
        assert provider._account.con.post.call_count == 2


# ---------------------------------------------------------------------------
# Sync: get_sync_state / get_new_messages
# ---------------------------------------------------------------------------


class TestSync:
    def test_get_sync_state_returns_delta_link(self, provider):
        provider._account.con.protocol = MagicMock()
        provider._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"
        delta_url = provider._get_inbox_delta_url()
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=xyz"
        provider._account.con._delta_responses[delta_url] = {
            "value": [],
            "@odata.deltaLink": delta_link,
        }

        result = provider.get_sync_state()
        assert result == delta_link

    def test_get_new_messages_returns_ids(self, provider):
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=abc"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=def"
        provider._account.con._delta_responses[delta_link] = {
            "value": [
                {"id": "msg-1"},
                {"id": "msg-2"},
            ],
            "@odata.deltaLink": new_delta,
        }

        result = provider.get_new_messages(delta_link)
        assert result == ["msg-1", "msg-2"]

    def test_get_new_messages_410_gone_returns_none(self, provider):
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=expired"
        gone_resp = MockHttpResponse({})
        gone_resp.status_code = 410
        provider._account.con.get = MagicMock(return_value=gone_resp)

        result = provider.get_new_messages(delta_link)
        assert result is None

    def test_get_new_messages_with_token(self, provider):
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=abc"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=def"
        provider._account.con._delta_responses[delta_link] = {
            "value": [{"id": "msg-1"}],
            "@odata.deltaLink": new_delta,
        }

        result = provider.get_new_messages_with_token(delta_link)
        assert result is not None
        ids, new_link = result
        assert ids == ["msg-1"]
        assert new_link == new_delta


# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------


class TestLazyInit:
    @patch("iobox.providers.o365.auth.get_outlook_account")
    def test_acct_lazy_authenticates(self, mock_get_acct):
        mock_account = make_mock_account()
        mock_get_acct.return_value = mock_account

        p = OutlookProvider()
        assert p._account is None
        # Accessing _acct should trigger authenticate
        acct = p._acct
        assert acct is mock_account
        mock_get_acct.assert_called_once()

    @patch("iobox.providers.o365.auth.get_outlook_account")
    def test_mb_lazy_initializes(self, mock_get_acct):
        mock_account = make_mock_account()
        mock_get_acct.return_value = mock_account

        p = OutlookProvider()
        assert p._mailbox is None
        # Accessing _mb should trigger auth + mailbox init
        mb = p._mb
        assert mb is not None


# ---------------------------------------------------------------------------
# Batch org operations
# ---------------------------------------------------------------------------


def _setup_batch_mock(provider: OutlookProvider) -> MagicMock:
    """Wire provider.con.post to return a successful batch response stub.

    Returns the ``MagicMock`` replacing ``provider._account.con.post`` so
    callers can assert on ``call_count`` and ``call_args``.
    """
    provider._account.con.protocol = MagicMock()
    provider._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"responses": [{"id": "0", "status": 200, "body": {}}]}
    mock_post = MagicMock(return_value=mock_resp)
    provider._account.con.post = mock_post
    return mock_post


class TestBatchMarkRead:
    def test_calls_batch_endpoint_once_for_two_messages(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg1 = make_mock_message(object_id="batch-read-id-1")
        msg2 = make_mock_message(object_id="batch-read-id-2")
        provider._mailbox._messages_by_id["batch-read-id-1"] = msg1
        provider._mailbox._messages_by_id["batch-read-id-2"] = msg2
        provider.batch_mark_read(["batch-read-id-1", "batch-read-id-2"], read=True)
        assert mock_post.call_count == 1

    def test_uses_relative_url_and_patch_method(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-read-id-3")
        provider._mailbox._messages_by_id["batch-read-id-3"] = msg
        provider.batch_mark_read(["batch-read-id-3"], read=False)
        payload = mock_post.call_args[1]["data"]
        sub_req = payload["requests"][0]
        assert sub_req["url"] == "/me/messages/batch-read-id-3"
        assert sub_req["method"] == "PATCH"
        assert sub_req["body"]["isRead"] is False

    def test_read_true_sets_is_read_true(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-read-id-4")
        provider._mailbox._messages_by_id["batch-read-id-4"] = msg
        provider.batch_mark_read(["batch-read-id-4"], read=True)
        payload = mock_post.call_args[1]["data"]
        assert payload["requests"][0]["body"]["isRead"] is True

    def test_empty_list_does_not_call_batch(self, provider):
        mock_post = _setup_batch_mock(provider)
        provider.batch_mark_read([])
        assert mock_post.call_count == 0

    def test_chunks_at_20(self, provider):
        """21 messages should result in 2 batch POST calls (20 + 1)."""
        mock_post = _setup_batch_mock(provider)
        msg_ids = [f"fake-read-id-{i}" for i in range(21)]
        provider.batch_mark_read(msg_ids, read=True)
        assert mock_post.call_count == 2


class TestBatchArchive:
    def test_calls_batch_endpoint_once_for_two_messages(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg1 = make_mock_message(object_id="batch-arch-id-1")
        msg2 = make_mock_message(object_id="batch-arch-id-2")
        provider._mailbox._messages_by_id["batch-arch-id-1"] = msg1
        provider._mailbox._messages_by_id["batch-arch-id-2"] = msg2
        provider.batch_archive(["batch-arch-id-1", "batch-arch-id-2"])
        assert mock_post.call_count == 1

    def test_uses_move_url_with_archive_destination(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-arch-id-3")
        provider._mailbox._messages_by_id["batch-arch-id-3"] = msg
        provider.batch_archive(["batch-arch-id-3"])
        payload = mock_post.call_args[1]["data"]
        sub_req = payload["requests"][0]
        assert sub_req["url"] == "/me/messages/batch-arch-id-3/move"
        assert sub_req["method"] == "POST"
        assert sub_req["body"]["destinationId"] == "archive"

    def test_url_is_relative_not_absolute(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-arch-id-4")
        provider._mailbox._messages_by_id["batch-arch-id-4"] = msg
        provider.batch_archive(["batch-arch-id-4"])
        payload = mock_post.call_args[1]["data"]
        url = payload["requests"][0]["url"]
        assert not url.startswith("http"), f"URL must be relative, got: {url!r}"

    def test_empty_list_does_not_call_batch(self, provider):
        mock_post = _setup_batch_mock(provider)
        provider.batch_archive([])
        assert mock_post.call_count == 0

    def test_chunks_at_20(self, provider):
        """21 messages → 2 POST calls (20 + 1)."""
        mock_post = _setup_batch_mock(provider)
        msg_ids = [f"fake-arch-id-{i}" for i in range(21)]
        provider.batch_archive(msg_ids)
        assert mock_post.call_count == 2


class TestBatchTrash:
    def test_calls_batch_endpoint_once_for_two_messages(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg1 = make_mock_message(object_id="batch-trash-id-1")
        msg2 = make_mock_message(object_id="batch-trash-id-2")
        provider._mailbox._messages_by_id["batch-trash-id-1"] = msg1
        provider._mailbox._messages_by_id["batch-trash-id-2"] = msg2
        provider.batch_trash(["batch-trash-id-1", "batch-trash-id-2"])
        assert mock_post.call_count == 1

    def test_uses_move_url_with_deleteditems_destination(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-trash-id-3")
        provider._mailbox._messages_by_id["batch-trash-id-3"] = msg
        provider.batch_trash(["batch-trash-id-3"])
        payload = mock_post.call_args[1]["data"]
        sub_req = payload["requests"][0]
        assert sub_req["url"] == "/me/messages/batch-trash-id-3/move"
        assert sub_req["method"] == "POST"
        assert sub_req["body"]["destinationId"] == "deleteditems"

    def test_url_is_relative_not_absolute(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-trash-id-4")
        provider._mailbox._messages_by_id["batch-trash-id-4"] = msg
        provider.batch_trash(["batch-trash-id-4"])
        payload = mock_post.call_args[1]["data"]
        url = payload["requests"][0]["url"]
        assert not url.startswith("http"), f"URL must be relative, got: {url!r}"

    def test_empty_list_does_not_call_batch(self, provider):
        mock_post = _setup_batch_mock(provider)
        provider.batch_trash([])
        assert mock_post.call_count == 0


class TestBatchAddTag:
    def test_calls_batch_endpoint_once_for_two_messages(self, provider):
        """Two messages without the tag → one $batch call with two sub-requests."""
        mock_post = _setup_batch_mock(provider)
        msg1 = make_mock_message(object_id="batch-addtag-id-1", categories=["Work"])
        msg2 = make_mock_message(object_id="batch-addtag-id-2", categories=[])
        provider._mailbox._messages_by_id["batch-addtag-id-1"] = msg1
        provider._mailbox._messages_by_id["batch-addtag-id-2"] = msg2
        provider.batch_add_tag(["batch-addtag-id-1", "batch-addtag-id-2"], "ProjectX")
        assert mock_post.call_count == 1

    def test_includes_new_tag_and_preserves_existing(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-addtag-id-3", categories=["Work"])
        provider._mailbox._messages_by_id["batch-addtag-id-3"] = msg
        provider.batch_add_tag(["batch-addtag-id-3"], "ProjectX")
        payload = mock_post.call_args[1]["data"]
        cats = payload["requests"][0]["body"]["categories"]
        assert "ProjectX" in cats
        assert "Work" in cats  # existing tag preserved

    def test_skips_already_tagged_message(self, provider):
        """If tag already present the message is excluded from the batch."""
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-addtag-id-4", categories=["Work"])
        provider._mailbox._messages_by_id["batch-addtag-id-4"] = msg
        provider.batch_add_tag(["batch-addtag-id-4"], "Work")
        assert mock_post.call_count == 0

    def test_skips_missing_message(self, provider):
        mock_post = _setup_batch_mock(provider)
        provider.batch_add_tag(["nonexistent-batch-add-id"], "Tag")
        assert mock_post.call_count == 0

    def test_uses_relative_url(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-addtag-id-5", categories=[])
        provider._mailbox._messages_by_id["batch-addtag-id-5"] = msg
        provider.batch_add_tag(["batch-addtag-id-5"], "NewTag")
        payload = mock_post.call_args[1]["data"]
        url = payload["requests"][0]["url"]
        assert url == "/me/messages/batch-addtag-id-5"
        assert not url.startswith("http"), f"URL must be relative, got: {url!r}"


class TestBatchRemoveTag:
    def test_calls_batch_endpoint_once_for_tagged_messages(self, provider):
        """Two messages with the tag → one $batch call."""
        mock_post = _setup_batch_mock(provider)
        msg1 = make_mock_message(object_id="batch-rmtag-id-1", categories=["Work"])
        msg2 = make_mock_message(object_id="batch-rmtag-id-2", categories=["Work", "Important"])
        provider._mailbox._messages_by_id["batch-rmtag-id-1"] = msg1
        provider._mailbox._messages_by_id["batch-rmtag-id-2"] = msg2
        provider.batch_remove_tag(["batch-rmtag-id-1", "batch-rmtag-id-2"], "Work")
        assert mock_post.call_count == 1

    def test_removes_tag_from_categories(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-rmtag-id-3", categories=["Work", "Important"])
        provider._mailbox._messages_by_id["batch-rmtag-id-3"] = msg
        provider.batch_remove_tag(["batch-rmtag-id-3"], "Work")
        payload = mock_post.call_args[1]["data"]
        cats = payload["requests"][0]["body"]["categories"]
        assert "Work" not in cats
        assert "Important" in cats  # unrelated tag preserved

    def test_skips_message_without_tag(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-rmtag-id-4", categories=[])
        provider._mailbox._messages_by_id["batch-rmtag-id-4"] = msg
        provider.batch_remove_tag(["batch-rmtag-id-4"], "Work")
        assert mock_post.call_count == 0

    def test_skips_missing_message(self, provider):
        mock_post = _setup_batch_mock(provider)
        provider.batch_remove_tag(["nonexistent-batch-rm-id"], "Tag")
        assert mock_post.call_count == 0

    def test_uses_relative_url(self, provider):
        mock_post = _setup_batch_mock(provider)
        msg = make_mock_message(object_id="batch-rmtag-id-5", categories=["Work"])
        provider._mailbox._messages_by_id["batch-rmtag-id-5"] = msg
        provider.batch_remove_tag(["batch-rmtag-id-5"], "Work")
        payload = mock_post.call_args[1]["data"]
        url = payload["requests"][0]["url"]
        assert url == "/me/messages/batch-rmtag-id-5"
        assert not url.startswith("http"), f"URL must be relative, got: {url!r}"


class TestBatchOrgDefaultLoop:
    """Verify that the ABC's default batch methods loop over single-message calls."""

    def test_base_batch_mark_read_loops(self, provider):
        """Default batch_mark_read in ABC must call mark_read for each ID."""
        called: list[tuple[str, bool]] = []
        original = provider.mark_read

        def recording_mark_read(message_id: str, read: bool = True) -> None:
            called.append((message_id, read))
            original(message_id, read=read)

        provider.mark_read = recording_mark_read  # type: ignore[method-assign]

        # Call the ABC's default (non-overridden) loop via the base class directly.
        from iobox.providers.base import EmailProvider

        ids = ["outlook-msg-id-1", "outlook-msg-id-2"]
        EmailProvider.batch_mark_read(provider, ids, read=False)
        assert called == [("outlook-msg-id-1", False), ("outlook-msg-id-2", False)]

    def test_base_batch_archive_loops(self, provider):
        called: list[str] = []
        original = provider.archive

        def recording_archive(message_id: str) -> None:
            called.append(message_id)
            original(message_id)

        provider.archive = recording_archive  # type: ignore[method-assign]

        from iobox.providers.base import EmailProvider

        EmailProvider.batch_archive(provider, ["outlook-msg-id-1", "outlook-msg-id-2"])
        assert called == ["outlook-msg-id-1", "outlook-msg-id-2"]
