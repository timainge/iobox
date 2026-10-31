# Quick Start

From zero to searching your email, calendar, and files in about five minutes. This walkthrough uses a single Google account; Microsoft 365 works the same way once [connected](connect-microsoft.md).

**Before you start:** [install iobox](installation.md) and save your Google OAuth client as `~/.iobox/credentials.json` ([how](connect-google.md#1-create-an-oauth-client)).

## 1. Create a workspace and add an account

```bash
iobox space create personal
iobox space add google you@gmail.com --email --calendar --drive --read
```

A browser window opens for Google consent. When it's done:

```bash
iobox space status
```

```
#  service  account        scopes                 mode      status
1  google   you@gmail.com  email,calendar,drive   readonly  ✓ authenticated
```

## 2. List calendar events

```bash
iobox events list --after 2026-01-01 --before 2026-02-01
```

```
Title                                    Start              End                Provider
------------------------------------------------------------------------------------------
Quarterly planning                       2026-01-12 10:00   2026-01-12 11:00   google_calendar
Dentist                                  2026-01-20 15:30   2026-01-20 16:00   google_calendar
```

Every calendar in the workspace is queried in parallel. Add `--provider you-gmail-cal` to target just one.

## 3. Search files

```bash
iobox files list --query "budget"
```

## 4. Search and save email

The email commands (`search`, `save`, …) act on one account at a time. Point them at the workspace token store so they reuse the token you just created:

```bash
export CREDENTIALS_DIR=~/.iobox
export IOBOX_ACCOUNT=you@gmail.com
export IOBOX_MODE=readonly
```

Then search with Gmail syntax:

```bash
iobox search -q "from:newsletter@example.com" -d 30
```

And save the results as Markdown:

```bash
iobox save -q "from:newsletter@example.com" -d 30 -o ./emails
ls ./emails
```

Each file has YAML frontmatter and a Markdown body:

```markdown
---
date: Mon, 05 Jan 2026 09:00:00 +0000
from: newsletter@example.com
labels:
  - INBOX
message_id: 18e4a2b3c1d5f6a7
subject: Weekly Digest
to: you@gmail.com
---

Here's what happened this week…
```

Run the same `save` with `--sync` later to fetch only new messages.

## 5. Pick your interface

You now have a working workspace. Use it from wherever suits you:

- **[Connect Claude Desktop](../mcp/index.md)** — ask *"What's on my calendar next week, and is there anything in my email I need to prepare?"*
- **[Explore the CLI](../cli/index.md)** — every command, option, and access mode.
- **[Use the Python SDK](../sdk/index.md)** — load the workspace in your own code.
