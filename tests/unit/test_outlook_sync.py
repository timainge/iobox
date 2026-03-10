"""
Unit tests for OutlookProvider delta sync operations.

Tests cover:
- Normal delta response with new message IDs
- 410-Gone fallback (expired delta token) returning None
- Initial sync with no token (get_sync_state)
- Multi-page delta responses
- get_new_messages_with_token returning both IDs and refreshed delta link
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iobox.providers.outlook import OutlookProvider
from tests.fixtures.mock_outlook_responses import (
    MockHttpResponse,
    make_full_mock_account,
    make_mock_account,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> OutlookProvider:
    """Return an OutlookProvider pre-wired with a full mock account."""
    p = OutlookProvider()
    account = make_full_mock_account()
    p._account = account
    p._mailbox = account.mailbox()
    return p


@pytest.fixture
def sync_provider() -> OutlookProvider:
    """Provider with protocol stub for delta URL construction."""
    p = OutlookProvider()
    account = make_mock_account()
    p._account = account
    p._mailbox = account.mailbox()
    # Set up protocol for _get_inbox_delta_url
    p._account.con.protocol = MagicMock()
    p._account.con.protocol.service_url = "https://graph.microsoft.com/v1.0"
    return p


# ---------------------------------------------------------------------------
# get_sync_state — initial sync with no token
# ---------------------------------------------------------------------------


class TestGetSyncState:
    def test_initial_sync_returns_delta_link(self, sync_provider):
        """First-time sync walks all pages and returns the deltaLink."""
        delta_url = sync_provider._get_inbox_delta_url()
        delta_link = (
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            "/delta?$deltatoken=initial123"
        )
        # Register a response for the initial delta URL
        sync_provider._account.con._delta_responses[delta_url] = {
            "value": [
                {"id": "existing-msg-1"},
                {"id": "existing-msg-2"},
                {"id": "existing-msg-3"},
            ],
            "@odata.deltaLink": delta_link,
        }

        result = sync_provider.get_sync_state()
        assert result == delta_link

    def test_initial_sync_empty_inbox(self, sync_provider):
        """Initial sync on an empty inbox still returns a valid deltaLink."""
        delta_url = sync_provider._get_inbox_delta_url()
        delta_link = (
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            "/delta?$deltatoken=empty000"
        )
        sync_provider._account.con._delta_responses[delta_url] = {
            "value": [],
            "@odata.deltaLink": delta_link,
        }

        result = sync_provider.get_sync_state()
        assert result == delta_link

    def test_initial_sync_multi_page(self, sync_provider):
        """Initial sync follows @odata.nextLink pages before returning deltaLink."""
        delta_url = sync_provider._get_inbox_delta_url()
        page2_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=page2"
        final_delta = "https://graph.microsoft.com/v1.0/delta?$deltatoken=final"

        # Page 1 has nextLink
        sync_provider._account.con._delta_responses[delta_url] = {
            "value": [{"id": "msg-page1"}],
            "@odata.nextLink": page2_url,
        }
        # Page 2 has deltaLink
        sync_provider._account.con._delta_responses[page2_url] = {
            "value": [{"id": "msg-page2"}],
            "@odata.deltaLink": final_delta,
        }

        result = sync_provider.get_sync_state()
        assert result == final_delta

    def test_initial_sync_no_delta_link_raises(self, sync_provider):
        """RuntimeError if the response has neither nextLink nor deltaLink."""
        delta_url = sync_provider._get_inbox_delta_url()
        sync_provider._account.con._delta_responses[delta_url] = {
            "value": [{"id": "msg-1"}],
            # No @odata.deltaLink or @odata.nextLink
        }

        with pytest.raises(RuntimeError, match="neither"):
            sync_provider.get_sync_state()


# ---------------------------------------------------------------------------
# get_new_messages — normal delta response
# ---------------------------------------------------------------------------


class TestGetNewMessagesNormal:
    def test_returns_new_message_ids(self, sync_provider):
        """Normal delta returns a list of message IDs."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=abc"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=def"
        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [
                {"id": "new-msg-1"},
                {"id": "new-msg-2"},
            ],
            "@odata.deltaLink": new_delta,
        }

        result = sync_provider.get_new_messages(delta_link)
        assert result == ["new-msg-1", "new-msg-2"]

    def test_returns_empty_list_when_no_changes(self, sync_provider):
        """Delta with no new messages returns an empty list."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=unchanged"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=still_unchanged"
        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [],
            "@odata.deltaLink": new_delta,
        }

        result = sync_provider.get_new_messages(delta_link)
        assert result == []

    def test_includes_ids_from_removed_items(self, sync_provider):
        """Items with @removed annotation still have their ID collected."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=with_removed"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=after_removed"
        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [
                {"id": "new-msg-1", "subject": "New"},
                {"id": "removed-msg-1", "@removed": {"reason": "deleted"}},
            ],
            "@odata.deltaLink": new_delta,
        }

        result = sync_provider.get_new_messages(delta_link)
        # Both IDs should be returned — caller decides what to do with removed items
        assert "new-msg-1" in result
        assert "removed-msg-1" in result

    def test_skips_items_without_id(self, sync_provider):
        """Items missing the 'id' field are silently skipped."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=noid"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=after_noid"
        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [
                {"id": "valid-msg"},
                {"subject": "Missing ID entry"},  # No "id" key
            ],
            "@odata.deltaLink": new_delta,
        }

        result = sync_provider.get_new_messages(delta_link)
        assert result == ["valid-msg"]

    def test_multi_page_delta(self, sync_provider):
        """Delta response spanning multiple pages collects all IDs."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=multipage"
        page2_url = "https://graph.microsoft.com/v1.0/delta?$skiptoken=p2"
        final_delta = "https://graph.microsoft.com/v1.0/delta?token=final"

        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [{"id": "msg-p1-1"}, {"id": "msg-p1-2"}],
            "@odata.nextLink": page2_url,
        }
        sync_provider._account.con._delta_responses[page2_url] = {
            "value": [{"id": "msg-p2-1"}],
            "@odata.deltaLink": final_delta,
        }

        result = sync_provider.get_new_messages(delta_link)
        assert result == ["msg-p1-1", "msg-p1-2", "msg-p2-1"]


# ---------------------------------------------------------------------------
# get_new_messages — 410-Gone fallback
# ---------------------------------------------------------------------------


class TestGetNewMessages410Gone:
    def test_expired_token_returns_none(self, sync_provider):
        """HTTP 410 response signals full re-sync needed by returning None."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=expired"
        gone_resp = MockHttpResponse({})
        gone_resp.status_code = 410
        sync_provider._account.con.get = MagicMock(return_value=gone_resp)

        result = sync_provider.get_new_messages(delta_link)
        assert result is None

    def test_410_gone_with_error_body(self, sync_provider):
        """410 with SyncStateNotFound error body still returns None."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=stale"
        gone_resp = MockHttpResponse({
            "error": {
                "code": "SyncStateNotFound",
                "message": "deltaLink has expired",
            }
        })
        gone_resp.status_code = 410
        sync_provider._account.con.get = MagicMock(return_value=gone_resp)

        result = sync_provider.get_new_messages(delta_link)
        assert result is None


# ---------------------------------------------------------------------------
# get_new_messages_with_token — returns (ids, new_delta_link)
# ---------------------------------------------------------------------------


class TestGetNewMessagesWithToken:
    def test_returns_ids_and_new_delta(self, sync_provider):
        """Normal response returns a (message_ids, new_delta_link) tuple."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=abc"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=refreshed"
        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [{"id": "msg-1"}, {"id": "msg-2"}],
            "@odata.deltaLink": new_delta,
        }

        result = sync_provider.get_new_messages_with_token(delta_link)
        assert result is not None
        ids, link = result
        assert ids == ["msg-1", "msg-2"]
        assert link == new_delta

    def test_empty_delta_returns_empty_ids_and_new_link(self, sync_provider):
        """No changes returns ([], new_delta_link)."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=quiet"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=still_quiet"
        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [],
            "@odata.deltaLink": new_delta,
        }

        result = sync_provider.get_new_messages_with_token(delta_link)
        assert result is not None
        ids, link = result
        assert ids == []
        assert link == new_delta

    def test_410_gone_returns_none(self, sync_provider):
        """Expired token returns None for the tuple variant too."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=old"
        gone_resp = MockHttpResponse({})
        gone_resp.status_code = 410
        sync_provider._account.con.get = MagicMock(return_value=gone_resp)

        result = sync_provider.get_new_messages_with_token(delta_link)
        assert result is None

    def test_multi_page_returns_all_ids(self, sync_provider):
        """Paged delta response aggregates IDs across pages."""
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=paged"
        page2 = "https://graph.microsoft.com/v1.0/delta?skip=2"
        final = "https://graph.microsoft.com/v1.0/delta?token=done"

        sync_provider._account.con._delta_responses[delta_link] = {
            "value": [{"id": "a"}],
            "@odata.nextLink": page2,
        }
        sync_provider._account.con._delta_responses[page2] = {
            "value": [{"id": "b"}],
            "@odata.deltaLink": final,
        }

        result = sync_provider.get_new_messages_with_token(delta_link)
        assert result is not None
        ids, link = result
        assert ids == ["a", "b"]
        assert link == final


# ---------------------------------------------------------------------------
# _get_inbox_delta_url
# ---------------------------------------------------------------------------


class TestGetInboxDeltaUrl:
    def test_constructs_correct_url(self, sync_provider):
        url = sync_provider._get_inbox_delta_url()
        assert url == (
            "https://graph.microsoft.com/v1.0"
            "/me/mailFolders/inbox/messages/delta"
        )
