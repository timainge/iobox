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


def _make_batch_mock(service_mock, metadata_responses):
    """Set up service_mock.new_batch_http_request to simulate batch execution.

    metadata_responses: dict mapping message_id -> raw API response dict
    """
    def fake_new_batch(callback):
        batch = MagicMock()
        added = []

        def add(request, request_id):
            added.append(request_id)

        batch.add.side_effect = add

        def execute():
            for req_id in added:
                resp = metadata_responses.get(req_id)
                callback(req_id, resp, None)

        batch.execute.side_effect = execute
        return batch

    service_mock.new_batch_http_request.side_effect = fake_new_batch


class TestEmailToMarkdownWorkflow:
    """Integration tests for the email to markdown workflow."""

    def test_full_conversion_process(self, mocker, tmp_path):
        """Test the complete process from email search to markdown file creation."""
        output_dir = tmp_path / "emails"
        os.makedirs(output_dir, exist_ok=True)

        mock_service = MagicMock()

        # Mock search results (messages.list)
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "messages": [
                {"id": "message-id-1", "threadId": "thread-id-1"}
            ],
            "resultSizeEstimate": 1
        }
        mock_service.users().messages().list = MagicMock(return_value=mock_list)

        # Mock batch metadata fetch
        _make_batch_mock(mock_service, {
            "message-id-1": {
                "id": "message-id-1",
                "threadId": "thread-id-1",
                "snippet": "Test snippet",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Email Subject"},
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Date", "value": "Mon, 01 Jan 2024 00:00:00 +0000"},
                    ]
                }
            }
        })

        # Mock email content retrieval (for get_email_content)
        mock_get = MagicMock()
        mock_get.execute.return_value = MOCK_PLAIN_TEXT_MESSAGE
        mock_service.users().messages().get = MagicMock(return_value=mock_get)

        mock_filename = "test-email.md"
        mock_full_path = os.path.join(os.path.abspath(str(output_dir)), mock_filename)

        mock_open = mocker.mock_open()

        with patch("builtins.open", mock_open), \
             patch("iobox.markdown.create_markdown_filename", return_value=mock_filename), \
             patch("iobox.file_manager.create_markdown_filename", return_value=mock_filename):

            search_results = search_emails(
                service=mock_service,
                query="from:example.com",
                max_results=1
            )

            assert len(search_results) == 1
            assert search_results[0]["message_id"] == "message-id-1"

            email_data = get_email_content(
                service=mock_service,
                message_id=search_results[0]["message_id"]
            )

            assert email_data["message_id"] == "message-id-1"
            assert email_data["subject"] == "Test Email Subject"

            markdown_content = convert_email_to_markdown(email_data)

            assert "---" in markdown_content
            assert "subject: Test Email Subject" in markdown_content

            output_path = save_email_to_markdown(
                email_data=email_data,
                markdown_content=markdown_content,
                output_dir=str(output_dir)
            )

            assert output_path == mock_full_path or output_path.endswith(mock_filename), \
                   f"Expected path ending with {mock_filename}, got {output_path}"

            mock_open.assert_called_once()
            mock_open().write.assert_called_once_with(markdown_content)

    def test_search_and_batch_convert(self, mocker, tmp_path):
        """Test searching for multiple emails and batch converting them."""
        output_dir = tmp_path / "emails"
        os.makedirs(output_dir, exist_ok=True)

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

        # Mock batch metadata fetch
        _make_batch_mock(mock_service, {
            "message-id-1": {
                "id": "message-id-1",
                "threadId": "thread-id-1",
                "snippet": "Snippet 1",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Email Subject"},
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Date", "value": "Mon, 01 Jan 2024 00:00:00 +0000"},
                    ]
                }
            },
            "message-id-2": {
                "id": "message-id-2",
                "threadId": "thread-id-2",
                "snippet": "Snippet 2",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Email Subject"},
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Date", "value": "Mon, 01 Jan 2024 00:00:00 +0000"},
                    ]
                }
            }
        })

        # Mock email content retrieval
        message1 = dict(MOCK_PLAIN_TEXT_MESSAGE)
        message2 = dict(MOCK_PLAIN_TEXT_MESSAGE)
        message2["id"] = "message-id-2"
        message2["threadId"] = "thread-id-2"
        message2["snippet"] = "This is the second email snippet"

        mock_get = MagicMock()

        def get_message_by_id(userId, id, format, **kwargs):
            if id == "message-id-1":
                mock_get.execute.return_value = message1
            else:
                mock_get.execute.return_value = message2
            return mock_get

        mock_service.users().messages().get.side_effect = get_message_by_id

        filename_calls = 0
        def get_filename():
            nonlocal filename_calls
            filename_calls += 1
            return f"test-email-{filename_calls}.md"

        with patch("builtins.open", mocker.mock_open()) as mock_file, \
             patch("iobox.markdown.create_markdown_filename", side_effect=get_filename):

            search_results = search_emails(
                service=mock_service,
                query="from:example.com",
                max_results=2
            )

            assert len(search_results) == 2

            converted_files = []
            for result in search_results:
                email_data = get_email_content(
                    service=mock_service,
                    message_id=result["message_id"]
                )

                markdown_content = convert_email_to_markdown(email_data)

                output_path = save_email_to_markdown(
                    email_data=email_data,
                    markdown_content=markdown_content,
                    output_dir=str(output_dir)
                )

                converted_files.append(output_path)

            assert len(converted_files) == 2
            for file_path in converted_files:
                assert file_path.startswith(str(output_dir))
                assert file_path.endswith(".md")
            assert mock_file.call_count == 2
