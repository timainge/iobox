"""
Unit tests for the file management module.

This module tests the functionality of the file_manager.py module which is responsible
for saving email content to markdown files and handling duplicates.
"""

import os
from unittest.mock import MagicMock, mock_open, patch

from iobox.file_manager import (
    SyncState,
    check_file_exists,
    create_attachments_directory,
    create_output_directory,
    download_email_attachments,
    handle_duplicate_filename,
    sanitize_filename,
    save_attachment,
    save_email_to_markdown,
)


class TestFileManager:
    """Test cases for the file management module."""

    def test_create_output_directory(self, tmp_path):
        """Test creating an output directory."""
        output_dir = tmp_path / "emails"

        # Ensure directory doesn't exist yet
        assert not output_dir.exists()

        # Call function to create directory
        created_dir = create_output_directory(str(output_dir))

        # Verify directory was created
        assert os.path.exists(created_dir)
        assert os.path.isdir(created_dir)
        assert created_dir == str(output_dir)

    def test_create_output_directory_existing(self, tmp_path):
        """Test creating an output directory that already exists."""
        output_dir = tmp_path / "existing_emails"
        os.makedirs(output_dir, exist_ok=True)

        # Verify directory already exists
        assert output_dir.exists()

        # Call function to create directory
        created_dir = create_output_directory(str(output_dir))

        # Verify function returns existing directory path
        assert created_dir == str(output_dir)

    def test_check_file_exists(self, tmp_path):
        """Test checking if a file exists."""
        # Create a test file
        test_file = tmp_path / "test_file.md"
        test_file.write_text("Test content")

        # Test with existing file
        assert check_file_exists(str(test_file)) is True

        # Test with non-existent file
        nonexistent_file = tmp_path / "nonexistent.md"
        assert check_file_exists(str(nonexistent_file)) is False

    def test_handle_duplicate_filename(self, tmp_path):
        """Test handling duplicate filenames."""
        # Create a test file
        test_file = tmp_path / "duplicate_file.md"
        test_file.write_text("Original content")

        # Create an alternative filename
        new_filename = handle_duplicate_filename(str(test_file))

        # Verify new filename is different but follows expected pattern
        assert new_filename != str(test_file)
        assert "_" in new_filename  # Should have a counter added
        assert new_filename.endswith(".md")

        # Create the new file
        with open(new_filename, "w") as f:
            f.write("New content")

        # Try again and verify we get a different filename again
        third_filename = handle_duplicate_filename(str(test_file))
        assert third_filename != str(test_file)
        assert third_filename != new_filename

    def test_save_email_to_markdown_new_file(self, tmp_path):
        """Test saving email to a new markdown file."""
        output_dir = tmp_path / "emails"
        os.makedirs(output_dir, exist_ok=True)

        email_data = {
            "id": "message-id-1",
            "subject": "Test Email Subject",
            "from": "sender@example.com",
        }

        markdown_content = """---
subject: Test Email Subject
from: sender@example.com
---

This is the test email body.
"""

        # Patch the open function and filename generation
        with (
            patch("iobox.file_manager.open", mock_open()) as mock_file,
            patch("iobox.file_manager.create_markdown_filename") as mock_filename,
        ):
            # Set up mock filename
            test_filename = "2025-03-23-test-email-subject.md"
            mock_filename.return_value = test_filename

            # Call function to save email
            filepath = save_email_to_markdown(
                email_data=email_data, markdown_content=markdown_content, output_dir=str(output_dir)
            )

            # Verify file was "saved" with correct content
            expected_path = os.path.join(str(output_dir), test_filename)
            assert filepath == expected_path
            mock_file.assert_called_once_with(expected_path, "w", encoding="utf-8")
            mock_file().write.assert_called_once_with(markdown_content)

    def test_save_email_to_markdown_with_duplicate(self, tmp_path):
        """Test saving email when filename already exists."""
        output_dir = tmp_path / "emails"
        os.makedirs(output_dir, exist_ok=True)

        # Create a file that will cause a duplicate
        original_file = output_dir / "2025-03-23-test-email-subject.md"
        original_file.write_text("Original content")

        email_data = {
            "id": "message-id-1",
            "subject": "Test Email Subject",
            "from": "sender@example.com",
        }

        markdown_content = """---
subject: Test Email Subject
from: sender@example.com
---

This is the test email body.
"""

        # Patch the open function and filename generation
        with (
            patch("iobox.file_manager.open", mock_open()) as mock_file,
            patch("iobox.file_manager.create_markdown_filename") as mock_filename,
            patch("iobox.file_manager.handle_duplicate_filename") as mock_handle_duplicate,
        ):
            # Set up mocks
            test_filename = "2025-03-23-test-email-subject.md"
            mock_filename.return_value = test_filename

            duplicate_filename = "2025-03-23-test-email-subject_1.md"
            mock_handle_duplicate.return_value = os.path.join(str(output_dir), duplicate_filename)

            # Call function to save email
            filepath = save_email_to_markdown(
                email_data=email_data, markdown_content=markdown_content, output_dir=str(output_dir)
            )

            # Verify duplicate handler was called
            mock_handle_duplicate.assert_called_once()

            # Verify file was "saved" with correct path and content
            expected_path = os.path.join(str(output_dir), duplicate_filename)
            assert filepath == expected_path
            mock_file.assert_called_once_with(expected_path, "w", encoding="utf-8")
            mock_file().write.assert_called_once_with(markdown_content)

    def test_sanitize_filename(self):
        """Test sanitizing filenames for safe filesystem usage."""
        # Test with unsafe characters
        filename = 'unsafe:filename*with?invalid\\chars<>|/"'
        sanitized = sanitize_filename(filename)
        # Check that all unsafe chars are replaced with underscores
        assert ":" not in sanitized
        assert "*" not in sanitized
        assert "?" not in sanitized
        assert "\\" not in sanitized
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert "|" not in sanitized
        assert "/" not in sanitized
        assert '"' not in sanitized

        # Test with Windows reserved name
        reserved_name = "CON.txt"
        sanitized = sanitize_filename(reserved_name)
        assert sanitized == "_CON.txt"

        # Test with extremely long name
        long_name = "a" * 300 + ".txt"
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 240
        assert sanitized.endswith(".txt")

    def test_create_attachments_directory(self, tmp_path):
        """Test creating a directory for email attachments."""
        output_dir = str(tmp_path)
        email_id = "test-email-id-123"

        # Call function to create attachments directory
        attachments_dir = create_attachments_directory(output_dir, email_id)

        # Verify directory structure was created
        expected_path = os.path.join(output_dir, "attachments", email_id)
        assert attachments_dir == expected_path
        assert os.path.exists(attachments_dir)
        assert os.path.isdir(attachments_dir)

    def test_save_attachment(self, tmp_path):
        """Test saving an email attachment to disk."""
        # Setup test data
        output_dir = str(tmp_path)
        email_id = "test-email-id-123"
        attachment_data = b"This is test attachment content"
        filename = "test_attachment.pdf"

        # Mock check_file_exists to simulate no duplicate files
        with patch("iobox.file_manager.check_file_exists", return_value=False):
            # Call function to save attachment
            filepath = save_attachment(
                attachment_data=attachment_data,
                filename=filename,
                email_id=email_id,
                output_dir=output_dir,
            )

            # Verify attachment was saved correctly
            expected_path = os.path.join(output_dir, "attachments", email_id, filename)
            assert filepath == expected_path
            assert os.path.exists(filepath)

            # Check file contents
            with open(filepath, "rb") as f:
                saved_content = f.read()
                assert saved_content == attachment_data

    def test_save_attachment_with_unsafe_filename(self, tmp_path):
        """Test saving an attachment with an unsafe filename."""
        # Setup test data
        output_dir = str(tmp_path)
        email_id = "test-email-id-123"
        attachment_data = b"This is test attachment content"
        unsafe_filename = "unsafe:filename*with?invalid\\chars.pdf"

        # Mock check_file_exists to simulate no duplicate files
        with patch("iobox.file_manager.check_file_exists", return_value=False):
            # Call function to save attachment
            filepath = save_attachment(
                attachment_data=attachment_data,
                filename=unsafe_filename,
                email_id=email_id,
                output_dir=output_dir,
            )

            # Verify filename was sanitized
            assert ":" not in os.path.basename(filepath)
            assert "*" not in os.path.basename(filepath)
            assert "?" not in os.path.basename(filepath)
            assert "\\" not in os.path.basename(filepath)

            # Check file contents
            with open(filepath, "rb") as f:
                saved_content = f.read()
                assert saved_content == attachment_data

    def test_save_attachment_with_duplicate_filename(self, tmp_path):
        """Test saving an attachment with a filename that already exists."""
        # Setup test data
        output_dir = str(tmp_path)
        email_id = "test-email-id-123"
        attachment_data = b"This is test attachment content"
        filename = "duplicate_attachment.pdf"

        # Create the attachment directory
        attachments_dir = os.path.join(output_dir, "attachments", email_id)
        os.makedirs(attachments_dir, exist_ok=True)

        # Create a file with the same name to simulate a duplicate
        original_path = os.path.join(attachments_dir, filename)
        with open(original_path, "wb") as f:
            f.write(b"Original content")

        # Mock check_file_exists to return True first time (for original file)
        # and False after (for the renamed file)
        check_side_effect = [True, False]

        with patch("iobox.file_manager.check_file_exists", side_effect=check_side_effect):
            # Call function to save attachment
            filepath = save_attachment(
                attachment_data=attachment_data,
                filename=filename,
                email_id=email_id,
                output_dir=output_dir,
            )

            # Verify a new filename was generated (should have _1 appended)
            expected_path = os.path.join(attachments_dir, "duplicate_attachment_1.pdf")
            assert filepath == expected_path
            assert os.path.exists(filepath)

            # Check file contents
            with open(filepath, "rb") as f:
                saved_content = f.read()
                assert saved_content == attachment_data

            # Verify original file still exists and has original content
            assert os.path.exists(original_path)
            with open(original_path, "rb") as f:
                original_content = f.read()
                assert original_content == b"Original content"


class TestSyncState:
    """Tests for the SyncState class."""

    def test_sync_state_save_and_load(self, tmp_path):
        """SyncState persists and reloads data correctly."""
        state = SyncState(str(tmp_path))
        state.last_history_id = "hist-999"
        state.synced_message_ids = ["msg-1", "msg-2"]
        state.save()

        # Verify JSON file was created
        assert os.path.exists(os.path.join(str(tmp_path), SyncState.FILENAME))

        # Load in a fresh instance
        state2 = SyncState(str(tmp_path))
        loaded = state2.load()

        assert loaded is True
        assert state2.last_history_id == "hist-999"
        assert set(state2.synced_message_ids) == {"msg-1", "msg-2"}

    def test_sync_state_load_returns_false_when_missing(self, tmp_path):
        """load() returns False when no state file exists."""
        state = SyncState(str(tmp_path))
        result = state.load()
        assert result is False
        assert state.last_history_id is None
        assert state.synced_message_ids == []

    def test_sync_state_update_merges_ids(self, tmp_path):
        """update() merges new message IDs with existing ones and saves."""
        state = SyncState(str(tmp_path))
        state.synced_message_ids = ["msg-1", "msg-2"]
        state.update("hist-500", ["msg-2", "msg-3", "msg-4"])

        assert state.last_history_id == "hist-500"
        assert set(state.synced_message_ids) == {"msg-1", "msg-2", "msg-3", "msg-4"}

        # Verify persisted
        state2 = SyncState(str(tmp_path))
        state2.load()
        assert set(state2.synced_message_ids) == {"msg-1", "msg-2", "msg-3", "msg-4"}
        assert state2.last_history_id == "hist-500"

    def test_sync_state_update_without_prior_load(self, tmp_path):
        """update() can be called on a fresh SyncState without prior load()."""
        state = SyncState(str(tmp_path))
        state.update("hist-100", ["msg-a", "msg-b"])

        state2 = SyncState(str(tmp_path))
        state2.load()
        assert set(state2.synced_message_ids) == {"msg-a", "msg-b"}


class TestDownloadEmailAttachments:
    """Tests for the download_email_attachments() function moved to file_manager."""

    def _make_email_data(self, attachments=None):
        return {
            "message_id": "msg-test",
            "attachments": attachments or [],
        }

    def test_no_attachments_returns_zero(self):
        """Returns zero counts when email has no attachments."""
        mock_service = MagicMock()
        email_data = self._make_email_data([])

        result = download_email_attachments(mock_service, email_data, "/tmp/out")

        assert result["downloaded_count"] == 0
        assert result["skipped_count"] == 0
        assert result["errors"] == []

    def test_download_success(self, tmp_path):
        """Successfully downloaded attachment is counted."""
        mock_service = MagicMock()
        email_data = self._make_email_data(
            [{"id": "att-1", "filename": "report.pdf", "mime_type": "application/pdf", "size": 100}]
        )

        with (
            patch(
                "iobox.email_retrieval.download_attachment", return_value=b"pdf-content"
            ) as mock_dl,
            patch("iobox.file_manager.save_attachment", return_value=str(tmp_path / "report.pdf")),
        ):
            result = download_email_attachments(mock_service, email_data, str(tmp_path))

        assert result["downloaded_count"] == 1
        assert result["skipped_count"] == 0
        assert result["errors"] == []
        mock_dl.assert_called_once_with(mock_service, "msg-test", "att-1")

    def test_filter_by_extension(self, tmp_path):
        """Attachments not matching the filter are skipped."""
        mock_service = MagicMock()
        email_data = self._make_email_data(
            [
                {
                    "id": "att-1",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "size": 100,
                },
                {"id": "att-2", "filename": "image.png", "mime_type": "image/png", "size": 50},
            ]
        )

        with (
            patch("iobox.email_retrieval.download_attachment", return_value=b"data") as mock_dl,
            patch("iobox.file_manager.save_attachment", return_value=str(tmp_path / "report.pdf")),
        ):
            result = download_email_attachments(
                mock_service, email_data, str(tmp_path), attachment_filters=["pdf"]
            )

        assert result["downloaded_count"] == 1
        assert result["skipped_count"] == 1
        # Only pdf was downloaded
        mock_dl.assert_called_once_with(mock_service, "msg-test", "att-1")

    def test_download_error_recorded(self, tmp_path):
        """Errors during download are collected in the errors list."""
        mock_service = MagicMock()
        email_data = self._make_email_data(
            [{"id": "att-1", "filename": "file.pdf", "mime_type": "application/pdf", "size": 100}]
        )

        with patch(
            "iobox.email_retrieval.download_attachment", side_effect=Exception("network error")
        ):
            result = download_email_attachments(mock_service, email_data, str(tmp_path))

        assert result["downloaded_count"] == 0
        assert len(result["errors"]) == 1
        assert "file.pdf" in result["errors"][0]
