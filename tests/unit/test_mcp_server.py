"""Tests for MCP server tools."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
    create_label,
    delete_event,
    delete_file,
    delete_gmail_draft,
    download_file,
    forward_gmail,
    get_active_workspace,
    get_email,
    get_emails,
    get_event,
    get_file,
    get_file_content,
    list_events,
    list_files,
    list_gmail_drafts,
    list_labels,
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


@pytest.fixture(autouse=True)
def mcp_root(tmp_path, monkeypatch):
    """Confine every MCP filesystem path to a per-test root (never ~/iobox)."""
    root = tmp_path / "mcp-root"
    root.mkdir()
    monkeypatch.setenv("IOBOX_MCP_ROOT", str(root))
    monkeypatch.setenv("CREDENTIALS_DIR", str(tmp_path / "creds"))
    # Never read the developer's real ~/.iobox (active space, configs, tokens).
    import iobox.space_config as sc

    home = tmp_path / "iobox-home"
    monkeypatch.setattr(sc, "IOBOX_HOME", home)
    monkeypatch.setattr(sc, "WORKSPACES_DIR", home / "workspaces")
    monkeypatch.setattr(sc, "TOKENS_DIR", home / "tokens")
    monkeypatch.setattr(sc, "INDEXES_DIR", home / "indexes")
    monkeypatch.setattr(sc, "ACTIVE_SPACE_FILE", home / "active_space")
    return Path(os.path.realpath(root))


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

    def test_get_email_body_none_omits_body(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {
            "message_id": "m1",
            "from_": "x",
            "body": "<p>big html</p>",
            "content_type": "text/html",
            "attachments": [{"id": "a1", "filename": "r.pdf"}],
        }
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_email("m1", body="none")
        assert "body" not in result
        assert "content_type" not in result
        assert result["attachments"][0]["filename"] == "r.pdf"

    def test_get_email_markdown_converts_html(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {
            "message_id": "m1",
            "from_": "x",
            "body": "<p>Hello <b>world</b></p>",
            "content_type": "text/html",
        }
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_email("m1", body="markdown")
        assert result["content_type"] == "text/markdown"
        assert "Hello" in result["body"]
        assert "<p>" not in result["body"]

    def test_get_email_text_converts_html_only_body(self):
        """HTML-only emails (no text/plain part) must still yield plain text."""
        provider = _make_provider()
        provider.get_email_content.return_value = {
            "message_id": "m1",
            "from_": "x",
            "body": '<p>Hello <b>world</b> <a href="https://x.com">link</a></p>',
            "content_type": "text/html",
        }
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_email("m1", body="text")
        assert result["content_type"] == "text/plain"
        assert result["body"] == "Hello world link"

    def test_get_email_truncates_body(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {
            "message_id": "m1",
            "from_": "x",
            "body": "x" * 5000,
            "content_type": "text/plain",
        }
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_email("m1", body="text", max_body_chars=100)
        assert result["truncated"] is True
        assert result["body"].startswith("x" * 100)
        assert "truncated" in result["body"]

    def test_get_email_invalid_mode(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_email("m1", body="bogus")
        assert "error" in result


class TestGetEmails:
    def test_batch_headers_only(self):
        provider = _make_provider()
        provider.batch_get_emails.return_value = [
            {"message_id": "m1", "from_": "a@y.com", "subject": "A", "body": "hi"},
            {"message_id": "m2", "from_": "b@y.com", "subject": "B", "body": "yo"},
        ]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "m2"])
        provider.batch_get_emails.assert_called_once_with(
            ["m1", "m2"], preferred_content_type="text/plain"
        )
        assert [r["message_id"] for r in result] == ["m1", "m2"]
        assert "body" not in result[0]  # default body="none"
        assert result[0]["from"] == "a@y.com"

    def test_batch_propagates_errors(self):
        provider = _make_provider()
        provider.batch_get_emails.return_value = [
            {"message_id": "m1", "from_": "a@y.com", "subject": "A"},
            {"message_id": "m2", "error": "Not found in batch response"},
        ]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "m2"], body="text")
        assert result[1]["error"] == "Not found in batch response"

    def test_batch_invalid_mode(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1"], body="bogus")
        assert "error" in result[0]


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
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            result = save_email("m1", output_dir="out")
        assert result["markdown_path"] == "/tmp/out/email.md"
        assert result["attachments"] == []

    def test_save_plain_text(self):
        provider = _make_provider()
        provider.get_email_content.return_value = {"message_id": "m2", "from_": "x"}
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
        ):
            save_email("m2", output_dir="out", prefer_html=False)
        provider.get_email_content.assert_called_once_with("m2", "text/plain")

    def test_save_with_attachments(self):
        email_data = {"message_id": "m3", "attachments": [{"filename": "f.pdf"}], "from_": "x"}
        provider = _make_provider()
        provider.get_email_content.return_value = email_data
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="/tmp/out/email.md"),
            patch(f"{MODULE}.download_email_attachments") as mock_dl,
        ):
            mock_dl.return_value = {
                "downloaded_count": 1,
                "skipped_count": 0,
                "errors": [],
                "saved": [{"filename": "f.pdf", "path": "/tmp/out/attachments/m3/f.pdf"}],
            }
            result = save_email("m3", download_attachments=True, attachment_types="pdf,docx")
        mock_dl.assert_called_once()
        _, kwargs = mock_dl.call_args
        assert kwargs["download_fn"] == provider.download_attachment
        assert kwargs["attachment_filters"] == ["pdf", "docx"]
        assert kwargs["include_inline"] is False
        assert result["attachments"][0]["filename"] == "f.pdf"


class TestSaveThread:
    def test_save_thread(self):
        messages = [{"subject": "Thread Subject", "message_id": "m1", "from_": "x"}]
        provider = _make_provider()
        provider.get_thread.return_value = messages
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.convert_thread_to_markdown", return_value="# Thread"),
            patch("builtins.open", MagicMock()),
        ):
            result = save_thread("t1", output_dir="out")
        assert "t1" in result
        assert result.endswith(".md")


class TestSaveEmailsByQuery:
    def test_no_results(self):
        provider = _make_provider()
        provider.search_emails.return_value = []
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
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

    def test_send_with_attachments(self, mcp_root):
        (mcp_root / "f.txt").write_text("x")
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            send_email("bob@example.com", "Hi", "See attached", attachments=["f.txt"])
        _, kwargs = provider.send_message.call_args
        assert kwargs["attachments"] == [str(mcp_root / "f.txt")]


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


class TestLabelDiscovery:
    def test_list_labels(self):
        provider = _make_provider()
        provider.list_tags.return_value = {"INBOX": "INBOX", "Label_1": "Work"}
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = list_labels()
        assert result == {"labels": {"INBOX": "INBOX", "Label_1": "Work"}}

    def test_create_label(self):
        provider = _make_provider()
        provider.create_tag.return_value = {"id": "Label_x", "name": "A/B/C"}
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = create_label("A/B/C")
        provider.create_tag.assert_called_once_with("A/B/C")
        assert result == {"id": "Label_x", "name": "A/B/C"}

    def test_create_label_not_supported(self):
        provider = _make_provider()
        provider.create_tag.side_effect = NotImplementedError()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = create_label("X")
        assert "error" in result


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


def _save_space(name, entries, active=False):
    """Write a workspace config into the test-isolated ~/.iobox."""
    import iobox.space_config as sc

    sc.save_space(sc.SpaceConfig(name=name, services=entries))
    if active:
        sc.set_active_space(name)


def _entry(account, service="google", scopes=("email",), number=1):
    from iobox.space_config import ServiceEntry

    return ServiceEntry(number=number, service=service, account=account, scopes=list(scopes))


def _give_token(entry):
    from iobox.space_config import token_file_for

    path = token_file_for(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")


class TestCheckAuth:
    def test_legacy_reports_cached_status_only(self):
        """No workspace → cached legacy token status; never builds a Gmail service."""
        with (
            patch(
                f"{MODULE}.check_auth_status",
                return_value={"authenticated": False, "token_file_exists": False},
            ),
            patch("iobox.providers.google.auth.get_gmail_service") as svc,
            patch("iobox.providers.google.auth.InstalledAppFlow") as flow,
        ):
            result = check_auth()
        assert result["authenticated"] is False
        svc.assert_not_called()
        flow.assert_not_called()

    def test_workspace_reports_per_service_from_cache(self):
        authed = _entry("me@gmail.com", scopes=("email", "calendar"))
        missing = _entry("corp@example.com", service="o365", number=2)
        _give_token(authed)
        _save_space("personal", [authed, missing], active=True)
        with patch(f"{MODULE}.check_auth_status") as legacy:
            result = check_auth()
        legacy.assert_not_called()
        assert result["workspace"] == "personal"
        assert result["authenticated"] is False
        by_account = {s["account"]: s for s in result["services"]}
        assert by_account["me@gmail.com"]["authenticated"] is True
        assert by_account["corp@example.com"]["authenticated"] is False
        assert "mode" in result

    def test_named_workspace_missing_returns_error(self):
        result = check_auth(workspace="typo")
        assert "error" in result
        assert result["authenticated"] is False

    def test_check_auth_reports_readonly_mode(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "readonly")
        with (
            patch(f"{MODULE}.check_auth_status", return_value={"authenticated": True}),
        ):
            result = check_auth()
        assert result["mode"] == "readonly"
        assert result["available_write_ops"] is False
        assert result["available_send_ops"] is False
        assert "mode_hint" in result

    def test_check_auth_reports_dangerous_mode(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "dangerous")
        with (
            patch(f"{MODULE}.check_auth_status", return_value={"authenticated": True}),
        ):
            result = check_auth()
        assert result["mode"] == "dangerous"
        assert result["available_write_ops"] is True
        assert result["available_send_ops"] is True
        assert "mode_hint" not in result


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
        ):
            result = save_event("e1", output_dir="saved")
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
        ):
            result = save_file("f1", output_dir="saved")
        assert result["filepath"].endswith(".md")
        assert "name" in result

    def test_save_file_no_workspace(self):
        with patch(f"{MODULE}._get_workspace", return_value=None):
            result = save_file("f1")
        assert "error" in result


class TestDownloadFile:
    def test_download_file_success(self, mcp_root):
        ws = _make_workspace(files=[{"id": "f1"}])
        ws.file_providers[0].provider.download_file.return_value = b"hello world"
        target = mcp_root / "out" / "file.bin"
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
    def test_upload_file_success(self, mcp_root):
        local = mcp_root / "report.pdf"
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


# ---------------------------------------------------------------------------
# Workspace loading: no silent fallback (SEC-05, MCP-05)
# ---------------------------------------------------------------------------


class TestWorkspaceLoading:
    def test_default_fn_no_workspace_returns_none(self):
        from iobox.mcp_server import _default_workspace_fn

        with patch("iobox.space_config.get_active_space", return_value=None):
            assert _default_workspace_fn(None) is None

    def test_default_fn_named_missing_raises(self):
        from iobox.mcp_server import WorkspaceLoadError, _default_workspace_fn

        with (
            patch("iobox.space_config.get_active_space", return_value=None),
            patch("iobox.space_config.load_space", side_effect=FileNotFoundError("nope")),
        ):
            try:
                _default_workspace_fn("typo")
            except WorkspaceLoadError as exc:
                assert "typo" in str(exc)
            else:
                raise AssertionError("expected WorkspaceLoadError")

    def test_default_fn_active_unloadable_raises(self):
        from iobox.mcp_server import WorkspaceLoadError, _default_workspace_fn

        with (
            patch("iobox.space_config.get_active_space", return_value="work"),
            patch("iobox.space_config.load_space", side_effect=ValueError("bad toml")),
        ):
            try:
                _default_workspace_fn(None)
            except WorkspaceLoadError as exc:
                assert "work" in str(exc)
            else:
                raise AssertionError("expected WorkspaceLoadError")

    def test_get_workspace_passes_name_without_retry(self):
        import iobox.mcp_server as srv

        calls = []

        def factory(name):
            calls.append(name)
            raise TypeError("boom")

        with patch.object(srv, "_workspace_factory", factory):
            try:
                srv._get_workspace("work")
            except TypeError:
                pass
            else:
                raise AssertionError("TypeError should propagate, not retry")
        assert calls == ["work"]

    def test_send_email_misspelled_workspace_does_not_fall_back(self):
        provider = _make_provider()
        with (
            patch("iobox.space_config.get_active_space", return_value=None),
            patch("iobox.space_config.load_space", side_effect=FileNotFoundError("nope")),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
            result = send_email("bob@example.com", "Hi", "Body", workspace="typo")
        assert "error" in result
        assert "typo" in result["error"]
        provider.send_message.assert_not_called()

    def test_search_gmail_misspelled_workspace_does_not_fall_back(self):
        provider = _make_provider()
        with (
            patch("iobox.space_config.get_active_space", return_value=None),
            patch("iobox.space_config.load_space", side_effect=FileNotFoundError("nope")),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
            result = search_gmail("hello", workspace="typo")
        assert len(result) == 1 and "error" in result[0]
        provider.search_emails.assert_not_called()

    def test_list_events_unloadable_workspace_returns_error(self):
        with (
            patch("iobox.space_config.get_active_space", return_value="work"),
            patch("iobox.space_config.load_space", side_effect=ValueError("bad")),
        ):
            result = list_events()
        assert len(result) == 1 and "work" in result[0]["error"]

    def test_workspace_without_email_slots_errors(self):
        ws = _make_full_workspace()
        ws.email_providers = []
        provider = _make_provider()
        with (
            patch(f"{MODULE}._get_workspace", return_value=ws),
            patch(f"{MODULE}._get_gmail_provider", return_value=provider),
        ):
            sent = send_email("bob@example.com", "Hi", "Body")
            found = search_gmail("hello")
        assert "error" in sent
        assert "error" in found[0]
        provider.send_message.assert_not_called()
        provider.search_emails.assert_not_called()


# ---------------------------------------------------------------------------
# Filesystem confinement (SEC-01, SEC-03, SEC-04)
# ---------------------------------------------------------------------------


class TestConfinePath:
    def test_relative_resolves_under_root(self, mcp_root):
        from iobox.mcp_server import _confine_path

        assert _confine_path("a/b.txt") == mcp_root / "a" / "b.txt"
        assert _confine_path(None) == mcp_root
        assert _confine_path(".") == mcp_root

    def test_absolute_inside_root_allowed(self, mcp_root):
        from iobox.mcp_server import _confine_path

        assert _confine_path(str(mcp_root / "x.bin")) == mcp_root / "x.bin"

    def test_traversal_rejected(self):
        from iobox.mcp_server import PathNotAllowedError, _confine_path

        with pytest.raises(PathNotAllowedError):
            _confine_path("../escape.txt")
        with pytest.raises(PathNotAllowedError):
            _confine_path("sub/../../escape.txt")

    def test_absolute_outside_rejected(self, tmp_path):
        from iobox.mcp_server import PathNotAllowedError, _confine_path

        with pytest.raises(PathNotAllowedError):
            _confine_path(str(tmp_path / "elsewhere.txt"))
        with pytest.raises(PathNotAllowedError):
            _confine_path("/etc/passwd")

    def test_symlink_escape_rejected(self, mcp_root, tmp_path):
        from iobox.mcp_server import PathNotAllowedError, _confine_path

        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("s")
        (mcp_root / "linkdir").symlink_to(outside)
        (mcp_root / "linkfile").symlink_to(outside / "secret.txt")
        with pytest.raises(PathNotAllowedError):
            _confine_path("linkdir/secret.txt")
        with pytest.raises(PathNotAllowedError):
            _confine_path("linkfile")
        with pytest.raises(PathNotAllowedError):
            _confine_path("linkdir/new.bin")

    def test_iobox_home_denied_even_when_root_contains_it(self, tmp_path, monkeypatch):
        from iobox.mcp_server import PathNotAllowedError, _confine_path

        home = tmp_path / "home"
        (home / ".iobox" / "tokens" / "me").mkdir(parents=True)
        (home / ".iobox" / "tokens" / "me" / "token_standard.json").write_text("{}")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("IOBOX_MCP_ROOT", str(home))
        with pytest.raises(PathNotAllowedError):
            _confine_path("~/.iobox/tokens/me/token_standard.json")
        with pytest.raises(PathNotAllowedError):
            _confine_path(".iobox/tokens/me/token_standard.json")
        with pytest.raises(PathNotAllowedError):
            _confine_path(".iobox")
        assert _confine_path("notes/a.md") == Path(os.path.realpath(home)) / "notes" / "a.md"

    def test_legacy_credentials_denied(self, mcp_root, monkeypatch):
        from iobox.mcp_server import PathNotAllowedError, _confine_path

        monkeypatch.setenv("CREDENTIALS_DIR", str(mcp_root))
        for name in ("credentials.json", "token.json", "o365_token.txt", "tokens/a/t.json"):
            with pytest.raises(PathNotAllowedError):
                _confine_path(name)

    def test_root_created_on_demand(self, tmp_path, monkeypatch):
        from iobox.mcp_server import _mcp_root

        target = tmp_path / "fresh" / "root"
        monkeypatch.setenv("IOBOX_MCP_ROOT", str(target))
        assert _mcp_root() == Path(os.path.realpath(target))
        assert target.is_dir()

    def test_default_root_is_home_iobox(self, tmp_path, monkeypatch):
        from iobox.mcp_server import _mcp_root

        monkeypatch.delenv("IOBOX_MCP_ROOT", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _mcp_root() == Path(os.path.realpath(tmp_path)) / "iobox"


class TestDownloadConfinement:
    def test_attachment_outside_root_refused(self, tmp_path):
        from iobox.mcp_server import download_email_attachment

        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = download_email_attachment("m1", "a1", output_path=str(tmp_path / "x.bin"))
        assert "error" in result
        provider.download_attachment.assert_not_called()

    def test_attachment_written_inside_root(self, mcp_root):
        from iobox.mcp_server import download_email_attachment

        provider = _make_provider()
        provider.download_attachment.return_value = b"data"
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = download_email_attachment("m1", "a1", output_path="att/x.bin")
        assert result == {"filepath": str(mcp_root / "att" / "x.bin"), "bytes_written": 4}
        assert (mcp_root / "att" / "x.bin").read_bytes() == b"data"

    def test_attachment_does_not_overwrite(self, mcp_root):
        from iobox.mcp_server import download_email_attachment

        existing = mcp_root / "keep.txt"
        existing.write_bytes(b"original")
        provider = _make_provider()
        provider.download_attachment.return_value = b"new"
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = download_email_attachment("m1", "a1", output_path="keep.txt")
        assert "error" in result
        assert existing.read_bytes() == b"original"

    def test_attachment_base64_needs_no_path(self):
        from iobox.mcp_server import download_email_attachment

        provider = _make_provider()
        provider.download_attachment.return_value = b"hi"
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = download_email_attachment("m1", "a1", return_base64=True)
        assert result["data"] == "aGk="

    def test_download_file_outside_root_refused(self, tmp_path):
        ws = _make_workspace(files=[{"id": "f1"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = download_file("f1", str(tmp_path / "evil.bin"))
        assert "error" in result
        ws.file_providers[0].provider.download_file.assert_not_called()

    def test_download_file_does_not_overwrite(self, mcp_root):
        (mcp_root / "f.bin").write_bytes(b"original")
        ws = _make_workspace(files=[{"id": "f1"}])
        ws.file_providers[0].provider.download_file.return_value = b"new"
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = download_file("f1", "f.bin")
        assert "error" in result
        assert (mcp_root / "f.bin").read_bytes() == b"original"

    def test_save_email_output_dir_outside_root_refused(self, tmp_path):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = save_email("m1", output_dir=str(tmp_path / "elsewhere"))
        assert "error" in result
        assert not (tmp_path / "elsewhere").exists()

    def test_save_thread_id_traversal_refused(self, mcp_root):
        provider = _make_provider()
        provider.get_thread.return_value = [{"subject": "S", "message_id": "m1", "from_": "x"}]
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.convert_thread_to_markdown", return_value="# T"),
        ):
            result = save_thread("x/../../../escape", output_dir="out")
        assert isinstance(result, dict) and "error" in result


class TestOutgoingFileConfinement:
    def test_draft_attachment_outside_root_refused(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("s")
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = create_gmail_draft("a@b.com", "S", "B", attachments=[str(secret)])
        assert "error" in result
        provider.create_draft.assert_not_called()

    def test_send_attachment_token_file_refused(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        token = home / ".iobox" / "tokens" / "me" / "token_standard.json"
        token.parent.mkdir(parents=True)
        token.write_text("{}")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("IOBOX_MCP_ROOT", str(home))
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = send_email("a@b.com", "S", "B", attachments=[str(token)])
        assert "error" in result
        provider.send_message.assert_not_called()

    def test_missing_attachment_refused(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = create_gmail_draft("a@b.com", "S", "B", attachments=["nope.pdf"])
        assert "error" in result

    def test_upload_outside_root_refused(self, tmp_path):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")
        ws = _make_workspace(files=[{"id": "f1"}])
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = upload_file(str(local))
        assert "error" in result
        ws.file_providers[0].provider.upload_file.assert_not_called()

    def test_upload_inside_root_passes_resolved_path(self, mcp_root):
        (mcp_root / "r.pdf").write_bytes(b"data")
        ws = _make_workspace(files=[{"id": "f1"}])
        ws.file_providers[0].provider.upload_file.return_value = {"id": "u1", "title": "r.pdf"}
        with patch(f"{MODULE}._get_workspace", return_value=ws):
            upload_file("r.pdf")
        ws.file_providers[0].provider.upload_file.assert_called_once_with(
            str(mcp_root / "r.pdf"), parent_id=None, name="r.pdf"
        )


# ---------------------------------------------------------------------------
# Mode allowlists (SEC-02)
# ---------------------------------------------------------------------------


class TestModeAllowlists:
    def test_send_gmail_draft_is_dangerous_only(self):
        from iobox.modes import MCP_TOOLS_BY_MODE, AccessMode

        assert "send_gmail_draft" not in MCP_TOOLS_BY_MODE[AccessMode.readonly]
        assert "send_gmail_draft" not in MCP_TOOLS_BY_MODE[AccessMode.standard]
        assert "send_gmail_draft" in MCP_TOOLS_BY_MODE[AccessMode.dangerous]

    def test_standard_has_no_outbound_mail_tool(self):
        from iobox.modes import MCP_TOOLS_BY_MODE, AccessMode

        outbound = {"send_email", "send_gmail_draft", "forward_gmail", "batch_forward_gmail"}
        assert not outbound & MCP_TOOLS_BY_MODE[AccessMode.standard]

    def test_check_auth_standard_reports_no_send(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "standard")
        with (
            patch(f"{MODULE}.check_auth_status", return_value={"authenticated": True}),
        ):
            result = check_auth()
        assert result["available_write_ops"] is True
        assert result["available_send_ops"] is False
        assert "dangerous" in result["mode_hint"]

    def test_capabilities_match_registered_tools(self, monkeypatch):
        from iobox.mcp_server import _SEND_OP_TOOLS, _WRITE_OP_TOOLS, _mode_capabilities
        from iobox.modes import MCP_TOOLS_BY_MODE, AccessMode

        for mode in AccessMode:
            monkeypatch.setenv("IOBOX_MODE", mode.value)
            caps = _mode_capabilities()
            allowed = MCP_TOOLS_BY_MODE[mode]
            assert caps["available_send_ops"] == any(t in allowed for t in _SEND_OP_TOOLS)
            assert caps["available_write_ops"] == any(t in allowed for t in _WRITE_OP_TOOLS)


# ---------------------------------------------------------------------------
# Batch guard rails and partial failure (SEC-06, MCP-01)
# ---------------------------------------------------------------------------


def _batch_calls():
    """(tool, kwargs) for each destructive batch tool."""
    return [
        (batch_trash_gmail, {}),
        (batch_forward_gmail, {"to": "bob@example.com"}),
        (batch_modify_gmail_labels, {"archive": True}),
    ]


class TestBatchGuardRails:
    @pytest.mark.parametrize("query", ["", "   "])
    def test_empty_query_refused(self, query):
        for tool, extra in _batch_calls():
            provider = _make_provider()
            with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
                result = tool(query, **extra)
            assert "error" in result, tool.__name__
            provider.search_emails.assert_not_called()

    @pytest.mark.parametrize("days", [0, -3])
    def test_days_below_one_refused(self, days):
        for tool, extra in _batch_calls():
            provider = _make_provider()
            with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
                result = tool("from:x@y.com", days=days, **extra)
            assert "error" in result, tool.__name__
            provider.search_emails.assert_not_called()

    def test_forward_explicit_start_date_allows_days_zero(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_forward_gmail(
                "subject:x", "bob@example.com", days=0, start_date="2024/01/01"
            )
        assert result["forwarded_count"] == 1

    def test_invalid_date_refused(self):
        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_forward_gmail("subject:x", "bob@example.com", start_date="soon")
        assert "error" in result

    def test_max_results_clamped(self):
        for tool, extra in _batch_calls():
            provider = _make_provider()
            provider.search_emails.return_value = [{"message_id": f"m{i}"} for i in range(150)]
            with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
                result = tool("from:x@y.com", max_results=100000, **extra)
            query = provider.search_emails.call_args[0][0]
            assert query.max_results == 100, tool.__name__
            assert result["matched_count"] == 100
            assert "clamped" in result["detail"]

    def test_days_bounds_query(self):
        from datetime import date, timedelta

        provider = _make_provider()
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            batch_trash_gmail("from:x@y.com", days=3)
        query = provider.search_emails.call_args[0][0]
        assert query.after == date.today() - timedelta(days=3)


class TestBatchPartialFailure:
    def test_trash_continues_after_failure(self):
        provider = _make_provider()
        provider.search_emails.return_value = [
            {"message_id": "m1"},
            {"message_id": "m2"},
            {"message_id": "m3"},
        ]
        provider.trash.side_effect = [None, RuntimeError("rate limited"), None]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_trash_gmail("from:x@y.com")
        assert result["trashed_count"] == 2
        assert result["matched_count"] == 3
        assert result["succeeded"] == ["m1", "m3"]
        assert result["failed"] == [{"message_id": "m2", "error": "rate limited"}]

    def test_forward_continues_after_failure(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        provider.forward_message.side_effect = [RuntimeError("boom"), {"message_id": "f2"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_forward_gmail("from:x@y.com", "bob@example.com")
        assert result["forwarded_count"] == 1
        assert result["succeeded"] == ["m2"]
        assert result["failed"][0]["message_id"] == "m1"

    def test_modify_continues_after_failure(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        provider.archive.side_effect = [None, RuntimeError("gone")]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = batch_modify_gmail_labels("from:x@y.com", archive=True)
        assert result["modified_count"] == 1
        assert result["succeeded"] == ["m1"]
        assert result["failed"] == [{"message_id": "m2", "error": "gone"}]

    def test_save_by_query_reports_failed(self):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        provider.batch_get_emails.return_value = [
            {"message_id": "m1", "subject": "A", "from_": "x"},
            {"message_id": "m2", "error": "Not found"},
        ]
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.check_for_duplicates", return_value=[]),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# Email"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="email.md"),
        ):
            result = save_emails_by_query("in:inbox")
        assert result["saved_count"] == 1
        assert result["failed"] == [{"message_id": "m2", "error": "Not found"}]


# ---------------------------------------------------------------------------
# No interactive OAuth from the server (MCP-02)
# ---------------------------------------------------------------------------


class TestNoInteractiveAuth:
    def test_workspace_auth_status_matches_deduplicated_slot_names(self):
        """Legacy configs with duplicate slugs get renamed slots (x, x-2)."""
        from iobox.workspace import Workspace

        first = _entry("tim@gmail.com", scopes=("email",))
        second = _entry("tim@gmail.co.uk", scopes=("email",), number=2)
        second.slug = first.slug  # as written by an older iobox
        _give_token(first)
        _save_space("personal", [first, second])

        from iobox.space_config import load_space

        with patch("iobox.providers.google.email.GmailProvider.get_profile") as profile:
            profile.return_value = {"emailAddress": "tim@gmail.com"}
            ws = Workspace.from_config(load_space("personal"))
            with patch(f"{MODULE}._get_workspace", return_value=ws):
                result = workspace_auth_status()

        assert [s.name for s in ws.email_providers] == ["tim-gmail", "tim-gmail-2"]
        assert result["slots"]["tim-gmail"]["authenticated"] is True
        assert result["slots"]["tim-gmail-2"]["authenticated"] is False
        assert profile.call_count == 1

    def test_workspace_auth_status_skips_slots_without_token(self):
        authed = _entry("me@gmail.com", scopes=("email", "drive"))
        missing = _entry("other@gmail.com", scopes=("email",), number=2)
        _give_token(authed)
        _save_space("personal", [authed, missing])

        ws = MagicMock()
        ws.name = "personal"
        slots = {}
        for name, entry in (
            (authed.slug, authed),
            (f"{authed.slug}-drive", authed),
            (missing.slug, missing),
        ):
            s = MagicMock()
            s.name = name
            s.service_id = entry.id
            s.provider.get_profile.return_value = {"emailAddress": "x@y.com"}
            slots[name] = s
        ws.email_providers = [slots[authed.slug], slots[missing.slug]]
        ws.calendar_providers = []
        ws.file_providers = [slots[f"{authed.slug}-drive"]]

        with patch(f"{MODULE}._get_workspace", return_value=ws):
            result = workspace_auth_status()

        assert result["slots"][authed.slug]["authenticated"] is True
        assert result["slots"][f"{authed.slug}-drive"]["authenticated"] is True
        assert result["slots"][missing.slug]["authenticated"] is False
        assert "iobox space login" in result["slots"][missing.slug]["error"]
        slots[missing.slug].provider.get_profile.assert_not_called()

    def test_sync_uses_selected_provider_not_legacy_service(self, mcp_root):
        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m1"}]
        provider.batch_get_emails.return_value = [{"message_id": "m1", "from_": "x"}]
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.check_for_duplicates", return_value=[]),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# E"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="e.md"),
            patch("iobox.providers.google.auth.get_gmail_service") as legacy,
        ):
            result = save_emails_by_query("in:inbox", output_dir="sync", sync=True)
        assert result["saved_count"] == 1
        legacy.assert_not_called()

        from iobox.processing.file_manager import SyncState

        state = SyncState(str(mcp_root / "sync"))
        assert state.load()
        assert state.query == "in:inbox"
        assert state.synced_message_ids == ["m1"]
        assert state.last_sync_time is not None

    def test_incremental_sync_reuses_query_window_and_skips_synced(self, mcp_root):
        from datetime import date

        from iobox.processing.file_manager import SyncState

        out = mcp_root / "sync"
        out.mkdir()
        seeded = SyncState(str(out))
        seeded.query = "in:inbox"
        seeded.last_sync_time = "2026-10-20T08:00:00+00:00"
        seeded.synced_message_ids = ["m-old"]
        seeded.save()

        provider = _make_provider()
        provider.search_emails.return_value = [{"message_id": "m-old"}, {"message_id": "m-new"}]
        provider.batch_get_emails.return_value = [{"message_id": "m-new", "from_": "x"}]
        with (
            patch(f"{MODULE}._resolve_email_provider", return_value=provider),
            patch(f"{MODULE}.check_for_duplicates", return_value=[]),
            patch(f"{MODULE}.convert_email_to_markdown", return_value="# E"),
            patch(f"{MODULE}.save_email_to_markdown", return_value="e.md"),
        ):
            result = save_emails_by_query("in:inbox", output_dir="sync", sync=True)

        assert result["saved_count"] == 1
        assert result["skipped_count"] == 1
        query = provider.search_emails.call_args.args[0]
        assert query.text == "in:inbox"
        assert query.after == date(2026, 10, 19)
        assert provider.batch_get_emails.call_args.args[0] == ["m-new"]
        provider.get_new_messages.assert_not_called()


# ---------------------------------------------------------------------------
# get_emails alignment (MCP-03)
# ---------------------------------------------------------------------------


class TestGetEmailsAlignment:
    def test_dropped_id_reported_in_place(self):
        """Outlook-style: provider silently omits a missing ID."""
        provider = _make_provider()
        provider.batch_get_emails.return_value = [
            {"message_id": "m1", "from_": "a", "subject": "A"},
            {"message_id": "m3", "from_": "c", "subject": "C"},
        ]
        provider.get_email_content.side_effect = KeyError("m2 not found")
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "m2", "m3"])
        assert [r["message_id"] for r in result] == ["m1", "m2", "m3"]
        assert "error" in result[1]
        assert "error" not in result[0] and "error" not in result[2]

    def test_reordered_response_returned_in_input_order(self):
        provider = _make_provider()
        provider.batch_get_emails.return_value = [
            {"message_id": "m2", "from_": "b"},
            {"message_id": "m1", "from_": "a"},
        ]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "m2"])
        assert [r["from"] for r in result] == ["a", "b"]

    def test_dropped_id_recovered_by_single_fetch(self):
        provider = _make_provider()
        provider.batch_get_emails.return_value = [{"message_id": "m1", "from_": "a"}]
        provider.get_email_content.return_value = {"message_id": "m2", "from_": "b"}
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "m2"])
        assert result[1] == {"message_id": "m2", "from": "b"}

    def test_batch_exception_falls_back_per_message(self):
        provider = _make_provider()
        provider.batch_get_emails.side_effect = RuntimeError("batch endpoint down")

        def _one(mid, _ct):
            if mid == "bad":
                raise RuntimeError("nope")
            return {"message_id": mid, "from_": "x"}

        provider.get_email_content.side_effect = _one
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "bad", "m2"])
        assert [r["message_id"] for r in result] == ["m1", "bad", "m2"]
        assert result[1] == {"message_id": "bad", "error": "nope"}
        assert "error" not in result[0] and "error" not in result[2]

    def test_duplicate_ids_each_get_an_entry(self):
        provider = _make_provider()
        provider.batch_get_emails.return_value = [{"message_id": "m1", "from_": "a"}]
        with patch(f"{MODULE}._resolve_email_provider", return_value=provider):
            result = get_emails(["m1", "m1"])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# No accepted-but-ignored parameters (MCP-04)
# ---------------------------------------------------------------------------


class TestToolParameters:
    def test_every_tool_parameter_is_used(self):
        import ast
        import inspect
        import textwrap

        from iobox.mcp_server import _ALL_TOOLS

        unused = []
        for name, wrapper in _ALL_TOOLS.items():
            fn = inspect.unwrap(wrapper)
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
            func = tree.body[0]
            assert isinstance(func, ast.FunctionDef)
            used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
            unused += [f"{name}.{a.arg}" for a in func.args.args if a.arg not in used]
        assert unused == []

    def test_save_tools_drop_ignored_params(self):
        import inspect

        assert "include_spam_trash" not in inspect.signature(save_email).parameters
        params = inspect.signature(save_thread).parameters
        assert "include_spam_trash" not in params
        assert "prefer_html" not in params


# ---------------------------------------------------------------------------
# semantic_search_workspace with no index (MCP-06)
# ---------------------------------------------------------------------------


class TestSemanticSearchWorkspace:
    def test_missing_index_returns_clear_error_without_side_effects(self):
        import iobox.space_config as sc
        from iobox.mcp_server import semantic_search_workspace

        _save_space("personal", [_entry("me@gmail.com")], active=True)
        with (
            patch("iobox.processing.embed.get_backend") as get_backend,
            patch("iobox.processing.embed.semantic_search") as search,
        ):
            result = semantic_search_workspace("budget")
        assert len(result) == 1
        assert "No semantic index for workspace personal" in result[0]["error"]
        get_backend.assert_not_called()
        search.assert_not_called()
        assert not (sc.INDEXES_DIR / "personal").exists()

    def test_empty_index_returns_error(self):
        import sqlite3

        import iobox.space_config as sc
        from iobox.mcp_server import semantic_search_workspace

        _save_space("personal", [_entry("me@gmail.com")])
        db = sc.INDEXES_DIR / "personal" / "index.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE resource_embeddings (resource_id TEXT, workspace TEXT, "
            "resource_type TEXT, provider_id TEXT, content_hash TEXT, embedding_json TEXT)"
        )
        conn.commit()
        conn.close()
        with patch("iobox.processing.embed.semantic_search") as search:
            result = semantic_search_workspace("budget", workspace="personal")
        assert "No semantic index" in result[0]["error"]
        search.assert_not_called()

    def test_populated_index_searches(self):
        import sqlite3

        import iobox.space_config as sc
        from iobox.mcp_server import semantic_search_workspace

        _save_space("personal", [_entry("me@gmail.com")])
        db = sc.INDEXES_DIR / "personal" / "index.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE resource_embeddings (resource_id TEXT, workspace TEXT, "
            "resource_type TEXT, provider_id TEXT, content_hash TEXT, embedding_json TEXT)"
        )
        conn.execute(
            "INSERT INTO resource_embeddings VALUES ('r1', 'personal', 'email', 'p', 'h', '[]')"
        )
        conn.commit()
        conn.close()
        hits = [{"id": "r1", "resource_type": "email", "provider_id": "p", "score": 0.9}]
        with (
            patch("iobox.processing.embed.get_backend", return_value="backend"),
            patch("iobox.processing.embed.semantic_search", return_value=hits) as search,
        ):
            result = semantic_search_workspace("budget", workspace="personal")
        assert result == hits
        _, kwargs = search.call_args
        assert kwargs["credentials_dir"] == str(sc.IOBOX_HOME)

    def test_unknown_workspace_returns_error(self):
        from iobox.mcp_server import semantic_search_workspace

        result = semantic_search_workspace("budget", workspace="../../etc")
        assert "not found" in result[0]["error"]


# ---------------------------------------------------------------------------
# Fan-out results: slot tags, slot errors, unknown slots (WS-01, WS-02)
# ---------------------------------------------------------------------------


class TestFanOutSlotReporting:
    def _workspace(self):
        from iobox.workspace import ProviderSlot, Workspace

        ok = MagicMock()
        ok.list_events.return_value = [
            {"id": "e1", "title": "Standup", "start": "2026-11-02T09:00:00+00:00"}
        ]
        broken = MagicMock()
        broken.list_events.side_effect = RuntimeError("token revoked")
        return Workspace(
            name="personal",
            calendar_providers=[
                ProviderSlot(name="me-gmail-cal", provider=ok),
                ProviderSlot(name="work-gmail-cal", provider=broken),
            ],
        )

    def test_results_carry_slot_and_failed_slots_are_reported(self):
        from iobox.mcp_server import list_events

        with patch(f"{MODULE}._get_workspace", return_value=self._workspace()):
            result = list_events(after="2026-11-01")

        events = [r for r in result if "id" in r]
        errors = [r for r in result if "error" in r]
        assert [e["slot"] for e in events] == ["me-gmail-cal"]
        assert errors == [
            {"slot": "work-gmail-cal", "error": "Slot 'work-gmail-cal' failed: token revoked"}
        ]

    def test_unknown_provider_slot_is_an_error_not_empty(self):
        from iobox.mcp_server import list_events

        with patch(f"{MODULE}._get_workspace", return_value=self._workspace()):
            result = list_events(provider="wrok-gmail-cal")

        assert len(result) == 1
        assert "Unknown provider slot 'wrok-gmail-cal'" in result[0]["error"]
        assert "me-gmail-cal" in result[0]["error"]
