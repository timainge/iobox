---
id: task-006
title: "GoogleDriveProvider (read-only)"
milestone: 0
status: done
priority: p0
depends_on: [task-002, task-003]
blocks: [task-007]
parallel_with: [task-005, task-008, task-009, task-012, task-013]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

The e-discovery PoC requires searching and retrieving files from Google Drive. `GoogleDriveProvider` is the first `FileProvider` implementation — it wraps the Drive API v3, shares auth with `GmailProvider` via `GoogleAuth`, and maps Drive file objects to the `File` TypedDict from task-002.

## Scope

**Does:**
- `src/iobox/providers/google_drive.py` — `GoogleDriveProvider(FileProvider)`
- `list_files(FileQuery)` — pagination-aware, with full-text search, mime type filter, folder filter
- `get_file(id)` — file metadata
- `get_file_content(id)` — text content (export for Google Docs types, download for others)
- `download_file(id)` — raw bytes
- `_drive_file_to_file()` normalizer
- `_build_drive_query(FileQuery)` — builds Drive API `q=` expression
- Register as `"google_drive"` in `providers/__init__.py`
- Unit tests with mocked Drive API responses

**Does NOT:**
- Implement write operations (upload, update, delete — task-019)
- Implement shared drive support (just personal `corpora='user'`)
- Index or cache file content locally
- Return binary content via `get_file_content()` — returns empty string with warning

## Strategic Fit

Third provider for the PoC demo alongside Gmail and GCal. With task-007's Workspace, these three providers enable the cross-type search that's the demo's core value.

## Architecture Notes

- `GoogleDriveProvider` accepts either a `GoogleAuth` instance or `(account, credentials_dir, mode)` to construct one — same pattern as `GoogleCalendarProvider`
- Required scope: `https://www.googleapis.com/auth/drive.readonly`
- Folders have `mimeType = 'application/vnd.google-apps.folder'`
- Google Workspace files (Docs/Sheets/Slides) must be **exported**, not downloaded directly
- `fields` parameter in API calls should be explicit to avoid fetching unused data
- `title` in `Resource` = Drive file's `name`
- `created_at` = `createdTime`, `modified_at` = `modifiedTime`
- `url` = `webViewLink`
- `path` is not directly available from the files API — set to `None` unless folder traversal is implemented (not required for MVP)

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/providers/google_drive.py` | `GoogleDriveProvider` implementation |
| Modify | `src/iobox/providers/__init__.py` | Register `"google_drive"` provider |
| Create | `tests/unit/test_google_drive_provider.py` | Unit tests |
| Modify | `tests/unit/test_provider_contract.py` | Add GoogleDriveProvider contract tests |
| Create | `tests/fixtures/mock_drive_responses.py` | Mock Drive API responses |

## Google Drive API Notes

### files().list() key parameters

```python
drive.files().list(
    q="fullText contains 'Q4 report'",         # search query
    fields="files(id,name,mimeType,size,parents,webViewLink,createdTime,modifiedTime,trashed)",
    pageSize=100,                               # max 1000
    corpora="user",                             # personal drive
    orderBy="modifiedTime desc",
    pageToken=page_token,                       # for pagination
)
```

### Drive query syntax

```python
# Text search
"fullText contains 'quarterly report'"

# Mime type
"mimeType = 'application/pdf'"

# In a folder
"'folder_id' in parents"

# Shared with me
"sharedWithMe = true"

# Exclude trashed
"trashed = false"

# Combine
"fullText contains 'Q4' and mimeType = 'application/pdf' and trashed = false"
```

### Google Workspace MIME types (require export)

```python
GOOGLE_WORKSPACE_EXPORT_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
```

### files().list() response structure

```python
{
    "files": [
        {
            "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
            "name": "Q4 Report.gdoc",
            "mimeType": "application/vnd.google-apps.document",
            "size": None,  # Google Docs don't have a size
            "parents": ["0AKsJ6-_YlBTTUk9PVA"],
            "webViewLink": "https://docs.google.com/...",
            "createdTime": "2026-01-15T10:00:00.000Z",
            "modifiedTime": "2026-03-10T14:30:00.000Z",
            "trashed": false
        },
        {
            "id": "abc123",
            "name": "budget.pdf",
            "mimeType": "application/pdf",
            "size": "204800",
            "parents": ["0AKsJ6-_YlBTTUk9PVA"],
            "webViewLink": "https://drive.google.com/file/d/abc123/view",
            "createdTime": "2026-02-01T09:00:00.000Z",
            "modifiedTime": "2026-02-15T11:00:00.000Z",
            "trashed": false
        }
    ],
    "nextPageToken": "tokenXYZ"
}
```

## Implementation Guide

### Step 1 — Scaffold the provider

Follow the multitool DI pattern: every method that calls the Drive API accepts `_service_fn=None`. Tests inject a mock service directly — no patching of `googleapiclient.discovery.build` required.

```python
# src/iobox/providers/google_drive.py
from __future__ import annotations
import logging
from typing import Any, Callable
from iobox.providers.base import FileProvider, File, FileQuery
from iobox.providers.google_auth import GoogleAuth

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_EXPORT_TYPES: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

FILE_FIELDS = "id,name,mimeType,size,parents,webViewLink,createdTime,modifiedTime,trashed"

class GoogleDriveProvider(FileProvider):

    PROVIDER_ID = "google_drive"

    def __init__(
        self,
        auth: GoogleAuth | None = None,
        account: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
    ):
        if auth is not None:
            self._auth = auth
        else:
            from iobox.modes import get_google_scopes, _tier_for_mode
            scopes = get_google_scopes(["drive"], mode)
            tier = _tier_for_mode(mode)
            self._auth = GoogleAuth(
                account=account,
                scopes=scopes,
                credentials_dir=credentials_dir,
                tier=tier,
            )
        self._service = None

    def _get_service(self):
        if self._service is None:
            self._service = self._auth.get_service("drive", "v3")
        return self._service

    def authenticate(self) -> None:
        self._auth.get_credentials()

    def get_profile(self) -> dict:
        svc = self._get_service()
        about = svc.about().get(fields="user").execute()
        user = about.get("user", {})
        return {
            "email": user.get("emailAddress"),
            "display_name": user.get("displayName"),
        }
```

### Step 2 — Implement list_files

```python
    def list_files(self, query: FileQuery, *, _service_fn: Callable | None = None) -> list[File]:
        svc = _service_fn or self._get_service()
        q = self._build_drive_query(query)
        files: list[File] = []
        page_token = None
        page_size = min(query.max_results, 100)

        while len(files) < query.max_results:
            params: dict[str, Any] = {
                "q": q,
                "fields": f"files({FILE_FIELDS}),nextPageToken",
                "pageSize": page_size,
                "corpora": "user",
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                params["pageToken"] = page_token
            resp = svc.files().list(**params).execute()
            for item in resp.get("files", []):
                if not item.get("trashed", False):
                    files.append(self._drive_file_to_file(item))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return files[:query.max_results]
```

### Step 3 — Build Drive query

```python
    def _build_drive_query(self, query: FileQuery) -> str:
        parts = ["trashed = false"]
        if query.text:
            safe = query.text.replace("'", "\\'")
            parts.append(f"fullText contains '{safe}'")
        if query.mime_type:
            parts.append(f"mimeType = '{query.mime_type}'")
        if query.folder_id:
            parts.append(f"'{query.folder_id}' in parents")
        if query.shared_with_me:
            parts.append("sharedWithMe = true")
        return " and ".join(parts)
```

### Step 4 — Normalizer

```python
    def _drive_file_to_file(self, raw: dict) -> File:
        return File(
            id=raw["id"],
            provider_id=self.PROVIDER_ID,
            resource_type="file",
            title=raw.get("name", ""),
            created_at=raw.get("createdTime", ""),
            modified_at=raw.get("modifiedTime", ""),
            url=raw.get("webViewLink"),
            name=raw.get("name", ""),
            mime_type=raw.get("mimeType", ""),
            size=int(raw.get("size") or 0),
            path=None,  # not fetching full path for MVP
            parent_id=(raw.get("parents") or [None])[0],
            is_folder=raw.get("mimeType") == FOLDER_MIME_TYPE,
            download_url=raw.get("webViewLink"),
            content=None,  # fetched on-demand via get_file_content
        )
```

### Step 5 — get_file, get_file_content, download_file

```python
    def get_file(self, file_id: str, *, _service_fn: Callable | None = None) -> File:
        svc = _service_fn or self._get_service()
        raw = svc.files().get(fileId=file_id, fields=FILE_FIELDS).execute()
        return self._drive_file_to_file(raw)

    def get_file_content(self, file_id: str, *, _service_fn: Callable | None = None) -> str:
        svc = _service_fn or self._get_service()
        file = self.get_file(file_id)
        mime = file["mime_type"]

        if mime in GOOGLE_WORKSPACE_EXPORT_TYPES:
            export_mime = GOOGLE_WORKSPACE_EXPORT_TYPES[mime]
            request = svc.files().export(fileId=file_id, mimeType=export_mime)
            content = request.execute()
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        elif mime.startswith("text/"):
            request = svc.files().get_media(fileId=file_id)
            content = request.execute()
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        else:
            logger.warning(f"Cannot extract text from binary file {file_id} ({mime})")
            return ""

    def download_file(self, file_id: str) -> bytes:
        svc = self._get_service()
        request = svc.files().get_media(fileId=file_id)
        return request.execute()
```

### Step 6 — Register in providers/__init__.py

### Step 7 — Mock fixtures

```python
# tests/fixtures/mock_drive_responses.py
MOCK_GDOC_FILE = {
    "id": "doc_001",
    "name": "Q4 Planning Notes",
    "mimeType": "application/vnd.google-apps.document",
    "size": None,
    "parents": ["folder_abc"],
    "webViewLink": "https://docs.google.com/document/d/doc_001",
    "createdTime": "2026-01-10T10:00:00.000Z",
    "modifiedTime": "2026-03-10T15:00:00.000Z",
    "trashed": False,
}
MOCK_PDF_FILE = {
    "id": "pdf_002",
    "name": "budget.pdf",
    "mimeType": "application/pdf",
    "size": "204800",
    "parents": ["folder_abc"],
    "webViewLink": "https://drive.google.com/file/d/pdf_002/view",
    "createdTime": "2026-02-01T09:00:00.000Z",
    "modifiedTime": "2026-02-15T11:00:00.000Z",
    "trashed": False,
}
MOCK_LIST_RESPONSE = {
    "files": [MOCK_GDOC_FILE, MOCK_PDF_FILE],
}
```

## Key Decisions

**Q: Should we return binary file content via get_file_content()?**
No — return empty string with a warning log. Binary files should use `download_file()` instead. This keeps `get_file_content()` safe to call on any file.

**Q: Should trashed files be returned?**
No — always add `trashed = false` to the query. Trash is not useful for e-discovery.

**Q: How to handle Google Workspace file sizes (which are None in API)?**
Use `0` as the size for Google Workspace files. Document this in the `File` TypedDict docstring.

**Q: What fields should be requested from the API?**
Use explicit `fields=` parameter always. The default (no fields) returns all fields and is slower.

## Test Strategy

```python
# tests/unit/test_google_drive_provider.py
# Inject mock_svc via _service_fn= — no patching needed.
@pytest.fixture
def mock_svc():
    svc = MagicMock()
    svc.files().list().execute.return_value = MOCK_LIST_RESPONSE
    return svc

@pytest.fixture
def provider(mock_google_auth):
    return GoogleDriveProvider(auth=mock_google_auth)

class TestGoogleDriveProviderListFiles:
    def test_list_files_basic(self, provider, mock_svc):
        files = provider.list_files(FileQuery(max_results=10), _service_fn=mock_svc)
        assert len(files) == 2

    def test_list_files_text_search(self, provider, mock_svc):
        provider.list_files(FileQuery(text="Q4"), _service_fn=mock_svc)
        q = mock_svc.files().list.call_args.kwargs["q"]
        assert "fullText contains 'Q4'" in q

    def test_list_files_skips_trashed(self, provider, mock_svc): ...
    def test_pagination(self, provider, mock_svc): ...

class TestBuildDriveQuery:
    def test_empty_query_only_trashed_false(self): ...
    def test_text_escapes_quotes(self): ...
    def test_mime_type_filter(self): ...
    def test_folder_id_filter(self): ...
    def test_shared_with_me(self): ...
    def test_combined_filters(self): ...

class TestFileNormalization:
    def test_google_doc_maps_to_file(self): ...
    def test_folder_is_folder_true(self): ...
    def test_pdf_size_parsed(self): ...

class TestGetFileContent:
    def test_google_doc_exported_as_text(self, mock_drive_service): ...
    def test_text_file_downloaded(self, mock_drive_service): ...
    def test_binary_file_returns_empty_string(self, mock_drive_service): ...
```

## Verification

```bash
make test
make type-check
python -c "from iobox.providers.google_drive import GoogleDriveProvider"
```

## Acceptance Criteria

- [ ] `GoogleDriveProvider` in `src/iobox/providers/google_drive.py`
- [ ] `list_files()` with text search, mime_type, folder_id, shared_with_me, pagination
- [ ] `_build_drive_query()` generates correct Drive `q=` expression
- [ ] `get_file()` returns `File` TypedDict
- [ ] `get_file_content()` exports Google Workspace docs, downloads text files, returns `""` for binary
- [ ] `download_file()` returns raw bytes
- [ ] Trashed files excluded from all queries
- [ ] Registered as `"google_drive"` in `providers/__init__.py`
- [ ] Mock fixtures in `tests/fixtures/mock_drive_responses.py`
- [ ] All unit tests pass
- [ ] Contract tests added
- [ ] `make type-check` passes
