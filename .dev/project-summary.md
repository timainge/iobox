# Research Summary: iobox

- **Date**: 2026-03-06
- **Tech Stack**: Python 3.10+, Typer (CLI), Gmail API (google-api-python-client), html2text, PyYAML, FastMCP (optional), hatchling, MkDocs
- **Origin**: Original project by Tim Ainge — https://github.com/timainge/iobox
- **State**: Working — actively developed, all planned phases complete
- **Completion**: ~90% — core feature set finished, O365/Outlook expansion being researched
- **Branch**: main @ 1d18d2b

## What It Is

Iobox is a Gmail-to-Markdown CLI tool that searches, retrieves, and saves emails as Markdown files with YAML frontmatter. It wraps the Gmail API with a polished `typer`-based CLI covering search, save, send, forward, label management, trash, draft CRUD, and auth flows. It also ships an optional MCP server (`mcp_server.py`) exposing its functionality to Claude Desktop and similar AI tools.

## Current State

All 9 planned roadmap phases are marked complete, including packaging (PyPI-ready via hatchling), CI/CD (GitHub Actions), MkDocs documentation site, and MCP server integration. The codebase has ~3,900 lines of source and ~5,000 lines of tests across 10 unit test files and an integration suite with 21 live CLI scenarios. The two most recent commits add multi-account token support (per-account, per-scope-tier token namespacing) and O365 research documents exploring Microsoft Graph API parity for a future Outlook backend. Code is linted (ruff), typed (py.typed marker), and structured cleanly with clear module separation.

## Potential

This is a genuinely useful tool for anyone who wants to work with email programmatically — archiving newsletters, piping email content into AI workflows, building email-triggered automations. The MCP server integration is well-timed and differentiating. The O365 research (a thorough 6-enquiry, 42-source analysis) shows the project is considering a provider abstraction layer to support both Gmail and Outlook, which would significantly expand its audience. The tool is close to PyPI-publishable and has the documentation scaffold in place.

## Recommendation

**Action**: Finish & launch

The project is in excellent shape — clean code, good test coverage, proper packaging, and a thoughtful roadmap. The most valuable next steps are: (1) publish to PyPI (the `pyproject.toml` and CI release workflow are already scaffolded), (2) implement the O365/Outlook provider using the research already completed, and (3) promote the MCP server integration as a first-class feature given the current AI tooling momentum. The O365 expansion is the most impactful future investment — the research concludes full feature parity is achievable and maps out the exact API differences to bridge.
