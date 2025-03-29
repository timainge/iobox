"""
Integration tests for the email to markdown conversion workflow.

This module tests the complete email to markdown conversion process,
combining multiple modules to verify the full workflow.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from iobox.auth import get_gmail_service
from iobox.email_search import search_emails, get_email_content
from iobox.markdown import convert_email_to_markdown
from iobox.file_manager import save_email_to_markdown
from tests.fixtures.mock_responses import MOCK_PLAIN_TEXT_MESSAGE


class TestEmailToMarkdownWorkflow:
    """Integration tests for the email to markdown workflow."""
    
    def test_full_conversion_process(self, mocker, tmp_path):
        """Test the complete process from email search to markdown file creation."""
        # Create output directory
        output_dir = tmp_path / "emails"
        os.makedirs(output_dir, exist_ok=True)
        
        # Mock the Gmail service
        mock_service = MagicMock()
        
        # Mock search results
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "messages": [
                {"id": "message-id-1", "threadId": "thread-id-1"}
            ],
            "resultSizeEstimate": 1
        }
        mock_service.users().messages().list = MagicMock(return_value=mock_list)
        
        # Mock email content retrieval
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_PLAIN_TEXT_MESSAGE
        mock_service.users().messages().get = MagicMock(return_value=mock_get)
        
        # Set a fixed filename for testing, mocking both module uses of create_markdown_filename
        mock_filename = "test-email.md"
        mock_full_path = os.path.join(os.path.abspath(str(output_dir)), mock_filename)
        
        # Mock file operations properly for context manager use
        mock_open = mocker.mock_open()
        
        # Apply patches in a way that works with context managers
        with patch("builtins.open", mock_open), \
             patch("iobox.markdown.create_markdown_filename", return_value=mock_filename), \
             patch("iobox.file_manager.create_markdown_filename", return_value=mock_filename):
            
            # Step 1: Search for emails
            search_results = search_emails(
                service=mock_service,
                query="from:example.com",
                max_results=1
            )
            
            assert len(search_results) == 1
            assert search_results[0]["id"] == "message-id-1"
            
            # Step 2: Get email content
            email_data = get_email_content(
                service=mock_service,
                message_id=search_results[0]["id"]
            )
            
            assert email_data["message_id"] == "message-id-1"
            assert email_data["subject"] == "Test Email Subject"
            
            # Step 3: Convert to markdown
            markdown_content = convert_email_to_markdown(email_data)
            
            assert "---" in markdown_content  # Has frontmatter
            assert "subject: Test Email Subject" in markdown_content
            
            # Step 4: Save to file
            output_path = save_email_to_markdown(
                email_data=email_data,
                markdown_content=markdown_content,
                output_dir=str(output_dir)
            )
            
            # Verify the output_path matches what we expect
            assert output_path == mock_full_path or output_path.endswith(mock_filename), \
                   f"Expected path ending with {mock_filename}, got {output_path}"
                
            # Verify file was "written"
            mock_open.assert_called_once()
            mock_open().write.assert_called_once_with(markdown_content)
    
    def test_search_and_batch_convert(self, mocker, tmp_path):
        """Test searching for multiple emails and batch converting them."""
        # Create output directory
        output_dir = tmp_path / "emails"
        os.makedirs(output_dir, exist_ok=True)
        
        # Mock the Gmail service
        mock_service = MagicMock()
        
        # Mock search results with multiple emails
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "messages": [
                {"id": "message-id-1", "threadId": "thread-id-1"},
                {"id": "message-id-2", "threadId": "thread-id-2"}
            ],
            "resultSizeEstimate": 2
        }
        mock_service.users().messages().list = MagicMock(return_value=mock_list)
        
        # Mock email content retrieval
        mock_get = MagicMock()
        
        # Modify the base message to create two different messages
        message1 = dict(MOCK_PLAIN_TEXT_MESSAGE)
        message2 = dict(MOCK_PLAIN_TEXT_MESSAGE)
        message2["id"] = "message-id-2"
        message2["threadId"] = "thread-id-2"
        message2["snippet"] = "This is the second email snippet"
        
        # Configure the mock to return different messages based on ID
        def get_message_by_id(userId, id, format, **kwargs):
            if id == "message-id-1":
                mock_get.execute.return_value = message1
            else:
                mock_get.execute.return_value = message2
            return mock_get
        
        mock_service.users().messages().get.side_effect = get_message_by_id
        
        # Setup filename mocks to handle multiple files
        filename_calls = 0
        def get_filename():
            nonlocal filename_calls
            filename_calls += 1
            return f"test-email-{filename_calls}.md"
        
        with patch("builtins.open", mocker.mock_open()) as mock_file, \
             patch("iobox.markdown.create_markdown_filename", side_effect=get_filename):
            
            # Step 1: Search for emails
            search_results = search_emails(
                service=mock_service,
                query="from:example.com",
                max_results=2
            )
            
            assert len(search_results) == 2
            
            # Step 2-4: Process each email
            converted_files = []
            for result in search_results:
                # Get email content
                email_data = get_email_content(
                    service=mock_service,
                    message_id=result["id"]
                )
                
                # Convert to markdown
                markdown_content = convert_email_to_markdown(email_data)
                
                # Save to file
                output_path = save_email_to_markdown(
                    email_data=email_data,
                    markdown_content=markdown_content,
                    output_dir=str(output_dir)
                )
                
                converted_files.append(output_path)
            
            # Verify both files were processed
            assert len(converted_files) == 2
            # Check that both files have the expected path format
            for file_path in converted_files:
                assert file_path.startswith(str(output_dir))
                assert file_path.endswith(".md")
            assert mock_file.call_count == 2
