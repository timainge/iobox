"""
MCP Server for iobox Gmail tools.

Exposes iobox Gmail functions as MCP tools for use with Claude Desktop,
Cursor, VS Code, and other MCP-compatible hosts.

Install with: pip install iobox[mcp]
Run with: python -m iobox.mcp_server
"""

from mcp.server.fastmcp import FastMCP
from typing import Optional

from iobox.auth import get_gmail_service, check_auth_status
from iobox.email_search import search_emails
from iobox.email_retrieval import get_email_content
from iobox.markdown_converter import convert_email_to_markdown
from iobox.file_manager import create_output_directory, save_email_to_markdown
from iobox.email_sender import send_message, compose_message, forward_email

mcp = FastMCP("iobox")


@mcp.tool()
def search_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Search Gmail for emails matching a query.

    Args:
        query: Gmail search syntax (e.g. 'from:newsletter@example.com')
        max_results: Maximum number of results (default 10)
        days: Days back to search (default 7)
        start_date: Start date YYYY/MM/DD (overrides days)
        end_date: End date YYYY/MM/DD
    """
    service = get_gmail_service()
    return search_emails(service, query, max_results, days, start_date, end_date)


@mcp.tool()
def get_email(message_id: str) -> dict:
    """Retrieve full email content by Gmail message ID."""
    service = get_gmail_service()
    return get_email_content(service, message_id)


@mcp.tool()
def save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
) -> str:
    """Save a Gmail message as a Markdown file.

    Args:
        message_id: Gmail message ID
        output_dir: Directory to save the file (default: current dir)
        prefer_html: Use HTML content if available (default: True)

    Returns:
        Absolute path to the saved file.
    """
    service = get_gmail_service()
    content_type = "text/html" if prefer_html else "text/plain"
    email_data = get_email_content(service, message_id, preferred_content_type=content_type)
    md = convert_email_to_markdown(email_data)
    out = create_output_directory(output_dir)
    return save_email_to_markdown(email_data, md, out)


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> dict:
    """Send an email via Gmail.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
    """
    service = get_gmail_service()
    message = compose_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    return send_message(service, message)


@mcp.tool()
def forward_gmail(
    message_id: str,
    to: str,
    note: Optional[str] = None,
) -> dict:
    """Forward a Gmail message to a recipient.

    Args:
        message_id: Gmail message ID to forward
        to: Recipient email address
        note: Optional text to prepend
    """
    service = get_gmail_service()
    return forward_email(service, message_id=message_id, to=to, additional_text=note)


@mcp.tool()
def check_auth() -> dict:
    """Check Gmail authentication status."""
    return check_auth_status()


if __name__ == "__main__":
    mcp.run(transport="stdio")
