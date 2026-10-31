# Testing O365 / Outlook Support

## What the current test suite covers

All existing tests are **unit tests with mocks** — they exercise logic paths in
`OutlookProvider` and `GmailProvider` but never touch a real Microsoft Graph
endpoint. Coverage includes:

- `_message_to_email_data` field normalization
- `search_emails` / `get_email_content` / `batch_get_emails` / `get_thread`
- `send_message` / `forward_message` / draft CRUD
- `mark_read` / `set_star` / `archive` / `trash` / `untrash`
- `add_tag` / `remove_tag` / `list_tags`
- Delta sync: normal response, 410-Gone fallback, multi-page paging
- Query translation: `$filter` vs `$search` path selection, `raw_query` passthrough
- Provider contract: both providers implement all ABC methods, return correct types
- Markdown parity: identical `EmailData` content produces identical markdown

What the mocks **cannot** verify:

- OData filter expressions accepted by Graph (e.g. the `categories/any` lambda)
- `$filter` + `$search` mutual exclusion enforcement
- ImmutableId header actually preventing ID rotation across folder moves
- Delta token lifetime and 410 recovery in a live environment
- python-o365 `Query` builder fluent API behavior vs our mock assumptions
- Auth token refresh across the full MSAL/O365 lifecycle

---

## Option A — Microsoft 365 Developer Program (recommended)

Free 90-day renewable sandbox tenant. Full M365 environment with dummy users and
pre-seeded email data. The right tool for a real live test suite.

### Setup steps

1. Sign up at https://developer.microsoft.com/microsoft-365/dev-program
   - Use a personal Microsoft account (not a work/school account)
   - Choose "Instant sandbox" — pre-populated with users and sample data
   - Tenant domain will be something like `youralias.onmicrosoft.com`

2. Register an app in Entra ID (Azure AD)
   - Go to https://entra.microsoft.com → App registrations → New registration
   - Name: `iobox-dev`
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: `http://localhost` (for browser flow) or skip (for device-code flow)
   - After creation, note the **Application (client) ID** and **Directory (tenant) ID**

3. Add API permissions
   - API permissions → Add a permission → Microsoft Graph → Delegated
   - Add: `Mail.ReadWrite`, `Mail.Send`
   - Click "Grant admin consent for [tenant]"

4. Configure iobox
   ```
   OUTLOOK_CLIENT_ID=<Application (client) ID>
   OUTLOOK_TENANT_ID=<Directory (tenant) ID>
   # OUTLOOK_CLIENT_SECRET is optional for public-client (desktop) flows
   ```

5. Authenticate using device-code flow (works in any terminal, no browser required):
   ```bash
   iobox --provider outlook auth-status
   # Will prompt you to open a URL and enter a code
   ```

6. Verify with a search:
   ```bash
   iobox --provider outlook search -q "from:megan@youralias.onmicrosoft.com" -m 5
   ```
   The sandbox tenant has pre-seeded emails from dummy users like Megan, Adele, etc.

### Sandbox tenant renewal

The sandbox auto-renews every 90 days if you have active developer usage. If it
expires, re-create it and re-run the app registration steps.

---

## Option B — VCR-style recorded HTTP cassettes

Capture real Graph HTTP traffic once; replay in CI without a live tenant.

### Setup

```bash
uv add --dev pytest-recording vcrpy
```

### Usage pattern

```python
# tests/live/test_outlook_vcr.py
import pytest

@pytest.mark.vcr()
def test_search_emails_from_filter():
    provider = OutlookProvider()
    provider.authenticate()
    results = provider.search_emails(EmailQuery(from_addr="megan@contoso.com"))
    assert len(results) > 0
    assert all("@" in r["from_"] for r in results)
```

Run once with a live tenant to record:
```bash
uv run pytest tests/live/test_outlook_vcr.py --record-mode=once
```

Subsequent runs replay from cassettes in `tests/cassettes/` — no tenant needed.

### Caveats

- Cassettes contain real auth tokens — add `tests/cassettes/` to `.gitignore` or
  scrub tokens from the YAML before committing
- Write operations (send, delete) need `record-mode=none` stubs or careful cassette
  management to avoid replaying destructive ops
- Best suited for read path verification; delta sync is tricky to cassette reliably

---

## Option C — Graph Explorer (manual validation only)

https://developer.microsoft.com/en-us/graph/graph-explorer

Good for manually testing OData filter expressions before writing code. Runs as a
Microsoft demo user — no tenant needed. Cannot be automated.

Useful for validating:
- `$filter=categories/any(c:c eq 'Work')` syntax
- `$search="from:alice"` KQL syntax
- Delta endpoint URL structure
- Response shapes for attachments, categories, flags

---

## Live test suite plan

When you have a dev tenant, create `tests/live/test_outlook_live.py` mirroring
the Gmail `run_tests.py` scenario structure. Suggested scenarios:

| # | Scenario | Command |
|---|----------|---------|
| 1 | Auth status | `iobox --provider outlook auth-status` |
| 2 | Search by sender | `iobox --provider outlook search -q "from:megan@..."` |
| 3 | Search unread | `iobox --provider outlook search --is-unread` |
| 4 | Search with label | `iobox --provider outlook search --label Work` |
| 5 | Save single email | `iobox --provider outlook save --message-id <id>` |
| 6 | Save by query | `iobox --provider outlook save -q "subject:Test" -o /tmp/out` |
| 7 | Send email | `iobox --provider outlook send --to ... --subject ... --body ...` |
| 8 | Forward email | `iobox --provider outlook forward --message-id <id> --to ...` |
| 9 | Create draft | `iobox --provider outlook draft-create --to ... -s ... -b ...` |
| 10 | List drafts | `iobox --provider outlook draft-list` |
| 11 | Send draft | `iobox --provider outlook draft-send --draft-id <id>` |
| 12 | Delete draft | `iobox --provider outlook draft-delete --draft-id <id>` |
| 13 | Mark read | `iobox --provider outlook label --message-id <id> --mark-read` |
| 14 | Star/flag | `iobox --provider outlook label --message-id <id> --star` |
| 15 | Archive | `iobox --provider outlook label --message-id <id> --archive` |
| 16 | Trash | `iobox --provider outlook trash --message-id <id>` |
| 17 | Untrash | `iobox --provider outlook trash --message-id <id> --untrash` |
| 18 | Add tag/category | `iobox --provider outlook label --message-id <id> --add Work` |
| 19 | Remove tag | `iobox --provider outlook label --message-id <id> --remove Work` |
| 20 | Sync state | programmatic — `provider.get_sync_state()` |
| 21 | Delta sync | programmatic — `provider.get_new_messages(token)` |

Key scenarios to prioritize (most likely to catch real bugs vs mocks):
- **#4** (label filter) — will immediately reveal the `categories/any` OData bug
- **#20–21** (delta sync) — live token lifecycle, 410-Gone in production
- **#5–6** (save) — validates the full `EmailData → markdown_converter` pipeline
  end-to-end including the `from_` / `from` key mismatch

---

## Known issues to verify with a live account

1. **Label filter silently dropped** — `_build_outlook_filter` line 205 does not
   reassign `q` after adding the label condition. Scenario #4 will fail.

2. **`from_` key not passed to markdown_converter** — `EmailData` uses `from_`
   but `convert_email_to_markdown` expects `from`. Scenario #5–6 will expose this.

3. **Inbox-only search** — `search_emails` and `get_thread` only query inbox.
   Emails in Sent, Drafts, Archive won't appear in results.
