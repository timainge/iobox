"""
Utility functions shared across iobox modules.

Contains filename generation and text sanitization helpers.
"""

import re
import hashlib
from datetime import datetime
from typing import Dict, Any


def slugify_text(text: str, max_length: int = 50) -> str:
    """
    Convert text to a URL/filename-safe slug.

    Args:
        text: Text to slugify
        max_length: Maximum length for the slug

    Returns:
        str: Slugified text
    """
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    return text[:max_length]


def create_markdown_filename(email_data: Dict[str, Any], use_subject: bool = True) -> str:
    """
    Create a filename for the markdown file based on email data.

    Args:
        email_data: Dictionary containing email metadata
        use_subject: If True, use the subject line in the filename

    Returns:
        str: Filename for the markdown file
    """
    message_id = email_data.get('message_id', '') or email_data.get('id', '')

    if not message_id and 'subject' in email_data:
        id_base = email_data.get('subject', '') + email_data.get('date', str(datetime.now()))
        message_id = hashlib.md5(id_base.encode()).hexdigest()[:12]

    if not message_id:
        raise ValueError("Email data missing message_id or id and no subject to create one from")

    if use_subject:
        subject = email_data.get('subject', 'No Subject')

        try:
            date_str = email_data.get('date', '')
            if date_str:
                date_obj = datetime.strptime(date_str[:16], '%a, %d %b %Y')
                date_prefix = date_obj.strftime('%Y-%m-%d')
            else:
                date_prefix = datetime.now().strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            date_prefix = datetime.now().strftime('%Y-%m-%d')

        safe_subject = slugify_text(subject)
        return f"{date_prefix}-{safe_subject}.md"
    else:
        return f"{message_id}.md"
