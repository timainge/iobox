"""
Email Sender Module.

This module handles composing and sending emails, including forwarding,
via the Gmail API.
"""

import base64
import html
import logging
import mimetypes
import os
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, getaddresses
from typing import Any

from googleapiclient.errors import HttpError

from iobox.providers.google._retrieval import download_attachment, get_email_content

logger = logging.getLogger(__name__)


def _encode_address_header(value: str) -> str:
    """Format a comma-separated address list with RFC 2047-encoded display names.

    ``"José Núñez <jose@example.com>, Smith, J <j@x.com>"``-style input is
    parsed into ``(name, addr)`` pairs and re-serialised so non-ASCII names are
    encoded-words and names with specials are quoted, rather than the raw
    non-ASCII header compat32 would otherwise emit as ``unknown-8bit``.
    """
    pairs = [(n, a) for n, a in getaddresses([value]) if a]
    if not pairs:
        return value
    out: list[str] = []
    for name, addr in pairs:
        try:
            out.append(formataddr((name, addr), charset="utf-8"))
        except UnicodeEncodeError:
            # Non-ASCII local part (SMTPUTF8) — nothing better to do than pass through.
            out.append(f"{name} <{addr}>" if name else addr)
    return ", ".join(out)


def _encode_text_header(value: str) -> str:
    """Return ``value`` as-is when ASCII, else RFC 2047 UTF-8 encoded-words."""
    try:
        value.encode("ascii")
        return value
    except UnicodeEncodeError:
        return Header(value, "utf-8").encode()


def _build_attachment_part(
    filename: str,
    mime_type: str,
    data: bytes,
    inline: bool = False,
    content_id: str | None = None,
) -> MIMEBase:
    """Build a base64-encoded MIME attachment part from in-memory bytes.

    The filename goes through ``add_header``'s parameter encoding, so
    non-ASCII names are RFC 2231-encoded and quotes are escaped. Inline parts
    keep their ``Content-ID`` so ``cid:`` references in HTML still resolve.
    """
    if not mime_type or "/" not in mime_type:
        mime_type = "application/octet-stream"
    main_type, sub_type = mime_type.split("/", 1)
    part = MIMEBase(main_type, sub_type)
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "inline" if inline else "attachment", filename=filename)
    if content_id:
        part.add_header("Content-ID", f"<{content_id.strip().strip('<>')}>")
    return part


def compose_message(
    to: str,
    subject: str,
    body: str,
    from_addr: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    content_type: str = "plain",
    attachments: list[str] | None = None,
    attachment_blobs: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """
    Compose an RFC 2822 email message encoded for the Gmail API.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body text
        from_addr: Sender email address (optional, Gmail uses authenticated user by default)
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        content_type: 'plain' for plain text (default) or 'html' for HTML
        attachments: Optional list of file paths to attach
        attachment_blobs: Optional list of in-memory attachments, each a dict with
            ``filename``, ``mime_type``, and ``data`` (bytes), plus optional
            ``inline`` (bool) and ``content_id``. Used by forwarding to re-attach
            the original message's files without writing them to disk. For an
            HTML body, inline blobs with a ``content_id`` are placed in a
            ``multipart/related`` with the HTML so ``cid:`` images resolve.

    Returns:
        dict: Message body with 'raw' base64url-encoded RFC 2822 payload
    """

    def _blob_part(blob: dict[str, Any]) -> MIMEBase:
        return _build_attachment_part(
            blob.get("filename", "attachment"),
            blob.get("mime_type", "application/octet-stream"),
            blob.get("data", b""),
            inline=bool(blob.get("inline")),
            content_id=blob.get("content_id"),
        )

    blobs = attachment_blobs or []
    related = [
        b for b in blobs if content_type == "html" and b.get("inline") and b.get("content_id")
    ]
    regular = [b for b in blobs if b not in related]

    # The HTML (or plain) body part, wrapped in multipart/related when it
    # references inline images.
    body_part: MIMEMultipart | MIMEText = MIMEText(body, content_type)
    if related:
        rel = MIMEMultipart("related")
        rel.attach(body_part)
        for blob in related:
            rel.attach(_blob_part(blob))
        body_part = rel

    message: MIMEMultipart | MIMEText

    if attachments or regular:
        outer = MIMEMultipart("mixed")
        if content_type == "html":
            # nested multipart: mixed outer, alternative inner
            inner = MIMEMultipart("alternative")
            inner.attach(MIMEText(body, "plain"))
            inner.attach(body_part)
            outer.attach(inner)
        else:
            outer.attach(body_part)

        for file_path in attachments or []:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"

            with open(file_path, "rb") as f:
                file_data = f.read()

            outer.attach(_build_attachment_part(os.path.basename(file_path), mime_type, file_data))

        for blob in regular:
            outer.attach(_blob_part(blob))

        message = outer
    else:
        message = body_part

    message["to"] = _encode_address_header(to)
    message["subject"] = _encode_text_header(subject)

    if from_addr:
        message["from"] = _encode_address_header(from_addr)
    if cc:
        message["cc"] = _encode_address_header(cc)
    if bcc:
        message["bcc"] = _encode_address_header(bcc)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


def compose_forward_message(
    original_email: dict[str, Any],
    to: str,
    from_addr: str | None = None,
    additional_text: str | None = None,
    attachment_blobs: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """
    Compose a forwarded email message.

    Wraps the original email content with standard forwarding headers, preserving
    the original body's content type (HTML or plain) and re-attaching any files
    passed via ``attachment_blobs``.

    Args:
        original_email: Email data dict as returned by get_email_content
        to: Recipient email address to forward to
        from_addr: Sender address (optional)
        additional_text: Optional text to prepend above the forwarded content
        attachment_blobs: In-memory attachments to carry over from the original
            message — each a dict with ``filename``, ``mime_type``, ``data``.

    Returns:
        dict: Message body with 'raw' base64url-encoded RFC 2822 payload
    """
    orig_from = original_email.get("from", "Unknown")
    orig_date = original_email.get("date", "Unknown")
    orig_subject = original_email.get("subject", "No Subject")
    orig_body = original_email.get("body", "") or original_email.get("content", "")
    is_html = original_email.get("content_type") == "text/html"
    comment_is_html = bool(additional_text and additional_text.lstrip().startswith("<"))

    if is_html or comment_is_html:
        # Header values and plain text are untrusted text going into HTML:
        # escape them so "Name <addr>" shows up and markup can't be injected.
        header_lines = [
            "---------- Forwarded message ----------",
            f"From: {html.escape(orig_from)}",
            f"Date: {html.escape(orig_date)}",
            f"Subject: {html.escape(orig_subject)}",
        ]
        if additional_text:
            prefix = (
                additional_text if comment_is_html else f"<p>{html.escape(additional_text)}</p>"
            )
        else:
            prefix = ""
        header_block = "<br>".join(header_lines)
        # An HTML comment forces an HTML forward even for a plain-text original.
        forwarded_body = orig_body if is_html else f"<pre>{html.escape(orig_body)}</pre>"
        body = f"{prefix}<div>{header_block}</div><hr>{forwarded_body}"
        content_type = "html"
    else:
        parts = []
        if additional_text:
            parts.append(additional_text)
            parts.append("")

        parts.append("---------- Forwarded message ----------")
        parts.append(f"From: {orig_from}")
        parts.append(f"Date: {orig_date}")
        parts.append(f"Subject: {orig_subject}")
        parts.append("")
        parts.append(orig_body)

        body = "\n".join(parts)
        content_type = "plain"

    subject = f"Fwd: {orig_subject}"

    return compose_message(
        to=to,
        subject=subject,
        body=body,
        from_addr=from_addr,
        content_type=content_type,
        attachment_blobs=attachment_blobs,
    )


def send_message(service: Any, message: dict[str, str]) -> dict[str, Any]:
    """
    Send an email message via the Gmail API.

    Args:
        service: Authenticated Gmail API service
        message: Message body dict with 'raw' key

    Returns:
        dict: Gmail API send response containing the message id and other metadata
    """
    try:
        result: dict[str, Any] = (
            service.users().messages().send(userId="me", body=message).execute()
        )
        logger.info(f"Message sent successfully. Message Id: {result.get('id', '')}")
        return result
    except HttpError as error:
        logger.error(f"Error sending message: {error}")
        raise


def forward_email(
    service: Any,
    message_id: str,
    to: str,
    from_addr: str | None = None,
    additional_text: str | None = None,
) -> dict[str, Any]:
    """
    Convenience function: retrieve an email and forward it.

    Args:
        service: Authenticated Gmail API service
        message_id: ID of the email to forward
        to: Recipient email address
        from_addr: Sender address (optional)
        additional_text: Optional text to prepend

    Returns:
        dict: Gmail API send response
    """
    email_data = get_email_content(
        service, message_id=message_id, preferred_content_type="text/html"
    )

    # Download each attachment so it can be re-attached to the forwarded message.
    attachment_blobs: list[dict[str, Any]] = []
    for att in email_data.get("attachments", []):
        att_id = att.get("id")
        if not att_id:
            continue
        try:
            data = download_attachment(service, message_id, att_id)
        except Exception as exc:  # pragma: no cover - logged, non-fatal
            logger.warning(f"Skipping attachment {att.get('filename', att_id)}: {exc}")
            continue
        attachment_blobs.append(
            {
                "filename": att.get("filename", "attachment"),
                "mime_type": att.get("mime_type", "application/octet-stream"),
                "data": data,
                "inline": bool(att.get("inline")),
                "content_id": att.get("content_id"),
            }
        )

    message = compose_forward_message(
        original_email=email_data,
        to=to,
        from_addr=from_addr,
        additional_text=additional_text,
        attachment_blobs=attachment_blobs,
    )
    return send_message(service, message)


def create_draft(service: Any, message: dict[str, str]) -> dict[str, Any]:
    """
    Create a Gmail draft.

    Args:
        service: Authenticated Gmail API service
        message: Message body dict with 'raw' key

    Returns:
        dict: The draft resource dict from the Gmail API
    """
    draft: dict[str, Any] = (
        service.users().drafts().create(userId="me", body={"message": message}).execute()
    )
    return draft


def list_drafts(service: Any, max_results: int = 10) -> list[dict[str, Any]]:
    """
    List Gmail drafts.

    Args:
        service: Authenticated Gmail API service
        max_results: Maximum number of drafts to return

    Returns:
        list: List of dicts with id, subject, and snippet for each draft
    """
    result = service.users().drafts().list(userId="me", maxResults=max_results).execute()
    drafts = result.get("drafts", [])
    draft_list = []
    for d in drafts:
        draft_data = (
            service.users().drafts().get(userId="me", id=d["id"], format="metadata").execute()
        )
        msg = draft_data.get("message", {})
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        draft_list.append(
            {
                "id": d["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": msg.get("snippet", ""),
            }
        )
    return draft_list


def get_draft(service: Any, draft_id: str) -> dict[str, Any]:
    """
    Get a specific draft by ID.

    Args:
        service: Authenticated Gmail API service
        draft_id: The draft ID to retrieve

    Returns:
        dict: The full draft resource dict from the Gmail API
    """
    result: dict[str, Any] = (
        service.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    )
    return result


def send_draft(service: Any, draft_id: str) -> dict[str, Any]:
    """
    Send an existing draft.

    Args:
        service: Authenticated Gmail API service
        draft_id: The draft ID to send

    Returns:
        dict: Gmail API send response
    """
    result: dict[str, Any] = (
        service.users().drafts().send(userId="me", body={"id": draft_id}).execute()
    )
    return result


def delete_draft(service: Any, draft_id: str) -> dict[str, Any]:
    """
    Permanently delete a draft.

    Args:
        service: Authenticated Gmail API service
        draft_id: The draft ID to delete

    Returns:
        dict: Status dict with 'status' and 'draft_id' keys
    """
    service.users().drafts().delete(userId="me", id=draft_id).execute()
    return {"status": "deleted", "draft_id": draft_id}
