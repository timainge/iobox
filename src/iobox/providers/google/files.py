"""
GoogleDriveProvider — read-only FileProvider backed by Google Drive API v3.

Shares OAuth tokens with GmailProvider for the same account via GoogleAuth.
Uses service injection (_service_fn=) for testability without patching build().
"""

from __future__ import annotations

import logging
from typing import Any

from iobox.providers.base import File, FileProvider, FileQuery
from iobox.providers.google.auth import GoogleAuth

logger = logging.getLogger(__name__)

# Google Workspace types that require export (not direct download)
GOOGLE_WORKSPACE_EXPORT_TYPES: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

FILE_FIELDS = "id,name,mimeType,size,parents,webViewLink,createdTime,modifiedTime,trashed"


class GoogleDriveProvider(FileProvider):
    """Read-only FileProvider for Google Drive API v3."""

    PROVIDER_ID: str = "google_drive"

    def __init__(
        self,
        auth: GoogleAuth | None = None,
        account: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
    ) -> None:
        if auth is not None:
            self._auth = auth
        else:
            from iobox.modes import _tier_for_mode, get_google_scopes

            scopes = get_google_scopes(["drive"], mode)
            tier = _tier_for_mode(mode)
            self._auth = GoogleAuth(
                account=account,
                scopes=scopes,
                credentials_dir=credentials_dir,
                tier=tier,
            )
        self._service: Any = None
        self.mode = mode

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        self._auth.get_credentials()

    def get_profile(self, *, _service_fn: Any | None = None) -> dict[str, Any]:
        """Return account info: email and display name."""
        svc = _service_fn or self._get_service()
        about = svc.about().get(fields="user").execute()
        user = about.get("user", {})
        return {
            "email": user.get("emailAddress"),
            "display_name": user.get("displayName"),
        }

    def _get_service(self) -> Any:
        if self._service is None:
            self._service = self._auth.get_service("drive", "v3")
        return self._service

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_files(self, query: FileQuery, *, _service_fn: Any | None = None) -> list[File]:
        """Return files matching query, sorted by modified time descending."""
        svc = _service_fn or self._get_service()
        q = self._build_drive_query(query)
        files: list[File] = []
        page_token: str | None = None
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

        return files[: query.max_results]

    def get_file(self, file_id: str, *, _service_fn: Any | None = None) -> File:
        """Return file metadata by ID."""
        svc = _service_fn or self._get_service()
        raw = svc.files().get(fileId=file_id, fields=FILE_FIELDS).execute()
        return self._drive_file_to_file(raw)

    def get_file_content(self, file_id: str, *, _service_fn: Any | None = None) -> str:
        """Return text content of file.

        Google Workspace files are exported as text/plain or text/csv.
        Plain text files are downloaded directly.
        Binary files return empty string with a warning log.
        """
        svc = _service_fn or self._get_service()
        file = self.get_file(file_id, _service_fn=svc)
        mime = file["mime_type"]

        if mime in GOOGLE_WORKSPACE_EXPORT_TYPES:
            export_mime = GOOGLE_WORKSPACE_EXPORT_TYPES[mime]
            content = svc.files().export(fileId=file_id, mimeType=export_mime).execute()
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        elif mime.startswith("text/"):
            content = svc.files().get_media(fileId=file_id).execute()
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        else:
            logger.warning("Cannot extract text from binary file %s (%s)", file_id, mime)
            return ""

    def download_file(self, file_id: str, *, _service_fn: Any | None = None) -> bytes:
        """Return raw bytes of file."""
        svc = _service_fn or self._get_service()
        return bytes(svc.files().get_media(fileId=file_id).execute())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_drive_query(self, query: FileQuery) -> str:
        """Build a Drive API q= expression from a FileQuery."""
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

    # ── Write ─────────────────────────────────────────────────────────────────

    def _check_write_mode(self) -> None:
        if self.mode == "readonly":
            raise PermissionError("File write operations require mode='standard'.")

    def upload_file(
        self,
        local_path: str,
        *,
        parent_id: str | None = None,
        name: str | None = None,
        _service_fn: Any | None = None,
    ) -> File:
        """Upload a local file to Google Drive. Returns the created File."""
        self._check_write_mode()
        import mimetypes
        from pathlib import Path

        from googleapiclient.http import MediaFileUpload

        path = Path(local_path)
        filename = name or path.name
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"
        body: dict[str, Any] = {"name": filename}
        if parent_id:
            body["parents"] = [parent_id]
        media = MediaFileUpload(str(path), mimetype=mime, resumable=False)
        svc = _service_fn or self._get_service()
        result = svc.files().create(body=body, media_body=media, fields=FILE_FIELDS).execute()
        return self._drive_file_to_file(result)

    def update_file(
        self,
        file_id: str,
        local_path: str,
        *,
        _service_fn: Any | None = None,
    ) -> File:
        """Replace the content of an existing Drive file. Returns the updated File."""
        self._check_write_mode()
        import mimetypes

        from googleapiclient.http import MediaFileUpload

        mime, _ = mimetypes.guess_type(local_path)
        mime = mime or "application/octet-stream"
        media = MediaFileUpload(local_path, mimetype=mime, resumable=False)
        svc = _service_fn or self._get_service()
        result = svc.files().update(
            fileId=file_id, media_body=media, fields=FILE_FIELDS
        ).execute()
        return self._drive_file_to_file(result)

    def delete_file(
        self,
        file_id: str,
        *,
        permanent: bool = False,
        _service_fn: Any | None = None,
    ) -> None:
        """Move a file to trash (default) or permanently delete it."""
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        if permanent:
            svc.files().delete(fileId=file_id).execute()
        else:
            svc.files().update(fileId=file_id, body={"trashed": True}).execute()

    def create_folder(
        self,
        name: str,
        *,
        parent_id: str | None = None,
        _service_fn: Any | None = None,
    ) -> File:
        """Create a new folder in Google Drive. Returns File with is_folder=True."""
        self._check_write_mode()
        body: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME_TYPE}
        if parent_id:
            body["parents"] = [parent_id]
        svc = _service_fn or self._get_service()
        result = svc.files().create(body=body, fields=FILE_FIELDS).execute()
        return self._drive_file_to_file(result)

    def _drive_file_to_file(self, raw: dict[str, Any]) -> File:
        """Map a Drive API file dict to the File TypedDict."""
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
            path=None,
            parent_id=(raw.get("parents") or [None])[0],
            is_folder=raw.get("mimeType") == FOLDER_MIME_TYPE,
            download_url=raw.get("webViewLink"),
            content=None,
        )
