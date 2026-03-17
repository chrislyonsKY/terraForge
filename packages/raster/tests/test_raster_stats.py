"""Tests for raster statistics module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from earthforge.raster.errors import RasterError
from earthforge.raster.stats import RasterStatsResult, compute_stats


def _run(coro):
    return asyncio.run(coro)


def _create_test_raster(path: Path, *, nodata: float | None = None) -> None:
    """Create a simple test GeoTIFF."""
    data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]], dtype=np.float32)
    transform = from_bounds(0, 0, 3, 3, 3, 3)
    with rasterio.open(
        str(path), "w", driver="GTiff", height=3, width=3,
        count=1, dtype="float32", crs="EPSG:4326", transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)


def _create_multiband_raster(path: Path) -> None:
    """Create a 2-band test GeoTIFF."""
    data1 = np.ones((3, 3), dtype=np.float32) * 10.0
    data2 = np.ones((3, 3), dtype=np.float32) * 20.0
    transform = from_bounds(0, 0, 3, 3, 3, 3)
    with rasterio.open(
        str(path), "w", driver="GTiff", height=3, width=3,
        count=2, dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data1, 1)
        dst.write(data2, 2)


class TestGlobalStats:
    def test_basic_stats(self, tmp_path: Path) -> None:
        path = tmp_path / "test.tif"
        _create_test_raster(path)

        result = _run(compute_stats(str(path)))

        assert isinstance(result, RasterStatsResult)
        assert result.band_count == 1
        assert result.width == 3
        assert result.height == 3
        assert result.crs == "EPSG:4326"
        assert result.is_zonal is False

        band = result.bands[0]
        assert band.band == 1
        assert band.min == 1.0
        assert band.max == 9.0
        assert abs(band.mean - 5.0) < 0.01
        assert band.valid_pixels == 9

    def test_multiband(self, tmp_path: Path) -> None:
        path = tmp_path / "multi.tif"
        _create_multiband_raster(path)

        result = _run(compute_stats(str(path)))

        assert len(result.bands) == 2
        assert result.bands[0].mean == 10.0
        assert result.bands[1].mean == 20.0

    def test_specific_bands(self, tmp_path: Path) -> None:
        path = tmp_path / "multi.tif"
        _create_multiband_raster(path)

        result = _run(compute_stats(str(path), bands=[2]))

        assert len(result.bands) == 1
        assert result.bands[0].band == 2
        assert result.bands[0].mean == 20.0

    def test_histogram(self, tmp_path: Path) -> None:
        path = tmp_path / "test.tif"
        _create_test_raster(path)

        result = _run(compute_stats(str(path), histogram_bins=10))

        band = result.bands[0]
        assert len(band.histogram_counts) == 10
        assert len(band.histogram_edges) == 11
        assert sum(band.histogram_counts) == 9


class TestNodata:
    def test_nodata_handling(self, tmp_path: Path) -> None:
        path = tmp_path / "nodata.tif"
        data = np.array(
            [[1.0, -9999.0, 3.0], [4.0, 5.0, -9999.0], [7.0, 8.0, 9.0]],
            dtype=np.float32,
        )
        transform = from_bounds(0, 0, 3, 3, 3, 3)
        with rasterio.open(
            str(path), "w", driver="GTiff", height=3, width=3,
            count=1, dtype="float32", crs="EPSG:4326", transform=transform,
            nodata=-9999.0,
        ) as dst:
            dst.write(data, 1)

        result = _run(compute_stats(str(path)))
        band = result.bands[0]
        assert band.valid_pixels == 7
        assert band.nodata_pixels == 2
        assert band.min == 1.0
        assert band.max == 9.0


class TestErrors:
    def test_nonexistent_file(self) -> None:
        with pytest.raises(RasterError):
            _run(compute_stats("/nonexistent/file.tif"))

    def test_invalid_band(self, tmp_path: Path) -> None:
        path = tmp_path / "test.tif"
        _create_test_raster(path)

        with pytest.raises(RasterError, match="out of range"):
            _run(compute_stats(str(path), bands=[5]))
