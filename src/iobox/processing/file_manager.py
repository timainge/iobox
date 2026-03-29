"""
File Management Module.

This module handles file operations including duplicate prevention.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from iobox.utils import create_markdown_filename

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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


def save_email_to_markdown(
    email_data: dict[str, Any], markdown_content: str, output_dir: str
) -> str:
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
    msg_id = email_data.get("message_id", "") or email_data.get("id", "")
    if not msg_id:
        raise ValueError("Email data missing message_id or id")

    # For compatibility, ensure message_id is set in the email_data
    if "message_id" not in email_data and "id" in email_data:
        email_data["message_id"] = email_data["id"]

    # Create filename using appropriate function
    filename = create_markdown_filename(email_data)
    filepath = os.path.join(output_dir, filename)

    # Check for duplicate filename
    if check_file_exists(filepath):
        filepath = handle_duplicate_filename(filepath)

    # Write content to file
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logging.info(f"Saved email to markdown file: {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Error saving email to markdown file: {e}")
        raise


def check_for_duplicates(email_ids: list[str], output_dir: str) -> list[str]:
    """
    Check which email IDs have already been processed and saved as markdown.

    Args:
        email_ids: List of email IDs to check
        output_dir: Directory to check for existing files

    Returns:
        List[str]: List of email IDs that are already processed
    """
    if not os.path.exists(output_dir):
        return []

    try:
        files = [f for f in os.listdir(output_dir) if f.endswith(".md")]
        processed_ids = [os.path.splitext(f)[0] for f in files]
    except Exception as e:
        logging.error(f"Error listing processed emails: {e}")
        return []

    duplicates = [email_id for email_id in email_ids if email_id in processed_ids]

    if duplicates:
        logging.info(f"Found {len(duplicates)} already processed emails")

    return duplicates


def handle_duplicate_filename(filepath: str) -> str:
    """
    Handle duplicate filenames by appending a number to the base filename.

    Args:
        filepath: Original filepath

    Returns:
        str: New filepath with a number appended
    """
    base, ext = os.path.splitext(filepath)
    counter = 1

    while os.path.exists(filepath):
        filepath = f"{base}_{counter}{ext}"
        counter += 1

    logging.info(f"Resolved duplicate filename: {filepath}")
    return filepath


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to make it safe for the filesystem.

    Args:
        filename: Original filename

    Returns:
        str: Sanitized filename
    """
    # Replace any character that's not alphanumeric, dash, underscore, dot, or space
    # with underscore
    sanitized = re.sub(r"[^\w\-\. ]", "_", filename)

    # Handle reserved filenames in Windows
    reserved_names = [
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    ]

    basename = os.path.splitext(sanitized)[0].upper()
    if basename in reserved_names:
        sanitized = f"_{sanitized}"

    # Ensure the filename is not too long
    max_length = 240  # Safely under most filesystem limits
    if len(sanitized) > max_length:
        base, ext = os.path.splitext(sanitized)
        sanitized = f"{base[: max_length - len(ext)]}{ext}"

    return sanitized


def create_attachments_directory(output_dir: str, email_id: str) -> str:
    """
    Create a directory for storing email attachments.

    Args:
        output_dir: Base output directory where markdown files are stored
        email_id: Email message ID

    Returns:
        str: Path to the attachments directory
    """
    # Create a subdirectory for attachments using the email ID
    attachments_dir = os.path.join(output_dir, "attachments", email_id)

    try:
        os.makedirs(attachments_dir, exist_ok=True)
        logging.info(f"Created attachments directory: {attachments_dir}")
        return attachments_dir
    except Exception as e:
        logging.error(f"Error creating attachments directory {attachments_dir}: {e}")
        raise


def save_attachment(attachment_data: bytes, filename: str, email_id: str, output_dir: str) -> str:
    """
    Save an email attachment to disk.

    Args:
        attachment_data: Binary attachment data
        filename: Original attachment filename
        email_id: Email message ID
        output_dir: Base output directory

    Returns:
        str: Path to the saved attachment file
    """
    # Create attachments directory
    attachments_dir = create_attachments_directory(output_dir, email_id)

    # Sanitize filename
    safe_filename = sanitize_filename(filename)

    # Create full path
    filepath = os.path.join(attachments_dir, safe_filename)

    # Handle duplicate filenames
    if check_file_exists(filepath):
        filepath = handle_duplicate_filename(filepath)

    # Write attachment data to file
    try:
        with open(filepath, "wb") as f:
            f.write(attachment_data)

        logging.info(f"Saved attachment to: {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Error saving attachment: {e}")
        raise


class SyncState:
    """Manages incremental sync state for a directory.

    Supports both Gmail and Outlook sync tokens:

    * **Gmail** uses a single ``last_history_id`` string (the ``historyId``
      returned by the Gmail API).
    * **Outlook** uses ``delta_links`` — a dict mapping folder identifiers
      (e.g. ``"inbox"``) to Microsoft Graph delta link URLs that encode the
      server-side sync cursor.

    The ``provider`` field (``"gmail"`` or ``"outlook"``) is persisted so
    that consumers know which token fields are relevant.
    """

    FILENAME = ".iobox-sync.json"

    def __init__(self, directory: str):
        self.filepath = os.path.join(directory, self.FILENAME)
        self.provider: str | None = None
        self.last_history_id: str | None = None
        self.delta_links: dict[str, str] = {}
        self.last_sync_time: str | None = None
        self.synced_message_ids: list[str] = []

    def load(self) -> bool:
        """Load sync state from file. Returns True if state exists."""
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                data = json.load(f)
            self.provider = data.get("provider")
            self.last_history_id = data.get("last_history_id")
            self.delta_links = data.get("delta_links", {})
            self.last_sync_time = data.get("last_sync_time")
            self.synced_message_ids = data.get("synced_message_ids", [])
            return True
        return False

    def save(self) -> None:
        """Save current sync state to file."""
        data = {
            "provider": self.provider,
            "last_history_id": self.last_history_id,
            "delta_links": self.delta_links,
            "last_sync_time": datetime.utcnow().isoformat(),
            "synced_message_ids": self.synced_message_ids,
        }
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=2)

    def update(self, history_id: str, new_message_ids: list[str]) -> None:
        """Update state with new sync results (Gmail convenience method)."""
        self.last_history_id = history_id
        self.synced_message_ids = list(set(self.synced_message_ids + new_message_ids))
        self.save()

    def update_delta(self, folder: str, delta_link: str, new_message_ids: list[str]) -> None:
        """Update state with new Outlook delta sync results.

        Args:
            folder: Folder key (e.g. ``"inbox"``).
            delta_link: The ``@odata.deltaLink`` URL from the last page of the
                delta response — used as the cursor for the next sync.
            new_message_ids: Newly discovered message IDs to merge into
                ``synced_message_ids``.
        """
        self.provider = "outlook"
        self.delta_links[folder] = delta_link
        self.synced_message_ids = list(set(self.synced_message_ids + new_message_ids))
        self.save()


def download_email_attachments(
    service: Any = None,
    email_data: dict[str, Any] | None = None,
    output_dir: str = "",
    attachment_filters: list[str] | None = None,
    download_fn: Any | None = None,
) -> dict[str, Any]:
    """
    Download all attachments for an email.

    Args:
        service: Authenticated Gmail API service (legacy — used when *download_fn* is ``None``).
        email_data: Email data dictionary.
        output_dir: Directory to save attachments to.
        attachment_filters: List of file extensions to filter by (e.g. ['pdf', 'docx']).
        download_fn: Optional callable ``(message_id, attachment_id) -> bytes``.
            When provided, it is used instead of the Gmail-specific download path
            so that any provider backend can supply attachment data.

    Returns:
        dict: Result with downloaded_count, skipped_count, and errors list
    """
    if download_fn is None:
        from iobox.providers.google._retrieval import download_attachment as _dl

        def download_fn(message_id: str, attachment_id: str) -> bytes:
            return _dl(service, message_id, attachment_id)

    message_id = email_data.get("message_id", "")  # type: ignore[union-attr]  # caller guarantees non-None at this point
    attachments = email_data.get("attachments", [])  # type: ignore[union-attr]

    if not attachments:
        logging.info("No attachments found")
        return {"downloaded_count": 0, "skipped_count": 0, "errors": []}

    logging.info(f"Found {len(attachments)} attachments for message {message_id}")

    downloaded_count = 0
    skipped_count = 0
    errors: list[str] = []

    for attachment in attachments:
        if attachment_filters:
            filename = attachment.get("filename", "")
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            if ext and ext not in attachment_filters:
                logging.info(f"Skipping attachment (type filter): {filename}")
                skipped_count += 1
                continue

        attachment_id = attachment.get("id", "")
        filename = attachment.get("filename", "")

        if not attachment_id or not filename:
            logging.info("Skipping attachment with missing ID or filename")
            skipped_count += 1
            continue

        try:
            logging.info(f"Downloading attachment: {filename}")
            attachment_data = download_fn(message_id, attachment_id)

            if attachment_data:
                filepath = save_attachment(
                    attachment_data=attachment_data,
                    filename=filename,
                    email_id=message_id,
                    output_dir=output_dir,
                )
                downloaded_count += 1
                logging.info(f"Saved attachment to: {filepath}")
            else:
                msg = f"Failed to download attachment: {filename}"
                logging.error(msg)
                errors.append(msg)
        except Exception as e:
            msg = f"Error downloading attachment {filename}: {e}"
            logging.error(msg)
            errors.append(msg)

    return {"downloaded_count": downloaded_count, "skipped_count": skipped_count, "errors": errors}
