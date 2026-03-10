"""
Unit tests for ``iobox.providers.outlook_auth``.

All tests inject a fake ``O365`` module into ``sys.modules`` so that the real
python-o365 library is not required at test time.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a fake O365 module
# ---------------------------------------------------------------------------


def _make_o365_module(mock_account_cls=None, mock_token_backend_cls=None):
    """Return a fake ``O365`` module with controllable Account and token backend."""
    o365 = types.ModuleType("O365")
    o365.Account = mock_account_cls or MagicMock()
    o365.FileSystemTokenBackend = mock_token_backend_cls or MagicMock()
    return o365


def _make_mock_account(is_authenticated=True, auth_result=True):
    """Return a MagicMock that behaves like an O365 Account."""
    account = MagicMock()
    account.is_authenticated = is_authenticated
    account.authenticate.return_value = auth_result
    return account


def _cfg(
    client_id="",
    client_secret="",
    tenant_id="common",
    credentials_dir="/tmp",
    token_dir=None,
):
    """Build a config dict as returned by _get_config()."""
    if token_dir is None:
        token_dir = os.path.join(credentials_dir, "tokens", "outlook")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "tenant_id": tenant_id,
        "credentials_dir": credentials_dir,
        "token_dir": token_dir,
    }


# ---------------------------------------------------------------------------
# get_outlook_account — browser flow (default)
# ---------------------------------------------------------------------------


class TestGetOutlookAccountBrowserFlow:
    def test_returns_account_when_already_authenticated(self, tmp_path):
        mock_account = _make_mock_account(is_authenticated=True)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                import iobox.providers.outlook_auth as mod
                result = mod.get_outlook_account()

        assert result is mock_account
        mock_account.authenticate.assert_not_called()

    def test_triggers_browser_flow_when_not_authenticated(self, tmp_path):
        mock_account = _make_mock_account(is_authenticated=False)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(
                    client_id="test-client-id",
                    tenant_id="common",
                    token_dir=token_dir,
                ),
            ):
                import iobox.providers.outlook_auth as mod
                result = mod.get_outlook_account()

        mock_account.authenticate.assert_called_once()
        # browser flow — grant_type should NOT be "device_code"
        call_kwargs = mock_account.authenticate.call_args.kwargs
        assert call_kwargs.get("grant_type") != "device_code"
        assert result is mock_account

    def test_scopes_passed_to_authenticate(self, tmp_path):
        mock_account = _make_mock_account(is_authenticated=False)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                import iobox.providers.outlook_auth as mod
                mod.get_outlook_account()

        call_kwargs = mock_account.authenticate.call_args.kwargs
        assert "Mail.ReadWrite" in call_kwargs["scopes"]
        assert "Mail.Send" in call_kwargs["scopes"]

    def test_raises_value_error_when_client_id_missing(self):
        o365 = _make_o365_module()
        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id=""),
            ):
                import iobox.providers.outlook_auth as mod
                with pytest.raises(ValueError, match="OUTLOOK_CLIENT_ID"):
                    mod.get_outlook_account()

    def test_raises_runtime_error_when_auth_fails(self, tmp_path):
        mock_account = _make_mock_account(is_authenticated=False, auth_result=False)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                import iobox.providers.outlook_auth as mod
                with pytest.raises(RuntimeError, match="authentication failed"):
                    mod.get_outlook_account()

    def test_raises_import_error_when_o365_missing(self):
        # Ensure O365 is NOT in sys.modules and cannot be imported
        sys_modules = {k: v for k, v in sys.modules.items() if k != "O365"}

        with patch.dict(sys.modules, sys_modules, clear=True):
            # Remove O365 if present
            sys.modules.pop("O365", None)
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id"),
            ):
                import iobox.providers.outlook_auth as mod
                with pytest.raises(ImportError, match="O365"):
                    mod.get_outlook_account()


# ---------------------------------------------------------------------------
# get_outlook_account — device-code flow
# ---------------------------------------------------------------------------


class TestGetOutlookAccountDeviceCodeFlow:
    def test_device_code_flag_passed_to_authenticate(self, tmp_path):
        mock_account = _make_mock_account(is_authenticated=False)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                import iobox.providers.outlook_auth as mod
                mod.get_outlook_account(device_code=True)

        call_kwargs = mock_account.authenticate.call_args.kwargs
        assert call_kwargs.get("grant_type") == "device_code"

    def test_device_code_scopes_passed(self, tmp_path):
        mock_account = _make_mock_account(is_authenticated=False)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                import iobox.providers.outlook_auth as mod
                mod.get_outlook_account(device_code=True)

        call_kwargs = mock_account.authenticate.call_args.kwargs
        assert "Mail.ReadWrite" in call_kwargs["scopes"]
        assert "Mail.Send" in call_kwargs["scopes"]

    def test_device_code_skipped_if_already_authenticated(self, tmp_path):
        """device_code flow should NOT be triggered when already authenticated."""
        mock_account = _make_mock_account(is_authenticated=True)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                import iobox.providers.outlook_auth as mod
                mod.get_outlook_account(device_code=True)

        mock_account.authenticate.assert_not_called()


# ---------------------------------------------------------------------------
# Token file path and Account construction
# ---------------------------------------------------------------------------


class TestTokenFilePath:
    def test_token_stored_under_outlook_token_dir(self, tmp_path):
        """FileSystemTokenBackend must receive the outlook token dir and filename."""
        mock_token_backend = MagicMock()
        mock_token_backend_cls = MagicMock(return_value=mock_token_backend)
        mock_account = _make_mock_account(is_authenticated=True)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(
            mock_account_cls=mock_account_cls,
            mock_token_backend_cls=mock_token_backend_cls,
        )
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-client-id", token_dir=token_dir),
            ):
                with patch("os.makedirs") as mock_makedirs:
                    import iobox.providers.outlook_auth as mod
                    mod.get_outlook_account()

        mock_makedirs.assert_called_once_with(token_dir, exist_ok=True)
        mock_token_backend_cls.assert_called_once_with(
            token_path=token_dir, token_filename="o365_token.txt"
        )

    def test_account_constructed_with_credentials_and_tenant(self, tmp_path):
        """Account() must receive (client_id, client_secret) tuple and tenant_id."""
        mock_token_backend = MagicMock()
        mock_token_backend_cls = MagicMock(return_value=mock_token_backend)
        mock_account = _make_mock_account(is_authenticated=True)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(
            mock_account_cls=mock_account_cls,
            mock_token_backend_cls=mock_token_backend_cls,
        )
        token_dir = str(tmp_path / "tokens" / "outlook")

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(
                    client_id="my-client-id",
                    client_secret="my-secret",
                    tenant_id="my-tenant",
                    token_dir=token_dir,
                ),
            ):
                with patch("os.makedirs"):
                    import iobox.providers.outlook_auth as mod
                    mod.get_outlook_account()

        mock_account_cls.assert_called_once_with(
            ("my-client-id", "my-secret"),
            tenant_id="my-tenant",
            token_backend=mock_token_backend,
        )


# ---------------------------------------------------------------------------
# check_outlook_auth_status
# ---------------------------------------------------------------------------


class TestCheckOutlookAuthStatus:
    def test_returns_not_authenticated_when_no_client_id(self):
        with patch(
            "iobox.providers.outlook_auth._get_config",
            return_value=_cfg(client_id=""),
        ):
            import iobox.providers.outlook_auth as mod
            status = mod.check_outlook_auth_status()

        assert status["authenticated"] is False
        assert status["client_id_configured"] is False

    def test_returns_not_authenticated_when_token_file_missing(self, tmp_path):
        non_existent_dir = str(tmp_path / "tokens" / "outlook")
        with patch(
            "iobox.providers.outlook_auth._get_config",
            return_value=_cfg(client_id="test-id", token_dir=non_existent_dir),
        ):
            import iobox.providers.outlook_auth as mod
            status = mod.check_outlook_auth_status()

        assert status["authenticated"] is False
        assert status["client_id_configured"] is True
        assert status["token_file_exists"] is False

    def test_returns_authenticated_when_token_valid(self, tmp_path):
        token_dir = tmp_path / "tokens" / "outlook"
        token_dir.mkdir(parents=True)
        (token_dir / "o365_token.txt").write_text("{}")

        mock_account = _make_mock_account(is_authenticated=True)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-id", token_dir=str(token_dir)),
            ):
                import iobox.providers.outlook_auth as mod
                status = mod.check_outlook_auth_status()

        assert status["authenticated"] is True
        assert status["token_file_exists"] is True
        assert status["client_id_configured"] is True

    def test_returns_not_authenticated_when_token_invalid(self, tmp_path):
        token_dir = tmp_path / "tokens" / "outlook"
        token_dir.mkdir(parents=True)
        (token_dir / "o365_token.txt").write_text("{}")

        mock_account = _make_mock_account(is_authenticated=False)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-id", token_dir=str(token_dir)),
            ):
                import iobox.providers.outlook_auth as mod
                status = mod.check_outlook_auth_status()

        assert status["authenticated"] is False

    def test_includes_error_on_exception(self, tmp_path):
        token_dir = tmp_path / "tokens" / "outlook"
        token_dir.mkdir(parents=True)
        (token_dir / "o365_token.txt").write_text("{}")

        mock_account_cls = MagicMock(side_effect=Exception("unexpected error"))
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-id", token_dir=str(token_dir)),
            ):
                import iobox.providers.outlook_auth as mod
                status = mod.check_outlook_auth_status()

        assert status["authenticated"] is False
        assert "error" in status
        assert "unexpected error" in status["error"]

    def test_includes_error_when_o365_not_installed(self, tmp_path):
        token_dir = tmp_path / "tokens" / "outlook"
        token_dir.mkdir(parents=True)
        (token_dir / "o365_token.txt").write_text("{}")

        # Remove O365 from sys.modules to simulate it not being installed
        saved = sys.modules.pop("O365", None)
        try:
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-id", token_dir=str(token_dir)),
            ):
                import iobox.providers.outlook_auth as mod
                status = mod.check_outlook_auth_status()
        finally:
            if saved is not None:
                sys.modules["O365"] = saved

        assert status["authenticated"] is False
        assert "error" in status

    def test_token_path_in_status(self, tmp_path):
        token_dir = tmp_path / "tokens" / "outlook"
        expected_path = str(token_dir / "o365_token.txt")

        with patch(
            "iobox.providers.outlook_auth._get_config",
            return_value=_cfg(client_id="test-id", token_dir=str(token_dir)),
        ):
            import iobox.providers.outlook_auth as mod
            status = mod.check_outlook_auth_status()

        assert status["token_path"] == expected_path

    def test_tenant_id_in_status(self):
        with patch(
            "iobox.providers.outlook_auth._get_config",
            return_value=_cfg(client_id="", tenant_id="mytenant"),
        ):
            import iobox.providers.outlook_auth as mod
            status = mod.check_outlook_auth_status()

        assert status["tenant_id"] == "mytenant"

    def test_does_not_trigger_auth_flow(self, tmp_path):
        """check_outlook_auth_status must never call account.authenticate()."""
        token_dir = tmp_path / "tokens" / "outlook"
        token_dir.mkdir(parents=True)
        (token_dir / "o365_token.txt").write_text("{}")

        mock_account = _make_mock_account(is_authenticated=True)
        mock_account_cls = MagicMock(return_value=mock_account)
        o365 = _make_o365_module(mock_account_cls=mock_account_cls)

        with patch.dict(sys.modules, {"O365": o365}):
            with patch(
                "iobox.providers.outlook_auth._get_config",
                return_value=_cfg(client_id="test-id", token_dir=str(token_dir)),
            ):
                import iobox.providers.outlook_auth as mod
                mod.check_outlook_auth_status()

        mock_account.authenticate.assert_not_called()


# ---------------------------------------------------------------------------
# OUTLOOK_SCOPES constant
# ---------------------------------------------------------------------------


class TestOutlookScopes:
    def test_scopes_contain_mail_readwrite(self):
        import iobox.providers.outlook_auth as mod
        assert "Mail.ReadWrite" in mod.OUTLOOK_SCOPES

    def test_scopes_contain_mail_send(self):
        import iobox.providers.outlook_auth as mod
        assert "Mail.Send" in mod.OUTLOOK_SCOPES

    def test_exactly_two_scopes(self):
        import iobox.providers.outlook_auth as mod
        assert len(mod.OUTLOOK_SCOPES) == 2


# ---------------------------------------------------------------------------
# _get_config isolation — patching os.getenv after import takes effect
# ---------------------------------------------------------------------------


class TestGetConfigIsolation:
    def test_patching_os_getenv_after_import_changes_client_id(self):
        """Demonstrate that patching os.getenv after import works via _get_config()."""
        import iobox.providers.outlook_auth as mod

        with patch.dict(os.environ, {"OUTLOOK_CLIENT_ID": "patched-id"}, clear=False):
            cfg = mod._get_config()

        assert cfg["client_id"] == "patched-id"

    def test_patching_os_getenv_after_import_changes_tenant_id(self):
        """Patching OUTLOOK_TENANT_ID in the env is reflected by _get_config()."""
        import iobox.providers.outlook_auth as mod

        with patch.dict(os.environ, {"OUTLOOK_TENANT_ID": "my-tenant"}, clear=False):
            cfg = mod._get_config()

        assert cfg["tenant_id"] == "my-tenant"
