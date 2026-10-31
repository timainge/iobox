"""
Unit tests for the legacy Outlook auth helpers in ``iobox.providers.o365.auth``:
``get_outlook_account`` (used by ``--provider outlook``) and
``check_outlook_auth_status`` (used by ``auth-status``).

Both delegate to the real python-o365 ``Account`` and token backend; only
the interactive consent step is stubbed. Tests needing python-o365 are
skipped when the ``outlook`` extra is not installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from iobox.providers.o365 import auth as auth_mod
from tests.unit.test_microsoft_auth import msal_cache

requires_o365 = pytest.mark.skipif(not auth_mod.HAS_O365, reason="outlook extra not installed")


def _cfg(tmp_path: Path, account: str = "default", client_id: str = "cid", **kw: str) -> dict:
    return {
        "client_id": client_id,
        "client_secret": kw.get("client_secret", ""),
        "tenant_id": kw.get("tenant_id", "common"),
        "credentials_dir": str(tmp_path),
        "token_dir": str(tmp_path / "tokens" / account),
    }


def _write(path: Path, **kwargs: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(msal_cache(client_id="cid", **kwargs)))
    return path


# ---------------------------------------------------------------------------
# get_outlook_account
# ---------------------------------------------------------------------------


class TestGetOutlookAccountErrors:
    def test_import_error_when_o365_missing(self, tmp_path: Path) -> None:
        with (
            patch.object(auth_mod, "HAS_O365", False),
            patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)),
            pytest.raises(ImportError, match="O365"),
        ):
            auth_mod.get_outlook_account()

    @requires_o365
    def test_value_error_without_client_id(self, tmp_path: Path) -> None:
        with (
            patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path, client_id="")),
            pytest.raises(ValueError, match="OUTLOOK_CLIENT_ID"),
        ):
            auth_mod.get_outlook_account()


@requires_o365
class TestGetOutlookAccount:
    def _call(self, tmp_path: Path, **kwargs: Any) -> tuple[Any, Any]:
        from O365 import Account

        with (
            patch.object(
                auth_mod, "_get_config", return_value=_cfg(tmp_path, **kwargs.pop("cfg", {}))
            ),
            patch.object(Account, "authenticate", autospec=True, return_value=True) as m,
        ):
            acct = auth_mod.get_outlook_account(**kwargs)
        return acct, m

    def test_standard_mode_requests_mail_write_scopes(self, tmp_path: Path) -> None:
        _, m = self._call(tmp_path)
        assert m.call_args.kwargs["requested_scopes"] == ["basic", "Mail.ReadWrite", "Mail.Send"]

    def test_readonly_mode_requests_only_mail_read(self, tmp_path: Path) -> None:
        _, m = self._call(tmp_path, mode="readonly")
        assert m.call_args.kwargs["requested_scopes"] == ["basic", "Mail.Read"]

    def test_uses_tiered_token_under_credentials_dir(self, tmp_path: Path) -> None:
        token = _write(
            tmp_path / "tokens" / "corp@x.com" / "microsoft_token_standard.txt",
            scopes="Mail.ReadWrite Mail.Send User.Read",
        )
        acct, m = self._call(tmp_path, account="corp@x.com", cfg={"account": "corp@x.com"})
        m.assert_not_called()
        assert str(acct.con.token_backend.token_path) == str(token)

    def test_migrates_old_o365_token(self, tmp_path: Path) -> None:
        legacy = _write(
            tmp_path / "tokens" / "outlook" / "o365_token.txt",
            scopes="Mail.ReadWrite Mail.Send User.Read",
        )
        _, m = self._call(tmp_path)
        m.assert_not_called()
        new = tmp_path / "tokens" / "default" / "microsoft_token_standard.txt"
        assert new.read_text() == legacy.read_text()

    def test_immutable_ids_enabled(self, tmp_path: Path) -> None:
        acct, _ = self._call(tmp_path)
        assert auth_mod.IMMUTABLE_ID_PREFER in acct.con.default_headers["Prefer"]

    def test_device_code_option_selects_public_device_flow(self, tmp_path: Path) -> None:
        with (
            patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path, client_secret="s")),
            patch.object(auth_mod, "_device_code_flow", return_value=True) as dc,
        ):
            acct = auth_mod.get_outlook_account(device_code=True)
        dc.assert_called_once()
        assert acct.con.auth_flow_type == "public"


# ---------------------------------------------------------------------------
# check_outlook_auth_status
# ---------------------------------------------------------------------------


class TestCheckOutlookAuthStatus:
    def test_no_client_id(self, tmp_path: Path) -> None:
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path, client_id="")):
            status = auth_mod.check_outlook_auth_status()
        assert status["authenticated"] is False
        assert status["client_id_configured"] is False

    def test_token_missing(self, tmp_path: Path) -> None:
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)):
            status = auth_mod.check_outlook_auth_status()
        assert status["token_file_exists"] is False
        assert status["token_path"] == str(
            tmp_path / "tokens" / "default" / "microsoft_token_standard.txt"
        )

    def test_readonly_token_path(self, tmp_path: Path) -> None:
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)):
            status = auth_mod.check_outlook_auth_status(mode="readonly")
        assert status["token_path"].endswith("microsoft_token_readonly.txt")

    def test_reports_missing_o365(self, tmp_path: Path) -> None:
        _write(tmp_path / "tokens" / "default" / "microsoft_token_standard.txt")
        with (
            patch.object(auth_mod, "HAS_O365", False),
            patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)),
        ):
            status = auth_mod.check_outlook_auth_status()
        assert status["authenticated"] is False
        assert "O365" in status["error"]

    @requires_o365
    def test_valid_token(self, tmp_path: Path) -> None:
        _write(tmp_path / "tokens" / "default" / "microsoft_token_standard.txt")
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)):
            status = auth_mod.check_outlook_auth_status()
        assert status["authenticated"] is True
        assert status["token_file_exists"] is True

    @requires_o365
    def test_legacy_token_counts_for_standard_only(self, tmp_path: Path) -> None:
        _write(tmp_path / "tokens" / "default" / "o365_token.txt")
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)):
            std = auth_mod.check_outlook_auth_status()
            ro = auth_mod.check_outlook_auth_status(mode="readonly")
        assert std["authenticated"] is True
        assert ro["token_file_exists"] is False

    @requires_o365
    def test_expired_token_without_refresh_is_not_authenticated(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens" / "default" / "microsoft_token_standard.txt"
        cache = msal_cache(client_id="cid", expires_in=-60)
        cache["RefreshToken"] = {}
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(cache))
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)):
            status = auth_mod.check_outlook_auth_status()
        assert status["authenticated"] is False

    @requires_o365
    def test_pre_2_1_token_reports_error(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens" / "default" / "microsoft_token_standard.txt"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"access_token": "old-format"}))
        with patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)):
            status = auth_mod.check_outlook_auth_status()
        assert status["authenticated"] is False
        assert "error" in status

    @requires_o365
    def test_does_not_trigger_auth_flow(self, tmp_path: Path) -> None:
        from O365 import Account

        _write(tmp_path / "tokens" / "default" / "microsoft_token_standard.txt")
        with (
            patch.object(auth_mod, "_get_config", return_value=_cfg(tmp_path)),
            patch.object(Account, "authenticate", autospec=True) as m,
        ):
            auth_mod.check_outlook_auth_status()
        m.assert_not_called()


class TestGetConfig:
    def test_reads_env_at_call_time(self, tmp_path: Path) -> None:
        env = {
            "OUTLOOK_CLIENT_ID": "late-id",
            "OUTLOOK_TENANT_ID": "tenant-x",
            "CREDENTIALS_DIR": str(tmp_path),
        }
        with patch.dict(os.environ, env):
            cfg = auth_mod._get_config(account="a@b.com")
        assert cfg["client_id"] == "late-id"
        assert cfg["tenant_id"] == "tenant-x"
        assert cfg["token_dir"] == os.path.join(str(tmp_path), "tokens", "a@b.com")
