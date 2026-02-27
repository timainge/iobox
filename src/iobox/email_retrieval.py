"""
Email Retrieval Module.

This module handles retrieving full email content and downloading attachments
from the Gmail API.
"""

import base64
import logging
from typing import Dict, Any, List, Tuple
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_email_content(service, message_id: str = None, msg_id: str = None,
                      preferred_content_type: str = 'text/plain') -> Dict[str, Any]:
    """
    Retrieve the full content of an email by its ID.

    Args:
        service: Authenticated Gmail API service
        message_id: Email message ID (new parameter name)
        msg_id: Email message ID (legacy parameter name)
        preferred_content_type: Preferred content type ('text/plain' or 'text/html')

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

        email_data = {
            'message_id': email_id,
            'subject': next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject'),
            'from': next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender'),
            'date': next((header['value'] for header in headers if header['name'].lower() == 'date'), 'Unknown Date'),
            'labels': message.get('labelIds', []),
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
