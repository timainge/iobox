# Iobox Roadmap

Strategic direction for iobox, organized by implementation phase. Functional enhancements first, then integration and distribution work.

Each phase has a dedicated spec doc in `docs/specs/` with detailed requirements, file changes, and acceptance criteria.

## Current State

- **CLI commands**: `search`, `save`, `send`, `forward`, `auth-status`, `version`
- **Gmail API coverage**: `messages.list`, `messages.get`, `messages.attachments.get`, `messages.send`
- **OAuth scopes**: `gmail.readonly` + `gmail.send`
- **Output**: Markdown + YAML frontmatter, optional attachment downloads
- **Packaging**: `setup.py` (legacy), no CI/CD, no PyPI publishing

## Phase Overview

| # | Phase | Spec | Status |
|---|---|---|---|
| 1 | [Critical Bug Fixes](#phase-1-critical-bug-fixes) | [specs/01-critical-fixes.md](specs/01-critical-fixes.md) | Not started |
| 2 | [Gmail Read Enhancements](#phase-2-gmail-read-enhancements) | [specs/02-read-enhancements.md](specs/02-read-enhancements.md) | Not started |
| 3 | [Gmail Write Operations](#phase-3-gmail-write-operations) | [specs/03-write-operations.md](specs/03-write-operations.md) | Not started |
| 4 | [Enhanced Send and Drafts](#phase-4-enhanced-send-and-drafts) | [specs/04-send-and-drafts.md](specs/04-send-and-drafts.md) | Not started |
| 5 | [Performance](#phase-5-performance) | [specs/05-performance.md](specs/05-performance.md) | Not started |
| 6 | [Packaging and Distribution](#phase-6-packaging-and-distribution) | [specs/06-packaging.md](specs/06-packaging.md) | Not started |
| 7 | [MCP Server](#phase-7-mcp-server) | [specs/07-mcp-server.md](specs/07-mcp-server.md) | Not started |
| 8 | [CI/CD](#phase-8-cicd) | [specs/08-cicd.md](specs/08-cicd.md) | Not started |
| 9 | [Documentation Site](#phase-9-documentation-site) | [specs/09-docs-site.md](specs/09-docs-site.md) | Not started |

---

## Phase 1: Critical Bug Fixes

Fix data-loss bugs and usability issues in the existing functionality.

- **Pagination**: `search_emails()` ignores `nextPageToken`, silently truncating results
- **Label resolution**: Raw label IDs (`Label_12345`) in YAML frontmatter instead of human-readable names

## Phase 2: Gmail Read Enhancements

Expand read capabilities using existing `gmail.readonly` scope.

- **Thread-level export**: Fetch all messages in a thread as a single markdown file
- **Profile in auth-status**: Show authenticated email address and mailbox stats via `users.getProfile`
- **Include spam/trash**: Expose `includeSpamTrash` as a CLI flag

## Phase 3: Gmail Write Operations

Add label management and message state changes. Requires scope upgrade to `gmail.modify`.

- **Label management**: Mark read/unread, star/unstar, archive, apply custom labels via `messages.modify`
- **Bulk label operations**: `messages.batchModify` for efficient batch tagging
- **Trash/untrash**: Safe (reversible) message deletion

## Phase 4: Enhanced Send and Drafts

Upgrade email composition from plain text to full MIME support.

- **HTML email sending**: Support HTML body and inline attachments in `compose_message()`
- **Attachment sending**: Attach files to outgoing emails
- **Draft management**: Create, list, and send drafts via `drafts.*` methods

## Phase 5: Performance

Reduce API round-trips and enable efficient repeated syncing.

- **HTTP batch requests**: Combine multiple `messages.get` calls into single HTTP requests
- **Incremental sync**: Use `history.list` to only fetch new/changed messages between runs
- **Refactor `download_email_attachments`**: Move business logic from `cli.py` to `file_manager.py`

## Phase 6: Packaging and Distribution

Modernize packaging for PyPI publishing and library consumption.

- **`pyproject.toml`**: Replace `setup.py` with hatchling-based config
- **Version single source of truth**: `importlib.metadata` instead of hardcoded `__version__`
- **Public API surface**: Expand `__init__.py` with `__all__` for library consumers
- **`py.typed` marker**: PEP 561 support for downstream type checkers
- **`__main__.py`**: Enable `python -m iobox`

## Phase 7: MCP Server

Expose iobox as an MCP tool server for Claude Desktop, Cursor, and VS Code.

- **`src/iobox/mcp_server.py`**: FastMCP-based server with search, save, send, forward tools
- **Optional dependency**: `pip install iobox[mcp]`
- **stdio transport**: Standard for CLI-launched MCP servers

## Phase 8: CI/CD

Automate testing, linting, and publishing via GitHub Actions.

- **CI workflow**: Lint (ruff) + test (pytest matrix) on push/PR
- **Release workflow**: Build and publish to PyPI on tag push via Trusted Publishing (OIDC)
- **Pre-commit hooks**: ruff-check + ruff-format

## Phase 9: Documentation Site

User-facing documentation site with auto-generated API reference.

- **mkdocs-material**: Markdown-native static site with search
- **mkdocstrings**: Auto-generate API docs from Google-style docstrings
- **GitHub Pages**: Deploy via `mkdocs gh-deploy` or CI

---

## OAuth Scope Progression

| Phase | Scopes | Enables |
|---|---|---|
| Current | `readonly` + `send` | Search, save, send, forward |
| Phase 3 | `modify` (replaces both) | + label management, trash, archive, star |
| Phase 4 | `modify` + `compose` | + draft create/list/send |

## Status Legend

- Not started
- In progress
- Blocked
- Complete
