"""
Email Retrieval Module.

This module handles retrieving full email content and downloading attachments
from the Gmail API.
"""

import base64
import logging
import re
import threading
import time
import weakref
from typing import Any

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Label ID → display name caches, one per Gmail service object (i.e. per
# authenticated account). A module-global dict would leak one account's labels
# into another's lookups when a workspace holds several Gmail slots.
_label_caches: weakref.WeakKeyDictionary[Any, dict[str, str]] = weakref.WeakKeyDictionary()
_label_caches_lock = threading.Lock()


def _label_cache_for(service: Any) -> dict[str, str]:
    """Return (creating if needed) the label cache bound to ``service``."""
    with _label_caches_lock:
        cache = _label_caches.get(service)
        if cache is None:
            cache = {}
            _label_caches[service] = cache
        return cache


def clear_label_cache(service: Any | None = None) -> None:
    """Drop the cached label map for ``service`` (or for every service)."""
    with _label_caches_lock:
        if service is None:
            _label_caches.clear()
        else:
            _label_caches.pop(service, None)


# Gmail rejects bursts of concurrent requests per user with 429
# "Too many concurrent requests for user", even inside a single batch.
# Keep batches small and retry the rejected sub-requests with backoff.
_BATCH_CHUNK_SIZE = 20
_BATCH_MAX_RETRIES = 4
_BATCH_RETRY_BASE_DELAY = 0.5
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _is_retryable(exception: Exception) -> bool:
    status = getattr(getattr(exception, "resp", None), "status", None)
    try:
        return int(status) in _RETRYABLE_STATUSES  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def batch_get_messages(
    service: Any, message_ids: list[str], **get_kwargs: Any
) -> tuple[dict[str, Any], dict[str, str]]:
    """Fetch ``users.messages.get`` for many IDs via batched requests.

    Sub-requests that fail with a rate-limit or transient server error are
    retried with exponential backoff.

    Args:
        service: Authenticated Gmail API service
        message_ids: Message IDs to fetch
        **get_kwargs: Extra arguments for ``messages().get`` (e.g. ``format``)

    Returns:
        ``(results, errors)`` — raw message resources and error strings, keyed
        by message ID.
    """
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    retryable: set[str] = set()

    def callback(request_id: str, response: Any, exception: Exception | None) -> None:
        if exception:
            errors[request_id] = str(exception)
            if _is_retryable(exception):
                retryable.add(request_id)
        else:
            results[request_id] = response

    pending = list(dict.fromkeys(message_ids))
    for attempt in range(_BATCH_MAX_RETRIES + 1):
        if attempt:
            time.sleep(_BATCH_RETRY_BASE_DELAY * 2 ** (attempt - 1))
        for msg_id in pending:
            errors.pop(msg_id, None)
        retryable.clear()

        for i in range(0, len(pending), _BATCH_CHUNK_SIZE):
            chunk = pending[i : i + _BATCH_CHUNK_SIZE]
            batch = service.new_batch_http_request(callback=callback)
            for msg_id in chunk:
                batch.add(
                    service.users().messages().get(userId="me", id=msg_id, **get_kwargs),
                    request_id=msg_id,
                )
            batch.execute()

        pending = [m for m in pending if m in retryable]
        if not pending:
            break
        logger.info(f"Retrying {len(pending)} rate-limited message fetches")

    return results, errors


def get_label_map(service: Any, refresh: bool = False) -> dict[str, str]:
    """
    Fetch the Gmail label ID-to-name mapping for the authenticated user.

    Results are cached per ``service`` (one per authenticated account), so the
    API is called once per service unless ``refresh=True``. If the API call
    fails, an empty dict is returned so callers can gracefully fall back to raw
    label IDs.

    Args:
        service: Authenticated Gmail API service
        refresh: Re-fetch from the API even when a cached map exists

    Returns:
        dict: Mapping of label ID → display name (e.g. {"Label_12345": "Newsletter"})
    """
    cache = _label_cache_for(service)
    if cache and not refresh:
        return dict(cache)
    try:
        response = service.users().labels().list(userId="me").execute()
        labels = response.get("labels", [])
        fresh = {label["id"]: label["name"] for label in labels}
        cache.clear()
        cache.update(fresh)
        logger.info(f"Fetched label map with {len(cache)} entries")
        return dict(cache)
    except Exception as e:
        logger.warning(f"Failed to fetch label map, returning empty dict: {e}")
        return dict(cache)


def _process_message_response(
    message: dict[str, Any],
    preferred_content_type: str = "text/plain",
    label_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Process a raw Gmail API message response dict into an email data dict.

    Shared by get_email_content() and batch_get_emails() so that the same
    extraction logic is used regardless of how the raw message was retrieved.

    Args:
        message: Raw Gmail API message resource dict
        preferred_content_type: Preferred content type ('text/plain' or 'text/html')
        label_map: Optional mapping of label ID to display name

    Returns:
        dict: Processed email data
    """
    email_id = message["id"]
    payload = message["payload"]
    headers = payload["headers"]

    raw_labels = message.get("labelIds", [])
    resolved_labels = (
        [label_map.get(lid, lid) for lid in raw_labels] if label_map is not None else raw_labels
    )

    def _hdr(name: str, default: str = "") -> str:
        return next((h["value"] for h in headers if h["name"].lower() == name), default)

    email_data = {
        "message_id": email_id,
        "subject": _hdr("subject", "No Subject"),
        "from": _hdr("from", "Unknown Sender"),
        "to": _hdr("to"),
        "cc": _hdr("cc"),
        "bcc": _hdr("bcc"),
        "reply_to": _hdr("reply-to"),
        "date": _hdr("date", "Unknown Date"),
        "labels": resolved_labels,
        "snippet": message.get("snippet", ""),
        "thread_id": message.get("threadId", ""),
    }

    content, content_type = _extract_content_from_payload(payload, preferred_content_type)
    email_data["body"] = content
    email_data["content"] = content
    email_data["content_type"] = content_type

    if content_type == "text/html":
        email_data["html_content"] = content
        email_data["plain_content"] = ""
    else:
        email_data["plain_content"] = content
        email_data["html_content"] = ""

    if "parts" in payload:
        email_data["attachments"] = _find_attachments(payload["parts"])
    else:
        email_data["attachments"] = []

    return email_data


def get_email_content(
    service: Any,
    message_id: str | None = None,
    msg_id: str | None = None,
    preferred_content_type: str = "text/plain",
    label_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Retrieve the full content of an email by its ID.

    Args:
        service: Authenticated Gmail API service
        message_id: Email message ID (new parameter name)
        msg_id: Email message ID (legacy parameter name)
        preferred_content_type: Preferred content type ('text/plain' or 'text/html')
        label_map: Optional mapping of label ID to display name. When provided,
            raw label IDs in the returned data are resolved to human-readable
            names. System labels (INBOX, UNREAD, etc.) pass through unchanged
            when the map contains their IDs. If None, raw IDs are returned
            (backward compatible).

    Returns:
        dict: Email data including subject, sender, date, content, and metadata
    """
    email_id = message_id if message_id is not None else msg_id

    if email_id is None:
        logger.error("No message ID provided")
        raise ValueError("No message ID provided")

    try:
        message = service.users().messages().get(userId="me", id=email_id, format="full").execute()

        email_data = _process_message_response(message, preferred_content_type, label_map)
        logger.info(f"Successfully retrieved email content for {email_id}")
        return email_data

    except HttpError as error:
        logger.error(f"Error retrieving email content for {email_id}: {error}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


def batch_get_emails(
    service: Any,
    message_ids: list[str],
    format: str = "full",
    preferred_content_type: str = "text/plain",
    label_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch multiple emails in batched HTTP requests (chunks of 50).

    Args:
        service: Gmail API service
        message_ids: List of message IDs to fetch
        format: API format parameter ('full', 'metadata', etc.)
        preferred_content_type: Content type preference for body extraction
        label_map: Optional mapping of label ID to display name

    Returns:
        List of email data dicts in same order as input IDs.
        Failed fetches are returned as dicts with 'error' key.
    """
    results, errors = batch_get_messages(service, message_ids, format=format)

    email_list = []
    for msg_id in message_ids:
        if msg_id in errors:
            email_list.append({"message_id": msg_id, "error": errors[msg_id]})
        elif msg_id in results:
            message = results[msg_id]
            try:
                email_data = _process_message_response(message, preferred_content_type, label_map)
            except Exception as e:  # one malformed message must not sink the batch
                logger.warning(f"Failed to process message {msg_id}: {e}")
                email_data = {"message_id": msg_id, "error": f"Failed to process message: {e}"}
            email_list.append(email_data)
        else:
            email_list.append({"message_id": msg_id, "error": "Not found in batch response"})

    logger.info(f"Batch fetched {len(email_list)} emails ({len(errors)} errors)")
    return email_list


def get_thread_content(
    service: Any, thread_id: str, preferred_content_type: str = "text/plain"
) -> list[dict[str, Any]]:
    """
    Retrieve all messages in a Gmail thread.

    Args:
        service: Authenticated Gmail API service
        thread_id: Thread ID to retrieve
        preferred_content_type: Preferred content type ('text/plain' or 'text/html')

    Returns:
        list: List of email data dicts ordered chronologically by internalDate
    """
    try:
        result = service.users().threads().get(userId="me", id=thread_id, format="full").execute()

        messages = result.get("messages", [])
        email_list = []

        for message in messages:
            payload = message["payload"]
            headers = payload["headers"]

            email_data = {
                "message_id": message["id"],
                "thread_id": message.get("threadId", thread_id),
                "subject": next(
                    (h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject"
                ),
                "from": next(
                    (h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender"
                ),
                "to": next((h["value"] for h in headers if h["name"].lower() == "to"), ""),
                "cc": next((h["value"] for h in headers if h["name"].lower() == "cc"), ""),
                "date": next(
                    (h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date"
                ),
                "labels": message.get("labelIds", []),
                "internal_date": int(message.get("internalDate", 0)),
            }

            content, content_type = _extract_content_from_payload(payload, preferred_content_type)
            email_data["body"] = content
            email_data["content_type"] = content_type

            email_list.append(email_data)

        # Sort chronologically
        email_list.sort(key=lambda m: m["internal_date"])

        logger.info(f"Retrieved {len(email_list)} messages for thread {thread_id}")
        return email_list

    except HttpError as error:
        logger.error(f"Error retrieving thread {thread_id}: {error}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving thread: {e}")
        raise


def modify_message_labels(
    service: Any,
    message_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict[str, Any]:
    """
    Modify labels on a Gmail message.

    Args:
        service: Authenticated Gmail API service
        message_id: Message ID to modify
        add_labels: List of label IDs to add
        remove_labels: List of label IDs to remove

    Returns:
        dict: Modified message resource
    """
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    result: dict[str, Any] = (
        service.users().messages().modify(userId="me", id=message_id, body=body).execute()
    )
    return result


def resolve_label_name(service: Any, label_name: str) -> str:
    """
    Resolve a human-readable label name to a Gmail label ID.

    System labels (INBOX, UNREAD, STARRED, SENT, DRAFT, SPAM, TRASH, IMPORTANT)
    and CATEGORY_* labels pass through as uppercase. Custom labels are looked up
    via the label map.

    Args:
        service: Authenticated Gmail API service
        label_name: Human-readable label name or system label

    Returns:
        str: Gmail label ID

    Raises:
        ValueError: If the label name cannot be resolved
    """
    system_labels = {"INBOX", "UNREAD", "STARRED", "SENT", "DRAFT", "SPAM", "TRASH", "IMPORTANT"}
    if label_name.upper() in system_labels:
        return label_name.upper()
    if label_name.upper().startswith("CATEGORY_"):
        return label_name.upper()
    for refresh in (False, True):
        # On a miss, refetch once — the label may have been created since the
        # map was cached (in the Gmail UI or by another process).
        name_to_id = {v: k for k, v in get_label_map(service, refresh=refresh).items()}
        if label_name in name_to_id:
            return name_to_id[label_name]
    raise ValueError(f"Label '{label_name}' not found")


def create_label(service: Any, name: str) -> dict[str, str]:
    """Create a Gmail label, returning its ``{id, name}``.

    Nested labels use ``/``-delimited names (e.g. ``"LifeAdmin/property/7-leslie-st"``)
    — Gmail renders the hierarchy automatically. If the label already exists,
    the existing label is returned rather than raising.

    Args:
        service: Authenticated Gmail API service
        name: Label name (``/``-delimited for nesting)

    Returns:
        dict: ``{"id": ..., "name": ...}`` for the created (or existing) label
    """
    body = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    try:
        created = service.users().labels().create(userId="me", body=body).execute()
    except HttpError as error:
        # 409 → label already exists; resolve and return it.
        if getattr(error, "resp", None) is not None and error.resp.status == 409:
            existing = get_label_map(service, refresh=True)
            name_to_id = {v: k for k, v in existing.items()}
            if name in name_to_id:
                return {"id": name_to_id[name], "name": name}
        logger.error(f"Error creating label {name!r}: {error}")
        raise
    # Update this service's cache so subsequent resolves see the new label.
    _label_cache_for(service)[created["id"]] = created["name"]
    return {"id": created["id"], "name": created["name"]}


def batch_modify_labels(
    service: Any,
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict[str, Any]:
    """
    Apply label changes to multiple messages in one API call (up to 1000 per chunk).

    Args:
        service: Authenticated Gmail API service
        message_ids: List of message IDs to modify
        add_labels: List of label IDs to add
        remove_labels: List of label IDs to remove

    Returns:
        dict: Result with modified_count
    """
    body: dict[str, Any] = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels

    for i in range(0, len(message_ids), 1000):
        chunk_body = dict(body)
        chunk_body["ids"] = message_ids[i : i + 1000]
        service.users().messages().batchModify(userId="me", body=chunk_body).execute()

    return {"modified_count": len(message_ids)}


def trash_message(service: Any, message_id: str) -> dict[str, Any]:
    """
    Move a message to trash.

    Args:
        service: Authenticated Gmail API service
        message_id: Message ID to trash

    Returns:
        dict: Updated message resource
    """
    result: dict[str, Any] = service.users().messages().trash(userId="me", id=message_id).execute()
    return result


def untrash_message(service: Any, message_id: str) -> dict[str, Any]:
    """
    Remove a message from trash.

    Args:
        service: Authenticated Gmail API service
        message_id: Message ID to untrash

    Returns:
        dict: Updated message resource
    """
    result: dict[str, Any] = (
        service.users().messages().untrash(userId="me", id=message_id).execute()
    )
    return result


def _find_attachments(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Find attachments in message parts.

    Args:
        parts: List of message parts

    Returns:
        list: List of attachment metadata
    """
    attachments = []

    for part in parts:
        if "filename" in part and part["filename"]:
            headers = {h["name"].lower(): h["value"] for h in part.get("headers", [])}
            disposition = headers.get("content-disposition", "").lower()
            content_id = headers.get("content-id", "")
            content_id = content_id.strip().lstrip("<").rstrip(">") or None
            # Inline when explicitly dispositioned inline, or (lacking a
            # disposition) when a Content-ID marks it as a cid-referenced part.
            is_inline = disposition.startswith("inline") or (
                not disposition and content_id is not None
            )
            attachments.append(
                {
                    "id": part.get("body", {}).get("attachmentId", ""),
                    "filename": part["filename"],
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "size": part.get("body", {}).get("size", 0),
                    "inline": is_inline,
                    "content_id": content_id,
                }
            )

        if "parts" in part:
            attachments.extend(_find_attachments(part["parts"]))

    return attachments


def download_attachment(service: Any, message_id: str, attachment_id: str) -> bytes:
    """
    Download an email attachment by its ID.

    Args:
        service: Authenticated Gmail API service
        message_id: Email message ID
        attachment_id: Attachment ID

    Returns:
        bytes: Attachment content as bytes
    """
    try:
        attachment = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )

        if "data" in attachment:
            file_data = base64.urlsafe_b64decode(attachment["data"])
            logger.info(f"Successfully downloaded attachment for email {message_id}")
            return file_data
        else:
            logger.warning(f"No data found in attachment {attachment_id} for email {message_id}")
            return b""
    except HttpError as error:
        logger.error(
            f"Error downloading attachment {attachment_id} for email {message_id}: {error}"
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading attachment: {e}")
        raise


def _extract_content_from_payload(
    payload: dict[str, Any], preferred_type: str = "text/plain"
) -> tuple[str, str]:
    """
    Extract content from message payload.

    Args:
        payload: Message payload
        preferred_type: Preferred content type ('text/plain' or 'text/html')

    Returns:
        tuple: (content, content_type)
    """
    if "body" in payload and "data" in payload["body"] and "parts" not in payload:
        content = _decode_part_body(payload)
        return content, payload.get("mimeType", "text/plain")

    if "parts" not in payload:
        return "", "text/plain"

    return _extract_content_from_parts(payload["parts"], preferred_type)


_CHARSET_RE = re.compile(r"""charset\s*=\s*["']?([^"';\s]+)""", re.IGNORECASE)


def _part_headers(part: dict[str, Any]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in part.get("headers", []) or []}


def _part_charset(part: dict[str, Any]) -> str:
    """Return the charset declared in the part's Content-Type header (default utf-8)."""
    match = _CHARSET_RE.search(_part_headers(part).get("content-type", ""))
    return match.group(1) if match else "utf-8"


def _decode_part_body(part: dict[str, Any]) -> str:
    """Base64url-decode a part's body and decode it with its declared charset.

    Undecodable bytes are replaced rather than raising, and an unknown charset
    falls back to UTF-8, so one oddly-encoded message can't abort a batch.
    """
    raw = base64.urlsafe_b64decode(part["body"]["data"])
    charset = _part_charset(part)
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _is_attachment_part(part: dict[str, Any]) -> bool:
    """True for parts that are attachments rather than message body text."""
    disposition = _part_headers(part).get("content-disposition", "").strip().lower()
    return disposition.startswith("attachment") or bool(part.get("filename"))


def _collect_text_parts(parts: list[dict[str, Any]], plain: list[str], html: list[str]) -> None:
    for part in parts:
        if _is_attachment_part(part):
            continue
        if "parts" in part:
            _collect_text_parts(part["parts"], plain, html)
            continue
        if "data" not in part.get("body", {}):
            continue
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            plain.append(_decode_part_body(part))
        elif mime == "text/html":
            html.append(_decode_part_body(part))


def _extract_content_from_parts(
    parts: list[dict[str, Any]], preferred_type: str = "text/plain"
) -> tuple[str, str]:
    """
    Extract content from multipart message parts.

    Every non-attachment ``text/plain`` / ``text/html`` leaf is collected (in
    order) and same-type parts are joined, so bodies split around inline
    images aren't truncated to their last fragment. Parts with an
    ``attachment`` disposition (or a filename) are skipped — an attached
    ``.txt`` or ``.html`` file is not the message body.

    Args:
        parts: List of message parts
        preferred_type: Preferred content type ('text/plain' or 'text/html')

    Returns:
        tuple: (content, content_type)
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_text_parts(parts, plain_parts, html_parts)
    plain_content = "\n".join(plain_parts)
    html_content = "\n".join(html_parts)

    if preferred_type == "text/html" and html_content:
        return html_content, "text/html"
    elif plain_content:
        return plain_content, "text/plain"
    elif html_content:
        return html_content, "text/html"

    return "No content found", "text/plain"
