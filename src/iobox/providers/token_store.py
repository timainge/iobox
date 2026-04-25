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


class FilesystemTokenStore:
    """Default store — JSON files at ``<credentials_dir>/tokens/<account>/token_<tier>.json``.

    Matches the layout iobox has used since 0.4.0 so existing on-disk tokens
    continue to work without migration.
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
        path = self._path(account, tier)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(token))

    def delete(self, account: str, tier: str) -> None:
        path = self._path(account, tier)
        if path.exists():
            path.unlink()
