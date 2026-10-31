"""
Unit tests for GoogleAuth and related scope helpers.

Tests cover:
- GoogleAuth token path derivation
- get_credentials() — load, refresh, new-flow paths
- get_service() — passes correct API name/version to build()
- modes.get_google_scopes() — scope aggregation
- modes._tier_for_mode() — tier mapping
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.google.auth import GoogleAuth

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_creds(tmp_path: Path) -> MagicMock:
    """Return a MagicMock that looks like a valid Credentials object."""
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "mock-refresh-token"
    creds.to_json.return_value = json.dumps({"token": "mock"})
    return creds


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    """Write a minimal fake token file and return its path."""
    token_path = tmp_path / "tokens" / "default" / "token_readonly.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps({"token": "existing"}))
    return token_path


@pytest.fixture
def creds_file(tmp_path: Path) -> Path:
    """Write a minimal fake credentials.json and return its path."""
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text(json.dumps({"installed": {"client_id": "x"}}))
    return creds_path


# ── TestGoogleAuth ─────────────────────────────────────────────────────────────


class TestGoogleAuth:
    def test_token_path_is_account_namespaced(self, tmp_path: Path) -> None:
        auth = GoogleAuth(
            account="tim@gmail.com",
            scopes=["scope1"],
            credentials_dir=str(tmp_path),
            tier="readonly",
        )
        assert "tim@gmail.com" in str(auth.token_path)
        assert auth.token_path.name == "token_readonly.json"

    def test_token_path_standard_tier(self, tmp_path: Path) -> None:
        auth = GoogleAuth(
            account="alice",
            scopes=["scope1"],
            credentials_dir=str(tmp_path),
            tier="standard",
        )
        assert auth.token_path.name == "token_standard.json"

    def test_token_path_creates_parent_dir(self, tmp_path: Path) -> None:
        auth = GoogleAuth(
            account="new-account",
            scopes=[],
            credentials_dir=str(tmp_path),
        )
        _ = auth.token_path
        assert (tmp_path / "tokens" / "new-account").is_dir()

    def test_credentials_file_uses_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = str(tmp_path / "custom_creds.json")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", custom)
        auth = GoogleAuth(credentials_dir=str(tmp_path))
        assert str(auth.credentials_file) == custom

    def test_credentials_file_fallback_to_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        auth = GoogleAuth(credentials_dir=str(tmp_path))
        assert auth.credentials_file == tmp_path / "credentials.json"

    def test_get_credentials_returns_cached_when_valid(
        self, tmp_path: Path, mock_creds: MagicMock
    ) -> None:
        auth = GoogleAuth(account="default", scopes=[], credentials_dir=str(tmp_path))
        auth._credentials = mock_creds

        with patch("iobox.providers.google.auth.Credentials") as MockCreds:
            result = auth.get_credentials()

        assert result is mock_creds
        MockCreds.from_authorized_user_file.assert_not_called()

    def test_get_credentials_loads_existing_token(
        self, tmp_path: Path, token_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)
        mock_creds = MagicMock()
        mock_creds.valid = True

        # GoogleAuth now reads via TokenStore.load (returns a dict) and passes
        # it to Credentials.from_authorized_user_info — patch the new path.
        with patch(
            "iobox.providers.google.auth.Credentials.from_authorized_user_info",
            return_value=mock_creds,
        ):
            auth = GoogleAuth(
                account="default",
                scopes=["scope"],
                credentials_dir=str(tmp_path),
                tier="readonly",
            )
            result = auth.get_credentials()

        assert result is mock_creds

    def test_get_credentials_refreshes_expired_token(
        self, tmp_path: Path, token_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "rtoken"
        mock_creds.to_json.return_value = "{}"

        with patch(
            "iobox.providers.google.auth.Credentials.from_authorized_user_info",
            return_value=mock_creds,
        ):
            with patch("iobox.providers.google.auth.Request"):
                auth = GoogleAuth(
                    account="default",
                    scopes=["scope"],
                    credentials_dir=str(tmp_path),
                    tier="readonly",
                )
                auth.get_credentials()

        mock_creds.refresh.assert_called_once()

    def test_get_credentials_triggers_flow_when_no_token(
        self, tmp_path: Path, creds_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = "{}"

        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = mock_creds
            mock_flow_cls.return_value = mock_flow

            auth = GoogleAuth(
                account="nobody",
                scopes=["scope"],
                credentials_dir=str(tmp_path),
                tier="readonly",
            )
            result = auth.get_credentials()

        assert result is mock_creds
        mock_flow_cls.assert_called_once()
        mock_flow.run_local_server.assert_called_once_with(port=0)

    def test_get_credentials_raises_when_no_creds_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        auth = GoogleAuth(
            account="nobody",
            scopes=["scope"],
            credentials_dir=str(tmp_path),
        )
        with pytest.raises(FileNotFoundError, match="Credentials file not found"):
            auth.get_credentials()

    def test_get_service_calls_build_with_correct_args(
        self, tmp_path: Path, mock_creds: MagicMock
    ) -> None:
        auth = GoogleAuth(account="default", scopes=[], credentials_dir=str(tmp_path))
        auth._credentials = mock_creds

        with patch("iobox.providers.google.auth.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            result = auth.get_service("calendar", "v3")

        mock_build.assert_called_once_with("calendar", "v3", credentials=mock_creds)
        assert result is mock_service

    def test_get_service_gmail(self, tmp_path: Path, mock_creds: MagicMock) -> None:
        auth = GoogleAuth(account="default", scopes=[], credentials_dir=str(tmp_path))
        auth._credentials = mock_creds

        with patch("iobox.providers.google.auth.build") as mock_build:
            auth.get_service("gmail", "v1")

        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)

    def test_get_service_drive(self, tmp_path: Path, mock_creds: MagicMock) -> None:
        auth = GoogleAuth(account="default", scopes=[], credentials_dir=str(tmp_path))
        auth._credentials = mock_creds

        with patch("iobox.providers.google.auth.build") as mock_build:
            auth.get_service("drive", "v3")

        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)


# ── Scope coverage / refresh failure / concurrency ────────────────────────────

GMAIL_RO = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MODIFY = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
CAL_RO = "https://www.googleapis.com/auth/calendar.readonly"
CAL = "https://www.googleapis.com/auth/calendar"


def _token(scopes: list[str], **extra: object) -> dict:
    info = {
        "token": "access",
        "refresh_token": "refresh",
        "client_id": "cid",
        "client_secret": "secret",
        "scopes": scopes,
        # Without an expiry google-auth treats the token as already expired.
        "expiry": "2099-01-01T00:00:00Z",
    }
    info.update(extra)
    return info


@pytest.fixture(autouse=True)
def _no_real_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard: a real Credentials.refresh would hit Google's token endpoint."""
    from google.oauth2.credentials import Credentials

    def _fail(self: object, request: object) -> None:
        raise AssertionError("test attempted a real token refresh")

    monkeypatch.setattr(Credentials, "refresh", _fail)


def _write_token(tmp_path: Path, account: str, tier: str, info: dict) -> Path:
    path = tmp_path / "tokens" / account / f"token_{tier}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info))
    return path


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GMAIL_TOKEN_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)


class TestScopeCoverage:
    """DATA-07: cached token must cover the requested scopes."""

    def test_token_with_all_scopes_is_used_without_flow(self, tmp_path: Path, no_env: None) -> None:
        _write_token(tmp_path, "a", "readonly", _token([GMAIL_RO, CAL_RO]))
        auth = GoogleAuth("a", [GMAIL_RO, CAL_RO], str(tmp_path), "readonly")
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            creds = auth.get_credentials()
        flow_cls.assert_not_called()
        assert set(creds.scopes) == {GMAIL_RO, CAL_RO}

    def test_missing_scope_triggers_consent_for_full_set(
        self, tmp_path: Path, creds_file: Path, no_env: None
    ) -> None:
        # Token was granted email only; calendar was added to the space later.
        _write_token(tmp_path, "a", "readonly", _token([GMAIL_RO]))
        new_creds = MagicMock(valid=True)
        new_creds.to_json.return_value = json.dumps(_token([GMAIL_RO, CAL_RO]))
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            flow_cls.return_value.run_local_server.return_value = new_creds
            auth = GoogleAuth("a", [GMAIL_RO, CAL_RO], str(tmp_path), "readonly")
            result = auth.get_credentials()
        assert result is new_creds
        assert flow_cls.call_args.args[1] == [GMAIL_RO, CAL_RO]

    def test_implied_scopes_count_as_covered(self, tmp_path: Path, no_env: None) -> None:
        _write_token(tmp_path, "a", "readonly", _token([GMAIL_MODIFY, CAL]))
        auth = GoogleAuth("a", [GMAIL_RO, CAL_RO], str(tmp_path), "readonly")
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            auth.get_credentials()
        flow_cls.assert_not_called()

    def test_loaded_creds_keep_stored_scopes(self, tmp_path: Path, no_env: None) -> None:
        _write_token(tmp_path, "a", "standard", _token([GMAIL_MODIFY, GMAIL_COMPOSE, CAL]))
        auth = GoogleAuth("a", [GMAIL_MODIFY, GMAIL_COMPOSE], str(tmp_path), "standard")
        creds = auth.get_credentials()
        assert CAL in creds.scopes

    def test_readonly_tier_accepts_broader_standard_token(
        self, tmp_path: Path, no_env: None
    ) -> None:
        _write_token(tmp_path, "a", "standard", _token([GMAIL_MODIFY, GMAIL_COMPOSE]))
        auth = GoogleAuth("a", [GMAIL_RO], str(tmp_path), "readonly")
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            creds = auth.get_credentials()
        flow_cls.assert_not_called()
        assert creds.refresh_token == "refresh"
        assert not (tmp_path / "tokens" / "a" / "token_readonly.json").exists()

    def test_standard_tier_does_not_accept_readonly_token(
        self, tmp_path: Path, creds_file: Path, no_env: None
    ) -> None:
        _write_token(tmp_path, "a", "readonly", _token([GMAIL_RO]))
        new_creds = MagicMock(valid=True)
        new_creds.to_json.return_value = "{}"
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            flow_cls.return_value.run_local_server.return_value = new_creds
            GoogleAuth("a", [GMAIL_MODIFY], str(tmp_path), "standard").get_credentials()
        flow_cls.assert_called_once()

    def test_saved_token_is_private(self, tmp_path: Path, creds_file: Path, no_env: None) -> None:
        new_creds = MagicMock(valid=True)
        new_creds.to_json.return_value = json.dumps(_token([GMAIL_RO]))
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            flow_cls.return_value.run_local_server.return_value = new_creds
            GoogleAuth("a", [GMAIL_RO], str(tmp_path), "readonly").get_credentials()
        path = tmp_path / "tokens" / "a" / "token_readonly.json"
        assert (path.stat().st_mode & 0o777) == 0o600


class TestRefreshFailure:
    """DATA-08: a revoked refresh token is discarded and consent re-run."""

    def _expired(self) -> MagicMock:
        from google.auth.exceptions import RefreshError

        creds = MagicMock(valid=False, expired=True, refresh_token="dead")
        creds.refresh.side_effect = RefreshError("invalid_grant")
        return creds

    def test_refresh_error_deletes_token_and_runs_flow(
        self, tmp_path: Path, creds_file: Path, no_env: None
    ) -> None:
        path = _write_token(tmp_path, "a", "readonly", _token([GMAIL_RO]))
        new_creds = MagicMock(valid=True)
        new_creds.to_json.return_value = json.dumps({"token": "fresh"})
        with (
            patch(
                "iobox.providers.google.auth.Credentials.from_authorized_user_info",
                return_value=self._expired(),
            ),
            patch("iobox.providers.google.auth.Request"),
            patch(
                "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
            ) as flow_cls,
        ):
            flow_cls.return_value.run_local_server.return_value = new_creds
            result = GoogleAuth("a", [GMAIL_RO], str(tmp_path), "readonly").get_credentials()
        assert result is new_creds
        assert json.loads(path.read_text()) == {"token": "fresh"}

    def test_refresh_error_without_client_secrets_gives_login_hint(
        self, tmp_path: Path, no_env: None
    ) -> None:
        path = _write_token(tmp_path, "a", "readonly", _token([GMAIL_RO]))
        with (
            patch(
                "iobox.providers.google.auth.Credentials.from_authorized_user_info",
                return_value=self._expired(),
            ),
            patch("iobox.providers.google.auth.Request"),
        ):
            with pytest.raises(FileNotFoundError, match="iobox space login"):
                GoogleAuth("a", [GMAIL_RO], str(tmp_path), "readonly").get_credentials()
        assert not path.exists()


class TestConcurrency:
    """WS-06: shared GoogleAuth across fan-out threads authenticates once."""

    def test_concurrent_get_credentials_runs_flow_once(
        self, tmp_path: Path, creds_file: Path, no_env: None
    ) -> None:
        import threading
        import time

        calls = 0

        def slow_flow(port: int) -> MagicMock:
            nonlocal calls
            calls += 1
            time.sleep(0.05)
            creds = MagicMock(valid=True)
            creds.to_json.return_value = "{}"
            return creds

        auth = GoogleAuth("a", [GMAIL_RO], str(tmp_path), "readonly")
        with patch(
            "iobox.providers.google.auth.InstalledAppFlow.from_client_secrets_file"
        ) as flow_cls:
            flow_cls.return_value.run_local_server.side_effect = slow_flow
            threads = [threading.Thread(target=auth.get_credentials) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        assert calls == 1


# ── TestGetGoogleScopes ────────────────────────────────────────────────────────


class TestGetGoogleScopes:
    def test_messages_only_readonly(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["email"], "readonly")
        assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
        assert not any("calendar" in s for s in scopes)
        assert not any("drive" in s for s in scopes)

    def test_messages_only_standard(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["email"], "standard")
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
        assert "https://www.googleapis.com/auth/gmail.compose" in scopes

    def test_calendar_readonly(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["calendar"], "readonly")
        assert "https://www.googleapis.com/auth/calendar.readonly" in scopes
        assert not any("gmail" in s for s in scopes)

    def test_calendar_standard(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["calendar"], "standard")
        assert "https://www.googleapis.com/auth/calendar" in scopes
        # Must not include calendar.readonly when standard calendar is present
        assert "https://www.googleapis.com/auth/calendar.readonly" not in scopes

    def test_drive_scopes_by_mode(self) -> None:
        from iobox.modes import get_google_scopes

        scopes_ro = get_google_scopes(["drive"], "readonly")
        scopes_std = get_google_scopes(["drive"], "standard")
        assert "https://www.googleapis.com/auth/drive.readonly" in scopes_ro
        # Standard mode gets full drive scope (write ops enabled in task-019)
        assert "https://www.googleapis.com/auth/drive" in scopes_std
        assert "https://www.googleapis.com/auth/drive.readonly" not in scopes_std

    def test_messages_calendar_drive_readonly(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["email", "calendar", "drive"], "readonly")
        assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
        assert "https://www.googleapis.com/auth/calendar.readonly" in scopes
        assert "https://www.googleapis.com/auth/drive.readonly" in scopes

    def test_messages_calendar_standard(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["email", "calendar"], "standard")
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
        assert "https://www.googleapis.com/auth/calendar" in scopes

    def test_empty_services_returns_empty(self) -> None:
        from iobox.modes import get_google_scopes

        assert get_google_scopes([], "readonly") == []

    def test_no_duplicates(self) -> None:
        from iobox.modes import get_google_scopes

        scopes = get_google_scopes(["email", "email", "calendar"], "readonly")
        assert len(scopes) == len(set(scopes))


# ── TestTierForMode ────────────────────────────────────────────────────────────


class TestTierForMode:
    def test_readonly_maps_to_readonly(self) -> None:
        from iobox.modes import _tier_for_mode

        assert _tier_for_mode("readonly") == "readonly"

    def test_standard_maps_to_standard(self) -> None:
        from iobox.modes import _tier_for_mode

        assert _tier_for_mode("standard") == "standard"

    def test_dangerous_maps_to_standard(self) -> None:
        from iobox.modes import _tier_for_mode

        assert _tier_for_mode("dangerous") == "standard"
