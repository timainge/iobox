"""
Unit tests for Workspace write operation routing (task-017).

Verifies that get_message_provider() resolves the correct slot and that
_check_write_mode() enforces readonly mode gating.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iobox.workspace import ProviderSlot, Workspace, WorkspaceSession


def _make_ws_with_providers(*slots: tuple[str, str]) -> Workspace:
    """Build a Workspace with message provider slots.

    Each slot is a (name, mode) tuple. The provider mock exposes a .mode attr.
    """
    ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
    for name, mode in slots:
        provider = MagicMock()
        provider.mode = mode
        ws.message_providers.append(ProviderSlot(name=name, provider=provider))
    return ws


# ---------------------------------------------------------------------------
# get_message_provider
# ---------------------------------------------------------------------------


class TestGetMessageProvider:
    def test_returns_first_slot_by_default(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"), ("gmail-work", "standard"))
        p = ws.get_message_provider()
        assert p is ws.message_providers[0].provider

    def test_returns_named_slot(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"), ("outlook-work", "readonly"))
        p = ws.get_message_provider("outlook-work")
        assert p is ws.message_providers[1].provider

    def test_raises_when_no_providers(self):
        ws = Workspace(name="empty", session=WorkspaceSession(workspace_name="empty"))
        with pytest.raises(ValueError, match="No message providers"):
            ws.get_message_provider()

    def test_raises_for_unknown_slot_name(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        with pytest.raises(ValueError, match="nonexistent"):
            ws.get_message_provider("nonexistent")

    def test_error_message_includes_available_slots(self):
        ws = _make_ws_with_providers(("slot-a", "standard"), ("slot-b", "standard"))
        with pytest.raises(ValueError, match="slot-a"):
            ws.get_message_provider("missing")


# ---------------------------------------------------------------------------
# _check_write_mode
# ---------------------------------------------------------------------------


class TestCheckWriteMode:
    def test_allows_standard_mode(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        # Should not raise
        ws._check_write_mode()

    def test_allows_dangerous_mode(self):
        ws = _make_ws_with_providers(("gmail-personal", "dangerous"))
        ws._check_write_mode()

    def test_blocks_readonly_mode(self):
        ws = _make_ws_with_providers(("gmail-personal", "readonly"))
        with pytest.raises(PermissionError, match="readonly mode"):
            ws._check_write_mode()

    def test_blocks_named_readonly_slot(self):
        ws = _make_ws_with_providers(
            ("gmail-personal", "standard"),
            ("outlook-work", "readonly"),
        )
        with pytest.raises(PermissionError, match="readonly mode"):
            ws._check_write_mode("outlook-work")

    def test_allows_standard_when_named(self):
        ws = _make_ws_with_providers(
            ("gmail-personal", "readonly"),
            ("gmail-work", "standard"),
        )
        # Targeting the standard slot by name — should succeed
        ws._check_write_mode("gmail-work")

    def test_does_nothing_when_no_matching_slot(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        # No slot named "nonexistent" — no PermissionError (get_message_provider raises later)
        ws._check_write_mode("nonexistent")

    def test_does_nothing_when_provider_has_no_mode_attr(self):
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        provider = MagicMock(spec=[])  # no .mode attribute
        ws.message_providers.append(ProviderSlot(name="slot", provider=provider))
        # Should not raise
        ws._check_write_mode()


# ---------------------------------------------------------------------------
# write op delegation via get_message_provider
# ---------------------------------------------------------------------------


class TestWriteOpDelegation:
    """Verify that callers can use get_message_provider() + provider methods."""

    def test_send_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_message_provider()
        provider.send_message.return_value = {"message_id": "sent-1"}
        result = provider.send_message(
            to="bob@example.com", subject="Hi", body="Hello", content_type="plain"
        )
        assert result["message_id"] == "sent-1"

    def test_forward_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_message_provider()
        provider.forward_message.return_value = {"message_id": "fwd-1"}
        result = provider.forward_message(message_id="m1", to="alice@example.com")
        assert result["message_id"] == "fwd-1"

    def test_trash_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_message_provider()
        provider.trash("m1")
        provider.trash.assert_called_once_with("m1")

    def test_untrash_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_message_provider()
        provider.untrash("m1")
        provider.untrash.assert_called_once_with("m1")
