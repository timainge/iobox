---
title: "Phase 10 \u2014 O365/Outlook Support"
spec: .dev/specs/10-outlook-o365-support.md
status: active
approved: true
---

## Tasks

- [x] Create provider abstraction layer (`src/iobox/providers/base.py` and `src/iobox/providers/__init__.py`) with `EmailProvider` ABC, `EmailQuery` dataclass, `EmailData` TypedDict, and `get_provider()` factory using lazy importlib loading [id: provider-abstraction]

- [x] Implement `GmailProvider` in `src/iobox/providers/gmail.py` that wraps all existing Gmail modules (`email_search`, `email_retrieval`, `email_sender`, `auth`) behind the `EmailProvider` ABC with `_build_gmail_query()` translation and `_to_email_data()` normalization — no direct Gmail API calls in the wrapper [id: gmail-provider] [depends: provider-abstraction]

- [x] Add mock fixtures for Outlook in `tests/fixtures/mock_outlook_responses.py` — python-o365 `Account`, `Mailbox`, `Message`, `Attachment`, and delta response objects needed by all Outlook tests [id: outlook-fixtures] [depends: provider-abstraction]

- [x] Create `src/iobox/providers/outlook_auth.py` with `get_outlook_account()` (browser and device-code flows) and `check_outlook_auth_status()`, reading `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_TENANT_ID` env vars, persisting tokens under `$CREDENTIALS_DIR/tokens/outlook/o365_token.txt` [id: outlook-auth] [depends: provider-abstraction]

- [ ] Implement `OutlookProvider` read operations in `src/iobox/providers/outlook.py`: `authenticate()`, `search_emails()` (with `$filter` / `$search` path selection), `get_email_content()`, `batch_get_emails()`, `get_thread()`, `download_attachment()`, `_message_to_email_data()`, and set `Prefer: IdType="ImmutableId"` header on all Graph requests [id: outlook-read] [depends: outlook-auth, outlook-fixtures]

- [ ] Implement `OutlookProvider` write operations in `src/iobox/providers/outlook.py`: `send_message()` (with file attachment support), `forward_message()` (native Graph forward), `create_draft()`, `list_drafts()`, `send_draft()`, `delete_draft()` [id: outlook-write] [depends: outlook-read]

- [ ] Implement `OutlookProvider` organization operations in `src/iobox/providers/outlook.py`: `mark_read()`, `set_star()`, `archive()`, `trash()`, `untrash()`, `add_tag()`, `remove_tag()`, `list_tags()`, using Graph's `$batch` with 20-request chunks for multi-message ops [id: outlook-org] [depends: outlook-read]

- [ ] Add query translation layer — `_build_gmail_query()` in `GmailProvider` (all `EmailQuery` fields → Gmail `q=` syntax), `_build_outlook_filter()` and `_build_outlook_search()` in `OutlookProvider` (`$filter` vs `$search` based on `text` presence, `raw_query` passthrough for both) [id: query-translation] [depends: gmail-provider, outlook-read]

- [ ] Implement `OutlookProvider` incremental sync in `src/iobox/providers/outlook.py` (`get_sync_state()`, `get_new_messages()` with delta query and 410-Gone fallback) and extend `SyncState` in `src/iobox/file_manager.py` to store both `last_history_id` (Gmail) and `delta_links: dict[str, str]` (Outlook) with `provider` field [id: outlook-sync] [depends: outlook-read]

- [ ] Refactor `src/iobox/cli.py` to add global `--provider` option (default `gmail`, env var `IOBOX_PROVIDER`) in `app.callback()`, route all commands through `ctx.obj["provider"]` using `EmailQuery`, update `auth-status` to show provider-specific info, and add optional-dependency `outlook = ["O365>=2.1.8"]` to `pyproject.toml` [id: cli-refactor] [depends: gmail-provider, query-translation]

- [ ] Add unit tests for `GmailProvider` in `tests/unit/test_gmail_provider.py` — one test per abstract method verifying correct delegation to existing module functions, plus `_build_gmail_query()` and `_to_email_data()` field-by-field coverage [id: test-gmail-provider] [depends: gmail-provider, query-translation]

- [ ] Add unit tests for `OutlookProvider` in `tests/unit/test_outlook_provider.py` — all abstract methods with mocked python-o365 objects, and unit tests for `outlook_auth.py` in `tests/unit/test_outlook_auth.py` (browser/device-code flows, missing client ID error, status check) [id: test-outlook-provider] [depends: outlook-org, outlook-write, outlook-sync, outlook-fixtures]

- [ ] Add shared ABC contract tests in `tests/unit/test_provider_contract.py` (both providers implement all methods, return correct types, `EmailData` has required keys) and query translation tests in `tests/unit/test_query_translation.py` (all `EmailQuery` fields individually and combined, `$search` vs `$filter` path selection, `raw_query` passthrough) [id: test-contracts] [depends: test-gmail-provider, test-outlook-provider]

- [ ] Add delta sync unit tests in `tests/unit/test_outlook_sync.py` (normal response, 410-Gone fallback, initial sync with no token) and cross-provider integration tests in `tests/integration/test_provider_parity.py` (identical `EmailData` output format, markdown output identical for same content) [id: test-integration] [depends: test-contracts, outlook-sync]
