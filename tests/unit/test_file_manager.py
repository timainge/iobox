"""
Unit tests for the file management module.

This module tests the functionality of the file_manager.py module which is responsible
for saving email content to markdown files and handling duplicates.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from iobox.file_manager import (
    save_email_to_markdown,
    check_file_exists,
    create_output_directory,
    handle_duplicate_filename
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
        with patch("iobox.file_manager.open", mock_open()) as mock_file, \
             patch("iobox.file_manager.create_markdown_filename") as mock_filename:
            
            # Set up mock filename
            test_filename = "2025-03-23-test-email-subject.md"
            mock_filename.return_value = test_filename
            
            # Call function to save email
            filepath = save_email_to_markdown(
                email_data=email_data,
                markdown_content=markdown_content,
                output_dir=str(output_dir)
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
        with patch("iobox.file_manager.open", mock_open()) as mock_file, \
             patch("iobox.file_manager.create_markdown_filename") as mock_filename, \
             patch("iobox.file_manager.handle_duplicate_filename") as mock_handle_duplicate:
            
            # Set up mocks
            test_filename = "2025-03-23-test-email-subject.md"
            mock_filename.return_value = test_filename
            
            duplicate_filename = "2025-03-23-test-email-subject_1.md"
            mock_handle_duplicate.return_value = os.path.join(str(output_dir), duplicate_filename)
            
            # Call function to save email
            filepath = save_email_to_markdown(
                email_data=email_data,
                markdown_content=markdown_content,
                output_dir=str(output_dir)
            )
            
            # Verify duplicate handler was called
            mock_handle_duplicate.assert_called_once()
            
            # Verify file was "saved" with correct path and content
            expected_path = os.path.join(str(output_dir), duplicate_filename)
            assert filepath == expected_path
            mock_file.assert_called_once_with(expected_path, "w", encoding="utf-8")
            mock_file().write.assert_called_once_with(markdown_content)
