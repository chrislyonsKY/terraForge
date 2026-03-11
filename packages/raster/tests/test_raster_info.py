"""Tests for raster info inspection.

Uses a synthetic GeoTIFF created with rasterio to avoid external test data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from earthforge.raster.errors import RasterError
from earthforge.raster.info import RasterInfo, inspect_raster


@pytest.fixture()
def sample_geotiff(tmp_path: Path) -> Path:
    """Create a minimal GeoTIFF for testing."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds

    path = tmp_path / "test.tif"
    width, height = 64, 64
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=3,
        dtype="uint8",
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as ds:
        for i in range(1, 4):
            ds.write(np.ones((height, width), dtype=np.uint8) * i, i)

    return path


@pytest.fixture()
def sample_cog(tmp_path: Path) -> Path:
    """Create a minimal tiled GeoTIFF (COG-like) for testing."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds

    path = tmp_path / "tiled.tif"
    width, height = 256, 256
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(32617),
        transform=transform,
        tiled=True,
        blockxsize=128,
        blockysize=128,
        compress="deflate",
    ) as ds:
        ds.write(np.random.rand(height, width).astype(np.float32), 1)
        ds.build_overviews([2, 4], rasterio.enums.Resampling.nearest)
        ds.update_tags(ns="rio_overview", resampling="nearest")

    return path


class TestInspectRaster:
    """Tests for raster metadata inspection."""

    async def test_basic_geotiff(self, sample_geotiff: Path) -> None:
        info = await inspect_raster(str(sample_geotiff))
        assert isinstance(info, RasterInfo)
        assert info.width == 64
        assert info.height == 64
        assert info.band_count == 3
        assert info.driver == "GTiff"
        assert info.crs is not None
        assert "4326" in info.crs

    async def test_bounds(self, sample_geotiff: Path) -> None:
        info = await inspect_raster(str(sample_geotiff))
        assert len(info.bounds) == 4
        west, south, east, north = info.bounds
        assert west == pytest.approx(-85.0)
        assert south == pytest.approx(37.0)
        assert east == pytest.approx(-84.0)
        assert north == pytest.approx(38.0)

    async def test_band_info(self, sample_geotiff: Path) -> None:
        info = await inspect_raster(str(sample_geotiff))
        assert len(info.bands) == 3
        assert info.bands[0].index == 1
        assert info.bands[0].dtype == "uint8"

    async def test_tiled_geotiff(self, sample_cog: Path) -> None:
        info = await inspect_raster(str(sample_cog))
        assert info.is_tiled is True
        assert info.tile_width == 128
        assert info.tile_height == 128
        assert info.compression == "deflate"

    async def test_overviews(self, sample_cog: Path) -> None:
        info = await inspect_raster(str(sample_cog))
        assert info.overview_count == 2
        assert 2 in info.overview_levels
        assert 4 in info.overview_levels

    async def test_untiled_has_no_tile_dims(self, sample_geotiff: Path) -> None:
        info = await inspect_raster(str(sample_geotiff))
        assert info.is_tiled is False
        assert info.tile_width is None
        assert info.tile_height is None

    async def test_transform(self, sample_geotiff: Path) -> None:
        info = await inspect_raster(str(sample_geotiff))
        assert len(info.transform) == 6

    async def test_nonexistent_raises(self) -> None:
        with pytest.raises(RasterError, match="Failed to read"):
            await inspect_raster("/nonexistent/file.tif")

    async def test_json_serializable(self, sample_geotiff: Path) -> None:
        """RasterInfo must be JSON-serializable for --output json."""
        import json

        info = await inspect_raster(str(sample_geotiff))
        dumped = info.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["width"] == 64
