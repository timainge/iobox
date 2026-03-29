"""
Iobox - Gmail to Markdown Converter

A tool that extracts emails from Gmail based on specific criteria
and saves them as markdown files with YAML frontmatter.
"""

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("iobox")
except PackageNotFoundError:
    __version__ = "0.1.0"  # fallback for uninstalled dev

try:
    from iobox.providers.google.auth import check_auth_status, get_gmail_service
    from iobox.providers.google._retrieval import download_attachment, get_email_content
    from iobox.providers.google._search import search_emails, validate_date_format
    from iobox.providers.google._sender import compose_message, forward_email, send_message
    from iobox.processing.file_manager import (
        check_for_duplicates,
        create_output_directory,
        save_attachment,
        save_email_to_markdown,
    )
    from iobox.processing.markdown_converter import convert_email_to_markdown, convert_html_to_markdown
except Exception:
    pass

__all__ = [
    "__version__",
    "get_gmail_service",
    "check_auth_status",
    "search_emails",
    "validate_date_format",
    "get_email_content",
    "download_attachment",
    "convert_email_to_markdown",
    "convert_html_to_markdown",
    "save_email_to_markdown",
    "create_output_directory",
    "check_for_duplicates",
    "save_attachment",
    "send_message",
    "compose_message",
    "forward_email",
]
