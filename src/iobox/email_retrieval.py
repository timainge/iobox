"""
Email Retrieval Module.

This module handles retrieving full email content and downloading attachments
from the Gmail API.
"""

import base64
import logging
from typing import Any

from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Module-level cache for label ID → display name mapping.
# Populated lazily by get_label_map() and shared across calls within one session.
_label_cache: dict[str, str] = {}


def get_label_map(service) -> dict[str, str]:
    """
    Fetch the Gmail label ID-to-name mapping for the authenticated user.

    Results are cached at module level so the API is called at most once per
    process invocation. If the API call fails, an empty dict is returned so
    callers can gracefully fall back to raw label IDs.

    Args:
        service: Authenticated Gmail API service

    Returns:
        dict: Mapping of label ID → display name (e.g. {"Label_12345": "Newsletter"})
    """
    global _label_cache
    if _label_cache:
        return _label_cache
    try:
        response = service.users().labels().list(userId="me").execute()
        labels = response.get("labels", [])
        _label_cache = {label["id"]: label["name"] for label in labels}
        logging.info(f"Fetched label map with {len(_label_cache)} entries")
        return _label_cache
    except Exception as e:
        logging.warning(f"Failed to fetch label map, returning empty dict: {e}")
        return {}


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

    email_data = {
        "message_id": email_id,
        "subject": next(
            (h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject"
        ),
        "from": next(
            (h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender"
        ),
        "date": next((h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date"),
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
    service,
    message_id: str = None,
    msg_id: str = None,
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
        logging.error("No message ID provided")
        raise ValueError("No message ID provided")

    try:
        message = service.users().messages().get(userId="me", id=email_id, format="full").execute()

        email_data = _process_message_response(message, preferred_content_type, label_map)
        logging.info(f"Successfully retrieved email content for {email_id}")
        return email_data

    except HttpError as error:
        logging.error(f"Error retrieving email content for {email_id}: {error}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise


def batch_get_emails(
    service,
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
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def callback(request_id, response, exception):
        if exception:
            errors[request_id] = str(exception)
        else:
            results[request_id] = response

    for i in range(0, len(message_ids), 50):
        chunk = message_ids[i : i + 50]
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(userId="me", id=msg_id, format=format),
                request_id=msg_id,
            )
        batch.execute()

    email_list = []
    for msg_id in message_ids:
        if msg_id in errors:
            email_list.append({"message_id": msg_id, "error": errors[msg_id]})
        elif msg_id in results:
            message = results[msg_id]
            email_data = _process_message_response(message, preferred_content_type, label_map)
            email_list.append(email_data)
        else:
            email_list.append({"message_id": msg_id, "error": "Not found in batch response"})

    logging.info(f"Batch fetched {len(email_list)} emails ({len(errors)} errors)")
    return email_list


def get_thread_content(
    service, thread_id: str, preferred_content_type: str = "text/plain"
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

        logging.info(f"Retrieved {len(email_list)} messages for thread {thread_id}")
        return email_list

    except HttpError as error:
        logging.error(f"Error retrieving thread {thread_id}: {error}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error retrieving thread: {e}")
        raise


def modify_message_labels(
    service,
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
    return service.users().messages().modify(userId="me", id=message_id, body=body).execute()


def resolve_label_name(service, label_name: str) -> str:
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
    label_map = get_label_map(service)
    name_to_id = {v: k for k, v in label_map.items()}
    if label_name in name_to_id:
        return name_to_id[label_name]
    raise ValueError(f"Label '{label_name}' not found")


def batch_modify_labels(
    service,
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


def trash_message(service, message_id: str) -> dict[str, Any]:
    """
    Move a message to trash.

    Args:
        service: Authenticated Gmail API service
        message_id: Message ID to trash

    Returns:
        dict: Updated message resource
    """
    return service.users().messages().trash(userId="me", id=message_id).execute()


def untrash_message(service, message_id: str) -> dict[str, Any]:
    """
    Remove a message from trash.

    Args:
        service: Authenticated Gmail API service
        message_id: Message ID to untrash

    Returns:
        dict: Updated message resource
    """
    return service.users().messages().untrash(userId="me", id=message_id).execute()


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
            attachments.append(
                {
                    "id": part.get("body", {}).get("attachmentId", ""),
                    "filename": part["filename"],
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "size": part.get("body", {}).get("size", 0),
                }
            )

        if "parts" in part:
            attachments.extend(_find_attachments(part["parts"]))

    return attachments


def download_attachment(service, message_id: str, attachment_id: str) -> bytes:
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
            logging.info(f"Successfully downloaded attachment for email {message_id}")
            return file_data
        else:
            logging.warning(f"No data found in attachment {attachment_id} for email {message_id}")
            return b""
    except HttpError as error:
        logging.error(
            f"Error downloading attachment {attachment_id} for email {message_id}: {error}"
        )
        raise
    except Exception as e:
        logging.error(f"Unexpected error downloading attachment: {e}")
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
        content = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        return content, payload.get("mimeType", "text/plain")

    if "parts" not in payload:
        return "", "text/plain"

    return _extract_content_from_parts(payload["parts"], preferred_type)


def _extract_content_from_parts(
    parts: list[dict[str, Any]], preferred_type: str = "text/plain"
) -> tuple[str, str]:
    """
    Extract content from multipart message parts.

    Args:
        parts: List of message parts
        preferred_type: Preferred content type ('text/plain' or 'text/html')

    Returns:
        tuple: (content, content_type)
    """
    plain_content = ""
    html_content = ""

    for part in parts:
        if part["mimeType"] == "text/plain" and "data" in part.get("body", {}):
            plain_content = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

        if part["mimeType"] == "text/html" and "data" in part.get("body", {}):
            html_content = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

        if "parts" in part and not (plain_content or html_content):
            nested_content, nested_type = _extract_content_from_parts(part["parts"], preferred_type)
            if nested_type == "text/plain" and not plain_content:
                plain_content = nested_content
            elif nested_type == "text/html" and not html_content:
                html_content = nested_content

    if preferred_type == "text/html" and html_content:
        return html_content, "text/html"
    elif plain_content:
        return plain_content, "text/plain"
    elif html_content:
        return html_content, "text/html"

    return "No content found", "text/plain"
