---
id: task-020
title: "PyPI v1.0.0 release + docs update"
milestone: deferred
status: done
priority: p3
depends_on: []
blocks: []
parallel_with: []
estimated_effort: M
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Iobox has been installable from source but not yet published to PyPI. This task prepares and executes the v1.0.0 public release, updates README and MkDocs documentation, and ensures the packaging is correct for all optional dependency groups.

This is independent of the Workspace expansion tasks — it can be done at any time, but makes most sense after at least the core email functionality is stable (current state) and ideally after the PoC (tasks 001–008).

## Scope

**Does:**
- Bump version to `1.0.0` in `pyproject.toml`
- Verify all optional dependency groups are correct: `outlook`, `mcp`, `ai`, and potentially `google-calendar`, `google-drive`
- Dry-run build and check: `uv build && twine check dist/*`
- Tag `v1.0.0` and push — CI publishes to PyPI
- Update README: PyPI badge, install instructions, workspace quickstart, MCP setup
- Update MkDocs docs: new CLI commands, workspace config guide, provider setup guides
- Update `mkdocs.yml` nav for new pages

**Does NOT:**
- Implement any new features
- Change any provider or CLI behavior
- Publish pre-release or beta versions

## Strategic Fit

Public PyPI release makes iobox discoverable and installable without cloning the repo. It's the "done" milestone for the current email-focused phase. The v1.x releases will add workspace/calendar/files capabilities.

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `pyproject.toml` | Bump version, verify optional groups |
| Modify | `README.md` | PyPI badge, install instructions, quickstart |
| Modify | `mkdocs.yml` | Nav for new docs pages |
| Create | `docs/workspace-guide.md` | Workspace setup + space commands |
| Create | `docs/providers/google-calendar.md` | GCal setup guide |
| Create | `docs/providers/google-drive.md` | GDrive setup guide |

## Version Bump

```toml
# pyproject.toml
[project]
version = "1.0.0"

[project.optional-dependencies]
outlook = ["O365>=2.0"]
mcp = ["mcp>=1.0"]
ai = ["anthropic>=0.40"]
# New groups added alongside Workspace expansion:
# google = ["google-api-python-client>=2.100", ...]  # already in base deps
```

## Packaging Checklist

- [ ] `uv build` produces both sdist and wheel
- [ ] `twine check dist/*` reports no issues
- [ ] All optional groups install cleanly: `pip install 'iobox[outlook]'`, `pip install 'iobox[mcp]'`, `pip install 'iobox[ai]'`
- [ ] `pip install iobox` (base, no extras) installs and `iobox --help` works

## README Updates

Key sections to add/update:
1. PyPI badge at top: `[![PyPI](https://img.shields.io/pypi/v/iobox)](https://pypi.org/project/iobox/)`
2. Install section:
   ```bash
   pip install iobox
   pip install 'iobox[outlook]'   # for Microsoft 365 / Outlook
   pip install 'iobox[mcp]'       # for MCP server
   pip install 'iobox[ai]'        # for AI summarization
   ```
3. Quickstart: OAuth setup, first search command
4. MCP setup snippet (Claude Desktop config)

## MkDocs Updates

```yaml
# mkdocs.yml nav additions
nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/installation.md
    - Authentication: getting-started/authentication.md
  - Workspace:
    - Setup: workspace/setup.md
    - Space Commands: workspace/space-commands.md
  - Providers:
    - Gmail: providers/gmail.md
    - Outlook: providers/outlook.md
    - Google Calendar: providers/google-calendar.md
    - Google Drive: providers/google-drive.md
  - CLI Reference: cli-reference.md
  - MCP Server: mcp-server.md
```

## Release Process

### Step 1 — Final pre-release check

```bash
make check   # lint + type-check + tests
uv build
twine check dist/*
```

### Step 2 — Update version

```bash
# pyproject.toml: version = "1.0.0"
# Update CHANGELOG.md if it exists
```

### Step 3 — Tag and push

```bash
git tag v1.0.0
git push origin v1.0.0
```

### Step 4 — Verify CI

CI pipeline (`.github/workflows/`) should detect the tag and publish to PyPI automatically. Verify the workflow exists and has `PYPI_TOKEN` secret configured.

### Step 5 — Verify PyPI

```bash
pip install iobox==1.0.0
iobox --version
```

## Key Decisions

**Q: Should we use `1.0.0` or start with `0.x`?**
`1.0.0` signals stable public API. The email functionality is stable. Calendar/file features will be `1.1.x`, `1.2.x`.

**Q: Should optional groups be split (e.g., separate `google-calendar` vs base Google deps)?**
Keep it simple for v1.0: `google` (or just base deps), `outlook`, `mcp`, `ai`. Split into finer groups in a future release if user feedback requests it.

**Q: Should docs be deployed before PyPI?**
Yes — deploy docs first so the PyPI package page links to live documentation.

## Verification

```bash
pip install iobox==1.0.0
iobox --help
iobox version
pip install 'iobox[outlook]==1.0.0'
pip install 'iobox[mcp]==1.0.0'
pip install 'iobox[ai]==1.0.0'
```

## Acceptance Criteria

- [ ] `pyproject.toml` version bumped to `1.0.0`
- [ ] `uv build` succeeds, produces sdist + wheel
- [ ] `twine check dist/*` passes
- [ ] All optional install groups install cleanly
- [ ] README has PyPI badge and updated install instructions
- [ ] `git tag v1.0.0` pushed
- [ ] CI publishes to PyPI
- [ ] `pip install iobox` works from PyPI
- [ ] MkDocs docs updated with new pages
- [ ] `iobox version` shows `1.0.0`
