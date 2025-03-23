"""
File Management Module.

This module handles file operations including duplicate prevention.
"""

import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def check_file_exists(msg_id, output_dir):
    """
    Check if a file for the given message ID already exists.
    
    Args:
        msg_id: Email message ID
        output_dir: Directory to check
        
    Returns:
        bool: True if file exists, False otherwise
    """
    filepath = os.path.join(output_dir, f"{msg_id}.md")
    return os.path.exists(filepath)


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
