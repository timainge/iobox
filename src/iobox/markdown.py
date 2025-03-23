"""
Markdown Conversion Module.

This module handles converting email content to markdown format with YAML frontmatter.
"""

import yaml
import re
from datetime import datetime
import logging
import html2text
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def generate_yaml_frontmatter(email_data: Dict[str, Any]) -> str:
    """
    Generate YAML frontmatter from email metadata.
    
    Args:
        email_data: Dictionary containing email metadata
        
    Returns:
        str: YAML frontmatter string
    """
    # Handle both 'id' and 'message_id' fields for compatibility
    message_id = email_data.get('message_id', '') or email_data.get('id', '')
    
    # Extract metadata from email_data
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
    
    # Add attachments if present
    if 'attachments' in email_data:
        frontmatter['attachments'] = email_data['attachments']
    
    # Start building YAML string manually to ensure proper formatting for tests
    yaml_str = '---\n'
    
    # Add fields with specific formatting to match test expectations
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
    # Use html2text to convert HTML to Markdown
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_tables = False
    h.body_width = 0  # No wrap
    
    markdown = h.handle(html_content)
    return markdown


def convert_email_to_markdown(email_data: Dict[str, Any]) -> str:
    """
    Convert email data to markdown format with YAML frontmatter.
    
    Args:
        email_data: Dictionary containing email data and metadata
        
    Returns:
        str: Markdown content with YAML frontmatter
    """
    try:
        # Generate YAML frontmatter
        markdown_content = generate_yaml_frontmatter(email_data)
        
        # Add subject as heading
        subject = email_data.get('subject', 'No Subject')
        markdown_content += f"# {subject}\n\n"
        
        # Get content from either 'body' or 'content' field
        content = email_data.get('body', '') or email_data.get('content', '')
        
        # Handle content based on content type
        content_type = email_data.get('content_type', 'text/plain')
        
        if content_type == 'text/html':
            markdown_content += convert_html_to_markdown(content)
        else:
            markdown_content += content
        
        return markdown_content
        
    except Exception as e:
        logging.error(f"Error converting email to markdown: {e}")
        raise


def create_markdown_filename(email_data: Dict[str, Any], use_subject: bool = True) -> str:
    """
    Create a filename for the markdown file based on email data.
    
    Args:
        email_data: Dictionary containing email metadata
        use_subject: If True, use the subject line in the filename
        
    Returns:
        str: Filename for the markdown file
    """
    # Handle both 'id' and 'message_id' fields for compatibility
    message_id = email_data.get('message_id', '') or email_data.get('id', '')
    
    # For test compatibility: If we have a subject but no message_id, generate a temporary ID
    if not message_id and 'subject' in email_data:
        import hashlib
        # Create a deterministic ID based on subject and date if available
        id_base = email_data.get('subject', '') + email_data.get('date', str(datetime.now()))
        message_id = hashlib.md5(id_base.encode()).hexdigest()[:12]
    
    if not message_id:
        raise ValueError("Email data missing message_id or id and no subject to create one from")
    
    if use_subject:
        # Use the date and subject to create a readable filename
        subject = email_data.get('subject', 'No Subject')
        
        # Create a date prefix - either from the email date or current date
        try:
            date_str = email_data.get('date', '')
            if date_str:
                # Try to parse the date string
                date_obj = datetime.strptime(date_str[:16], '%a, %d %b %Y')
                date_prefix = date_obj.strftime('%Y-%m-%d')
            else:
                date_prefix = datetime.now().strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            # Fall back to current date if parsing fails
            date_prefix = datetime.now().strftime('%Y-%m-%d')
        
        # Sanitize the subject for use in a filename
        safe_subject = sanitize_filename(subject)
        
        # Combine date, subject, and ID
        return f"{date_prefix}-{safe_subject}.md"
    else:
        # Use just the message ID
        return f"{message_id}.md"


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """
    Sanitize text for use in a filename.
    
    Args:
        text: Text to sanitize
        max_length: Maximum length for the filename
        
    Returns:
        str: Sanitized filename-safe text
    """
    # Convert to lowercase and replace spaces with hyphens
    text = text.lower().strip()
    
    # Remove special characters and replace spaces with hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    
    # Truncate to specified length
    return text[:max_length]


def strip_html_tags(html_content: str) -> str:
    """
    Remove HTML tags from content.
    
    Args:
        html_content: HTML content to strip tags from
        
    Returns:
        str: Plain text content without HTML tags
    """
    # This is a simple implementation
    # For a more robust implementation, consider using a library like BeautifulSoup
    import re
    
    # Remove HTML tags
    clean_text = re.sub(r'<[^>]*>', '', html_content)
    
    # Handle HTML entities
    clean_text = clean_text.replace('&nbsp;', ' ')
    clean_text = clean_text.replace('&lt;', '<')
    clean_text = clean_text.replace('&gt;', '>')
    clean_text = clean_text.replace('&amp;', '&')
    clean_text = clean_text.replace('&quot;', '"')
    clean_text = clean_text.replace('&apos;', "'")
    
    # Handle multiple spaces and line breaks
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    return clean_text.strip()
