"""TokenStore protocol — abstracts where OAuth tokens live.

Single-user CLI uses :class:`FilesystemTokenStore` (the historical default —
``<credentials_dir>/tokens/<account>/token_<tier>.json``). Multi-tenant servers
(e.g. Nexus's FastAPI BFF) inject a ``PostgresTokenStore`` that stores
encrypted blobs in a per-user row.

A ``token`` is the parsed JSON form of an OAuth credential (the same shape
``Credentials.to_json()`` returns and ``Credentials.from_authorized_user_info``
consumes). Stores deal in ``dict``s; the auth layer handles
serialization to/from :class:`google.oauth2.credentials.Credentials`.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

# Token payload — the parsed JSON form of an OAuth credential. The Google
# client library accepts/produces a flat str→str mapping; we widen to
# ``dict[str, Any]`` so callers (including future MS / generic backends) don't
# fight typing for things like nested expiry metadata.
TokenPayload = dict[str, Any]


@runtime_checkable
class TokenStore(Protocol):
    """Where OAuth tokens are loaded from / persisted to.

    Implementations are scoped to whatever identity the caller has — for the
    CLI that's the local user; for a multi-tenant server it's the request's
    authenticated user. The store does **not** know about that scoping;
    callers pass distinct ``account``/``tier`` pairs per identity.
    """

    def load(self, account: str, tier: str) -> TokenPayload | None:
        """Return the stored token dict for ``(account, tier)`` or ``None``."""
        ...

    def save(self, account: str, tier: str, token: TokenPayload) -> None:
        """Persist ``token`` under ``(account, tier)``. Overwrites silently."""
        ...

    def delete(self, account: str, tier: str) -> None:
        """Remove the token at ``(account, tier)``. No-op if absent."""
        ...


_DIR_MODE = 0o700
_FILE_MODE = 0o600


def ensure_private_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) if needed and restrict it to mode 0700.

    Only the leaf directory is chmod-ed — parents such as ``~`` keep their
    existing permissions.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
    try:
        os.chmod(p, _DIR_MODE)
    except OSError:
        pass
    return p


def write_private_file(path: str | Path, data: str) -> None:
    """Atomically write ``data`` to ``path`` with mode 0600.

    The content goes to a temp file in the same directory (created 0600 by
    :func:`tempfile.mkstemp`), is flushed and fsync-ed, then ``os.replace``-d
    over the target — so readers never see a half-written token and a crash
    mid-write leaves the previous token intact. The parent directory is
    created/tightened to 0700. An existing file with looser permissions is
    replaced by the 0600 temp file, which tightens it.
    """
    target = Path(path)
    ensure_private_dir(target.parent)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, _FILE_MODE)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class FilesystemTokenStore:
    """Default store — JSON files at ``<credentials_dir>/tokens/<account>/token_<tier>.json``.

    Matches the layout iobox has used since 0.4.0 so existing on-disk tokens
    continue to work without migration. Token files are written atomically
    with mode 0600 inside 0700 directories (they hold refresh tokens and the
    OAuth client secret).
    """

    def __init__(self, credentials_dir: str | Path) -> None:
        self.credentials_dir = Path(credentials_dir)

    def _path(self, account: str, tier: str) -> Path:
        return self.credentials_dir / "tokens" / account / f"token_{tier}.json"

    def load(self, account: str, tier: str) -> TokenPayload | None:
        path = self._path(account, tier)
        if not path.exists():
            return None
        try:
            return cast(TokenPayload, json.loads(path.read_text()))
        except (OSError, ValueError):
            return None

    def save(self, account: str, tier: str, token: TokenPayload) -> None:
        ensure_private_dir(self.credentials_dir / "tokens")
        write_private_file(self._path(account, tier), json.dumps(token))

    def delete(self, account: str, tier: str) -> None:
        path = self._path(account, tier)
        if path.exists():
            path.unlink()
