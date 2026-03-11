"""Tests for raster preview generation.

Uses synthetic GeoTIFFs created with rasterio to verify PNG quicklook output.
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
from earthforge.raster.preview import PreviewResult, generate_preview


@pytest.fixture()
def rgb_geotiff(tmp_path: Path) -> Path:
    """Create a 3-band GeoTIFF for preview testing."""
    path = tmp_path / "rgb.tif"
    width, height = 128, 128
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
            ds.write(
                np.random.randint(0, 255, (height, width), dtype=np.uint8), i
            )

    return path


@pytest.fixture()
def single_band_geotiff(tmp_path: Path) -> Path:
    """Create a single-band float32 GeoTIFF."""
    path = tmp_path / "dem.tif"
    width, height = 64, 64
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
        ds.write(
            np.random.rand(height, width).astype(np.float32) * 1000, 1
        )

    return path


class TestGeneratePreview:
    """Tests for PNG quicklook generation."""

    async def test_rgb_preview(
        self, rgb_geotiff: Path, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.png")
        result = await generate_preview(str(rgb_geotiff), output_path=out)

        assert isinstance(result, PreviewResult)
        assert Path(result.output_path).exists()
        assert result.bands_used == 3
        assert result.width > 0
        assert result.height > 0

    async def test_single_band_preview(
        self, single_band_geotiff: Path, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.png")
        result = await generate_preview(
            str(single_band_geotiff), output_path=out
        )

        assert result.bands_used == 1
        assert Path(result.output_path).exists()

    async def test_max_size_constrains_output(
        self, rgb_geotiff: Path, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "small.png")
        result = await generate_preview(
            str(rgb_geotiff), output_path=out, max_size=32
        )

        assert result.width <= 32
        assert result.height <= 32

    async def test_auto_output_path(
        self, rgb_geotiff: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(rgb_geotiff.parent)
        result = await generate_preview(str(rgb_geotiff))

        assert result.output_path == "rgb_preview.png"
        assert Path(rgb_geotiff.parent / "rgb_preview.png").exists()

    async def test_source_recorded(
        self, rgb_geotiff: Path, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.png")
        result = await generate_preview(str(rgb_geotiff), output_path=out)
        assert result.source == str(rgb_geotiff)

    async def test_output_is_valid_png(
        self, rgb_geotiff: Path, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.png")
        await generate_preview(str(rgb_geotiff), output_path=out)

        # Verify it's a valid raster file readable by rasterio
        with rasterio.open(out) as ds:
            assert ds.driver == "PNG"
            assert ds.count == 3

    async def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(RasterError, match="Failed to open"):
            await generate_preview("/nonexistent/path.tif")

    async def test_json_serializable(
        self, rgb_geotiff: Path, tmp_path: Path
    ) -> None:
        import json

        out = str(tmp_path / "out.png")
        result = await generate_preview(str(rgb_geotiff), output_path=out)
        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["source"] == str(rgb_geotiff)
