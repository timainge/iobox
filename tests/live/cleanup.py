#!/usr/bin/env python3
"""
Cleanup script for iobox live integration tests.

Searches for emails and drafts with the test subject tag [iobox-test-]
and permanently deletes them using the Gmail API.

Usage:
    python tests/live/cleanup.py
"""

import sys

from iobox.auth import get_gmail_service

TAG_PATTERN = "iobox-test-"
QUERY = f"subject:{TAG_PATTERN}"


def cleanup_messages(service) -> int:
    """Find and trash test messages.

    Uses trash (not permanent delete) because permanent delete requires
    the full https://mail.google.com/ scope, while trash works with
    gmail.modify.
    """
    trashed = 0
    page_token = None

    while True:
        kwargs = {
            "userId": "me",
            "q": QUERY,
            "maxResults": 100,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().messages().list(**kwargs).execute()
        messages = resp.get("messages", [])

        if not messages:
            break

        for msg in messages:
            msg_id = msg["id"]
            try:
                service.users().messages().trash(userId="me", id=msg_id).execute()
                trashed += 1
                print(f"  Trashed message {msg_id}")
            except Exception as e:
                print(f"  Warning: Could not trash message {msg_id}: {e}")

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return trashed


def cleanup_drafts(service) -> int:
    """Find and permanently delete test drafts."""
    deleted = 0
    page_token = None

    while True:
        kwargs = {
            "userId": "me",
            "maxResults": 100,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().drafts().list(**kwargs).execute()
        drafts = resp.get("drafts", [])

        if not drafts:
            break

        for draft in drafts:
            draft_id = draft["id"]
            try:
                # Fetch draft details to check subject
                detail = (
                    service.users()
                    .drafts()
                    .get(userId="me", id=draft_id, format="metadata")
                    .execute()
                )
                headers = detail.get("message", {}).get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

                if TAG_PATTERN in subject:
                    service.users().drafts().delete(userId="me", id=draft_id).execute()
                    deleted += 1
                    print(f"  Deleted draft {draft_id} ({subject})")
            except Exception as e:
                print(f"  Warning: Could not process draft {draft_id}: {e}")

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return deleted


def main():
    print("iobox Live Test Cleanup")
    print(f"Searching for messages/drafts matching: {QUERY}")
    print()

    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"Error: Could not authenticate: {e}")
        sys.exit(1)

    print("Cleaning up messages...")
    msg_count = cleanup_messages(service)

    print("\nCleaning up drafts...")
    draft_count = cleanup_drafts(service)

    print(f"\nDone. Trashed {msg_count} message(s) and deleted {draft_count} draft(s).")


if __name__ == "__main__":
    main()
