"""
Unit tests for `iobox space` command group.

All tests use typer.testing.CliRunner and monkeypatch path constants in
iobox.space_config so that no real ~/.iobox/ directories are touched.
OAuth calls are mocked — no real tokens are created.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from iobox.cli import _resolve_slot, app

runner = CliRunner()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all space_config path constants to tmp_path so tests don't
    touch the real ~/.iobox directory."""
    iobox_home = tmp_path / ".iobox"
    workspaces_dir = iobox_home / "workspaces"
    tokens_dir = iobox_home / "tokens"
    indexes_dir = iobox_home / "indexes"
    active_space_file = iobox_home / "active_space"

    monkeypatch.setattr("iobox.space_config.IOBOX_HOME", iobox_home)
    monkeypatch.setattr("iobox.space_config.WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr("iobox.space_config.TOKENS_DIR", tokens_dir)
    monkeypatch.setattr("iobox.space_config.INDEXES_DIR", indexes_dir)
    monkeypatch.setattr("iobox.space_config.ACTIVE_SPACE_FILE", active_space_file)


@pytest.fixture
def mock_google_auth() -> Any:
    """Return a patcher that makes GoogleAuth.get_credentials() a no-op."""
    with patch("iobox.cli._authenticate_service_entry") as mock:
        mock.return_value = None
        yield mock


def _invoke(*args: str) -> Any:
    """Invoke the CLI with a mocked provider to avoid real provider init."""
    with patch("iobox.cli.get_provider") as mock_prov:
        mock_prov.return_value = MagicMock()
        return runner.invoke(app, list(args))


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceCreate
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceCreate:
    def test_create_new_space(self) -> None:
        result = _invoke("space", "create", "personal")
        assert result.exit_code == 0
        assert "personal" in result.output

    def test_create_sets_active_when_first(self) -> None:
        result = _invoke("space", "create", "personal")
        assert result.exit_code == 0
        assert "active" in result.output.lower() or "set" in result.output.lower()

        from iobox.space_config import get_active_space

        assert get_active_space() == "personal"

    def test_create_does_not_overwrite_active_when_exists(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "create", "work")
        assert result.exit_code == 0

        from iobox.space_config import get_active_space

        # Active should still be "personal", not "work"
        assert get_active_space() == "personal"

    def test_create_duplicate_fails(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "create", "personal")
        assert result.exit_code != 0

    def test_create_writes_toml(self) -> None:
        _invoke("space", "create", "myspace")

        from iobox.space_config import WORKSPACES_DIR

        assert (WORKSPACES_DIR / "myspace.toml").exists()


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceList
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceList:
    def test_list_empty(self) -> None:
        result = _invoke("space", "list")
        assert result.exit_code == 0
        assert "No spaces" in result.output

    def test_list_shows_spaces(self) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "create", "work")
        result = _invoke("space", "list")
        assert result.exit_code == 0
        assert "personal" in result.output
        assert "work" in result.output

    def test_list_marks_active(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "list")
        assert result.exit_code == 0
        assert "active" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceUse
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceUse:
    def test_use_existing_space(self) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "create", "work")
        result = _invoke("space", "use", "work")
        assert result.exit_code == 0
        assert "work" in result.output

        from iobox.space_config import get_active_space

        assert get_active_space() == "work"

    def test_use_nonexistent_fails(self) -> None:
        result = _invoke("space", "use", "nonexistent")
        assert result.exit_code != 0

    def test_use_shows_available_on_error(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "use", "nonexistent")
        assert "personal" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceStatus
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceStatus:
    def test_status_no_active_space(self) -> None:
        result = _invoke("space", "status")
        assert result.exit_code == 0
        assert "No active space" in result.output

    def test_status_empty_space(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "status")
        assert result.exit_code == 0
        # Rich table should mention the space name
        assert "personal" in result.output

    def test_status_shows_service_session(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke(
            "space",
            "add",
            "google",
            "tim@gmail.com",
            "--email",
            "--calendar",
            "--read",
        )
        result = _invoke("space", "status")
        assert result.exit_code == 0
        assert "google" in result.output
        assert "tim@gmail.com" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceAdd
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceAdd:
    def test_add_gmail_messages_only(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "add", "google", "tim@gmail.com", "--email")
        assert result.exit_code == 0
        assert "authenticated" in result.output
        mock_google_auth.assert_called_once()

    def test_add_gmail_with_calendar_and_drive(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        result = _invoke(
            "space",
            "add",
            "google",
            "tim@gmail.com",
            "--email",
            "--calendar",
            "--drive",
        )
        assert result.exit_code == 0
        assert "calendar" in result.output
        assert "drive" in result.output

    def test_add_outlook_messages_only(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "add", "o365", "corp@company.com", "--email")
        assert result.exit_code == 0
        assert "authenticated" in result.output

    def test_add_outlook_with_drive_fails(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke(
            "space",
            "add",
            "o365",
            "corp@company.com",
            "--email",
            "--drive",
        )
        assert result.exit_code != 0
        assert "Drive" in result.output

    def test_add_no_scopes_fails(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "add", "google", "tim@gmail.com")
        assert result.exit_code != 0
        assert "scope" in result.output.lower()

    def test_add_unknown_service_fails(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "add", "yahoo", "tim@yahoo.com", "--email")
        assert result.exit_code != 0

    def test_add_without_active_space_fails(self) -> None:
        result = _invoke("space", "add", "google", "tim@gmail.com", "--email")
        assert result.exit_code != 0

    def test_add_saves_slot_to_toml(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")

        from iobox.space_config import load_space

        config = load_space("personal")
        assert len(config.services) == 1
        assert config.services[0].service == "google"
        assert config.services[0].account == "tim@gmail.com"

    def test_add_readonly_mode(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email", "--read")

        from iobox.space_config import load_space

        config = load_space("personal")
        assert config.services[0].mode == "readonly"

    def test_add_standard_mode_by_default(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")

        from iobox.space_config import load_space

        config = load_space("personal")
        assert config.services[0].mode == "standard"

    def test_add_assigns_incrementing_numbers(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")
        _invoke("space", "add", "google", "work@company.com", "--email")

        from iobox.space_config import load_space

        config = load_space("personal")
        assert config.services[0].number == 1
        assert config.services[1].number == 2

    def test_add_auth_failure_does_not_save(self) -> None:
        _invoke("space", "create", "personal")
        with patch("iobox.cli._authenticate_service_entry", side_effect=Exception("auth error")):
            result = _invoke("space", "add", "google", "tim@gmail.com", "--email")

        assert result.exit_code != 0

        from iobox.space_config import load_space

        config = load_space("personal")
        assert len(config.services) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceLogin
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceLogin:
    def test_login_by_number(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")
        mock_google_auth.reset_mock()

        result = _invoke("space", "login", "1")
        assert result.exit_code == 0
        assert "Authenticated" in result.output
        mock_google_auth.assert_called_once()

    def test_login_by_slug(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")
        mock_google_auth.reset_mock()

        result = _invoke("space", "login", "tim-gmail")
        assert result.exit_code == 0
        mock_google_auth.assert_called_once()

    def test_login_nonexistent_fails(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "login", "99")
        assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceLogout
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceLogout:
    def test_logout_deletes_token(self, tmp_path: Path, mock_google_auth: Any) -> None:
        import iobox.space_config as sc

        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")

        # Create a fake token file
        token_dir = sc.IOBOX_HOME / "tokens" / "tim@gmail.com"
        token_dir.mkdir(parents=True, exist_ok=True)
        token_file = token_dir / "token_standard.json"
        token_file.write_text("{}")

        result = _invoke("space", "logout", "1")
        assert result.exit_code == 0
        assert not token_file.exists()

    def test_logout_no_token_is_graceful(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")
        result = _invoke("space", "logout", "1")
        assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# TestSpaceRemove
# ─────────────────────────────────────────────────────────────────────────────


class TestSpaceRemove:
    def test_remove_by_number_with_yes(self, mock_google_auth: Any) -> None:
        _invoke("space", "create", "personal")
        _invoke("space", "add", "google", "tim@gmail.com", "--email")

        result = _invoke("space", "remove", "1", "--yes")
        assert result.exit_code == 0
        assert "Removed" in result.output

        from iobox.space_config import load_space

        config = load_space("personal")
        assert len(config.services) == 0

    def test_remove_nonexistent_fails(self) -> None:
        _invoke("space", "create", "personal")
        result = _invoke("space", "remove", "99", "--yes")
        assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# TestSlotResolution
# ─────────────────────────────────────────────────────────────────────────────


class TestSlotResolution:
    def _make_config(self) -> Any:
        from iobox.space_config import ServiceEntry, SpaceConfig

        return SpaceConfig(
            name="test",
            services=[
                ServiceEntry(
                    number=1,
                    service="google",
                    account="tim@gmail.com",
                    scopes=["email"],
                ),
                ServiceEntry(
                    number=2,
                    service="o365",
                    account="corp@company.com",
                    scopes=["email"],
                ),
            ],
        )

    def test_resolve_by_number(self) -> None:
        config = self._make_config()
        entry = _resolve_slot(config, "1")
        assert entry.number == 1

    def test_resolve_by_id(self) -> None:
        config = self._make_config()
        entry = _resolve_slot(config, "google-timgmailcom")
        assert entry.service == "google"

    def test_resolve_by_slug(self) -> None:
        config = self._make_config()
        entry = _resolve_slot(config, "tim-gmail")
        assert entry.account == "tim@gmail.com"

    def test_resolve_missing_number_raises(self) -> None:
        import typer as _typer

        config = self._make_config()
        with pytest.raises(_typer.Exit):
            _resolve_slot(config, "99")

    def test_resolve_missing_name_raises(self) -> None:
        import typer as _typer

        config = self._make_config()
        with pytest.raises(_typer.Exit):
            _resolve_slot(config, "nonexistent-slug")


# ─────────────────────────────────────────────────────────────────────────────
# TestAuthStatusDeprecation
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthStatusDeprecation:
    def test_auth_status_shows_deprecation_note(self) -> None:
        with (
            patch("iobox.cli.get_provider") as mock_prov,
            patch(
                "iobox.providers.google.auth.check_auth_status",
                return_value={
                    "authenticated": False,
                    "credentials_file_exists": False,
                    "token_file_exists": False,
                    "credentials_path": "/tmp/creds.json",
                    "token_path": "/tmp/token.json",
                },
            ),
            patch("iobox.providers.google.auth.get_gmail_service", side_effect=Exception("no auth")),
        ):
            mock_prov.return_value = MagicMock()
            result = runner.invoke(app, ["auth-status"])
        assert "deprecated" in result.output.lower()
        assert "space status" in result.output
