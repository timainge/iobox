# files

Cloud file operations on the file slots of a workspace.

Unlike the top-level email commands, `files` uses the active workspace (set with [`iobox space use`](space.md#use)), or the one named with `--workspace/-w`. Each session added with `--drive` contributes a file slot named `<slug>-drive`, where the slug comes from the account email (`you@gmail.com` → `you-gmail`, so the slot is `you-gmail-drive`). `iobox space add` only accepts `--drive` for Google, so file slots are Google Drive in practice; OneDrive slots exist only if added to the space's TOML by hand. See [Concepts](../get-started/concepts.md) for workspaces and slots.

**Access mode:** `files` is allowed in every global `--mode`. Write subcommands (`upload`, `delete`, `mkdir`) also need the drive session to have been added without `--read`.

!!! note "`--provider` here is a slot name"
    The `--provider` option after `files <subcommand>` selects a workspace slot (e.g. `you-gmail-drive`). It is different from the global `iobox --provider gmail|outlook` option, which goes before `files` and must still be `gmail` or `outlook`.

## Subcommands

| Command | Description |
|---|---|
| [`list`](#list) | Search for files across file slots |
| [`get`](#get) | Print file metadata as Markdown |
| [`save`](#save) | Save file metadata to a Markdown file |
| [`upload`](#upload) | Upload a local file |
| [`delete`](#delete) | Trash or delete a file |
| [`mkdir`](#mkdir) | Create a folder |

`list` queries every file slot unless `--provider` is given. The other subcommands act on one slot: the one named by `--provider`, or the workspace's first file slot.

---

## list

Search for files. `--query` is required to avoid listing everything.

```
iobox files list --query TEXT [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--query` | `-q` | TEXT | *(required)* | Search text |
| `--provider` | | TEXT | `None` | Only query this file slot (e.g. `you-gmail-drive`) |
| `--max` | `-m` | INT | `20` | Maximum results |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

An unknown `--provider` slot name returns `No files found.` rather than an error.

```bash
iobox files list -q "Q4 report"
iobox files list -q "budget" --provider you-gmail-drive --max 50
```

Output is a table with `Name`, `Modified`, `MIME`, and `Provider` columns; the provider column shows the backend (`google_drive` or `onedrive`), not the slot name.

---

## get

Print file metadata as Markdown.

```
iobox files get FILE_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--provider` | | TEXT | first file slot | File slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox files get 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
```

---

## save

Save file **metadata** (not the file's content) as a Markdown file named `{slugified-name}.md`. An existing file with the same name is overwritten.

```
iobox files save FILE_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--output` | `-o` | TEXT | `.` | Output directory (created if missing) |
| `--provider` | | TEXT | first file slot | File slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox files save 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms -o ./files
```

See [Output format](../reference/output-format.md).

---

## upload

Upload a local file.

```
iobox files upload LOCAL_PATH [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--parent-id` | | TEXT | `None` | Parent folder ID (root if omitted) |
| `--name` | `-n` | TEXT | `None` | Override the uploaded filename |
| `--provider` | | TEXT | first file slot | File slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox files upload ./report.pdf
iobox files upload ./report.pdf --parent-id FOLDER_ID --name "Q1 Report.pdf"
```

---

## delete

Move a file to trash, or delete it permanently with `--permanent`. Asks for confirmation unless `--yes` is given.

```
iobox files delete FILE_ID [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--permanent` | | FLAG | `False` | Permanently delete (skip trash) |
| `--yes` | `-y` | FLAG | `False` | Skip the confirmation prompt |
| `--provider` | | TEXT | first file slot | File slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

!!! warning
    OneDrive has no trash via this API: deletion is always permanent, with or without `--permanent`.

```bash
iobox files delete FILE_ID --yes
iobox files delete FILE_ID --permanent --yes
```

---

## mkdir

Create a folder.

```
iobox files mkdir NAME [OPTIONS]
```

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--parent-id` | | TEXT | `None` | Parent folder ID (root if omitted) |
| `--provider` | | TEXT | first file slot | File slot name |
| `--workspace` | `-w` | TEXT | `None` | Named workspace |

```bash
iobox files mkdir "2026 Reports"
iobox files mkdir "Q1" --parent-id PARENT_FOLDER_ID
```
