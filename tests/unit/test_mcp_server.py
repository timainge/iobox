"""Tests for MCP server tools."""

import sys
from unittest.mock import MagicMock, patch

# Mock FastMCP so tests work without mcp package installed
mock_fastmcp_module = MagicMock()
mock_mcp_instance = MagicMock()
mock_mcp_instance.tool.return_value = lambda fn: fn  # decorator passes through
mock_fastmcp_module.FastMCP.return_value = mock_mcp_instance
sys.modules["mcp"] = MagicMock()
sys.modules["mcp.server"] = MagicMock()
sys.modules["mcp.server.fastmcp"] = mock_fastmcp_module

from iobox.mcp_server import (  # noqa: E402
    batch_forward_gmail,
    batch_modify_gmail_labels,
    batch_trash_gmail,
    check_auth,
    create_gmail_draft,
    delete_gmail_draft,
    forward_gmail,
    get_email,
    list_gmail_drafts,
    modify_labels,
    save_email,
    save_emails_by_query,
    save_thread,
    search_gmail,
    send_email,
    send_gmail_draft,
    trash_gmail,
    untrash_gmail,
)

MODULE = "iobox.mcp_server"


# ---------------------------------------------------------------------------
# Search & Read
# ---------------------------------------------------------------------------


class TestSearchGmail:
    def test_basic_search(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[{"message_id": "m1"}]) as mock_search,
        ):
            mock_svc.return_value = MagicMock()
            result = search_gmail("from:test@example.com", max_results=5, days=3)
            assert result == [{"message_id": "m1"}]
            mock_search.assert_called_once_with(
                mock_svc.return_value,
                "from:test@example.com",
                5,
                3,
                None,
                None,
                label_map={},
                include_spam_trash=False,
            )

    def test_search_with_dates(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[]) as mock_search,
        ):
            mock_svc.return_value = MagicMock()
            result = search_gmail(
                "subject:report",
                max_results=20,
                days=0,
                start_date="2024/01/01",
                end_date="2024/01/31",
            )
            assert result == []
            mock_search.assert_called_once()

    def test_search_include_spam_trash(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[]) as mock_search,
        ):
            mock_svc.return_value = MagicMock()
            search_gmail("in:anywhere", include_spam_trash=True)
            _, kwargs = mock_search.call_args
            assert kwargs["include_spam_trash"] is True


class TestGetEmail:
    def test_get_email_html(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(
                f"{MODULE}.get_email_content", return_value={"message_id": "m1", "subject": "Test"}
            ) as mock_get,
        ):
            mock_svc.return_value = MagicMock()
            result = get_email("m1")
            assert result["subject"] == "Test"
            mock_get.assert_called_once_with(
                mock_svc.return_value, "m1", preferred_content_type="text/html", label_map={}
            )

    def test_get_email_plain(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.get_email_content", return_value={"message_id": "m1"}) as mock_get,
        ):
            mock_svc.return_value = MagicMock()
            get_email("m1", prefer_html=False)
            mock_get.assert_called_once_with(
                mock_svc.return_value, "m1", preferred_content_type="text/plain", label_map={}
            )


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


class TestSaveEmail:
    def test_save_single(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.get_email_content", return_value={"message_id": "m1"}),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            mock_svc.return_value = MagicMock()
            result = save_email("m1", output_dir="/tmp/out")
            assert result == "/tmp/out/email.md"

    def test_save_plain_text(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.get_email_content", return_value={"message_id": "m2"}) as mock_get,
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            mock_svc.return_value = MagicMock()
            save_email("m2", output_dir="/tmp/out", prefer_html=False)
            mock_get.assert_called_once_with(
                mock_svc.return_value, "m2", preferred_content_type="text/plain", label_map={}
            )

    def test_save_with_attachments(self):
        email_data = {"message_id": "m3", "attachments": [{"filename": "f.pdf"}]}
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.get_email_content", return_value=email_data),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
            patch(f"{MODULE}.download_email_attachments") as mock_dl,
        ):
            mock_svc.return_value = MagicMock()
            save_email("m3", download_attachments=True, attachment_types="pdf,docx")
            mock_dl.assert_called_once()
            _, kwargs = mock_dl.call_args
            assert kwargs["attachment_filters"] == ["pdf", "docx"]


class TestSaveThread:
    def test_save_thread(self):
        messages = [{"subject": "Thread Subject", "message_id": "m1"}]
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_thread_content", return_value=messages),
            patch(f"{MODULE}.convert_thread_to_markdown", return_value="# Thread"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch("builtins.open", MagicMock()),
        ):
            mock_svc.return_value = MagicMock()
            result = save_thread("t1", output_dir="/tmp/out")
            assert "t1" in result
            assert result.endswith(".md")


class TestSaveEmailsByQuery:
    def test_no_results(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[]),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
        ):
            mock_svc.return_value = MagicMock()
            result = save_emails_by_query("from:nobody@example.com")
            assert result["saved_count"] == 0

    def test_batch_save(self):
        search_results = [{"message_id": "m1"}, {"message_id": "m2"}]
        email_batch = [{"message_id": "m1", "subject": "A"}, {"message_id": "m2", "subject": "B"}]
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=search_results),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.check_for_duplicates", return_value=[]),
            patch(f"{MODULE}.batch_get_emails", return_value=email_batch),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            mock_svc.return_value = MagicMock()
            result = save_emails_by_query("in:inbox", max_results=2)
            assert result["saved_count"] == 2
            assert result["skipped_count"] == 0

    def test_batch_save_with_duplicates(self):
        search_results = [{"message_id": "m1"}, {"message_id": "m2"}]
        email_batch = [{"message_id": "m2", "subject": "B"}]
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=search_results),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.check_for_duplicates", return_value=["m1"]),
            patch(f"{MODULE}.batch_get_emails", return_value=email_batch),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            mock_svc.return_value = MagicMock()
            result = save_emails_by_query("in:inbox")
            assert result["saved_count"] == 1
            assert result["skipped_count"] == 1


# ---------------------------------------------------------------------------
# Send & Forward
# ---------------------------------------------------------------------------


class TestSendEmail:
    def test_send_plain(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose,
            patch(f"{MODULE}.send_message", return_value={"id": "sent-1"}),
        ):
            mock_svc.return_value = MagicMock()
            result = send_email("bob@example.com", "Hello", "Body text")
            assert result["id"] == "sent-1"
            mock_compose.assert_called_once_with(
                to="bob@example.com",
                subject="Hello",
                body="Body text",
                cc=None,
                bcc=None,
                content_type="plain",
                attachments=None,
            )

    def test_send_html(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose,
            patch(f"{MODULE}.send_message", return_value={"id": "sent-2"}),
        ):
            mock_svc.return_value = MagicMock()
            send_email("bob@example.com", "Hi", "<b>Bold</b>", html=True)
            _, kwargs = mock_compose.call_args
            assert kwargs["content_type"] == "html"

    def test_send_with_cc_bcc(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose,
            patch(f"{MODULE}.send_message", return_value={"id": "sent-3"}),
        ):
            mock_svc.return_value = MagicMock()
            send_email("bob@example.com", "Hi", "Body", cc="cc@example.com", bcc="bcc@example.com")
            mock_compose.assert_called_once_with(
                to="bob@example.com",
                subject="Hi",
                body="Body",
                cc="cc@example.com",
                bcc="bcc@example.com",
                content_type="plain",
                attachments=None,
            )

    def test_send_with_attachments(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose,
            patch(f"{MODULE}.send_message", return_value={"id": "sent-4"}),
            patch("pathlib.Path.exists", return_value=True),
        ):
            mock_svc.return_value = MagicMock()
            send_email("bob@example.com", "Hi", "See attached", attachments=["/tmp/f.txt"])
            _, kwargs = mock_compose.call_args
            assert kwargs["attachments"] == ["/tmp/f.txt"]


class TestForwardGmail:
    def test_forward(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.forward_email", return_value={"id": "fwd-1"}) as mock_fwd,
        ):
            mock_svc.return_value = MagicMock()
            result = forward_gmail("m1", "bob@example.com", note="FYI")
            assert result["id"] == "fwd-1"
            mock_fwd.assert_called_once_with(
                mock_svc.return_value, message_id="m1", to="bob@example.com", additional_text="FYI"
            )

    def test_forward_no_note(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.forward_email", return_value={"id": "fwd-2"}),
        ):
            mock_svc.return_value = MagicMock()
            result = forward_gmail("m2", "alice@example.com")
            assert result["id"] == "fwd-2"


class TestBatchForwardGmail:
    def test_batch_forward(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(
                f"{MODULE}.search_emails", return_value=[{"message_id": "m1"}, {"message_id": "m2"}]
            ),
            patch(f"{MODULE}.forward_email", return_value={"id": "fwd-1"}) as mock_fwd,
        ):
            mock_svc.return_value = MagicMock()
            result = batch_forward_gmail("from:test@example.com", "bob@example.com", note="FYI")
            assert result["forwarded_count"] == 2
            assert mock_fwd.call_count == 2

    def test_batch_forward_no_results(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[]),
        ):
            mock_svc.return_value = MagicMock()
            result = batch_forward_gmail("from:nobody@example.com", "bob@example.com")
            assert result["forwarded_count"] == 0

    def test_batch_forward_with_dates(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[{"message_id": "m1"}]) as mock_search,
            patch(f"{MODULE}.forward_email", return_value={"id": "fwd-1"}),
        ):
            mock_svc.return_value = MagicMock()
            result = batch_forward_gmail(
                "subject:report",
                "bob@example.com",
                start_date="2024/01/01",
                end_date="2024/01/31",
            )
            assert result["forwarded_count"] == 1
            mock_search.assert_called_once_with(
                mock_svc.return_value,
                "subject:report",
                10,
                7,
                "2024/01/01",
                "2024/01/31",
                label_map={},
            )


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


class TestDrafts:
    def test_create_draft(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.compose_message", return_value={"raw": "dGVzdA=="}),
            patch(f"{MODULE}.create_draft", return_value={"id": "d1"}) as mock_create,
        ):
            mock_svc.return_value = MagicMock()
            result = create_gmail_draft("bob@example.com", "Draft Subject", "Body")
            assert result["id"] == "d1"
            mock_create.assert_called_once()

    def test_create_draft_html(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose,
            patch(f"{MODULE}.create_draft", return_value={"id": "d2"}),
        ):
            mock_svc.return_value = MagicMock()
            create_gmail_draft("bob@example.com", "HTML Draft", "<b>Bold</b>", html=True)
            _, kwargs = mock_compose.call_args
            assert kwargs["content_type"] == "html"

    def test_list_drafts(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(
                f"{MODULE}.list_drafts", return_value=[{"id": "d1", "subject": "Test"}]
            ) as mock_list,
        ):
            mock_svc.return_value = MagicMock()
            result = list_gmail_drafts(max_results=5)
            assert len(result) == 1
            mock_list.assert_called_once_with(mock_svc.return_value, max_results=5)

    def test_send_draft(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.send_draft", return_value={"id": "sent-d1"}) as mock_send,
        ):
            mock_svc.return_value = MagicMock()
            result = send_gmail_draft("d1")
            assert result["id"] == "sent-d1"
            mock_send.assert_called_once_with(mock_svc.return_value, "d1")

    def test_delete_draft(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(
                f"{MODULE}.delete_draft", return_value={"status": "deleted", "draft_id": "d1"}
            ) as mock_del,
        ):
            mock_svc.return_value = MagicMock()
            result = delete_gmail_draft("d1")
            assert result["draft_id"] == "d1"
            mock_del.assert_called_once_with(mock_svc.return_value, "d1")


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_modify_labels_star(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.modify_message_labels", return_value={"id": "m1"}) as mock_mod,
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", star=True)
            mock_mod.assert_called_once_with(mock_svc.return_value, "m1", ["STARRED"], None)

    def test_modify_labels_mark_read(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.modify_message_labels", return_value={"id": "m1"}) as mock_mod,
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", mark_read=True)
            mock_mod.assert_called_once_with(mock_svc.return_value, "m1", None, ["UNREAD"])

    def test_modify_labels_archive(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.modify_message_labels", return_value={"id": "m1"}) as mock_mod,
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", archive=True)
            mock_mod.assert_called_once_with(mock_svc.return_value, "m1", None, ["INBOX"])

    def test_modify_labels_custom(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.resolve_label_name", return_value="Label_123"),
            patch(f"{MODULE}.modify_message_labels", return_value={"id": "m1"}) as mock_mod,
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", add_label="MyLabel")
            mock_mod.assert_called_once_with(mock_svc.return_value, "m1", ["Label_123"], None)

    def test_batch_modify_labels(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(
                f"{MODULE}.search_emails", return_value=[{"message_id": "m1"}, {"message_id": "m2"}]
            ),
            patch(f"{MODULE}.batch_modify_labels") as mock_batch,
        ):
            mock_svc.return_value = MagicMock()
            result = batch_modify_gmail_labels("in:inbox", star=True)
            assert result["modified_count"] == 2
            mock_batch.assert_called_once()

    def test_batch_modify_no_results(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[]),
        ):
            mock_svc.return_value = MagicMock()
            result = batch_modify_gmail_labels("from:nobody@example.com", mark_read=True)
            assert result["modified_count"] == 0


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


class TestTrash:
    def test_trash(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.trash_message", return_value={"id": "m1"}) as mock_trash,
        ):
            mock_svc.return_value = MagicMock()
            result = trash_gmail("m1")
            assert result["id"] == "m1"
            mock_trash.assert_called_once_with(mock_svc.return_value, "m1")

    def test_untrash(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.untrash_message", return_value={"id": "m1"}) as mock_untrash,
        ):
            mock_svc.return_value = MagicMock()
            result = untrash_gmail("m1")
            assert result["id"] == "m1"
            mock_untrash.assert_called_once_with(mock_svc.return_value, "m1")


class TestBatchTrashGmail:
    def test_batch_trash(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(
                f"{MODULE}.search_emails", return_value=[{"message_id": "m1"}, {"message_id": "m2"}]
            ),
            patch(f"{MODULE}.trash_message", return_value={"id": "m1"}) as mock_trash,
        ):
            mock_svc.return_value = MagicMock()
            result = batch_trash_gmail("from:spam@example.com", max_results=5, days=30)
            assert result["trashed_count"] == 2
            assert mock_trash.call_count == 2

    def test_batch_trash_no_results(self):
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.get_label_map", return_value={}),
            patch(f"{MODULE}.search_emails", return_value=[]),
        ):
            mock_svc.return_value = MagicMock()
            result = batch_trash_gmail("from:nobody@example.com")
            assert result["trashed_count"] == 0


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestCheckAuth:
    def test_check_auth_with_profile(self):
        with (
            patch(f"{MODULE}.check_auth_status", return_value={"authenticated": True}),
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(
                f"{MODULE}.get_gmail_profile",
                return_value={
                    "emailAddress": "user@gmail.com",
                    "messagesTotal": 100,
                    "threadsTotal": 50,
                },
            ),
        ):
            mock_svc.return_value = MagicMock()
            result = check_auth()
            assert result["authenticated"] is True
            assert result["email"] == "user@gmail.com"
            assert result["messages_total"] == 100
            assert result["threads_total"] == 50

    def test_check_auth_not_authenticated(self):
        with (
            patch(
                f"{MODULE}.check_auth_status",
                return_value={"authenticated": False, "token_file_exists": False},
            ),
            patch(f"{MODULE}.get_gmail_service", side_effect=Exception("no token")),
        ):
            result = check_auth()
            assert result["authenticated"] is False
            assert "email" not in result
