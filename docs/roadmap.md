# Iobox Roadmap

This document covers the strategic direction for iobox: expanded Gmail API coverage, consumption modes, packaging, documentation, and CI/CD.

## Current State

Iobox currently implements:
- **Messages (read)**: `messages.list`, `messages.get` (metadata + full), `messages.attachments.get`
- **Messages (write)**: `messages.send` (plain text only)
- **Forwarding**: Retrieve-and-resend via `messages.send`
- **OAuth scopes**: `gmail.readonly` + `gmail.send`
- **CLI commands**: `search`, `save`, `send`, `forward`, `auth-status`, `version`
- **Output**: Markdown files with YAML frontmatter, optional attachment downloads

## 1. Gmail API Feature Gaps

### Critical Fixes

| Issue | Impact | Effort |
|---|---|---|
| **Pagination missing in `search_emails()`** — `nextPageToken` is never followed, silently truncating results beyond the first page | Data loss | Low |
| **Label IDs not resolved** — raw IDs like `Label_12345` appear in YAML frontmatter instead of human-readable names; one `labels.list` call (1 quota unit) would build an ID-to-name map | Usability | Low |

### High Priority — New Capabilities

| Feature | Gmail API Methods | Scope Change | Notes |
|---|---|---|---|
| **Label management** — mark read/unread, star, archive, apply custom labels | `messages.modify`, `messages.batchModify` | Add `gmail.modify` (replaces `readonly` + `send`) | Core email workflow; enables post-save tagging |
| **Trash/untrash** | `messages.trash`, `messages.untrash` | `gmail.modify` | Safe (reversible) message management |
| **Thread-level export** | `threads.get` | No change | `thread_id` already captured in frontmatter; fetch all messages in a thread as a single markdown file |
| **Profile in auth-status** | `users.getProfile` | No change | Shows authenticated email address, mailbox size, `historyId`; 1 quota unit |
| **Include spam/trash flag** | `messages.list` `includeSpamTrash` param | No change | Expose as `--include-spam-trash` on search/save |

### Medium Priority

| Feature | Notes |
|---|---|
| **Draft management** — create, list, send drafts | Requires `gmail.compose` scope; natural "compose now, send later" workflow |
| **HTML email sending** | Current `compose_message()` only does plain text `MIMEText`; support HTML body and attachments |
| **HTTP batch requests** | Combine multiple `messages.get` calls into one HTTP request; cuts round-trips in half for batch save |
| **Incremental sync via `history.list`** | Store `historyId` between runs; only fetch new/changed messages; requires persistent state file |

### Low Priority / Niche

- `settings.filters.list/create` — manage Gmail filter rules from CLI
- `settings.sendAs.list` — inspect configured send-as aliases and signatures
- Vacation responder (`getVacation` / `updateVacation`)
- Push notifications (`users.watch`) — requires a running server, not applicable to CLI
- `messages.import` / `messages.insert` — migration use cases

### OAuth Scope Strategy

Current scopes are `gmail.readonly` + `gmail.send`. To enable label management and trash operations, the recommended upgrade path is:

| Phase | Scopes | Enables |
|---|---|---|
| Current | `readonly` + `send` | Search, save, send, forward |
| Phase 2 | `modify` (replaces both) | + label management, trash, archive, star |
| Phase 3 | `modify` + `compose` | + draft create/list/send |

### Quota Impact Reference

| Operation | Units | Current usage for N emails |
|---|---|---|
| `messages.list` | 5 | 1 call |
| `messages.get` | 5 | 2N calls (metadata + full) |
| `messages.send` | 100 | 1 per send/forward |
| `labels.list` | 1 | 0 (should be 1) |
| `getProfile` | 1 | 0 (should be 1) |
| Per-user limit | 15,000 units/min | Batch save of 50 emails = ~505 units |

## 2. Consumption Modes

### CLI (current)

The Typer-based CLI is the primary interface. No changes needed to the architecture — it correctly acts as a thin orchestration layer over the library modules.

One improvement: move `download_email_attachments` from `cli.py` into `file_manager.py` — it contains business logic that should be in the library layer.

### Library (Python import)

Currently `src/iobox/__init__.py` only exports `__version__`. Anyone using iobox as a library must know the internal module names.

**Action**: Expand `__init__.py` to expose the full public API with `__all__`:
- `get_gmail_service`, `check_auth_status`
- `search_emails`, `validate_date_format`
- `get_email_content`, `download_attachment`
- `convert_email_to_markdown`, `convert_html_to_markdown`
- `save_email_to_markdown`, `create_output_directory`, `check_for_duplicates`, `save_attachment`
- `send_message`, `compose_message`, `forward_email`

Add a `py.typed` marker (PEP 561) for downstream type checkers.

Add `src/iobox/__main__.py` to enable `python -m iobox`.

### MCP Server (new)

Create `src/iobox/mcp_server.py` using FastMCP (`mcp` package) to expose iobox functions as tools for Claude Desktop, Cursor, VS Code, and other MCP-compatible hosts.

Tools to expose:

| Tool | Wraps | Description |
|---|---|---|
| `search_gmail` | `search_emails` | Search Gmail by query, date range, max results |
| `save_email` | `get_email_content` + `save_email_to_markdown` | Retrieve and save a message as markdown |
| `send_email` | `compose_message` + `send_message` | Compose and send a new email |
| `forward_gmail_message` | `forward_email` | Forward an existing message |
| `check_auth` | `check_auth_status` | Check authentication state |

Transport: `stdio` (standard for CLI-launched MCP servers).

Registration example for Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "iobox": {
      "command": "python",
      "args": ["-m", "iobox.mcp_server"]
    }
  }
}
```

Add `mcp` as an optional dependency: `pip install iobox[mcp]`.

## 3. Packaging and Distribution

### Replace `setup.py` with `pyproject.toml`

The `setup.py` is legacy. Migrate to `pyproject.toml` with hatchling as the build backend:

- Declare all dependencies, optional dependency groups (`dev`, `docs`, `mcp`)
- Move `pytest.ini` config into `[tool.pytest.ini_options]`
- Add ruff config in `[tool.ruff]`
- Add mypy config in `[tool.mypy]`
- Set `[project.scripts] iobox = "iobox.cli:app"`

### Version Single Source of Truth

Currently `__version__` is hardcoded in both `__init__.py` and `cli.py`. Fix:

1. Define version once in `pyproject.toml` `[project] version = "0.2.0"` (or use `hatch-vcs` for git-tag-based versioning)
2. In `__init__.py`, read via `importlib.metadata.version("iobox")`
3. In `cli.py`, import from `iobox.__version__`

### PyPI Publishing

Prerequisites:
- `pyproject.toml` with `[project]` table
- `LICENSE` file (MIT)
- `README.md`
- PyPI classifiers

Use Trusted Publishing (OIDC) with GitHub Actions — no long-lived API tokens needed.

## 4. CI/CD

### CI Workflow (`.github/workflows/ci.yml`)

Triggers on push/PR to `main`:
- **Lint**: `ruff check` + `ruff format --check`
- **Test**: pytest across Python 3.9–3.12 matrix with coverage threshold (`--cov-fail-under=80`)
- **Coverage reporting**: Upload to Codecov

### Release Workflow (`.github/workflows/release.yml`)

Triggers on `v*` tag push:
1. Run the CI workflow
2. Build with `python -m build` (or `uv build`)
3. Publish to PyPI via `pypa/gh-action-pypi-publish` with `id-token: write` (Trusted Publishing)

### Pre-commit Hooks

`.pre-commit-config.yaml` with:
- `ruff-check` (with `--fix`)
- `ruff-format`

## 5. Documentation Site

### mkdocs-material

Use Material for MkDocs with mkdocstrings for auto-generated API docs from Google-style docstrings (already used consistently in the codebase).

Suggested site structure:

```
docs/
├── index.md                    # Home / overview
├── getting-started/
│   ├── installation.md
│   ├── authentication.md       # (existing docs/authentication.md)
│   └── quickstart.md
├── cli/
│   ├── search.md
│   ├── save.md
│   ├── send.md
│   ├── forward.md
│   └── auth-status.md
├── api/                        # Auto-generated from docstrings
│   ├── auth.md
│   ├── email_search.md
│   ├── email_retrieval.md
│   ├── markdown_converter.md
│   ├── file_manager.md
│   └── email_sender.md
├── mcp.md                      # MCP server setup and usage
├── integrations.md             # (existing docs/integrations.md)
├── roadmap.md                  # This file
└── changelog.md
```

Deploy to GitHub Pages: `mkdocs gh-deploy` or via GitHub Actions.

Add `mkdocs-material` and `mkdocstrings[python]` as optional docs dependencies.

## 6. Implementation Order

| Phase | Items | Estimated Effort |
|---|---|---|
| **Phase 1: Foundation** | `pyproject.toml` migration, version fix, `__init__.py` public API, `py.typed`, `__main__.py`, `LICENSE` | 1 session |
| **Phase 2: Critical fixes** | Pagination in `search_emails()`, label name resolution, `getProfile` in auth-status | 1 session |
| **Phase 3: CI/CD** | `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.pre-commit-config.yaml`, ruff config | 1 session |
| **Phase 4: MCP server** | `src/iobox/mcp_server.py`, optional `mcp` dependency, Claude Desktop config docs | 1 session |
| **Phase 5: Gmail write ops** | `messages.modify` (label/star/archive), `messages.trash`, scope upgrade to `gmail.modify` | 1–2 sessions |
| **Phase 6: Docs site** | mkdocs-material setup, CLI reference pages, API reference, deploy to GitHub Pages | 1–2 sessions |
| **Phase 7: Enhanced send** | HTML email body, attachment sending, draft management | 1–2 sessions |
| **Phase 8: Performance** | HTTP batch requests, incremental sync via `history.list`, thread-level export | 2–3 sessions |
