---
id: task-013
title: "OneDriveProvider (read-only)"
milestone: 2
status: done
priority: p1
depends_on: [task-002]
blocks: [task-014]
parallel_with: [task-005, task-006, task-012]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Milestone 2 O365 parity: `OneDriveProvider` reads files from Microsoft OneDrive/SharePoint via the O365 Python library (`python-o365`), implementing the same `FileProvider` ABC as `GoogleDriveProvider`.

## Scope

**Does:**
- `src/iobox/providers/onedrive.py` — `OneDriveProvider(FileProvider)`
- `list_files(FileQuery)` — text search, folder listing
- `get_file(id)` — file metadata
- `get_file_content(id)` — text download; Word/Office docs may need conversion
- `download_file(id)` — raw bytes
- `_o365_item_to_file()` normalizer
- Register as `"onedrive"` in `providers/__init__.py`
- Unit tests with mocked O365 objects

**Does NOT:**
- Implement write operations (task-019)
- Implement `MicrosoftAuth` shared object (task-014)
- SharePoint site search (just personal OneDrive)

## Architecture Notes

- Use `O365.Account.storage()` to get the `Storage` object
- `storage.get_default_drive()` returns the user's personal OneDrive
- Text search: `drive.search(query, limit=N)` — O365 library wraps `/me/drive/search(q=...)`
- Folder listing: `drive.get_root_folder().get_items()` or `drive.get_item(folder_id).get_items()`
- O365 DriveItem properties: `name`, `object_id`, `mime_type` (via `file.mime_type`), `size`, `web_url`, `created_datetime`, `modified_datetime`, `is_folder`
- Import guard pattern: same as OutlookProvider
- Word/Office docs: O365 library may not support export-to-text natively; for MVP return empty string with warning

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/providers/onedrive.py` | `OneDriveProvider` |
| Modify | `src/iobox/providers/__init__.py` | Register `"onedrive"` |
| Create | `tests/unit/test_onedrive_provider.py` | Unit tests |
| Modify | `tests/unit/test_provider_contract.py` | Add contract tests |

## O365 Storage API

```python
from O365 import Account
account = Account(...)
storage = account.storage()
drive = storage.get_default_drive()

# Search
items = list(drive.search("Q4 report", limit=20))

# Root folder listing
root = drive.get_root_folder()
items = list(root.get_items())

# Get item by ID
item = drive.get_item(object_id)

# DriveItem properties
item.name                    # filename
item.object_id               # ID
item.web_url                 # browser URL
item.size                    # bytes (None for folders)
item.is_folder               # bool
item.created_datetime        # datetime
item.modified_datetime       # datetime
item.mime_type               # for files (None for folders)
item.parent                  # parent folder

# Download
item.download(to_path, chunk_size=...)  # writes to file
# Or use requests-based approach via item's download_url
```

## Implementation Guide

### Step 1 — Scaffold with import guard

```python
# src/iobox/providers/onedrive.py
from __future__ import annotations
import logging
from iobox.providers.base import FileProvider, File, FileQuery

try:
    from O365 import Account
    HAS_O365 = True
except ImportError:
    HAS_O365 = False

logger = logging.getLogger(__name__)

class OneDriveProvider(FileProvider):

    PROVIDER_ID = "onedrive"

    def __init__(
        self,
        account_email: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
    ):
        if not HAS_O365:
            raise ImportError("O365 package required. Install with: pip install 'iobox[outlook]'")
        self.account_email = account_email
        self.credentials_dir = credentials_dir
        self._account = None

    def _get_account(self):
        if self._account is None:
            from iobox.providers.outlook_auth import OutlookAuth
            auth = OutlookAuth(account=self.account_email, credentials_dir=self.credentials_dir)
            self._account = auth.get_account()
        return self._account

    def _get_drive(self):
        return self._get_account().storage().get_default_drive()

    def authenticate(self) -> None:
        self._get_account()

    def get_profile(self) -> dict:
        drive = self._get_drive()
        return {
            "name": drive.name,
            "drive_type": getattr(drive, "drive_type", "personal"),
        }
```

### Step 2 — Implement list_files

```python
    def list_files(self, query: FileQuery) -> list[File]:
        drive = self._get_drive()

        if query.text:
            raw_items = list(drive.search(query.text, limit=query.max_results))
        elif query.folder_id:
            folder = drive.get_item(query.folder_id)
            raw_items = list(folder.get_items())[:query.max_results]
        else:
            root = drive.get_root_folder()
            raw_items = list(root.get_items())[:query.max_results]

        files = []
        for item in raw_items:
            if query.mime_type and getattr(item, "mime_type", None) != query.mime_type:
                continue
            files.append(self._o365_item_to_file(item))

        return files[:query.max_results]
```

### Step 3 — Normalizer

```python
    def _o365_item_to_file(self, item) -> File:
        is_folder = getattr(item, "is_folder", False)
        created = getattr(item, "created_datetime", None)
        modified = getattr(item, "modified_datetime", None)
        parent = getattr(item, "parent", None)
        parent_id = str(getattr(parent, "object_id", "") or "") if parent else None

        return File(
            id=str(getattr(item, "object_id", "") or ""),
            provider_id=self.PROVIDER_ID,
            resource_type="file",
            title=getattr(item, "name", ""),
            created_at=created.isoformat() if created else "",
            modified_at=modified.isoformat() if modified else "",
            url=getattr(item, "web_url", None),
            name=getattr(item, "name", ""),
            mime_type=getattr(item, "mime_type", "") or ("inode/directory" if is_folder else ""),
            size=getattr(item, "size", 0) or 0,
            path=None,
            parent_id=parent_id,
            is_folder=is_folder,
            download_url=getattr(item, "web_url", None),
            content=None,
        )
```

### Step 4 — get_file, get_file_content, download_file

```python
    def get_file(self, file_id: str) -> File:
        drive = self._get_drive()
        item = drive.get_item(file_id)
        if item is None:
            raise KeyError(f"File '{file_id}' not found")
        return self._o365_item_to_file(item)

    def get_file_content(self, file_id: str) -> str:
        drive = self._get_drive()
        item = drive.get_item(file_id)
        if item is None:
            return ""
        mime = getattr(item, "mime_type", "") or ""
        if "officedocument" in mime or "msword" in mime:
            logger.warning(f"Text extraction for Office docs not supported in MVP: {file_id}")
            return ""
        try:
            import io
            buffer = io.BytesIO()
            item.download(output=buffer)
            return buffer.getvalue().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Could not download file content {file_id}: {e}")
            return ""

    def download_file(self, file_id: str) -> bytes:
        drive = self._get_drive()
        item = drive.get_item(file_id)
        import io
        buffer = io.BytesIO()
        item.download(output=buffer)
        return buffer.getvalue()
```

### Step 5 — Register in providers/__init__.py

### Step 6 — Unit tests

Mock O365 `DriveItem` objects similar to how `OutlookProvider` tests mock O365 `Message` objects.

```python
# tests/unit/test_onedrive_provider.py
class MockDriveItem:
    name = "Q4 Report.docx"
    object_id = "item_001"
    web_url = "https://onedrive.live.com/..."
    size = 40960
    is_folder = False
    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    created_datetime = None
    modified_datetime = None
    parent = None

class TestOneDriveProviderListFiles:
    def test_text_search_calls_drive_search(self, mock_drive): ...
    def test_folder_listing(self, mock_drive): ...
    def test_mime_type_filter(self, mock_drive): ...

class TestFileNormalization:
    def test_file_item_mapped(self): ...
    def test_folder_is_folder_true(self): ...

class TestGetFileContent:
    def test_office_doc_returns_empty_string(self, mock_drive): ...
    def test_text_file_decoded(self, mock_drive): ...
```

## Key Decisions

**Q: How to handle file download for content extraction?**
Use `item.download(output=io.BytesIO())` pattern. Office formats return empty string with warning for MVP. Plain text files are decoded as UTF-8.

**Q: Should shared files be included?**
Default to personal drive only (`get_default_drive()`). The `FileQuery.shared_with_me` flag is not implemented for MVP — log a warning if specified.

**Q: What `mime_type` do OneDrive folders return?**
O365 library sets `is_folder=True` and `mime_type=None` for folders. Use `"inode/directory"` as a consistent placeholder.

## Verification

```bash
make test
python -c "from iobox.providers.onedrive import OneDriveProvider"
```

## Acceptance Criteria

- [ ] `OneDriveProvider` in `src/iobox/providers/onedrive.py`
- [ ] Import guard with clear error message
- [ ] `list_files()` with text search and folder listing
- [ ] `get_file()` returns `File` TypedDict
- [ ] `get_file_content()` downloads text files; returns `""` for Office docs with warning
- [ ] `download_file()` returns raw bytes
- [ ] `_o365_item_to_file()` normalizer maps all fields
- [ ] Registered as `"onedrive"` in `providers/__init__.py`
- [ ] Unit tests pass
- [ ] Contract tests added
