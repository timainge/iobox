"""
Unit tests for the command-line interface.

This module tests the functionality of the CLI module which provides
the user-facing command-line interface for the iobox application.
"""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from iobox.cli import app


# Create a CLI runner for testing Typer apps
runner = CliRunner()


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
        # Mock the email search functionality
        mock_emails = [
            {"message_id": "message-id-1", "subject": "Test", "from": "a@b.com", "date": "", "snippet": "First email snippet", "labels": []}
        ]
        
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.search_emails", return_value=mock_emails), \
             patch("iobox.cli.get_label_map", return_value={}):

            # Mock the Gmail service
            mock_service.return_value = MagicMock()

            # Call the search command
            result = runner.invoke(app, ["search", "--query", "from:example.com", "--max-results", "5"])

            assert result.exit_code == 0
            assert "message-id-1" in result.stdout
            assert "First email snippet" in result.stdout

    def test_search_command_no_results(self):
        """Test the search command with no results."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.search_emails", return_value=[]), \
             patch("iobox.cli.get_label_map", return_value={}):

            # Mock the Gmail service
            mock_service.return_value = MagicMock()
            
            # Call the search command
            result = runner.invoke(app, ["search", "--query", "from:nonexistent"])
            
            assert result.exit_code == 0
            assert "No emails found" in result.stdout
    
    def test_convert_command(self):
        """Test the convert command."""
        # Mock email data and file path
        mock_email_data = {
            "message_id": "message-id-1",
            "subject": "Test Subject",
            "content": "Email body content",
            "content_type": "text/plain",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100"
        }
        mock_markdown = "# Test Subject\n\nEmail body content"
        mock_filepath = "/path/to/output/email.md"
        
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.get_email_content", return_value=mock_email_data), \
             patch("iobox.cli.convert_email_to_markdown", return_value=mock_markdown), \
             patch("iobox.cli.save_email_to_markdown", return_value=mock_filepath), \
             patch("iobox.cli.create_output_directory", return_value="./output"), \
             patch("iobox.cli.get_label_map", return_value={}):

            # Mock the Gmail service
            mock_service.return_value = MagicMock()

            # Call the convert command
            result = runner.invoke(app, ["save", "--message-id", "message-id-1", "--output-dir", "./output"])
            
            assert result.exit_code == 0
            assert "Successfully saved email" in result.stdout
    
    def test_batch_convert_command(self):
        """Test the batch-convert command."""
        # Mock search results (search_emails returns 'message_id' key)
        mock_emails = [
            {"message_id": "message-id-1", "subject": "First email", "snippet": "First email snippet"},
            {"message_id": "message-id-2", "subject": "Second email", "snippet": "Second email snippet"}
        ]
        
        # Mock email data
        mock_email_data = {
            "message_id": "message-id-1",
            "subject": "Test Subject",
            "content": "Email body content",
            "content_type": "text/plain",
            "from": "sender@example.com",
            "date": "Mon, 23 Mar 2025 10:00:00 +1100"
        }
        
        # Mock markdown content and file paths
        mock_markdown = "# Test Subject\n\nEmail body content"
        mock_filepath = "/path/to/output/email.md"
        
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.search_emails", return_value=mock_emails), \
             patch("iobox.cli.get_email_content", return_value=mock_email_data), \
             patch("iobox.cli.convert_email_to_markdown", return_value=mock_markdown), \
             patch("iobox.cli.save_email_to_markdown", return_value=mock_filepath), \
             patch("iobox.cli.create_output_directory", return_value="./output"), \
             patch("iobox.cli.check_for_duplicates", return_value=[]), \
             patch("iobox.cli.get_label_map", return_value={}):

            # Mock the Gmail service
            mock_service.return_value = MagicMock()

            # Call the batch-convert command
            result = runner.invoke(app, [
                "save",
                "--query", "from:example.com",
                "--max", "5",
                "--output-dir", "./output"
            ])

            assert result.exit_code == 0
            assert "Searching for emails matching" in result.stdout
    
    def test_auth_status_command(self):
        """Test the auth-status command."""
        # Mock authentication status
        mock_status = {
            "authenticated": True,
            "credentials_file_exists": True,
            "token_file_exists": True,
            "credentials_path": "/path/to/credentials.json",
            "token_path": "/path/to/token.json"
        }
        
        with patch("iobox.cli.check_auth_status", return_value=mock_status):
            # Call the auth-status command
            result = runner.invoke(app, ["auth-status"])
            
            assert result.exit_code == 0
            assert "Authentication Status" in result.stdout
            assert "Authenticated: True" in result.stdout
            assert "Credentials file exists: True" in result.stdout
            assert "Token file exists: True" in result.stdout

    def test_forward_single_email(self):
        """Test forwarding a single email by message ID."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.forward_email", return_value={"id": "fwd-1"}):
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "forward",
                "--message-id", "msg-123",
                "--to", "bob@example.com",
            ])

            assert result.exit_code == 0
            assert "Successfully forwarded" in result.stdout

    def test_forward_batch(self):
        """Test forwarding multiple emails via query."""
        mock_emails = [
            {"message_id": "m1", "subject": "First"},
            {"message_id": "m2", "subject": "Second"},
        ]

        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.search_emails", return_value=mock_emails), \
             patch("iobox.cli.forward_email", return_value={"id": "fwd-x"}):
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "forward",
                "--query", "from:test@example.com",
                "--to", "bob@example.com",
            ])

            assert result.exit_code == 0
            assert "Forwarded 2 emails" in result.stdout

    def test_forward_no_query_or_id(self):
        """Test forward command fails without --message-id or --query."""
        with patch("iobox.cli.get_gmail_service") as mock_service:
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "forward",
                "--to", "bob@example.com",
            ])

            assert result.exit_code == 1

    def test_send_with_body(self):
        """Test sending an email with inline body."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose, \
             patch("iobox.cli.send_message", return_value={"id": "sent-1"}) as mock_send:
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "send",
                "--to", "bob@example.com",
                "--subject", "Hello",
                "--body", "Hi there",
            ])

            assert result.exit_code == 0
            assert "Email sent successfully" in result.stdout
            mock_compose.assert_called_once_with(
                to="bob@example.com", subject="Hello", body="Hi there",
                cc=None, bcc=None
            )

    def test_send_with_body_file(self, tmp_path):
        """Test sending an email with body from file."""
        body_file = tmp_path / "body.txt"
        body_file.write_text("File body content")

        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose, \
             patch("iobox.cli.send_message", return_value={"id": "sent-2"}):
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "send",
                "--to", "bob@example.com",
                "--subject", "Hello",
                "--body-file", str(body_file),
            ])

            assert result.exit_code == 0
            assert "Email sent successfully" in result.stdout
            mock_compose.assert_called_once_with(
                to="bob@example.com", subject="Hello", body="File body content",
                cc=None, bcc=None
            )

    def test_send_no_body(self):
        """Test send command fails without --body or --body-file."""
        with patch("iobox.cli.get_gmail_service") as mock_service:
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "send",
                "--to", "bob@example.com",
                "--subject", "Hello",
            ])

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

        with patch("iobox.cli.check_auth_status", return_value=mock_status), \
             patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.get_gmail_profile", return_value=mock_profile):
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

        with patch("iobox.cli.check_auth_status", return_value=mock_status), \
             patch("iobox.cli.get_gmail_service", side_effect=Exception("Auth failed")):
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
                "from": "a@example.com",
                "to": "b@example.com",
                "date": "Mon, 01 Jan 2024 00:00:00 +0000",
                "labels": ["INBOX"],
                "body": "Hello",
                "content_type": "text/plain",
            }
        ]
        mock_md = "---\nthread_id: thread-abc\n---\n\n## From: a@example.com — Mon\n\nHello"

        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.get_label_map", return_value={}), \
             patch("iobox.cli.get_thread_content", return_value=mock_messages), \
             patch("iobox.cli.convert_thread_to_markdown", return_value=mock_md), \
             patch("iobox.cli.create_output_directory", return_value=str(tmp_path)):
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, [
                "save", "--thread-id", "thread-abc", "--output-dir", str(tmp_path)
            ])

        assert result.exit_code == 0
        assert "Successfully saved thread" in result.stdout

    # ------------------------------------------------------------------
    # search --include-spam-trash
    # ------------------------------------------------------------------

    def test_search_include_spam_trash(self):
        """search --include-spam-trash passes flag to search_emails."""
        mock_emails = [
            {"message_id": "m1", "subject": "Spam Email", "from": "x@y.com",
             "date": "", "snippet": "spam", "labels": []}
        ]

        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.get_label_map", return_value={}), \
             patch("iobox.cli.search_emails", return_value=mock_emails) as mock_search:
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, [
                "search", "--query", "in:spam", "--include-spam-trash"
            ])

        assert result.exit_code == 0
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs.get("include_spam_trash") is True

    # ------------------------------------------------------------------
    # label command
    # ------------------------------------------------------------------

    def test_label_mark_read(self):
        """label --mark-read removes UNREAD label."""
        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.modify_message_labels") as mock_modify:
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, [
                "label", "--message-id", "msg-1", "--mark-read"
            ])

        assert result.exit_code == 0
        mock_modify.assert_called_once_with(
            mock_svc.return_value, "msg-1", None, ["UNREAD"]
        )

    def test_label_add_custom(self):
        """label --add 'Newsletter' resolves name and adds label ID."""
        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.resolve_label_name", return_value="Label_12345") as mock_resolve, \
             patch("iobox.cli.modify_message_labels") as mock_modify:
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, [
                "label", "--message-id", "msg-1", "--add", "Newsletter"
            ])

        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(mock_svc.return_value, "Newsletter")
        # add_labels should contain the resolved ID
        args = mock_modify.call_args[0]
        assert "Label_12345" in args[2]

    def test_label_no_message_or_query(self):
        """label without --message-id or --query exits with error."""
        with patch("iobox.cli.get_gmail_service") as mock_svc:
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, ["label", "--mark-read"])

        assert result.exit_code == 1

    # ------------------------------------------------------------------
    # trash command
    # ------------------------------------------------------------------

    def test_trash_single(self):
        """trash --message-id trashes the message without confirmation."""
        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.trash_message") as mock_trash:
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, ["trash", "--message-id", "msg-1"])

        assert result.exit_code == 0
        mock_trash.assert_called_once_with(mock_svc.return_value, "msg-1")
        assert "Trashed" in result.stdout

    def test_trash_batch_confirm(self):
        """trash --query prompts for confirmation before trashing."""
        mock_emails = [
            {"message_id": "m1", "subject": "Old Email"},
            {"message_id": "m2", "subject": "Another Old"},
        ]

        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.get_label_map", return_value={}), \
             patch("iobox.cli.search_emails", return_value=mock_emails), \
             patch("iobox.cli.trash_message") as mock_trash:
            mock_svc.return_value = MagicMock()
            # Provide "y" as input to confirm
            result = runner.invoke(app, ["trash", "--query", "older_than:1y"], input="y\n")

        assert result.exit_code == 0
        assert mock_trash.call_count == 2

    def test_trash_batch_abort(self):
        """trash --query with 'n' input aborts without trashing."""
        mock_emails = [{"message_id": "m1", "subject": "Old"}]

        with patch("iobox.cli.get_gmail_service") as mock_svc, \
             patch("iobox.cli.get_label_map", return_value={}), \
             patch("iobox.cli.search_emails", return_value=mock_emails), \
             patch("iobox.cli.trash_message") as mock_trash:
            mock_svc.return_value = MagicMock()
            result = runner.invoke(app, ["trash", "--query", "older_than:1y"], input="n\n")

        assert result.exit_code == 0
        mock_trash.assert_not_called()
        assert "Aborted" in result.stdout
