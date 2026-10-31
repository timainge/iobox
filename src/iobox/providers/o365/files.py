"""
OneDriveProvider — FileProvider backed by python-o365.

Uses the same O365 Account object as OutlookProvider for the same account.
O365 is an optional dependency; this module raises ImportError with a clear
message if the package is not installed.

python-o365 2.1 ``DriveItem`` API notes (verified against the source):
``created`` / ``modified`` (datetimes), ``parent_id``, ``parent_path``,
``web_url``, ``size``, ``is_folder``; ``mime_type`` exists only on ``File``.
Folders are created with ``Folder.create_child_folder(name)``.
``DriveItem.delete()`` moves the item to the recycle bin.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from iobox.providers.base import File, FileProvider, FileQuery

try:
    from O365 import Account as _O365Account  # noqa: F401

    HAS_O365 = True
except ImportError:
    HAS_O365 = False

logger = logging.getLogger(__name__)


def _http_status(exc: BaseException) -> int | None:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


class OneDriveProvider(FileProvider):
    """FileProvider for Microsoft OneDrive via python-o365."""

    PROVIDER_ID: str = "onedrive"

    def __init__(
        self,
        account_email: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
        auth: Any | None = None,
    ) -> None:
        if not HAS_O365:
            raise ImportError(
                "O365 package required for OneDrive support. "
                "Install with: pip install 'iobox[outlook]'"
            )
        self.account_email = account_email
        self.credentials_dir = credentials_dir
        self.mode = mode
        self._microsoft_auth: Any | None = auth
        self._account: Any = None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        self._get_account()

    def get_profile(self) -> dict[str, Any]:
        """Return drive info: name and drive type."""
        drive = self._get_account().storage().get_default_drive(request_drive=True)
        return {
            "name": getattr(drive, "name", None),
            "drive_type": getattr(drive, "drive_type", None) or "personal",
        }

    def _get_account(self) -> Any:
        if self._account is None:
            from iobox.providers.o365.auth import ensure_immutable_ids

            if self._microsoft_auth is None:
                from iobox.providers.o365.auth import MicrosoftAuth, get_microsoft_scopes

                self._microsoft_auth = MicrosoftAuth(
                    account=self.account_email,
                    scopes=get_microsoft_scopes(["drive"], self.mode),
                    credentials_dir=self.credentials_dir,
                    mode=self.mode,
                )
            self._account = self._microsoft_auth.get_account()
            ensure_immutable_ids(self._account)
        return self._account

    def _get_drive(self) -> Any:
        return self._get_account().storage().get_default_drive()

    def _get_item(self, file_id: str) -> Any:
        """Return the DriveItem for *file_id*; ``KeyError`` if it does not exist."""
        try:
            item = self._get_drive().get_item(file_id)
        except Exception as exc:
            if _http_status(exc) == 404:
                raise KeyError(f"File '{file_id}' not found") from exc
            raise
        if item is None:
            raise KeyError(f"File '{file_id}' not found")
        return item

    def _get_folder(self, folder_id: str | None) -> Any:
        if folder_id:
            folder = self._get_item(folder_id)
            if not getattr(folder, "is_folder", False):
                raise ValueError(f"Item '{folder_id}' is not a folder")
            return folder
        root = self._get_drive().get_root_folder()
        if root is None:
            raise RuntimeError("Could not load the OneDrive root folder")
        return root

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_files(self, query: FileQuery) -> list[File]:
        """Return files matching query."""
        drive = self._get_drive()
        limit = query.max_results

        if query.shared_with_me:
            raw_items = drive.get_shared_with_me(limit=limit)
        elif query.text:
            # The search(q='...') path segment is an OData string literal.
            raw_items = drive.search(query.text.replace("'", "''"), limit=limit)
        else:
            raw_items = self._get_folder(query.folder_id).get_items(limit=limit)

        files: list[File] = []
        for item in raw_items:
            if query.mime_type and getattr(item, "mime_type", None) != query.mime_type:
                continue
            files.append(self._o365_item_to_file(item))
            if len(files) >= limit:
                break
        return files

    def get_file(self, file_id: str) -> File:
        """Return file metadata by ID."""
        return self._o365_item_to_file(self._get_item(file_id))

    def get_file_content(self, file_id: str) -> str:
        """Return text content of file.

        Office documents (Word, Excel, etc.) return empty string with a warning.
        Plain text and other text/* files are decoded as UTF-8.
        """
        try:
            item = self._get_item(file_id)
        except KeyError:
            return ""
        mime: str = getattr(item, "mime_type", "") or ""
        if "officedocument" in mime or "msword" in mime:
            logger.warning("Text extraction for Office docs not supported in MVP: %s", file_id)
            return ""
        buffer = io.BytesIO()
        if not item.download(output=buffer):
            logger.warning("Could not download file content %s", file_id)
            return ""
        return buffer.getvalue().decode("utf-8", errors="replace")

    def download_file(self, file_id: str) -> bytes:
        """Return raw bytes of file."""
        item = self._get_item(file_id)
        if getattr(item, "is_folder", False):
            raise ValueError(f"'{file_id}' is a folder, not a file")
        buffer = io.BytesIO()
        # DriveItem.download() logs and returns False instead of raising.
        if not item.download(output=buffer):
            raise RuntimeError(f"Failed to download OneDrive file {file_id!r}")
        return buffer.getvalue()

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
    ) -> File:
        """Upload a local file to OneDrive. Returns the created File."""
        self._check_write_mode()
        path = Path(local_path)
        filename = name or path.name
        folder = self._get_folder(parent_id)
        item = folder.upload_file(item=str(path), item_name=filename)
        if item is None:
            raise RuntimeError(f"Failed to upload {local_path!r}")
        return self._o365_item_to_file(item)

    def update_file(self, file_id: str, local_path: str) -> File:
        """Replace the content of an existing OneDrive file. Returns the updated File.

        Re-uploads into the item's parent folder under the same name, which
        Graph treats as a content replace (the item ID is preserved).
        """
        self._check_write_mode()
        item = self._get_item(file_id)
        parent = self._get_folder(item.parent_id) if item.parent_id else self._get_folder(None)
        new_item = parent.upload_file(item=str(local_path), item_name=item.name)
        if new_item is None:
            raise RuntimeError(f"Failed to update OneDrive file {file_id!r}")
        return self._o365_item_to_file(new_item)

    def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
        """Delete a file from OneDrive.

        By default the item goes to the recycle bin (``DriveItem.delete()``).
        With ``permanent=True`` it is removed via Graph ``permanentDelete``
        (supported for OneDrive for Business / SharePoint; personal OneDrive
        rejects it). Missing items are a no-op.
        """
        self._check_write_mode()
        try:
            item = self._get_item(file_id)
        except KeyError:
            logger.warning("delete_file: %r not found", file_id)
            return
        if permanent:
            url = item.build_url(f"/items/{item.object_id}/permanentDelete")
            if not item.con.post(url):
                raise RuntimeError(f"Failed to permanently delete {file_id!r}")
            return
        if not item.delete():
            raise RuntimeError(f"Failed to delete {file_id!r}")

    def create_folder(self, name: str, *, parent_id: str | None = None) -> File:
        """Create a new folder in OneDrive. Returns File with is_folder=True."""
        self._check_write_mode()
        parent = self._get_folder(parent_id)
        folder = parent.create_child_folder(name)
        if folder is None:
            raise RuntimeError(f"Failed to create folder {name!r}")
        return self._o365_item_to_file(folder)

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _o365_item_to_file(self, item: Any) -> File:
        """Map a python-o365 ``DriveItem`` to the iobox ``File`` TypedDict."""
        is_folder: bool = bool(getattr(item, "is_folder", False))
        created = getattr(item, "created", None)
        modified = getattr(item, "modified", None)
        name: str = getattr(item, "name", "") or ""
        mime_type: str = getattr(item, "mime_type", None) or (
            "inode/directory" if is_folder else ""
        )
        parent_path: str | None = getattr(item, "parent_path", None)
        path: str | None = None
        if parent_path:
            # "/drive/root:/Folder/Sub" → "/Folder/Sub/name"
            rel = parent_path.split("root:", 1)[-1] if "root:" in parent_path else parent_path
            path = f"{rel.rstrip('/')}/{name}" if rel else f"/{name}"

        return File(
            id=str(getattr(item, "object_id", "") or ""),
            provider_id=self.PROVIDER_ID,
            resource_type="file",
            title=name,
            created_at=created.isoformat() if created else "",
            modified_at=modified.isoformat() if modified else "",
            url=getattr(item, "web_url", None),
            name=name,
            mime_type=mime_type,
            size=int(getattr(item, "size", 0) or 0),
            path=path,
            parent_id=getattr(item, "parent_id", None) or None,
            is_folder=is_folder,
            download_url=getattr(item, "web_url", None),
            content=None,
        )
