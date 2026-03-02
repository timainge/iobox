"""
Unit tests for the email_retrieval module.

Verifies that the canonical imports work and that functions
behave identically whether imported from email_retrieval or email_search.
"""

import pytest
from unittest.mock import MagicMock, patch
import base64

import iobox.email_retrieval as er
from iobox.email_retrieval import (
    get_email_content,
    get_label_map,
    download_attachment,
    get_thread_content,
    modify_message_labels,
    resolve_label_name,
    batch_modify_labels,
    trash_message,
    untrash_message,
    batch_get_emails,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(msg_id, subject, sender, date, internal_date, body_b64):
    """Build a minimal Gmail API message dict."""
    return {
        "id": msg_id,
        "threadId": "thread-123",
        "labelIds": ["INBOX"],
        "snippet": "snippet",
        "internalDate": str(internal_date),
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date},
            ],
            "body": {"data": body_b64, "size": len(body_b64)},
        },
    }


class TestGetThreadContent:
    """Tests for get_thread_content()."""

    def test_get_thread_content_returns_ordered_messages(self, mock_gmail_service):
        """Three messages returned in chronological order."""
        body_b64 = base64.urlsafe_b64encode(b"Hello").decode()
        messages = [
            _make_message("msg-3", "Re: Hi", "c@example.com", "Wed", 3000, body_b64),
            _make_message("msg-1", "Hi", "a@example.com", "Mon", 1000, body_b64),
            _make_message("msg-2", "Re: Hi", "b@example.com", "Tue", 2000, body_b64),
        ]
        mock_get = MagicMock()
        mock_get.execute.return_value = {"messages": messages}
        mock_gmail_service.users().threads().get.return_value = mock_get

        result = get_thread_content(mock_gmail_service, "thread-123")

        assert len(result) == 3
        # Sorted by internalDate
        assert result[0]["message_id"] == "msg-1"
        assert result[1]["message_id"] == "msg-2"
        assert result[2]["message_id"] == "msg-3"

    def test_get_thread_content_has_required_fields(self, mock_gmail_service):
        """Each message dict has the required keys."""
        body_b64 = base64.urlsafe_b64encode(b"body").decode()
        messages = [
            _make_message("msg-1", "Subject", "sender@example.com", "Mon", 1000, body_b64),
        ]
        mock_get = MagicMock()
        mock_get.execute.return_value = {"messages": messages}
        mock_gmail_service.users().threads().get.return_value = mock_get

        result = get_thread_content(mock_gmail_service, "thread-123")
        msg = result[0]

        for key in ("message_id", "thread_id", "subject", "from", "to", "date", "labels", "body"):
            assert key in msg, f"Missing key: {key}"

    def test_get_thread_content_empty_thread(self, mock_gmail_service):
        """Empty message list returns empty list."""
        mock_get = MagicMock()
        mock_get.execute.return_value = {"messages": []}
        mock_gmail_service.users().threads().get.return_value = mock_get

        result = get_thread_content(mock_gmail_service, "thread-123")

        assert result == []


class TestModifyMessageLabels:
    """Tests for modify_message_labels()."""

    def test_modify_message_labels_add(self, mock_gmail_service):
        """add_labels is passed in addLabelIds."""
        mock_modify = MagicMock()
        mock_modify.execute.return_value = {"id": "msg-1"}
        mock_gmail_service.users().messages().modify.return_value = mock_modify

        modify_message_labels(mock_gmail_service, "msg-1", add_labels=["STARRED"])

        mock_gmail_service.users().messages().modify.assert_called_once_with(
            userId='me', id='msg-1', body={'addLabelIds': ['STARRED']}
        )

    def test_modify_message_labels_remove(self, mock_gmail_service):
        """remove_labels is passed in removeLabelIds."""
        mock_modify = MagicMock()
        mock_modify.execute.return_value = {"id": "msg-1"}
        mock_gmail_service.users().messages().modify.return_value = mock_modify

        modify_message_labels(mock_gmail_service, "msg-1", remove_labels=["UNREAD"])

        mock_gmail_service.users().messages().modify.assert_called_once_with(
            userId='me', id='msg-1', body={'removeLabelIds': ['UNREAD']}
        )

    def test_modify_message_labels_both(self, mock_gmail_service):
        """Both add and remove labels are passed correctly."""
        mock_modify = MagicMock()
        mock_modify.execute.return_value = {"id": "msg-1"}
        mock_gmail_service.users().messages().modify.return_value = mock_modify

        modify_message_labels(mock_gmail_service, "msg-1",
                              add_labels=["STARRED"], remove_labels=["UNREAD"])

        call_body = mock_gmail_service.users().messages().modify.call_args[1]['body']
        assert call_body['addLabelIds'] == ['STARRED']
        assert call_body['removeLabelIds'] == ['UNREAD']


class TestResolveLabelName:
    """Tests for resolve_label_name()."""

    def test_resolve_label_name_system(self, mock_gmail_service):
        """System labels are returned as-is (uppercased)."""
        for name in ('inbox', 'INBOX', 'UNREAD', 'STARRED', 'TRASH'):
            result = resolve_label_name(mock_gmail_service, name)
            assert result == name.upper()

    def test_resolve_label_name_category(self, mock_gmail_service):
        """CATEGORY_* labels are returned uppercased."""
        result = resolve_label_name(mock_gmail_service, 'category_personal')
        assert result == 'CATEGORY_PERSONAL'

    def test_resolve_label_name_custom(self, mock_gmail_service, mocker):
        """Custom label names are resolved via the label map."""
        mocker.patch.dict(er._label_cache, {"Label_12345": "Newsletter"}, clear=True)

        result = resolve_label_name(mock_gmail_service, "Newsletter")

        assert result == "Label_12345"

    def test_resolve_label_name_not_found(self, mock_gmail_service, mocker):
        """Unknown label name raises ValueError."""
        mocker.patch.dict(er._label_cache, {}, clear=True)
        mock_labels = MagicMock()
        mock_labels.execute.return_value = {"labels": []}
        mock_gmail_service.users().labels().list.return_value = mock_labels

        with pytest.raises(ValueError, match="not found"):
            resolve_label_name(mock_gmail_service, "NonExistent")


class TestBatchModifyLabels:
    """Tests for batch_modify_labels()."""

    def test_batch_modify_single_chunk(self, mock_gmail_service):
        """Fewer than 1000 messages → one batchModify call."""
        mock_batch = MagicMock()
        mock_batch.execute.return_value = None
        mock_gmail_service.users().messages().batchModify.return_value = mock_batch

        ids = [f"msg-{i}" for i in range(5)]
        result = batch_modify_labels(mock_gmail_service, ids, add_labels=["STARRED"])

        mock_gmail_service.users().messages().batchModify.assert_called_once()
        assert result == {"modified_count": 5}

    def test_batch_modify_multiple_chunks(self, mock_gmail_service):
        """More than 1000 messages → multiple batchModify calls."""
        mock_batch = MagicMock()
        mock_batch.execute.return_value = None
        mock_gmail_service.users().messages().batchModify.return_value = mock_batch

        ids = [f"msg-{i}" for i in range(1500)]
        result = batch_modify_labels(mock_gmail_service, ids, remove_labels=["UNREAD"])

        assert mock_gmail_service.users().messages().batchModify.call_count == 2
        assert result == {"modified_count": 1500}


class TestTrashUntrash:
    """Tests for trash_message() and untrash_message()."""

    def test_trash_message(self, mock_gmail_service):
        """trash_message calls messages.trash with correct args."""
        mock_trash = MagicMock()
        mock_trash.execute.return_value = {"id": "msg-1", "labelIds": ["TRASH"]}
        mock_gmail_service.users().messages().trash.return_value = mock_trash

        result = trash_message(mock_gmail_service, "msg-1")

        mock_gmail_service.users().messages().trash.assert_called_once_with(userId='me', id='msg-1')
        assert result["id"] == "msg-1"

    def test_untrash_message(self, mock_gmail_service):
        """untrash_message calls messages.untrash with correct args."""
        mock_untrash = MagicMock()
        mock_untrash.execute.return_value = {"id": "msg-1", "labelIds": ["INBOX"]}
        mock_gmail_service.users().messages().untrash.return_value = mock_untrash

        result = untrash_message(mock_gmail_service, "msg-1")

        mock_gmail_service.users().messages().untrash.assert_called_once_with(userId='me', id='msg-1')
        assert result["id"] == "msg-1"


def _make_full_message(msg_id, subject="Subject", sender="a@b.com"):
    """Build a minimal full-format Gmail API message for batch tests."""
    body_b64 = base64.urlsafe_b64encode(b"Hello world").decode()
    return {
        "id": msg_id,
        "threadId": f"thread-{msg_id}",
        "labelIds": ["INBOX"],
        "snippet": "snippet",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 01 Jan 2024 00:00:00 +0000"},
            ],
            "body": {"data": body_b64, "size": 11},
        },
    }


class TestBatchGetEmails:
    """Tests for batch_get_emails()."""

    def test_batch_get_emails_all_succeed(self, mock_gmail_service):
        """All messages in a batch are processed and returned in order."""
        msg_ids = ["msg1", "msg2", "msg3"]
        responses = {mid: _make_full_message(mid) for mid in msg_ids}

        mock_batch = MagicMock()
        mock_gmail_service.new_batch_http_request.return_value = mock_batch

        def fake_execute():
            callback = mock_gmail_service.new_batch_http_request.call_args[1]['callback']
            for req_id, resp in responses.items():
                callback(req_id, resp, None)

        mock_batch.execute.side_effect = fake_execute

        result = batch_get_emails(mock_gmail_service, msg_ids)

        assert len(result) == 3
        assert result[0]['message_id'] == 'msg1'
        assert result[1]['message_id'] == 'msg2'
        assert result[2]['message_id'] == 'msg3'
        # No error keys
        for item in result:
            assert 'error' not in item

    def test_batch_get_emails_partial_failure(self, mock_gmail_service):
        """Failed messages appear with 'error' key; successful ones are processed normally."""
        msg_ids = ["msg1", "msg2", "msg3", "msg4", "msg5"]
        responses = {
            "msg1": _make_full_message("msg1"),
            "msg3": _make_full_message("msg3"),
            "msg4": _make_full_message("msg4"),
        }
        # msg2 and msg5 will fail
        error_ids = {"msg2": Exception("API error for msg2"), "msg5": Exception("API error for msg5")}

        mock_batch = MagicMock()
        mock_gmail_service.new_batch_http_request.return_value = mock_batch

        def fake_execute():
            callback = mock_gmail_service.new_batch_http_request.call_args[1]['callback']
            for req_id, resp in responses.items():
                callback(req_id, resp, None)
            for req_id, exc in error_ids.items():
                callback(req_id, None, exc)

        mock_batch.execute.side_effect = fake_execute

        result = batch_get_emails(mock_gmail_service, msg_ids)

        assert len(result) == 5
        # Check order
        assert result[0]['message_id'] == 'msg1'
        assert 'error' not in result[0]

        assert result[1]['message_id'] == 'msg2'
        assert 'error' in result[1]

        assert result[2]['message_id'] == 'msg3'
        assert 'error' not in result[2]

        assert result[3]['message_id'] == 'msg4'
        assert 'error' not in result[3]

        assert result[4]['message_id'] == 'msg5'
        assert 'error' in result[4]

    def test_batch_get_emails_chunks_of_50(self, mock_gmail_service):
        """More than 50 message IDs triggers multiple batch executions."""
        msg_ids = [f"msg-{i}" for i in range(75)]
        responses = {mid: _make_full_message(mid) for mid in msg_ids}

        # Track how many batches were created
        batches_created = []

        def make_mock_batch(*args, **kwargs):
            mock_batch = MagicMock()
            callback = kwargs.get('callback')
            # Track which IDs are added to this batch
            ids_in_batch = []
            original_add = mock_batch.add

            def track_add(request, request_id=None):
                ids_in_batch.append(request_id)

            mock_batch.add.side_effect = track_add

            def fake_execute():
                for mid in ids_in_batch:
                    if mid in responses:
                        callback(mid, responses[mid], None)

            mock_batch.execute.side_effect = fake_execute
            batches_created.append(mock_batch)
            return mock_batch

        mock_gmail_service.new_batch_http_request.side_effect = make_mock_batch

        result = batch_get_emails(mock_gmail_service, msg_ids)

        # Should have created 2 batches (50 + 25)
        assert mock_gmail_service.new_batch_http_request.call_count == 2
        assert len(result) == 75
        assert all('error' not in item for item in result)
