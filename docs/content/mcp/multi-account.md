# Multi-account

The headline use case: one assistant conversation that can see your personal *and* work accounts — mail, calendars, and drives — at once.

## Set up two accounts

```bash
iobox space create personal
iobox space add google personal@gmail.com --email --calendar --drive --read
iobox space add google work@gmail.com --email --calendar --drive --read
iobox space status
```

```
#  service  account             scopes                 mode      status
1  google   personal@gmail.com  email,calendar,drive   readonly  ✓ authenticated
2  google   work@gmail.com      email,calendar,drive   readonly  ✓ authenticated
```

That produces six [slots](../get-started/concepts.md#slot):

| | Email | Calendar | Files |
|---|---|---|---|
| personal@gmail.com | `personal-gmail` | `personal-gmail-cal` | `personal-gmail-drive` |
| work@gmail.com | `work-gmail` | `work-gmail-cal` | `work-gmail-drive` |

Restart your MCP host so the server picks up the new accounts.

## Fan-out (default)

Omit `provider` and a tool queries every slot of its type in parallel, then merges and sorts the results.

```text
User   → "Find every email from accountant@example.com across both accounts."
Claude → search_gmail(query="from:accountant@example.com", days=90)
           ↳ personal-gmail and work-gmail in parallel
```

`search_workspace` goes further and fans out across *types* too:

```text
User   → "Everything about the Henderson project."
Claude → search_workspace(query="Henderson")
           ↳ email, calendar, and files across all six slots
```

If a slot fails — an expired token, a network error — it's logged and skipped. The remaining slots still return.

## Targeting one account

Every workspace tool accepts `provider="<slot-name>"`:

```text
User   → "What's on my work calendar next week?"
Claude → list_events(after="2026-11-02", before="2026-11-09", provider="work-gmail-cal")
```

Assistants discover slot names with `list_provider_slots`:

```json
{
  "workspace": "personal",
  "email":    [{"name": "personal-gmail", "tags": [], "provider_class": "GmailProvider"},
               {"name": "work-gmail",     "tags": [], "provider_class": "GmailProvider"}],
  "calendar": [{"name": "personal-gmail-cal", ...}, {"name": "work-gmail-cal", ...}],
  "file":     [{"name": "personal-gmail-drive", ...}, {"name": "work-gmail-drive", ...}]
}
```

!!! tip
    Fetch-by-ID tools (`get_email`, `get_event`, `get_file`, …) use the **first** slot of their type when `provider` is omitted. When working across accounts, pass the same `provider` that the search result came from.

## Multiple workspaces

Every tool also accepts `workspace="<name>"` to query a workspace other than the active one. `list_workspaces` shows what's available, and `set_active_workspace` (`standard` mode) switches the default.

## Prompts that exercise this well

- *"List my workspaces and the provider slots in each."*
- *"Search both Gmail accounts for invoices this month and list them by sender."*
- *"Compare my personal and work calendars next week and find a free hour on Thursday."*
- *"What's the auth status of each slot?"* — calls `workspace_auth_status`.
