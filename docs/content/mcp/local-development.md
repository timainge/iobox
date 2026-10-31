# Local Development

To test changes against your in-development checkout instead of the pip-installed version, point Claude Desktop at the project's editable install. Three options, ranked by ergonomics:

## Option A — editable install (recommended)

```bash
cd /path/to/iobox
uv sync --extra mcp
```

`uv sync` installs the project in editable mode by default, so `.venv/bin/iobox-mcp` resolves to live source under `src/iobox/`. Edits take effect on the next Claude Desktop relaunch — no reinstall needed.

Point Claude Desktop at the venv binary by absolute path so PATH resolution doesn't bite you:

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/path/to/iobox/.venv/bin/iobox-mcp",
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

Verify the binary is the editable one:

```bash
ls -la /path/to/iobox/.venv/bin/iobox-mcp
head -1 /path/to/iobox/.venv/bin/iobox-mcp   # shebang should be .venv/bin/python
```

## Option B — `uv run` (always uses the current lockfile)

```json
{
  "mcpServers": {
    "iobox": {
      "command": "uv",
      "args": ["--directory", "/path/to/iobox", "run", "iobox-mcp"],
      "env": {
        "IOBOX_MODE": "readonly",
        "PATH": "/Users/you/.local/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

`uv` must be discoverable at spawn time. Claude Desktop on macOS does not inherit your shell's `PATH`, so set it explicitly in `env` (use `which uv` to find the right prefix).

## Option C — explicit python + module

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/path/to/iobox/.venv/bin/python",
      "args": ["-m", "iobox.mcp_server"],
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

Equivalent to Option A but skips the console-script entry point. Useful when you're iterating on `pyproject.toml`'s `[project.scripts]` block itself.

## Switching back to the pip-installed version

Change `command` back to plain `"iobox-mcp"` (resolved via `PATH`) and restart. The two installs can coexist — pip puts `iobox-mcp` in your global Python's bin dir, the editable install puts one in `.venv/bin/`.

## Iteration loop

Code changes are picked up on Claude Desktop **process restart only** (Cmd-Q + relaunch, not just closing the window) — the MCP subprocess is long-lived for the session. Tail the log while iterating:

```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-iobox.log
```

A quick way to confirm the server is on local code: add a temporary `print("LOCAL DEV BUILD", file=sys.stderr)` to `main()` in `src/iobox/mcp_server.py` — it'll appear in the log on next launch.
