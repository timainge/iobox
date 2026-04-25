"""Tests for the TokenStoreTokenBackend adapter (o365 → TokenStore)."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("O365")  # whole module skipped when outlook extra absent

from iobox.providers.o365.auth import TokenStoreTokenBackend  # noqa: E402
from iobox.providers.token_store import TokenStore  # noqa: E402


class _InMemoryStore:
    """Trivial TokenStore impl used as a test double."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict[str, Any]] = {}

    def load(self, account: str, tier: str) -> dict[str, Any] | None:
        return self.data.get((account, tier))

    def save(self, account: str, tier: str, token: dict[str, Any]) -> None:
        self.data[(account, tier)] = token

    def delete(self, account: str, tier: str) -> None:
        self.data.pop((account, tier), None)


def test_implements_token_store_protocol() -> None:
    store = _InMemoryStore()
    assert isinstance(store, TokenStore)


def test_load_returns_false_when_empty() -> None:
    backend = TokenStoreTokenBackend(_InMemoryStore(), "alice")
    assert backend.load_token() is False


def test_save_then_load_round_trips() -> None:
    store = _InMemoryStore()
    backend = TokenStoreTokenBackend(store, "alice")

    # Seed the cache with a small payload that survives a JSON round-trip.
    backend._cache = {"some": "value"}
    backend._has_state_changed = True
    assert backend.save_token() is True
    assert ("alice", "default") in store.data
    persisted = store.data[("alice", "default")]
    assert "_o365" in persisted
    # Sanity: the stored blob is JSON-serializable text.
    assert json.loads(persisted["_o365"]) == {"some": "value"}

    # Fresh backend should re-populate _cache from the store.
    backend2 = TokenStoreTokenBackend(store, "alice")
    assert backend2.load_token() is True
    assert backend2._cache == {"some": "value"}


def test_save_no_op_when_state_unchanged() -> None:
    store = _InMemoryStore()
    backend = TokenStoreTokenBackend(store, "alice")
    backend._cache = {"some": "value"}
    # No state change yet → save should report True (idempotent) without
    # writing to the store.
    assert backend.save_token() is True
    assert store.data == {}


def test_save_force_writes_anyway() -> None:
    store = _InMemoryStore()
    backend = TokenStoreTokenBackend(store, "alice")
    backend._cache = {"some": "value"}
    assert backend.save_token(force=True) is True
    assert ("alice", "default") in store.data


def test_save_empty_cache_returns_false() -> None:
    store = _InMemoryStore()
    backend = TokenStoreTokenBackend(store, "alice")
    backend._cache = {}
    assert backend.save_token(force=True) is False
    assert store.data == {}


def test_delete_token_clears_store() -> None:
    store = _InMemoryStore()
    backend = TokenStoreTokenBackend(store, "alice")
    backend._cache = {"some": "value"}
    backend._has_state_changed = True
    backend.save_token()
    assert backend.delete_token() is True
    assert ("alice", "default") not in store.data


def test_check_token() -> None:
    store = _InMemoryStore()
    backend = TokenStoreTokenBackend(store, "alice")
    assert backend.check_token() is False
    backend._cache = {"some": "value"}
    backend._has_state_changed = True
    backend.save_token()
    assert backend.check_token() is True


def test_account_segregation() -> None:
    """Two accounts → two distinct slots."""
    store = _InMemoryStore()
    a = TokenStoreTokenBackend(store, "alice")
    b = TokenStoreTokenBackend(store, "bob")
    a._cache = {"alice_key": 1}
    a._has_state_changed = True
    a.save_token()
    assert b.load_token() is False
    b._cache = {"bob_key": 2}
    b._has_state_changed = True
    b.save_token()
    assert a.load_token() is True
    assert a._cache == {"alice_key": 1}


def test_load_handles_corrupt_blob() -> None:
    store = _InMemoryStore()
    store.save("alice", "default", {"_o365": "not json {{{"})
    backend = TokenStoreTokenBackend(store, "alice")
    assert backend.load_token() is False
