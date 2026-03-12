# Roadmap: iobox

- **Date**: 2026-03-07
- **Target**: Publish library — release to PyPI, deploy docs site, promote MCP integration
- **Effort**: 1–2 weeks

## Why This Target

All 9 development phases are complete — packaging, CI/CD, and docs are already scaffolded. The
project is a `git tag` and a `twine upload` away from being a real PyPI package, and the MCP
server is a timely differentiator worth promoting now.

## Steps to Ship

### Phase 1: PyPI Release
- [ ] Verify `pyproject.toml` version, classifiers, and `[project.urls]` (homepage, docs, changelog)
- [ ] Dry-run: `uv build && twine check dist/*`
- [ ] Configure PyPI Trusted Publishing (OIDC) in the PyPI project settings
- [ ] Tag `v1.0.0`, push tag — confirm CI `release.yml` publishes successfully
- [ ] Smoke-test: `pip install iobox` on a clean env, run `iobox --help` and `iobox auth-status`

### Phase 2: Docs & README
- [ ] Deploy MkDocs site via `mkdocs gh-deploy` or add GitHub Pages step to CI
- [ ] Update README: add PyPI badge, one-liner install, and MCP setup snippet for Claude Desktop
- [ ] Add a Quickstart doc page: authenticate → search → save in under 5 minutes
- [ ] Confirm `pip install iobox[mcp]` installs FastMCP and `mcp_server.py` is wired correctly

### Phase 3: O365 Provider (v1.1)
- [ ] Define `EmailProvider` abstract base class (search, fetch, send, label, trash, draft)
- [ ] Refactor Gmail modules to implement the interface without breaking existing CLI behavior
- [ ] Implement `OutlookProvider` using Microsoft Graph API per the O365 research in `.dev/`
- [ ] Add `--provider gmail|outlook` CLI flag with separate OAuth flow per provider
- [ ] Add mocked Graph API unit tests mirroring the Gmail test suite structure

## Claude Code Tooling

### Skills
- **claude-api**: Relevant if adding an AI-summarize or MCP tool-description generation step
  using the Anthropic SDK — this skill covers idiomatic SDK and agent patterns.

### Plugins / MCP Servers
- **iobox MCP server (self)**: Register `mcp_server.py` in Claude Desktop to dogfood the tool
  during development — the fastest way to find gaps in tool descriptions and error handling.

### Reference Material
- **`.dev/o365-research.md`** (or equivalent): The 6-enquiry, 42-source O365 analysis already
  in this repo is the spec for Phase 3 — use it directly to drive `OutlookProvider` implementation.
- **PyPI Trusted Publishing docs**: Covers the OIDC setup needed so the GitHub Actions release
  workflow can publish without a stored API token.
- **MkDocs Material + mkdocstrings**: Already in the project's doc dependencies — reference the
  mkdocstrings `:::` directive syntax to auto-generate API docs from existing Google-style docstrings.

## Success Criteria

- `pip install iobox` works on a clean machine and `iobox search -q "from:me" -m 5` returns results
- MkDocs documentation site is live at a public URL (GitHub Pages or equivalent)
- MCP server is listed in at least one public MCP registry or directory
