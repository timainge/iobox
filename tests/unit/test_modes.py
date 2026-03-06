"""
Unit tests for the access modes module.
"""

import pytest

from iobox.modes import (
    CLI_COMMANDS_BY_MODE,
    MCP_TOOLS_BY_MODE,
    SCOPES_BY_MODE,
    AccessMode,
    get_mode_from_env,
)


class TestAccessModeEnum:
    def test_enum_values(self):
        assert AccessMode.readonly.value == "readonly"
        assert AccessMode.standard.value == "standard"
        assert AccessMode.dangerous.value == "dangerous"

    def test_enum_from_string(self):
        assert AccessMode("readonly") is AccessMode.readonly
        assert AccessMode("standard") is AccessMode.standard
        assert AccessMode("dangerous") is AccessMode.dangerous


class TestScopesByMode:
    def test_readonly_has_readonly_scope(self):
        scopes = SCOPES_BY_MODE[AccessMode.readonly]
        assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
        assert "https://www.googleapis.com/auth/gmail.modify" not in scopes

    def test_standard_has_modify_and_compose(self):
        scopes = SCOPES_BY_MODE[AccessMode.standard]
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
        assert "https://www.googleapis.com/auth/gmail.compose" in scopes

    def test_dangerous_same_scopes_as_standard(self):
        assert SCOPES_BY_MODE[AccessMode.dangerous] == SCOPES_BY_MODE[AccessMode.standard]


class TestCliCommandsByMode:
    def test_readonly_subset_of_standard(self):
        assert CLI_COMMANDS_BY_MODE[AccessMode.readonly] < CLI_COMMANDS_BY_MODE[AccessMode.standard]

    def test_standard_subset_of_dangerous(self):
        assert (
            CLI_COMMANDS_BY_MODE[AccessMode.standard] < CLI_COMMANDS_BY_MODE[AccessMode.dangerous]
        )

    def test_readonly_allows_search_and_save(self):
        cmds = CLI_COMMANDS_BY_MODE[AccessMode.readonly]
        assert "search" in cmds
        assert "save" in cmds
        assert "auth-status" in cmds
        assert "version" in cmds
        assert "draft-list" in cmds

    def test_readonly_blocks_send_and_trash(self):
        cmds = CLI_COMMANDS_BY_MODE[AccessMode.readonly]
        assert "send" not in cmds
        assert "trash" not in cmds
        assert "forward" not in cmds
        assert "label" not in cmds

    def test_standard_allows_drafts_and_label(self):
        cmds = CLI_COMMANDS_BY_MODE[AccessMode.standard]
        assert "draft-create" in cmds
        assert "draft-send" in cmds
        assert "draft-delete" in cmds
        assert "label" in cmds

    def test_standard_blocks_send_forward_trash(self):
        cmds = CLI_COMMANDS_BY_MODE[AccessMode.standard]
        assert "send" not in cmds
        assert "forward" not in cmds
        assert "trash" not in cmds

    def test_dangerous_allows_everything(self):
        cmds = CLI_COMMANDS_BY_MODE[AccessMode.dangerous]
        assert "send" in cmds
        assert "forward" in cmds
        assert "trash" in cmds
        assert "label" in cmds
        assert "search" in cmds


class TestMcpToolsByMode:
    def test_readonly_subset_of_standard(self):
        assert MCP_TOOLS_BY_MODE[AccessMode.readonly] < MCP_TOOLS_BY_MODE[AccessMode.standard]

    def test_standard_subset_of_dangerous(self):
        assert MCP_TOOLS_BY_MODE[AccessMode.standard] < MCP_TOOLS_BY_MODE[AccessMode.dangerous]

    def test_readonly_has_search_and_get(self):
        tools = MCP_TOOLS_BY_MODE[AccessMode.readonly]
        assert "search_gmail" in tools
        assert "get_email" in tools
        assert "check_auth" in tools

    def test_readonly_excludes_send(self):
        tools = MCP_TOOLS_BY_MODE[AccessMode.readonly]
        assert "send_email" not in tools
        assert "trash_gmail" not in tools

    def test_dangerous_includes_all(self):
        tools = MCP_TOOLS_BY_MODE[AccessMode.dangerous]
        assert "send_email" in tools
        assert "trash_gmail" in tools
        assert "forward_gmail" in tools


class TestGetModeFromEnv:
    def test_default_is_standard(self, monkeypatch):
        monkeypatch.delenv("IOBOX_MODE", raising=False)
        assert get_mode_from_env() == AccessMode.standard

    def test_reads_readonly(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "readonly")
        assert get_mode_from_env() == AccessMode.readonly

    def test_reads_dangerous(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "dangerous")
        assert get_mode_from_env() == AccessMode.dangerous

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "READONLY")
        assert get_mode_from_env() == AccessMode.readonly

    def test_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("IOBOX_MODE", "invalid")
        with pytest.raises(ValueError, match="Invalid IOBOX_MODE"):
            get_mode_from_env()
