"""
Unit tests for the file management module.

This module tests the functionality of the file_manager.py module which is responsible
for saving email content to markdown files and handling duplicates.
"""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from iobox.processing.file_manager import (
    SyncState,
    _read_frontmatter_message_id,
    check_file_exists,
    check_for_duplicates,
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
            patch("iobox.processing.file_manager.open", mock_open()) as mock_file,
            patch("iobox.processing.file_manager.create_markdown_filename") as mock_filename,
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
            patch("iobox.processing.file_manager.open", mock_open()) as mock_file,
            patch("iobox.processing.file_manager.create_markdown_filename") as mock_filename,
            patch(
                "iobox.processing.file_manager.handle_duplicate_filename"
            ) as mock_handle_duplicate,
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
        with patch("iobox.processing.file_manager.check_file_exists", return_value=False):
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
        with patch("iobox.processing.file_manager.check_file_exists", return_value=False):
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

        with patch(
            "iobox.processing.file_manager.check_file_exists", side_effect=check_side_effect
        ):
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


class TestCheckForDuplicates:
    def test_detects_ids_saved_by_save_email_to_markdown(self, tmp_path):
        from iobox.processing.markdown_converter import convert_email_to_markdown

        email = {
            "message_id": "18e4a2b3c1d5f6a7",
            "subject": "Weekly Digest",
            "from": "news@example.com",
            "date": "Mon, 05 Jan 2026 09:00:00 +0000",
            "body": "Hello",
        }
        save_email_to_markdown(email, convert_email_to_markdown(email), str(tmp_path))

        assert check_for_duplicates(["18e4a2b3c1d5f6a7", "other"], str(tmp_path)) == [
            "18e4a2b3c1d5f6a7"
        ]

    def test_matches_legacy_filename_stem(self, tmp_path):
        (tmp_path / "abc123.md").write_text("no frontmatter")
        assert check_for_duplicates(["abc123"], str(tmp_path)) == ["abc123"]

    def test_ignores_message_id_outside_frontmatter(self, tmp_path):
        (tmp_path / "note.md").write_text("---\ntitle: x\n---\n\nmessage_id: abc123\n")
        assert check_for_duplicates(["abc123"], str(tmp_path)) == []

    def test_missing_directory_returns_empty(self, tmp_path):
        assert check_for_duplicates(["abc"], str(tmp_path / "nope")) == []


class TestReadFrontmatterMessageId:
    """DATA-01: message_id read via yaml.safe_load, tolerant of legacy files."""

    def _save(self, tmp_path, subject, message_id="real-id"):
        from iobox.processing.markdown_converter import convert_email_to_markdown

        email = {
            "message_id": message_id,
            "subject": subject,
            "from": "a@example.com",
            "date": "Mon, 05 Jan 2026 09:00:00 +0000",
            "body": "Hello",
        }
        path = tmp_path / "x.md"
        path.write_text(convert_email_to_markdown(email), encoding="utf-8")
        return str(path)

    @pytest.mark.parametrize(
        "subject",
        ["Re: hi", "yes", "12345", "# x", "a\nmessage_id: evil", "---", "Ünïcödé ✓"],
    )
    def test_nasty_subjects(self, tmp_path, subject):
        path = self._save(tmp_path, subject)
        assert _read_frontmatter_message_id(path) == "real-id"

    def test_numeric_message_id_stays_string(self, tmp_path):
        path = self._save(tmp_path, "x", message_id="012345")
        assert _read_frontmatter_message_id(path) == "012345"

    def test_legacy_unquoted_frontmatter(self, tmp_path):
        path = tmp_path / "legacy.md"
        path.write_text(
            "---\ndate: Mon, 05 Jan\nmessage_id: abc123\nsubject: Re: hi: there\n---\n\nBody\n"
        )
        assert _read_frontmatter_message_id(str(path)) == "abc123"

    def test_legacy_numeric_id_uses_raw_text(self, tmp_path):
        path = tmp_path / "legacy.md"
        path.write_text("---\nmessage_id: 0777\nsubject: x\n---\n")
        assert _read_frontmatter_message_id(str(path)) == "0777"

    def test_no_frontmatter(self, tmp_path):
        path = tmp_path / "plain.md"
        path.write_text("message_id: abc\n")
        assert _read_frontmatter_message_id(str(path)) is None

    def test_missing_file(self, tmp_path):
        assert _read_frontmatter_message_id(str(tmp_path / "nope.md")) is None


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

    @pytest.mark.parametrize("content", ["", "{not json", "[1, 2]", "null", "\xff\xfe"])
    def test_load_corrupt_file_is_treated_as_no_state(self, tmp_path, content, caplog):
        """SYNC-03: a corrupt state file logs a warning and returns False."""
        path = tmp_path / SyncState.FILENAME
        path.write_bytes(content.encode("latin-1"))
        state = SyncState(str(tmp_path))
        with caplog.at_level("WARNING", logger="iobox.processing.file_manager"):
            assert state.load() is False
        assert state.last_history_id is None
        assert state.synced_message_ids == []
        assert "corrupt sync state" in caplog.text

    def test_save_after_corrupt_load_recovers(self, tmp_path):
        (tmp_path / SyncState.FILENAME).write_text("{trunc")
        state = SyncState(str(tmp_path))
        state.load()
        state.update("hist-1", ["m1"])
        state2 = SyncState(str(tmp_path))
        assert state2.load() is True
        assert state2.last_history_id == "hist-1"

    def test_save_is_atomic_on_write_failure(self, tmp_path):
        """SYNC-03: a failed write leaves the previous state intact and no temp files."""
        state = SyncState(str(tmp_path))
        state.update("hist-1", ["m1"])
        original = (tmp_path / SyncState.FILENAME).read_text()

        state.last_history_id = "hist-2"
        with (
            patch("iobox.processing.file_manager.json.dump", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            state.save()

        assert (tmp_path / SyncState.FILENAME).read_text() == original
        assert os.listdir(tmp_path) == [SyncState.FILENAME]

    def test_save_uses_os_replace(self, tmp_path):
        state = SyncState(str(tmp_path))
        with patch("iobox.processing.file_manager.os.replace", wraps=os.replace) as rep:
            state.save()
        rep.assert_called_once()
        src, dst = rep.call_args[0]
        assert dst == state.filepath
        assert os.path.dirname(src) == str(tmp_path)

    def test_save_sets_timezone_aware_sync_time(self, tmp_path):
        state = SyncState(str(tmp_path))
        state.save()
        state2 = SyncState(str(tmp_path))
        state2.load()
        assert state2.last_sync_time is not None
        assert state2.last_sync_time.endswith("+00:00")

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
                "iobox.providers.google._retrieval.download_attachment", return_value=b"pdf-content"
            ) as mock_dl,
            patch(
                "iobox.processing.file_manager.save_attachment",
                return_value=str(tmp_path / "report.pdf"),
            ),
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
            patch(
                "iobox.providers.google._retrieval.download_attachment", return_value=b"data"
            ) as mock_dl,
            patch(
                "iobox.processing.file_manager.save_attachment",
                return_value=str(tmp_path / "report.pdf"),
            ),
        ):
            result = download_email_attachments(
                mock_service, email_data, str(tmp_path), attachment_filters=["pdf"]
            )

        assert result["downloaded_count"] == 1
        assert result["skipped_count"] == 1
        # Only pdf was downloaded
        mock_dl.assert_called_once_with(mock_service, "msg-test", "att-1")

    def test_filter_excludes_extensionless_attachments(self, tmp_path):
        """DATA-15: an extensionless attachment never matches a type filter."""
        email_data = self._make_email_data(
            [
                {"id": "att-1", "filename": "report.pdf", "mime_type": "application/pdf"},
                {"id": "att-2", "filename": "README", "mime_type": "text/plain"},
            ]
        )
        download_fn = MagicMock(return_value=b"data")
        result = download_email_attachments(
            email_data=email_data,
            output_dir=str(tmp_path),
            attachment_filters=["pdf"],
            download_fn=download_fn,
        )
        assert result["downloaded_count"] == 1
        assert result["skipped_count"] == 1
        download_fn.assert_called_once_with("msg-test", "att-1")

    def test_extensionless_kept_without_filter(self, tmp_path):
        email_data = self._make_email_data(
            [{"id": "att-2", "filename": "README", "mime_type": "text/plain"}]
        )
        result = download_email_attachments(
            email_data=email_data,
            output_dir=str(tmp_path),
            download_fn=MagicMock(return_value=b"data"),
        )
        assert result["downloaded_count"] == 1

    def test_filter_normalises_case_and_dots(self, tmp_path):
        email_data = self._make_email_data(
            [{"id": "att-1", "filename": "REPORT.PDF", "mime_type": "application/pdf"}]
        )
        result = download_email_attachments(
            email_data=email_data,
            output_dir=str(tmp_path),
            attachment_filters=[".Pdf"],
            download_fn=MagicMock(return_value=b"data"),
        )
        assert result["downloaded_count"] == 1

    def test_inline_attachments_skipped_by_default(self, tmp_path):
        """Inline parts (signature logos) are skipped unless include_inline=True."""
        mock_service = MagicMock()
        email_data = self._make_email_data(
            [
                {
                    "id": "att-1",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "size": 100,
                    "inline": False,
                },
                {
                    "id": "att-2",
                    "filename": "image001.png",
                    "mime_type": "image/png",
                    "size": 50,
                    "inline": True,
                },
            ]
        )

        with (
            patch(
                "iobox.providers.google._retrieval.download_attachment", return_value=b"data"
            ) as mock_dl,
            patch(
                "iobox.processing.file_manager.save_attachment",
                return_value=str(tmp_path / "report.pdf"),
            ),
        ):
            result = download_email_attachments(mock_service, email_data, str(tmp_path))

        assert result["downloaded_count"] == 1
        assert result["skipped_count"] == 1
        assert result["saved"][0]["filename"] == "report.pdf"
        assert result["saved"][0]["inline"] is False
        mock_dl.assert_called_once_with(mock_service, "msg-test", "att-1")

    def test_inline_attachments_included_when_opted_in(self, tmp_path):
        """include_inline=True downloads inline parts too."""
        mock_service = MagicMock()
        email_data = self._make_email_data(
            [
                {
                    "id": "att-2",
                    "filename": "image001.png",
                    "mime_type": "image/png",
                    "size": 50,
                    "inline": True,
                },
            ]
        )

        with (
            patch("iobox.providers.google._retrieval.download_attachment", return_value=b"data"),
            patch(
                "iobox.processing.file_manager.save_attachment",
                return_value=str(tmp_path / "image001.png"),
            ),
        ):
            result = download_email_attachments(
                mock_service, email_data, str(tmp_path), include_inline=True
            )

        assert result["downloaded_count"] == 1
        assert result["skipped_count"] == 0

    def test_download_error_recorded(self, tmp_path):
        """Errors during download are collected in the errors list."""
        mock_service = MagicMock()
        email_data = self._make_email_data(
            [{"id": "att-1", "filename": "file.pdf", "mime_type": "application/pdf", "size": 100}]
        )

        with patch(
            "iobox.providers.google._retrieval.download_attachment",
            side_effect=Exception("network error"),
        ):
            result = download_email_attachments(mock_service, email_data, str(tmp_path))

        assert result["downloaded_count"] == 0
        assert len(result["errors"]) == 1
        assert "file.pdf" in result["errors"][0]


class TestNoImportTimeLoggingConfig:
    """PROC-06: importing processing modules must not configure the root logger."""

    def test_import_does_not_add_root_handlers(self):
        import subprocess
        import sys

        code = (
            "import logging\n"
            "import iobox.processing.file_manager\n"
            "import iobox.processing.markdown_converter\n"
            "import iobox.processing.markdown\n"
            "import iobox.utils\n"
            "assert logging.getLogger().handlers == [], logging.getLogger().handlers\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_modules_use_named_loggers(self):
        from iobox.processing import file_manager, markdown_converter

        assert file_manager.logger.name == "iobox.processing.file_manager"
        assert markdown_converter.logger.name == "iobox.processing.markdown_converter"


class TestSanitizeFilenameEdgeCases:
    """DATA-14: byte-length limits, extensions, dot names, reserved names."""

    def test_truncates_by_utf8_bytes(self):
        name = "日" * 200 + ".pdf"  # 600 bytes of stem
        result = sanitize_filename(name)
        assert len(result.encode("utf-8")) <= 240
        assert result.endswith(".pdf")
        result.encode("utf-8").decode("utf-8")  # no split characters

    def test_does_not_split_multibyte_character(self):
        name = "a" + "é" * 200 + ".txt"
        result = sanitize_filename(name)
        assert len(result.encode("utf-8")) <= 240
        assert result.endswith(".txt")
        assert "�" not in result

    def test_long_extension_is_capped(self):
        name = "report." + "x" * 400
        result = sanitize_filename(name)
        assert len(result.encode("utf-8")) <= 240
        assert result.startswith("report")

    @pytest.mark.parametrize("name", ["", ".", "..", "...", "   ", " . ", None])
    def test_dot_and_empty_names_use_fallback(self, name):
        assert sanitize_filename(name) == "attachment"

    def test_custom_fallback(self):
        assert sanitize_filename("..", fallback="x") == "x"

    def test_strips_trailing_dots_and_spaces(self):
        assert sanitize_filename("report.pdf. . ") == "report.pdf"
        assert sanitize_filename("  name.txt") == "name.txt"

    @pytest.mark.parametrize("name", ["CON.tar.gz", "nul.txt", "com1", "LPT9.a.b", "aux .txt"])
    def test_reserved_names_checked_before_first_dot(self, name):
        assert sanitize_filename(name).startswith("_")

    @pytest.mark.parametrize("name", ["CONSOLE.txt", "icon.png", "com10.txt"])
    def test_non_reserved_names_unchanged(self, name):
        assert sanitize_filename(name) == name

    def test_path_separators_removed(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert result != ".."


class TestAttachmentPathContainment:
    """SEC-12: message IDs are sanitised and attachment paths stay in output_dir."""

    @pytest.mark.parametrize("email_id", ["../../evil", "..", "a/../../b", "/abs/path", ""])
    def test_traversal_ids_stay_inside(self, tmp_path, email_id):
        out = tmp_path / "out"
        out.mkdir()
        attachments_dir = create_attachments_directory(str(out), email_id)
        real = os.path.realpath(attachments_dir)
        assert real.startswith(os.path.realpath(str(out / "attachments")) + os.sep)
        assert os.path.isdir(real)

    def test_dotdot_id_uses_fallback(self, tmp_path):
        attachments_dir = create_attachments_directory(str(tmp_path), "..")
        assert os.path.basename(attachments_dir) == "unknown-message"

    def test_save_attachment_with_traversal_id(self, tmp_path):
        out = tmp_path / "out"
        path = save_attachment(b"x", "../../a.txt", "../../../m", str(out))
        assert os.path.realpath(path).startswith(os.path.realpath(str(out)) + os.sep)

    def test_symlinked_attachments_dir_escaping_is_rejected(self, tmp_path):
        out = tmp_path / "out"
        (out / "attachments").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (out / "attachments" / "msg").symlink_to(outside)
        with pytest.raises(ValueError, match="outside output directory"):
            create_attachments_directory(str(out), "msg")
