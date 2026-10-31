# Troubleshooting

## Confirm the server is running

1. Look for the **slider icon** (MCP indicator) at the bottom-right of the Claude Desktop input box.
2. Ask Claude: *"List my workspaces."* — should return your configured workspace and the active one.
3. Ask Claude: *"What's the auth status of each provider slot?"* — calls `workspace_auth_status` and returns per-slot OK/error.

## Reading logs

| OS | Log directory |
|---|---|
| macOS | `~/Library/Logs/Claude/` |
| Windows | `%APPDATA%\Claude\logs\` |

Two files matter:

- `mcp.log` — Claude Desktop's own MCP client log
- `mcp-server-iobox.log` — stdout/stderr of the `iobox-mcp` process

Tail both on macOS:

```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
```

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Slider icon missing | Claude Desktop didn't spawn the server | Check `mcp.log` for spawn errors; verify `iobox-mcp` is on `PATH` (`which iobox-mcp`); ensure `pip install 'iobox[mcp]'` ran in the same Python that owns `iobox-mcp` |
| Tools list is empty | `IOBOX_MODE` set to a value with few tools, or workspace not configured | Check `IOBOX_MODE` is a valid value; run `iobox space status` to confirm slots exist |
| `"No active workspace configured"` | Server can't find a workspace | Run `iobox space create NAME` then `iobox space add google ...`; confirm with `iobox space list` |
| `"Could not load workspace 'X'"` | `workspace` arg misspelled, or the workspace TOML is invalid | Call `list_workspaces` for valid names; run `iobox space status` to check the config |
| `"Email provider 'X' not found"` | `provider` arg doesn't match any slot | Call `list_provider_slots` to see valid names |
| `"... is outside the iobox MCP root"` | A path argument points outside `IOBOX_MCP_ROOT` | Use a path inside the root (default `~/iobox`), or change it — see [file access root](configuration.md#file-access-root) |
| `"No cached token; run iobox space login"` | That slot has never been signed in | Run `iobox space login N` in a terminal |
| Tool returns `{"error": "..."}` mentioning auth | Token expired or revoked | Run `iobox space login N` from the CLI to re-authenticate |
| Server keeps restarting | Crashing on startup | Check `mcp-server-iobox.log` for the traceback; common cause is missing `credentials.json` |

## OAuth can't run inside the host

Interactive OAuth (`iobox space add`, `iobox space login`) needs a browser handoff, which doesn't work from the spawned MCP subprocess. Always run those commands in a normal terminal, then restart the host so the server picks up the new tokens.

`check_auth` and `workspace_auth_status` never start a sign-in themselves: `check_auth` reads cached tokens only, and `workspace_auth_status` skips any slot that has no cached token. Other tools still call the provider directly, so a slot with no token can still try to open a browser sign-in from inside the server — sign in from the terminal first.
