# Installation

## Requirements

- Python 3.10 or higher
- A Google account and/or a Microsoft 365 account

## Install

```bash
pip install iobox
```

This installs the `iobox` CLI and the Python package with Google support (Gmail, Calendar, Drive).

## Optional extras

Install only what you need:

| Extra | Adds | Install |
|---|---|---|
| `outlook` | Microsoft 365 — Outlook, Outlook Calendar, OneDrive | `pip install 'iobox[outlook]'` |
| `mcp` | The `iobox-mcp` server for Claude Desktop and other MCP hosts | `pip install 'iobox[mcp]'` |
| `ai` | Claude-powered summaries (`iobox.processing.summarize`) | `pip install 'iobox[ai]'` |
| `semantic` | Embedding index and semantic search | `pip install 'iobox[semantic]'` |

Combine them: `pip install 'iobox[mcp,outlook]'`.

!!! tip
    For a standalone CLI install, `pipx install 'iobox[mcp]'` or `uv tool install 'iobox[mcp]'` keeps iobox isolated and puts both `iobox` and `iobox-mcp` on your `PATH`.

## Verify

```bash
iobox version
```

## Install from source

```bash
git clone https://github.com/timainge/iobox.git
cd iobox
uv sync                 # editable install with dev dependencies
uv run iobox version
```

To build these docs locally:

```bash
pip install 'iobox[docs]'
mkdocs serve -f docs/mkdocs.yml
```

## Next

Connect an account: [Google](connect-google.md) or [Microsoft 365](connect-microsoft.md).
