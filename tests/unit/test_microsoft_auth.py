"""
Unit tests for MicrosoftAuth and the Microsoft scope / ImmutableId helpers.

Tests that need python-o365 run the **real** ``O365.Account`` / token
backends (no hand-rolled fakes of the library) and stub only the parts that
would reach the network: the interactive consent step and the MSAL client.
They are skipped when the ``outlook`` extra is not installed.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from iobox.providers.o365 import auth as auth_mod
from iobox.providers.o365.auth import (
    IMMUTABLE_ID_PREFER,
    ensure_immutable_ids,
    get_microsoft_scopes,
    scopes_cover,
    tier_for_mode,
    tier_for_scopes,
)

requires_o365 = pytest.mark.skipif(not auth_mod.HAS_O365, reason="outlook extra not installed")

CLIENT_ID = "test-client-id"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def msal_cache(
    *,
    username: str = "user@example.com",
    scopes: str = "Mail.Read User.Read",
    client_id: str = CLIENT_ID,
    expires_in: int = 3600,
) -> dict[str, Any]:
    """Return a serialized MSAL token cache as python-o365 stores it."""
    hid, env, realm = "uid.tid", "login.microsoftonline.com", "tid"
    now = int(time.time())
    base = {"home_account_id": hid, "environment": env, "client_id": client_id}
    return {
        "Account": {
            f"{hid}-{env}-{realm}": {
                "home_account_id": hid,
                "environment": env,
                "realm": realm,
                "local_account_id": "uid",
                "username": username,
                "authority_type": "MSSTS",
            }
        },
        "AccessToken": {
            "at": {
                **base,
                "credential_type": "AccessToken",
                "secret": "access-token",
                "target": scopes,
                "realm": realm,
                "token_type": "Bearer",
                "cached_at": str(now),
                "expires_on": str(now + expires_in),
            }
        },
        "RefreshToken": {
            "rt": {**base, "credential_type": "RefreshToken", "secret": "rt", "target": scopes}
        },
        "IdToken": {},
        "AppMetadata": {},
    }


def write_token(path: Path, **kwargs: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(msal_cache(**kwargs)))
    return path


def make_auth(tmp_path: Path, **kwargs: Any) -> Any:
    kwargs.setdefault("account", "user@example.com")
    kwargs.setdefault("client_id", CLIENT_ID)
    kwargs.setdefault("client_secret", "")
    return auth_mod.MicrosoftAuth(credentials_dir=str(tmp_path), **kwargs)


def mode_of(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


# ---------------------------------------------------------------------------
# Pure helpers (no O365 needed)
# ---------------------------------------------------------------------------


class TestGetMicrosoftScopes:
    def test_messages_readonly(self) -> None:
        scopes = get_microsoft_scopes(["email"], "readonly")
        assert "Mail.Read" in scopes
        assert "Mail.ReadWrite" not in scopes
        assert "Mail.Send" not in scopes

    def test_messages_standard(self) -> None:
        scopes = get_microsoft_scopes(["email"], "standard")
        assert "Mail.ReadWrite" in scopes
        assert "Mail.Send" in scopes

    def test_calendar_and_drive(self) -> None:
        assert "Calendars.Read" in get_microsoft_scopes(["calendar"], "readonly")
        assert "Calendars.ReadWrite" in get_microsoft_scopes(["calendar"], "standard")
        assert "Files.Read.All" in get_microsoft_scopes(["drive"], "readonly")
        assert "Files.ReadWrite.All" in get_microsoft_scopes(["drive"], "standard")

    def test_readonly_never_contains_write_scopes(self) -> None:
        scopes = get_microsoft_scopes(["email", "calendar", "drive"], "readonly")
        assert tier_for_scopes(scopes) == "readonly"
        assert scopes[0] == "basic"

    def test_empty_services(self) -> None:
        assert get_microsoft_scopes([], "readonly") == ["basic"]

    def test_no_duplicates(self) -> None:
        assert get_microsoft_scopes(["email", "email"], "readonly").count("Mail.Read") == 1


class TestTierHelpers:
    def test_tier_for_mode(self) -> None:
        assert tier_for_mode("readonly") == "readonly"
        assert tier_for_mode("standard") == "standard"
        assert tier_for_mode("dangerous") == "standard"

    @pytest.mark.parametrize(
        ("scopes", "tier"),
        [
            (["basic", "Mail.Read"], "readonly"),
            (["Files.Read.All", "Calendars.Read"], "readonly"),
            (["Mail.ReadWrite"], "standard"),
            (["Mail.Send"], "standard"),
            (["https://graph.microsoft.com/Calendars.ReadWrite"], "standard"),
        ],
    )
    def test_tier_for_scopes(self, scopes: list[str], tier: str) -> None:
        assert tier_for_scopes(scopes) == tier


class TestScopesCover:
    def test_exact_match_ignores_prefix_and_case(self) -> None:
        assert scopes_cover(
            ["mail.read", "User.Read"],
            ["https://graph.microsoft.com/Mail.Read", "https://graph.microsoft.com/User.Read"],
        )

    def test_readwrite_covers_read(self) -> None:
        assert scopes_cover(
            ["Mail.ReadWrite", "Files.ReadWrite.All"], ["Mail.Read", "Files.Read.All"]
        )

    def test_read_does_not_cover_readwrite(self) -> None:
        assert not scopes_cover(["Mail.Read"], ["Mail.ReadWrite"])

    def test_missing_send(self) -> None:
        assert not scopes_cover(["Mail.ReadWrite"], ["Mail.Send"])

    def test_reserved_scopes_ignored(self) -> None:
        assert scopes_cover(["Mail.Read"], ["Mail.Read", "offline_access", "openid"])


class TestEnsureImmutableIds:
    """O365-01: the preference must live on con.default_headers, never con.session."""

    def test_sets_prefer_without_touching_session(self) -> None:
        con = SimpleNamespace(default_headers={}, session=None)
        ensure_immutable_ids(SimpleNamespace(con=con))
        assert con.default_headers["Prefer"] == IMMUTABLE_ID_PREFER
        assert con.session is None  # old code crashed: None.headers.update

    def test_appends_to_existing_prefer(self) -> None:
        con = SimpleNamespace(default_headers={"Prefer": 'outlook.timezone="UTC"'})
        ensure_immutable_ids(SimpleNamespace(con=con))
        assert con.default_headers["Prefer"] == f'outlook.timezone="UTC", {IMMUTABLE_ID_PREFER}'

    def test_idempotent(self) -> None:
        con = SimpleNamespace(default_headers={})
        acct = SimpleNamespace(con=con)
        ensure_immutable_ids(acct)
        ensure_immutable_ids(acct)
        assert con.default_headers["Prefer"] == IMMUTABLE_ID_PREFER


# ---------------------------------------------------------------------------
# MicrosoftAuth construction (no network)
# ---------------------------------------------------------------------------


@requires_o365
class TestMicrosoftAuthConstruction:
    def test_token_file_is_per_tier(self, tmp_path: Path) -> None:
        ro = make_auth(tmp_path, scopes=["basic", "Mail.Read"])
        std = make_auth(tmp_path, scopes=["basic", "Mail.ReadWrite", "Mail.Send"])
        base = tmp_path / "tokens" / "user@example.com"
        assert ro.tier == "readonly"
        assert ro.token_file == base / "microsoft_token_readonly.txt"
        assert std.tier == "standard"
        assert std.token_file == base / "microsoft_token_standard.txt"

    def test_explicit_tier_and_mode(self, tmp_path: Path) -> None:
        assert make_auth(tmp_path, scopes=["Mail.ReadWrite"], tier="readonly").tier == "readonly"
        assert make_auth(tmp_path, scopes=["Mail.Read"], mode="dangerous").tier == "standard"

    def test_invalid_tier(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="tier"):
            make_auth(tmp_path, tier="admin")

    def test_constructor_compatible_with_workspace_from_config(self, tmp_path: Path) -> None:
        # Workspace.from_config passes (account=, scopes=, credentials_dir=) only.
        a = auth_mod.MicrosoftAuth(
            account="corp@example.com",
            scopes=get_microsoft_scopes(["email", "calendar"], "standard"),
            credentials_dir=str(tmp_path),
        )
        assert a.tier == "standard"

    def test_token_dir_is_private(self, tmp_path: Path) -> None:
        d = make_auth(tmp_path).token_dir
        assert mode_of(d) == 0o700

    def test_default_credentials_dir_is_iobox_home(self) -> None:
        a = auth_mod.MicrosoftAuth(account="user@example.com", client_id="x")
        assert a._credentials_dir.name == ".iobox"

    def test_raises_without_client_id(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"OUTLOOK_CLIENT_ID": ""}):
            a = auth_mod.MicrosoftAuth(credentials_dir=str(tmp_path), client_id="")
            with pytest.raises(ValueError, match="OUTLOOK_CLIENT_ID"):
                a.get_account()

    def test_public_flow_without_secret(self, tmp_path: Path) -> None:
        acct = make_auth(tmp_path)._build_account()
        assert acct.con.auth_flow_type == "public"
        assert acct.con.auth == (CLIENT_ID,)

    def test_confidential_flow_with_secret(self, tmp_path: Path) -> None:
        acct = make_auth(tmp_path, client_secret="s3cret")._build_account()
        assert acct.con.auth_flow_type == "authorization"
        assert acct.con.auth == (CLIENT_ID, "s3cret")

    def test_built_account_requests_immutable_ids(self, tmp_path: Path) -> None:
        acct = make_auth(tmp_path)._build_account()
        assert acct.con.session is None  # created lazily by python-o365
        assert IMMUTABLE_ID_PREFER in acct.con.default_headers["Prefer"]


@requires_o365
class TestImmutableIdOnTheWire:
    """O365-01: the real Connection must send Prefer on every request."""

    def test_default_headers_reach_requests(self, tmp_path: Path) -> None:
        acct = make_auth(tmp_path)._build_account()
        session = MagicMock()
        session.headers = {"Authorization": "Bearer x"}
        session.request.return_value = MagicMock(status_code=200)
        acct.con.session = session

        acct.con.get("https://graph.microsoft.com/v1.0/me/events")
        acct.con.get(
            "https://graph.microsoft.com/v1.0/me/calendar/calendarView",
            headers={"Prefer": 'outlook.timezone="UTC"'},
        )

        first, second = (c.kwargs["headers"]["Prefer"] for c in session.request.call_args_list)
        assert first == IMMUTABLE_ID_PREFER
        assert second == f'outlook.timezone="UTC", {IMMUTABLE_ID_PREFER}'


# ---------------------------------------------------------------------------
# Authentication flow (O365-06)
# ---------------------------------------------------------------------------


@requires_o365
class TestAuthenticateScopes:
    def _run(self, auth: Any) -> list[str]:
        """Run get_account with consent aborted; return scopes sent to MSAL."""
        from O365.connection import Connection

        with (
            patch.object(
                Connection, "get_authorization_url", autospec=True, return_value=("url", {})
            ) as gau,
            patch("builtins.input", return_value=""),
            pytest.raises(RuntimeError, match="authentication failed"),
        ):
            auth.get_account()
        return list(gau.call_args.args[1])

    def test_readonly_requests_only_read_scopes(self, tmp_path: Path) -> None:
        auth = make_auth(tmp_path, scopes=get_microsoft_scopes(["email", "calendar"], "readonly"))
        requested = self._run(auth)
        short = sorted(s.rsplit("/", 1)[-1] for s in requested)
        # The old code passed scopes= (ignored) → python-o365 requested all 24
        # default scopes, including Mail.ReadWrite / Files.ReadWrite.All.
        assert short == ["Calendars.Read", "Mail.Read", "User.Read"]

    def test_standard_requests_write_scopes(self, tmp_path: Path) -> None:
        auth = make_auth(tmp_path, scopes=get_microsoft_scopes(["email"], "standard"))
        short = sorted(s.rsplit("/", 1)[-1] for s in self._run(auth))
        assert short == ["Mail.ReadWrite", "Mail.Send", "User.Read"]

    def test_authenticate_called_with_requested_scopes_kwarg(self, tmp_path: Path) -> None:
        from O365 import Account

        auth = make_auth(tmp_path, scopes=["basic", "Mail.Read"])
        with patch.object(Account, "authenticate", autospec=True, return_value=True) as m:
            auth.get_account()
        assert m.call_args.kwargs == {"requested_scopes": ["basic", "Mail.Read"]}

    def test_skips_flow_when_token_covers_scopes(self, tmp_path: Path) -> None:
        from O365 import Account

        auth = make_auth(tmp_path, scopes=["basic", "Mail.Read"])
        write_token(auth.token_file, scopes="Mail.Read User.Read")
        with patch.object(Account, "authenticate", autospec=True) as m:
            acct = auth.get_account()
        m.assert_not_called()
        assert acct.is_authenticated
        assert auth.get_account() is acct  # cached

    def test_raises_when_flow_fails(self, tmp_path: Path) -> None:
        from O365 import Account

        auth = make_auth(tmp_path)
        with (
            patch.object(Account, "authenticate", autospec=True, return_value=False),
            pytest.raises(RuntimeError, match="authentication failed"),
        ):
            auth.get_account()


@requires_o365
class TestScopeCoverage:
    """O365-12: a cached token that lacks requested scopes forces re-consent."""

    def test_reauth_when_token_lacks_scopes(self, tmp_path: Path) -> None:
        from O365 import Account

        auth = make_auth(tmp_path, scopes=get_microsoft_scopes(["email", "calendar"], "standard"))
        write_token(auth.token_file, scopes="Mail.ReadWrite Mail.Send User.Read")
        with patch.object(Account, "authenticate", autospec=True, return_value=True) as m:
            auth.get_account()
        m.assert_called_once()
        requested = m.call_args.kwargs["requested_scopes"]
        assert "Calendars.ReadWrite" in requested
        assert not auth.token_file.exists()  # stale token discarded

    def test_readwrite_grant_satisfies_read_request(self, tmp_path: Path) -> None:
        from O365 import Account

        auth = make_auth(tmp_path, scopes=["basic", "Mail.Read"], tier="standard")
        write_token(auth.token_file, scopes="Mail.ReadWrite User.Read")
        with patch.object(Account, "authenticate", autospec=True) as m:
            auth.get_account()
        m.assert_not_called()

    def test_readonly_reauth_never_widens(self, tmp_path: Path) -> None:
        from O365 import Account

        auth = make_auth(tmp_path, scopes=["basic", "Calendars.Read"])
        write_token(auth.token_file, scopes="Mail.ReadWrite User.Read")
        with patch.object(Account, "authenticate", autospec=True, return_value=True) as m:
            auth.get_account()
        requested = m.call_args.kwargs["requested_scopes"]
        assert "Mail.ReadWrite" not in requested
        assert "Calendars.Read" in requested


@requires_o365
class TestDeviceCodeFlow:
    def test_device_code_uses_msal_public_client(self, tmp_path: Path, capsys: Any) -> None:
        from O365 import Account
        from O365.connection import Connection

        client = MagicMock()
        client.initiate_device_flow.return_value = {"user_code": "ABC", "message": "Go to x"}
        client.acquire_token_by_device_flow.return_value = {
            "access_token": "t",
            "id_token_claims": {"preferred_username": "user@example.com"},
        }
        auth = make_auth(tmp_path, scopes=["basic", "Mail.Read"], device_code=True)
        with (
            patch.object(Connection, "msal_client", new_callable=PropertyMock, return_value=client),
            patch.object(Account, "authenticate", autospec=True) as interactive,
        ):
            acct = auth.get_account()

        interactive.assert_not_called()
        assert acct.con.auth_flow_type == "public"
        scopes = client.initiate_device_flow.call_args.kwargs["scopes"]
        assert sorted(s.rsplit("/", 1)[-1] for s in scopes) == ["Mail.Read", "User.Read"]
        assert acct.con.username == "user@example.com"
        assert "Go to x" in capsys.readouterr().err

    def test_device_code_failure(self, tmp_path: Path) -> None:
        from O365.connection import Connection

        client = MagicMock()
        client.initiate_device_flow.return_value = {"error_description": "nope"}
        auth = make_auth(tmp_path, device_code=True)
        with (
            patch.object(Connection, "msal_client", new_callable=PropertyMock, return_value=client),
            pytest.raises(RuntimeError, match="authentication failed"),
        ):
            auth.get_account()


# ---------------------------------------------------------------------------
# Token files: migration + permissions (O365-12, SEC-07)
# ---------------------------------------------------------------------------


@requires_o365
class TestTokenMigration:
    def _get(self, auth: Any) -> None:
        from O365 import Account

        with patch.object(Account, "authenticate", autospec=True, return_value=True):
            auth.get_account()

    @pytest.mark.parametrize(
        "legacy_rel",
        [
            "tokens/user@example.com/microsoft_token.txt",
            "tokens/user@example.com/o365_token.txt",
            "tokens/outlook/o365_token.txt",
        ],
    )
    def test_legacy_token_migrates_to_standard(self, tmp_path: Path, legacy_rel: str) -> None:
        legacy = write_token(tmp_path / legacy_rel, scopes="Mail.ReadWrite Mail.Send User.Read")
        os.chmod(legacy, 0o644)
        auth = make_auth(tmp_path, scopes=get_microsoft_scopes(["email"], "standard"))
        self._get(auth)
        assert auth.token_file.read_text() == legacy.read_text()
        assert mode_of(auth.token_file) == 0o600
        assert mode_of(legacy) == 0o600

    def test_readonly_tier_never_inherits_legacy_write_token(self, tmp_path: Path) -> None:
        write_token(tmp_path / "tokens/user@example.com/microsoft_token.txt")
        auth = make_auth(tmp_path, scopes=["basic", "Mail.Read"])
        self._get(auth)
        assert not auth.token_file.exists()

    def test_existing_tier_token_not_overwritten(self, tmp_path: Path) -> None:
        write_token(tmp_path / "tokens/user@example.com/microsoft_token.txt", username="old@x")
        auth = make_auth(tmp_path, scopes=get_microsoft_scopes(["email"], "standard"))
        write_token(auth.token_file, scopes="Mail.ReadWrite Mail.Send User.Read")
        before = auth.token_file.read_text()
        self._get(auth)
        assert auth.token_file.read_text() == before


@requires_o365
class TestSecureTokenBackend:
    """SEC-07: refresh tokens must not be world/group readable."""

    def test_save_creates_0600_file_in_0700_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "tokens" / "acct"
        backend = auth_mod.SecureFileSystemTokenBackend(token_path=str(d), token_filename="t.txt")
        backend._cache = msal_cache()
        backend._has_state_changed = True
        assert backend.save_token() is True
        assert mode_of(d / "t.txt") == 0o600
        assert mode_of(d) == 0o700
        assert json.loads((d / "t.txt").read_text())["Account"]

    def test_save_tightens_existing_world_readable_file(self, tmp_path: Path) -> None:
        f = tmp_path / "t.txt"
        f.write_text("{}")
        os.chmod(f, 0o644)
        backend = auth_mod.SecureFileSystemTokenBackend(
            token_path=str(tmp_path), token_filename="t.txt"
        )
        backend._cache = msal_cache()
        assert backend.save_token(force=True) is True
        assert mode_of(f) == 0o600

    def test_upstream_backend_would_be_world_readable(self, tmp_path: Path) -> None:
        """Documents why the subclass exists (umask 022 → 0644 upstream)."""
        from O365 import FileSystemTokenBackend

        old = os.umask(0o022)
        try:
            backend = FileSystemTokenBackend(token_path=str(tmp_path), token_filename="t.txt")
            backend._cache = msal_cache()
            backend.save_token(force=True)
        finally:
            os.umask(old)
        assert mode_of(tmp_path / "t.txt") == 0o644


@requires_o365
class TestCustomTokenStore:
    def test_store_namespaced_per_tier_with_legacy_fallback(self, tmp_path: Path) -> None:
        store = MagicMock()
        auth = make_auth(
            tmp_path, scopes=get_microsoft_scopes(["email"], "standard"), token_store=store
        )
        backend = auth._make_token_backend()
        assert isinstance(backend, auth_mod.TokenStoreTokenBackend)
        assert backend._tier == "microsoft_standard"
        assert backend._fallback_tiers == ("default",)

        ro = make_auth(tmp_path, scopes=["Mail.Read"], token_store=store)._make_token_backend()
        assert ro._tier == "microsoft_readonly"
        assert ro._fallback_tiers == ()
