"""Tests for COG validation.

Uses synthetic GeoTIFFs created with rasterio to test COG compliance checks.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
import rasterio.enums
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from earthforge.raster.errors import RasterError
from earthforge.raster.validate import CogValidationResult, validate_cog


@pytest.fixture()
def strip_geotiff(tmp_path: Path) -> Path:
    """Create a strip-layout (non-tiled) GeoTIFF — not COG-compliant."""
    path = tmp_path / "strip.tif"
    width, height = 64, 64
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as ds:
        ds.write(np.ones((height, width), dtype=np.uint8), 1)

    return path


@pytest.fixture()
def tiled_compressed_geotiff(tmp_path: Path) -> Path:
    """Create a tiled, compressed GeoTIFF with overviews — COG-compliant."""
    path = tmp_path / "cog.tif"
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


@pytest.fixture()
def tiled_no_overviews(tmp_path: Path) -> Path:
    """Create a tiled, compressed GeoTIFF without overviews."""
    path = tmp_path / "tiled_no_ovr.tif"
    width, height = 256, 256
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs=CRS.from_epsg(4326),
        transform=transform,
        tiled=True,
        blockxsize=128,
        blockysize=128,
        compress="lzw",
    ) as ds:
        ds.write(np.ones((height, width), dtype=np.uint8), 1)

    return path


class TestValidateCog:
    """Tests for COG compliance validation."""

    async def test_valid_cog(self, tiled_compressed_geotiff: Path) -> None:
        result = await validate_cog(str(tiled_compressed_geotiff))
        assert isinstance(result, CogValidationResult)
        assert result.is_valid
        assert "Valid COG" in result.summary

    async def test_strip_layout_fails_tiled_check(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        assert not result.is_valid

        tiled_check = next(c for c in result.checks if c.name == "tiled")
        assert not tiled_check.passed

    async def test_missing_overviews_detected(self, tiled_no_overviews: Path) -> None:
        result = await validate_cog(str(tiled_no_overviews))
        assert not result.is_valid

        ovr_check = next(c for c in result.checks if c.name == "overviews")
        assert not ovr_check.passed

    async def test_compression_detected(self, tiled_compressed_geotiff: Path) -> None:
        result = await validate_cog(str(tiled_compressed_geotiff))
        comp_check = next(c for c in result.checks if c.name == "compression")
        assert comp_check.passed
        assert "deflate" in comp_check.message.lower()

    async def test_no_compression_detected(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        comp_check = next(c for c in result.checks if c.name == "compression")
        assert not comp_check.passed

    async def test_geotiff_check(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        gtiff_check = next(c for c in result.checks if c.name == "geotiff")
        assert gtiff_check.passed

    async def test_ifd_order_check_present(self, tiled_compressed_geotiff: Path) -> None:
        result = await validate_cog(str(tiled_compressed_geotiff))
        ifd_check = next(c for c in result.checks if c.name == "ifd_order")
        assert ifd_check.passed

    async def test_summary_includes_counts(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        assert "/" in result.summary  # e.g. "2/5 checks passed"

    async def test_all_checks_present(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        check_names = {c.name for c in result.checks}
        assert check_names == {"geotiff", "tiled", "overviews", "compression", "ifd_order"}

    async def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(RasterError, match="Failed to open"):
            await validate_cog("/nonexistent/path.tif")

    async def test_source_recorded(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        assert result.source == str(strip_geotiff)

    async def test_json_serializable(self, tiled_compressed_geotiff: Path) -> None:
        import json

        result = await validate_cog(str(tiled_compressed_geotiff))
        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["is_valid"] is True
