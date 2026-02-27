"""
Email Sender Module.

This module handles composing and sending emails, including forwarding,
via the Gmail API.
"""

import base64
import logging
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

from googleapiclient.errors import HttpError

from iobox.email_retrieval import get_email_content

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def compose_message(to: str, subject: str, body: str,
                    from_addr: Optional[str] = None,
                    cc: Optional[str] = None,
                    bcc: Optional[str] = None) -> Dict[str, str]:
    """
    Compose an RFC 2822 email message encoded for the Gmail API.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain-text email body
        from_addr: Sender email address (optional, Gmail uses authenticated user by default)
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)

    Returns:
        dict: Message body with 'raw' base64url-encoded RFC 2822 payload
    """
    message = MIMEText(body)
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
