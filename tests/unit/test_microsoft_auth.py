"""
Unit tests for MicrosoftAuth and get_microsoft_scopes.

Covers token path namespacing, scope aggregation, account caching, and the
legacy token migration helper — all without triggering a real OAuth flow.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.o365.auth import MicrosoftAuth, get_microsoft_scopes

# HAS_O365 is False in CI (O365 not installed). Tests that construct MicrosoftAuth
# patch it to True so the __init__ guard doesn't block them.
_MODULE = "iobox.providers.o365.auth"


def _make_auth(
    tmp_path: Path, account: str = "user@example.com", **kwargs: object
) -> MicrosoftAuth:
    """Construct MicrosoftAuth with HAS_O365 patched to True."""
    with patch(f"{_MODULE}.HAS_O365", True):
        return MicrosoftAuth(
            account=account,
            credentials_dir=str(tmp_path),
            client_id="fake-client-id",
            **kwargs,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# get_microsoft_scopes
# ---------------------------------------------------------------------------


class TestGetMicrosoftScopes:
    def test_messages_readonly(self):
        scopes = get_microsoft_scopes(["email"], "readonly")
        assert "Mail.Read" in scopes
        assert "Mail.ReadWrite" not in scopes
        assert "Mail.Send" not in scopes

    def test_messages_standard(self):
        scopes = get_microsoft_scopes(["email"], "standard")
        assert "Mail.ReadWrite" in scopes
        assert "Mail.Send" in scopes
        assert "Mail.Read" not in scopes

    def test_calendar_readonly(self):
        scopes = get_microsoft_scopes(["calendar"], "readonly")
        assert "Calendars.Read" in scopes
        assert "Calendars.ReadWrite" not in scopes

    def test_calendar_standard(self):
        scopes = get_microsoft_scopes(["calendar"], "standard")
        assert "Calendars.ReadWrite" in scopes

    def test_drive_readonly(self):
        scopes = get_microsoft_scopes(["drive"], "readonly")
        assert "Files.Read.All" in scopes
        assert "Files.ReadWrite.All" not in scopes

    def test_drive_standard(self):
        scopes = get_microsoft_scopes(["drive"], "standard")
        assert "Files.ReadWrite.All" in scopes

    def test_all_services_readonly(self):
        scopes = get_microsoft_scopes(["email", "calendar", "drive"], "readonly")
        assert "Mail.Read" in scopes
        assert "Calendars.Read" in scopes
        assert "Files.Read.All" in scopes
        # basic should always be present
        assert "basic" in scopes

    def test_all_services_standard(self):
        scopes = get_microsoft_scopes(["email", "calendar", "drive"], "standard")
        assert "Mail.ReadWrite" in scopes
        assert "Calendars.ReadWrite" in scopes
        assert "Files.ReadWrite.All" in scopes

    def test_empty_services(self):
        scopes = get_microsoft_scopes([], "readonly")
        assert scopes == ["basic"]

    def test_no_duplicates(self):
        scopes = get_microsoft_scopes(["email", "email"], "readonly")
        assert scopes.count("Mail.Read") == 1


# ---------------------------------------------------------------------------
# MicrosoftAuth token path
# ---------------------------------------------------------------------------


class TestMicrosoftAuthTokenPath:
    def test_token_dir_is_account_namespaced(self, tmp_path: Path):
        auth = _make_auth(tmp_path, account="corp@example.com")
        assert auth.token_dir == tmp_path / "tokens" / "corp@example.com"

    def test_token_file_path(self, tmp_path: Path):
        auth = _make_auth(tmp_path, account="user@example.com")
        assert auth.token_file == tmp_path / "tokens" / "user@example.com" / "microsoft_token.txt"

    def test_token_dir_created_on_access(self, tmp_path: Path):
        auth = _make_auth(tmp_path, account="new@example.com")
        _ = auth.token_dir  # access triggers mkdir
        assert (tmp_path / "tokens" / "new@example.com").is_dir()

    def test_default_credentials_dir_is_iobox_home(self):
        with patch(f"{_MODULE}.HAS_O365", True):
            auth = MicrosoftAuth(account="user@example.com", client_id="fake")
        assert auth.token_dir.parts[-3] == ".iobox"


# ---------------------------------------------------------------------------
# MicrosoftAuth.get_account
# ---------------------------------------------------------------------------


class TestMicrosoftAuthGetAccount:
    def _build_auth(self, tmp_path: Path, **kwargs: object) -> MicrosoftAuth:
        return _make_auth(tmp_path, account="corp@example.com", **kwargs)

    def test_raises_without_client_id(self, tmp_path: Path):
        with patch(f"{_MODULE}.HAS_O365", True):
            auth = MicrosoftAuth(
                account="user@example.com",
                credentials_dir=str(tmp_path),
                client_id="",
            )
        with pytest.raises(ValueError, match="OUTLOOK_CLIENT_ID"):
            auth.get_account()

    def test_get_account_authenticates_when_needed(self, tmp_path: Path):
        mock_account = MagicMock()
        mock_account.is_authenticated = False
        mock_account.authenticate.return_value = True

        auth = self._build_auth(tmp_path)

        with (
            patch(f"{_MODULE}.HAS_O365", True),
            patch(f"{_MODULE}.Account", return_value=mock_account),
            patch(f"{_MODULE}.FileSystemTokenBackend"),
        ):
            result = auth.get_account()

        assert result is mock_account
        mock_account.authenticate.assert_called_once_with(scopes=auth.scopes)

    def test_get_account_skips_auth_when_already_authenticated(self, tmp_path: Path):
        mock_account = MagicMock()
        mock_account.is_authenticated = True

        auth = self._build_auth(tmp_path)

        with (
            patch(f"{_MODULE}.HAS_O365", True),
            patch(f"{_MODULE}.Account", return_value=mock_account),
            patch(f"{_MODULE}.FileSystemTokenBackend"),
        ):
            result = auth.get_account()

        assert result is mock_account
        mock_account.authenticate.assert_not_called()

    def test_get_account_cached_after_first_call(self, tmp_path: Path):
        mock_account = MagicMock()
        mock_account.is_authenticated = True

        auth = self._build_auth(tmp_path)

        with (
            patch(f"{_MODULE}.HAS_O365", True),
            patch(f"{_MODULE}.Account", return_value=mock_account) as mock_cls,
            patch(f"{_MODULE}.FileSystemTokenBackend"),
        ):
            r1 = auth.get_account()
            r2 = auth.get_account()

        assert r1 is r2
        assert mock_cls.call_count == 1

    def test_raises_when_oauth_fails(self, tmp_path: Path):
        mock_account = MagicMock()
        mock_account.is_authenticated = False
        mock_account.authenticate.return_value = False  # failure

        auth = self._build_auth(tmp_path)

        with (
            patch(f"{_MODULE}.HAS_O365", True),
            patch(f"{_MODULE}.Account", return_value=mock_account),
            patch(f"{_MODULE}.FileSystemTokenBackend"),
            pytest.raises(RuntimeError, match="authentication failed"),
        ):
            auth.get_account()


# ---------------------------------------------------------------------------
# Token migration
# ---------------------------------------------------------------------------


class TestMicrosoftAuthMigration:
    def test_migrates_legacy_token_on_first_use(self, tmp_path: Path):
        legacy_dir = tmp_path / "tokens" / "outlook"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "o365_token.txt").write_text("old-token")

        mock_account = MagicMock()
        mock_account.is_authenticated = True

        auth = _make_auth(tmp_path, account="user@example.com")

        with (
            patch(f"{_MODULE}.HAS_O365", True),
            patch(f"{_MODULE}.Account", return_value=mock_account),
            patch(f"{_MODULE}.FileSystemTokenBackend"),
        ):
            auth.get_account()

        new_token = tmp_path / "tokens" / "user@example.com" / "microsoft_token.txt"
        assert new_token.exists()
        assert new_token.read_text() == "old-token"

    def test_does_not_overwrite_existing_new_token(self, tmp_path: Path):
        legacy_dir = tmp_path / "tokens" / "outlook"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "o365_token.txt").write_text("old-token")

        new_dir = tmp_path / "tokens" / "user@example.com"
        new_dir.mkdir(parents=True)
        new_token = new_dir / "microsoft_token.txt"
        new_token.write_text("new-token")

        mock_account = MagicMock()
        mock_account.is_authenticated = True

        auth = _make_auth(tmp_path, account="user@example.com")

        with (
            patch(f"{_MODULE}.HAS_O365", True),
            patch(f"{_MODULE}.Account", return_value=mock_account),
            patch(f"{_MODULE}.FileSystemTokenBackend"),
        ):
            auth.get_account()

        assert new_token.read_text() == "new-token"  # not overwritten
