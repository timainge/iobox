"""
Markdown Conversion Module.

This module handles converting email content to markdown format with YAML frontmatter.
"""

import re
from datetime import datetime
import logging
import html2text
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def generate_yaml_frontmatter(email_data: Dict[str, Any]) -> str:
    """
    Generate YAML frontmatter from email metadata.

    Args:
        email_data: Dictionary containing email metadata

    Returns:
        str: YAML frontmatter string
    """
    message_id = email_data.get('message_id', '') or email_data.get('id', '')

    frontmatter = {
        'message_id': message_id,
        'thread_id': email_data.get('thread_id', ''),
        'subject': email_data.get('subject', 'No Subject'),
        'from': email_data.get('from', 'Unknown'),
        'to': email_data.get('to', ''),
        'date': email_data.get('date', datetime.now().isoformat()),
        'labels': email_data.get('labels', []),
        'saved_date': datetime.now().isoformat()
    }

    if 'attachments' in email_data:
        frontmatter['attachments'] = email_data['attachments']

    yaml_str = '---\n'

    for key, value in sorted(frontmatter.items()):
        if key == 'labels':
            yaml_str += f"{key}:\n"
            for label in value:
                yaml_str += f"  - {label}\n"
        elif key == 'attachments':
            yaml_str += f"{key}:\n"
            for attachment in value:
                yaml_str += f"  - filename: {attachment.get('filename', '')}\n"
                yaml_str += f"    mime_type: {attachment.get('mime_type', '')}\n"
        else:
            yaml_str += f"{key}: {value}\n"

    yaml_str += '---\n\n'

    return yaml_str


def convert_html_to_markdown(html_content: str) -> str:
    """
    Convert HTML content to markdown format.

    Args:
        html_content: HTML content to convert

    Returns:
        str: Markdown content
    """
    h = html2text.HTML2Text()

    h.ignore_links = False
    h.ignore_images = False
    h.ignore_tables = False
    h.ignore_emphasis = False
    h.body_width = 0
    h.unicode_snob = True
    h.mark_code = True
    h.wrap_links = False
    h.protect_links = True
    h.default_image_alt = ""
    h.single_line_break = False

    h.bypass_tables = False
    h.pad_tables = True

    try:
        markdown = h.handle(html_content)
        markdown = _clean_email_markdown(markdown)
        return markdown
    except Exception as e:
        logging.warning(f"Error converting HTML to markdown: {e}")
        return strip_html_tags(html_content)


def _clean_email_markdown(markdown_content: str) -> str:
    """
    Clean up common email HTML artifacts in markdown content.

    Args:
        markdown_content: Raw markdown content from html2text

    Returns:
        str: Cleaned markdown content
    """
    markdown_content = markdown_content.replace('\r\n', '\n').replace('\r', '\n')

    lines = markdown_content.split('\n')
    lines = [line.rstrip() for line in lines]
    markdown_content = '\n'.join(lines)

    while '\n\n\n' in markdown_content:
        markdown_content = markdown_content.replace('\n\n\n', '\n\n')

    markdown_content = re.sub(r'!\[\]\([^)]*\)', '', markdown_content)
    markdown_content = re.sub(r'\[\s*\]\([^)]*\)', '', markdown_content)
    markdown_content = re.sub(r'^\s*[-=]{3,}\s*$', '---', markdown_content, flags=re.MULTILINE)
    markdown_content = re.sub(r'\]\(<([^>]+)>\)', r'](\1)', markdown_content)

    return markdown_content.strip()


def convert_email_to_markdown(email_data: Dict[str, Any]) -> str:
    """
    Convert email data to markdown format with YAML frontmatter.

    Args:
        email_data: Dictionary containing email data and metadata

    Returns:
        str: Markdown content with YAML frontmatter
    """
    try:
        markdown_content = generate_yaml_frontmatter(email_data)

        subject = email_data.get('subject', 'No Subject')
        markdown_content += f"# {subject}\n\n"

        content = email_data.get('body', '') or email_data.get('content', '')
        content_type = email_data.get('content_type', 'text/plain')

        if content_type == 'text/html':
            markdown_content += convert_html_to_markdown(content)
        else:
            markdown_content += content

        return markdown_content

    except Exception as e:
        logging.error(f"Error converting email to markdown: {e}")
        raise


def strip_html_tags(html_content: str) -> str:
    """
    Remove HTML tags from content.

    Args:
        html_content: HTML content to strip tags from

    Returns:
        str: Plain text content without HTML tags
    """
    clean_text = re.sub(r'<[^>]*>', '', html_content)

    clean_text = clean_text.replace('&nbsp;', ' ')
    clean_text = clean_text.replace('&lt;', '<')
    clean_text = clean_text.replace('&gt;', '>')
    clean_text = clean_text.replace('&amp;', '&')
    clean_text = clean_text.replace('&quot;', '"')
    clean_text = clean_text.replace('&apos;', "'")

    clean_text = re.sub(r'\s+', ' ', clean_text)

    return clean_text.strip()
