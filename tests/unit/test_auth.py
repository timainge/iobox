"""
Unit tests for the authentication module.

This module tests the core functionality of the auth.py module which is responsible
for OAuth 2.0 authentication with the Gmail API.
"""

import json
from unittest.mock import MagicMock, patch

from iobox.auth import SCOPES, check_auth_status, get_gmail_profile, get_gmail_service


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

    def test_check_auth_status_with_files(
        self, monkeypatch, mock_credentials_file, mock_token_file
    ):
        """Test auth status when credential files exist."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))

        # Mock the Credentials.from_authorized_user_file to avoid actual API calls
        with patch("iobox.auth.Credentials.from_authorized_user_file") as mock_creds:
            # Configure the mock credential to be valid
            mock_creds.return_value = MagicMock(
                valid=True, expired=False, refresh_token="mock-refresh-token"
            )

            status = check_auth_status()

            assert status["authenticated"] is True
            assert status["credentials_file_exists"] is True
            assert status["token_file_exists"] is True
            assert status["expired"] is False
            assert status["has_refresh_token"] is True

    def test_check_auth_status_expired_token(
        self, monkeypatch, mock_credentials_file, mock_token_file
    ):
        """Test auth status with expired token."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))

        # Mock the Credentials.from_authorized_user_file to simulate expired token
        with patch("iobox.auth.Credentials.from_authorized_user_file") as mock_creds:
            mock_creds.return_value = MagicMock(
                valid=False, expired=True, refresh_token="mock-refresh-token"
            )

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

        with (
            patch("iobox.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow),
            patch("iobox.auth.build", return_value=mock_service),
        ):
            service = get_gmail_service()

            # Verify flow was created with the right parameters
            assert service == mock_service

            # Verify token was saved
            assert token_path.exists()

    def test_get_gmail_service_refresh_token(
        self, monkeypatch, mock_credentials_file, mock_token_file
    ):
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

        with (
            patch("iobox.auth.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("iobox.auth.build", return_value=mock_service),
            patch("builtins.open", mock_open_obj),
        ):
            service = get_gmail_service()

            # Just verify refresh was called (we can't easily mock the Request instance)
            assert mock_creds.refresh.called

            # Verify credentials became valid after refresh
            assert mock_creds.valid is True
            assert mock_creds.expired is False

            # Verify token was saved
            mock_open_obj.assert_called_once_with(str(mock_token_file), "w")
            mock_file_handle.write.assert_called_once_with(token_json)
            assert service == mock_service

    def test_get_gmail_service_valid_token(
        self, monkeypatch, mock_credentials_file, mock_token_file
    ):
        """Test using an existing valid token."""
        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(mock_token_file))

        # Mock the credentials with a valid token and matching scopes
        mock_creds = MagicMock(valid=True, expired=False)
        mock_creds.scopes = set(SCOPES)  # Must match current SCOPES to avoid mismatch re-auth

        # Mock build service
        mock_service = MagicMock()

        with (
            patch("iobox.auth.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("iobox.auth.build", return_value=mock_service),
        ):
            service = get_gmail_service()

            # Verify refresh was not called (token is valid)
            mock_creds.refresh.assert_not_called()
            assert service == mock_service


class TestGetGmailProfile:
    """Tests for get_gmail_profile()."""

    def test_get_gmail_profile(self, mock_gmail_service):
        """get_gmail_profile returns the profile dict from the API."""
        profile_data = {
            "emailAddress": "user@gmail.com",
            "messagesTotal": 66327,
            "threadsTotal": 13902,
        }
        mock_get = MagicMock()
        mock_get.execute.return_value = profile_data
        mock_gmail_service.users().getProfile.return_value = mock_get

        result = get_gmail_profile(mock_gmail_service)

        assert result["emailAddress"] == "user@gmail.com"
        assert result["messagesTotal"] == 66327
        assert result["threadsTotal"] == 13902
        mock_gmail_service.users().getProfile.assert_called_once_with(userId="me")


class TestScopeMismatch:
    """Tests for scope mismatch detection in get_gmail_service()."""

    def test_scope_mismatch_triggers_reauth(self, monkeypatch, mock_credentials_file, tmp_path):
        """If token has old scopes, token file is deleted and re-auth is triggered."""
        token_path = tmp_path / "token.json"
        # Write a dummy token file so os.path.exists returns True
        token_path.write_text('{"token": "old"}')

        monkeypatch.setattr("iobox.auth.CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr("iobox.auth.TOKEN_PATH", str(token_path))

        # Credentials with old (mismatched) scopes
        old_scopes = {"https://www.googleapis.com/auth/gmail.readonly"}
        mock_creds = MagicMock(
            valid=True,
            expired=False,
            scopes=old_scopes,
        )

        # After deletion, re-auth via OAuth flow
        mock_flow = MagicMock()
        new_creds = MagicMock(valid=True, to_json=lambda: '{"token": "new"}')
        mock_flow.run_local_server.return_value = new_creds

        mock_service = MagicMock()

        with (
            patch("iobox.auth.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("iobox.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow),
            patch("iobox.auth.build", return_value=mock_service),
        ):
            service = get_gmail_service()

            # Token file should have been deleted during scope mismatch detection
            # (then re-created by the OAuth flow write)
            assert service == mock_service
            # The flow was invoked because old creds were discarded
            mock_flow.run_local_server.assert_called_once()
