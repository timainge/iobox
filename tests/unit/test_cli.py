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
             patch("iobox.cli.search_emails", return_value=mock_emails):
            
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
             patch("iobox.cli.search_emails", return_value=[]):
            
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
             patch("iobox.cli.create_output_directory", return_value="./output"):
            
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
             patch("iobox.cli.check_for_duplicates", return_value=[]):

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
                cc=None, bcc=None, content_type='plain', attachments=None
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
                cc=None, bcc=None, content_type='plain', attachments=None
            )

    def test_send_html_flag(self):
        """Test send with --html flag sets content_type to html."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose, \
             patch("iobox.cli.send_message", return_value={"id": "sent-3"}):
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "send",
                "--to", "bob@example.com",
                "--subject", "Hello HTML",
                "--body", "<b>Hi</b>",
                "--html",
            ])

            assert result.exit_code == 0
            assert "Email sent successfully" in result.stdout
            mock_compose.assert_called_once_with(
                to="bob@example.com", subject="Hello HTML", body="<b>Hi</b>",
                cc=None, bcc=None, content_type='html', attachments=None
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


class TestDraftCommands:
    """Test cases for draft CLI commands."""

    def test_draft_create_command(self):
        """Test draft-create command creates a draft."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose, \
             patch("iobox.cli.create_draft", return_value={"id": "draft-1"}) as mock_create:
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "draft-create",
                "--to", "bob@example.com",
                "--subject", "Draft Subject",
                "--body", "Draft body",
            ])

            assert result.exit_code == 0
            assert "Draft created successfully" in result.stdout
            assert "draft-1" in result.stdout
            mock_create.assert_called_once()

    def test_draft_list_command(self):
        """Test draft-list command lists drafts."""
        mock_drafts = [
            {"id": "draft-1", "subject": "First Draft", "snippet": "First snippet"},
            {"id": "draft-2", "subject": "Second Draft", "snippet": "Second snippet"},
        ]

        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.list_drafts", return_value=mock_drafts):
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, ["draft-list"])

            assert result.exit_code == 0
            assert "draft-1" in result.stdout
            assert "First Draft" in result.stdout
            assert "draft-2" in result.stdout

    def test_draft_list_empty(self):
        """Test draft-list when no drafts exist."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.list_drafts", return_value=[]):
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, ["draft-list"])

            assert result.exit_code == 0
            assert "No drafts found" in result.stdout

    def test_draft_send_command(self):
        """Test draft-send command sends a draft."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.send_draft", return_value={"id": "sent-from-draft"}) as mock_send:
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "draft-send",
                "--draft-id", "draft-1",
            ])

            assert result.exit_code == 0
            assert "Draft sent successfully" in result.stdout
            mock_send.assert_called_once_with(mock_service.return_value, "draft-1")

    def test_draft_delete_command(self):
        """Test draft-delete command deletes a draft."""
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.delete_draft", return_value={"status": "deleted", "draft_id": "draft-1"}) as mock_delete:
            mock_service.return_value = MagicMock()

            result = runner.invoke(app, [
                "draft-delete",
                "--draft-id", "draft-1",
            ])

            assert result.exit_code == 0
            assert "Draft deleted successfully" in result.stdout
            mock_delete.assert_called_once_with(mock_service.return_value, "draft-1")
