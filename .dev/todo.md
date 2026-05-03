# MCP Server — gaps to close for full workspace parity

Context: `src/iobox/mcp_server.py` was originally a thin Gmail-only wrapper. The
workspace layer (`Workspace`, `ProviderSlot`, `SpaceConfig`) and the three
provider ABCs now cover Gmail + O365 across email, calendar, and files with
both read and write surfaces. The MCP server has caught up on **read** for
calendar / files and on cross-type search, but is missing most **write**
operations and has zero Outlook/OneDrive coverage for email-style actions.

This is the punch list to bring MCP up to full workspace parity.

## 1. Replace Gmail-only email tools with workspace-routed equivalents

The current `search_gmail`, `get_email`, `save_email`, `save_thread`,
`save_emails_by_query`, `send_email`, `forward_gmail`,
`batch_forward_gmail`, drafts (`create_gmail_draft`, `list_gmail_drafts`,
`send_gmail_draft`, `delete_gmail_draft`), `modify_labels`,
`batch_modify_gmail_labels`, `trash_gmail`, `untrash_gmail`,
`batch_trash_gmail`, and `check_auth` all bypass the workspace and call
`_get_gmail_provider()` directly. Outlook users get nothing.

- [ ] Add `provider` slot-name argument (default = first email slot) to every
      email tool, mirroring the pattern already used by `get_event` /
      `get_file` (mcp_server.py:881, 940).
- [ ] Route reads through `Workspace.search_emails(EmailQuery, providers=...)`
      so a single `search_email` tool fans out across Gmail + Outlook slots.
- [ ] Route writes through `Workspace.get_email_provider(slot_name)` (already
      exists at workspace.py:229) so `send_email`, `forward_email`,
      `create_draft` etc. work for whichever slot the caller picks.
- [ ] Decide on naming: collapse `_gmail` suffixes (`forward_gmail` →
      `forward_email`, `trash_gmail` → `trash_email`, etc.) since the tools
      are no longer Gmail-specific. Keep old names as aliases for one release
      or accept the breaking change in 0.6.0.
- [ ] Keep the `_email_data_to_dict` `from_` → `from` shim — invariant
      documented in CLAUDE.md.

## 2. Calendar write tools (currently missing entirely)

Read coverage exists (`list_events`, `get_event`). All of these methods are
already on `CalendarProvider` (base.py:393-468) and exercised by the CLI:

- [ ] `create_event(title, start, end, attendees, description, location,
      provider=None)` → `CalendarProvider.create_event`
- [ ] `update_event(event_id, updates, provider=None)` →
      `CalendarProvider.update_event`
- [ ] `delete_event(event_id, provider=None)` →
      `CalendarProvider.delete_event`
- [ ] `rsvp_event(event_id, response, provider=None)` →
      `CalendarProvider.rsvp` (response: accepted | declined | tentative)
- [ ] `save_event(event_id, output_dir, provider=None)` →
      `convert_event_to_markdown` from `processing/markdown.py`
- [ ] Wire all into `_STANDARD_MCP` (mutating reads/saves) or `_DANGEROUS_MCP`
      (delete) in `modes.py:127-165`.

## 3. File write tools (currently missing entirely)

Read coverage exists (`list_files`, `get_file`, `get_file_content`). Provider
methods on `FileProvider` (base.py:479-548):

- [ ] `upload_file(local_path, name=None, folder_id=None, provider=None)` →
      `FileProvider.upload_file`
- [ ] `update_file(file_id, local_path, provider=None)` →
      `FileProvider.update_file`
- [ ] `delete_file(file_id, permanent=False, provider=None)` →
      `FileProvider.delete_file`
- [ ] `create_folder(name, parent_id=None, provider=None)` →
      `FileProvider.create_folder`
- [ ] `download_file(file_id, output_path, provider=None)` →
      `FileProvider.download_file` (returns bytes; MCP tool writes to disk)
- [ ] `save_file(file_id, output_dir, provider=None)` →
      `convert_file_to_markdown`
- [ ] Mode placement: writes in `_STANDARD_MCP`, `delete_file(permanent=True)`
      in `_DANGEROUS_MCP`.

## 4. Multi-account / multi-session surface

The workspace already supports multiple slots per type (Gmail + Outlook side
by side, multiple Gmail accounts, etc.). MCP needs to expose that:

- [ ] `list_workspaces()` → `space_config.list_spaces()` — returns name +
      active flag.
- [ ] `get_active_workspace()` → `space_config.get_active_space()`.
- [ ] `set_active_workspace(name)` → `space_config.set_active_space()`.
      Treat as standard-mode (config write, not data write).
- [ ] `list_provider_slots(workspace=None)` — enumerate
      `email_providers / calendar_providers / file_providers` with name, tags,
      account, mode. Lets the LLM discover which slot to target.
- [ ] Add an optional `workspace` argument (in addition to existing
      `provider`) to all workspace tools, so an MCP client can target a
      non-active workspace without first calling `set_active_workspace`. Today
      `_get_workspace()` (mcp_server.py:97) only loads the active space.
- [ ] `tags` argument on fan-out reads (`search_email`, `list_events`,
      `list_files`, `search_workspace`) — `Workspace._fan_out` already accepts
      `tags`, but the MCP layer drops it.

## 5. Outlook / O365 parity verification

Listed separately because it's the highest-risk area and gated by the M365
sandbox work (`.dev/testing-o365.md`):

- [ ] Once tools from §1 are workspace-routed, smoke-test them against an
      Outlook slot (search, get, send, draft, label, trash, forward).
- [ ] Verify ImmutableId IDs round-trip cleanly through MCP JSON
      (CLAUDE.md invariant).
- [ ] Verify `Workspace.search()` interleaves Gmail + Outlook results sorted
      by `created_at` desc with no provider-specific keys leaking.
- [ ] Verify OneDrive `upload_file`, `delete_file`, `create_folder` work via
      MCP after §3 lands.
- [ ] Verify `OutlookCalendarProvider.create_event` / `rsvp` work via MCP
      after §2 lands.
- [ ] Confirm Outlook search-folder limitation (inbox only — CLAUDE.md
      invariant) is surfaced in tool docstrings so the LLM doesn't promise
      "all mail" results.

## 6. Auth / session tools

`check_auth` (mcp_server.py:799) is Gmail-only. Workspace has
`auth_status()` (workspace.py:223) returning per-slot session state.

- [ ] `workspace_auth_status(workspace=None)` → returns
      `{slot_name: {authenticated, scopes, last_error}}` for every slot.
      Probably the right replacement for `check_auth`.
- [ ] Decide whether to expose `space_login` / `space_logout` as MCP tools.
      Both trigger interactive OAuth (`InstalledAppFlow.run_local_server`),
      which doesn't fit the MCP request/response model — likely **out of
      scope**, but document the limitation in mcp.md and tell users to run
      `iobox space login N` from the CLI first.

## 7. Mode allowlist updates

`modes.py:127-165` — every new tool above needs an entry. Suggested
placement:

- [ ] `_READONLY_MCP`: `search_email`, `get_email`, `save_email`,
      `save_thread`, `save_emails_by_query`, `save_event`, `save_file`,
      `download_file`, `list_workspaces`, `get_active_workspace`,
      `list_provider_slots`, `workspace_auth_status`.
- [ ] `_STANDARD_MCP`: existing drafts + label tools, plus `create_event`,
      `update_event`, `rsvp_event`, `upload_file`, `update_file`,
      `create_folder`, `delete_file(permanent=False)`,
      `set_active_workspace`.
- [ ] `_DANGEROUS_MCP`: existing send/forward/trash, plus `delete_event`,
      `delete_file(permanent=True)`. Consider whether `delete_event` belongs
      in standard rather than dangerous (it's recoverable in Google Calendar
      trash for ~30 days).

## 8. Docs rewrite — `docs/content/mcp.md`

- [ ] Replace "exposes Gmail operations" framing with "exposes workspace
      operations across email, calendar, files, and semantic search".
- [ ] Document `IOBOX_MODE` and which tools each mode unlocks, with a table
      keyed off the new `MCP_TOOLS_BY_MODE` allowlist.
- [ ] Standardise the Claude Desktop config snippet on the `iobox-mcp`
      console script (matches README), drop `python -m iobox.mcp_server`.
- [ ] Add a "Workspace prerequisites" section: `iobox space create`,
      `iobox space add ...`, `iobox space use NAME` before MCP starts.
- [ ] Document each new workspace tool from §1-§6 with signatures.
- [ ] Add cross-type usage examples ("what's on my calendar tomorrow",
      "find files about the migration project", "show me the Q4 report email
      and the related Drive doc").
- [ ] Cross-link to `workspace-guide.md` for slot/tag concepts referenced by
      `provider=` and `tags=` arguments.

## 9. Testing

- [ ] Unit tests for new tools using `_workspace_factory` injection
      (mcp_server.py:88, 94) — pass mock Workspace with mock slots.
- [ ] Test slot-routing precedence (named `provider` overrides default).
- [ ] Test partial-failure behaviour propagates as `error` keys, never
      exceptions (workspace invariant from CLAUDE.md).
- [ ] Test mode gating: in `readonly`, write tools must not be registered.
- [ ] Add an integration test that starts the MCP server with a
      multi-slot workspace (Gmail + Outlook) and exercises a fan-out search.

## 10. Nice-to-haves (deprioritised)

- [ ] `embed_resources(workspace=None, types=None)` MCP tool so an LLM can
      trigger semantic-index population without dropping to the CLI.
- [ ] `summarize_resource(id, resource_type)` MCP tool wrapping
      `processing/summarize.py` for the `iobox[ai]` extra.
- [ ] Streaming results for long fan-out queries (FastMCP supports it; would
      avoid blocking the LLM on slow Outlook calls).
