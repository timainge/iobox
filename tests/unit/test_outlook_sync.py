"""
Unit tests for OutlookProvider delta sync (O365-11).

Runs the real python-o365 ``Connection`` (which raises ``requests.HTTPError``
for 4xx/5xx) over a fake Graph session.
"""

from __future__ import annotations

import pytest

pytest.importorskip("O365")

from iobox.providers.o365.auth import IMMUTABLE_ID_PREFER  # noqa: E402
from tests.fixtures.mock_outlook_responses import (  # noqa: E402
    DELTA_ROOT,
    MOCK_DELTA_RESPONSE,
    MOCK_DELTA_RESPONSE_EMPTY,
    MOCK_DELTA_RESPONSE_EXPIRED,
    MOCK_DELTA_RESPONSE_WITH_REMOVED,
    FakeOutlookTenant,
    make_outlook_provider,
)

DELTA_PATH = r"/me/mailFolders/inbox/messages/delta"


@pytest.fixture
def provider():
    return make_outlook_provider(FakeOutlookTenant())


@pytest.fixture
def graph(provider):
    return provider.tenant.graph


def _pages(graph, *pages):
    """Serve successive delta responses for every request to the delta path."""
    it = iter(pages)
    graph.route("GET", DELTA_PATH, lambda call: next(it))


class TestGetSyncState:
    def test_initial_sync_returns_delta_link_and_selects_ids(self, provider, graph) -> None:
        _pages(graph, MOCK_DELTA_RESPONSE)
        assert provider.get_sync_state() == MOCK_DELTA_RESPONSE["@odata.deltaLink"]
        call = graph.last("GET", DELTA_PATH)
        assert call.url == DELTA_ROOT  # no double slash, /me resource
        assert call.params["$select"] == "id"
        assert IMMUTABLE_ID_PREFER in call.headers["Prefer"]

    def test_multi_page(self, provider, graph) -> None:
        _pages(
            graph,
            {"value": [{"id": "a"}], "@odata.nextLink": f"{DELTA_ROOT}?$skiptoken=p2"},
            MOCK_DELTA_RESPONSE_EMPTY,
        )
        assert provider.get_sync_state() == MOCK_DELTA_RESPONSE_EMPTY["@odata.deltaLink"]
        second = graph.find("GET", DELTA_PATH)[1]
        assert second.params == {"$skiptoken": "p2"}  # $select not re-sent

    def test_neither_link_raises(self, provider, graph) -> None:
        _pages(graph, {"value": []})
        with pytest.raises(RuntimeError, match="neither"):
            provider.get_sync_state()


class TestGetNewMessages:
    def test_returns_new_ids(self, provider, graph) -> None:
        _pages(graph, MOCK_DELTA_RESPONSE)
        token = f"{DELTA_ROOT}?$deltatoken=prev"
        assert provider.get_new_messages(token) == ["outlook-msg-id-1", "outlook-msg-id-2"]
        assert graph.last("GET", DELTA_PATH).params == {"$deltatoken": "prev"}

    def test_removed_items_are_not_new(self, provider, graph) -> None:
        """Old code counted ``@removed`` (deleted / moved-out) items as new."""
        _pages(graph, MOCK_DELTA_RESPONSE_WITH_REMOVED)
        assert provider.get_new_messages(f"{DELTA_ROOT}?$deltatoken=x") == ["outlook-msg-id-1"]

    def test_duplicates_across_pages_collapsed(self, provider, graph) -> None:
        _pages(
            graph,
            {"value": [{"id": "a"}, {"name": "no id"}], "@odata.nextLink": f"{DELTA_ROOT}?p=2"},
            {"value": [{"id": "a"}, {"id": "b"}], "@odata.deltaLink": f"{DELTA_ROOT}?d=3"},
        )
        assert provider.get_new_messages(f"{DELTA_ROOT}?d=1") == ["a", "b"]

    def test_empty(self, provider, graph) -> None:
        _pages(graph, MOCK_DELTA_RESPONSE_EMPTY)
        assert provider.get_new_messages(f"{DELTA_ROOT}?$deltatoken=x") == []


class TestExpiredToken:
    """python-o365 raises HTTPError on 410; the old code checked
    ``resp.status_code`` after the fact and never saw it."""

    def test_410_returns_none(self, provider, graph) -> None:
        graph.route("GET", DELTA_PATH, MOCK_DELTA_RESPONSE_EXPIRED, status=410)
        assert provider.get_new_messages(f"{DELTA_ROOT}?$deltatoken=old") is None
        assert provider.get_new_messages_with_token(f"{DELTA_ROOT}?$deltatoken=old") is None

    def test_sync_state_not_found_400_returns_none(self, provider, graph) -> None:
        graph.route(
            "GET",
            DELTA_PATH,
            {"error": {"code": "SyncStateNotFound", "message": "gone"}},
            status=400,
        )
        assert provider.get_new_messages(f"{DELTA_ROOT}?$deltatoken=old") is None

    def test_other_errors_propagate(self, provider, graph) -> None:
        import requests

        graph.route("GET", DELTA_PATH, {"error": {"code": "Boom", "message": "x"}}, status=500)
        with pytest.raises(requests.HTTPError):
            provider.get_new_messages(f"{DELTA_ROOT}?$deltatoken=old")


class TestGetNewMessagesWithToken:
    def test_returns_ids_and_new_delta(self, provider, graph) -> None:
        _pages(graph, MOCK_DELTA_RESPONSE)
        ids, link = provider.get_new_messages_with_token(f"{DELTA_ROOT}?$deltatoken=x")
        assert ids == ["outlook-msg-id-1", "outlook-msg-id-2"]
        assert link == MOCK_DELTA_RESPONSE["@odata.deltaLink"]


def test_delta_url(provider) -> None:
    assert provider._get_inbox_delta_url() == DELTA_ROOT
