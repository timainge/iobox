# Quick Start

Get up and running with iobox in 5 minutes.

## Prerequisites

- iobox installed (`pip install iobox`)
- `credentials.json` in your working directory (see [Installation](installation.md))

## Step 1: Authenticate

Check your authentication status and trigger the OAuth flow if needed:

```bash
iobox auth-status
```

On first run, this will open a browser window for you to grant Gmail access. After
authorizing, a `token.json` file is saved for future runs.

Expected output:

```
Authentication Status
-------------------
Authenticated: True
Credentials file exists: True
Token file exists: True

Gmail Profile
-------------------
Email: you@example.com
Messages: 12,345
Threads: 9,876
```

## Step 2: Search for Emails

Use Gmail search syntax to find emails:

```bash
iobox search -q "from:newsletter@example.com" -d 7
```

This searches the last 7 days for emails from that sender.

Expected output:

```
Searching for emails matching: from:newsletter@example.com
Found 3 emails:
1. Weekly Digest - March 2026
   ID: 18e4a2b3c1d5f6a7
   Preview: Here's what happened this week in tech...
   From: newsletter@example.com
   Date: 01/03/2026 09:00
   ----------------------------------------
```

## Step 3: Save Emails as Markdown

Save matching emails to a local directory:

```bash
iobox save -q "from:newsletter@example.com" -d 7 -o ./emails
```

Expected output:

```
Searching for emails matching: from:newsletter@example.com
Found 3 emails to process.
Fetching 3 email(s) in batch...
Processing email 1/3: Weekly Digest - March 2026
Processing email 2/3: Weekly Digest - February 2026
Processing email 3/3: Weekly Digest - January 2026

Completed processing 3 emails:
  - 3 emails saved to markdown
  - 0 emails skipped (already processed)
```

## Step 4: View the Markdown Files

Each email is saved as a `.md` file with YAML frontmatter:

```bash
ls ./emails/
# 2026-03-01-weekly-digest-march-2026.md
# 2026-02-01-weekly-digest-february-2026.md
# ...
```

```bash
cat ./emails/2026-03-01-weekly-digest-march-2026.md
```

```markdown
---
date: Mon, 01 Mar 2026 09:00:00 +0000
from: newsletter@example.com
labels:
  - INBOX
  - UNREAD
message_id: 18e4a2b3c1d5f6a7
saved_date: 2026-03-02T10:30:00
subject: Weekly Digest - March 2026
thread_id: 18e4a2b3c1d5f6a7
to: you@example.com
---

Here's what happened this week in tech...
```

## Next Steps

- Use `--sync` flag to only fetch new emails since your last run
- Download attachments with `--download-attachments`
- Explore [CLI Reference](../cli/search.md) for all available options
- Set up the [MCP server](../mcp.md) for AI assistant integration
