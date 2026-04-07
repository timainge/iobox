"""
MCP Server for iobox workspace tools.

Exposes iobox functions as MCP tools for use with Claude Desktop,
Cursor, VS Code, and other MCP-compatible hosts.

Install with: pip install iobox[mcp]
Run with: python -m iobox.mcp_server
"""

import os
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from iobox.modes import MCP_TOOLS_BY_MODE, AccessMode, get_mode_from_env
from iobox.processing.file_manager import (
    SyncState,
    check_for_duplicates,
    create_output_directory,
    download_email_attachments,
    save_email_to_markdown,
)
from iobox.processing.markdown_converter import (
    convert_email_to_markdown,
    convert_thread_to_markdown,
)
from iobox.providers.google.auth import (
    check_auth_status,
    get_gmail_profile,
    get_gmail_service,
    set_active_mode,
)
from iobox.utils import slugify_text

mcp = FastMCP("iobox")

# ---------------------------------------------------------------------------
# Tool registry – functions are collected here and selectively registered
# with mcp.tool() based on the active access mode.
# ---------------------------------------------------------------------------

_ALL_TOOLS: dict[str, Any] = {}


def _tool(fn: Any) -> Any:
    """Collect a tool function without registering it yet."""
    _ALL_TOOLS[fn.__name__] = fn
    return fn


def register_tools(mode: AccessMode) -> None:
    """Register only the MCP tools allowed for *mode*."""
    allowed = MCP_TOOLS_BY_MODE[mode]
    for name, fn in _ALL_TOOLS.items():
        if name in allowed:
            mcp.tool()(fn)


# ---------------------------------------------------------------------------
# Provider / workspace factories (injectable for tests)
# ---------------------------------------------------------------------------


def _get_gmail_provider() -> Any:
    """Return a GmailProvider instance. Override in tests by patching."""
    from iobox.providers.google.email import GmailProvider

    return GmailProvider()


def _default_workspace_fn() -> Any | None:
    """Default factory: load active workspace from disk, or None."""
    try:
        from iobox.space_config import IOBOX_HOME, get_active_space, load_space
        from iobox.workspace import Workspace

        active = get_active_space()
        if not active:
            return None
        config = load_space(active)
        return Workspace.from_config(config, credentials_dir=str(IOBOX_HOME))
    except Exception:
        return None


def create_mcp_server(*, _workspace_fn: Callable[[], Any] | None = None) -> FastMCP:
    """Build the FastMCP server with an optional mock workspace factory for tests."""
    return mcp


# Module-level workspace factory (can be replaced in tests)
_workspace_factory: Callable[[], Any | None] = _default_workspace_fn


def _get_workspace() -> Any | None:
    """Return the active Workspace, or None if no space is configured."""
    return _workspace_factory()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _email_data_to_dict(data: Any) -> dict[str, Any]:
    """Convert EmailData (from_ key) to legacy MCP format (from key).

    Preserves backward compatibility for MCP clients that expect ``from``
    rather than ``from_``.
    """
    result = dict(data)
    if "from_" in result and "from" not in result:
        result["from"] = result.pop("from_")
    return result


# ---------------------------------------------------------------------------
# Search & Read
# ---------------------------------------------------------------------------


@_tool
def search_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
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
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    # Build EmailQuery from the legacy date params
    after: date | None = None
    before: date | None = None
    if start_date:
        parts = start_date.replace("-", "/").split("/")
        after = date(int(parts[0]), int(parts[1]), int(parts[2]))
    elif days:
        after = date.today() - timedelta(days=days)
    if end_date:
        parts = end_date.replace("-", "/").split("/")
        before = date(int(parts[0]), int(parts[1]), int(parts[2]))

    provider = _get_gmail_provider()
    results = provider.search_emails(
        EmailQuery(
            text=query,
            max_results=max_results,
            after=after,
            before=before,
            include_spam_trash=include_spam_trash,
        )
    )
    return [_email_data_to_dict(r) for r in results]


@_tool
def get_email(message_id: str, prefer_html: bool = True) -> dict:
    """Retrieve full email content by Gmail message ID.

    Args:
        message_id: Gmail message ID
        prefer_html: Use HTML content if available (default True)
    """
    content_type = "text/html" if prefer_html else "text/plain"
    provider = _get_gmail_provider()
    return _email_data_to_dict(provider.get_email_content(message_id, content_type))


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


@_tool
def save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: str | None = None,
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
    content_type = "text/html" if prefer_html else "text/plain"
    provider = _get_gmail_provider()
    email_data = _email_data_to_dict(provider.get_email_content(message_id, content_type))
    md = convert_email_to_markdown(email_data)
    out = create_output_directory(output_dir)
    filepath = save_email_to_markdown(email_data, md, out)

    if download_attachments and email_data.get("attachments"):
        filters = (
            [ext.strip().lower() for ext in attachment_types.split(",")] if attachment_types else []
        )
        service = get_gmail_service()
        download_email_attachments(
            service=service,
            email_data=email_data,
            output_dir=out,
            attachment_filters=filters,
        )

    return filepath


@_tool
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
    provider = _get_gmail_provider()
    messages_raw = provider.get_thread(thread_id)
    messages = [_email_data_to_dict(m) for m in messages_raw]
    md = convert_thread_to_markdown(messages)
    subject = messages[0].get("subject", "thread") if messages else "thread"
    subject_slug = slugify_text(subject)
    filename = f"{subject_slug}_{thread_id}.md"
    out = create_output_directory(output_dir)
    filepath = os.path.join(out, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    return filepath


@_tool
def save_emails_by_query(
    query: str,
    output_dir: str = ".",
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: str | None = None,
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
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    content_type = "text/html" if prefer_html else "text/plain"
    out = create_output_directory(output_dir)
    att_filters = (
        [ext.strip().lower() for ext in attachment_types.split(",")] if attachment_types else []
    )
    provider = _get_gmail_provider()

    # Incremental sync
    sync_state = SyncState(out)
    message_ids_to_fetch: list[str] | None = None

    if sync:
        state_exists = sync_state.load()
        if state_exists and sync_state.last_history_id:
            new_ids = provider.get_new_messages(sync_state.last_history_id)
            if new_ids is not None:
                message_ids_to_fetch = new_ids

    if message_ids_to_fetch is not None:
        if not message_ids_to_fetch:
            service = get_gmail_service()
            profile = service.users().getProfile(userId="me").execute()
            sync_state.update(profile.get("historyId", sync_state.last_history_id), [])
            return {
                "saved_count": 0,
                "skipped_count": 0,
                "attachment_count": 0,
                "detail": "No new emails since last sync.",
            }
    else:
        # Build EmailQuery
        after: date | None = None
        before: date | None = None
        if start_date:
            parts = start_date.replace("-", "/").split("/")
            after = date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif days:
            after = date.today() - timedelta(days=days)
        if end_date:
            parts = end_date.replace("-", "/").split("/")
            before = date(int(parts[0]), int(parts[1]), int(parts[2]))

        search_results = provider.search_emails(
            EmailQuery(
                text=query,
                max_results=max_results,
                after=after,
                before=before,
                include_spam_trash=include_spam_trash,
            )
        )
        if not search_results:
            if sync:
                service = get_gmail_service()
                profile = service.users().getProfile(userId="me").execute()
                sync_state.update(profile.get("historyId", ""), [])
            return {
                "saved_count": 0,
                "skipped_count": 0,
                "attachment_count": 0,
                "detail": "No emails found.",
            }
        message_ids_to_fetch = [r["message_id"] for r in search_results]

    all_ids = list(message_ids_to_fetch)
    duplicates = check_for_duplicates(all_ids, out)
    ids_to_process = [mid for mid in all_ids if mid not in duplicates]

    saved_count = 0
    attachment_count = 0

    if ids_to_process:
        email_batch = provider.batch_get_emails(ids_to_process, preferred_content_type=content_type)
        for email_raw in email_batch:
            if "error" in email_raw:
                continue
            email_data = _email_data_to_dict(email_raw)
            md = convert_email_to_markdown(email_data)
            save_email_to_markdown(email_data, md, out)
            saved_count += 1
            if download_attachments and email_data.get("attachments"):
                service = get_gmail_service()
                res = download_email_attachments(
                    service=service,
                    email_data=email_data,
                    output_dir=out,
                    attachment_filters=att_filters,
                )
                attachment_count += res["downloaded_count"]

    if sync:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        sync_state.update(profile.get("historyId", ""), ids_to_process)

    return {
        "saved_count": saved_count,
        "skipped_count": len(duplicates),
        "attachment_count": attachment_count,
    }


# ---------------------------------------------------------------------------
# Send & Forward
# ---------------------------------------------------------------------------


@_tool
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html: bool = False,
    attachments: list[str] | None = None,
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
    from pathlib import Path

    if attachments:
        for fp in attachments:
            if not Path(fp).exists():
                raise FileNotFoundError(f"Attachment not found: {fp}")

    content_type = "html" if html else "plain"
    provider = _get_gmail_provider()
    return provider.send_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        content_type=content_type,
        attachments=attachments,
    )


@_tool
def forward_gmail(
    message_id: str,
    to: str,
    note: str | None = None,
) -> dict:
    """Forward a Gmail message to a recipient.

    Args:
        message_id: Gmail message ID to forward
        to: Recipient email address
        note: Optional text to prepend
    """
    provider = _get_gmail_provider()
    return provider.forward_message(message_id=message_id, to=to, comment=note)


@_tool
def batch_forward_gmail(
    query: str,
    to: str,
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    note: str | None = None,
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
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    after: date | None = None
    before: date | None = None
    if start_date:
        parts = start_date.replace("-", "/").split("/")
        after = date(int(parts[0]), int(parts[1]), int(parts[2]))
    elif days:
        after = date.today() - timedelta(days=days)
    if end_date:
        parts = end_date.replace("-", "/").split("/")
        before = date(int(parts[0]), int(parts[1]), int(parts[2]))

    provider = _get_gmail_provider()
    results = provider.search_emails(
        EmailQuery(text=query, max_results=max_results, after=after, before=before)
    )
    if not results:
        return {"forwarded_count": 0, "detail": "No emails found matching the query."}

    for r in results:
        provider.forward_message(message_id=r["message_id"], to=to, comment=note)

    return {"forwarded_count": len(results)}


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


@_tool
def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html: bool = False,
    attachments: list[str] | None = None,
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
    from pathlib import Path

    if attachments:
        for fp in attachments:
            if not Path(fp).exists():
                raise FileNotFoundError(f"Attachment not found: {fp}")

    content_type = "html" if html else "plain"
    provider = _get_gmail_provider()
    return provider.create_draft(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        content_type=content_type,
        attachments=attachments,
    )


@_tool
def list_gmail_drafts(max_results: int = 10) -> list[dict]:
    """List Gmail drafts.

    Args:
        max_results: Maximum number of drafts to return (default 10)
    """
    provider = _get_gmail_provider()
    return list(provider.list_drafts(max_results=max_results))


@_tool
def send_gmail_draft(draft_id: str) -> dict:
    """Send an existing Gmail draft.

    Args:
        draft_id: The draft ID to send
    """
    provider = _get_gmail_provider()
    return provider.send_draft(draft_id)


@_tool
def delete_gmail_draft(draft_id: str) -> dict:
    """Permanently delete a Gmail draft.

    Args:
        draft_id: The draft ID to delete
    """
    provider = _get_gmail_provider()
    return provider.delete_draft(draft_id)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@_tool
def modify_labels(
    message_id: str,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: str | None = None,
    remove_label: str | None = None,
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
    from iobox.providers.google._retrieval import (
        modify_message_labels,
        resolve_label_name,
    )

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


@_tool
def batch_modify_gmail_labels(
    query: str,
    max_results: int = 10,
    days: int = 7,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: str | None = None,
    remove_label: str | None = None,
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
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery
    from iobox.providers.google._retrieval import (
        batch_modify_labels,
        modify_message_labels,
        resolve_label_name,
    )

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

    provider = _get_gmail_provider()
    after_date: date | None = date.today() - timedelta(days=days) if days else None
    results = provider.search_emails(
        EmailQuery(text=query, max_results=max_results, after=after_date)
    )
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


@_tool
def trash_gmail(message_id: str) -> dict:
    """Move a Gmail message to trash.

    Args:
        message_id: Gmail message ID to trash
    """
    provider = _get_gmail_provider()
    provider.trash(message_id)
    return {"message_id": message_id, "status": "trashed"}


@_tool
def untrash_gmail(message_id: str) -> dict:
    """Restore a Gmail message from trash.

    Args:
        message_id: Gmail message ID to restore
    """
    provider = _get_gmail_provider()
    provider.untrash(message_id)
    return {"message_id": message_id, "status": "untrashed"}


@_tool
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
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    provider = _get_gmail_provider()
    after_date: date | None = date.today() - timedelta(days=days) if days else None
    results = provider.search_emails(
        EmailQuery(text=query, max_results=max_results, after=after_date)
    )
    if not results:
        return {"trashed_count": 0, "detail": "No emails found matching the query."}

    for r in results:
        provider.trash(r["message_id"])

    return {"trashed_count": len(results)}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@_tool
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


# ---------------------------------------------------------------------------
# Workspace: cross-type search
# ---------------------------------------------------------------------------


@_tool
def search_workspace(
    query: str,
    types: list[str] | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Cross-type search across messages, calendar events, and files.

    Args:
        query: Search text.
        types: List of ``"email"``, ``"event"``, ``"file"`` (default: all).
        max_results: Max results per resource type (default 10).

    Returns:
        List of Resource dicts with ``resource_type`` field for client dispatch.
    """
    ws = _get_workspace()
    if not ws:
        return [{"error": "No active workspace configured. Run `iobox space create` first."}]
    try:
        results = ws.search(query, types=types, max_results_per_type=max_results)
        return [dict(r) for r in results]
    except Exception as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Workspace: calendar events
# ---------------------------------------------------------------------------


@_tool
def list_events(
    after: str | None = None,
    before: str | None = None,
    text: str | None = None,
    provider: str | None = None,
    max_results: int = 25,
) -> list[dict]:
    """List calendar events from the active workspace.

    Args:
        after: Start date filter (YYYY-MM-DD).
        before: End date filter (YYYY-MM-DD).
        text: Text search filter.
        provider: Provider slot name (default: all calendar slots).
        max_results: Maximum results (default 25).
    """
    from iobox.providers.base import EventQuery

    ws = _get_workspace()
    if not ws:
        return [{"error": "No active workspace configured."}]
    try:
        query = EventQuery(text=text, after=after, before=before, max_results=max_results)
        providers = [provider] if provider else None
        events = ws.list_events(query, providers=providers)
        return [dict(e) for e in events]
    except Exception as exc:
        return [{"error": str(exc)}]


@_tool
def get_event(event_id: str, provider: str | None = None) -> dict:
    """Get a single calendar event by ID.

    Args:
        event_id: Event ID.
        provider: Provider slot name (default: first calendar slot).
    """
    ws = _get_workspace()
    if not ws:
        return {"error": "No active workspace configured."}
    if not ws.calendar_providers:
        return {"error": "No calendar providers in workspace."}
    slot = ws.calendar_providers[0]
    if provider:
        matches = [s for s in ws.calendar_providers if s.name == provider]
        if not matches:
            return {"error": f"Calendar provider '{provider}' not found."}
        slot = matches[0]
    try:
        return dict(slot.provider.get_event(event_id))
    except KeyError:
        return {"error": f"Event '{event_id}' not found."}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Workspace: files
# ---------------------------------------------------------------------------


@_tool
def list_files(
    query: str,
    provider: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """List files from the active workspace.

    Args:
        query: Search text (required — avoids listing all files).
        provider: Provider slot name (default: all file slots).
        max_results: Maximum results (default 20).
    """
    from iobox.providers.base import FileQuery

    ws = _get_workspace()
    if not ws:
        return [{"error": "No active workspace configured."}]
    try:
        fq = FileQuery(text=query, max_results=max_results)
        providers = [provider] if provider else None
        files = ws.list_files(fq, providers=providers)
        return [dict(f) for f in files]
    except Exception as exc:
        return [{"error": str(exc)}]


@_tool
def get_file(file_id: str, provider: str | None = None) -> dict:
    """Get file metadata by ID.

    Args:
        file_id: File ID.
        provider: Provider slot name (default: first file slot).
    """
    ws = _get_workspace()
    if not ws:
        return {"error": "No active workspace configured."}
    if not ws.file_providers:
        return {"error": "No file providers in workspace."}
    slot = ws.file_providers[0]
    if provider:
        matches = [s for s in ws.file_providers if s.name == provider]
        if not matches:
            return {"error": f"File provider '{provider}' not found."}
        slot = matches[0]
    try:
        return dict(slot.provider.get_file(file_id))
    except KeyError:
        return {"error": f"File '{file_id}' not found."}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def get_file_content(file_id: str, provider: str | None = None) -> dict:
    """Get text content of a file.

    Args:
        file_id: File ID.
        provider: Provider slot name (default: first file slot).

    Returns:
        Dict with ``content`` key (str) or ``error`` key on failure.
    """
    ws = _get_workspace()
    if not ws:
        return {"error": "No active workspace configured."}
    if not ws.file_providers:
        return {"error": "No file providers in workspace."}
    slot = ws.file_providers[0]
    if provider:
        matches = [s for s in ws.file_providers if s.name == provider]
        if not matches:
            return {"error": f"File provider '{provider}' not found."}
        slot = matches[0]
    try:
        content = slot.provider.get_file_content(file_id)
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


@_tool
def semantic_search_workspace(
    query: str,
    types: list[str] | None = None,
    top_k: int = 10,
    backend: str = "openai",
    workspace: str | None = None,
) -> list[dict]:
    """Semantic (vector) search across indexed workspace resources.

    Requires the ``semantic`` optional dependency group:
    ``pip install 'iobox[semantic]'``.

    Resources must be indexed first via ``embed_resources()`` before this
    tool returns meaningful results.  Falls back gracefully if no index
    exists yet.

    Args:
        query: Natural-language search query.
        types: Resource types to search — any of ``"email"``, ``"event"``,
            ``"file"`` (default: all types).
        top_k: Maximum number of results (default 10).
        backend: Embedding backend — ``"openai"`` (default), ``"voyage"``,
            or ``"local"``.
        workspace: Workspace name (default: active workspace).

    Returns:
        List of dicts with ``id``, ``resource_type``, ``provider_id``, and
        ``score`` fields, ranked by similarity (highest first).
    """
    try:
        from iobox.processing.embed import get_backend as _get_backend
        from iobox.processing.embed import semantic_search as _semantic_search
    except ImportError:
        return [
            {
                "error": (
                    "Semantic search requires 'iobox[semantic]'. "
                    "Run: pip install 'iobox[semantic]'"
                )
            }
        ]

    # Resolve workspace name
    ws_name = workspace
    if not ws_name:
        try:
            from iobox.space_config import get_active_space

            ws_name = get_active_space()
        except Exception:
            pass
    if not ws_name:
        return [{"error": "No active workspace. Set one with `iobox space use NAME`."}]

    try:
        emb_backend = _get_backend(backend)
        results = _semantic_search(query, ws_name, types=types, top_k=top_k, backend=emb_backend)
        return results
    except Exception as exc:
        return [{"error": str(exc)}]


def main() -> None:
    from iobox.accounts import get_account_from_env, set_active_account

    mode = get_mode_from_env()
    set_active_mode(mode)
    set_active_account(get_account_from_env())
    register_tools(mode)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
