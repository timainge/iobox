"""
Mock Google Drive API responses for unit tests.
"""

from __future__ import annotations

MOCK_GDOC_FILE: dict = {
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

MOCK_PDF_FILE: dict = {
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

MOCK_TEXT_FILE: dict = {
    "id": "txt_003",
    "name": "notes.txt",
    "mimeType": "text/plain",
    "size": "1024",
    "parents": ["folder_abc"],
    "webViewLink": "https://drive.google.com/file/d/txt_003/view",
    "createdTime": "2026-02-10T08:00:00.000Z",
    "modifiedTime": "2026-02-10T08:30:00.000Z",
    "trashed": False,
}

MOCK_FOLDER: dict = {
    "id": "folder_abc",
    "name": "Work Documents",
    "mimeType": "application/vnd.google-apps.folder",
    "size": None,
    "parents": ["root"],
    "webViewLink": "https://drive.google.com/drive/folders/folder_abc",
    "createdTime": "2025-12-01T10:00:00.000Z",
    "modifiedTime": "2026-03-10T15:00:00.000Z",
    "trashed": False,
}

MOCK_TRASHED_FILE: dict = {
    "id": "trash_004",
    "name": "old_file.pdf",
    "mimeType": "application/pdf",
    "size": "512",
    "parents": ["folder_abc"],
    "webViewLink": "https://drive.google.com/file/d/trash_004/view",
    "createdTime": "2025-01-01T00:00:00.000Z",
    "modifiedTime": "2025-01-01T00:00:00.000Z",
    "trashed": True,
}

MOCK_LIST_RESPONSE: dict = {
    "files": [MOCK_GDOC_FILE, MOCK_PDF_FILE],
}

MOCK_LIST_RESPONSE_WITH_TRASHED: dict = {
    "files": [MOCK_GDOC_FILE, MOCK_PDF_FILE, MOCK_TRASHED_FILE],
}

MOCK_LIST_RESPONSE_PAGINATED_PAGE1: dict = {
    "files": [MOCK_GDOC_FILE],
    "nextPageToken": "page_token_2",
}

MOCK_LIST_RESPONSE_PAGINATED_PAGE2: dict = {
    "files": [MOCK_PDF_FILE],
}

MOCK_ABOUT_RESPONSE: dict = {
    "user": {
        "emailAddress": "tim@gmail.com",
        "displayName": "Tim",
    }
}
