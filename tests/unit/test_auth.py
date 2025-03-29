"""
Unit tests for the authentication module.

This module tests the core functionality of the auth.py module which is responsible
for OAuth 2.0 authentication with the Gmail API.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from iobox.auth import get_gmail_service, check_auth_status, CREDENTIALS_PATH, TOKEN_PATH


class TestAuthentication:
    """Test cases for the authentication module."""
    
    def test_check_auth_status_no_files(self, monkeypatch, tmp_path):
        """Test auth status when no credential files exist."""
        # Set paths to nonexistent files
        nonexistent_creds = tmp_path / "nonexistent_creds.json"
        nonexistent_token = tmp_path / "nonexistent_token.json"
        
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(nonexistent_creds))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(nonexistent_token))
        
        status = check_auth_status()
        
        assert status["authenticated"] is False
        assert status["credentials_file_exists"] is False
        assert status["token_file_exists"] is False
    
    def test_check_auth_status_with_files(self, monkeypatch, mock_credentials_file, mock_token_file):
        """Test auth status when credential files exist."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))
        
        # Mock the Credentials.from_authorized_user_file to avoid actual API calls
        with patch("iobox.auth.Credentials.from_authorized_user_file") as mock_creds:
            # Configure the mock credential to be valid
            mock_creds.return_value = MagicMock(valid=True, expired=False, refresh_token="mock-refresh-token")
            
            status = check_auth_status()
            
            assert status["authenticated"] is True
            assert status["credentials_file_exists"] is True
            assert status["token_file_exists"] is True
            assert status["expired"] is False
            assert status["has_refresh_token"] is True
    
    def test_check_auth_status_expired_token(self, monkeypatch, mock_credentials_file, mock_token_file):
        """Test auth status with expired token."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))
        
        # Mock the Credentials.from_authorized_user_file to simulate expired token
        with patch("iobox.auth.Credentials.from_authorized_user_file") as mock_creds:
            mock_creds.return_value = MagicMock(valid=False, expired=True, refresh_token="mock-refresh-token")
            
            status = check_auth_status()
            
            assert status["authenticated"] is False
            assert status["expired"] is True
            assert status["has_refresh_token"] is True
    
    def test_get_gmail_service_new_credentials(self, monkeypatch, mock_credentials_file, tmp_path):
        """Test creating new credentials when none exist."""
        # Create a temporary token path
        token_path = tmp_path / "test_token.json"
        
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(token_path))
        
        # Mock the OAuth flow
        mock_flow = MagicMock()
        mock_creds = MagicMock(valid=True, to_json=lambda: json.dumps({"token": "new-token"}))
        mock_flow.run_local_server.return_value = mock_creds
        
        # Mock build service
        mock_service = MagicMock()
        
        with patch("iobox.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow), \
             patch("iobox.auth.build", return_value=mock_service):
            
            service = get_gmail_service()
            
            # Verify flow was created with the right parameters
            assert service == mock_service
            
            # Verify token was saved
            assert token_path.exists()
    
    def test_get_gmail_service_refresh_token(self, monkeypatch, mock_credentials_file, mock_token_file):
        """Test refreshing an expired token."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))
        
        # Mock the credentials with an expired token that needs refreshing
        mock_creds = MagicMock(valid=False, expired=True, refresh_token="mock-refresh-token")
        
        # Mock to_json to return a valid JSON string
        token_json = '{"token": "refreshed-token", "refresh_token": "refresh-token"}'
        mock_creds.to_json.return_value = token_json
        
        # After refreshing, the token becomes valid
        def refresh_side_effect(request):
            mock_creds.valid = True
            mock_creds.expired = False
        
        mock_creds.refresh.side_effect = refresh_side_effect
        
        # Mock build service
        mock_service = MagicMock()
        
        # Create a proper mock for file operations
        mock_open_obj = MagicMock()
        mock_file_handle = MagicMock()
        mock_open_obj.return_value.__enter__.return_value = mock_file_handle
        
        with patch("iobox.auth.Credentials.from_authorized_user_file", return_value=mock_creds), \
             patch("iobox.auth.build", return_value=mock_service), \
             patch("builtins.open", mock_open_obj):
            
            service = get_gmail_service()
            
            # Just verify refresh was called (we can't easily mock the Request instance)
            assert mock_creds.refresh.called
            
            # Verify credentials became valid after refresh
            assert mock_creds.valid is True
            assert mock_creds.expired is False
            
            # Verify token was saved
            mock_open_obj.assert_called_once_with(str(mock_token_file), 'w')
            mock_file_handle.write.assert_called_once_with(token_json)
            assert service == mock_service
    
    def test_get_gmail_service_valid_token(self, monkeypatch, mock_credentials_file, mock_token_file):
        """Test using an existing valid token."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))
        
        # Mock the credentials with a valid token
        mock_creds = MagicMock(valid=True, expired=False)
        
        # Mock build service
        mock_service = MagicMock()
        
        with patch("iobox.auth.Credentials.from_authorized_user_file", return_value=mock_creds), \
             patch("iobox.auth.build", return_value=mock_service):
            
            service = get_gmail_service()
            
            # Verify refresh was not called (token is valid)
            mock_creds.refresh.assert_not_called()
            assert service == mock_service
