"""Tests for the TokenStore protocol + FilesystemTokenStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from iobox.providers.token_store import FilesystemTokenStore, TokenStore


def test_filesystem_store_implements_protocol(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    assert isinstance(store, TokenStore)


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    payload = {"refresh_token": "r", "client_id": "c", "client_secret": "s"}
    store.save("alice@gmail.com", "readonly", payload)
    assert store.load("alice@gmail.com", "readonly") == payload


def test_load_returns_none_when_missing(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    assert store.load("nobody", "readonly") is None


def test_save_writes_to_account_namespaced_path(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    store.save("bob", "standard", {"token": "x"})
    expected = tmp_path / "tokens" / "bob" / "token_standard.json"
    assert expected.exists()


def test_save_overwrites(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    store.save("alice", "readonly", {"v": 1})
    store.save("alice", "readonly", {"v": 2})
    assert store.load("alice", "readonly") == {"v": 2}


def test_delete_removes_file(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    store.save("alice", "readonly", {"v": 1})
    store.delete("alice", "readonly")
    assert store.load("alice", "readonly") is None


def test_delete_missing_is_noop(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    # No exception — delete is idempotent.
    store.delete("ghost", "readonly")


def test_load_returns_none_on_corrupt_json(tmp_path: Path) -> None:
    store = FilesystemTokenStore(tmp_path)
    path = tmp_path / "tokens" / "alice" / "token_readonly.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json {{{")
    assert store.load("alice", "readonly") is None


def test_in_memory_store_satisfies_protocol() -> None:
    """A trivial alternate impl proves the Protocol is structural-only."""

    class InMemoryStore:
        def __init__(self) -> None:
            self.data: dict[tuple[str, str], dict] = {}

        def load(self, account: str, tier: str) -> dict | None:
            return self.data.get((account, tier))

        def save(self, account: str, tier: str, token: dict) -> None:
            self.data[(account, tier)] = token

        def delete(self, account: str, tier: str) -> None:
            self.data.pop((account, tier), None)

    store = InMemoryStore()
    assert isinstance(store, TokenStore)
    store.save("a", "r", {"x": 1})
    assert store.load("a", "r") == {"x": 1}


@pytest.mark.parametrize("tier", ["readonly", "standard"])
def test_tier_segregates_storage(tmp_path: Path, tier: str) -> None:
    store = FilesystemTokenStore(tmp_path)
    other = "standard" if tier == "readonly" else "readonly"
    store.save("alice", tier, {"tier": tier})
    assert store.load("alice", other) is None
    assert store.load("alice", tier) == {"tier": tier}
