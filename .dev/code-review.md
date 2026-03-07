# Code Review — Phase 10 (Outlook/O365 Support)

**Date:** 2026-03-07
**Scope:** `src/iobox/providers/`, `tests/fixtures/mock_outlook_responses.py`,
all Phase 10 test files, CLI refactor in `src/iobox/cli.py`

---

## Summary

The abstraction layer is well-designed, the mock fixtures are thorough, and test
coverage is solid for everything that can be verified without a live tenant.
Three correctness bugs exist, all of which will surface on first live use.

---

## Bugs

### 1. Label filter silently dropped — `outlook.py:205`

```python
# Every other filter condition does this:
q = q.on_attribute("from/emailAddress/address").equals(query.from_addr)

# The label condition does NOT reassign q:
q.on_attribute(raw_expr).equals(True)   # ← return value discarded
```

`MockQueryCondition.equals()` mutates `query._filters` in-place, so tests pass.
Real python-o365's fluent `Query` builder requires the chain result to be captured.
The label filter is silently dropped on every live call with `query.label` set.

**Fix:** `q = q.on_attribute(raw_expr).equals(True)` (or confirm python-o365's
mutation semantics with a live test — see `testing-o365.md` scenario #4).

### 2. `_batch_graph_requests` implemented but never called

The spec (task `outlook-org`) requires multi-message operations to use Graph's
`$batch` endpoint with 20-request chunks. The `_batch_graph_requests` helper is
correctly implemented but every org method (`mark_read`, `set_star`, `archive`,
`trash`, `untrash`, `add_tag`, `remove_tag`) calls single per-message operations.

**Impact:** Not a correctness issue for single-message calls. Becomes a
performance/rate-limit issue when batch-archiving or batch-tagging many messages.

**Fix (deferred):** Update org methods to accept `list[str]` message IDs and
route through `_batch_graph_requests` — or explicitly document the ABC methods
as single-message only and add separate `batch_*` variants.

### 3. `from_` / `from` impedance mismatch

`EmailData` uses key `from_` (to avoid the Python keyword). `markdown_converter
.convert_email_to_markdown` expects key `from`. The integration test papers over
this with a `_normalize_email_data_for_markdown()` adapter:

```python
"from": data["from_"],   # manual rename in test helper
```

Any caller that passes `EmailData` directly to `convert_email_to_markdown`
will silently omit the sender in the output. The `cli.py` save path likely has
this bug — worth tracing the call chain.

**Fix options:**
- Update `convert_email_to_markdown` to accept both `from` and `from_`
- Rename the key throughout to `sender` (avoids the keyword problem cleanly)
- Add an adapter function in `providers/base.py` that converts `EmailData` to
  the dict shape expected by the markdown converter

---

## Issues / Design Notes

### Search is inbox-only

`search_emails`, `get_thread`, and `batch_get_emails` all call
`self._mb.inbox_folder()`. Emails in Sent, Archive, Drafts, or custom folders
are invisible. This is a significant limitation for any "search all mail" use case.

**Fix (if needed):** Use `/me/messages` endpoint (root mailbox search) instead of
`/me/mailFolders/inbox/messages`. This requires bypassing the python-o365 folder
abstraction and calling `con.get(...)` directly, or using `self._mb.get_messages()`
if that method exists on the root mailbox object.

### `EmailData(total=False)` loses required-field type safety

All fields are optional to the type checker because `total=False` applies to the
whole TypedDict. The comment correctly documents which are "always present" but
mypy/pyright won't enforce it. A real type violation (missing `message_id`) is
invisible at static analysis time.

**Better pattern:**
```python
class EmailMetadata(TypedDict):
    message_id: str
    subject: str
    from_: str
    date: str
    snippet: str
    labels: list[str]
    thread_id: str

class EmailData(EmailMetadata, total=False):
    body: str
    content_type: str
    attachments: list[AttachmentInfo]
```

This gives correct static types without changing runtime behavior.

### `outlook_auth.py` resolves env vars at import time

```python
OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")  # line 35 — module-level
```

Tests that need to override these must patch before import or call
`importlib.reload(outlook_auth)`. This is consistent with how Gmail auth works
but makes test isolation fragile. Consider wrapping in a function or using
`functools.cached_property` on a config object.

### `get_new_messages_with_token` not in ABC

A useful method but inaccessible through the `EmailProvider` interface. Code
typed against `EmailProvider` cannot call it. Consider adding it to the ABC or
keeping it private (`_get_new_messages_with_token`) to signal it's
implementation-specific.

---

## Additional Code Reviews Recommended

### 1. Full CLI audit — `src/iobox/cli.py`

**Scope:** Verify every command correctly routes through `ctx.obj["provider"]`
and that Gmail-specific assumptions (label IDs vs category names, `historyId`
sync token vs delta link) are not leaking through.

**Specific checks:**
- `label` command: does `--add`/`--remove` pass a label *name* or *ID*? Gmail
  resolves name→ID in `add_tag`; Outlook uses names directly. Confirm the CLI
  passes a name and both providers handle it correctly.
- `auth-status`: confirm Outlook branch calls `check_outlook_auth_status` and
  the output is user-friendly.
- `save` command: trace the `EmailData → markdown_converter` call chain to
  confirm the `from_` / `from` key mismatch (bug #3) is caught here.

### 2. `GmailProvider.search_emails` — date handling double-count

`_build_gmail_query` emits `after:YYYY/MM/DD` and `before:YYYY/MM/DD` operators.
`search_emails` *also* passes `start_date` and `end_date` as separate keyword
args to `email_search.search_emails`. Review whether this causes duplicate date
filtering or interacts poorly with `raw_query` (which skips query building but
still passes `start_date`).

### 3. `file_manager.py` — SyncState provider field

The spec (task `outlook-sync`) requires `SyncState` to store `provider`,
`last_history_id` (Gmail), and `delta_links: dict[str, str]` (Outlook). Review
whether the current `SyncState` implementation is actually used anywhere in the
CLI save/sync flow, or whether it's only tested in isolation. If unused, the sync
infrastructure is not wired up.

### 4. Error propagation review — Outlook write ops

`send_message`, `create_draft`, `send_draft`, `delete_draft` all call
`msg.send()` / `msg.save_draft()` / `msg.delete()` and trust they succeed.
python-o365 returns `False` on failure (not an exception). Review whether any
error handling is needed:

```python
if not msg.send():
    raise RuntimeError("Failed to send message")
```

The mock always returns `True` so this is untested behavior.

---

## Agent Dev Experience Improvements

### Update CLAUDE.md with Outlook context

The project CLAUDE.md describes iobox as "a Gmail to Markdown converter". After
Phase 10 this is no longer accurate. Update to describe the provider abstraction
and add Outlook-specific configuration guidance so future agents don't assume
Gmail-only behavior.

Suggested additions:
```markdown
## Provider Architecture (Phase 10+)
- All email operations route through `EmailProvider` ABC (`src/iobox/providers/base.py`)
- Two providers: `GmailProvider` (default) and `OutlookProvider`
- Select with `--provider outlook` or `IOBOX_PROVIDER=outlook`
- Outlook requires: `OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID` env vars
- Outlook optional deps: `pip install 'iobox[outlook]'`

## Key Invariants
- `EmailData["from_"]` (with underscore) — note: markdown_converter expects `from` (without)
- Outlook searches inbox only; Gmail searches all mail
- Outlook message IDs use ImmutableId header — always stable across folder moves
```

### Add a linter + type-checker pre-commit loop

No linting configuration exists in the repo. Adding it gives agents (and humans)
immediate feedback on the patterns above.

**Recommended tools:**

```toml
# pyproject.toml additions

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "W", "I", "UP", "B", "RUF"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true
# Exclude live tests and fixture stubs
exclude = ["tests/live/", "tests/fixtures/"]

[tool.pytest.ini_options]
# already configured — add:
addopts = "--tb=short"
```

**Pre-commit config** (`.pre-commit-config.yaml`):
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: [types-PyYAML]
```

Install: `uv add --dev pre-commit ruff mypy types-PyYAML && pre-commit install`

**Immediate mypy wins from enabling this:**
- `EmailData(total=False)` TypedDict issue will surface as type errors
- Missing return type annotations on several provider methods
- `Any`-typed `_account` / `_mailbox` — can be made more precise with a
  `TYPE_CHECKING` block that imports O365 types only for mypy

### Add a Makefile / dev task runner

Agents benefit from named tasks they can discover and run rather than
reconstructing command strings from CLAUDE.md:

```makefile
.PHONY: test lint type-check check

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

With this in place, a CLAUDE.md instruction like "always run `make check` before
marking a task complete" gives agents a single reliable entry point.

### Add `# type: ignore` audit comments

Several `# type: ignore` and `Any` usages exist (`_account: Any`, `_mailbox: Any`,
`msg: Any` in `_message_to_email_data`). These are reasonable given the optional
O365 import, but they should carry explanatory comments so future agents don't
remove them or try to "fix" them:

```python
# O365.Account is only available when the optional 'O365' package is installed.
# We use Any here to avoid a hard import dependency at the class level.
self._account: Any | None = None
```

### Test file naming convention

The existing tests mix styles:
- `test_gmail_provider.py` — flat functions with `class Test*` grouping
- `test_outlook_provider.py` — `class Test*` with method grouping
- `test_provider_contract.py` — flat functions

Pick one pattern and document it in CLAUDE.md so agents generate consistent
test structure. Recommendation: `class Test<Feature>` grouping (matches the
outlook tests, easier to run a subset with `-k TestSync`).

### Autopilot spec improvements

Future `.dev/specs/` documents should include:

1. **Explicit mock contract** — specify which attributes/methods a mock must
   implement so the mock stays in sync when the real library changes
2. **Known limitations section** — "inbox-only search is acceptable for v1"
   prevents agents from gold-plating or filing unnecessary bugs
3. **Verification steps** — concrete commands to run after implementation to
   confirm correctness, e.g. "run `make check` and verify scenario #4 from
   `testing-o365.md`"
4. **Type annotation requirements** — "all public methods must have complete
   type annotations" as an explicit constraint avoids `Any` sprawl across phases
