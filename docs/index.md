# iobox

**Gmail to Markdown Converter**

iobox extracts emails from Gmail and saves them as clean Markdown files with YAML frontmatter — ready for notes apps, static sites, or AI pipelines.

## Features

- **Search** your Gmail inbox using Gmail's full query syntax
- **Save** emails as Markdown with structured YAML metadata
- **Send and forward** emails directly from the command line
- **Label, star, archive, and trash** messages in bulk
- **MCP server** for use with Claude Desktop and other AI tools

## Quick Install

```bash
pip install iobox
```

## Quick Usage

```bash
# Authenticate with Gmail
iobox auth-status

# Search for emails
iobox search -q "from:newsletter@example.com" -d 7

# Save matching emails as Markdown
iobox save -q "from:newsletter@example.com" -o ./emails
```

## Get Started

- [Installation](getting-started/installation.md) — prerequisites and setup
- [Authentication](getting-started/authentication.md) — Google OAuth 2.0 configuration
- [Quick Start](getting-started/quickstart.md) — 5-minute tutorial
