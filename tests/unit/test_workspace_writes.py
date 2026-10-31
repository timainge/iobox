"""
Unit tests for Workspace write operation routing (task-017).

Verifies that get_email_provider() / get_calendar_provider() /
get_file_provider() resolve the correct slot.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iobox.workspace import ProviderSlot, Workspace


def _make_ws_with_providers(*slots: tuple[str, str]) -> Workspace:
    """Build a Workspace with message provider slots.

    Each slot is a (name, mode) tuple. The provider mock exposes a .mode attr.
    """
    ws = Workspace(name="test")
    for name, mode in slots:
        provider = MagicMock()
        provider.mode = mode
        ws.email_providers.append(ProviderSlot(name=name, provider=provider))
    return ws


# ---------------------------------------------------------------------------
# get_email_provider
# ---------------------------------------------------------------------------


class TestGetEmailProvider:
    def test_returns_first_slot_by_default(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"), ("gmail-work", "standard"))
        p = ws.get_email_provider()
        assert p is ws.email_providers[0].provider

    def test_returns_named_slot(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"), ("outlook-work", "readonly"))
        p = ws.get_email_provider("outlook-work")
        assert p is ws.email_providers[1].provider

    def test_raises_when_no_providers(self):
        ws = Workspace(name="empty")
        with pytest.raises(ValueError, match="No email providers"):
            ws.get_email_provider()

    def test_raises_for_unknown_slot_name(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        with pytest.raises(ValueError, match="nonexistent"):
            ws.get_email_provider("nonexistent")

    def test_error_message_includes_available_slots(self):
        ws = _make_ws_with_providers(("slot-a", "standard"), ("slot-b", "standard"))
        with pytest.raises(ValueError, match="slot-a"):
            ws.get_email_provider("missing")


# ---------------------------------------------------------------------------
# get_calendar_provider / get_file_provider
# ---------------------------------------------------------------------------


class TestGetOtherProviders:
    def _ws(self) -> Workspace:
        return Workspace(
            name="test",
            calendar_providers=[
                ProviderSlot(name="a-cal", provider=MagicMock()),
                ProviderSlot(name="b-cal", provider=MagicMock()),
            ],
            file_providers=[ProviderSlot(name="a-drive", provider=MagicMock())],
        )

    def test_calendar_named_slot(self):
        ws = self._ws()
        assert ws.get_calendar_provider("b-cal") is ws.calendar_providers[1].provider

    def test_calendar_default_first(self):
        ws = self._ws()
        assert ws.get_calendar_provider() is ws.calendar_providers[0].provider

    def test_file_named_slot(self):
        ws = self._ws()
        assert ws.get_file_provider("a-drive") is ws.file_providers[0].provider

    def test_unknown_slot_lists_available(self):
        with pytest.raises(ValueError, match="a-cal"):
            self._ws().get_calendar_provider("missing")

    def test_no_file_providers(self):
        with pytest.raises(ValueError, match="No file providers"):
            Workspace(name="x").get_file_provider()

    def test_dead_write_mode_helper_removed(self):
        # Readonly gating lives in providers / CLI / MCP, not on Workspace.
        assert not hasattr(Workspace, "_check_write_mode")


# ---------------------------------------------------------------------------
# write op delegation via get_email_provider
# ---------------------------------------------------------------------------


class TestWriteOpDelegation:
    """Verify that callers can use get_email_provider() + provider methods."""

    def test_send_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_email_provider()
        provider.send_message.return_value = {"message_id": "sent-1"}
        result = provider.send_message(
            to="bob@example.com", subject="Hi", body="Hello", content_type="plain"
        )
        assert result["message_id"] == "sent-1"

    def test_forward_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_email_provider()
        provider.forward_message.return_value = {"message_id": "fwd-1"}
        result = provider.forward_message(message_id="m1", to="alice@example.com")
        assert result["message_id"] == "fwd-1"

    def test_trash_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_email_provider()
        provider.trash("m1")
        provider.trash.assert_called_once_with("m1")

    def test_untrash_via_provider(self):
        ws = _make_ws_with_providers(("gmail-personal", "standard"))
        provider = ws.get_email_provider()
        provider.untrash("m1")
        provider.untrash.assert_called_once_with("m1")
