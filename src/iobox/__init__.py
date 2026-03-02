"""
Iobox - Gmail to Markdown Converter

A tool that extracts emails from Gmail based on specific criteria
and saves them as markdown files with YAML frontmatter.
"""

try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("iobox")
except PackageNotFoundError:
    __version__ = "0.1.0"  # fallback for uninstalled dev

try:
    from iobox.auth import get_gmail_service, check_auth_status
    from iobox.email_search import search_emails, validate_date_format
    from iobox.email_retrieval import get_email_content, download_attachment
    from iobox.markdown_converter import convert_email_to_markdown, convert_html_to_markdown
    from iobox.file_manager import (
        save_email_to_markdown, create_output_directory,
        check_for_duplicates, save_attachment,
    )
    from iobox.email_sender import send_message, compose_message, forward_email
except Exception:
    pass

__all__ = [
    "__version__",
    "get_gmail_service", "check_auth_status",
    "search_emails", "validate_date_format",
    "get_email_content", "download_attachment",
    "convert_email_to_markdown", "convert_html_to_markdown",
    "save_email_to_markdown", "create_output_directory",
    "check_for_duplicates", "save_attachment",
    "send_message", "compose_message", "forward_email",
]
