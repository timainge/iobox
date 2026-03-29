"""
OneDriveProvider — read-only FileProvider backed by python-o365.

Uses the same O365 Account object as OutlookProvider for the same account.
O365 is an optional dependency; this module raises ImportError with a clear
message if the package is not installed.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from iobox.providers.base import File, FileProvider, FileQuery

try:
    from O365 import Account as _O365Account  # noqa: F401

    HAS_O365 = True
except ImportError:
    HAS_O365 = False

logger = logging.getLogger(__name__)


class OneDriveProvider(FileProvider):
    """Read-only FileProvider for Microsoft OneDrive via python-o365."""

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
        drive = self._get_drive()
        return {
            "name": getattr(drive, "name", None),
            "drive_type": getattr(drive, "drive_type", "personal"),
        }

    def _get_account(self) -> Any:
        if self._account is None:
            if self._microsoft_auth is not None:
                self._account = self._microsoft_auth.get_account()
            else:
                from iobox.providers.o365.auth import get_outlook_account

                self._account = get_outlook_account(account=self.account_email)
        return self._account

    def _get_drive(self) -> Any:
        return self._get_account().storage().get_default_drive()

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_files(self, query: FileQuery) -> list[File]:
        """Return files matching query."""
        drive = self._get_drive()

        if query.shared_with_me:
            logger.warning(
                "OneDriveProvider: shared_with_me filter not implemented for MVP; "
                "returning personal drive results."
            )

        if query.text:
            raw_items = list(drive.search(query.text, limit=query.max_results))
        elif query.folder_id:
            folder = drive.get_item(query.folder_id)
            raw_items = list(folder.get_items())[: query.max_results]
        else:
            root = drive.get_root_folder()
            raw_items = list(root.get_items())[: query.max_results]

        files: list[File] = []
        for item in raw_items:
            if query.mime_type and getattr(item, "mime_type", None) != query.mime_type:
                continue
            files.append(self._o365_item_to_file(item))

        return files[: query.max_results]

    def get_file(self, file_id: str) -> File:
        """Return file metadata by ID."""
        drive = self._get_drive()
        item = drive.get_item(file_id)
        if item is None:
            raise KeyError(f"File '{file_id}' not found")
        return self._o365_item_to_file(item)

    def get_file_content(self, file_id: str) -> str:
        """Return text content of file.

        Office documents (Word, Excel, etc.) return empty string with a warning.
        Plain text and other text/* files are decoded as UTF-8.
        """
        drive = self._get_drive()
        item = drive.get_item(file_id)
        if item is None:
            return ""
        mime: str = getattr(item, "mime_type", "") or ""
        if "officedocument" in mime or "msword" in mime:
            logger.warning("Text extraction for Office docs not supported in MVP: %s", file_id)
            return ""
        try:
            buffer = io.BytesIO()
            item.download(output=buffer)
            return buffer.getvalue().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Could not download file content %s: %s", file_id, exc)
            return ""

    def download_file(self, file_id: str) -> bytes:
        """Return raw bytes of file."""
        drive = self._get_drive()
        item = drive.get_item(file_id)
        buffer = io.BytesIO()
        item.download(output=buffer)
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
        """Upload a local file to OneDrive. Returns the created File.

        Note: OneDrive via python-o365 does not support trash — deletes are permanent.
        """
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
        """Replace the content of an existing OneDrive file. Returns the updated File."""
        self._check_write_mode()
        drive = self._get_drive()
        item = drive.get_item(file_id)
        if item is None:
            raise KeyError(f"File '{file_id}' not found")
        parent = item.parent
        new_item = parent.upload_file(item=local_path, item_name=item.name)
        return self._o365_item_to_file(new_item)

    def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
        """Delete a file from OneDrive (always permanent — OneDrive has no trash API).

        The ``permanent`` parameter is accepted for interface compatibility but
        OneDrive deletion via python-o365 is always permanent.
        """
        self._check_write_mode()
        drive = self._get_drive()
        item = drive.get_item(file_id)
        if item is not None:
            item.delete()

    def create_folder(self, name: str, *, parent_id: str | None = None) -> File:
        """Create a new folder in OneDrive. Returns File with is_folder=True."""
        self._check_write_mode()
        drive = self._get_drive()
        if parent_id:
            parent = drive.get_item(parent_id)
        else:
            parent = drive.get_root_folder()
        folder = parent.mkdir(name)
        return self._o365_item_to_file(folder)

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _o365_item_to_file(self, item: Any) -> File:
        """Map a python-o365 DriveItem object to the File TypedDict."""
        is_folder: bool = bool(getattr(item, "is_folder", False))
        created = getattr(item, "created_datetime", None)
        modified = getattr(item, "modified_datetime", None)
        parent = getattr(item, "parent", None)
        parent_id: str | None = str(getattr(parent, "object_id", "") or "") if parent else None
        name: str = getattr(item, "name", "") or ""
        mime_type: str = getattr(item, "mime_type", "") or ("inode/directory" if is_folder else "")

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
            path=None,
            parent_id=parent_id or None,
            is_folder=is_folder,
            download_url=getattr(item, "web_url", None),
            content=None,
        )
