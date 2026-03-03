"""
MCP Server for iobox Gmail tools.

Exposes iobox Gmail functions as MCP tools for use with Claude Desktop,
Cursor, VS Code, and other MCP-compatible hosts.

Install with: pip install iobox[mcp]
Run with: python -m iobox.mcp_server
"""

import os
from mcp.server.fastmcp import FastMCP
from typing import Optional

from iobox.auth import get_gmail_service, check_auth_status, get_gmail_profile
from iobox.email_search import search_emails
from iobox.email_retrieval import (
    get_email_content,
    get_label_map,
    get_thread_content,
    modify_message_labels,
    resolve_label_name,
    batch_modify_labels,
    trash_message,
    untrash_message,
    batch_get_emails,
)
from iobox.markdown_converter import convert_email_to_markdown, convert_thread_to_markdown
from iobox.file_manager import (
    create_output_directory,
    save_email_to_markdown,
    check_for_duplicates,
    download_email_attachments,
    SyncState,
)
from iobox.email_sender import (
    send_message,
    compose_message,
    forward_email,
    create_draft,
    list_drafts,
    send_draft,
    delete_draft,
)
from iobox.utils import slugify_text

mcp = FastMCP("iobox")


# ---------------------------------------------------------------------------
# Search & Read
# ---------------------------------------------------------------------------

@mcp.tool()
def search_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_spam_trash: bool = False,
) -> list[dict]:
    """Search Gmail for emails matching a query.

    Args:
        query: Gmail search syntax (e.g. 'from:newsletter@example.com')
        max_results: Maximum number of results (default 10)
        days: Days back to search (default 7)
        start_date: Start date YYYY/MM/DD (overrides days)
        end_date: End date YYYY/MM/DD
        include_spam_trash: Include messages from SPAM and TRASH (default False)
    """
    service = get_gmail_service()
    label_map = get_label_map(service)
    return search_emails(
        service, query, max_results, days, start_date, end_date,
        label_map=label_map, include_spam_trash=include_spam_trash,
    )


@mcp.tool()
def get_email(message_id: str, prefer_html: bool = True) -> dict:
    """Retrieve full email content by Gmail message ID.

    Args:
        message_id: Gmail message ID
        prefer_html: Use HTML content if available (default True)
    """
    service = get_gmail_service()
    label_map = get_label_map(service)
    content_type = "text/html" if prefer_html else "text/plain"
    return get_email_content(service, message_id, preferred_content_type=content_type, label_map=label_map)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

@mcp.tool()
def save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: Optional[str] = None,
    include_spam_trash: bool = False,
) -> str:
    """Save a Gmail message as a Markdown file.

    Args:
        message_id: Gmail message ID
        output_dir: Directory to save the file (default: current dir)
        prefer_html: Use HTML content if available (default: True)
        download_attachments: Download email attachments (default: False)
        attachment_types: Filter attachments by extension, comma-separated (e.g. 'pdf,docx')
        include_spam_trash: Include messages from SPAM and TRASH (default False)

    Returns:
        Absolute path to the saved file.
    """
    service = get_gmail_service()
    label_map = get_label_map(service)
    content_type = "text/html" if prefer_html else "text/plain"
    email_data = get_email_content(service, message_id, preferred_content_type=content_type, label_map=label_map)
    md = convert_email_to_markdown(email_data)
    out = create_output_directory(output_dir)
    filepath = save_email_to_markdown(email_data, md, out)

    if download_attachments and email_data.get("attachments"):
        filters = [ext.strip().lower() for ext in attachment_types.split(",")] if attachment_types else []
        download_email_attachments(service=service, email_data=email_data, output_dir=out, attachment_filters=filters)

    return filepath


@mcp.tool()
def save_thread(
    thread_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    include_spam_trash: bool = False,
) -> str:
    """Save an entire Gmail thread as a single Markdown file.

    Args:
        thread_id: Gmail thread ID
        output_dir: Directory to save the file (default: current dir)
        prefer_html: Use HTML content if available (default: True)
        include_spam_trash: Include messages from SPAM and TRASH (default False)

    Returns:
        Absolute path to the saved file.
    """
    service = get_gmail_service()
    content_type = "text/html" if prefer_html else "text/plain"
    messages = get_thread_content(service, thread_id, preferred_content_type=content_type)
    md = convert_thread_to_markdown(messages)
    subject = messages[0].get("subject", "thread") if messages else "thread"
    subject_slug = slugify_text(subject)
    filename = f"{subject_slug}_{thread_id}.md"
    out = create_output_directory(output_dir)
    filepath = os.path.join(out, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    return filepath


@mcp.tool()
def save_emails_by_query(
    query: str,
    output_dir: str = ".",
    max_results: int = 10,
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: Optional[str] = None,
    include_spam_trash: bool = False,
    sync: bool = False,
) -> dict:
    """Save multiple Gmail messages matching a query as Markdown files.

    Args:
        query: Gmail search syntax
        output_dir: Directory to save files (default: current dir)
        max_results: Maximum emails to save (default 10)
        days: Days back to search (default 7)
        start_date: Start date YYYY/MM/DD (overrides days)
        end_date: End date YYYY/MM/DD
        prefer_html: Use HTML content if available (default True)
        download_attachments: Download attachments (default False)
        attachment_types: Filter attachments by extension, comma-separated
        include_spam_trash: Include SPAM and TRASH (default False)
        sync: Enable incremental sync — only fetch new emails since last run (default False)

    Returns:
        Summary dict with saved_count, skipped_count, and attachment_count.
    """
    service = get_gmail_service()
    label_map = get_label_map(service)
    content_type = "text/html" if prefer_html else "text/plain"
    out = create_output_directory(output_dir)
    att_filters = [ext.strip().lower() for ext in attachment_types.split(",")] if attachment_types else []

    # Incremental sync
    sync_state = SyncState(out)
    message_ids_to_fetch = None

    if sync:
        from iobox.email_search import get_new_messages
        state_exists = sync_state.load()
        if state_exists and sync_state.last_history_id:
            new_ids = get_new_messages(service, sync_state.last_history_id)
            if new_ids is not None:
                message_ids_to_fetch = new_ids

    if message_ids_to_fetch is not None:
        if not message_ids_to_fetch:
            profile = service.users().getProfile(userId="me").execute()
            sync_state.update(profile.get("historyId", sync_state.last_history_id), [])
            return {"saved_count": 0, "skipped_count": 0, "attachment_count": 0, "detail": "No new emails since last sync."}
        results_for_batch = [{"message_id": mid} for mid in message_ids_to_fetch]
    else:
        search_results = search_emails(
            service, query, max_results, days, start_date, end_date,
            label_map=label_map, include_spam_trash=include_spam_trash,
        )
        if not search_results:
            if sync:
                profile = service.users().getProfile(userId="me").execute()
                sync_state.update(profile.get("historyId", ""), [])
            return {"saved_count": 0, "skipped_count": 0, "attachment_count": 0, "detail": "No emails found."}
        results_for_batch = search_results

    all_ids = [r["message_id"] for r in results_for_batch]
    duplicates = check_for_duplicates(all_ids, out)
    ids_to_process = [mid for mid in all_ids if mid not in duplicates]

    saved_count = 0
    attachment_count = 0

    if ids_to_process:
        email_batch = batch_get_emails(service, ids_to_process, preferred_content_type=content_type, label_map=label_map)
        for email_data in email_batch:
            if "error" in email_data:
                continue
            md = convert_email_to_markdown(email_data)
            save_email_to_markdown(email_data, md, out)
            saved_count += 1
            if download_attachments and email_data.get("attachments"):
                res = download_email_attachments(service=service, email_data=email_data, output_dir=out, attachment_filters=att_filters)
                attachment_count += res["downloaded_count"]

    if sync:
        profile = service.users().getProfile(userId="me").execute()
        sync_state.update(profile.get("historyId", ""), ids_to_process)

    return {"saved_count": saved_count, "skipped_count": len(duplicates), "attachment_count": attachment_count}


# ---------------------------------------------------------------------------
# Send & Forward
# ---------------------------------------------------------------------------

@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html: bool = False,
    attachments: Optional[list[str]] = None,
) -> dict:
    """Send an email via Gmail.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text (plain text or HTML)
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        html: Send body as HTML content (default False)
        attachments: List of file paths to attach
    """
    service = get_gmail_service()
    content_type = "html" if html else "plain"
    if attachments:
        from pathlib import Path
        for fp in attachments:
            if not Path(fp).exists():
                raise FileNotFoundError(f"Attachment not found: {fp}")
    message = compose_message(
        to=to, subject=subject, body=body, cc=cc, bcc=bcc,
        content_type=content_type, attachments=attachments,
    )
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
def batch_forward_gmail(
    query: str,
    to: str,
    max_results: int = 10,
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """Forward multiple Gmail messages matching a query to a recipient.

    Args:
        query: Gmail search syntax to find messages
        to: Recipient email address
        max_results: Maximum messages to forward (default 10)
        days: Days back to search (default 7)
        start_date: Start date YYYY/MM/DD (overrides days)
        end_date: End date YYYY/MM/DD
        note: Optional text to prepend to each forwarded email

    Returns:
        Summary dict with forwarded_count.
    """
    service = get_gmail_service()
    label_map = get_label_map(service)
    results = search_emails(service, query, max_results, days, start_date, end_date, label_map=label_map)
    if not results:
        return {"forwarded_count": 0, "detail": "No emails found matching the query."}

    forwarded = 0
    for r in results:
        forward_email(service, message_id=r["message_id"], to=to, additional_text=note)
        forwarded += 1

    return {"forwarded_count": forwarded}


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

@mcp.tool()
def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html: bool = False,
    attachments: Optional[list[str]] = None,
) -> dict:
    """Create an email draft in Gmail.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text (plain text or HTML)
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        html: Use HTML content type (default False)
        attachments: List of file paths to attach
    """
    service = get_gmail_service()
    content_type = "html" if html else "plain"
    if attachments:
        from pathlib import Path
        for fp in attachments:
            if not Path(fp).exists():
                raise FileNotFoundError(f"Attachment not found: {fp}")
    message = compose_message(
        to=to, subject=subject, body=body, cc=cc, bcc=bcc,
        content_type=content_type, attachments=attachments,
    )
    return create_draft(service, message)


@mcp.tool()
def list_gmail_drafts(max_results: int = 10) -> list[dict]:
    """List Gmail drafts.

    Args:
        max_results: Maximum number of drafts to return (default 10)
    """
    service = get_gmail_service()
    return list_drafts(service, max_results=max_results)


@mcp.tool()
def send_gmail_draft(draft_id: str) -> dict:
    """Send an existing Gmail draft.

    Args:
        draft_id: The draft ID to send
    """
    service = get_gmail_service()
    return send_draft(service, draft_id)


@mcp.tool()
def delete_gmail_draft(draft_id: str) -> dict:
    """Permanently delete a Gmail draft.

    Args:
        draft_id: The draft ID to delete
    """
    service = get_gmail_service()
    return delete_draft(service, draft_id)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

@mcp.tool()
def modify_labels(
    message_id: str,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: Optional[str] = None,
    remove_label: Optional[str] = None,
) -> dict:
    """Add or remove labels on a Gmail message.

    Args:
        message_id: Gmail message ID
        mark_read: Mark as read
        mark_unread: Mark as unread
        star: Star the message
        unstar: Unstar the message
        archive: Archive (remove from INBOX)
        add_label: Label name to add
        remove_label: Label name to remove

    Returns:
        Updated message resource.
    """
    service = get_gmail_service()

    add_labels: list[str] = []
    remove_labels: list[str] = []

    if mark_read:
        remove_labels.append("UNREAD")
    if mark_unread:
        add_labels.append("UNREAD")
    if star:
        add_labels.append("STARRED")
    if unstar:
        remove_labels.append("STARRED")
    if archive:
        remove_labels.append("INBOX")
    if add_label:
        add_labels.append(resolve_label_name(service, add_label))
    if remove_label:
        remove_labels.append(resolve_label_name(service, remove_label))

    return modify_message_labels(service, message_id, add_labels or None, remove_labels or None)


@mcp.tool()
def batch_modify_gmail_labels(
    query: str,
    max_results: int = 10,
    days: int = 7,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: Optional[str] = None,
    remove_label: Optional[str] = None,
) -> dict:
    """Modify labels on multiple Gmail messages matching a query.

    Args:
        query: Gmail search syntax to find messages
        max_results: Maximum messages to modify (default 10)
        days: Days back to search (default 7)
        mark_read: Mark as read
        mark_unread: Mark as unread
        star: Star messages
        unstar: Unstar messages
        archive: Archive (remove from INBOX)
        add_label: Label name to add
        remove_label: Label name to remove

    Returns:
        Summary dict with count of modified messages.
    """
    service = get_gmail_service()
    label_map = get_label_map(service)

    add_labels: list[str] = []
    remove_labels: list[str] = []

    if mark_read:
        remove_labels.append("UNREAD")
    if mark_unread:
        add_labels.append("UNREAD")
    if star:
        add_labels.append("STARRED")
    if unstar:
        remove_labels.append("STARRED")
    if archive:
        remove_labels.append("INBOX")
    if add_label:
        add_labels.append(resolve_label_name(service, add_label))
    if remove_label:
        remove_labels.append(resolve_label_name(service, remove_label))

    results = search_emails(service, query, max_results, days, label_map=label_map)
    if not results:
        return {"modified_count": 0, "detail": "No emails found matching the query."}

    msg_ids = [r["message_id"] for r in results]
    if len(msg_ids) >= 2:
        batch_modify_labels(service, msg_ids, add_labels or None, remove_labels or None)
    else:
        modify_message_labels(service, msg_ids[0], add_labels or None, remove_labels or None)

    return {"modified_count": len(msg_ids)}


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

@mcp.tool()
def trash_gmail(message_id: str) -> dict:
    """Move a Gmail message to trash.

    Args:
        message_id: Gmail message ID to trash
    """
    service = get_gmail_service()
    return trash_message(service, message_id)


@mcp.tool()
def untrash_gmail(message_id: str) -> dict:
    """Restore a Gmail message from trash.

    Args:
        message_id: Gmail message ID to restore
    """
    service = get_gmail_service()
    return untrash_message(service, message_id)


@mcp.tool()
def batch_trash_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
) -> dict:
    """Move multiple Gmail messages matching a query to trash.

    Args:
        query: Gmail search syntax to find messages
        max_results: Maximum messages to trash (default 10)
        days: Days back to search (default 7)

    Returns:
        Summary dict with trashed_count.
    """
    service = get_gmail_service()
    label_map = get_label_map(service)
    results = search_emails(service, query, max_results, days, label_map=label_map)
    if not results:
        return {"trashed_count": 0, "detail": "No emails found matching the query."}

    for r in results:
        trash_message(service, r["message_id"])

    return {"trashed_count": len(results)}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@mcp.tool()
def check_auth() -> dict:
    """Check Gmail authentication status and profile info."""
    status = check_auth_status()
    try:
        service = get_gmail_service()
        profile = get_gmail_profile(service)
        status["email"] = profile.get("emailAddress")
        status["messages_total"] = profile.get("messagesTotal")
        status["threads_total"] = profile.get("threadsTotal")
    except Exception:
        pass
    return status


if __name__ == "__main__":
    mcp.run(transport="stdio")
