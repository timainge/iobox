"""Tests for src/iobox/space_config.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import iobox.space_config as sc
from iobox.space_config import (
    ServiceEntry,
    ServiceSessionState,
    SpaceConfig,
    SpaceSession,
    _derive_id,
    _derive_slug,
    ensure_iobox_home,
    get_active_space,
    list_spaces,
    load_session,
    load_space,
    save_session,
    save_space,
    set_active_space,
)

# ── Fixture: redirect all path constants to tmp_path ─────────────────────────


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all ~/.iobox/ path constants to a temp directory."""
    iobox_home = tmp_path / ".iobox"
    workspaces = iobox_home / "workspaces"
    tokens = iobox_home / "tokens"
    indexes = iobox_home / "indexes"
    active = iobox_home / "active_space"

    monkeypatch.setattr(sc, "IOBOX_HOME", iobox_home)
    monkeypatch.setattr(sc, "WORKSPACES_DIR", workspaces)
    monkeypatch.setattr(sc, "TOKENS_DIR", tokens)
    monkeypatch.setattr(sc, "INDEXES_DIR", indexes)
    monkeypatch.setattr(sc, "ACTIVE_SPACE_FILE", active)


# ── Derive helpers ────────────────────────────────────────────────────────────


class TestDeriveHelpers:
    def test_derive_id_gmail(self) -> None:
        assert _derive_id("gmail", "tim@gmail.com") == "gmail-timgmailcom"

    def test_derive_id_outlook(self) -> None:
        assert _derive_id("outlook", "corp@megacorp.com") == "outlook-corpmegacorpcom"

    def test_derive_id_strips_special_chars(self) -> None:
        result = _derive_id("gmail", "my.name+tag@example.co.uk")
        assert "@" not in result
        assert "." not in result
        assert result.startswith("gmail-")

    def test_derive_slug_gmail(self) -> None:
        assert _derive_slug("tim@gmail.com") == "tim-gmail"

    def test_derive_slug_outlook(self) -> None:
        assert _derive_slug("corp@megacorp.com") == "corp-megacorp"

    def test_derive_slug_no_at_sign(self) -> None:
        # Graceful fallback
        assert _derive_slug("plainname") == "plainname"

    def test_derive_slug_is_lowercase(self) -> None:
        assert _derive_slug("TIM@GMAIL.COM") == "tim-gmail"


# ── ServiceEntry auto-derive ──────────────────────────────────────────────────


class TestServiceEntry:
    def test_id_auto_derived_when_empty(self) -> None:
        entry = ServiceEntry(
            number=1, service="gmail", account="tim@gmail.com", scopes=["messages"]
        )
        assert entry.id == "gmail-timgmailcom"

    def test_slug_auto_derived_when_empty(self) -> None:
        entry = ServiceEntry(
            number=1, service="gmail", account="tim@gmail.com", scopes=["messages"]
        )
        assert entry.slug == "tim-gmail"

    def test_explicit_id_preserved(self) -> None:
        entry = ServiceEntry(
            number=1, service="gmail", account="tim@gmail.com", scopes=["messages"], id="custom-id"
        )
        assert entry.id == "custom-id"

    def test_explicit_slug_preserved(self) -> None:
        entry = ServiceEntry(
            number=1, service="gmail", account="tim@gmail.com", scopes=["messages"], slug="my-work"
        )
        assert entry.slug == "my-work"

    def test_default_mode_is_standard(self) -> None:
        entry = ServiceEntry(number=1, service="gmail", account="a@b.com", scopes=["messages"])
        assert entry.mode == "standard"


# ── ensure_iobox_home ─────────────────────────────────────────────────────────


class TestEnsureIoboxHome:
    def test_creates_all_directories(self, tmp_path: Path) -> None:
        ensure_iobox_home()
        assert sc.WORKSPACES_DIR.exists()
        assert sc.TOKENS_DIR.exists()
        assert sc.INDEXES_DIR.exists()

    def test_idempotent(self) -> None:
        ensure_iobox_home()
        ensure_iobox_home()  # second call must not raise
        assert sc.WORKSPACES_DIR.exists()


# ── save_space / load_space roundtrip ────────────────────────────────────────


class TestSpaceConfigIO:
    def _make_config(self) -> SpaceConfig:
        return SpaceConfig(
            name="personal",
            services=[
                ServiceEntry(
                    number=1,
                    service="gmail",
                    account="tim@gmail.com",
                    scopes=["messages", "calendar", "drive"],
                    mode="readonly",
                ),
                ServiceEntry(
                    number=2,
                    service="outlook",
                    account="corp@megacorp.com",
                    scopes=["messages"],
                    mode="standard",
                ),
            ],
        )

    def test_save_creates_toml_file(self) -> None:
        config = self._make_config()
        save_space(config)
        path = sc.WORKSPACES_DIR / "personal.toml"
        assert path.exists()

    def test_roundtrip_name(self) -> None:
        save_space(self._make_config())
        loaded = load_space("personal")
        assert loaded.name == "personal"

    def test_roundtrip_service_count(self) -> None:
        save_space(self._make_config())
        loaded = load_space("personal")
        assert len(loaded.services) == 2

    def test_roundtrip_service_fields(self) -> None:
        save_space(self._make_config())
        loaded = load_space("personal")
        svc = loaded.services[0]
        assert svc.service == "gmail"
        assert svc.account == "tim@gmail.com"
        assert svc.scopes == ["messages", "calendar", "drive"]
        assert svc.mode == "readonly"
        assert svc.number == 1

    def test_roundtrip_derived_id_and_slug(self) -> None:
        save_space(self._make_config())
        loaded = load_space("personal")
        svc = loaded.services[0]
        assert svc.id == "gmail-timgmailcom"
        assert svc.slug == "tim-gmail"

    def test_load_missing_space_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Space 'missing'"):
            load_space("missing")

    def test_save_creates_parent_dirs(self) -> None:
        # WORKSPACES_DIR doesn't exist yet
        assert not sc.WORKSPACES_DIR.exists()
        save_space(SpaceConfig(name="new"))
        assert sc.WORKSPACES_DIR.exists()


# ── list_spaces ───────────────────────────────────────────────────────────────


class TestListSpaces:
    def test_empty_when_no_dir(self) -> None:
        assert list_spaces() == []

    def test_empty_when_dir_exists_but_no_toml(self) -> None:
        sc.WORKSPACES_DIR.mkdir(parents=True)
        assert list_spaces() == []

    def test_returns_sorted_names(self) -> None:
        for name in ("work", "personal", "archive"):
            save_space(SpaceConfig(name=name))
        assert list_spaces() == ["archive", "personal", "work"]

    def test_ignores_non_toml_files(self) -> None:
        sc.WORKSPACES_DIR.mkdir(parents=True)
        (sc.WORKSPACES_DIR / "notes.txt").write_text("ignored")
        save_space(SpaceConfig(name="personal"))
        assert list_spaces() == ["personal"]


# ── get_active_space / set_active_space ───────────────────────────────────────


class TestActiveSpace:
    def test_returns_none_when_no_file(self) -> None:
        assert get_active_space() is None

    def test_returns_none_when_file_empty(self) -> None:
        sc.IOBOX_HOME.mkdir(parents=True, exist_ok=True)
        sc.ACTIVE_SPACE_FILE.write_text("  \n")
        assert get_active_space() is None

    def test_set_and_get_roundtrip(self) -> None:
        set_active_space("personal")
        assert get_active_space() == "personal"

    def test_set_overwrites_previous(self) -> None:
        set_active_space("personal")
        set_active_space("work")
        assert get_active_space() == "work"

    def test_set_creates_parent_dirs(self) -> None:
        assert not sc.IOBOX_HOME.exists()
        set_active_space("personal")
        assert sc.ACTIVE_SPACE_FILE.exists()


# ── load_session / save_session roundtrip ────────────────────────────────────


class TestSessionIO:
    def _make_session(self) -> SpaceSession:
        return SpaceSession(
            workspace="personal",
            updated_at="2026-03-16T10:00:00Z",
            services={
                "gmail-timgmailcom": ServiceSessionState(
                    authenticated=True,
                    scopes=["messages", "calendar"],
                    token_path="~/.iobox/tokens/tim@gmail.com/token_readonly.json",
                    last_sync="2026-03-16T09:55:00Z",
                    error=None,
                ),
                "outlook-corpmegacorpcom": ServiceSessionState(
                    authenticated=False,
                    scopes=["messages"],
                    token_path="~/.iobox/tokens/corp/microsoft_token.txt",
                    last_sync=None,
                    error="TokenExpiredError",
                ),
            },
        )

    def test_load_returns_default_when_missing(self) -> None:
        session = load_session("nonexistent")
        assert session.workspace == "nonexistent"
        assert session.services == {}

    def test_save_creates_json_file(self) -> None:
        save_session(self._make_session())
        path = sc.WORKSPACES_DIR / "personal.session.json"
        assert path.exists()

    def test_roundtrip_workspace_name(self) -> None:
        save_session(self._make_session())
        loaded = load_session("personal")
        assert loaded.workspace == "personal"

    def test_roundtrip_authenticated_state(self) -> None:
        save_session(self._make_session())
        loaded = load_session("personal")
        assert loaded.services["gmail-timgmailcom"].authenticated is True
        assert loaded.services["outlook-corpmegacorpcom"].authenticated is False

    def test_roundtrip_error_field(self) -> None:
        save_session(self._make_session())
        loaded = load_session("personal")
        assert loaded.services["gmail-timgmailcom"].error is None
        assert loaded.services["outlook-corpmegacorpcom"].error == "TokenExpiredError"

    def test_roundtrip_scopes(self) -> None:
        save_session(self._make_session())
        loaded = load_session("personal")
        assert loaded.services["gmail-timgmailcom"].scopes == ["messages", "calendar"]

    def test_roundtrip_none_last_sync(self) -> None:
        save_session(self._make_session())
        loaded = load_session("personal")
        assert loaded.services["outlook-corpmegacorpcom"].last_sync is None
