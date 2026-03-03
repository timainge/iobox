# Phase 9: Documentation Site

**Status**: Not started
**Priority**: Low — user-facing docs site, not blocking other work
**Scope change**: None (project infrastructure only)
**Depends on**: Phase 6 (pyproject.toml with docs optional dependency)

---

## Overview

Build a documentation site using Material for MkDocs with auto-generated API reference from existing Google-style docstrings.

## Dependencies

```
pip install iobox[docs]
```

In `pyproject.toml`:
```toml
[project.optional-dependencies]
docs = [
    "mkdocs-material>=9.0",
    "mkdocstrings[python]>=0.25",
]
```

---

## 9.1 mkdocs.yml Configuration

### Required Changes

**Create**: `mkdocs.yml` at project root

```yaml
site_name: iobox
site_description: Gmail to Markdown Converter
site_url: https://yourusername.github.io/iobox
repo_url: https://github.com/yourusername/iobox

theme:
  name: material
  features:
    - navigation.instant
    - navigation.tabs
    - navigation.sections
    - search.suggest
    - content.code.copy
  palette:
    - scheme: default
      primary: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
          options:
            docstring_style: google
            show_source: true
            show_bases: false
            heading_level: 3

nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/installation.md
    - Authentication: getting-started/authentication.md
    - Quick Start: getting-started/quickstart.md
  - CLI Reference:
    - search: cli/search.md
    - save: cli/save.md
    - send: cli/send.md
    - forward: cli/forward.md
    - auth-status: cli/auth-status.md
  - API Reference:
    - auth: api/auth.md
    - email_search: api/email_search.md
    - email_retrieval: api/email_retrieval.md
    - email_sender: api/email_sender.md
    - markdown_converter: api/markdown_converter.md
    - file_manager: api/file_manager.md
    - utils: api/utils.md
  - MCP Server: mcp.md
  - Integrations: integrations.md
  - Roadmap: roadmap.md
  - Changelog: changelog.md

markdown_extensions:
  - admonition
  - pymdownx.highlight
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - toc:
      permalink: true
```

---

## 9.2 Documentation Pages

### Site Structure

```
docs/
├── index.md                          # Home page with overview and quick links
├── getting-started/
│   ├── installation.md               # pip install, prerequisites, credentials setup
│   ├── authentication.md             # Existing docs/authentication.md (move)
│   └── quickstart.md                 # 5-minute tutorial: search → save → view
├── cli/
│   ├── search.md                     # search command reference with examples
│   ├── save.md                       # save command (single + batch) with examples
│   ├── send.md                       # send command with examples
│   ├── forward.md                    # forward command with examples
│   └── auth-status.md               # auth-status command
├── api/
│   ├── auth.md                       # ::: iobox.auth
│   ├── email_search.md               # ::: iobox.email_search
│   ├── email_retrieval.md            # ::: iobox.email_retrieval
│   ├── email_sender.md               # ::: iobox.email_sender
│   ├── markdown_converter.md         # ::: iobox.markdown_converter
│   ├── file_manager.md               # ::: iobox.file_manager
│   └── utils.md                      # ::: iobox.utils
├── mcp.md                            # MCP server setup and Claude Desktop config
├── integrations.md                   # Existing docs/integrations.md (move)
├── roadmap.md                        # Existing docs/roadmap.md (move)
├── specs/                            # Spec docs (not in nav, available via direct link)
└── changelog.md                      # Release notes
```

### API Reference Pages

Each API reference page uses mkdocstrings auto-generation:

```markdown
# Email Search

::: iobox.email_search
    options:
      members:
        - search_emails
        - validate_date_format
```

### CLI Reference Pages

Each CLI page documents:
- Command syntax
- All options with descriptions
- 2-3 usage examples
- Example output

---

## 9.3 Deployment

### GitHub Pages (manual)

```bash
mkdocs gh-deploy
```

### GitHub Actions (automated)

Add to `.github/workflows/ci.yml` or create `.github/workflows/docs.yml`:

```yaml
name: Deploy Docs
on:
  push:
    branches: [main]
    paths: [docs/**, mkdocs.yml]

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[docs]"
      - run: mkdocs gh-deploy --force
```

---

## Acceptance Criteria

- [ ] `mkdocs serve` starts a local preview server at localhost:8000
- [ ] All nav pages render without errors
- [ ] API reference pages auto-generate from docstrings
- [ ] CLI reference pages have accurate command syntax and examples
- [ ] Search works across all pages
- [ ] Dark/light mode toggle works
- [ ] `mkdocs gh-deploy` publishes to GitHub Pages
- [ ] Docs CI workflow deploys on push to main (when docs change)

## Files Created/Modified

| Action | File |
|---|---|
| Create | `mkdocs.yml` |
| Create | `docs/index.md` |
| Create | `docs/getting-started/installation.md` |
| Create | `docs/getting-started/quickstart.md` |
| Create | `docs/cli/search.md`, `save.md`, `send.md`, `forward.md`, `auth-status.md` |
| Create | `docs/api/auth.md`, `email_search.md`, `email_retrieval.md`, `email_sender.md`, `markdown_converter.md`, `file_manager.md`, `utils.md` |
| Create | `docs/mcp.md` |
| Create | `docs/changelog.md` |
| Move | `docs/authentication.md` → `docs/getting-started/authentication.md` |
| Move | `docs/integrations.md` → stays or moves to match nav |
