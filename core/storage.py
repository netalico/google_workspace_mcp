"""Shared helpers for creating key-value stores backing OAuth/session state."""

import string
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from key_value.aio.errors import InvalidKeyError
from key_value.aio.wrappers.base import BaseWrapper

if TYPE_CHECKING:
    from key_value.aio.stores.filetree import FileTreeStore

SAFE_FILENAME_CHARS = string.ascii_letters + string.digits + "-_."
"""Characters allowed in on-disk file names for key-value stores."""


def make_sanitized_file_store(data_directory: str) -> "FileTreeStore":
    """Return a ``FileTreeStore`` using the project-wide sanitization rules.

    Both the OAuth-proxy server storage and the CLI token storage need
    identical sanitization; this factory keeps them in sync.
    """
    # Imported here so the module stays usable without the 'disk' extra.
    from key_value.aio._utils.sanitization import HybridSanitizationStrategy
    from key_value.aio.stores.filetree import FileTreeStore

    return FileTreeStore(
        data_directory=data_directory,
        key_sanitization_strategy=HybridSanitizationStrategy(
            allowed_characters=SAFE_FILENAME_CHARS,
        ),
    )


class MissingOnInvalidKeyWrapper(BaseWrapper):
    """Report keys the backend cannot represent as absent instead of raising.

    A backend's key sanitizer rejects IDs it has no way to encode. Firestore's
    strategy raises ``InvalidKeyError`` for the reserved ``S_``/``H_`` prefixes
    it stamps onto sanitized document IDs, so a client_id starting with those
    is unstorable rather than merely unknown.

    OAuth client IDs come straight off the query string
    (``/authorize?client_id=...``) and FastMCP's ``get_client()`` does not catch
    storage errors, so such a request escaped as a bare 500 instead of the
    normal "client is not registered" 400.

    Reads answer "not found", which is the truthful answer: a key the backend
    can never write is a key it can never hold. Writes stay strict -- client IDs
    are server-generated (registration ignores a client-supplied one), so an
    unrepresentable key on the write path is a bug worth surfacing loudly rather
    than dropping data silently.
    """

    def __init__(self, key_value: Any) -> None:
        self.key_value = key_value

    async def get(self, key: str, *, collection: str | None = None) -> dict[str, Any] | None:
        try:
            return await self.key_value.get(collection=collection, key=key)
        except InvalidKeyError:
            return None

    async def get_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[dict[str, Any] | None]:
        try:
            return await self.key_value.get_many(collection=collection, keys=keys)
        except InvalidKeyError:
            # One bad key fails the whole batch; retry per key so the valid ones
            # still resolve and only the unstorable ones come back as None.
            return [await self.get(key, collection=collection) for key in keys]

    async def ttl(
        self, key: str, *, collection: str | None = None
    ) -> tuple[dict[str, Any] | None, float | None]:
        try:
            return await self.key_value.ttl(collection=collection, key=key)
        except InvalidKeyError:
            return (None, None)

    async def ttl_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[tuple[dict[str, Any] | None, float | None]]:
        try:
            return await self.key_value.ttl_many(collection=collection, keys=keys)
        except InvalidKeyError:
            return [await self.ttl(key, collection=collection) for key in keys]

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        try:
            return await self.key_value.delete(collection=collection, key=key)
        except InvalidKeyError:
            return False

    async def delete_many(self, keys: Sequence[str], *, collection: str | None = None) -> int:
        try:
            return await self.key_value.delete_many(keys=keys, collection=collection)
        except InvalidKeyError:
            deleted = 0
            for key in keys:
                if await self.delete(key, collection=collection):
                    deleted += 1
            return deleted
