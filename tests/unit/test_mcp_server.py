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
    create_event,
    create_folder,
    create_gmail_draft,
    delete_event,
    delete_file,
    delete_gmail_draft,
    download_file,
    forward_gmail,
    get_active_workspace,
    get_email,
    get_event,
    get_file,
    get_file_content,
    list_events,
    list_files,
    list_gmail_drafts,
    list_provider_slots,
    list_workspaces,
    modify_labels,
    rsvp_event,
    save_email,
    save_emails_by_query,
    save_event,
    save_file,
    save_thread,
    search_gmail,
    search_workspace,
    send_email,
    send_gmail_draft,
    set_active_workspace,
    trash_gmail,
    untrash_gmail,
    update_event,
    upload_file,
    workspace_auth_status,
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
        with (
            patch(f"{MODULE}._get_workspace", return_value=None),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
            result = search_gmail("from:test@example.com", max_results=5, days=3)
        assert result == [{"message_id": "m1"}]
        provider.search_emails.assert_called_once()
        call_query = provider.search_emails.call_args[0][0]
        assert call_query.text == "from:test@example.com"
        assert call_query.max_results == 5

    def test_search_with_dates(self):
        provider = _make_provider()
        with (
            patch(f"{MODULE}._get_workspace", return_value=None),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
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
        with (
            patch(f"{MODULE}._get_workspace", return_value=None),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
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
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_email("m1")
        assert result["subject"] == "Test"
        provider.get_email_content.assert_called_once_with("m1", "text/html")

    def test_get_email_plain(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.create_output_directory", return_value="/tmp/out"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
            patch(f"{MODULE}.download_email_attachments") as mock_dl,
        ):
            save_email("m3", download_attachments=True, attachment_types="pdf,docx")
        mock_dl.assert_called_once()
        _, kwargs = mock_dl.call_args
        assert kwargs["download_fn"] == provider.download_attachment
        assert kwargs["attachment_filters"] == ["pdf", "docx"]


class TestSaveThread:
    def test_save_thread(self):
        messages = [{"subject": "Thread Subject", "message_id": "m1", "from_": "x"}]
        provider = _make_provider()
        provider.get_thread.return_value = messages
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
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
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            send_email("bob@example.com", "Hi", "<b>Bold</b>", html=True)
        _, kwargs = provider.send_message.call_args
        assert kwargs["content_type"] == "html"

    def test_send_with_cc_bcc(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
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
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch("pathlib.Path.exists", return_value=True),
        ):
            send_email("bob@example.com", "Hi", "See attached", attachments=["/tmp/f.txt"])
        _, kwargs = provider.send_message.call_args
        assert kwargs["attachments"] == ["/tmp/f.txt"]


class TestForwardGmail:
    def test_forward(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = forward_gmail("m1", "bob@example.com", note="FYI")
        assert result["id"] == "fwd-1"
        provider.forward_message.assert_called_once_with(
            message_id="m1", to="bob@example.com", comment="FYI"
        )

    def test_forward_no_note(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = forward_gmail("m2", "alice@example.com")
        assert result["id"] == "fwd-1"


class TestBatchForwardGmail:
    def test_batch_forward(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_forward_gmail("from:test@example.com", "bob@example.com", note="FYI")
        assert result["forwarded_count"] == 2
        assert provider.forward_message.call_count == 2

    def test_batch_forward_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_forward_gmail("from:nobody@example.com", "bob@example.com")
        assert result["forwarded_count"] == 0

    def test_batch_forward_with_dates(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
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
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = create_gmail_draft("bob@example.com", "Draft Subject", "Body")
        assert result["id"] == "d1"
        provider.create_draft.assert_called_once()

    def test_create_draft_html(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            create_gmail_draft("bob@example.com", "HTML Draft", "<b>Bold</b>", html=True)
        _, kwargs = provider.create_draft.call_args
        assert kwargs["content_type"] == "html"

    def test_list_drafts(self):
        provider = _make_provider()
        provider.list_drafts.return_value = [{"id": "d1", "subject": "Test"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = list_gmail_drafts(max_results=5)
        assert len(result) == 1
        provider.list_drafts.assert_called_once_with(max_results=5)

    def test_send_draft(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = send_gmail_draft("d1")
        assert result["id"] == "sent-d1"
        provider.send_draft.assert_called_once_with("d1")

    def test_delete_draft(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = delete_gmail_draft("d1")
        assert result["draft_id"] == "d1"
        provider.delete_draft.assert_called_once_with("d1")


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_modify_labels_star(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = modify_labels("m1", star=True)
        assert result == {"message_id": "m1", "status": "modified"}
        provider.set_star.assert_called_once_with("m1", True)

    def test_modify_labels_mark_read(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            modify_labels("m1", mark_read=True)
        provider.mark_read.assert_called_once_with("m1", True)

    def test_modify_labels_archive(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            modify_labels("m1", archive=True)
        provider.archive.assert_called_once_with("m1")

    def test_modify_labels_custom(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            modify_labels("m1", add_label="MyLabel")
        provider.add_tag.assert_called_once_with("m1", "MyLabel")

    def test_batch_modify_labels(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_modify_gmail_labels("in:inbox", star=True)
        assert result["modified_count"] == 2
        assert provider.set_star.call_count == 2

    def test_batch_modify_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_modify_gmail_labels("from:nobody@example.com", mark_read=True)
        assert result["modified_count"] == 0


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


class TestTrash:
    def test_trash(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = trash_gmail("m1")
        assert result["message_id"] == "m1"
        assert result["status"] == "trashed"
        provider.trash.assert_called_once_with("m1")

    def test_untrash(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = untrash_gmail("m1")
        assert result["message_id"] == "m1"
        assert result["status"] == "untrashed"
        provider.untrash.assert_called_once_with("m1")


class TestBatchTrashGmail:
    def test_batch_trash(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_trash_gmail("from:spam@example.com", max_results=5, days=30)
        assert result["trashed_count"] == 2
        assert provider.trash.call_count == 2

    def test_batch_trash_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
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


# ---------------------------------------------------------------------------
# Workspace: calendar writes
# ---------------------------------------------------------------------------


class TestSaveEvent:
    def test_save_event_success(self, tmp_path):
        ws = _make_workspace(events=[{"id": "e1", "title": "Standup"}])
        with (
            patch(f"{MODULE}._get_workspace", return_value=ws),
            patch(
                "iobox.processing.markdown.convert_event_to_markdown",
                return_value="# Event",
            ),
            patch(f"{MODULE}.create_output_directory", return_value=str(tmp_path)),
        ):
            result = save_event("e1", output_dir=str(tmp_path))
        assert result["title"] == "Standup"
        assert result["filepath"].endswith(".md")

    def test_save_event_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = save_event("e1")
        assert "error" in result

    def test_save_event_unknown_provider(self):
        ws = _make_workspace(events=[{"id": "e1", "title": "Standup"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = save_event("e1", provider="nonexistent")
        assert "error" in result


class TestCreateEvent:
    def test_create_event_success(self):
        ws = _make_workspace(events=[])
        ws.calendar_providers[0].provider.create_event.return_value = {
            "id": "evt-new",
            "title": "Standup",
        }
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = create_event(
                "Standup",
                "2026-04-01T09:00:00",
                "2026-04-01T09:30:00",
                attendees=["a@b.com"],
            )
        assert result == {"id": "evt-new", "title": "Standup"}
        ws.calendar_providers[0].provider.create_event.assert_called_once_with(
            title="Standup",
            start="2026-04-01T09:00:00",
            end="2026-04-01T09:30:00",
            all_day=False,
            description=None,
            location=None,
            attendees=["a@b.com"],
        )

    def test_create_event_no_calendar_slots(self):
        ws = MagicMock()
        ws.calendar_providers = []
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = create_event("X", "2026-04-01", "2026-04-02")
        assert "error" in result


class TestUpdateEvent:
    def test_update_event_success(self):
        ws = _make_workspace(events=[{"id": "e1"}])
        ws.calendar_providers[0].provider.update_event.return_value = {
            "id": "e1",
            "title": "New",
        }
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = update_event("e1", {"title": "New"})
        assert result["title"] == "New"
        ws.calendar_providers[0].provider.update_event.assert_called_once_with(
            "e1", {"title": "New"}
        )

    def test_update_event_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = update_event("e1", {"title": "X"})
        assert "error" in result


class TestDeleteEvent:
    def test_delete_event_success(self):
        ws = _make_workspace(events=[{"id": "e1"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = delete_event("e1")
        assert result == {"event_id": "e1", "status": "deleted"}
        ws.calendar_providers[0].provider.delete_event.assert_called_once_with("e1")

    def test_delete_event_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = delete_event("e1")
        assert "error" in result


class TestRsvpEvent:
    def test_rsvp_event_success(self):
        ws = _make_workspace(events=[{"id": "e1"}])
        ws.calendar_providers[0].provider.rsvp.return_value = {
            "id": "e1",
            "response": "accepted",
        }
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = rsvp_event("e1", "accepted")
        assert result["response"] == "accepted"
        ws.calendar_providers[0].provider.rsvp.assert_called_once_with("e1", "accepted")

    def test_rsvp_event_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = rsvp_event("e1", "accepted")
        assert "error" in result


# ---------------------------------------------------------------------------
# Workspace: file writes
# ---------------------------------------------------------------------------


class TestSaveFile:
    def test_save_file_success(self, tmp_path):
        ws = _make_workspace(files=[{"id": "f1", "title": "report"}])
        with (
            patch(f"{MODULE}._get_workspace", return_value=ws),
            patch(
                "iobox.processing.markdown.convert_file_to_markdown",
                return_value="# File",
            ),
            patch(f"{MODULE}.create_output_directory", return_value=str(tmp_path)),
        ):
            result = save_file("f1", output_dir=str(tmp_path))
        assert result["filepath"].endswith(".md")
        assert "name" in result

    def test_save_file_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = save_file("f1")
        assert "error" in result


class TestDownloadFile:
    def test_download_file_success(self, tmp_path):
        ws = _make_workspace(files=[{"id": "f1"}])
        ws.file_providers[0].provider.download_file.return_value = b"hello world"
        target = tmp_path / "out" / "file.bin"
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = download_file("f1", str(target))
        assert result["bytes_written"] == len(b"hello world")
        assert result["filepath"] == str(target)
        assert target.read_bytes() == b"hello world"

    def test_download_file_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = download_file("f1", "/tmp/x")
        assert "error" in result


class TestUploadFile:
    def test_upload_file_success(self, tmp_path):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")
        ws = _make_workspace(files=[{"id": "f1"}])
        ws.file_providers[0].provider.upload_file.return_value = {
            "id": "uploaded-1",
            "title": "report.pdf",
        }
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = upload_file(str(local))
        assert result == {"id": "uploaded-1", "name": "report.pdf"}

    def test_upload_file_missing_local(self, tmp_path):
        result = upload_file(str(tmp_path / "missing.pdf"))
        assert "error" in result


class TestDeleteFile:
    def test_delete_file_trash(self):
        ws = _make_workspace(files=[{"id": "f1"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = delete_file("f1")
        assert result == {"file_id": "f1", "status": "trashed"}
        ws.file_providers[0].provider.delete_file.assert_called_once_with("f1", permanent=False)

    def test_delete_file_permanent(self):
        ws = _make_workspace(files=[{"id": "f1"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = delete_file("f1", permanent=True)
        assert result == {"file_id": "f1", "status": "deleted_permanently"}
        ws.file_providers[0].provider.delete_file.assert_called_once_with("f1", permanent=True)


class TestCreateFolder:
    def test_create_folder_success(self):
        ws = _make_workspace(files=[{"id": "f1"}])
        ws.file_providers[0].provider.create_folder.return_value = {
            "id": "folder-1",
            "title": "New Folder",
        }
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = create_folder("New Folder")
        assert result == {"id": "folder-1", "name": "New Folder"}
        ws.file_providers[0].provider.create_folder.assert_called_once_with(
            "New Folder", parent_id=None
        )

    def test_create_folder_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = create_folder("X")
        assert "error" in result


# ---------------------------------------------------------------------------
# Workspace: discovery + auth
# ---------------------------------------------------------------------------


class TestListWorkspaces:
    def test_list_workspaces(self):
        with (
            patch(
                "iobox.space_config.list_spaces",
                return_value=["personal", "work"],
            ),
            patch("iobox.space_config.get_active_space", return_value="personal"),
        ):
            result = list_workspaces()
        assert result == {"workspaces": ["personal", "work"], "active": "personal"}


class TestGetActiveWorkspace:
    def test_get_active_workspace(self):
        with patch("iobox.space_config.get_active_space", return_value="personal"):
            result = get_active_workspace()
        assert result == {"active": "personal"}

    def test_get_active_workspace_none(self):
        with patch("iobox.space_config.get_active_space", return_value=None):
            result = get_active_workspace()
        assert result == {"active": None}


class TestSetActiveWorkspace:
    def test_set_active_workspace_success(self):
        with (
            patch("iobox.space_config.list_spaces", return_value=["personal", "work"]),
            patch("iobox.space_config.set_active_space") as mock_set,
        ):
            result = set_active_workspace("work")
        assert result == {"active": "work"}
        mock_set.assert_called_once_with("work")

    def test_set_active_workspace_unknown(self):
        with (
            patch("iobox.space_config.list_spaces", return_value=["personal"]),
            patch("iobox.space_config.set_active_space") as mock_set,
        ):
            result = set_active_workspace("nope")
        assert "error" in result
        mock_set.assert_not_called()


def _make_full_workspace():
    """Build a workspace with all three slot types populated."""
    ws = MagicMock()
    ws.name = "personal"

    def _slot(name, tags, klass_name):
        s = MagicMock()
        s.name = name
        s.tags = tags
        s.provider = MagicMock()
        s.provider.__class__.__name__ = klass_name
        type(s.provider).__name__ = klass_name  # ensure type() reads correctly
        return s

    email_slot = _slot("personal-gmail", ["primary"], "GmailProvider")
    cal_slot = _slot("personal-cal", [], "GoogleCalendarProvider")
    file_slot = _slot("personal-drive", ["work"], "GoogleDriveProvider")

    ws.email_providers = [email_slot]
    ws.calendar_providers = [cal_slot]
    ws.file_providers = [file_slot]
    return ws


class TestListProviderSlots:
    def test_list_provider_slots(self):
        ws = _make_full_workspace()
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = list_provider_slots()
        assert result["workspace"] == "personal"
        assert len(result["email"]) == 1
        assert result["email"][0]["name"] == "personal-gmail"
        assert result["email"][0]["tags"] == ["primary"]
        assert "provider_class" in result["email"][0]
        assert result["calendar"][0]["name"] == "personal-cal"
        assert result["file"][0]["name"] == "personal-drive"
        assert result["file"][0]["tags"] == ["work"]

    def test_list_provider_slots_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = list_provider_slots()
        assert "error" in result


class TestWorkspaceAuthStatus:
    def test_auth_status_success(self):
        ws = _make_full_workspace()
        ws.email_providers[0].provider.get_profile.return_value = {"emailAddress": "me@gmail.com"}
        ws.calendar_providers[0].provider.get_profile.return_value = {
            "emailAddress": "me@gmail.com"
        }
        ws.file_providers[0].provider.get_profile.return_value = {"email": "me@gmail.com"}
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = workspace_auth_status()
        assert result["workspace"] == "personal"
        slots = result["slots"]
        assert slots["personal-gmail"]["authenticated"] is True
        assert slots["personal-gmail"]["account"] == "me@gmail.com"
        assert slots["personal-gmail"]["error"] is None
        assert slots["personal-drive"]["account"] == "me@gmail.com"

    def test_auth_status_exception(self):
        ws = _make_full_workspace()
        ws.email_providers[0].provider.get_profile.side_effect = RuntimeError("expired")
        ws.calendar_providers[0].provider.get_profile.return_value = {
            "emailAddress": "me@gmail.com"
        }
        ws.file_providers[0].provider.get_profile.return_value = {"emailAddress": "me@gmail.com"}
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = workspace_auth_status()
        slot = result["slots"]["personal-gmail"]
        assert slot["authenticated"] is False
        assert slot["account"] is None
        assert "expired" in slot["error"]

    def test_auth_status_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = workspace_auth_status()
        assert "error" in result


# ---------------------------------------------------------------------------
# Email tools: workspace routing
# ---------------------------------------------------------------------------


class TestEmailToolsWorkspaceRouting:
    def test_search_gmail_routes_via_workspace(self):
        """search_gmail with workspace fans out via Workspace.search_emails."""
        ws = _make_full_workspace()
        ws.search_emails.return_value = [{"message_id": "m1", "from_": "x@y.com"}]
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = search_gmail("hello", workspace="personal")
        assert len(result) == 1
        assert result[0]["from"] == "x@y.com"
        ws.search_emails.assert_called_once()

    def test_search_gmail_with_provider_filter(self):
        ws = _make_full_workspace()
        ws.search_emails.return_value = []
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            search_gmail("hello", provider="personal-gmail")
        _, kwargs = ws.search_emails.call_args
        assert kwargs["providers"] == ["personal-gmail"]

    def test_send_email_routes_to_named_slot(self):
        """send_email with provider= picks the named slot via _resolve_email_provider."""
        ws = _make_full_workspace()
        ws.email_providers[0].provider.send_message.return_value = {
            "message_id": "sent-1",
            "id": "sent-1",
        }
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = send_email("bob@example.com", "Hi", "Body", provider="personal-gmail")
        assert result["id"] == "sent-1"
        ws.email_providers[0].provider.send_message.assert_called_once()

    def test_send_email_unknown_provider_raises(self):
        ws = _make_full_workspace()
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            try:
                send_email("bob@example.com", "Hi", "Body", provider="nonexistent")
            except ValueError as exc:
                assert "nonexistent" in str(exc)
            else:
                raise AssertionError("expected ValueError")

    def test_search_gmail_legacy_fallback(self):
        """No workspace + no provider → legacy _get_gmail_provider() path."""
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1", "from_": "x"}]
        with (
            patch(f"{MODULE}._get_workspace", return_value=None),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
            result = search_gmail("hello")
        assert result == [{"message_id": "m1", "from": "x"}]
        provider.search_emails.assert_called_once()

    def test_send_email_legacy_fallback(self):
        provider = _make_provider()
        with (
            patch(f"{MODULE}._get_workspace", return_value=None),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
            result = send_email("bob@example.com", "Hi", "Body")
        assert result["id"] == "sent-1"
        provider.send_message.assert_called_once()
