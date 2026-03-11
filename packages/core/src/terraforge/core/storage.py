"""TerraForge cloud storage abstraction.

All cloud storage access in TerraForge flows through this module. Domain packages
never import ``obstore`` directly — they use :class:`StorageClient` to get a
unified async interface across S3, GCS, Azure Blob, and local filesystem.

The wrapper translates obstore's free-function API into a method-based client
that carries its store reference internally, and converts obstore exceptions
into :class:`~terraforge.core.errors.StorageError`.

Usage in domain code::

    from terraforge.core.storage import StorageClient

    async def read_header(profile: TerraForgeProfile, path: str) -> bytes:
        client = StorageClient.from_profile(profile)
        return await client.get_range(path, start=0, end=512)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import obstore as obs
from obstore.store import AzureStore, GCSStore, LocalStore, S3Store

from terraforge.core.errors import StorageError

if TYPE_CHECKING:
    from obstore.store import ObjectStore

    from terraforge.core.config import TerraForgeProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ObjectMeta:
    """Metadata about a stored object.

    Parameters:
        path: Full object path within the store.
        size: Object size in bytes.
        last_modified: Last modification timestamp.
        e_tag: Entity tag (opaque identifier for the object version).
    """

    path: str
    size: int
    last_modified: datetime
    e_tag: str


def _build_store(profile: TerraForgeProfile) -> ObjectStore:
    """Create an obstore store instance from a TerraForge profile.

    Parameters:
        profile: The active TerraForge profile with backend and options.

    Returns:
        An obstore ``ObjectStore`` implementation.

    Raises:
        StorageError: If the backend is unknown or store creation fails.
    """
    backend = profile.storage_backend
    opts = profile.storage_options

    try:
        if backend == "s3":
            return S3Store(
                bucket=opts.get("bucket", ""),
                region=opts.get("region", "us-east-1"),
                endpoint=opts.get("endpoint"),
                skip_signature=opts.get("skip_signature", "false").lower() == "true",
            )
        if backend == "gcs":
            return GCSStore(
                bucket=opts.get("bucket", ""),
            )
        if backend == "azure":
            return AzureStore(
                container=opts.get("container", ""),
                account_name=opts.get("account_name"),
            )
        if backend == "local":
            root = opts.get("root", ".")
            return LocalStore(prefix=root)
    except Exception as exc:
        raise StorageError(f"Failed to create {backend} storage client: {exc}") from exc

    raise StorageError(f"Unknown storage backend: {backend!r}")


def _convert_meta(raw: object) -> ObjectMeta:
    """Convert an obstore ObjectMeta dict to our dataclass.

    obstore >=0.9 returns plain dicts from head/list operations with keys:
    ``path``, ``size``, ``last_modified``, ``e_tag``, ``version``.

    Parameters:
        raw: The obstore metadata dict.

    Returns:
        A TerraForge ``ObjectMeta``.
    """
    if isinstance(raw, dict):
        return ObjectMeta(
            path=raw["path"],
            size=raw["size"],
            last_modified=raw["last_modified"],
            e_tag=raw.get("e_tag") or "",
        )
    # Fallback for future obstore versions that may return objects
    return ObjectMeta(
        path=raw.path,  # type: ignore[union-attr]
        size=raw.size,  # type: ignore[union-attr]
        last_modified=raw.last_modified,  # type: ignore[union-attr]
        e_tag=raw.e_tag or "",  # type: ignore[union-attr]
    )


class StorageClient:
    """Unified cloud storage client wrapping obstore.

    Provides async methods for common object storage operations. Created
    from a :class:`~terraforge.core.config.TerraForgeProfile` via the
    :meth:`from_profile` classmethod.

    Parameters:
        store: The underlying obstore ``ObjectStore`` implementation.
    """

    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    @classmethod
    def from_profile(cls, profile: TerraForgeProfile) -> StorageClient:
        """Create a storage client from a TerraForge profile.

        Parameters:
            profile: The profile containing backend selection and credentials.

        Returns:
            A configured ``StorageClient``.

        Raises:
            StorageError: If the storage backend cannot be initialized.
        """
        store = _build_store(profile)
        return cls(store)

    async def get(self, path: str) -> bytes:
        """Read an entire object as bytes.

        Parameters:
            path: Object path within the store.

        Returns:
            The full object content.

        Raises:
            StorageError: If the object cannot be read.
        """
        try:
            result = await obs.get_async(self._store, path)
            raw = await result.bytes_async()
            return bytes(raw)
        except Exception as exc:
            raise StorageError(f"Failed to read {path!r}: {exc}") from exc

    async def get_range(self, path: str, *, start: int, end: int) -> bytes:
        """Read a byte range from an object.

        This is critical for cloud-native formats where only a small portion
        of a large file needs to be read (magic bytes, COG overviews, etc.).

        Parameters:
            path: Object path within the store.
            start: Start byte offset (inclusive).
            end: End byte offset (exclusive).

        Returns:
            The requested byte range.

        Raises:
            StorageError: If the range cannot be read.
        """
        try:
            result = await obs.get_range_async(self._store, path, start=start, end=end)
            return bytes(result)
        except Exception as exc:
            raise StorageError(
                f"Failed to read range [{start}:{end}] from {path!r}: {exc}"
            ) from exc

    async def put(self, path: str, data: bytes) -> None:
        """Write bytes to an object.

        Parameters:
            path: Object path within the store.
            data: The content to write.

        Raises:
            StorageError: If the object cannot be written.
        """
        try:
            await obs.put_async(self._store, path, data)
        except Exception as exc:
            raise StorageError(f"Failed to write {path!r}: {exc}") from exc

    async def head(self, path: str) -> ObjectMeta:
        """Retrieve object metadata without downloading content.

        Parameters:
            path: Object path within the store.

        Returns:
            Metadata about the object.

        Raises:
            StorageError: If the metadata cannot be retrieved.
        """
        try:
            raw = await obs.head_async(self._store, path)
            return _convert_meta(raw)
        except Exception as exc:
            raise StorageError(f"Failed to head {path!r}: {exc}") from exc

    async def list(self, prefix: str | None = None) -> AsyncIterator[ObjectMeta]:
        """List objects under a prefix.

        Parameters:
            prefix: Optional path prefix to filter results.

        Yields:
            :class:`ObjectMeta` for each matching object.

        Raises:
            StorageError: If the listing fails.
        """
        try:
            # obstore 0.9 provides sync list() returning a ListStream that
            # yields batches (lists of dicts). No list_async exists.
            stream = obs.list(self._store, prefix=prefix)
            for batch in stream:
                if isinstance(batch, list):
                    for item in batch:
                        yield _convert_meta(item)
                else:
                    yield _convert_meta(batch)
        except Exception as exc:
            raise StorageError(f"Failed to list {prefix!r}: {exc}") from exc

    async def delete(self, path: str) -> None:
        """Delete an object.

        Parameters:
            path: Object path within the store.

        Raises:
            StorageError: If the deletion fails. Note that some backends
                          (S3) silently succeed for missing objects.
        """
        try:
            await obs.delete_async(self._store, path)
        except Exception as exc:
            raise StorageError(f"Failed to delete {path!r}: {exc}") from exc
