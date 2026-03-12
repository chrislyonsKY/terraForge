"""Tests for earthforge.stac.fetch — STAC asset download.

All HTTP is mocked via respx. No real network calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.errors import StacError
from earthforge.stac.fetch import (
    FetchResult,
    _select_assets,
    fetch_assets,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROFILE = EarthForgeProfile(name="test", storage_backend="local")

ITEM_URL = "https://earth-search.example.com/v1/collections/sentinel-2/items/S2A_TEST"

ITEM_JSON = {
    "id": "S2A_TEST",
    "type": "Feature",
    "stac_version": "1.0.0",
    "bbox": [-85.0, 37.0, -84.0, 38.0],
    "geometry": {"type": "Polygon", "coordinates": [[]]},
    "properties": {"datetime": "2025-06-01T00:00:00Z"},
    "links": [],
    "assets": {
        "red": {
            "href": "https://cdn.example.com/S2A_TEST/red.tif",
            "type": "image/tiff; application=geotiff",
            "roles": ["data"],
        },
        "green": {
            "href": "https://cdn.example.com/S2A_TEST/green.tif",
            "type": "image/tiff; application=geotiff",
            "roles": ["data"],
        },
        "blue": {
            "href": "https://cdn.example.com/S2A_TEST/blue.tif",
            "type": "image/tiff; application=geotiff",
            "roles": ["data"],
        },
        "thumbnail": {
            "href": "https://cdn.example.com/S2A_TEST/thumb.jpg",
            "type": "image/jpeg",
            "roles": ["thumbnail"],
        },
    },
}

FAKE_TIFF = b"\x49\x49\x2a\x00" + b"\x00" * 1020  # fake TIFF bytes


# ---------------------------------------------------------------------------
# _select_assets
# ---------------------------------------------------------------------------


class TestSelectAssets:
    """Tests for the asset selection helper."""

    def test_select_all_excludes_thumbnail(self) -> None:
        result = _select_assets(ITEM_JSON["assets"], None)
        assert "thumbnail" not in result
        assert "red" in result
        assert "green" in result
        assert "blue" in result

    def test_select_specific_keys(self) -> None:
        result = _select_assets(ITEM_JSON["assets"], ["red", "blue"])
        assert set(result.keys()) == {"red", "blue"}

    def test_select_unknown_key_skipped(self) -> None:
        result = _select_assets(ITEM_JSON["assets"], ["red", "nir"])
        assert "red" in result
        assert "nir" not in result

    def test_select_empty_list(self) -> None:
        result = _select_assets(ITEM_JSON["assets"], [])
        assert result == {}

    def test_overview_role_excluded(self) -> None:
        assets = {
            "data": {"href": "data.tif", "roles": ["data"]},
            "overview": {"href": "overview.tif", "roles": ["overview"]},
        }
        result = _select_assets(assets, None)
        assert "data" in result
        assert "overview" not in result


# ---------------------------------------------------------------------------
# fetch_assets — mocked HTTP
# ---------------------------------------------------------------------------


class TestFetchAssets:
    """Integration tests for fetch_assets with mocked HTTP."""

    @respx.mock
    async def test_basic_fetch(self, tmp_path: Path) -> None:
        """Downloads requested assets and returns FetchResult."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))
        for color in ("red", "green", "blue"):
            url = f"https://cdn.example.com/S2A_TEST/{color}.tif"
            respx.head(url).mock(
                return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
            )
            respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        result = await fetch_assets(
            PROFILE,
            ITEM_URL,
            output_dir=str(tmp_path),
            assets=["red", "green", "blue"],
            parallel=2,
        )

        assert isinstance(result, FetchResult)
        assert result.item_id == "S2A_TEST"
        assert result.assets_requested == 3
        assert result.assets_fetched == 3
        assert result.assets_skipped == 0
        assert result.total_bytes_downloaded == len(FAKE_TIFF) * 3

    @respx.mock
    async def test_default_excludes_thumbnail(self, tmp_path: Path) -> None:
        """Default asset selection excludes thumbnail role."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))
        for color in ("red", "green", "blue"):
            url = f"https://cdn.example.com/S2A_TEST/{color}.tif"
            respx.head(url).mock(
                return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
            )
            respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        result = await fetch_assets(PROFILE, ITEM_URL, output_dir=str(tmp_path))

        # thumbnail excluded by default
        assert result.assets_requested == 3
        keys = {f.key for f in result.files}
        assert "thumbnail" not in keys

    @respx.mock
    async def test_resume_skips_complete_file(self, tmp_path: Path) -> None:
        """Skips assets whose local file matches the remote Content-Length."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))

        # Pre-write red.tif with the same size as the mock response
        (tmp_path / "red.tif").write_bytes(FAKE_TIFF)

        for color in ("red", "green", "blue"):
            url = f"https://cdn.example.com/S2A_TEST/{color}.tif"
            respx.head(url).mock(
                return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
            )
        # Only green and blue should be downloaded
        for color in ("green", "blue"):
            url = f"https://cdn.example.com/S2A_TEST/{color}.tif"
            respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        result = await fetch_assets(
            PROFILE,
            ITEM_URL,
            output_dir=str(tmp_path),
            assets=["red", "green", "blue"],
        )

        assert result.assets_skipped == 1
        assert result.assets_fetched == 2
        skipped = [f for f in result.files if f.skipped]
        assert skipped[0].key == "red"

    @respx.mock
    async def test_output_dir_created(self, tmp_path: Path) -> None:
        """Creates output directory if it does not exist."""
        out = tmp_path / "nested" / "deep"
        assert not out.exists()

        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))
        url = "https://cdn.example.com/S2A_TEST/red.tif"
        respx.head(url).mock(
            return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
        )
        respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        await fetch_assets(PROFILE, ITEM_URL, output_dir=str(out), assets=["red"])

        assert out.exists()
        assert (out / "red.tif").exists()

    @respx.mock
    async def test_default_output_dir_is_item_id(self, tmp_path: Path) -> None:
        """Default output dir is cwd/<item_id> when output_dir not specified."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))
        url = "https://cdn.example.com/S2A_TEST/red.tif"
        respx.head(url).mock(
            return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
        )
        respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = await fetch_assets(PROFILE, ITEM_URL, assets=["red"])
        finally:
            os.chdir(old_cwd)

        assert result.output_dir.endswith("S2A_TEST")

    @respx.mock
    async def test_item_fetch_failure_raises_stac_error(self, tmp_path: Path) -> None:
        """StacError raised if the item URL returns non-200."""
        respx.get(ITEM_URL).mock(return_value=Response(404))

        with pytest.raises(StacError, match="Failed to fetch"):
            await fetch_assets(PROFILE, ITEM_URL, output_dir=str(tmp_path))

    @respx.mock
    async def test_no_matching_assets_raises(self, tmp_path: Path) -> None:
        """StacError raised if requested asset keys don't exist in item."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))

        with pytest.raises(StacError, match="No matching assets"):
            await fetch_assets(
                PROFILE, ITEM_URL, output_dir=str(tmp_path), assets=["nir", "swir"]
            )

    @respx.mock
    async def test_elapsed_seconds_recorded(self, tmp_path: Path) -> None:
        """FetchResult includes a positive elapsed_seconds."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))
        url = "https://cdn.example.com/S2A_TEST/red.tif"
        respx.head(url).mock(
            return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
        )
        respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        result = await fetch_assets(PROFILE, ITEM_URL, output_dir=str(tmp_path), assets=["red"])

        assert result.elapsed_seconds >= 0

    @respx.mock
    async def test_files_written_to_disk(self, tmp_path: Path) -> None:
        """Downloaded files are actually written to disk."""
        respx.get(ITEM_URL).mock(return_value=Response(200, json=ITEM_JSON))
        url = "https://cdn.example.com/S2A_TEST/green.tif"
        respx.head(url).mock(
            return_value=Response(200, headers={"content-length": str(len(FAKE_TIFF))})
        )
        respx.get(url).mock(return_value=Response(200, content=FAKE_TIFF))

        result = await fetch_assets(
            PROFILE, ITEM_URL, output_dir=str(tmp_path), assets=["green"]
        )

        assert len(result.files) == 1
        assert Path(result.files[0].local_path).exists()
        assert Path(result.files[0].local_path).read_bytes() == FAKE_TIFF

    @respx.mock
    async def test_item_with_no_assets_raises(self, tmp_path: Path) -> None:
        """StacError raised if item has no assets."""
        empty_item = {**ITEM_JSON, "assets": {}}
        respx.get(ITEM_URL).mock(return_value=Response(200, json=empty_item))

        with pytest.raises(StacError, match="no assets"):
            await fetch_assets(PROFILE, ITEM_URL, output_dir=str(tmp_path))
