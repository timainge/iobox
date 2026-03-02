"""
Authentication Module for Gmail API access.

This module handles the OAuth 2.0 authentication flow for the Gmail API.
"""

import os
import logging
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# If modifying these scopes, delete the token.json file.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
]

# Get credential paths from environment variables or use defaults
CREDENTIALS_DIR = os.getenv('CREDENTIALS_DIR', os.getcwd())
CREDENTIALS_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
TOKEN_FILE = os.getenv('GMAIL_TOKEN_FILE', 'token.json')

# Create full paths
CREDENTIALS_PATH = os.path.join(CREDENTIALS_DIR, CREDENTIALS_FILE)
TOKEN_PATH = os.path.join(CREDENTIALS_DIR, TOKEN_FILE)


def get_gmail_service():
    """
    Authenticate with Gmail API and return a service object.
    
    Handles the OAuth 2.0 flow, including:
    - Loading saved credentials if they exist
    - Refreshing expired credentials
    - Creating new credentials if none exist
    - Saving credentials for future use
    
    Returns:
        googleapiclient.discovery.Resource: Authenticated Gmail API service
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists(TOKEN_PATH):
        logger.info(f"Loading existing credentials from {TOKEN_PATH}")
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        # Detect scope mismatch and trigger re-auth if required scopes are missing
        if creds and creds.valid and hasattr(creds, 'scopes') and creds.scopes:
            required = set(SCOPES)
            current = set(creds.scopes)
            if not required.issubset(current):
                logger.warning("Scope upgrade required. Re-authenticating...")
                os.remove(TOKEN_PATH)
                creds = None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            creds.refresh(Request())
        else:
            logger.info(f"Initiating OAuth flow with credentials from {CREDENTIALS_PATH}")
            
            # Check if credentials file exists
            if not os.path.exists(CREDENTIALS_PATH):
                logger.error(f"Credentials file not found at {CREDENTIALS_PATH}")
                raise FileNotFoundError(f"Credentials file not found at {CREDENTIALS_PATH}. "
                                      f"Please download OAuth 2.0 Client ID JSON from Google Cloud Console.")
                
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        logger.info(f"Saving credentials to {TOKEN_PATH}")
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    
    # Build and return the Gmail service
    logger.info("Successfully authenticated with Gmail API")
    service = build('gmail', 'v1', credentials=creds)
    return service


def get_gmail_profile(service) -> dict:
    """
    Get Gmail profile info including email address and mailbox stats.

    Args:
        service: Authenticated Gmail API service

    Returns:
        dict: Profile data with emailAddress, messagesTotal, threadsTotal
    """
    return service.users().getProfile(userId='me').execute()


def check_auth_status():
    """
    Check the status of Gmail API authentication.
    
    Returns:
        dict: Authentication status information
    """
    status = {
        "authenticated": False,
        "credentials_file_exists": os.path.exists(CREDENTIALS_PATH),
        "token_file_exists": os.path.exists(TOKEN_PATH),
        "credentials_path": CREDENTIALS_PATH,
        "token_path": TOKEN_PATH
    }
    
    if status["token_file_exists"]:
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            status["authenticated"] = creds.valid
            status["expired"] = creds.expired if hasattr(creds, 'expired') else False
            status["has_refresh_token"] = bool(creds.refresh_token) if hasattr(creds, 'refresh_token') else False
            
        except Exception as e:
            logger.error(f"Error checking token file: {e}")
            status["error"] = str(e)
    
    return status
