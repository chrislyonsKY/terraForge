"""Tests for GeoTIFF to COG conversion.

Creates synthetic GeoTIFF files and converts them to COG, validating
tiling, compression, overviews, and metadata preservation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
import rasterio.enums
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from earthforge.raster.convert import CogConvertResult, convert_to_cog
from earthforge.raster.errors import RasterError


@pytest.fixture()
def strip_geotiff(tmp_path: Path) -> Path:
    """Create a strip-layout (non-tiled) GeoTIFF — typical pre-COG file."""
    path = tmp_path / "strip.tif"
    width, height = 2048, 2048
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as ds:
        ds.write(np.random.rand(height, width).astype(np.float32) * 100, 1)

    return path


@pytest.fixture()
def rgb_geotiff(tmp_path: Path) -> Path:
    """Create a 3-band strip-layout GeoTIFF."""
    path = tmp_path / "rgb.tif"
    width, height = 256, 256
    transform = from_bounds(-85.0, 37.0, -84.0, 38.0, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=3,
        dtype="uint8",
        crs=CRS.from_epsg(32617),
        transform=transform,
    ) as ds:
        for i in range(1, 4):
            ds.write(np.random.randint(0, 255, (height, width), dtype=np.uint8), i)

    return path


class TestConvertToCog:
    """Tests for GeoTIFF → COG conversion."""

    async def test_basic_conversion(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output)

        assert isinstance(result, CogConvertResult)
        assert Path(output).exists()
        assert result.width == 2048
        assert result.height == 2048

    async def test_output_is_tiled(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        await convert_to_cog(str(strip_geotiff), output=output)

        with rasterio.open(output) as ds:
            block_h, block_w = ds.block_shapes[0]
            # Block should be a standard tile size (not full-row strip)
            assert block_w == 512  # Default blocksize
            assert block_h == 512

    async def test_output_is_compressed(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output, compression="deflate")

        assert result.compression == "deflate"
        with rasterio.open(output) as ds:
            assert ds.compression is not None

    async def test_overviews_generated(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output)

        with rasterio.open(output) as ds:
            overviews = ds.overviews(1)
            assert len(overviews) > 0

        assert len(result.overview_levels) > 0

    async def test_crs_preserved(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output)

        assert result.crs is not None
        assert "4326" in result.crs

        with rasterio.open(output) as ds:
            assert ds.crs is not None
            assert ds.crs.to_epsg() == 4326

    async def test_rgb_conversion(self, rgb_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(rgb_geotiff), output=output)

        assert result.band_count == 3
        with rasterio.open(output) as ds:
            assert ds.count == 3

    async def test_custom_blocksize(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output, blocksize=256)

        assert result.blocksize == 256
        with rasterio.open(output) as ds:
            block_h, block_w = ds.block_shapes[0]
            assert block_w == 256
            assert block_h == 256

    async def test_custom_compression(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output, compression="lzw")

        assert result.compression == "lzw"

    async def test_auto_output_path(self, strip_geotiff: Path) -> None:
        result = await convert_to_cog(str(strip_geotiff))
        expected = str(strip_geotiff.with_stem("strip_cog"))
        assert result.output == expected
        assert Path(expected).exists()

    async def test_file_size_recorded(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output)

        assert result.file_size_bytes is not None
        assert result.file_size_bytes > 0

    async def test_nonexistent_source_raises(self) -> None:
        with pytest.raises(RasterError, match="Failed to open"):
            await convert_to_cog("/nonexistent/file.tif")

    async def test_validates_as_cog(self, strip_geotiff: Path, tmp_path: Path) -> None:
        """Verify the output passes our own COG validation."""
        from earthforge.raster.validate import validate_cog

        output = str(tmp_path / "output.tif")
        await convert_to_cog(str(strip_geotiff), output=output)

        validation = await validate_cog(output)
        assert validation.is_valid

    async def test_json_serializable(self, strip_geotiff: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "output.tif")
        result = await convert_to_cog(str(strip_geotiff), output=output)

        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["width"] == 2048
