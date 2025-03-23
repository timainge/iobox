"""
File Management Module.

This module handles file operations including duplicate prevention.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from iobox.markdown import create_markdown_filename

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def check_file_exists(filepath: str) -> bool:
    """
    Check if a file exists at the given path.
    
    Args:
        filepath: Full path to the file to check
        
    Returns:
        bool: True if file exists, False otherwise
    """
    return os.path.exists(filepath)


def create_output_directory(output_dir: str) -> str:
    """
    Create the output directory if it doesn't exist.
    
    Args:
        output_dir: Directory path to create
        
    Returns:
        str: Absolute path to the output directory
    """
    # Convert to absolute path if relative
    output_path = os.path.abspath(output_dir)
    
    try:
        os.makedirs(output_path, exist_ok=True)
        logging.info(f"Created output directory: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Error creating output directory {output_path}: {e}")
        raise


def ensure_output_directory(output_dir):
    """
    Ensure the output directory exists, creating it if necessary.
    
    Args:
        output_dir: Directory path to ensure
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        logging.info(f"Ensured output directory exists: {output_dir}")
        return True
    except Exception as e:
        logging.error(f"Error creating output directory {output_dir}: {e}")
        return False


def save_email_to_markdown(email_data: Dict[str, Any], markdown_content: str, output_dir: str) -> str:
    """
    Save email markdown content to a file in the output directory.
    
    Args:
        email_data: Dictionary containing email metadata
        markdown_content: Markdown content to save
        output_dir: Directory to save the file in
        
    Returns:
        str: Path to the saved file
    """
    # Ensure output directory exists
    create_output_directory(output_dir)
    
    # Get message ID from email data - handle both 'id' and 'message_id' for compatibility
    msg_id = email_data.get('message_id', '') or email_data.get('id', '')
    if not msg_id:
        raise ValueError("Email data missing message_id or id")
    
    # For compatibility, ensure message_id is set in the email_data
    if 'message_id' not in email_data and 'id' in email_data:
        email_data['message_id'] = email_data['id']
    
    # Create filename using appropriate function
    filename = create_markdown_filename(email_data)
    filepath = os.path.join(output_dir, filename)
    
    # Check for duplicate filename
    if check_file_exists(filepath):
        filepath = handle_duplicate_filename(filepath)
    
    # Write content to file
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        logging.info(f"Saved email to markdown file: {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Error saving email to markdown file: {e}")
        raise


def list_processed_emails(output_dir):
    """
    List all previously processed emails in the output directory.
    
    Args:
        output_dir: Directory containing markdown files
        
    Returns:
        list: List of message IDs (without .md extension)
    """
    if not os.path.exists(output_dir):
        return []
        
    try:
        files = [f for f in os.listdir(output_dir) if f.endswith('.md')]
        message_ids = [os.path.splitext(f)[0] for f in files]
        return message_ids
    except Exception as e:
        logging.error(f"Error listing processed emails: {e}")
        return []


def check_for_duplicates(email_ids: List[str], output_dir: str) -> List[str]:
    """
    Check which email IDs have already been processed and saved as markdown.
    
    Args:
        email_ids: List of email IDs to check
        output_dir: Directory to check for existing files
        
    Returns:
        List[str]: List of email IDs that are already processed
    """
    processed_ids = list_processed_emails(output_dir)
    duplicates = [email_id for email_id in email_ids if email_id in processed_ids]
    
    if duplicates:
        logging.info(f"Found {len(duplicates)} already processed emails")
    
    return duplicates


def handle_duplicate_filename(filepath: str) -> str:
    """
    Handle duplicate filenames by appending a number to the filename.
    
    Args:
        filepath: Path to the file that already exists
        
    Returns:
        str: New filepath with a number appended
    """
    # Split path into directory, filename, and extension
    directory = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)
    
    # Try adding numbers until we find a filename that doesn't exist
    counter = 1
    while check_file_exists(filepath):
        new_filename = f"{name}_{counter}{ext}"
        filepath = os.path.join(directory, new_filename)
        counter += 1
    
    logging.info(f"Renamed duplicate file to: {os.path.basename(filepath)}")
    return filepath
