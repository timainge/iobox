---
id: task-019
title: "FileProvider write methods"
milestone: 5
status: done
priority: p3
depends_on: [task-006, task-013]
blocks: []
parallel_with: [task-018]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

After read-only file access is proven (tasks 006, 013), this task adds upload, update, and delete capabilities to both `GoogleDriveProvider` and `OneDriveProvider`. File writes are less common in e-discovery use cases but essential for round-trip workflows (e.g., upload a summary document back to Drive).

Write operations are gated behind `--mode standard`.

## Scope

**Does:**
- Add write methods to `FileProvider` ABC: `upload_file`, `update_file`, `delete_file`, `create_folder`
- Implement in `GoogleDriveProvider`
- Implement in `OneDriveProvider`
- Mode gate: writes require `mode="standard"`
- Add CLI commands: `iobox files upload`, `iobox files delete`

**Does NOT:**
- Implement multi-part chunked uploads for very large files (MVP: single-shot)
- Implement file sharing permission management
- Implement move/copy operations

## Architecture Notes

- `upload_file(local_path, parent_id, name)` — upload from local filesystem
- `update_file(file_id, local_path)` — replace file content
- `delete_file(file_id)` — moves to trash (Google) or deletes (OneDrive); consistent behavior: trash first
- `create_folder(name, parent_id)` — creates a new folder
- Google: `drive.files().create()` with `MediaFileUpload` for content
- Google delete: `drive.files().update(fileId=id, body={"trashed": True})` — moves to trash rather than permanent delete
- OneDrive: `folder.upload_file(path)` or `drive.get_root_folder().upload_file(path)`
- OneDrive delete: `item.delete()` — permanent; document this

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/providers/base.py` | Add write abstract methods to FileProvider |
| Modify | `src/iobox/providers/google_drive.py` | Implement write methods |
| Modify | `src/iobox/providers/onedrive.py` | Implement write methods |
| Modify | `src/iobox/cli.py` | Add files write commands |
| Create | `tests/unit/test_file_write_ops.py` | Unit tests |

## FileProvider ABC additions

```python
# providers/base.py additions to FileProvider
@abstractmethod
def upload_file(
    self,
    local_path: str,
    *,
    parent_id: str | None = None,
    name: str | None = None,  # override filename; default: basename of local_path
) -> File:
    """Upload a local file. Returns the created File."""
    ...

@abstractmethod
def update_file(self, file_id: str, local_path: str) -> File:
    """Replace content of an existing file. Returns the updated File."""
    ...

@abstractmethod
def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
    """
    Move file to trash (default) or permanently delete (permanent=True).
    OneDrive does not support trash — always permanent.
    """
    ...

@abstractmethod
def create_folder(
    self,
    name: str,
    *,
    parent_id: str | None = None,
) -> File:
    """Create a new folder. Returns File with is_folder=True."""
    ...
```

## GoogleDriveProvider write implementations

```python
def upload_file(self, local_path: str, *, parent_id=None, name=None) -> File:
    self._check_write_mode()
    from googleapiclient.http import MediaFileUpload
    import mimetypes
    from pathlib import Path

    path = Path(local_path)
    filename = name or path.name
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"

    body = {"name": filename}
    if parent_id:
        body["parents"] = [parent_id]

    media = MediaFileUpload(str(path), mimetype=mime, resumable=False)
    result = self._get_service().files().create(
        body=body, media_body=media, fields=FILE_FIELDS
    ).execute()
    return self._drive_file_to_file(result)

def update_file(self, file_id: str, local_path: str) -> File:
    self._check_write_mode()
    from googleapiclient.http import MediaFileUpload
    import mimetypes

    mime, _ = mimetypes.guess_type(local_path)
    mime = mime or "application/octet-stream"
    media = MediaFileUpload(local_path, mimetype=mime, resumable=False)
    result = self._get_service().files().update(
        fileId=file_id, media_body=media, fields=FILE_FIELDS
    ).execute()
    return self._drive_file_to_file(result)

def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
    self._check_write_mode()
    svc = self._get_service()
    if permanent:
        svc.files().delete(fileId=file_id).execute()
    else:
        svc.files().update(fileId=file_id, body={"trashed": True}).execute()

def create_folder(self, name: str, *, parent_id=None) -> File:
    self._check_write_mode()
    body = {"name": name, "mimeType": FOLDER_MIME_TYPE}
    if parent_id:
        body["parents"] = [parent_id]
    result = self._get_service().files().create(body=body, fields=FILE_FIELDS).execute()
    return self._drive_file_to_file(result)

def _check_write_mode(self) -> None:
    if self.mode == "readonly":
        raise PermissionError("File write operations require mode='standard'.")
```

## OneDriveProvider write implementations

```python
def upload_file(self, local_path: str, *, parent_id=None, name=None) -> File:
    self._check_write_mode()
    from pathlib import Path
    path = Path(local_path)
    filename = name or path.name
    drive = self._get_drive()
    if parent_id:
        folder = drive.get_item(parent_id)
    else:
        folder = drive.get_root_folder()
    item = folder.upload_file(item=str(path), item_name=filename)
    return self._o365_item_to_file(item)

def update_file(self, file_id: str, local_path: str) -> File:
    self._check_write_mode()
    drive = self._get_drive()
    item = drive.get_item(file_id)
    # O365 library: update content by re-uploading
    parent = item.parent
    new_item = parent.upload_file(item=local_path, item_name=item.name)
    return self._o365_item_to_file(new_item)

def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
    self._check_write_mode()
    drive = self._get_drive()
    item = drive.get_item(file_id)
    if item:
        item.delete()  # OneDrive always permanent

def create_folder(self, name: str, *, parent_id=None) -> File:
    self._check_write_mode()
    drive = self._get_drive()
    if parent_id:
        parent = drive.get_item(parent_id)
    else:
        parent = drive.get_root_folder()
    folder = parent.mkdir(name)
    return self._o365_item_to_file(folder)
```

## CLI additions

```bash
# Upload file
iobox files upload ./report.pdf [--parent-id FOLDER_ID] [--name "Q4 Report.pdf"]
iobox files upload ./notes.md

# Delete file (to trash by default)
iobox files delete FILE_ID
iobox files delete FILE_ID --permanent   # prompts confirm for permanent

# Create folder
iobox files mkdir "Q4 Reports" [--parent-id FOLDER_ID]
```

## Key Decisions

**Q: Should delete move to trash or permanently delete by default?**
Trash by default for Google (reversible). OneDrive doesn't have a trash API via O365 library, so it's always permanent — document this prominently.

**Q: Should `update_file` match by file_id or by name?**
Always by `file_id` — unambiguous.

**Q: Should upload require `--mode standard` even for the CLI?**
Yes — same as email write ops. The `--mode standard` flag is already in the CLI callback.

## Test Strategy

```python
# tests/unit/test_file_write_ops.py
class TestGoogleDriveUploadFile:
    def test_upload_basic(self, mock_service, tmp_path): ...
    def test_upload_to_folder(self, mock_service, tmp_path): ...
    def test_blocked_in_readonly_mode(self, tmp_path): ...

class TestGoogleDriveDeleteFile:
    def test_move_to_trash_default(self, mock_service): ...
    def test_permanent_delete(self, mock_service): ...

class TestGoogleDriveCreateFolder:
    def test_create_folder_at_root(self, mock_service): ...
    def test_create_folder_with_parent(self, mock_service): ...
```

## Verification

```bash
make test
# With real credentials and --mode standard:
iobox files upload ./test.txt
iobox files delete FILE_ID
```

## Acceptance Criteria

- [ ] `FileProvider` ABC has `upload_file`, `update_file`, `delete_file`, `create_folder`
- [ ] `GoogleDriveProvider` implements all four methods
- [ ] `OneDriveProvider` implements all four methods
- [ ] All write methods raise `PermissionError` in readonly mode
- [ ] Google delete moves to trash by default; permanent delete with `permanent=True`
- [ ] OneDrive permanent-delete behavior documented
- [ ] Drive scopes updated for standard mode (task-003's `get_google_scopes` should already handle this)
- [ ] CLI commands `files upload`, `files delete`, `files mkdir` added
- [ ] Unit tests pass
