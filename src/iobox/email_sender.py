"""
Email Sender Module.

This module handles composing and sending emails, including forwarding,
via the Gmail API.
"""

import base64
import logging
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, List

from googleapiclient.errors import HttpError

from iobox.email_retrieval import get_email_content

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def compose_message(to: str, subject: str, body: str,
                    from_addr: Optional[str] = None,
                    cc: Optional[str] = None,
                    bcc: Optional[str] = None,
                    content_type: str = 'plain',
                    attachments: Optional[List[str]] = None) -> Dict[str, str]:
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

    Returns:
        dict: Message body with 'raw' base64url-encoded RFC 2822 payload
    """
    text_part = MIMEText(body, content_type)

    if attachments:
        if content_type == 'html':
            # nested multipart: mixed outer, alternative inner
            outer = MIMEMultipart('mixed')
            inner = MIMEMultipart('alternative')
            inner.attach(MIMEText(body, 'plain'))
            inner.attach(MIMEText(body, 'html'))
            outer.attach(inner)
        else:
            outer = MIMEMultipart('mixed')
            outer.attach(text_part)

        for file_path in attachments:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            main_type, sub_type = mime_type.split('/', 1)

            with open(file_path, 'rb') as f:
                file_data = f.read()

            part = MIMEBase(main_type, sub_type)
            part.set_payload(file_data)
            encoders.encode_base64(part)
            import os
            filename = os.path.basename(file_path)
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            outer.attach(part)

        message = outer
    else:
        message = text_part

    message['to'] = to
    message['subject'] = subject

    if from_addr:
        message['from'] = from_addr
    if cc:
        message['cc'] = cc
    if bcc:
        message['bcc'] = bcc

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw}


def compose_forward_message(original_email: Dict[str, Any], to: str,
                            from_addr: Optional[str] = None,
                            additional_text: Optional[str] = None) -> Dict[str, str]:
    """
    Compose a forwarded email message.

    Wraps the original email content with standard forwarding headers.

    Args:
        original_email: Email data dict as returned by get_email_content
        to: Recipient email address to forward to
        from_addr: Sender address (optional)
        additional_text: Optional text to prepend above the forwarded content

    Returns:
        dict: Message body with 'raw' base64url-encoded RFC 2822 payload
    """
    orig_from = original_email.get('from', 'Unknown')
    orig_date = original_email.get('date', 'Unknown')
    orig_subject = original_email.get('subject', 'No Subject')
    orig_body = original_email.get('body', '') or original_email.get('content', '')

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
    subject = f"Fwd: {orig_subject}"

    return compose_message(to=to, subject=subject, body=body, from_addr=from_addr)


def send_message(service, message: Dict[str, str]) -> Dict[str, Any]:
    """
    Send an email message via the Gmail API.

    Args:
        service: Authenticated Gmail API service
        message: Message body dict with 'raw' key

    Returns:
        dict: Gmail API send response containing the message id and other metadata
    """
    try:
        result = service.users().messages().send(
            userId='me',
            body=message
        ).execute()
        logging.info(f"Message sent successfully. Message Id: {result.get('id', '')}")
        return result
    except HttpError as error:
        logging.error(f"Error sending message: {error}")
        raise


def forward_email(service, message_id: str, to: str,
                  from_addr: Optional[str] = None,
                  additional_text: Optional[str] = None) -> Dict[str, Any]:
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
    email_data = get_email_content(service, message_id=message_id)
    message = compose_forward_message(
        original_email=email_data,
        to=to,
        from_addr=from_addr,
        additional_text=additional_text,
    )
    return send_message(service, message)


def create_draft(service, message: Dict[str, str]) -> Dict[str, Any]:
    """
    Create a Gmail draft.

    Args:
        service: Authenticated Gmail API service
        message: Message body dict with 'raw' key

    Returns:
        dict: The draft resource dict from the Gmail API
    """
    draft = service.users().drafts().create(
        userId='me', body={'message': message}
    ).execute()
    return draft


def list_drafts(service, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    List Gmail drafts.

    Args:
        service: Authenticated Gmail API service
        max_results: Maximum number of drafts to return

    Returns:
        list: List of dicts with id, subject, and snippet for each draft
    """
    result = service.users().drafts().list(
        userId='me', maxResults=max_results
    ).execute()
    drafts = result.get('drafts', [])
    draft_list = []
    for d in drafts:
        draft_data = service.users().drafts().get(
            userId='me', id=d['id'], format='metadata'
        ).execute()
        msg = draft_data.get('message', {})
        headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        draft_list.append({
            'id': d['id'],
            'subject': headers.get('Subject', '(no subject)'),
            'snippet': msg.get('snippet', ''),
        })
    return draft_list


def get_draft(service, draft_id: str) -> Dict[str, Any]:
    """
    Get a specific draft by ID.

    Args:
        service: Authenticated Gmail API service
        draft_id: The draft ID to retrieve

    Returns:
        dict: The full draft resource dict from the Gmail API
    """
    return service.users().drafts().get(
        userId='me', id=draft_id, format='full'
    ).execute()


def send_draft(service, draft_id: str) -> Dict[str, Any]:
    """
    Send an existing draft.

    Args:
        service: Authenticated Gmail API service
        draft_id: The draft ID to send

    Returns:
        dict: Gmail API send response
    """
    return service.users().drafts().send(
        userId='me', body={'id': draft_id}
    ).execute()


def delete_draft(service, draft_id: str) -> Dict[str, Any]:
    """
    Permanently delete a draft.

    Args:
        service: Authenticated Gmail API service
        draft_id: The draft ID to delete

    Returns:
        dict: Status dict with 'status' and 'draft_id' keys
    """
    service.users().drafts().delete(
        userId='me', id=draft_id
    ).execute()
    return {'status': 'deleted', 'draft_id': draft_id}
