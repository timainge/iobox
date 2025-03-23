"""
Email Search and Retrieval Module.

This module handles searching for emails based on query criteria and date range.
"""

from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def search_emails(service, query, max_results=100, days_back=7):
    """
    Search for emails based on the given query and date range.
    
    Args:
        service: Authenticated Gmail API service
        query: Gmail search query string
        max_results: Maximum number of results to return (default: 100)
        days_back: Number of days back to search (default: 7)
        
    Returns:
        list: List of message dictionaries containing id and threadId
    """
    try:
        # Add date range to query
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
        
        # Handle pagination if more results are available
        while 'nextPageToken' in result and len(messages) < max_results:
            page_token = result['nextPageToken']
            result = service.users().messages().list(
                userId='me', 
                q=full_query, 
                maxResults=max_results,
                pageToken=page_token
            ).execute()
            messages.extend(result.get('messages', []))
        
        logging.info(f"Found {len(messages)} matching emails")
        return messages
        
    except HttpError as error:
        logging.error(f"An error occurred during search: {error}")
        return []
    

def get_email_content(service, msg_id):
    """
    Retrieve the full content of an email by its ID.
    
    Args:
        service: Authenticated Gmail API service
        msg_id: Email message ID
        
    Returns:
        tuple: (subject, sender, date, content) or (None, None, None, None) on error
    """
    try:
        # Get the full message
        message = service.users().messages().get(
            userId='me', 
            id=msg_id, 
            format='full'
        ).execute()
        
        # Extract headers
        payload = message['payload']
        headers = payload['headers']
        
        subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
        sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
        date = next((header['value'] for header in headers if header['name'].lower() == 'date'), 'Unknown Date')
        
        # Extract content based on MIME type
        content = ""
        
        if 'parts' in payload:
            # Multipart message
            content = _extract_content_from_parts(payload['parts'])
        else:
            # Single part message
            if 'body' in payload and 'data' in payload['body']:
                import base64
                content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return subject, sender, date, content
        
    except HttpError as error:
        logging.error(f"Error retrieving email content for {msg_id}: {error}")
        return None, None, None, None


def _extract_content_from_parts(parts):
    """
    Extract content from multipart message parts.
    
    Args:
        parts: List of message parts
        
    Returns:
        str: Extracted content
    """
    import base64
    
    # First look for plain text parts
    for part in parts:
        if part['mimeType'] == 'text/plain' and 'data' in part['body']:
            return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
    
    # If no plain text, look for HTML parts
    for part in parts:
        if part['mimeType'] == 'text/html' and 'data' in part['body']:
            html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            # TODO: Convert HTML to markdown in a future enhancement
            return html_content
    
    # Handle nested parts (if any)
    for part in parts:
        if 'parts' in part:
            return _extract_content_from_parts(part['parts'])
    
    return "No content found"
