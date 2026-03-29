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
    get_event,
    get_file,
    get_file_content,
    list_events,
    list_files,
    list_gmail_drafts,
    modify_labels,
    save_email,
    save_emails_by_query,
    save_thread,
    search_gmail,
    search_workspace,
    send_email,
    send_gmail_draft,
    trash_gmail,
    untrash_gmail,
)

MODULE = "iobox.mcp_server"


def _make_provider():
    """Build a mock GmailProvider with sensible defaults."""
    p = MagicMock()
    p.search_emails.return_value = []
    p.get_email_content.return_value = {
        "message_id": "m1",
        "subject": "Test",
        "from_": "x@y.com",
    }
    p.get_thread.return_value = []
    p.batch_get_emails.return_value = []
    p.send_message.return_value = {"message_id": "sent-1", "id": "sent-1"}
    p.forward_message.return_value = {"message_id": "fwd-1", "id": "fwd-1"}
    p.create_draft.return_value = {"id": "d1"}
    p.list_drafts.return_value = []
    p.send_draft.return_value = {"id": "sent-d1"}
    p.delete_draft.return_value = {"status": "deleted", "draft_id": "d1"}
    p.get_new_messages.return_value = None
    return p


# ---------------------------------------------------------------------------
# Search & Read
# ---------------------------------------------------------------------------


class TestSearchGmail:
    def test_basic_search(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}]
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = search_gmail("from:test@example.com", max_results=5, days=3)
        assert result == [{"message_id": "m1"}]
        provider.search_emails.assert_called_once()
        call_query = provider.search_emails.call_args[0][0]
        assert call_query.text == "from:test@example.com"
        assert call_query.max_results == 5

    def test_search_with_dates(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = search_gmail(
                "subject:report",
                max_results=20,
                days=0,
                start_date="2024/01/01",
                end_date="2024/01/31",
            )
        assert result == []
        provider.search_emails.assert_called_once()

    def test_search_include_spam_trash(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            search_gmail("in:anywhere", include_spam_trash=True)
        call_query = provider.search_emails.call_args[0][0]
        assert call_query.include_spam_trash is True


class TestGetEmail:
    def test_get_email_html(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {
            "message_id": "m1",
            "subject": "Test",
            "from_": "x",
        }
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = get_email("m1")
        assert result["subject"] == "Test"
        provider.get_email_content.assert_called_once_with("m1", "text/html")

    def test_get_email_plain(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            get_email("m1", prefer_html=False)
        provider.get_email_content.assert_called_once_with("m1", "text/plain")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


class TestSaveEmail:
    def test_save_single(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {"message_id": "m1", "from_": "x"}
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            result = save_email("m1", output_dir="/tmp/out")
        assert result == "/tmp/out/email.md"

    def test_save_plain_text(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {"message_id": "m2", "from_": "x"}
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            save_email("m2", output_dir="/tmp/out", prefer_html=False)
        provider.get_email_content.assert_called_once_with("m2", "text/plain")

    def test_save_with_attachments(self):
        email_data = {"message_id": "m3", "attachments": [{"filename": "f.pdf"}], "from_": "x"}
        provider = _make_provider()
        provider.get_email_content.return_value = email_data
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(f"{MODULE}.download_email_attachments") as mock_dl,
        ):
            mock_svc.return_value = MagicMock()
            save_email("m3", download_attachments=True, attachment_types="pdf,docx")
        mock_dl.assert_called_once()
        _, kwargs = mock_dl.call_args
        assert kwargs["attachment_filters"] == ["pdf", "docx"]


class TestSaveThread:
    def test_save_thread(self):
        messages = [{"subject": "Thread Subject", "message_id": "m1", "from_": "x"}]
        provider = _make_provider()
        provider.get_thread.return_value = messages
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.convert_thread_to_markdown", return_value="# Thread"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch("builtins.open", MagicMock()),
        ):
            result = save_thread("t1", output_dir="/tmp/out")
        assert "t1" in result
        assert result.endswith(".md")


class TestSaveEmailsByQuery:
    def test_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
        ):
            result = save_emails_by_query("from:nobody@example.com")
        assert result["saved_count"] == 0

    def test_batch_save(self):
        search_results = [{"message_id": "m1"}, {"message_id": "m2"}]
        email_batch = [
            {"message_id": "m1", "subject": "A", "from_": "x"},
            {"message_id": "m2", "subject": "B", "from_": "x"},
        ]
        provider = _make_provider()
        provider.search_emails.return_value = search_results
        provider.batch_get_emails.return_value = email_batch
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.check_for_duplicates", return_value=[]),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            result = save_emails_by_query("in:inbox", max_results=2)
        assert result["saved_count"] == 2
        assert result["skipped_count"] == 0

    def test_batch_save_with_duplicates(self):
        search_results = [{"message_id": "m1"}, {"message_id": "m2"}]
        email_batch = [{"message_id": "m2", "subject": "B", "from_": "x"}]
        provider = _make_provider()
        provider.search_emails.return_value = search_results
        provider.batch_get_emails.return_value = email_batch
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.check_for_duplicates", return_value=["m1"]),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            result = save_emails_by_query("in:inbox")
        assert result["saved_count"] == 1
        assert result["skipped_count"] == 1


# ---------------------------------------------------------------------------
# Send & Forward
# ---------------------------------------------------------------------------


class TestSendEmail:
    def test_send_plain(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = send_email("bob@example.com", "Hello", "Body text")
        assert result["id"] == "sent-1"
        provider.send_message.assert_called_once_with(
            to="bob@example.com",
            subject="Hello",
            body="Body text",
            cc=None,
            bcc=None,
            content_type="plain",
            attachments=None,
        )

    def test_send_html(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            send_email("bob@example.com", "Hi", "<b>Bold</b>", html=True)
        _, kwargs = provider.send_message.call_args
        assert kwargs["content_type"] == "html"

    def test_send_with_cc_bcc(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            send_email("bob@example.com", "Hi", "Body", cc="cc@example.com", bcc="bcc@example.com")
        provider.send_message.assert_called_once_with(
            to="bob@example.com",
            subject="Hi",
            body="Body",
            cc="cc@example.com",
            bcc="bcc@example.com",
            content_type="plain",
            attachments=None,
        )

    def test_send_with_attachments(self):
        provider = _make_provider()
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch("pathlib.Path.exists", return_value=True),
        ):
            send_email("bob@example.com", "Hi", "See attached", attachments=["/tmp/f.txt"])
        _, kwargs = provider.send_message.call_args
        assert kwargs["attachments"] == ["/tmp/f.txt"]


class TestForwardGmail:
    def test_forward(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = forward_gmail("m1", "bob@example.com", note="FYI")
        assert result["id"] == "fwd-1"
        provider.forward_message.assert_called_once_with(
            message_id="m1", to="bob@example.com", comment="FYI"
        )

    def test_forward_no_note(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = forward_gmail("m2", "alice@example.com")
        assert result["id"] == "fwd-1"


class TestBatchForwardGmail:
    def test_batch_forward(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = batch_forward_gmail("from:test@example.com", "bob@example.com", note="FYI")
        assert result["forwarded_count"] == 2
        assert provider.forward_message.call_count == 2

    def test_batch_forward_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = batch_forward_gmail("from:nobody@example.com", "bob@example.com")
        assert result["forwarded_count"] == 0

    def test_batch_forward_with_dates(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}]
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = batch_forward_gmail(
                "subject:report",
                "bob@example.com",
                start_date="2024/01/01",
                end_date="2024/01/31",
            )
        assert result["forwarded_count"] == 1
        provider.search_emails.assert_called_once()
        call_query = provider.search_emails.call_args[0][0]
        assert call_query.text == "subject:report"


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


class TestDrafts:
    def test_create_draft(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = create_gmail_draft("bob@example.com", "Draft Subject", "Body")
        assert result["id"] == "d1"
        provider.create_draft.assert_called_once()

    def test_create_draft_html(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            create_gmail_draft("bob@example.com", "HTML Draft", "<b>Bold</b>", html=True)
        _, kwargs = provider.create_draft.call_args
        assert kwargs["content_type"] == "html"

    def test_list_drafts(self):
        provider = _make_provider()
        provider.list_drafts.return_value = [{"id": "d1", "subject": "Test"}]
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = list_gmail_drafts(max_results=5)
        assert len(result) == 1
        provider.list_drafts.assert_called_once_with(max_results=5)

    def test_send_draft(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = send_gmail_draft("d1")
        assert result["id"] == "sent-d1"
        provider.send_draft.assert_called_once_with("d1")

    def test_delete_draft(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = delete_gmail_draft("d1")
        assert result["draft_id"] == "d1"
        provider.delete_draft.assert_called_once_with("d1")


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_modify_labels_star(self):
        _MOD_LABELS = "iobox.providers.google._retrieval.modify_message_labels"
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(_MOD_LABELS, return_value={"id": "m1"}) as mock_mod,
            patch("iobox.providers.google._retrieval.resolve_label_name"),
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", star=True)
        mock_mod.assert_called_once_with(mock_svc.return_value, "m1", ["STARRED"], None)

    def test_modify_labels_mark_read(self):
        _MOD_LABELS = "iobox.providers.google._retrieval.modify_message_labels"
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(_MOD_LABELS, return_value={"id": "m1"}) as mock_mod,
            patch("iobox.providers.google._retrieval.resolve_label_name"),
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", mark_read=True)
        mock_mod.assert_called_once_with(mock_svc.return_value, "m1", None, ["UNREAD"])

    def test_modify_labels_archive(self):
        _MOD_LABELS = "iobox.providers.google._retrieval.modify_message_labels"
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch(_MOD_LABELS, return_value={"id": "m1"}) as mock_mod,
            patch("iobox.providers.google._retrieval.resolve_label_name"),
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", archive=True)
        mock_mod.assert_called_once_with(mock_svc.return_value, "m1", None, ["INBOX"])

    def test_modify_labels_custom(self):
        _MOD_LABELS = "iobox.providers.google._retrieval.modify_message_labels"
        with (
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch("iobox.providers.google._retrieval.resolve_label_name", return_value="Label_123"),
            patch(_MOD_LABELS, return_value={"id": "m1"}) as mock_mod,
        ):
            mock_svc.return_value = MagicMock()
            modify_labels("m1", add_label="MyLabel")
        mock_mod.assert_called_once_with(mock_svc.return_value, "m1", ["Label_123"], None)

    def test_batch_modify_labels(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch("iobox.providers.google._retrieval.resolve_label_name", return_value=""),
            patch("iobox.providers.google._retrieval.batch_modify_labels") as mock_batch,
            patch("iobox.providers.google._retrieval.modify_message_labels"),
        ):
            mock_svc.return_value = MagicMock()
            result = batch_modify_gmail_labels("in:inbox", star=True)
        assert result["modified_count"] == 2
        mock_batch.assert_called_once()

    def test_batch_modify_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with (
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
            patch(f"{MODULE}.get_gmail_service") as mock_svc,
            patch("iobox.providers.google._retrieval.resolve_label_name", return_value=""),
        ):
            mock_svc.return_value = MagicMock()
            result = batch_modify_gmail_labels("from:nobody@example.com", mark_read=True)
        assert result["modified_count"] == 0


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


class TestTrash:
    def test_trash(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = trash_gmail("m1")
        assert result["message_id"] == "m1"
        assert result["status"] == "trashed"
        provider.trash.assert_called_once_with("m1")

    def test_untrash(self):
        provider = _make_provider()
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = untrash_gmail("m1")
        assert result["message_id"] == "m1"
        assert result["status"] == "untrashed"
        provider.untrash.assert_called_once_with("m1")


class TestBatchTrashGmail:
    def test_batch_trash(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
            result = batch_trash_gmail("from:spam@example.com", max_results=5, days=30)
        assert result["trashed_count"] == 2
        assert provider.trash.call_count == 2

    def test_batch_trash_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with patch(f"{MODULE}._get_gmail_provider", return_value=provider):
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


# ---------------------------------------------------------------------------
# Workspace tools
# ---------------------------------------------------------------------------


def _make_workspace(events=None, files=None, messages=None):
    """Build a minimal mock Workspace."""
    ws = MagicMock()
    ws.calendar_providers = []
    ws.file_providers = []
    ws.message_providers = []

    if events is not None:
        cal_slot = MagicMock()
        cal_slot.name = "gcal"
        cal_slot.provider.get_event.return_value = events[0] if events else {}
        ws.calendar_providers = [cal_slot]
        ws.list_events.return_value = events

    if files is not None:
        file_slot = MagicMock()
        file_slot.name = "gdrive"
        file_slot.provider.get_file.return_value = files[0] if files else {}
        file_slot.provider.get_file_content.return_value = "file content"
        ws.file_providers = [file_slot]
        ws.list_files.return_value = files

    ws.search.return_value = []
    return ws


class TestSearchWorkspace:
    def test_no_workspace_returns_error(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = search_workspace("Q4 planning")
        assert len(result) == 1
        assert "error" in result[0]

    def test_search_with_workspace(self):
        ws = _make_workspace()
        ws.search.return_value = [{"resource_type": "event", "title": "Q4 planning"}]
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = search_workspace("Q4 planning")
        assert len(result) == 1
        assert result[0]["title"] == "Q4 planning"

    def test_search_type_filter(self):
        ws = _make_workspace()
        ws.search.return_value = []
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            search_workspace("budget", types=["file"])
        ws.search.assert_called_once_with("budget", types=["file"], max_results_per_type=10)


class TestListEvents:
    def test_no_workspace_returns_error(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = list_events()
        assert len(result) == 1
        assert "error" in result[0]

    def test_list_events_basic(self):
        ws = _make_workspace(events=[{"id": "e1", "title": "Standup"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = list_events()
        assert len(result) == 1
        assert result[0]["title"] == "Standup"

    def test_list_events_with_provider_filter(self):
        ws = _make_workspace(events=[])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            list_events(provider="gcal")
        ws.list_events.assert_called_once()
        _, kwargs = ws.list_events.call_args
        assert kwargs["providers"] == ["gcal"]


class TestGetEvent:
    def test_no_workspace_returns_error(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = get_event("evt1")
        assert "error" in result

    def test_no_calendar_providers_returns_error(self):
        ws = MagicMock()
        ws.calendar_providers = []
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_event("evt1")
        assert "error" in result

    def test_get_event_basic(self):
        ws = _make_workspace(events=[{"id": "evt1", "title": "Standup"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_event("evt1")
        assert result["id"] == "evt1"

    def test_get_event_unknown_provider(self):
        ws = _make_workspace(events=[{"id": "evt1", "title": "Standup"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_event("evt1", provider="nonexistent")
        assert "error" in result


class TestListFiles:
    def test_no_workspace_returns_error(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = list_files("Q4 report")
        assert len(result) == 1
        assert "error" in result[0]

    def test_list_files_basic(self):
        ws = _make_workspace(files=[{"id": "f1", "name": "report.pdf"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = list_files("report")
        assert len(result) == 1
        assert result[0]["name"] == "report.pdf"

    def test_list_files_with_provider_filter(self):
        ws = _make_workspace(files=[])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            list_files("budget", provider="gdrive")
        ws.list_files.assert_called_once()
        _, kwargs = ws.list_files.call_args
        assert kwargs["providers"] == ["gdrive"]


class TestGetFile:
    def test_no_workspace_returns_error(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = get_file("file1")
        assert "error" in result

    def test_no_file_providers_returns_error(self):
        ws = MagicMock()
        ws.file_providers = []
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_file("file1")
        assert "error" in result

    def test_get_file_basic(self):
        ws = _make_workspace(files=[{"id": "file1", "name": "report.pdf"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_file("file1")
        assert result["id"] == "file1"

    def test_get_file_unknown_provider(self):
        ws = _make_workspace(files=[{"id": "file1", "name": "report.pdf"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_file("file1", provider="nonexistent")
        assert "error" in result


class TestGetFileContent:
    def test_no_workspace_returns_error(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = get_file_content("file1")
        assert "error" in result

    def test_get_file_content_basic(self):
        ws = _make_workspace(files=[{"id": "file1", "name": "notes.txt"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_file_content("file1")
        assert "content" in result
        assert result["content"] == "file content"

    def test_get_file_content_no_file_providers(self):
        ws = MagicMock()
        ws.file_providers = []
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = get_file_content("file1")
        assert "error" in result
