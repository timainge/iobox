"""Tests for the process-wide interactive OAuth policy (MCP-02)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from iobox.auth_policy import (
    InteractiveAuthRequired,
    interactive_auth_allowed,
    set_interactive_auth,
)


@pytest.fixture(autouse=True)
def _restore_policy():
    yield
    set_interactive_auth(True)


class TestInteractiveAuthPolicy:
    def test_allowed_by_default(self) -> None:
        assert interactive_auth_allowed()

    def test_google_auth_refuses_consent_flow_when_disabled(self, tmp_path) -> None:
        from iobox.providers.google.auth import GoogleAuth

        (tmp_path / "credentials.json").write_text("{}")
        auth = GoogleAuth(account="me@gmail.com", scopes=["s"], credentials_dir=str(tmp_path))
        set_interactive_auth(False)
        with patch("iobox.providers.google.auth.InstalledAppFlow") as flow:
            with pytest.raises(InteractiveAuthRequired, match="iobox space login"):
                auth.get_credentials()
        flow.from_client_secrets_file.assert_not_called()

    def test_mcp_main_disables_interactive_auth(self) -> None:
        pytest.importorskip("mcp")
        import iobox.mcp_server as srv

        with (
            patch.object(srv.mcp, "run"),
            patch.object(srv, "register_tools"),
            patch.object(srv, "set_active_mode"),
            patch("iobox.accounts.set_active_account"),
        ):
            srv.main()
        assert not interactive_auth_allowed()


class TestMicrosoftInteractivePolicy:
    def test_microsoft_auth_refuses_flow_when_disabled(self, tmp_path) -> None:
        pytest.importorskip("O365")
        from iobox.providers.o365.auth import MicrosoftAuth

        auth = MicrosoftAuth(
            account="corp@company.com",
            scopes=["basic", "Mail.Read"],
            credentials_dir=str(tmp_path),
            client_id="00000000-0000-0000-0000-000000000000",
        )
        set_interactive_auth(False)
        account = MagicMock()
        with pytest.raises(InteractiveAuthRequired):
            auth._run_auth_flow(account)
        account.authenticate.assert_not_called()
