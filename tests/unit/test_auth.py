"""
Unit tests for the authentication module.

This module tests the core functionality of the auth.py module which is responsible
for OAuth 2.0 authentication with the Gmail API, including multi-profile token storage.
"""

import json
import os
from unittest.mock import MagicMock, patch

from iobox.accounts import set_active_account
from iobox.modes import AccessMode
from iobox.providers.google.auth import (
    SCOPES,
    _resolve_token,
    _scope_tier_for_mode,
    check_auth_status,
    get_active_scopes,
    get_gmail_profile,
    get_gmail_service,
    set_active_mode,
)

_GA = "iobox.providers.google.auth"


class TestAuthentication:
    """Test cases for the authentication module."""

    def test_check_auth_status_no_files(self, monkeypatch, tmp_path):
        """Test auth status when no credential files exist."""
        nonexistent_creds = tmp_path / "nonexistent_creds.json"

        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(nonexistent_creds))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        # Use custom token file to trigger legacy path
        monkeypatch.setenv("GMAIL_TOKEN_FILE", "nonexistent.json")
        monkeypatch.setattr(_GA + ".TOKEN_PATH", str(tmp_path / "nonexistent.json"))

        status = check_auth_status()

        assert status["authenticated"] is False
        assert status["credentials_file_exists"] is False
        assert status["token_file_exists"] is False

    def test_check_auth_status_with_files(
        self, monkeypatch, mock_credentials_file, mock_token_file
    ):
        """Test auth status when credential files exist (legacy mode)."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".TOKEN_PATH", str(mock_token_file))
        # Force legacy path
        monkeypatch.setenv("GMAIL_TOKEN_FILE", "custom.json")

        with patch(_GA + ".Credentials.from_authorized_user_file") as mock_creds:
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
        """Test auth status with expired token (legacy mode)."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".TOKEN_PATH", str(mock_token_file))
        monkeypatch.setenv("GMAIL_TOKEN_FILE", "custom.json")

        with patch(_GA + ".Credentials.from_authorized_user_file") as mock_creds:
            mock_creds.return_value = MagicMock(
                valid=False, expired=True, refresh_token="mock-refresh-token"
            )

            status = check_auth_status()

            assert status["authenticated"] is False
            assert status["expired"] is True
            assert status["has_refresh_token"] is True

    def test_get_gmail_service_new_credentials(self, monkeypatch, mock_credentials_file, tmp_path):
        """Test creating new credentials when none exist (multi-profile)."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        mock_flow = MagicMock()
        mock_creds = MagicMock(valid=True, to_json=lambda: json.dumps({"token": "new-token"}))
        mock_flow.run_local_server.return_value = mock_creds
        mock_service = MagicMock()

        with (
            patch(_GA + ".InstalledAppFlow.from_client_secrets_file", return_value=mock_flow),
            patch(_GA + ".build", return_value=mock_service),
        ):
            service = get_gmail_service()

            assert service == mock_service

            # Verify token was saved in multi-profile location
            expected_path = os.path.join(str(tmp_path), "tokens", "default", "token_standard.json")
            assert os.path.exists(expected_path)

    def test_get_gmail_service_refresh_token(self, monkeypatch, mock_credentials_file, tmp_path):
        """Test refreshing an expired token (multi-profile)."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        # Create a token file in multi-profile location
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        token_file = token_dir / "token_standard.json"
        token_file.write_text('{"token": "old"}')

        mock_creds = MagicMock(valid=False, expired=True, refresh_token="mock-refresh-token")
        token_json = '{"token": "refreshed-token", "refresh_token": "refresh-token"}'
        mock_creds.to_json.return_value = token_json

        def refresh_side_effect(request):
            mock_creds.valid = True
            mock_creds.expired = False

        mock_creds.refresh.side_effect = refresh_side_effect
        mock_service = MagicMock()

        with (
            patch(_GA + ".Credentials.from_authorized_user_file", return_value=mock_creds),
            patch(_GA + ".build", return_value=mock_service),
        ):
            service = get_gmail_service()

            assert mock_creds.refresh.called
            assert mock_creds.valid is True
            assert service == mock_service

    def test_get_gmail_service_valid_token(self, monkeypatch, mock_credentials_file, tmp_path):
        """Test using an existing valid token (multi-profile)."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        # Create token file
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text('{"token": "valid"}')

        mock_creds = MagicMock(valid=True, expired=False)
        mock_creds.scopes = set(SCOPES)
        mock_service = MagicMock()

        with (
            patch(_GA + ".Credentials.from_authorized_user_file", return_value=mock_creds),
            patch(_GA + ".build", return_value=mock_service),
        ):
            service = get_gmail_service()
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

    def test_scope_mismatch_triggers_reauth_no_delete(
        self, monkeypatch, mock_credentials_file, tmp_path
    ):
        """If token has old scopes, a new token file is created (old one is NOT deleted)."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        # Create a readonly token in multi-profile location
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        readonly_token = token_dir / "token_readonly.json"
        readonly_token.write_text('{"token": "readonly"}')

        # No standard token exists, so _resolve_token returns None for load_path
        # This triggers OAuth flow without touching the readonly token

        mock_flow = MagicMock()
        new_creds = MagicMock(valid=True, to_json=lambda: '{"token": "new-standard"}')
        mock_flow.run_local_server.return_value = new_creds
        mock_service = MagicMock()

        with (
            patch(_GA + ".InstalledAppFlow.from_client_secrets_file", return_value=mock_flow),
            patch(_GA + ".build", return_value=mock_service),
        ):
            service = get_gmail_service()

            assert service == mock_service
            mock_flow.run_local_server.assert_called_once()
            # The readonly token should still exist
            assert readonly_token.exists()
            # The new standard token should be created
            assert (token_dir / "token_standard.json").exists()

    def test_scope_upgrade_keeps_old_token(self, monkeypatch, mock_credentials_file, tmp_path):
        """Upgrading from readonly to standard never deletes the readonly token."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_account("default")

        # Set up readonly token
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        readonly_token = token_dir / "token_readonly.json"
        readonly_token.write_text('{"token": "ro-token"}')

        # First use readonly mode — should find the readonly token
        set_active_mode(AccessMode.readonly)
        load_path, save_path = _resolve_token("default", AccessMode.readonly)
        assert load_path == str(readonly_token)

        # Now switch to standard — readonly token can't serve, no standard token exists
        set_active_mode(AccessMode.standard)
        load_path, save_path = _resolve_token("default", AccessMode.standard)
        assert load_path is None
        assert save_path == str(token_dir / "token_standard.json")

        # After OAuth flow creates standard token, readonly should still be there
        assert readonly_token.exists()

    def test_modify_token_accepted_in_readonly_mode(
        self, monkeypatch, mock_credentials_file, tmp_path
    ):
        """A token with gmail.modify scopes should be accepted in readonly mode."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(mock_credentials_file))
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.readonly)
        set_active_account("default")

        # Create a standard token (broader scopes)
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text('{"token": "standard"}')

        mock_creds = MagicMock(valid=True, expired=False)
        mock_creds.scopes = {
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.compose",
        }
        mock_service = MagicMock()

        with (
            patch(_GA + ".Credentials.from_authorized_user_file", return_value=mock_creds),
            patch(_GA + ".build", return_value=mock_service),
        ):
            service = get_gmail_service()
            mock_creds.refresh.assert_not_called()
            assert service == mock_service


class TestGetActiveScopes:
    """Tests for get_active_scopes()."""

    def test_readonly_scopes(self):
        set_active_mode(AccessMode.readonly)
        scopes = get_active_scopes()
        assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
        assert "https://www.googleapis.com/auth/gmail.modify" not in scopes

    def test_standard_scopes(self):
        set_active_mode(AccessMode.standard)
        scopes = get_active_scopes()
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
        assert "https://www.googleapis.com/auth/gmail.compose" in scopes


class TestTokenResolution:
    """Tests for _resolve_token with various file layouts."""

    def test_exact_match_readonly(self, tmp_path, monkeypatch):
        """Exact match: readonly mode finds token_readonly.json."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_readonly.json").write_text("{}")

        load_path, save_path = _resolve_token("default", AccessMode.readonly)
        assert load_path == str(token_dir / "token_readonly.json")
        assert save_path == str(token_dir / "token_readonly.json")

    def test_exact_match_standard(self, tmp_path, monkeypatch):
        """Exact match: standard mode finds token_standard.json."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text("{}")

        load_path, save_path = _resolve_token("default", AccessMode.standard)
        assert load_path == str(token_dir / "token_standard.json")

    def test_readonly_falls_back_to_standard(self, tmp_path, monkeypatch):
        """Readonly mode falls back to standard token when no readonly token exists."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text("{}")

        load_path, save_path = _resolve_token("default", AccessMode.readonly)
        assert load_path == str(token_dir / "token_standard.json")
        # save_path should still point to the readonly tier
        assert save_path == str(token_dir / "token_readonly.json")

    def test_no_tokens_returns_none(self, tmp_path, monkeypatch):
        """No tokens at all returns None for load_path."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))

        load_path, save_path = _resolve_token("default", AccessMode.standard)
        assert load_path is None
        assert "token_standard.json" in save_path

    def test_standard_does_not_fall_back_to_readonly(self, tmp_path, monkeypatch):
        """Standard mode does NOT fall back to readonly token."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_readonly.json").write_text("{}")

        load_path, save_path = _resolve_token("default", AccessMode.standard)
        assert load_path is None

    def test_dangerous_uses_standard_tier(self, tmp_path, monkeypatch):
        """Dangerous mode maps to the standard scope tier."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text("{}")

        load_path, save_path = _resolve_token("default", AccessMode.dangerous)
        assert load_path == str(token_dir / "token_standard.json")

    def test_different_account(self, tmp_path, monkeypatch):
        """Tokens are namespaced per account."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))

        # Create token for 'work' account only
        work_dir = tmp_path / "tokens" / "work"
        work_dir.mkdir(parents=True)
        (work_dir / "token_standard.json").write_text("{}")

        # 'work' account should find it
        load_path, _ = _resolve_token("work", AccessMode.standard)
        assert load_path is not None

        # 'default' account should not find it
        load_path, _ = _resolve_token("default", AccessMode.standard)
        assert load_path is None


class TestScopeTier:
    """Tests for _scope_tier_for_mode."""

    def test_readonly_tier(self):
        assert _scope_tier_for_mode(AccessMode.readonly) == "readonly"

    def test_standard_tier(self):
        assert _scope_tier_for_mode(AccessMode.standard) == "standard"

    def test_dangerous_tier(self):
        assert _scope_tier_for_mode(AccessMode.dangerous) == "standard"


class TestLegacyMigration:
    """Tests for legacy token.json migration."""

    def test_migrates_legacy_token(self, monkeypatch, tmp_path):
        """Legacy token.json is copied to tokens/default/ on first use."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        # Create a legacy token with modify scopes
        legacy_token = tmp_path / "token.json"
        legacy_data = {
            "token": "legacy-token",
            "refresh_token": "legacy-refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test.apps.googleusercontent.com",
            "client_secret": "secret",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.compose",
            ],
        }
        legacy_token.write_text(json.dumps(legacy_data))

        # Mock credentials for the migration read
        mock_creds = MagicMock()
        mock_creds.scopes = legacy_data["scopes"]

        with patch(_GA + ".Credentials.from_authorized_user_file", return_value=mock_creds):
            from iobox.providers.google.auth import _maybe_migrate_legacy_token

            _maybe_migrate_legacy_token("default")

        # Should be migrated to token_standard.json
        migrated = tmp_path / "tokens" / "default" / "token_standard.json"
        assert migrated.exists()

        # Legacy file should NOT be deleted
        assert legacy_token.exists()

    def test_migrates_readonly_legacy_token(self, monkeypatch, tmp_path):
        """Legacy readonly token is migrated to token_readonly.json."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))

        legacy_token = tmp_path / "token.json"
        legacy_data = {
            "token": "readonly-token",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        legacy_token.write_text(json.dumps(legacy_data))

        mock_creds = MagicMock()
        mock_creds.scopes = legacy_data["scopes"]

        with patch(_GA + ".Credentials.from_authorized_user_file", return_value=mock_creds):
            from iobox.providers.google.auth import _maybe_migrate_legacy_token

            _maybe_migrate_legacy_token("default")

        migrated = tmp_path / "tokens" / "default" / "token_readonly.json"
        assert migrated.exists()

    def test_skips_migration_for_non_default_account(self, monkeypatch, tmp_path):
        """Migration only runs for the 'default' account."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))

        legacy_token = tmp_path / "token.json"
        legacy_token.write_text('{"token": "x"}')

        from iobox.providers.google.auth import _maybe_migrate_legacy_token

        _maybe_migrate_legacy_token("work")

        # No migration should have occurred
        assert not (tmp_path / "tokens" / "work").exists()

    def test_skips_migration_if_tokens_exist(self, monkeypatch, tmp_path):
        """Migration is skipped if token files already exist in the directory."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))

        legacy_token = tmp_path / "token.json"
        legacy_token.write_text('{"token": "old"}')

        # Pre-create token dir with existing token
        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text('{"token": "existing"}')

        from iobox.providers.google.auth import _maybe_migrate_legacy_token

        _maybe_migrate_legacy_token("default")

        # Existing token should be unchanged
        assert (token_dir / "token_standard.json").read_text() == '{"token": "existing"}'


class TestMultiProfileAuthStatus:
    """Tests for check_auth_status with multi-profile tokens."""

    def test_auth_status_finds_multiprofile_token(self, monkeypatch, tmp_path):
        """check_auth_status uses multi-profile token resolution."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)
        (tmp_path / "credentials.json").write_text("{}")

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        token_dir = tmp_path / "tokens" / "default"
        token_dir.mkdir(parents=True)
        (token_dir / "token_standard.json").write_text('{"token": "t"}')

        with patch(_GA + ".Credentials.from_authorized_user_file") as mock_creds:
            mock_creds.return_value = MagicMock(valid=True, expired=False, refresh_token="r")
            status = check_auth_status()

        assert status["authenticated"] is True
        assert status["token_file_exists"] is True
        assert "token_standard.json" in status["token_path"]

    def test_auth_status_no_token(self, monkeypatch, tmp_path):
        """check_auth_status reports no token when directory is empty."""
        monkeypatch.setattr(_GA + ".CREDENTIALS_DIR", str(tmp_path))
        monkeypatch.setattr(_GA + ".CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)

        set_active_mode(AccessMode.standard)
        set_active_account("default")

        status = check_auth_status()

        assert status["authenticated"] is False
        assert status["token_file_exists"] is False
