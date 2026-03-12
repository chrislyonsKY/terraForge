"""Tests for COG validation backed by rio-cogeo.

Uses rio-cogeo's own ``cog_translate`` to create genuine COG fixtures —
files written with rasterio's standard GTiff driver have incorrect IFD
ordering and would fail byte-level validation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from earthforge.raster.errors import RasterError
from earthforge.raster.validate import CogValidationResult, validate_cog

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def strip_geotiff(tmp_path: Path) -> Path:
    """Create a strip-layout (non-tiled), uncompressed GeoTIFF — not COG-compliant."""
    path = tmp_path / "strip.tif"
    width, height = 1024, 1024
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
def valid_cog(tmp_path: Path) -> Path:
    """Create a genuine COG using rio-cogeo's cog_translate.

    Files written with rasterio's standard GTiff driver do not have the
    correct IFD ordering required by the COG spec (overview data must
    precede full-resolution data in the file). cog_translate produces a
    properly structured COG that passes rio-cogeo's byte-level validation.
    """
    pytest.importorskip("rio_cogeo")
    from rio_cogeo.cogeo import cog_translate  # type: ignore[import-untyped]
    from rio_cogeo.profiles import cog_profiles  # type: ignore[import-untyped]

    src_path = tmp_path / "src.tif"
    cog_path = tmp_path / "cog.tif"
    width, height = 1024, 1024
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        src_path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as ds:
        ds.write(np.random.rand(height, width).astype(np.float32), 1)

    cog_translate(
        str(src_path),
        str(cog_path),
        cog_profiles.get("deflate"),
        add_mask=False,
        quiet=True,
    )
    return cog_path


@pytest.fixture()
def tiled_no_overviews(tmp_path: Path) -> Path:
    """Create a tiled, compressed GeoTIFF without overviews (1024x1024).

    At >512 pixels, rio-cogeo flags missing overviews. Using strict mode
    ensures this is reported as an error rather than a warning.
    """
    path = tmp_path / "tiled_no_ovr.tif"
    width, height = 1024, 1024
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
        blockxsize=256,
        blockysize=256,
        compress="lzw",
    ) as ds:
        ds.write(np.ones((height, width), dtype=np.uint8), 1)

    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidateCog:
    """Tests for COG compliance validation."""

    async def test_valid_cog(self, valid_cog: Path) -> None:
        result = await validate_cog(str(valid_cog))
        assert isinstance(result, CogValidationResult)
        assert result.is_valid
        assert "Valid COG" in result.summary

    async def test_strip_layout_fails(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        assert not result.is_valid
        tiled_check = next(c for c in result.checks if c.name == "tiled")
        assert not tiled_check.passed

    async def test_missing_overviews_fails(self, tiled_no_overviews: Path) -> None:
        result = await validate_cog(str(tiled_no_overviews))
        assert not result.is_valid
        ovr_check = next(c for c in result.checks if c.name == "overviews")
        assert not ovr_check.passed

    async def test_compression_detected(self, valid_cog: Path) -> None:
        result = await validate_cog(str(valid_cog))
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

    async def test_ifd_order_passes_for_valid_cog(self, valid_cog: Path) -> None:
        result = await validate_cog(str(valid_cog))
        ifd_check = next(c for c in result.checks if c.name == "ifd_order")
        assert ifd_check.passed

    async def test_summary_includes_counts(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        assert "/" in result.summary

    async def test_all_standard_checks_present(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        check_names = {c.name for c in result.checks}
        assert {"geotiff", "tiled", "overviews", "compression", "ifd_order"}.issubset(
            check_names
        )

    async def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(RasterError, match="Failed to validate"):
            await validate_cog("/nonexistent/path.tif")

    async def test_source_recorded(self, strip_geotiff: Path) -> None:
        result = await validate_cog(str(strip_geotiff))
        assert result.source == str(strip_geotiff)

    async def test_json_serializable(self, valid_cog: Path) -> None:
        import json

        result = await validate_cog(str(valid_cog))
        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["is_valid"] is True
