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
    get_label_map,
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def batch_get_metadata(service, message_ids: List[str],
                       label_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Fetch metadata for multiple messages using BatchHttpRequest.

    Args:
        service: Authenticated Gmail API service
        message_ids: List of message IDs to fetch metadata for
        label_map: Optional mapping of label ID to display name

    Returns:
        List of metadata dicts (message_id, subject, from, date, snippet, labels)
        in the same order as input IDs. Failed fetches include an 'error' key.
    """
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    def callback(request_id, response, exception):
        if exception:
            errors[request_id] = str(exception)
        else:
            results[request_id] = response

    for i in range(0, len(message_ids), 50):
        chunk = message_ids[i:i + 50]
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId='me', id=msg_id, format='metadata',
                    metadataHeaders=['From', 'To', 'Subject', 'Date']
                ),
                request_id=msg_id
            )
        batch.execute()

    metadata_list = []
    for msg_id in message_ids:
        if msg_id in errors:
            metadata_list.append({'message_id': msg_id, 'error': errors[msg_id]})
        elif msg_id in results:
            msg = results[msg_id]
            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
            raw_labels = msg.get('labelIds', [])
            resolved_labels = (
                [label_map.get(lid, lid) for lid in raw_labels]
                if label_map is not None
                else raw_labels
            )
            metadata_list.append({
                'message_id': msg_id,
                'thread_id': msg.get('threadId', ''),
                'subject': headers.get('Subject', 'No Subject'),
                'from': headers.get('From', 'Unknown'),
                'date': headers.get('Date', ''),
                'snippet': msg.get('snippet', ''),
                'labels': resolved_labels,
            })
        else:
            metadata_list.append({'message_id': msg_id, 'error': 'Not found in batch response'})

    logging.info(f"Batch fetched metadata for {len(metadata_list)} messages ({len(errors)} errors)")
    return metadata_list


def get_new_messages(service, history_id: str) -> Optional[List[str]]:
    """
    Get message IDs added since the given historyId.

    Args:
        service: Authenticated Gmail API service
        history_id: Starting history ID

    Returns:
        List of message IDs added since history_id.
        Returns None if history is expired (API returns 404).
    """
    try:
        message_ids = []
        page_token = None
        while True:
            kwargs: Dict[str, Any] = {
                'userId': 'me',
                'startHistoryId': history_id,
                'historyTypes': ['messageAdded'],
            }
            if page_token:
                kwargs['pageToken'] = page_token
            result = service.users().history().list(**kwargs).execute()
            for record in result.get('history', []):
                for msg in record.get('messagesAdded', []):
                    message_ids.append(msg['message']['id'])
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        logging.info(f"Found {len(message_ids)} new messages since historyId {history_id}")
        return message_ids
    except Exception as e:
        if '404' in str(e) or 'notFound' in str(e):
            logging.warning(f"History expired for historyId {history_id}, falling back to full sync")
            return None
        raise


def search_emails(service, query: str, max_results: int = 100, days_back: int = 7,
                 start_date: Optional[str] = None, end_date: Optional[str] = None,
                 label_map: Optional[Dict[str, str]] = None,
                 include_spam_trash: bool = False) -> List[Dict[str, Any]]:
    """
    Search for emails based on the given query and date range.

    Args:
        service: Authenticated Gmail API service
        query: Gmail search query string
        max_results: Maximum number of results to return (default: 100)
        days_back: Number of days back to search (default: 7)
        start_date: Start date in YYYY/MM/DD format (overrides days_back if provided)
        end_date: End date in YYYY/MM/DD format (defaults to today if start_date is provided)
        label_map: Optional mapping of label ID to display name. When provided,
            label IDs in preview results are resolved to human-readable names.
            If None, raw IDs are returned (backward compatible).
        include_spam_trash: Whether to include messages from SPAM and TRASH (default: False)

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

        # First page
        result = service.users().messages().list(
            userId='me',
            q=full_query,
            maxResults=max_results,
            includeSpamTrash=include_spam_trash
        ).execute()

        messages = result.get('messages', [])
        page_token = result.get('nextPageToken')
        page_num = 1

        # Paginate while more results exist and we haven't reached max_results
        while page_token and len(messages) < max_results:
            page_num += 1
            logging.info(f"Fetching page {page_num}...")
            result = service.users().messages().list(
                userId='me',
                q=full_query,
                maxResults=max_results - len(messages),
                pageToken=page_token,
                includeSpamTrash=include_spam_trash
            ).execute()
            batch = result.get('messages', [])
            messages.extend(batch)
            page_token = result.get('nextPageToken')

        # Truncate to exactly max_results
        messages = messages[:max_results]

        if not messages:
            logging.info(f"Found 0 matching emails")
            return []

        logging.info(f"Found {len(messages)} matching emails")

        message_ids = [m['id'] for m in messages]
        email_list = batch_get_metadata(service, message_ids, label_map=label_map)

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
