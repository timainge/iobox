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
| `"Email provider 'X' not found"` | `provider` arg doesn't match any slot | Call `list_provider_slots` to see valid names |
| Tool returns `{"error": "..."}` mentioning auth | Token expired or revoked | Run `iobox space login N` from the CLI to re-authenticate |
| Server keeps restarting | Crashing on startup | Check `mcp-server-iobox.log` for the traceback; common cause is missing `credentials.json` |

## OAuth can't run inside the host

Interactive OAuth (`iobox space add`, `iobox space login`) needs a browser handoff, which doesn't work from the spawned MCP subprocess. Always run those commands in a normal terminal, then restart the host so the server picks up the new tokens.
