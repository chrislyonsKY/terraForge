"""Tests for the TerraForge storage abstraction.

Uses obstore's LocalStore backend so no real cloud calls are made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from terraforge.core.config import TerraForgeProfile
from terraforge.core.errors import StorageError
from terraforge.core.storage import StorageClient, _build_store

# ---------------------------------------------------------------------------
# Store construction
# ---------------------------------------------------------------------------


class TestBuildStore:
    """Tests for store factory from profile."""

    def test_local_backend(self, tmp_path: Path) -> None:
        profile = TerraForgeProfile(
            name="test",
            storage_backend="local",
            storage_options={"root": str(tmp_path)},
        )
        store = _build_store(profile)
        assert store is not None

    def test_unknown_backend_raises(self) -> None:
        profile = TerraForgeProfile.__new__(TerraForgeProfile)
        # Bypass __post_init__ validation to test _build_store directly
        object.__setattr__(profile, "name", "bad")
        object.__setattr__(profile, "stac_api", None)
        object.__setattr__(profile, "storage_backend", "ftp")
        object.__setattr__(profile, "storage_options", {})
        with pytest.raises(StorageError, match="Unknown storage backend"):
            _build_store(profile)


# ---------------------------------------------------------------------------
# StorageClient with local backend
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_client(tmp_path: Path) -> StorageClient:
    """A StorageClient backed by a local tmp directory."""
    profile = TerraForgeProfile(
        name="local-test",
        storage_backend="local",
        storage_options={"root": str(tmp_path)},
    )
    return StorageClient.from_profile(profile)


@pytest.fixture()
def tmp_path_with_file(tmp_path: Path) -> Path:
    """Create a test file in the tmp directory."""
    test_file = tmp_path / "sample.bin"
    test_file.write_bytes(b"HELLO WORLD 1234567890")
    return tmp_path


@pytest.fixture()
def client_with_file(tmp_path_with_file: Path) -> StorageClient:
    """A StorageClient with a pre-existing test file."""
    profile = TerraForgeProfile(
        name="local-test",
        storage_backend="local",
        storage_options={"root": str(tmp_path_with_file)},
    )
    return StorageClient.from_profile(profile)


class TestStorageClientPutGet:
    """Tests for put and get operations."""

    async def test_put_then_get(self, local_client: StorageClient) -> None:
        await local_client.put("test.txt", b"hello terraforge")
        data = await local_client.get("test.txt")
        assert data == b"hello terraforge"

    async def test_get_nonexistent_raises(self, local_client: StorageClient) -> None:
        with pytest.raises(StorageError, match="Failed to read"):
            await local_client.get("does-not-exist.bin")

    async def test_put_overwrites(self, local_client: StorageClient) -> None:
        await local_client.put("file.bin", b"version1")
        await local_client.put("file.bin", b"version2")
        data = await local_client.get("file.bin")
        assert data == b"version2"


class TestStorageClientGetRange:
    """Tests for range reads."""

    async def test_range_read(self, client_with_file: StorageClient) -> None:
        data = await client_with_file.get_range("sample.bin", start=0, end=5)
        assert data == b"HELLO"

    async def test_range_read_middle(self, client_with_file: StorageClient) -> None:
        data = await client_with_file.get_range("sample.bin", start=6, end=11)
        assert data == b"WORLD"

    async def test_range_nonexistent_raises(self, local_client: StorageClient) -> None:
        with pytest.raises(StorageError, match="Failed to read range"):
            await local_client.get_range("nope.bin", start=0, end=10)


class TestStorageClientHead:
    """Tests for metadata retrieval."""

    async def test_head_returns_meta(self, client_with_file: StorageClient) -> None:
        meta = await client_with_file.head("sample.bin")
        assert meta.path == "sample.bin"
        assert meta.size == len(b"HELLO WORLD 1234567890")
        assert meta.last_modified is not None

    async def test_head_nonexistent_raises(self, local_client: StorageClient) -> None:
        with pytest.raises(StorageError, match="Failed to head"):
            await local_client.head("ghost.bin")


class TestStorageClientList:
    """Tests for object listing."""

    async def test_list_objects(self, client_with_file: StorageClient) -> None:
        items = [item async for item in client_with_file.list()]
        paths = [item.path for item in items]
        assert "sample.bin" in paths

    async def test_list_empty(self, local_client: StorageClient) -> None:
        items = [item async for item in local_client.list()]
        assert items == []


class TestStorageClientDelete:
    """Tests for deletion."""

    async def test_delete_existing(self, client_with_file: StorageClient) -> None:
        await client_with_file.delete("sample.bin")
        with pytest.raises(StorageError):
            await client_with_file.get("sample.bin")
