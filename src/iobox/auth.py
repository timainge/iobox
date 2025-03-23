"""
Authentication Module for Gmail API access.

This module handles the OAuth 2.0 authentication flow for the Gmail API.
"""

import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# If modifying these scopes, delete the token.json file.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


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
    from googleapiclient.discovery import build
    
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    # Build and return the Gmail service
    service = build('gmail', 'v1', credentials=creds)
    return service
