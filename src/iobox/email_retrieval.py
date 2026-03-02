"""
Email Retrieval Module.

This module handles retrieving full email content and downloading attachments
from the Gmail API.
"""

import base64
import logging
from typing import Dict, Any, List, Optional, Tuple
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Module-level cache for label ID → display name mapping.
# Populated lazily by get_label_map() and shared across calls within one session.
_label_cache: Dict[str, str] = {}


def get_label_map(service) -> Dict[str, str]:
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
        response = service.users().labels().list(userId='me').execute()
        labels = response.get('labels', [])
        _label_cache = {label['id']: label['name'] for label in labels}
        logging.info(f"Fetched label map with {len(_label_cache)} entries")
        return _label_cache
    except Exception as e:
        logging.warning(f"Failed to fetch label map, returning empty dict: {e}")
        return {}


def get_email_content(service, message_id: str = None, msg_id: str = None,
                      preferred_content_type: str = 'text/plain',
                      label_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
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
        message = service.users().messages().get(
            userId='me',
            id=email_id,
            format='full'
        ).execute()

        payload = message['payload']
        headers = payload['headers']

        raw_labels = message.get('labelIds', [])
        resolved_labels = (
            [label_map.get(lid, lid) for lid in raw_labels]
            if label_map is not None
            else raw_labels
        )

        email_data = {
            'message_id': email_id,
            'subject': next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject'),
            'from': next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender'),
            'date': next((header['value'] for header in headers if header['name'].lower() == 'date'), 'Unknown Date'),
            'labels': resolved_labels,
            'snippet': message.get('snippet', ''),
            'thread_id': message.get('threadId', '')
        }

        content, content_type = _extract_content_from_payload(payload, preferred_content_type)
        email_data['body'] = content
        email_data['content'] = content
        email_data['content_type'] = content_type

        if content_type == 'text/html':
            email_data['html_content'] = content
            email_data['plain_content'] = ''
        else:
            email_data['plain_content'] = content
            email_data['html_content'] = ''

        if 'parts' in payload:
            email_data['attachments'] = _find_attachments(payload['parts'])
        else:
            email_data['attachments'] = []

        logging.info(f"Successfully retrieved email content for {email_id}")
        return email_data

    except HttpError as error:
        logging.error(f"Error retrieving email content for {email_id}: {error}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise


def _find_attachments(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find attachments in message parts.

    Args:
        parts: List of message parts

    Returns:
        list: List of attachment metadata
    """
    attachments = []

    for part in parts:
        if 'filename' in part and part['filename']:
            attachments.append({
                'id': part.get('body', {}).get('attachmentId', ''),
                'filename': part['filename'],
                'mime_type': part.get('mimeType', 'application/octet-stream'),
                'size': part.get('body', {}).get('size', 0)
            })

        if 'parts' in part:
            attachments.extend(_find_attachments(part['parts']))

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
        attachment = service.users().messages().attachments().get(
            userId='me',
            messageId=message_id,
            id=attachment_id
        ).execute()

        if 'data' in attachment:
            file_data = base64.urlsafe_b64decode(attachment['data'])
            logging.info(f"Successfully downloaded attachment for email {message_id}")
            return file_data
        else:
            logging.warning(f"No data found in attachment {attachment_id} for email {message_id}")
            return b''
    except HttpError as error:
        logging.error(f"Error downloading attachment {attachment_id} for email {message_id}: {error}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error downloading attachment: {e}")
        raise


def _extract_content_from_payload(payload: Dict[str, Any], preferred_type: str = 'text/plain') -> Tuple[str, str]:
    """
    Extract content from message payload.

    Args:
        payload: Message payload
        preferred_type: Preferred content type ('text/plain' or 'text/html')

    Returns:
        tuple: (content, content_type)
    """
    if 'body' in payload and 'data' in payload['body'] and 'parts' not in payload:
        content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        return content, payload.get('mimeType', 'text/plain')

    if 'parts' not in payload:
        return "", "text/plain"

    return _extract_content_from_parts(payload['parts'], preferred_type)


def _extract_content_from_parts(parts: List[Dict[str, Any]], preferred_type: str = 'text/plain') -> Tuple[str, str]:
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
        if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
            plain_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

        if part['mimeType'] == 'text/html' and 'data' in part.get('body', {}):
            html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

        if 'parts' in part and not (plain_content or html_content):
            nested_content, nested_type = _extract_content_from_parts(part['parts'], preferred_type)
            if nested_type == 'text/plain' and not plain_content:
                plain_content = nested_content
            elif nested_type == 'text/html' and not html_content:
                html_content = nested_content

    if preferred_type == 'text/html' and html_content:
        return html_content, 'text/html'
    elif plain_content:
        return plain_content, 'text/plain'
    elif html_content:
        return html_content, 'text/html'

    return "No content found", "text/plain"
