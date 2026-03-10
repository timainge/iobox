---
goal: Fix post-Phase-10 code review findings for Outlook/O365 provider
spec: .dev/code-review.md
approved: true
status: active
---

## Context

This sprint addresses correctness bugs, CLI key mismatches, and developer-experience
gaps identified in `.dev/code-review.md` after Phase 10 landed the Outlook provider
(`src/iobox/providers/outlook.py`, `outlook_auth.py`) and the provider abstraction
layer (`src/iobox/providers/base.py`, `providers/gmail.py`).

Key constraints discovered during Phase 1 exploration:

- `EmailData` stores the sender under `from_` (Python keyword avoidance); all
  legacy modules (`markdown_converter.py`, `file_manager.py`) expect `from`. The
  `_email_data_to_dict()` adapter in `cli.py` (line 48–58) bridges these correctly —
  do not change the key in `EmailData` or in the provider return values.
- All write methods (`send_message`, `create_draft`, `send_draft`, `delete_draft`,
  `forward_message`) in `outlook.py` currently return `{"message_id": ..., ...}`;
  the CLI reads `result.get("id", "unknown")` everywhere — always prints "unknown".
  The fix is in `cli.py`, not in the providers.
- `O365` is an optional dependency (`iobox[outlook]`). All Outlook imports must
  remain lazy (inside function bodies or under `TYPE_CHECKING`). Never add a
  top-level `from O365 import ...`.
- `ruff` and `ruff-format` are enforced by pre-commit hooks (`.pre-commit-config.yaml`).
  All changed files must pass `uv run ruff check src/ tests/` and
  `uv run ruff format --check src/ tests/` before a task is marked done.
- The test suite runs with `uv run pytest`. Unit tests mock the Gmail/Outlook APIs;
  no live credentials are required for `tests/unit/` or `tests/integration/`.

---

## Tasks

### [x] fix-outlook-label-filter

**Bug #1 from code-review.md — label filter silently dropped.**

In `src/iobox/providers/outlook.py` at line 205, the return value of the fluent
`Query` chain is discarded:

```python
# WRONG — return value discarded
q.on_attribute(raw_expr).equals(True)

# CORRECT
q = q.on_attribute(raw_expr).equals(True)
```

The mock's `MockQueryCondition.equals()` mutates `query._filters` in-place, so
unit tests pass today but the filter is silently dropped on every live call where
`EmailQuery.label` is set.

Files to change:
- `src/iobox/providers/outlook.py` — one-line fix in `_build_outlook_filter()`.

**Watch:** The existing label-filter test in `tests/unit/test_outlook_provider.py`
and `tests/unit/test_query_translation.py` should still pass after the fix because
the mock mutates in place *and* we now also capture the return value.

**Done:** `uv run pytest tests/unit/test_outlook_provider.py tests/unit/test_query_translation.py` passes;
the label filter line reads `q = q.on_attribute(...)`.

---

### [x] fix-cli-result-key-mismatch

**Two CLI key bugs — result IDs always show "unknown"; `draft-list` raises KeyError.**

All write-operation providers (`GmailProvider`, `OutlookProvider`) return dicts
with a `message_id` key, but `cli.py` reads `result.get("id", "unknown")`:

| Command | CLI line | Should read |
|---------|----------|-------------|
| `send` | line 661 | `result.get("message_id", "unknown")` |
| `forward` (single) | line 574 | `result.get("message_id", "unknown")` |
| `draft-create` | line 719 | `result.get("message_id", "unknown")` |
| `draft-send` | line 761 | `result.get("message_id", "unknown")` |

Additionally, `draft-list` (line 742) accesses `draft["id"]` but both providers
return `{"message_id": ..., "subject": ..., "snippet": ...}` — this is a `KeyError`
on every call, not just "unknown".

Files to change:
- `src/iobox/cli.py` — update five `result.get(...)` / `draft[...]` references.

Also update the corresponding test assertions in `tests/unit/test_cli.py` if they
assert on the "unknown" placeholder or the `draft["id"]` path.

**Watch:** `draft-delete` at line 777 correctly falls back to the `draft_id`
parameter (`result.get("draft_id", draft_id)`) — leave that one alone; the
`OutlookProvider.delete_draft` returns `{"message_id": draft_id, ...}` so it
actually works but the key name is still inconsistent. Normalise it to
`result.get("message_id", draft_id)` for consistency.

**Done:** `iobox send`, `iobox forward`, `iobox draft-create`, `iobox draft-list`,
`iobox draft-send`, and `iobox draft-delete` all display a real ID rather than
"unknown" when mocked; `uv run pytest tests/unit/test_cli.py` passes.

---

### [x] fix-outlook-write-op-error-handling

**python-o365 returns `False` on write failures; iobox ignores the return value.**

`send_message`, `create_draft`, `send_draft`, `delete_draft`, and `forward_message`
in `src/iobox/providers/outlook.py` call `msg.send()`, `msg.save_draft()`,
`msg.delete()`, and `fwd.send()` without checking their `bool` return. The mock
always returns `True`, so this is untested failure behaviour.

Fix pattern for each call site:

```python
if not msg.send():
    raise RuntimeError(f"Failed to send message: {msg.object_id!r}")
```

Apply the same guard to `save_draft()` and `delete()`.

Files to change:
- `src/iobox/providers/outlook.py` — 5 call sites across the write methods.

Add a negative-path test in `tests/unit/test_outlook_provider.py` for at least
`send_message` and `create_draft` where `msg.send()` / `msg.save_draft()` returns
`False` and verify `RuntimeError` is raised.

**Watch:** `msg.delete()` in `trash()` is intentionally a soft-delete; don't add
error handling there (the method returns the result of a folder move, not a
boolean). Only add guards in the three named write methods plus `forward_message`.

**Done:** `uv run pytest tests/unit/test_outlook_provider.py` passes including new
negative-path tests; every write method raises `RuntimeError` when the underlying
call returns `False`.

---

### [x] split-emaildata-typeddict [depends: fix-outlook-label-filter]

**`EmailData(total=False)` makes all fields optional — required fields invisible to mypy.**

Refactor `src/iobox/providers/base.py` to split the TypedDict into a required base
and an optional extension:

```python
class EmailMetadata(TypedDict):
    """Fields always present in every EmailData dict."""
    message_id: str
    subject: str
    from_: str
    date: str
    snippet: str
    labels: list[str]
    thread_id: str

class EmailData(EmailMetadata, total=False):
    """Full email data — optional fields present only after content retrieval."""
    body: str
    content_type: str
    attachments: list[AttachmentInfo]
```

Export `EmailMetadata` from `src/iobox/providers/__init__.py` alongside `EmailData`.

Files to change:
- `src/iobox/providers/base.py` — REWRITE the `EmailData` class block.
- `src/iobox/providers/__init__.py` — add `EmailMetadata` to `__all__`.

**Watch:** No call sites import `EmailMetadata` today so adding it is additive.
The runtime behaviour of `EmailData` dicts is unchanged — this is a type-annotation
refactor only. Grep for `EmailData` imports before starting:
`grep -r "EmailData" src/ tests/ --include="*.py" -l`

**Done:** `uv run pytest` passes; `from iobox.providers import EmailMetadata` works
in a Python REPL; mypy reports no new errors for `src/iobox/providers/base.py`.

---

### [x] add-get-new-messages-with-token-to-abc [depends: split-emaildata-typeddict]

**`get_new_messages_with_token()` is a useful public method absent from the ABC.**

Code typed against `EmailProvider` cannot call `get_new_messages_with_token()` on
an `OutlookProvider`. Either:

1. Add it as an abstract method to the `EmailProvider` ABC in
   `src/iobox/providers/base.py`, and add a stub implementation to
   `src/iobox/providers/gmail.py` (e.g. raise `NotImplementedError` or return
   `([], sync_token)` if GmailProvider already tracks its historyId).
2. Or rename it `_get_new_messages_with_token()` in `outlook.py` to signal it is
   implementation-specific and not part of the interface.

Recommended: **option 1** — add it to the ABC, since the CLI `--sync` path would
benefit from the refreshed token returned by the `with_token` variant. The
`GmailProvider` stub can return `([], "")` with a `NotImplementedError` note in
the docstring, or a real implementation if `GmailProvider.get_new_messages` already
captures a fresh historyId.

Files to change:
- `src/iobox/providers/base.py` — add abstract method.
- `src/iobox/providers/gmail.py` — add concrete implementation or stub.
- `src/iobox/providers/outlook.py` — no change needed (already implemented).
- `tests/unit/test_provider_contract.py` — extend contract tests to cover the new
  method signature.

**Done:** `uv run pytest tests/unit/test_provider_contract.py` passes; mypy
reports no missing-abstract-method errors for `GmailProvider` or `OutlookProvider`.

---

### [x] fix-outlook-auth-env-at-import

**`outlook_auth.py` resolves env vars at module import time — breaks test isolation.**

Lines 35–38 of `src/iobox/providers/outlook_auth.py` read env vars at module level:

```python
OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_TENANT_ID: str = os.getenv("OUTLOOK_TENANT_ID", "common")
...
```

Tests that need to override these must call `importlib.reload(outlook_auth)` or
patch before import, making isolation fragile. Wrap the configuration in a
`_get_config()` function (or a `@functools.lru_cache` singleton) and call it
lazily inside `get_outlook_account()` and `check_outlook_auth_status()`.

The module-level constants can remain as cached references (for backward
compatibility with any code that reads them directly), but the actual resolution
should happen in a function so tests can patch `os.getenv` without import-time
ordering constraints.

Files to change:
- `src/iobox/providers/outlook_auth.py` — wrap config in `_config()` or similar.
- `tests/unit/test_outlook_auth.py` — update any tests that patch module-level vars
  to patch `os.getenv` instead (or patch the `_config` function).

**Watch:** `check_outlook_auth_status()` reads `OUTLOOK_CLIENT_ID`,
`OUTLOOK_TENANT_ID`, and `OUTLOOK_TOKEN_DIR` from module-level constants. After the
refactor, each should read from the config function, not cached globals, so that
patching `os.getenv` in a test actually takes effect.

**Done:** `uv run pytest tests/unit/test_outlook_auth.py` passes; a test that
patches `os.getenv("OUTLOOK_CLIENT_ID", "")` after import can change the effective
client ID without `importlib.reload`.

---

### [x] update-claude-md-provider-context [depends: fix-cli-result-key-mismatch]

**CLAUDE.md still describes iobox as "a Gmail to Markdown converter" after Phase 10.**

Update `CLAUDE.md` to reflect the provider abstraction introduced in Phase 10.

Additions required (per code-review.md recommendations):

1. Change the Project Overview opening sentence from "Gmail to Markdown converter"
   to "multi-provider email to Markdown tool".
2. Add a `## Provider Architecture (Phase 10+)` section covering:
   - `EmailProvider` ABC at `src/iobox/providers/base.py`
   - Two providers: `GmailProvider` (default) and `OutlookProvider`
   - Selection via `--provider outlook` or `IOBOX_PROVIDER=outlook`
   - Outlook requires `OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID` env vars
   - Outlook optional deps: `pip install 'iobox[outlook]'`
3. Add a `## Key Invariants` section:
   - `EmailData["from_"]` (with underscore) — `markdown_converter` expects `from`
     (without); `_email_data_to_dict()` in `cli.py` bridges the two
   - Outlook searches inbox only; Gmail searches all mail
   - Outlook message IDs use ImmutableId — stable across folder moves
   - Write ops return `{"message_id": ..., "status": ...}` — not `"id"`
4. Add a test convention note to `## Testing Strategy`: prefer
   `class Test<Feature>` grouping in test files (matches `test_outlook_provider.py`
   style).

Files to change:
- `CLAUDE.md` — targeted additions; do not rewrite existing accurate sections.

**Done:** `CLAUDE.md` accurately describes the provider architecture; `grep -i outlook CLAUDE.md` returns multiple meaningful results.

---

### [x] add-makefile

**No dev task runner exists; agents and contributors reconstruct command strings from CLAUDE.md.**

Create a `Makefile` in the project root with the following targets:

```makefile
.PHONY: test lint fmt type-check check

test:
	uv run pytest tests/unit tests/integration -v

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

type-check:
	uv run mypy src/iobox/

check: lint type-check test
```

Update the `## Development Commands` section in `CLAUDE.md` to document `make check`
as the standard pre-commit verification step.

Files to change:
- `Makefile` — new file in project root.
- `CLAUDE.md` — add `make check` to the Development Commands section.

**Watch:** `mypy` is listed in `[project.optional-dependencies] dev` in
`pyproject.toml` but is not yet installed in `[tool.uv] dev-dependencies`. Add it
to the uv dev deps so `uv run mypy` works out of the box:

```toml
[tool.uv]
dev-dependencies = [
    "pytest",
    "pytest-cov",
    "pytest-mock",
    "mypy",
    "ruff",
    "types-PyYAML",
]
```

**Done:** `make lint` exits 0; `make test` runs the full unit + integration suite;
`make check` is the documented pre-commit step in CLAUDE.md.

---

### [ ] configure-mypy-strict [depends: add-makefile, split-emaildata-typeddict]

**Mypy is configured but not enforced; `[tool.mypy]` in `pyproject.toml` is minimal.**

Enable a reasonable strict mypy configuration and add it to the pre-commit hook.

`pyproject.toml` additions:

```toml
[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true
exclude = ["tests/live/", "tests/fixtures/"]
warn_return_any = true
warn_unused_configs = true
```

`.pre-commit-config.yaml` addition:

```yaml
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: [types-PyYAML]
        args: [src/iobox/]
```

Before enabling strict mode, fix any errors surfaced by `uv run mypy src/iobox/`.
Common expected findings:

- Missing return type annotations on CLI helper functions.
- `Any`-typed `_account: Any` and `_mailbox: Any` in `OutlookProvider` — these are
  intentional (O365 is optional). Add explanatory `# type: ignore[annotation-unchecked]`
  comments with a note: *"O365.Account is only available when the optional 'O365'
  package is installed; Any is required to avoid a hard import at the class level."*
- `total=False` TypedDict issues resolved by the `split-emaildata-typeddict` task.

Files to change:
- `pyproject.toml` — update `[tool.mypy]`.
- `.pre-commit-config.yaml` — add mypy hook.
- `src/iobox/providers/outlook.py` — add `# type: ignore` comments with explanations.
- Any other `src/iobox/*.py` files with annotation gaps surfaced by strict mode.

**Watch:** Run `uv run mypy src/iobox/` before and after to get a baseline count.
Fix errors incrementally; do not suppress wholesale with `# type: ignore` without a
comment explaining why.

**Done:** `uv run mypy src/iobox/` exits 0; `make check` includes type-check and
passes end-to-end.

---

### [ ] fix-outlook-search-all-mail [depends: fix-outlook-label-filter]

**Outlook `search_emails`, `get_thread`, and `batch_get_emails` search inbox only.**

All three methods call `self._mb.inbox_folder()`. Emails in Sent, Archive, Drafts,
or custom folders are invisible — a significant limitation for "search all mail"
use cases.

Fix: use the root mailbox message collection (`/me/messages`) instead of the inbox
folder. In python-o365, this is `self._mb.get_messages(...)` called on the mailbox
object directly (not on a folder). Verify this path is available by checking the
python-o365 `MailBox` class API; if not, fall back to calling the Graph endpoint
directly via `con.get("/me/messages", params={...})`.

Files to change:
- `src/iobox/providers/outlook.py` — update `search_emails()`, `get_thread()`, and
  `batch_get_emails()` to search across all folders.
- `tests/unit/test_outlook_provider.py` — update mock setup if
  `make_mock_mailbox()` hard-codes `inbox_folder()` calls.
- `tests/fixtures/mock_outlook_responses.py` — add root-mailbox message mock if
  required.

**Watch:** The `$filter` and `$search` restrictions on `/me/mailFolders/{id}/messages`
may not apply the same way at `/me/messages`. Test the query path selection logic
(`raw_query` → `$search`, structured → `$filter`) still works correctly when
pointing to the root endpoint. Document the limitation clearly in a docstring if
full parity cannot be achieved without a live tenant test.

**Done:** `search_emails` returns results from all folders in mocked tests;
`uv run pytest tests/unit/test_outlook_provider.py` passes.

---

### [ ] wire-outlook-batch-org-operations [depends: fix-outlook-write-op-error-handling]

**`_batch_graph_requests` helper exists but is never called — org methods use single-message operations.**

Per the spec (`task outlook-org`), multi-message operations (mark_read, set_star,
archive, trash, untrash, add_tag, remove_tag) should route through
`_batch_graph_requests` for 20-request chunks. The helper is correctly implemented
but the org methods each call single per-message Graph operations.

Two acceptable approaches:
1. Keep the current ABC signatures as single-message and add separate
   `batch_mark_read(message_ids: list[str], ...)` variants that call
   `_batch_graph_requests` — leave the existing single-message methods untouched.
2. Change org method signatures to accept `list[str]` and route through the batch
   helper internally.

Recommended: **approach 1** (additive, backward-compatible). Add `batch_mark_read`,
`batch_archive`, `batch_trash`, `batch_add_tag`, `batch_remove_tag` methods to
`OutlookProvider`. Add optional batch variants to the ABC (non-abstract, with a
default implementation that calls the single-message method in a loop).

Files to change:
- `src/iobox/providers/base.py` — add non-abstract batch method stubs with
  loop-based default implementations.
- `src/iobox/providers/outlook.py` — override batch methods to call
  `_batch_graph_requests`.
- `tests/unit/test_outlook_provider.py` — add tests for batch org operations.

**Watch:** The Graph `$batch` endpoint requires each sub-request `"url"` to be a
relative path (e.g. `/me/messages/{id}`) not a full URL. Verify this in the
existing `_batch_graph_requests` helper and in any new batch method.

**Done:** `OutlookProvider.batch_archive(["id1", "id2"])` calls
`_batch_graph_requests` once (not twice); `uv run pytest tests/unit/test_outlook_provider.py`
passes including new batch tests.

---
