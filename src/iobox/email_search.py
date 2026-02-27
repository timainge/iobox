"""
Email Search and Retrieval Module.

This module handles searching for emails based on query criteria and date range.
Retrieval functions are re-exported from email_retrieval for backward compatibility.
"""

from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
import logging
from typing import Dict, Any, List, Optional

# Re-export public retrieval functions for backward compatibility
from iobox.email_retrieval import (
    get_email_content,
    download_attachment,
)

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
        full_query = query

        if start_date and validate_date_format(start_date):
            date_query = f"after:{start_date}"

            if end_date and validate_date_format(end_date):
                date_query += f" before:{end_date}"

            full_query = f"{query} {date_query}"
        else:
            date_query = f"after:{(datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')}"
            full_query = f"{query} {date_query}"

        logging.info(f"Searching for emails with query: {full_query}")

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

        email_list = []
        for message in messages:
            email_id = message['id']

            msg = service.users().messages().get(
                userId='me',
                id=email_id,
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'Date']
            ).execute()

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
        parts = date_str.split('/')
        if len(parts) != 3:
            return False

        year, month, day = parts
        if len(year) != 4 or len(month) != 2 or len(day) != 2:
            return False

        datetime.strptime(date_str, '%Y/%m/%d')
        return True
    except ValueError:
        logging.warning(f"Invalid date format: {date_str}. Expected YYYY/MM/DD")
        return False
