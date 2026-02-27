"""
Email Search and Retrieval Module.

This module handles searching for emails based on query criteria and date range.
"""

from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
import logging
import base64
from typing import Dict, Any, List, Optional, Tuple, Union

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def search_emails(service, query: str, max_results: int = 100, days_back: int = 7, 
                 start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for emails based on the given query and date range.
    
    Args:
        service: Authenticated Gmail API service
        query: Gmail search query string
        max_results: Maximum number of results to return (default: 100)
        days_back: Number of days back to search (default: 7)
        start_date: Start date in YYYY/MM/DD format (overrides days_back if provided)
        end_date: End date in YYYY/MM/DD format (defaults to today if start_date is provided)
        
    Returns:
        list: List of message dictionaries with basic preview information
    """
    try:
        # Determine date range for query
        full_query = query
        
        if start_date and validate_date_format(start_date):
            # If start_date is provided, use it instead of days_back
            date_query = f"after:{start_date}"
            
            # Add end_date if provided, otherwise default to current date
            if end_date and validate_date_format(end_date):
                date_query += f" before:{end_date}"
                
            full_query = f"{query} {date_query}"
        else:
            # Use days_back approach if no specific dates provided
            date_query = f"after:{(datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')}"
            full_query = f"{query} {date_query}"
        
        logging.info(f"Searching for emails with query: {full_query}")
        
        # Execute the search
        result = service.users().messages().list(
            userId='me', 
            q=full_query, 
            maxResults=max_results
        ).execute()
        
        messages = result.get('messages', [])
        
        if not messages:
            logging.info(f"Found 0 matching emails")
            return []
            
        logging.info(f"Found {len(messages)} matching emails")
        
        # Get message details
        email_list = []
        for message in messages:
            email_id = message['id']
            
            # Get message details with minimal scope to avoid large payload
            msg = service.users().messages().get(
                userId='me', 
                id=email_id,
                format='metadata', 
                metadataHeaders=['From', 'To', 'Subject', 'Date']
            ).execute()
            
            # Extract relevant data
            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
            
            email_list.append({
                'message_id': email_id,
                'thread_id': msg.get('threadId', ''),
                'subject': headers.get('Subject', 'No Subject'),
                'from': headers.get('From', 'Unknown'),
                'date': headers.get('Date', ''),
                'snippet': msg.get('snippet', ''),
                'labels': msg.get('labelIds', [])
            })
            
        return email_list
        
    except HttpError as error:
        logging.error(f"Error searching for emails: {error}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise


def validate_date_format(date_str: str) -> bool:
    """
    Validate that a date string matches the YYYY/MM/DD format.
    
    Args:
        date_str: Date string to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    try:
        # Check format first using split to ensure we have leading zeros in months and days
        parts = date_str.split('/')
        if len(parts) != 3:
            return False
            
        year, month, day = parts
        if len(year) != 4 or len(month) != 2 or len(day) != 2:
            return False
            
        # Now try parsing the date
        datetime.strptime(date_str, '%Y/%m/%d')
        return True
    except ValueError:
        logging.warning(f"Invalid date format: {date_str}. Expected YYYY/MM/DD")
        return False


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
    # Handle both parameter names for backwards compatibility
    email_id = message_id if message_id is not None else msg_id
    
    if email_id is None:
        logging.error("No message ID provided")
        raise ValueError("No message ID provided")
    
    try:
        # Get the full message
        message = service.users().messages().get(
            userId='me', 
            id=email_id, 
            format='full'
        ).execute()
        
        # Extract headers
        payload = message['payload']
        headers = payload['headers']
        
        # Create email data dictionary
        email_data = {
            'message_id': email_id,
            'subject': next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject'),
            'from': next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender'),
            'date': next((header['value'] for header in headers if header['name'].lower() == 'date'), 'Unknown Date'),
            'labels': message.get('labelIds', []),
            'snippet': message.get('snippet', ''),
            'thread_id': message.get('threadId', '')
        }
        
        # Extract content based on MIME type
        content, content_type = _extract_content_from_payload(payload, preferred_content_type)
        email_data['body'] = content           # Primary field used by markdown conversion
        email_data['content'] = content        # Keep for backward compatibility
        email_data['content_type'] = content_type
        
        # For backward compatibility
        if content_type == 'text/html':
            email_data['html_content'] = content
            email_data['plain_content'] = ''
        else:
            email_data['plain_content'] = content
            email_data['html_content'] = ''
        
        # Look for attachments
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
        
        # Check for nested parts
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
        
        # Attachment data is base64 encoded
        if 'data' in attachment:
            # The data might include URL-safe base64 encoding with '-' and '_'
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
    import base64
    
    # Handle single-part messages
    if 'body' in payload and 'data' in payload['body'] and 'parts' not in payload:
        content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        return content, payload.get('mimeType', 'text/plain')
    
    # Handle multi-part messages
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
    import base64
    
    plain_content = ""
    html_content = ""
    
    # First pass - find content of both types
    for part in parts:
        if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
            plain_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        
        if part['mimeType'] == 'text/html' and 'data' in part.get('body', {}):
            html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        
        # Handle nested parts
        if 'parts' in part and not (plain_content or html_content):
            nested_content, nested_type = _extract_content_from_parts(part['parts'], preferred_type)
            if nested_type == 'text/plain' and not plain_content:
                plain_content = nested_content
            elif nested_type == 'text/html' and not html_content:
                html_content = nested_content
    
    # Return based on preference and availability
    if preferred_type == 'text/html' and html_content:
        return html_content, 'text/html'
    elif plain_content:
        return plain_content, 'text/plain'
    elif html_content:
        return html_content, 'text/html'
    
    return "No content found", "text/plain"
