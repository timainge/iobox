"""
Unit tests for the command-line interface.

This module tests the functionality of the CLI module which provides
the user-facing command-line interface for the iobox application.

All commands now route through the provider abstraction layer.  Tests mock
``iobox.cli.get_provider`` to return a fake :class:`MagicMock` provider so that
no real Gmail or Outlook APIs are called.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from iobox.cli import app

# Create a CLI runner for testing Typer apps
runner = CliRunner()


def _mock_provider(**overrides) -> MagicMock:
    """Return a MagicMock that acts as an EmailProvider."""
    p = MagicMock()
    # Default return values for common methods
    p.search_emails.return_value = overrides.get("search_emails", [])
    p.get_email_content.return_value = overrides.get("get_email_content", {})
    p.batch_get_emails.return_value = overrides.get("batch_get_emails", [])
    p.get_thread.return_value = overrides.get("get_thread", [])
    p.send_message.return_value = overrides.get("send_message", {"message_id": "sent-1"})
    p.forward_message.return_value = overrides.get("forward_message", {"message_id": "fwd-1"})
    p.create_draft.return_value = overrides.get("create_draft", {"message_id": "draft-1"})
    p.list_drafts.return_value = overrides.get("list_drafts", [])
    p.send_draft.return_value = overrides.get("send_draft", {"message_id": "sent-draft"})
    p.delete_draft.return_value = overrides.get("delete_draft", {"message_id": "d1"})
    p.get_sync_state.return_value = overrides.get("get_sync_state", "hist-100")
    p.get_new_messages.return_value = overrides.get("get_new_messages", None)
    p.get_profile.return_value = overrides.get("get_profile", {})
    return p


class TestCliCommands:
    """Test cases for the CLI commands."""

    def test_version_command(self):
        """Test the version command."""
        with patch("iobox.cli.__version__", "0.1.0"):
            result = runner.invoke(app, ["version"])
            assert result.exit_code == 0
            assert "0.1.0" in result.stdout

    def test_search_command(self):
        """Test the search command."""
        mock_emails = [
            {
                "message_id": "message-id-1",
                "subject": "Test",
                "from_": "a@b.com",
                "date": "",
                "snippet": "First email snippet",
                "labels": [],
                "thread_id": "",
            }
        ]

        provider = _mock_provider(search_emails=mock_emails)
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app, ["search", "--query", "from:example.com", "--max-results", "5"]
            )

            assert result.exit_code == 0
            assert "message-id-1" in result.stdout
            assert "First email snippet" in result.stdout

    def test_search_command_no_results(self):
        """Test the search command with no results."""
        provider = _mock_provider(search_emails=[])
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["search", "--query", "from:nonexistent"])

            assert result.exit_code == 0
            assert "No emails found" in result.stdout

    def test_convert_command(self):
        """Test the save command (single email mode)."""
        mock_email_data = {
            "message_id": "message-id-1",
            "subject": "Test Subject",
            "body": "Email body content",
            "content_type": "text/plain",
            "from_": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100",
            "labels": [],
            "snippet": "",
            "thread_id": "",
        }
        mock_markdown = "# Test Subject\n\nEmail body content"
        mock_filepath = "/path/to/output/email.md"

        provider = _mock_provider(get_email_content=mock_email_data)
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.cli.convert_email_to_markdown", return_value=mock_markdown),
            patch("iobox.cli.save_email_to_markdown", return_value=mock_filepath),
            patch("iobox.cli.create_output_directory", return_value="./output"),
        ):
            result = runner.invoke(
                app, ["save", "--message-id", "message-id-1", "--output-dir", "./output"]
            )

            assert result.exit_code == 0
            assert "Successfully saved email" in result.stdout

    def test_batch_convert_command(self):
        """Test the save command in batch mode."""
        mock_search = [
            {
                "message_id": "message-id-1",
                "subject": "First email",
                "snippet": "First email snippet",
                "from_": "sender@example.com",
                "date": "",
                "labels": [],
                "thread_id": "",
            },
            {
                "message_id": "message-id-2",
                "subject": "Second email",
                "snippet": "Second email snippet",
                "from_": "sender@example.com",
                "date": "",
                "labels": [],
                "thread_id": "",
            },
        ]

        mock_batch_results = [
            {
                "message_id": "message-id-1",
                "subject": "First email",
                "body": "Email body content",
                "content_type": "text/plain",
                "from_": "sender@example.com",
                "date": "Mon, 23 Mar 2025 10:00:00 +1100",
                "labels": [],
                "attachments": [],
                "snippet": "First email snippet",
                "thread_id": "thread-1",
            },
            {
                "message_id": "message-id-2",
                "subject": "Second email",
                "body": "Another body",
                "content_type": "text/plain",
                "from_": "sender@example.com",
                "date": "Mon, 24 Mar 2025 10:00:00 +1100",
                "labels": [],
                "attachments": [],
                "snippet": "Second email snippet",
                "thread_id": "thread-2",
            },
        ]

        mock_markdown = "# Test Subject\n\nEmail body content"
        mock_filepath = "/path/to/output/email.md"

        provider = _mock_provider(
            search_emails=mock_search,
            batch_get_emails=mock_batch_results,
        )
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.cli.convert_email_to_markdown", return_value=mock_markdown),
            patch("iobox.cli.save_email_to_markdown", return_value=mock_filepath),
            patch("iobox.cli.create_output_directory", return_value="./output"),
            patch("iobox.cli.check_for_duplicates", return_value=[]),
        ):
            result = runner.invoke(
                app,
                ["save", "--query", "from:example.com", "--max", "5", "--output-dir", "./output"],
            )

            assert result.exit_code == 0
            assert "Searching for emails matching" in result.stdout

    def test_auth_status_outlook_uses_account_flag(self):
        mock_status = {
            "authenticated": True,
            "client_id_configured": True,
            "tenant_id": "common",
            "token_file_exists": True,
            "token_path": "/tokens/corp@company.com/o365_token.txt",
        }
        with (
            patch("iobox.cli.get_provider", return_value=_mock_provider()),
            patch(
                "iobox.providers.o365.auth.check_outlook_auth_status", return_value=mock_status
            ) as mock_check,
        ):
            result = runner.invoke(
                app, ["--provider", "outlook", "--account", "corp@company.com", "auth-status"]
            )

        assert result.exit_code == 0
        mock_check.assert_called_once_with(account="corp@company.com")

    def test_auth_status_command(self):
        """Test the auth-status command."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/path/to/credentials.json",
            "token_path": "/path/to/token.json",
        }
        mock_profile = {
            "emailAddress": "test@gmail.com",
            "messagesTotal": 1000,
            "threadsTotal": 500,
        }

        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service") as mock_service,
            patch("iobox.providers.google.auth.get_gmail_profile", return_value=mock_profile),
        ):
            mock_service.return_value = MagicMock()
            result = runner.invoke(app, ["auth-status"])

            assert result.exit_code == 0
            assert "Authentication Status" in result.stdout
            assert "Authenticated: True" in result.stdout
            assert "Credentials file exists: True" in result.stdout
            assert "Token file exists: True" in result.stdout

    def test_forward_single_email(self):
        """Test forwarding a single email by message ID."""
        provider = _mock_provider(forward_message={"message_id": "fwd-1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "forward",
                    "--message-id",
                    "msg-123",
                    "--to",
                    "bob@example.com",
                ],
            )

            assert result.exit_code == 0
            assert "Successfully forwarded" in result.stdout

    def test_forward_batch(self):
        """Test forwarding multiple emails via query."""
        _e = {"from_": "", "date": "", "snippet": "", "labels": [], "thread_id": ""}
        mock_emails = [
            {"message_id": "m1", "subject": "First", **_e},
            {"message_id": "m2", "subject": "Second", **_e},
        ]

        provider = _mock_provider(
            search_emails=mock_emails, forward_message={"message_id": "fwd-x"}
        )
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "forward",
                    "--query",
                    "from:test@example.com",
                    "--to",
                    "bob@example.com",
                    "--yes",
                ],
            )

            assert result.exit_code == 0
            assert "Forwarded 2 emails" in result.stdout

    def test_forward_no_query_or_id(self):
        """Test forward command fails without --message-id or --query."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "forward",
                    "--to",
                    "bob@example.com",
                ],
            )

            assert result.exit_code == 1

    def test_send_with_body(self):
        """Test sending an email with inline body."""
        provider = _mock_provider(send_message={"message_id": "sent-1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "send",
                    "--to",
                    "bob@example.com",
                    "--subject",
                    "Hello",
                    "--body",
                    "Hi there",
                ],
            )

            assert result.exit_code == 0
            assert "Email sent successfully" in result.stdout
            provider.send_message.assert_called_once_with(
                to="bob@example.com",
                subject="Hello",
                body="Hi there",
                cc=None,
                bcc=None,
                content_type="plain",
                attachments=None,
            )

    def test_send_with_body_file(self, tmp_path):
        """Test sending an email with body from file."""
        body_file = tmp_path / "body.txt"
        body_file.write_text("File body content")

        provider = _mock_provider(send_message={"message_id": "sent-2"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "send",
                    "--to",
                    "bob@example.com",
                    "--subject",
                    "Hello",
                    "--body-file",
                    str(body_file),
                ],
            )

            assert result.exit_code == 0
            assert "Email sent successfully" in result.stdout
            provider.send_message.assert_called_once_with(
                to="bob@example.com",
                subject="Hello",
                body="File body content",
                cc=None,
                bcc=None,
                content_type="plain",
                attachments=None,
            )

    def test_send_html_flag(self):
        """Test send with --html flag sets content_type to html."""
        provider = _mock_provider(send_message={"message_id": "sent-3"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "send",
                    "--to",
                    "bob@example.com",
                    "--subject",
                    "Hello HTML",
                    "--body",
                    "<b>Hi</b>",
                    "--html",
                ],
            )

            assert result.exit_code == 0
            assert "Email sent successfully" in result.stdout
            provider.send_message.assert_called_once_with(
                to="bob@example.com",
                subject="Hello HTML",
                body="<b>Hi</b>",
                cc=None,
                bcc=None,
                content_type="html",
                attachments=None,
            )

    def test_send_no_body(self):
        """Test send command fails without --body or --body-file."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "send",
                    "--to",
                    "bob@example.com",
                    "--subject",
                    "Hello",
                ],
            )

            assert result.exit_code == 1


class TestNewCliFeatures:
    """Tests for Phase 2/3 CLI additions."""

    # ------------------------------------------------------------------
    # auth-status with profile
    # ------------------------------------------------------------------

    def test_auth_status_with_profile(self):
        """auth-status shows Gmail profile when auth succeeds."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }
        mock_profile = {
            "emailAddress": "user@gmail.com",
            "messagesTotal": 66327,
            "threadsTotal": 13902,
        }

        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service") as mock_svc,
            patch("iobox.providers.google.auth.get_gmail_profile", return_value=mock_profile),
        ):
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, ["auth-status"])

        assert result.exit_code == 0
        assert "Gmail Profile" in result.stdout
        assert "user@gmail.com" in result.stdout
        assert "66,327" in result.stdout
        assert "13,902" in result.stdout

    def test_auth_status_profile_fallback(self):
        """auth-status shows base info even when profile fetch fails."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }

        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch(
                "iobox.providers.google.auth.get_gmail_service",
                side_effect=Exception("Auth failed"),
            ),
        ):
            result = runner.invoke(app, ["auth-status"])

        assert result.exit_code == 0
        assert "Authentication Status" in result.stdout
        assert "Authenticated: True" in result.stdout
        # Profile section should not appear
        assert "Gmail Profile" not in result.stdout

    # ------------------------------------------------------------------
    # save --thread-id
    # ------------------------------------------------------------------

    def test_save_with_thread_id(self, tmp_path):
        """save --thread-id writes a single thread markdown file."""
        mock_messages = [
            {
                "message_id": "msg-1",
                "thread_id": "thread-abc",
                "subject": "Test Thread",
                "from_": "a@example.com",
                "to": "b@example.com",
                "date": "Mon, 01 Jan 2024 00:00:00 +0000",
                "labels": ["INBOX"],
                "body": "Hello",
                "content_type": "text/plain",
                "snippet": "",
            }
        ]
        mock_md = "---\nthread_id: thread-abc\n---\n\n## From: a@example.com — Mon\n\nHello"

        provider = _mock_provider(get_thread=mock_messages)
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.cli.convert_thread_to_markdown", return_value=mock_md),
            patch("iobox.cli.create_output_directory", return_value=str(tmp_path)),
        ):
            result = runner.invoke(
                app, ["save", "--thread-id", "thread-abc", "--output-dir", str(tmp_path)]
            )

        assert result.exit_code == 0
        assert "Successfully saved thread" in result.stdout

    # ------------------------------------------------------------------
    # search --include-spam-trash
    # ------------------------------------------------------------------

    def test_search_include_spam_trash(self):
        """search --include-spam-trash passes flag via EmailQuery."""
        mock_emails = [
            {
                "message_id": "m1",
                "subject": "Spam Email",
                "from_": "x@y.com",
                "date": "",
                "snippet": "spam",
                "labels": [],
                "thread_id": "",
            }
        ]

        provider = _mock_provider(search_emails=mock_emails)
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["search", "--query", "in:spam", "--include-spam-trash"])

        assert result.exit_code == 0
        call_args = provider.search_emails.call_args[0][0]  # EmailQuery positional arg
        assert call_args.include_spam_trash is True

    # ------------------------------------------------------------------
    # label command
    # ------------------------------------------------------------------

    def test_label_mark_read(self):
        """label --mark-read calls provider.mark_read()."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["label", "--message-id", "msg-1", "--mark-read"])

        assert result.exit_code == 0
        provider.mark_read.assert_called_once_with("msg-1", read=True)

    def test_label_add_custom(self):
        """label --add 'Newsletter' calls provider.add_tag()."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["label", "--message-id", "msg-1", "--add", "Newsletter"])

        assert result.exit_code == 0
        provider.add_tag.assert_called_once_with("msg-1", "Newsletter")

    def test_label_no_message_or_query(self):
        """label without --message-id or --query exits with error."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["label", "--mark-read"])

        assert result.exit_code == 1

    # ------------------------------------------------------------------
    # trash command
    # ------------------------------------------------------------------

    def test_trash_single(self):
        """trash --message-id trashes the message without confirmation."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["--mode", "dangerous", "trash", "--message-id", "msg-1"])

        assert result.exit_code == 0
        provider.trash.assert_called_once_with("msg-1")
        assert "Trashed" in result.stdout

    def test_trash_batch_confirm(self):
        """trash --query prompts for confirmation before trashing."""
        _e = {"from_": "", "date": "", "snippet": "", "labels": [], "thread_id": ""}
        mock_emails = [
            {"message_id": "m1", "subject": "Old Email", **_e},
            {"message_id": "m2", "subject": "Another Old", **_e},
        ]

        provider = _mock_provider(search_emails=mock_emails)
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app, ["--mode", "dangerous", "trash", "--query", "older_than:1y"], input="y\n"
            )

        assert result.exit_code == 0
        assert provider.trash.call_count == 2

    def test_trash_batch_abort(self):
        """trash --query with 'n' input aborts without trashing."""
        _e = {"from_": "", "date": "", "snippet": "", "labels": [], "thread_id": ""}
        mock_emails = [
            {"message_id": "m1", "subject": "Old", **_e},
        ]

        provider = _mock_provider(search_emails=mock_emails)
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app, ["--mode", "dangerous", "trash", "--query", "older_than:1y"], input="n\n"
            )

        assert result.exit_code == 0
        provider.trash.assert_not_called()
        assert "Aborted" in result.stdout


class TestSyncFlag:
    """Tests for the --sync flag on the save command."""

    def _mock_email_data(self, msg_id="m1"):
        return {
            "message_id": msg_id,
            "subject": "Test Subject",
            "body": "body",
            "content_type": "text/plain",
            "from_": "a@b.com",
            "date": "Mon, 01 Jan 2024 00:00:00 +0000",
            "labels": [],
            "attachments": [],
            "snippet": "snip",
            "thread_id": "thread-1",
        }

    def _search_hit(self, msg_id):
        return {
            "message_id": msg_id,
            "from_": "",
            "date": "",
            "snippet": "",
            "subject": "Test",
            "labels": [],
            "thread_id": "",
        }

    def _run_save(self, provider, out, *extra):
        import logging

        # These tests run the real file manager, which logs at INFO. With the
        # project's `log_cli = true`, pytest's live-log handler suspends/resumes
        # capture mid-invoke and closes CliRunner's output stream, so silence
        # INFO logging for the duration of the invocation.
        logging.disable(logging.INFO)
        try:
            with patch("iobox.cli.get_provider", return_value=provider):
                args = ["save", "--query", "from:boss@x.com", "--output-dir", str(out)]
                return runner.invoke(app, [*args, "--sync", *extra])
        finally:
            logging.disable(logging.NOTSET)

    def test_first_run_records_query_and_saved_ids(self, tmp_path):
        from iobox.processing.file_manager import SyncState

        provider = _mock_provider(
            search_emails=[self._search_hit("m1")],
            batch_get_emails=[self._mock_email_data("m1")],
        )
        result = self._run_save(provider, tmp_path)

        assert result.exit_code == 0, result.output
        state = SyncState(str(tmp_path))
        assert state.load()
        assert state.query == "from:boss@x.com"
        assert state.synced_message_ids == ["m1"]
        assert state.last_sync_time is not None
        provider.get_new_messages.assert_not_called()

    def test_incremental_run_reuses_query_with_window_and_skips_synced(self, tmp_path):
        from datetime import date

        from iobox.processing.file_manager import SyncState

        state = SyncState(str(tmp_path))
        state.query = "from:boss@x.com"
        state.last_sync_time = "2026-10-20T08:00:00+00:00"
        state.synced_message_ids = ["m-old"]
        state.save()

        provider = _mock_provider(
            search_emails=[self._search_hit("m-old"), self._search_hit("m-new")],
            batch_get_emails=[self._mock_email_data("m-new")],
        )
        result = self._run_save(provider, tmp_path)

        assert result.exit_code == 0, result.output
        query = provider.search_emails.call_args.args[0]
        assert query.raw_query == "from:boss@x.com"  # SYNC-01: query is honoured
        assert query.after == date(2026, 10, 19)  # day before last complete run
        provider.batch_get_emails.assert_called_once()
        assert provider.batch_get_emails.call_args.args[0] == ["m-new"]
        reloaded = SyncState(str(tmp_path))
        reloaded.load()
        assert set(reloaded.synced_message_ids) == {"m-old", "m-new"}
        assert reloaded.last_sync_time > "2026-10-20T08:00:00+00:00"

    def test_changed_query_runs_full_sync(self, tmp_path):
        from iobox.processing.file_manager import SyncState

        state = SyncState(str(tmp_path))
        state.query = "from:someone-else@x.com"
        state.last_sync_time = "2026-10-20T08:00:00+00:00"
        state.save()

        provider = _mock_provider(search_emails=[])
        result = self._run_save(provider, tmp_path, "-d", "30")

        assert result.exit_code == 0, result.output
        assert "Query changed" in result.output
        query = provider.search_emails.call_args.args[0]
        assert query.after != date_type_day_before("2026-10-20")

    def test_failed_message_does_not_advance_window(self, tmp_path):
        from iobox.processing.file_manager import SyncState

        provider = _mock_provider(
            search_emails=[self._search_hit("m1"), self._search_hit("m2")],
            batch_get_emails=[
                self._mock_email_data("m1"),
                {"message_id": "m2", "error": "boom"},
            ],
        )
        result = self._run_save(provider, tmp_path)

        assert result.exit_code == 0, result.output
        state = SyncState(str(tmp_path))
        state.load()
        assert state.synced_message_ids == ["m1"]
        assert state.last_sync_time is None
        assert "will be retried" in result.output

    def test_truncated_results_do_not_advance_window(self, tmp_path):
        from iobox.processing.file_manager import SyncState

        provider = _mock_provider(
            search_emails=[self._search_hit("m1")],
            batch_get_emails=[self._mock_email_data("m1")],
        )
        result = self._run_save(provider, tmp_path, "--max", "1")

        assert result.exit_code == 0, result.output
        state = SyncState(str(tmp_path))
        state.load()
        assert state.last_sync_time is None
        assert "not advanced" in result.output


def date_type_day_before(iso_day: str):
    from datetime import date, timedelta

    return date.fromisoformat(iso_day) - timedelta(days=1)


class TestDraftCommands:
    """Test cases for draft CLI commands."""

    def test_draft_create_command(self):
        """Test draft-create command creates a draft."""
        provider = _mock_provider(create_draft={"message_id": "draft-1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "draft-create",
                    "--to",
                    "bob@example.com",
                    "--subject",
                    "Draft Subject",
                    "--body",
                    "Draft body",
                ],
            )

            assert result.exit_code == 0
            assert "Draft created successfully" in result.stdout
            assert "draft-1" in result.stdout
            provider.create_draft.assert_called_once()

    def test_draft_create_passes_attachments(self, tmp_path):
        attachment = tmp_path / "report.pdf"
        attachment.write_bytes(b"%PDF")
        provider = _mock_provider(create_draft={"message_id": "draft-1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "draft-create",
                    "--to",
                    "bob@example.com",
                    "--subject",
                    "Report",
                    "--body",
                    "Attached.",
                    "--attach",
                    str(attachment),
                ],
            )

        assert result.exit_code == 0
        _, kwargs = provider.create_draft.call_args
        assert kwargs["attachments"] == [str(attachment)]

    def test_draft_list_command(self):
        """Test draft-list command lists drafts."""
        mock_drafts = [
            {"message_id": "draft-1", "subject": "First Draft", "snippet": "First snippet"},
            {"message_id": "draft-2", "subject": "Second Draft", "snippet": "Second snippet"},
        ]

        provider = _mock_provider(list_drafts=mock_drafts)
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["draft-list"])

            assert result.exit_code == 0
            assert "draft-1" in result.stdout
            assert "First Draft" in result.stdout
            assert "draft-2" in result.stdout

    def test_draft_list_empty(self):
        """Test draft-list when no drafts exist."""
        provider = _mock_provider(list_drafts=[])
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["draft-list"])

            assert result.exit_code == 0
            assert "No drafts found" in result.stdout

    def test_draft_send_command(self):
        """Test draft-send command sends a draft."""
        provider = _mock_provider(send_draft={"message_id": "sent-from-draft"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "draft-send",
                    "--draft-id",
                    "draft-1",
                ],
            )

            assert result.exit_code == 0
            assert "Draft sent successfully" in result.stdout
            provider.send_draft.assert_called_once_with("draft-1")

    def test_draft_delete_command(self):
        """Test draft-delete command deletes a draft."""
        provider = _mock_provider(delete_draft={"status": "deleted", "message_id": "draft-1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "draft-delete",
                    "--draft-id",
                    "draft-1",
                ],
            )

            assert result.exit_code == 0
            assert "Draft deleted successfully" in result.stdout
            provider.delete_draft.assert_called_once_with("draft-1")


class TestModeGating:
    """Tests for --mode command gating."""

    def test_default_mode_is_standard(self):
        """Default mode allows draft-create but blocks send."""
        provider = _mock_provider(create_draft={"message_id": "d1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                ["draft-create", "--to", "a@b.com", "--subject", "x", "--body", "y"],
            )
        assert result.exit_code == 0

    def test_readonly_blocks_send(self):
        """send is blocked in readonly mode."""
        result = runner.invoke(
            app,
            ["--mode", "readonly", "send", "--to", "a@b.com", "--subject", "x", "--body", "y"],
        )
        assert result.exit_code == 1
        assert "not allowed in 'readonly' mode" in result.stderr

    def test_readonly_blocks_label(self):
        """label is blocked in readonly mode."""
        result = runner.invoke(
            app,
            ["--mode", "readonly", "label", "--message-id", "m1", "--mark-read"],
        )
        assert result.exit_code == 1
        assert "not allowed in 'readonly' mode" in result.stderr

    def test_readonly_blocks_trash(self):
        """trash is blocked in readonly mode."""
        result = runner.invoke(
            app,
            ["--mode", "readonly", "trash", "--message-id", "m1"],
        )
        assert result.exit_code == 1
        assert "not allowed in 'readonly' mode" in result.stderr

    def test_readonly_allows_search(self):
        """search is allowed in readonly mode."""
        mock_emails = [
            {
                "message_id": "m1",
                "subject": "Test",
                "from_": "a@b.com",
                "date": "",
                "snippet": "snip",
                "labels": [],
                "thread_id": "",
            }
        ]
        provider = _mock_provider(search_emails=mock_emails)
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["--mode", "readonly", "search", "--query", "test"])
        assert result.exit_code == 0

    def test_readonly_allows_version(self):
        """version is allowed in readonly mode."""
        result = runner.invoke(app, ["--mode", "readonly", "version"])
        assert result.exit_code == 0

    def test_mode_error_suggests_lowest_sufficient_mode(self):
        """A standard-tier command blocked in readonly suggests --mode standard."""
        result = runner.invoke(
            app,
            ["--mode", "readonly", "label", "--message-id", "m1", "--mark-read"],
        )
        assert result.exit_code == 1
        assert "Use --mode standard" in result.stderr

    def test_mode_error_suggests_dangerous_for_send(self):
        result = runner.invoke(
            app,
            ["--mode", "standard", "send", "--to", "a@b.com", "--subject", "x", "--body", "y"],
        )
        assert result.exit_code == 1
        assert "Use --mode dangerous" in result.stderr

    def test_standard_blocks_trash(self):
        """trash is blocked in standard mode."""
        result = runner.invoke(
            app,
            ["--mode", "standard", "trash", "--message-id", "m1"],
        )
        assert result.exit_code == 1
        assert "not allowed in 'standard' mode" in result.stderr

    def test_standard_blocks_send(self):
        """send is blocked in standard mode."""
        result = runner.invoke(
            app,
            ["--mode", "standard", "send", "--to", "a@b.com", "--subject", "x", "--body", "y"],
        )
        assert result.exit_code == 1
        assert "not allowed in 'standard' mode" in result.stderr

    def test_standard_blocks_forward(self):
        """forward is blocked in standard mode."""
        result = runner.invoke(
            app,
            ["--mode", "standard", "forward", "--message-id", "m1", "--to", "a@b.com"],
        )
        assert result.exit_code == 1
        assert "not allowed in 'standard' mode" in result.stderr

    def test_dangerous_allows_send(self):
        """send is allowed in dangerous mode."""
        provider = _mock_provider(send_message={"message_id": "sent-1"})
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "dangerous",
                    "send",
                    "--to",
                    "a@b.com",
                    "--subject",
                    "x",
                    "--body",
                    "y",
                ],
            )
        assert result.exit_code == 0
        assert "Email sent successfully" in result.stdout

    def test_dangerous_allows_trash(self):
        """trash is allowed in dangerous mode."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                ["--mode", "dangerous", "trash", "--message-id", "m1"],
            )
        assert result.exit_code == 0
        assert "Trashed" in result.stdout

    def test_invalid_mode(self):
        """Invalid mode value exits with error."""
        result = runner.invoke(app, ["--mode", "invalid", "version"])
        assert result.exit_code == 1
        assert "Invalid mode" in result.stderr

    def test_auth_status_shows_mode(self):
        """auth-status displays the current access mode."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }
        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service", side_effect=Exception("skip")),
        ):
            result = runner.invoke(app, ["--mode", "readonly", "auth-status"])
        assert result.exit_code == 0
        assert "Access mode: readonly" in result.stdout


class TestAccountFlag:
    """Tests for --account CLI flag."""

    def test_account_flag_passed(self):
        """--account flag is stored in context and shown in auth-status."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }
        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service", side_effect=Exception("skip")),
        ):
            result = runner.invoke(app, ["--account", "work", "auth-status"])
        assert result.exit_code == 0
        assert "Account: work" in result.stdout

    def test_default_account(self):
        """Without --account flag, defaults to 'default'."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }
        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service", side_effect=Exception("skip")),
        ):
            result = runner.invoke(app, ["auth-status"])
        assert result.exit_code == 0
        assert "Account: default" in result.stdout

    def test_account_with_envvar(self, monkeypatch):
        """IOBOX_ACCOUNT env var is used when --account is not passed."""
        monkeypatch.setenv("IOBOX_ACCOUNT", "personal")
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }
        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service", side_effect=Exception("skip")),
        ):
            result = runner.invoke(app, ["auth-status"])
        assert result.exit_code == 0
        assert "Account: personal" in result.stdout


class TestProviderFlag:
    """Tests for the --provider CLI flag."""

    def test_default_provider_is_gmail(self):
        """Default provider is gmail."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider) as mock_gp:
            result = runner.invoke(app, ["draft-list"])
        assert result.exit_code == 0
        mock_gp.assert_called_once_with("gmail")

    def test_provider_flag_outlook(self):
        """--provider outlook is passed to get_provider."""
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider) as mock_gp:
            result = runner.invoke(app, ["--provider", "outlook", "draft-list"])
        assert result.exit_code == 0
        mock_gp.assert_called_once_with("outlook")

    def test_provider_env_var(self, monkeypatch):
        """IOBOX_PROVIDER env var sets the default provider."""
        monkeypatch.setenv("IOBOX_PROVIDER", "outlook")
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider) as mock_gp:
            result = runner.invoke(app, ["draft-list"])
        assert result.exit_code == 0
        mock_gp.assert_called_once_with("outlook")

    def test_invalid_provider(self):
        """Invalid provider name exits with an error."""
        with patch("iobox.cli.get_provider", side_effect=ValueError("Unknown provider 'bogus'")):
            result = runner.invoke(app, ["--provider", "bogus", "draft-list"])
        assert result.exit_code == 1
        assert "Unknown provider" in result.stderr

    def test_missing_outlook_dependency(self):
        """Missing O365 package exits with install hint."""
        with patch(
            "iobox.cli.get_provider",
            side_effect=ImportError("Install them with: pip install 'iobox[outlook]'"),
        ):
            result = runner.invoke(app, ["--provider", "outlook", "draft-list"])
        assert result.exit_code == 1
        assert "iobox[outlook]" in result.stderr

    def test_provider_not_created_for_non_email_commands(self):
        """Workspace/utility commands don't instantiate the global email provider."""
        with patch("iobox.cli.get_provider", side_effect=ImportError("no O365")) as mock_gp:
            result = runner.invoke(app, ["--provider", "outlook", "version"])
        assert result.exit_code == 0
        mock_gp.assert_not_called()

    def test_auth_status_shows_provider(self):
        """auth-status displays the current provider name."""
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/p/credentials.json",
            "token_path": "/p/token.json",
        }
        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.google.auth.check_auth_status", return_value=mock_status),
            patch("iobox.providers.google.auth.get_gmail_service", side_effect=Exception("skip")),
        ):
            result = runner.invoke(app, ["auth-status"])
        assert result.exit_code == 0
        assert "Provider: gmail" in result.stdout


class TestValidationExits:
    """Validation exits print one clean message, not a wrapped 'Error ...: ' line (CLI-06)."""

    def _invoke(self, args: list[str]):
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            return runner.invoke(app, args)

    def test_save_without_target(self):
        result = self._invoke(["save"])
        assert result.exit_code == 1
        assert "You must specify --message-id" in result.output
        assert "Error saving emails" not in result.output

    def test_forward_without_target(self):
        result = self._invoke(["--mode", "dangerous", "forward", "--to", "a@b.com"])
        assert result.exit_code == 1
        assert "Error forwarding emails" not in result.output

    def test_send_without_body(self):
        result = self._invoke(["--mode", "dangerous", "send", "--to", "a@b.com", "-s", "x"])
        assert result.exit_code == 1
        assert "You must specify either --body" in result.output
        assert "Error sending email" not in result.output

    def test_send_missing_body_file(self, tmp_path):
        missing = str(tmp_path / "nope.txt")
        result = self._invoke(
            ["--mode", "dangerous", "send", "--to", "a@b.com", "-s", "x", "-f", missing]
        )
        assert result.exit_code == 1
        assert "File not found" in result.output
        assert "Error sending email" not in result.output

    def test_draft_create_missing_attachment(self, tmp_path):
        missing = str(tmp_path / "nope.pdf")
        result = self._invoke(
            ["draft-create", "--to", "a@b.com", "-s", "x", "-b", "y", "--attach", missing]
        )
        assert result.exit_code == 1
        assert "Attachment file not found" in result.output
        assert "Error creating draft" not in result.output

    def test_label_without_target(self):
        result = self._invoke(["label", "--star"])
        assert result.exit_code == 1
        assert "Error updating labels" not in result.output

    def test_provider_error_still_reported(self):
        provider = _mock_provider()
        provider.send_message.side_effect = RuntimeError("boom")
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app, ["--mode", "dangerous", "send", "--to", "a@b.com", "-s", "x", "-b", "y"]
            )
        assert result.exit_code == 1
        assert "Error sending email: boom" in result.output


class TestForwardBatchSafety:
    """Batch forward confirms first and reports partial failures (CLI-01)."""

    _e = {"from_": "", "date": "", "snippet": "", "labels": [], "thread_id": ""}

    def _emails(self, n: int = 2):
        return [{"message_id": f"m{i}", "subject": f"S{i}", **self._e} for i in range(1, n + 1)]

    def _args(self, *extra: str) -> list[str]:
        return ["--mode", "dangerous", "forward", "-q", "x", "--to", "bob@example.com", *extra]

    def test_prompts_with_count_and_recipient(self):
        provider = _mock_provider(search_emails=self._emails())
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, self._args(), input="y\n")
        assert result.exit_code == 0
        assert "Forward 2 email(s) to bob@example.com?" in result.output
        assert provider.forward_message.call_count == 2

    def test_declining_aborts_without_forwarding(self):
        provider = _mock_provider(search_emails=self._emails())
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, self._args(), input="n\n")
        assert "Aborted." in result.output
        provider.forward_message.assert_not_called()

    def test_yes_skips_prompt(self):
        provider = _mock_provider(search_emails=self._emails())
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, self._args("-y"))
        assert result.exit_code == 0
        assert "Forward 2 email(s) to" not in result.output
        assert provider.forward_message.call_count == 2

    def test_partial_failure_reported_and_exit_1(self):
        provider = _mock_provider(search_emails=self._emails(3))
        provider.forward_message.side_effect = [
            {"message_id": "f1"},
            RuntimeError("quota"),
            {"message_id": "f3"},
        ]
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, self._args("--yes"))
        assert result.exit_code == 1
        assert provider.forward_message.call_count == 3
        assert "Forwarded 2 emails" in result.output
        assert "Failed to forward m2: quota" in result.stderr
        assert "1 email(s) failed to forward." in result.stderr

    def test_single_mode_does_not_prompt(self):
        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app, ["--mode", "dangerous", "forward", "-m", "m1", "--to", "bob@example.com"]
            )
        assert result.exit_code == 0
        provider.forward_message.assert_called_once()


class TestLabelValidation:
    """label rejects no-op and contradictory flag combinations (CLI-03)."""

    def _invoke(self, args: list[str]):
        provider = _mock_provider(search_emails=[{"message_id": "m1"}])
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(app, ["label", *args])
        return result, provider

    def test_no_operation_flag_errors(self):
        result, provider = self._invoke(["-q", "from:x@y.com"])
        assert result.exit_code == 1
        assert "Specify at least one operation" in result.stderr
        provider.search_emails.assert_not_called()

    def test_no_operation_flag_single_mode(self):
        result, provider = self._invoke(["--message-id", "m1"])
        assert result.exit_code == 1
        assert "Labels updated" not in result.output

    def test_mark_read_and_unread_rejected(self):
        result, provider = self._invoke(["--message-id", "m1", "--mark-read", "--mark-unread"])
        assert result.exit_code == 1
        assert "--mark-read and --mark-unread cannot be used together" in result.stderr
        provider.mark_read.assert_not_called()

    def test_star_and_unstar_rejected(self):
        result, provider = self._invoke(["-q", "x", "--star", "--unstar"])
        assert result.exit_code == 1
        assert "--star and --unstar cannot be used together" in result.stderr
        provider.set_star.assert_not_called()

    def test_valid_combination_allowed(self):
        result, provider = self._invoke(["--message-id", "m1", "--mark-read", "--star"])
        assert result.exit_code == 0
        provider.mark_read.assert_called_once_with("m1", read=True)
        provider.set_star.assert_called_once_with("m1", starred=True)


class TestUntrashBatch:
    """trash --untrash in query mode searches the trash (CLI-02)."""

    def _run(self, args: list[str], global_args: list[str] | None = None):
        provider = _mock_provider(search_emails=[{"message_id": "m1"}])
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app,
                [*(global_args or []), "--mode", "dangerous", "trash", *args],
                input="y\n",
            )
        return result, provider

    def test_untrash_includes_trash_and_scopes_gmail_query(self):
        result, provider = self._run(["-q", "from:x@y.com", "--untrash"])
        assert result.exit_code == 0, result.output
        eq = provider.search_emails.call_args[0][0]
        assert eq.include_spam_trash is True
        assert eq.raw_query == "in:trash from:x@y.com"
        provider.untrash.assert_called_once_with("m1")

    def test_untrash_keeps_explicit_in_operator(self):
        _, provider = self._run(["-q", "in:anywhere from:x@y.com", "--untrash"])
        eq = provider.search_emails.call_args[0][0]
        assert eq.raw_query == "in:anywhere from:x@y.com"
        assert eq.include_spam_trash is True

    def test_untrash_domain_operator_is_not_in_operator(self):
        _, provider = self._run(["-q", "from:(domain:example.com)", "--untrash"])
        eq = provider.search_emails.call_args[0][0]
        assert eq.raw_query.startswith("in:trash ")

    def test_untrash_outlook_does_not_rewrite_query(self):
        _, provider = self._run(["-q", "invoice", "--untrash"], ["--provider", "outlook"])
        eq = provider.search_emails.call_args[0][0]
        assert eq.raw_query == "invoice"
        assert eq.include_spam_trash is True

    def test_trash_does_not_include_trash(self):
        _, provider = self._run(["-q", "from:x@y.com"])
        eq = provider.search_emails.call_args[0][0]
        assert eq.include_spam_trash is False
        assert eq.raw_query == "from:x@y.com"
        provider.trash.assert_called_once_with("m1")


class TestAuthStatusNoInteractiveFlow:
    """auth-status never starts OAuth and reports profile errors (CLI-05)."""

    _base = {
        "credentials_file_exists": True,
        "credentials_path": "/p/credentials.json",
    }

    def _run_gmail(self, status: dict, svc_side_effect=None):
        with (
            patch("iobox.cli.get_provider", return_value=_mock_provider()),
            patch("iobox.providers.google.auth.check_auth_status", return_value=status),
            patch("iobox.providers.google.auth.get_gmail_service") as mock_svc,
            patch(
                "iobox.providers.google.auth.get_gmail_profile",
                return_value={"emailAddress": "u@gmail.com"},
            ),
        ):
            if svc_side_effect is not None:
                mock_svc.side_effect = svc_side_effect
            result = runner.invoke(app, ["auth-status"])
        return result, mock_svc

    def test_no_token_does_not_build_service(self):
        status = {
            **self._base,
            "authenticated": False,
            "token_file_exists": False,
            "token_path": "/p/none.json",
        }
        result, mock_svc = self._run_gmail(status)
        assert result.exit_code == 0
        mock_svc.assert_not_called()
        assert "Not signed in" in result.output

    def test_expired_without_refresh_token_does_not_build_service(self):
        status = {
            **self._base,
            "authenticated": False,
            "token_file_exists": True,
            "token_path": "/p/t.json",
            "expired": True,
            "has_refresh_token": False,
        }
        result, mock_svc = self._run_gmail(status)
        mock_svc.assert_not_called()

    def test_expired_with_refresh_token_fetches_profile(self):
        status = {
            **self._base,
            "authenticated": False,
            "token_file_exists": True,
            "token_path": "/p/t.json",
            "expired": True,
            "has_refresh_token": True,
        }
        result, mock_svc = self._run_gmail(status)
        mock_svc.assert_called_once()
        assert "u@gmail.com" in result.output

    def test_token_missing_scopes_does_not_build_service(self, tmp_path):
        token = tmp_path / "token_standard.json"
        token.write_text(
            '{"scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}', encoding="utf-8"
        )
        status = {
            **self._base,
            "authenticated": True,
            "token_file_exists": True,
            "token_path": str(token),
        }
        result, mock_svc = self._run_gmail(status)
        mock_svc.assert_not_called()
        assert "missing scopes" in result.output

    def test_profile_error_is_reported(self):
        status = {
            **self._base,
            "authenticated": True,
            "token_file_exists": True,
            "token_path": "/p/t.json",
        }
        result, _ = self._run_gmail(status, svc_side_effect=RuntimeError("refresh failed"))
        assert result.exit_code == 0
        assert "Could not fetch Gmail profile: refresh failed" in result.stderr

    def test_outlook_unauthenticated_does_not_touch_provider(self):
        status = {
            "authenticated": False,
            "client_id_configured": True,
            "tenant_id": "common",
            "token_file_exists": False,
            "token_path": "/t/o365_token.txt",
        }
        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.o365.auth.check_outlook_auth_status", return_value=status),
        ):
            result = runner.invoke(app, ["--provider", "outlook", "auth-status"])
        assert result.exit_code == 0
        provider.get_profile.assert_not_called()
        assert "Not signed in" in result.output

    def test_outlook_profile_error_is_reported(self):
        status = {
            "authenticated": True,
            "client_id_configured": True,
            "tenant_id": "common",
            "token_file_exists": True,
            "token_path": "/t/o365_token.txt",
        }
        provider = _mock_provider()
        provider.get_profile.side_effect = RuntimeError("graph down")
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.providers.o365.auth.check_outlook_auth_status", return_value=status),
        ):
            result = runner.invoke(app, ["--provider", "outlook", "auth-status"])
        assert "Could not fetch Outlook profile: graph down" in result.stderr


class TestInclusiveEndDate:
    """--end-date is inclusive: providers get the following day as 'before' (TIME-01)."""

    def test_parse_dates_end_date_plus_one_day(self):
        from datetime import date

        from iobox.cli import _parse_dates

        after, before = _parse_dates(None, "2026/03/01", "2026/03/31")
        assert after == date(2026, 3, 1)
        assert before == date(2026, 4, 1)

    def test_parse_dates_dash_format_and_year_rollover(self):
        from datetime import date

        from iobox.cli import _parse_dates

        _, before = _parse_dates(None, None, "2026-12-31")
        assert before == date(2027, 1, 1)

    def test_parse_dates_no_end_date(self):
        from iobox.cli import _parse_dates

        _, before = _parse_dates(7, None, None)
        assert before is None

    def test_search_passes_next_day_to_provider(self):
        from datetime import date

        provider = _mock_provider()
        with patch("iobox.cli.get_provider", return_value=provider):
            result = runner.invoke(
                app, ["search", "-q", "x", "-s", "2026/03/01", "-e", "2026/03/15"]
            )
        assert result.exit_code == 0
        eq = provider.search_emails.call_args[0][0]
        assert eq.after == date(2026, 3, 1)
        assert eq.before == date(2026, 3, 16)

    def test_save_batch_passes_next_day_to_provider(self, tmp_path):
        from datetime import date

        provider = _mock_provider()
        with (
            patch("iobox.cli.get_provider", return_value=provider),
            patch("iobox.cli.create_output_directory", return_value=str(tmp_path)),
        ):
            result = runner.invoke(
                app,
                ["save", "-q", "x", "-s", "2026/03/01", "-e", "2026/03/15", "-o", str(tmp_path)],
            )
        assert result.exit_code == 0, result.output
        eq = provider.search_emails.call_args[0][0]
        assert eq.before == date(2026, 3, 16)
