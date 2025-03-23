"""
Markdown Conversion Module.

This module handles converting email content to markdown format with YAML frontmatter.
"""

import yaml
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def save_as_markdown(subject, sender, date, content, msg_id, output_dir):
    """
    Save email content as a markdown file with YAML frontmatter.
    
    Args:
        subject: Email subject
        sender: Email sender
        date: Email date
        content: Email content
        msg_id: Unique email ID
        output_dir: Directory to save the markdown file
        
    Returns:
        str: Path to the saved file, or None on error
    """
    import os
    
    # Create filename from message ID
    filename = f"{msg_id}.md"
    filepath = os.path.join(output_dir, filename)
    
    # Create frontmatter with metadata
    frontmatter = {
        'message_id': msg_id,
        'subject': subject,
        'sender': sender,
        'date': date,
        'saved_date': datetime.now().isoformat()
    }
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Write markdown file with YAML frontmatter
        with open(filepath, 'w', encoding='utf-8') as f:
            # Write YAML frontmatter
            f.write('---\n')
            yaml.dump(frontmatter, f, default_flow_style=False)
            f.write('---\n\n')
            
            # Write content with subject as heading
            f.write(f"# {subject}\n\n")
            f.write(content)
        
        logging.info(f"Saved email: {filename}")
        return filepath
        
    except IOError as error:
        logging.error(f"Error saving file {filename}: {error}")
        return None


def format_html_content(html_content):
    """
    Convert HTML email content to markdown format.
    
    Note: This is a placeholder for future HTML to Markdown conversion.
    Currently, it returns the HTML content unchanged.
    
    Args:
        html_content: HTML content to convert
        
    Returns:
        str: Markdown content
    """
    # TODO: Implement HTML to Markdown conversion
    # For a full implementation, we would use a library like html2text
    return html_content
