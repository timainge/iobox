#!/usr/bin/env python
"""
Test script for Gmail API authentication.

This script tests the authentication module by:
1. Checking the status of authentication
2. Attempting to authenticate with Gmail API
3. Fetching user profile information to verify connection
"""

import os
import sys
import json
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add src directory to path so we can import iobox
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from iobox.auth import get_gmail_service, check_auth_status


def main():
    """Run the authentication test."""
    # Step 1: Check authentication status
    logger.info("Checking authentication status...")
    status = check_auth_status()
    logger.info(f"Authentication status: {json.dumps(status, indent=2)}")
    
    # Check if credentials file exists
    if not status["credentials_file_exists"]:
        logger.error(
            "Credentials file not found. Please download OAuth 2.0 Client ID JSON "
            "from Google Cloud Console and save it as 'credentials.json' in the project root."
        )
        print("\nTo set up Google Cloud OAuth 2.0 credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project or select an existing one")
        print("3. Navigate to APIs & Services > Credentials")
        print("4. Click 'Create Credentials' > 'OAuth client ID'")
        print("5. Choose 'Desktop app' as application type")
        print("6. Download the JSON file and save it as 'credentials.json' in the project root")
        return
    
    # Step 2: Try to authenticate and get service
    try:
        logger.info("Attempting to authenticate with Gmail API...")
        service = get_gmail_service()
        
        # Step 3: Fetch user profile to verify connection
        logger.info("Fetching user profile to verify connection...")
        profile = service.users().getProfile(userId='me').execute()
        
        logger.info("-" * 50)
        logger.info("Authentication successful!")
        logger.info(f"Connected to Gmail account: {profile['emailAddress']}")
        logger.info(f"Total threads: {profile['threadsTotal']}")
        logger.info(f"Total messages: {profile['messagesTotal']}")
        logger.info("-" * 50)
        
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return


if __name__ == "__main__":
    main()
