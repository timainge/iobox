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
    is_authenticated,
    list_spaces,
    load_session,
    load_space,
    save_session,
    save_space,
    set_active_space,
    token_file_for,
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
    def test_derive_id_google(self) -> None:
        assert _derive_id("google", "tim@gmail.com") == "google-timgmailcom"

    def test_derive_id_o365(self) -> None:
        assert _derive_id("o365", "corp@megacorp.com") == "o365-corpmegacorpcom"

    def test_derive_id_strips_special_chars(self) -> None:
        result = _derive_id("google", "my.name+tag@example.co.uk")
        assert "@" not in result
        assert "." not in result
        assert result.startswith("google-")

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
        entry = ServiceEntry(number=1, service="google", account="tim@gmail.com", scopes=["email"])
        assert entry.id == "google-timgmailcom"

    def test_slug_auto_derived_when_empty(self) -> None:
        entry = ServiceEntry(number=1, service="google", account="tim@gmail.com", scopes=["email"])
        assert entry.slug == "tim-gmail"

    def test_explicit_id_preserved(self) -> None:
        entry = ServiceEntry(
            number=1, service="google", account="tim@gmail.com", scopes=["email"], id="custom-id"
        )
        assert entry.id == "custom-id"

    def test_explicit_slug_preserved(self) -> None:
        entry = ServiceEntry(
            number=1, service="google", account="tim@gmail.com", scopes=["email"], slug="my-work"
        )
        assert entry.slug == "my-work"

    def test_default_mode_is_standard(self) -> None:
        entry = ServiceEntry(number=1, service="google", account="a@b.com", scopes=["email"])
        assert entry.mode == "standard"


# ── Slug uniqueness / duplicate detection (WS-04) ─────────────────────────────


def _entry(account: str, service: str = "google", slug: str = "") -> ServiceEntry:
    return ServiceEntry(
        number=1,
        service=service,  # type: ignore[arg-type]
        account=account,
        scopes=["email"],
        slug=slug,
    )


class TestUniqueSlug:
    def test_no_collision_returns_derived_slug(self) -> None:
        cfg = SpaceConfig(name="p", services=[_entry("work@company.com")])
        assert sc.unique_slug(cfg, "tim@gmail.com") == "tim-gmail"

    def test_collision_appends_suffix(self) -> None:
        cfg = SpaceConfig(name="p", services=[_entry("tim@gmail.com")])
        assert sc.unique_slug(cfg, "tim@gmail.co.uk") == "tim-gmail-2"

    def test_multiple_collisions_increment(self) -> None:
        cfg = SpaceConfig(
            name="p",
            services=[_entry("tim@gmail.com"), _entry("tim@gmail.co.uk", slug="tim-gmail-2")],
        )
        assert sc.unique_slug(cfg, "tim@gmail.de") == "tim-gmail-3"

    def test_same_account_other_service_gets_distinct_slug(self) -> None:
        cfg = SpaceConfig(name="p", services=[_entry("tim@company.com", "google")])
        assert sc.unique_slug(cfg, "tim@company.com") == "tim-company-2"

    def test_existing_stored_slugs_unchanged_on_load(self) -> None:
        cfg = SpaceConfig(
            name="personal",
            services=[_entry("tim@gmail.com"), _entry("tim@gmail.co.uk", slug="tim-gmail")],
        )
        save_space(cfg)
        assert [s.slug for s in load_space("personal").services] == ["tim-gmail", "tim-gmail"]


class TestFindService:
    def test_finds_existing_entry_case_insensitive(self) -> None:
        e = _entry("Tim@Gmail.com")
        cfg = SpaceConfig(name="p", services=[e])
        assert sc.find_service(cfg, "google", "tim@gmail.com") is e

    def test_different_service_not_matched(self) -> None:
        cfg = SpaceConfig(name="p", services=[_entry("tim@gmail.com", "google")])
        assert sc.find_service(cfg, "o365", "tim@gmail.com") is None

    def test_legacy_service_name_normalised(self) -> None:
        e = _entry("corp@megacorp.com", "o365")
        cfg = SpaceConfig(name="p", services=[e])
        assert sc.find_service(cfg, "outlook", "corp@megacorp.com") is e

    def test_missing_returns_none(self) -> None:
        assert sc.find_service(SpaceConfig(name="p"), "google", "x@y.com") is None


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
                    service="google",
                    account="tim@gmail.com",
                    scopes=["email", "calendar", "drive"],
                    mode="readonly",
                ),
                ServiceEntry(
                    number=2,
                    service="o365",
                    account="corp@megacorp.com",
                    scopes=["email"],
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
        assert svc.service == "google"
        assert svc.account == "tim@gmail.com"
        assert svc.scopes == ["email", "calendar", "drive"]
        assert svc.mode == "readonly"
        assert svc.number == 1

    def test_roundtrip_derived_id_and_slug(self) -> None:
        save_space(self._make_config())
        loaded = load_space("personal")
        svc = loaded.services[0]
        assert svc.id == "google-timgmailcom"
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
        save_space(SpaceConfig(name="personal"))
        set_active_space("personal")
        assert get_active_space() == "personal"

    def test_set_overwrites_previous(self) -> None:
        save_space(SpaceConfig(name="personal"))
        save_space(SpaceConfig(name="work"))
        set_active_space("personal")
        set_active_space("work")
        assert get_active_space() == "work"

    def test_set_creates_parent_dirs(self) -> None:
        assert not sc.IOBOX_HOME.exists()
        set_active_space("personal")
        assert sc.ACTIVE_SPACE_FILE.exists()

    def test_returns_none_when_active_space_deleted(self, caplog: pytest.LogCaptureFixture) -> None:
        save_space(SpaceConfig(name="gone"))
        set_active_space("gone")
        (sc.WORKSPACES_DIR / "gone.toml").unlink()
        with caplog.at_level("WARNING"):
            assert get_active_space() is None
        assert "no longer exists" in caplog.text

    def test_returns_none_when_active_file_has_invalid_name(self) -> None:
        sc.IOBOX_HOME.mkdir(parents=True, exist_ok=True)
        sc.ACTIVE_SPACE_FILE.write_text("../../etc/passwd")
        assert get_active_space() is None


# ── File name is authoritative (WS-05) ────────────────────────────────────────


class TestLoadUsesFileName:
    def test_copied_file_saves_back_to_itself(self) -> None:
        save_space(SpaceConfig(name="original"))
        original = (sc.WORKSPACES_DIR / "original.toml").read_text()
        # User copies the file; [workspace] name inside still says "original".
        (sc.WORKSPACES_DIR / "copy.toml").write_text(original)

        cfg = load_space("copy")
        assert cfg.name == "copy"
        cfg.services.append(
            ServiceEntry(number=1, service="google", account="a@b.com", scopes=["email"])
        )
        save_space(cfg)

        assert load_space("original").services == []
        assert len(load_space("copy").services) == 1


# ── Malformed files and atomic writes (WS-09) ─────────────────────────────────


class TestMalformedConfig:
    def _write(self, body: str) -> None:
        sc.WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        (sc.WORKSPACES_DIR / "personal.toml").write_text(body)

    def test_missing_workspace_table(self) -> None:
        self._write("[[services]]\nnumber = 1\n")
        with pytest.raises(ValueError, match=r"personal\.toml.*missing required key 'workspace'"):
            load_space("personal")

    @pytest.mark.parametrize("key", ["number", "service", "account", "scopes"])
    def test_missing_service_key(self, key: str) -> None:
        fields = {
            "number": "1",
            "service": '"google"',
            "account": '"a@b.com"',
            "scopes": '["email"]',
        }
        del fields[key]
        body = "\n".join(f"{k} = {v}" for k, v in fields.items())
        self._write(f'[workspace]\nname = "personal"\n\n[[services]]\n{body}\n')
        with pytest.raises(
            ValueError, match=rf"personal\.toml.*missing required key '{key}'.*entry #1"
        ):
            load_space("personal")

    def test_invalid_toml_raises_value_error_with_path(self) -> None:
        self._write("this is = = not toml")
        with pytest.raises(ValueError, match=r"personal\.toml.*invalid TOML"):
            load_space("personal")

    def test_corrupt_session_file_returns_empty_session(self) -> None:
        sc.WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        (sc.WORKSPACES_DIR / "personal.session.json").write_text("{not json")
        assert load_session("personal").services == {}


class TestAtomicWrites:
    def test_failed_write_leaves_existing_file_intact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_space(SpaceConfig(name="personal"))
        before = (sc.WORKSPACES_DIR / "personal.toml").read_text()

        def boom(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(sc.os, "replace", boom)
        cfg = SpaceConfig(
            name="personal",
            services=[ServiceEntry(number=1, service="google", account="a@b.com", scopes=[])],
        )
        with pytest.raises(OSError):
            save_space(cfg)
        assert (sc.WORKSPACES_DIR / "personal.toml").read_text() == before
        # No temp files left behind
        assert sorted(p.name for p in sc.WORKSPACES_DIR.iterdir()) == ["personal.toml"]

    def test_set_active_space_is_atomic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, str]] = []
        real_replace = sc.os.replace

        def spy(src: str, dst: object) -> None:
            calls.append((str(src), str(dst)))
            real_replace(src, dst)  # type: ignore[arg-type]

        monkeypatch.setattr(sc.os, "replace", spy)
        set_active_space("personal")
        assert calls and calls[0][1] == str(sc.ACTIVE_SPACE_FILE)


# ── load_session / save_session roundtrip ────────────────────────────────────


class TestSessionIO:
    def _make_session(self) -> SpaceSession:
        return SpaceSession(
            workspace="personal",
            updated_at="2026-03-16T10:00:00Z",
            services={
                "gmail-timgmailcom": ServiceSessionState(
                    authenticated=True,
                    scopes=["email", "calendar"],
                    token_path="~/.iobox/tokens/tim@gmail.com/token_readonly.json",
                    last_sync="2026-03-16T09:55:00Z",
                    error=None,
                ),
                "outlook-corpmegacorpcom": ServiceSessionState(
                    authenticated=False,
                    scopes=["email"],
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
        assert loaded.services["gmail-timgmailcom"].scopes == ["email", "calendar"]

    def test_roundtrip_none_last_sync(self) -> None:
        save_session(self._make_session())
        loaded = load_session("personal")
        assert loaded.services["outlook-corpmegacorpcom"].last_sync is None


# ── Token-file probes ────────────────────────────────────────────────────────


class TestTokenFileProbes:
    def _entry(self, service: str, mode: str = "standard") -> ServiceEntry:
        return ServiceEntry(
            number=1,
            service=service,  # type: ignore[arg-type]
            account="tim@gmail.com",
            scopes=["email"],
            mode=mode,  # type: ignore[arg-type]
        )

    def _touch(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")

    def test_token_file_for_google_standard(self) -> None:
        path = token_file_for(self._entry("google", "standard"))
        assert path == sc.IOBOX_HOME / "tokens" / "tim@gmail.com" / "token_standard.json"

    def test_token_file_for_google_readonly(self) -> None:
        path = token_file_for(self._entry("google", "readonly"))
        assert path == sc.IOBOX_HOME / "tokens" / "tim@gmail.com" / "token_readonly.json"

    def test_token_file_for_o365(self) -> None:
        base = sc.IOBOX_HOME / "tokens" / "tim@gmail.com"
        assert token_file_for(self._entry("o365")) == base / "microsoft_token_standard.txt"
        assert (
            token_file_for(self._entry("o365", mode="readonly"))
            == base / "microsoft_token_readonly.txt"
        )

    def test_o365_readonly_does_not_inherit_legacy_write_token(self) -> None:
        legacy = token_file_for(self._entry("o365")).parent / "microsoft_token.txt"
        self._touch(legacy)
        assert is_authenticated(self._entry("o365")) is True
        assert is_authenticated(self._entry("o365", mode="readonly")) is False

    def test_unauthenticated_when_no_token_file(self) -> None:
        assert is_authenticated(self._entry("google")) is False

    def test_authenticated_when_token_file_exists(self) -> None:
        self._touch(token_file_for(self._entry("google")))
        assert is_authenticated(self._entry("google")) is True

    def test_readonly_falls_back_to_standard_token(self) -> None:
        # Broader standard-tier token satisfies a readonly entry.
        self._touch(token_file_for(self._entry("google", "standard")))
        assert is_authenticated(self._entry("google", "readonly")) is True

    def test_standard_does_not_fall_back_to_readonly_token(self) -> None:
        self._touch(token_file_for(self._entry("google", "readonly")))
        assert is_authenticated(self._entry("google", "standard")) is False

    def test_o365_legacy_filename_counts(self) -> None:
        legacy = token_file_for(self._entry("o365")).parent / "o365_token.txt"
        self._touch(legacy)
        assert is_authenticated(self._entry("o365")) is True


# ── Validation (SEC-09 / SEC-11) ──────────────────────────────────────────────


class TestSpaceNameValidation:
    @pytest.mark.parametrize(
        "name", ["../../x", "a/b", "a\\b", "", "x" * 65, "has space", "dot.name", "nl\n"]
    )
    def test_invalid_names_rejected_everywhere(self, name: str) -> None:
        with pytest.raises(ValueError, match="Invalid workspace name"):
            sc.validate_space_name(name)
        with pytest.raises(ValueError):
            load_space(name)
        with pytest.raises(ValueError):
            save_space(SpaceConfig(name=name))
        with pytest.raises(ValueError):
            set_active_space(name)
        with pytest.raises(ValueError):
            load_session(name)
        with pytest.raises(ValueError):
            save_session(SpaceSession(workspace=name))

    @pytest.mark.parametrize("name", ["personal", "Work_2", "a-b", "x" * 64])
    def test_valid_names_accepted(self, name: str) -> None:
        assert sc.validate_space_name(name) == name

    def test_traversal_does_not_write_outside_workspaces(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            save_space(SpaceConfig(name="../../escape"))
        assert not list(tmp_path.rglob("escape.toml"))

    def test_list_spaces_skips_invalid_stems(self) -> None:
        sc.WORKSPACES_DIR.mkdir(parents=True)
        (sc.WORKSPACES_DIR / "bad name.toml").write_text('[workspace]\nname = "x"\n')
        save_space(SpaceConfig(name="good"))
        assert list_spaces() == ["good"]


class TestAccountValidation:
    @pytest.mark.parametrize(
        "account",
        ["../evil", "..", ".", "a/b@x.com", "a\\b@x.com", ".hidden@x.com", "a\x00b", "", "  "],
    )
    def test_invalid_accounts_rejected(self, account: str) -> None:
        with pytest.raises(ValueError, match="Invalid account"):
            sc.validate_account(account)
        with pytest.raises(ValueError):
            ServiceEntry(number=1, service="google", account=account, scopes=["email"])

    @pytest.mark.parametrize(
        "account", ["tim@gmail.com", "Tim.Ainge@Example.COM", "default", "a..b@x.com"]
    )
    def test_valid_accounts_preserved(self, account: str) -> None:
        # Case is preserved so existing token directories keep working.
        assert sc.validate_account(account) == account


class TestTomlValueValidation:
    def _write(self, body: str) -> None:
        sc.WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        (sc.WORKSPACES_DIR / "personal.toml").write_text(body)

    def _svc(self, **overrides: str) -> str:
        fields = {
            "number": "1",
            "service": '"google"',
            "account": '"tim@gmail.com"',
            "scopes": '["email"]',
            "mode": '"standard"',
        }
        fields.update(overrides)
        lines = "\n".join(f"{k} = {v}" for k, v in fields.items())
        return f'[workspace]\nname = "personal"\n\n[[services]]\n{lines}\n'

    def test_invalid_mode_rejected_with_file_name(self) -> None:
        self._write(self._svc(mode='"read-only"'))
        with pytest.raises(ValueError, match=r"personal\.toml.*invalid mode 'read-only'"):
            load_space("personal")

    def test_invalid_service_rejected(self) -> None:
        self._write(self._svc(service='"yahoo"'))
        with pytest.raises(ValueError, match=r"personal\.toml.*invalid service 'yahoo'"):
            load_space("personal")

    def test_legacy_service_names_still_migrate(self) -> None:
        self._write(self._svc(service='"gmail"'))
        assert load_space("personal").services[0].service == "google"

    def test_invalid_account_rejected_with_file_name(self) -> None:
        self._write(self._svc(account='"../../etc"'))
        with pytest.raises(ValueError, match=r"personal\.toml.*Invalid account"):
            load_space("personal")

    def test_missing_mode_defaults_to_standard(self) -> None:
        self._write(self._svc().replace('mode = "standard"\n', ""))
        assert load_space("personal").services[0].mode == "standard"
