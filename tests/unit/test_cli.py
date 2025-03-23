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
            {"id": "message-id-1", "snippet": "First email snippet"}
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
            "id": "message-id-1",
            "subject": "Test Subject",
            "body": "Email body content"
        }
        mock_markdown = "# Test Subject\n\nEmail body content"
        mock_filepath = "/path/to/output/email.md"
        
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.get_email_content", return_value=mock_email_data), \
             patch("iobox.cli.convert_email_to_markdown", return_value=mock_markdown), \
             patch("iobox.cli.save_email_to_markdown", return_value=mock_filepath):
            
            # Mock the Gmail service
            mock_service.return_value = MagicMock()
            
            # Call the convert command
            result = runner.invoke(app, ["convert", "--message-id", "message-id-1", "--output-dir", "./output"])
            
            assert result.exit_code == 0
            assert "Successfully converted email" in result.stdout
            assert mock_filepath in result.stdout
    
    def test_batch_convert_command(self):
        """Test the batch-convert command."""
        # Mock search results
        mock_emails = [
            {"id": "message-id-1", "snippet": "First email snippet"},
            {"id": "message-id-2", "snippet": "Second email snippet"}
        ]
        
        # Mock email data
        mock_email_data = {
            "id": "message-id-1",
            "subject": "Test Subject",
            "body": "Email body content"
        }
        
        # Mock markdown content and file paths
        mock_markdown = "# Test Subject\n\nEmail body content"
        mock_filepath = "/path/to/output/email.md"
        
        with patch("iobox.cli.get_gmail_service") as mock_service, \
             patch("iobox.cli.search_emails", return_value=mock_emails), \
             patch("iobox.cli.get_email_content", return_value=mock_email_data), \
             patch("iobox.cli.convert_email_to_markdown", return_value=mock_markdown), \
             patch("iobox.cli.save_email_to_markdown", return_value=mock_filepath):
            
            # Mock the Gmail service
            mock_service.return_value = MagicMock()
            
            # Call the batch-convert command
            result = runner.invoke(app, [
                "batch-convert",
                "--query", "from:example.com",
                "--max-results", "5",
                "--output-dir", "./output"
            ])
            
            assert result.exit_code == 0
            assert "Converting 2 emails" in result.stdout
            assert "Successfully converted 2 emails" in result.stdout
    
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
