# files

Cloud file operations across all providers in the active workspace (Google Drive and OneDrive).

## Subcommands

| Command | Description |
|---|---|
| [`list`](#list) | Search for files |
| [`get`](#get) | Print file metadata as Markdown |
| [`save`](#save) | Save file metadata to a Markdown file |
| [`upload`](#upload) | Upload a local file to cloud storage |
| [`delete`](#delete) | Delete a file |
| [`mkdir`](#mkdir) | Create a new folder |

---

## list

Search for files in the active workspace. A `--query` is required to avoid unbounded listings.

```
iobox files list [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--query` | `-q` | TEXT | *(required)* | Search text |
| `--max` | `-m` | INT | `20` | Maximum results |
| `--provider` | | TEXT | None | Target a specific provider slot by name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox files list -q "Q4 report"
iobox files list -q "budget" --provider my-drive --max 50
```

---

## get

Print file metadata as Markdown.

```
iobox files get FILE_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox files get 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
```

---

## save

Save file metadata as a Markdown file.

```
iobox files save FILE_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--output` | `-o` | PATH | `.` | Output directory |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox files save 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms -o ./files
```

---

## upload

Upload a local file to cloud storage. Requires `--mode standard`.

```
iobox files upload LOCAL_PATH [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--parent-id` | | TEXT | None | Parent folder ID (uploads to root if omitted) |
| `--name` | `-n` | TEXT | None | Override the filename |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox files upload ./report.pdf
iobox files upload ./report.pdf --parent-id FOLDER_ID --name "Q1 Report.pdf"
```

---

## delete

Delete a file. Moves to trash by default. Requires `--mode standard`.

```
iobox files delete FILE_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--permanent` | | FLAG | `False` | Permanently delete (skip trash) |
| `--yes` | `-y` | FLAG | `False` | Skip confirmation prompt |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

!!! warning
    OneDrive does not support trash — deletion is always permanent regardless of `--permanent`.

```bash
iobox files delete FILE_ID --yes
iobox files delete FILE_ID --permanent --yes
```

---

## mkdir

Create a new folder in cloud storage. Requires `--mode standard`.

```
iobox files mkdir NAME [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--parent-id` | | TEXT | None | Parent folder ID (creates at root if omitted) |
| `--provider` | | TEXT | None | Provider slot name |
| `--workspace` | `-w` | TEXT | None | Named workspace |

```bash
iobox files mkdir "2026 Reports"
iobox files mkdir "Q1" --parent-id PARENT_FOLDER_ID
```
