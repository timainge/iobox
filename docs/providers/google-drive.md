# Google Drive Provider

The `GoogleDriveProvider` connects iobox to your Google Drive via the Drive API v3. It shares OAuth tokens with Gmail for the same account — no separate login required if you have a Gmail session with the `--drive` scope.

## Prerequisites

- A Google Cloud project with the **Google Drive API** enabled
- OAuth credentials (`credentials.json`) in your project root or `CREDENTIALS_DIR`
- The `drive` scope included when adding your Gmail service session

## Setup

```bash
# Add Gmail with drive access (readonly)
iobox space add gmail you@gmail.com --messages --drive --read

# Or with write access (upload, delete, create folders)
iobox space add gmail you@gmail.com --messages --drive
```

## Scopes

| Mode | Scope |
|---|---|
| `readonly` | `https://www.googleapis.com/auth/drive.readonly` |
| `standard` | `https://www.googleapis.com/auth/drive` |

## CLI Commands

### List files

```bash
iobox files list
iobox files list --query "Q4 report"
iobox files list --query "budget" --max 20
```

| Option | Description |
|---|---|
| `--query TEXT` | Full-text search across Drive |
| `--max N` | Maximum results (default: 20) |
| `--provider NAME` | Target a specific workspace slot |

### Get file metadata

```bash
iobox files get FILE_ID
```

### Save file info as Markdown

```bash
iobox files save FILE_ID -o ./files
```

Produces a Markdown file with YAML frontmatter including file metadata and (if text-based) a content preview.

### Upload file (requires standard mode)

```bash
iobox files upload ./report.pdf
iobox files upload ./notes.md --name "Q4 Notes.md"
iobox files upload ./data.csv --parent-id FOLDER_ID
```

| Option | Description |
|---|---|
| `--name TEXT` | Override the filename in Drive |
| `--parent-id ID` | Upload into a specific folder |

### Delete file (requires standard mode)

By default, files are moved to **trash** (reversible). Use `--permanent` to delete immediately.

```bash
iobox files delete FILE_ID               # move to trash (prompts)
iobox files delete FILE_ID --yes         # move to trash (no prompt)
iobox files delete FILE_ID --permanent   # permanent delete (prompts)
```

### Create folder (requires standard mode)

```bash
iobox files mkdir "Q4 Reports"
iobox files mkdir "Sub Folder" --parent-id FOLDER_ID
```

## File Markdown Format

```markdown
---
id: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs
provider_id: google_drive
resource_type: file
title: Q4 Planning Notes
name: q4_planning_notes.txt
mime_type: text/plain
size: 5120
url: https://drive.google.com/file/d/1Bxi.../view
saved_date: 2026-03-24T21:30:00
---

Key decisions from the Q4 planning session: budget increased by 10%.
[Content preview — first 10,000 characters]
```

## Supported File Types

| Type | Handling |
|---|---|
| `text/*` | Downloaded and included as content |
| Google Docs | Exported as `text/plain` |
| Google Sheets | Exported as `text/csv` |
| Google Slides | Exported as `text/plain` |
| Binary files | Metadata only (no content preview) |

## API Notes

- Files are listed from the user's personal Drive (`corpora='user'`)
- Trashed files are excluded from `list_files()` results automatically
- Google Workspace files (Docs, Sheets, Slides) must be **exported** rather than downloaded directly
- `delete_file()` moves to trash by default; pass `permanent=True` to skip trash
- `create_folder()` uses `mimeType = 'application/vnd.google-apps.folder'`
