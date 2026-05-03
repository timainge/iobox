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


def _default_workspace_fn(name: str | None = None) -> Any | None:
    """Default factory: load named (or active) workspace from disk, or None."""
    try:
        from iobox.space_config import IOBOX_HOME, get_active_space, load_space
        from iobox.workspace import Workspace

        target = name or get_active_space()
        if not target:
            return None
        config = load_space(target)
        return Workspace.from_config(config, credentials_dir=str(IOBOX_HOME))
    except Exception:
        return None


def create_mcp_server(*, _workspace_fn: Callable[..., Any] | None = None) -> FastMCP:
    """Build the FastMCP server with an optional mock workspace factory for tests."""
    return mcp


# Module-level workspace factory (can be replaced in tests).
# Accepts an optional workspace name; ``None`` means "use the active space".
_workspace_factory: Callable[..., Any | None] = _default_workspace_fn


def _get_workspace(name: str | None = None) -> Any | None:
    """Return the named (or active) Workspace, or None if not configured."""
    try:
        # Newer factories accept a name argument; tolerate older zero-arg fns.
        return _workspace_factory(name)  # type: ignore[call-arg]
    except TypeError:
        return _workspace_factory()


def _find_email_slot(ws: Any, name: str | None = None) -> Any | None:
    """Return the named email slot, or the first slot if name is None."""
    if not ws.email_providers:
        return None
    if name is None:
        return ws.email_providers[0]
    for slot in ws.email_providers:
        if slot.name == name:
            return slot
    return None


def _find_calendar_slot(ws: Any, name: str | None = None) -> Any | None:
    """Return the named calendar slot, or the first slot if name is None."""
    if not ws.calendar_providers:
        return None
    if name is None:
        return ws.calendar_providers[0]
    for slot in ws.calendar_providers:
        if slot.name == name:
            return slot
    return None


def _find_file_slot(ws: Any, name: str | None = None) -> Any | None:
    """Return the named file slot, or the first slot if name is None."""
    if not ws.file_providers:
        return None
    if name is None:
        return ws.file_providers[0]
    for slot in ws.file_providers:
        if slot.name == name:
            return slot
    return None


def _resolve_email_provider(
    provider: str | None = None,
    workspace: str | None = None,
) -> Any:
    """Resolve an email provider via workspace slot, falling back to legacy Gmail.

    Resolution order:
    1. If a workspace (named or active) is configured and has email slots, return
       the matching slot's provider — this is the only path that supports
       multiple Gmail/Outlook accounts.
    2. Otherwise, fall back to the legacy module-level ``GmailProvider()``
       (single-account, env-driven).
    """
    ws = _get_workspace(workspace) if (workspace or provider) else _get_workspace()
    if ws is not None and ws.email_providers:
        slot = _find_email_slot(ws, provider)
        if slot is None:
            available = ", ".join(s.name for s in ws.email_providers)
            raise ValueError(
                f"Email provider '{provider}' not found in workspace. Available: {available}"
            )
        return slot.provider
    if provider is not None:
        raise ValueError(
            "No active workspace; cannot route by provider name. "
            "Run `iobox space create` and `iobox space add google ACCOUNT --email ...` first."
        )
    return _get_gmail_provider()


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
    provider: str | None = None,
    workspace: str | None = None,
) -> list[dict]:
    """Search email for messages matching a query.

    When an iobox workspace is active, this fans out across the configured
    email slots (Gmail and/or Outlook). Pass ``provider`` to target a single
    slot, or omit to search every email slot in parallel. With no active
    workspace, falls back to the single-account Gmail provider.

    Args:
        query: Search text (Gmail uses Gmail search syntax; Outlook accepts
            free-text and basic operators).
        max_results: Maximum number of results per slot (default 10).
        days: Days back to search (default 7).
        start_date: Start date YYYY/MM/DD (overrides days).
        end_date: End date YYYY/MM/DD.
        include_spam_trash: Include messages from SPAM and TRASH (default False).
        provider: Optional email slot name (e.g. ``"personal-gmail"``).
        workspace: Optional workspace name (default: active workspace).
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

    eq = EmailQuery(
        text=query,
        max_results=max_results,
        after=after,
        before=before,
        include_spam_trash=include_spam_trash,
    )

    ws = _get_workspace(workspace) if (workspace or provider) else _get_workspace()
    if ws is not None and ws.email_providers:
        providers_arg = [provider] if provider else None
        try:
            results = ws.search_emails(eq, providers=providers_arg)
        except Exception as exc:
            return [{"error": str(exc)}]
        return [_email_data_to_dict(r) for r in results]

    # Legacy fallback: single-account Gmail
    p = _get_gmail_provider()
    results = p.search_emails(eq)
    return [_email_data_to_dict(r) for r in results]


@_tool
def get_email(
    message_id: str,
    prefer_html: bool = True,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Retrieve full email content by message ID.

    Args:
        message_id: Email message ID (Gmail message ID or Outlook ImmutableId).
        prefer_html: Use HTML content if available (default True).
        provider: Optional email slot name. Required when the workspace has
            multiple email slots and you want a specific account.
        workspace: Optional workspace name (default: active workspace).
    """
    content_type = "text/html" if prefer_html else "text/plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return _email_data_to_dict(p.get_email_content(message_id, content_type))


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
    provider: str | None = None,
    workspace: str | None = None,
) -> str:
    """Save an email message as a Markdown file.

    Args:
        message_id: Email message ID.
        output_dir: Directory to save the file (default: current dir).
        prefer_html: Use HTML content if available (default: True).
        download_attachments: Download email attachments (default: False).
            Currently only supported for Gmail slots.
        attachment_types: Filter attachments by extension, comma-separated.
        include_spam_trash: Include messages from SPAM and TRASH (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Absolute path to the saved file.
    """
    content_type = "text/html" if prefer_html else "text/plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    email_data = _email_data_to_dict(p.get_email_content(message_id, content_type))
    md = convert_email_to_markdown(email_data)
    out = create_output_directory(output_dir)
    filepath = save_email_to_markdown(email_data, md, out)

    if download_attachments and email_data.get("attachments"):
        # Attachment download currently uses the Gmail-specific service handle.
        try:
            filters = (
                [ext.strip().lower() for ext in attachment_types.split(",")]
                if attachment_types
                else []
            )
            service = get_gmail_service()
            download_email_attachments(
                service=service,
                email_data=email_data,
                output_dir=out,
                attachment_filters=filters,
            )
        except Exception:
            # Non-Gmail providers fall through silently — Markdown is still saved.
            pass

    return filepath


@_tool
def save_thread(
    thread_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    include_spam_trash: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> str:
    """Save an entire email thread/conversation as a single Markdown file.

    Args:
        thread_id: Thread/conversation ID.
        output_dir: Directory to save the file (default: current dir).
        prefer_html: Use HTML content if available (default: True).
        include_spam_trash: Include messages from SPAM and TRASH (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Absolute path to the saved file.
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    messages_raw = p.get_thread(thread_id)
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
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save multiple email messages matching a query as Markdown files.

    Args:
        query: Email search syntax.
        output_dir: Directory to save files (default: current dir).
        max_results: Maximum emails to save (default 10).
        days: Days back to search (default 7).
        start_date: Start date YYYY/MM/DD (overrides days).
        end_date: End date YYYY/MM/DD.
        prefer_html: Use HTML content if available (default True).
        download_attachments: Download attachments (default False, Gmail only).
        attachment_types: Filter attachments by extension, comma-separated.
        include_spam_trash: Include SPAM and TRASH (default False).
        sync: Enable incremental sync — Gmail only (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

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
    p = _resolve_email_provider(provider=provider, workspace=workspace)

    # Incremental sync
    sync_state = SyncState(out)
    message_ids_to_fetch: list[str] | None = None

    if sync:
        state_exists = sync_state.load()
        if state_exists and sync_state.last_history_id:
            new_ids = p.get_new_messages(sync_state.last_history_id)
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

        search_results = p.search_emails(
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
                try:
                    service = get_gmail_service()
                    profile = service.users().getProfile(userId="me").execute()
                    sync_state.update(profile.get("historyId", ""), [])
                except Exception:
                    pass
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
        email_batch = p.batch_get_emails(ids_to_process, preferred_content_type=content_type)
        for email_raw in email_batch:
            if "error" in email_raw:
                continue
            email_data = _email_data_to_dict(email_raw)
            md = convert_email_to_markdown(email_data)
            save_email_to_markdown(email_data, md, out)
            saved_count += 1
            if download_attachments and email_data.get("attachments"):
                try:
                    service = get_gmail_service()
                    res = download_email_attachments(
                        service=service,
                        email_data=email_data,
                        output_dir=out,
                        attachment_filters=att_filters,
                    )
                    attachment_count += res["downloaded_count"]
                except Exception:
                    pass  # Non-Gmail providers: skip attachments silently.

    if sync:
        try:
            service = get_gmail_service()
            profile = service.users().getProfile(userId="me").execute()
            sync_state.update(profile.get("historyId", ""), ids_to_process)
        except Exception:
            pass  # sync only meaningful for Gmail.

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
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Send an email via the active provider slot.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text (plain text or HTML).
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
        html: Send body as HTML content (default False).
        attachments: List of file paths to attach.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    from pathlib import Path

    if attachments:
        for fp in attachments:
            if not Path(fp).exists():
                raise FileNotFoundError(f"Attachment not found: {fp}")

    content_type = "html" if html else "plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.send_message(
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
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Forward an email to a recipient.

    Args:
        message_id: Source message ID to forward.
        to: Recipient email address.
        note: Optional text to prepend.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.forward_message(message_id=message_id, to=to, comment=note)


@_tool
def batch_forward_gmail(
    query: str,
    to: str,
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    note: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Forward multiple emails matching a query to a recipient.

    Args:
        query: Email search syntax to find messages.
        to: Recipient email address.
        max_results: Maximum messages to forward (default 10).
        days: Days back to search (default 7).
        start_date: Start date YYYY/MM/DD (overrides days).
        end_date: End date YYYY/MM/DD.
        note: Optional text to prepend to each forwarded email.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

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

    p = _resolve_email_provider(provider=provider, workspace=workspace)
    results = p.search_emails(
        EmailQuery(text=query, max_results=max_results, after=after, before=before)
    )
    if not results:
        return {"forwarded_count": 0, "detail": "No emails found matching the query."}

    for r in results:
        p.forward_message(message_id=r["message_id"], to=to, comment=note)

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
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create an email draft.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text (plain text or HTML).
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
        html: Use HTML content type (default False).
        attachments: List of file paths to attach.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    from pathlib import Path

    if attachments:
        for fp in attachments:
            if not Path(fp).exists():
                raise FileNotFoundError(f"Attachment not found: {fp}")

    content_type = "html" if html else "plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.create_draft(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        content_type=content_type,
        attachments=attachments,
    )


@_tool
def list_gmail_drafts(
    max_results: int = 10,
    provider: str | None = None,
    workspace: str | None = None,
) -> list[dict]:
    """List email drafts.

    Args:
        max_results: Maximum number of drafts to return (default 10).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return list(p.list_drafts(max_results=max_results))


@_tool
def send_gmail_draft(
    draft_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Send an existing email draft.

    Args:
        draft_id: The draft ID to send.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.send_draft(draft_id)


@_tool
def delete_gmail_draft(
    draft_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Permanently delete an email draft.

    Args:
        draft_id: The draft ID to delete.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.delete_draft(draft_id)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def _apply_label_actions(
    p: Any,
    message_id: str,
    *,
    mark_read: bool,
    mark_unread: bool,
    star: bool,
    unstar: bool,
    archive: bool,
    add_label: str | None,
    remove_label: str | None,
) -> None:
    """Apply label actions via the EmailProvider ABC (works for Gmail + Outlook)."""
    if mark_read:
        p.mark_read(message_id, True)
    if mark_unread:
        p.mark_read(message_id, False)
    if star:
        p.set_star(message_id, True)
    if unstar:
        p.set_star(message_id, False)
    if archive:
        p.archive(message_id)
    if add_label:
        p.add_tag(message_id, add_label)
    if remove_label:
        p.remove_tag(message_id, remove_label)


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
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Add or remove labels/tags on an email message.

    Args:
        message_id: Email message ID.
        mark_read: Mark as read.
        mark_unread: Mark as unread.
        star: Star the message.
        unstar: Unstar the message.
        archive: Archive (remove from INBOX).
        add_label: Label/tag name to add.
        remove_label: Label/tag name to remove.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Status dict with the message ID and ``status: "modified"``.
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    _apply_label_actions(
        p,
        message_id,
        mark_read=mark_read,
        mark_unread=mark_unread,
        star=star,
        unstar=unstar,
        archive=archive,
        add_label=add_label,
        remove_label=remove_label,
    )
    return {"message_id": message_id, "status": "modified"}


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
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Modify labels/tags on multiple email messages matching a query.

    Args:
        query: Email search syntax to find messages.
        max_results: Maximum messages to modify (default 10).
        days: Days back to search (default 7).
        mark_read: Mark as read.
        mark_unread: Mark as unread.
        star: Star messages.
        unstar: Unstar messages.
        archive: Archive (remove from INBOX).
        add_label: Label/tag name to add.
        remove_label: Label/tag name to remove.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Summary dict with ``modified_count``.
    """
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    p = _resolve_email_provider(provider=provider, workspace=workspace)
    after_date: date | None = date.today() - timedelta(days=days) if days else None
    results = p.search_emails(EmailQuery(text=query, max_results=max_results, after=after_date))
    if not results:
        return {"modified_count": 0, "detail": "No emails found matching the query."}

    msg_ids = [r["message_id"] for r in results]
    for mid in msg_ids:
        _apply_label_actions(
            p,
            mid,
            mark_read=mark_read,
            mark_unread=mark_unread,
            star=star,
            unstar=unstar,
            archive=archive,
            add_label=add_label,
            remove_label=remove_label,
        )

    return {"modified_count": len(msg_ids)}


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


@_tool
def trash_gmail(
    message_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Move an email message to trash.

    Args:
        message_id: Email message ID to trash.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    p.trash(message_id)
    return {"message_id": message_id, "status": "trashed"}


@_tool
def untrash_gmail(
    message_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Restore an email message from trash.

    Args:
        message_id: Email message ID to restore.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    p.untrash(message_id)
    return {"message_id": message_id, "status": "untrashed"}


@_tool
def batch_trash_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Move multiple email messages matching a query to trash.

    Args:
        query: Email search syntax to find messages.
        max_results: Maximum messages to trash (default 10).
        days: Days back to search (default 7).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Summary dict with trashed_count.
    """
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    p = _resolve_email_provider(provider=provider, workspace=workspace)
    after_date: date | None = date.today() - timedelta(days=days) if days else None
    results = p.search_emails(EmailQuery(text=query, max_results=max_results, after=after_date))
    if not results:
        return {"trashed_count": 0, "detail": "No emails found matching the query."}

    for r in results:
        p.trash(r["message_id"])

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
    workspace: str | None = None,
) -> list[dict]:
    """Cross-type search across email, calendar events, and files.

    Fans out across every configured slot in parallel — covers multiple
    Gmail accounts, multiple Outlook accounts, or any mix.

    Args:
        query: Search text.
        types: List of ``"email"``, ``"event"``, ``"file"`` (default: all).
        max_results: Max results per resource type (default 10).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        List of Resource dicts with a ``resource_type`` field for dispatch.
    """
    ws = _get_workspace(workspace)
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
    workspace: str | None = None,
) -> list[dict]:
    """List calendar events from the active workspace.

    Fans out across every calendar slot when ``provider`` is omitted —
    covers multiple Google Calendar accounts in a single call.

    Args:
        after: Start date filter (YYYY-MM-DD).
        before: End date filter (YYYY-MM-DD).
        text: Text search filter.
        provider: Calendar slot name (default: all calendar slots).
        max_results: Maximum results (default 25).
        workspace: Optional workspace name (default: active workspace).
    """
    from iobox.providers.base import EventQuery

    ws = _get_workspace(workspace)
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
def get_event(
    event_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Get a single calendar event by ID.

    Args:
        event_id: Event ID.
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        return dict(slot.provider.get_event(event_id))
    except KeyError:
        return {"error": f"Event '{event_id}' not found."}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def save_event(
    event_id: str,
    output_dir: str = ".",
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save a calendar event as a Markdown file.

    Args:
        event_id: Event ID.
        output_dir: Directory to save the file (default: current dir).
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``filepath`` and ``title`` keys, or ``error``.
    """
    from iobox.processing.markdown import convert_event_to_markdown

    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        event = slot.provider.get_event(event_id)
        md = convert_event_to_markdown(event)
        out = create_output_directory(output_dir)
        title_slug = slugify_text(event.get("title", "event"))
        filename = f"{title_slug}_{event_id}.md"
        filepath = os.path.join(out, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        return {"filepath": filepath, "title": event.get("title", "")}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def create_event(
    title: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    all_day: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create a calendar event.

    Args:
        title: Event title.
        start: ISO 8601 start (e.g. ``"2026-04-01T09:00:00"``) or ``YYYY-MM-DD``
            for all-day events.
        end: ISO 8601 end or ``YYYY-MM-DD``.
        description: Optional event description.
        location: Optional location.
        attendees: Optional list of attendee email addresses.
        all_day: Treat start/end as date-only (default False).
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``title``, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        event = slot.provider.create_event(
            title=title,
            start=start,
            end=end,
            all_day=all_day,
            description=description,
            location=location,
            attendees=attendees or [],
        )
        return {"id": event.get("id", ""), "title": event.get("title", title)}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def update_event(
    event_id: str,
    updates: dict,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Update fields on an existing calendar event.

    Args:
        event_id: Event ID to update.
        updates: Dict of fields to change (e.g. ``{"title": "...", "start": "..."}``).
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Updated event dict, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        return dict(slot.provider.update_event(event_id, updates))
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def delete_event(
    event_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Delete a calendar event.

    Args:
        event_id: Event ID to delete.
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        slot.provider.delete_event(event_id)
        return {"event_id": event_id, "status": "deleted"}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def rsvp_event(
    event_id: str,
    response: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """RSVP to a calendar event invitation.

    Args:
        event_id: Event ID.
        response: ``"accepted"``, ``"declined"``, or ``"tentative"``.
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Updated event dict with the new response, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        return dict(slot.provider.rsvp(event_id, response))
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
    workspace: str | None = None,
) -> list[dict]:
    """List files from the active workspace.

    Fans out across every file slot when ``provider`` is omitted — covers
    multiple Drive/OneDrive accounts in a single call.

    Args:
        query: Search text (required — avoids listing all files).
        provider: File slot name (default: all file slots).
        max_results: Maximum results (default 20).
        workspace: Optional workspace name (default: active workspace).
    """
    from iobox.providers.base import FileQuery

    ws = _get_workspace(workspace)
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
def get_file(
    file_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Get file metadata by ID.

    Args:
        file_id: File ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        return dict(slot.provider.get_file(file_id))
    except KeyError:
        return {"error": f"File '{file_id}' not found."}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def get_file_content(
    file_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Get text content of a file.

    Args:
        file_id: File ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``content`` key (str) or ``error`` key on failure.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        content = slot.provider.get_file_content(file_id)
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def save_file(
    file_id: str,
    output_dir: str = ".",
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save a file's metadata + extracted text content as a Markdown file.

    Args:
        file_id: File ID.
        output_dir: Directory to save the file (default: current dir).
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``filepath`` and ``name``, or ``error``.
    """
    from iobox.processing.markdown import convert_file_to_markdown

    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        file_meta = slot.provider.get_file(file_id)
        md = convert_file_to_markdown(file_meta)
        out = create_output_directory(output_dir)
        name_slug = slugify_text(file_meta.get("title") or file_meta.get("name", "file"))
        filename = f"{name_slug}_{file_id}.md"
        filepath = os.path.join(out, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        return {"filepath": filepath, "name": file_meta.get("title", "")}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def download_file(
    file_id: str,
    output_path: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Download a file's binary content to disk.

    Args:
        file_id: File ID.
        output_path: Local file path to write the bytes to.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``filepath`` and ``bytes_written``, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        data = slot.provider.download_file(file_id)
        from pathlib import Path

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"filepath": str(path), "bytes_written": len(data)}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def upload_file(
    local_path: str,
    name: str | None = None,
    parent_id: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Upload a local file to the file provider.

    Args:
        local_path: Path to the file on disk.
        name: Optional remote filename (defaults to ``Path(local_path).name``).
        parent_id: Optional parent folder ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``name``, or ``error``.
    """
    from pathlib import Path

    if not Path(local_path).exists():
        return {"error": f"File not found: {local_path}"}
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        f = slot.provider.upload_file(local_path, parent_id=parent_id, name=name)
        return {"id": f.get("id", ""), "name": f.get("title") or f.get("name", "")}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def delete_file(
    file_id: str,
    permanent: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Delete a file (move to trash by default).

    Args:
        file_id: File ID.
        permanent: If True, permanently delete (skip trash).
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        slot.provider.delete_file(file_id, permanent=permanent)
        return {
            "file_id": file_id,
            "status": "deleted_permanently" if permanent else "trashed",
        }
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def create_folder(
    name: str,
    parent_id: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create a folder/directory in the file provider.

    Args:
        name: Folder name.
        parent_id: Optional parent folder ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``name``, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        f = slot.provider.create_folder(name, parent_id=parent_id)
        return {"id": f.get("id", ""), "name": f.get("title") or f.get("name", name)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Workspace: discovery + auth
# ---------------------------------------------------------------------------


@_tool
def list_workspaces() -> dict:
    """List all configured workspaces and the active one.

    Returns:
        Dict with ``workspaces`` (list of names) and ``active`` (name or None).
    """
    try:
        from iobox.space_config import get_active_space, list_spaces

        return {"workspaces": list_spaces(), "active": get_active_space()}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def get_active_workspace() -> dict:
    """Return the name of the currently active workspace, or None."""
    try:
        from iobox.space_config import get_active_space

        return {"active": get_active_space()}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def set_active_workspace(name: str) -> dict:
    """Switch the active workspace to ``name``.

    Args:
        name: Workspace name (must exist on disk).

    Returns:
        Dict with ``active`` set to the new name, or ``error``.
    """
    try:
        from iobox.space_config import list_spaces, set_active_space

        if name not in list_spaces():
            available = ", ".join(list_spaces()) or "(none)"
            return {"error": f"Workspace '{name}' not found. Available: {available}"}
        set_active_space(name)
        return {"active": name}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def list_provider_slots(workspace: str | None = None) -> dict:
    """Enumerate every provider slot in a workspace.

    Useful for discovering which ``provider`` names are available to pass
    to other tools when working with multiple accounts.

    Args:
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``email``, ``calendar``, ``file`` lists. Each entry has
        ``name``, ``tags``, and ``provider_class``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}

    def _describe(slot: Any) -> dict:
        return {
            "name": slot.name,
            "tags": list(slot.tags),
            "provider_class": type(slot.provider).__name__,
        }

    return {
        "workspace": ws.name,
        "email": [_describe(s) for s in ws.email_providers],
        "calendar": [_describe(s) for s in ws.calendar_providers],
        "file": [_describe(s) for s in ws.file_providers],
    }


@_tool
def workspace_auth_status(workspace: str | None = None) -> dict:
    """Report per-slot authentication status across the workspace.

    Calls ``get_profile`` on each slot to surface whether tokens are valid
    and which account they belong to.

    Args:
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict mapping slot name to ``{authenticated, account, error}``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}

    def _check(slot: Any) -> dict:
        try:
            profile = slot.provider.get_profile()
            return {
                "authenticated": True,
                "account": profile.get("emailAddress") or profile.get("email") or "",
                "error": None,
            }
        except Exception as exc:
            return {"authenticated": False, "account": None, "error": str(exc)}

    out: dict[str, Any] = {"workspace": ws.name, "slots": {}}
    for slot in ws.email_providers + ws.calendar_providers + ws.file_providers:
        out["slots"][slot.name] = _check(slot)
    return out


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
                    "Semantic search requires 'iobox[semantic]'. Run: pip install 'iobox[semantic]'"
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
