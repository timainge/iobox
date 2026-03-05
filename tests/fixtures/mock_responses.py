"""
Mock response data for Gmail API tests.

This module contains mock response data structures that mimic the actual
responses from the Gmail API for use in tests.
"""

# Mock message list response
MOCK_MESSAGE_LIST = {
    "messages": [
        {"id": "message-id-1", "threadId": "thread-id-1"},
        {"id": "message-id-2", "threadId": "thread-id-2"},
        {"id": "message-id-3", "threadId": "thread-id-3"},
    ],
    "nextPageToken": "next-page-token",
    "resultSizeEstimate": 3,
}

# Mock message with plain text content
MOCK_PLAIN_TEXT_MESSAGE = {
    "id": "message-id-1",
    "threadId": "thread-id-1",
    "labelIds": ["INBOX", "CATEGORY_PERSONAL"],
    "snippet": "This is a snippet of the email content...",
    "payload": {
        "mimeType": "text/plain",
        "headers": [
            {"name": "From", "value": "sender@example.com"},
            {"name": "To", "value": "recipient@example.com"},
            {"name": "Subject", "value": "Test Email Subject"},
            {"name": "Date", "value": "Mon, 23 Mar 2025 10:00:00 +1100"},
        ],
        "body": {
            "data": "VGhpcyBpcyB0aGUgcGxhaW4gdGV4dCBib2R5IG9mIHRoZSBlbWFpbC4K",  # Base64 encoded
            "size": 123,
        },
    },
}

# Mock message with HTML content
MOCK_HTML_MESSAGE = {
    "id": "message-id-2",
    "threadId": "thread-id-2",
    "labelIds": ["INBOX", "CATEGORY_UPDATES"],
    "snippet": "This is a snippet of the HTML email...",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "sender@example.com"},
            {"name": "To", "value": "recipient@example.com"},
            {"name": "Subject", "value": "HTML Email Subject"},
            {"name": "Date", "value": "Mon, 23 Mar 2025 11:00:00 +1100"},
        ],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": "VGhpcyBpcyB0aGUgcGxhaW4gdGV4dCB2ZXJzaW9uIG9mIHRoZSBIVE1MIGVtYWlsLg==",
                    "size": 123,
                },
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": (
                        "PGh0bWw+PGJvZHk+PHA+VGhpcyBpcyB0aGUgSFRNTCB2ZXJzaW9uIG9mIHRoZSBlbWFpbC4"
                        "8L3A+PC9ib2R5PjwvaHRtbD4="
                    ),
                    "size": 456,
                },
            },
        ],
    },
}

# Mock message with only plain text (for fallback testing)
MOCK_PLAIN_TEXT_ONLY_MESSAGE = {
    "id": "message-id-2",
    "threadId": "thread-id-2",
    "labelIds": ["INBOX", "CATEGORY_UPDATES"],
    "snippet": "This is a snippet of the HTML email...",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "sender@example.com"},
            {"name": "To", "value": "recipient@example.com"},
            {"name": "Subject", "value": "HTML Email Subject"},
            {"name": "Date", "value": "Mon, 23 Mar 2025 11:00:00 +1100"},
        ],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": "VGhpcyBpcyB0aGUgcGxhaW4gdGV4dCB2ZXJzaW9uIG9mIHRoZSBIVE1MIGVtYWlsLg==",
                    "size": 123,
                },
            }
        ],
    },
}

# Mock message with attachment
MOCK_ATTACHMENT_MESSAGE = {
    "id": "message-id-3",
    "threadId": "thread-id-3",
    "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"],
    "snippet": "This is a snippet of the email with attachment...",
    "payload": {
        "mimeType": "multipart/mixed",
        "headers": [
            {"name": "From", "value": "sender@example.com"},
            {"name": "To", "value": "recipient@example.com"},
            {"name": "Subject", "value": "Email with Attachment"},
            {"name": "Date", "value": "Mon, 23 Mar 2025 12:00:00 +1100"},
        ],
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "VGhpcyBlbWFpbCBoYXMgYW4gYXR0YWNobWVudC4=", "size": 123},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": (
                                "PGh0bWw+PGJvZHk+PHA+VGhpcyBlbWFpbCBoYXMgYW4gYXR0YWNobWVudC4"
                                "8L3A+PC9ib2R5PjwvaHRtbD4="
                            ),
                            "size": 456,
                        },
                    },
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "document.pdf",
                "headers": [
                    {"name": "Content-Type", "value": "application/pdf"},
                    {"name": "Content-Disposition", "value": "attachment; filename=document.pdf"},
                ],
                "body": {"attachmentId": "attachment-id-1", "size": 789},
            },
        ],
    },
}
