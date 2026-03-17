"""Tests for raster band math calculator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from earthforge.raster.calc import RasterCalcResult, raster_calc
from earthforge.raster.errors import RasterError


def _run(coro):
    return asyncio.run(coro)


def _create_band(path: Path, values: np.ndarray) -> None:
    """Create a single-band GeoTIFF with the given values."""
    transform = from_bounds(
        0, 0, values.shape[1], values.shape[0],
        values.shape[1], values.shape[0],
    )
    with rasterio.open(
        str(path), "w", driver="GTiff",
        height=values.shape[0], width=values.shape[1],
        count=1, dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(values.astype(np.float32), 1)


class TestRasterCalc:
    def test_simple_addition(self, tmp_path: Path) -> None:
        a = np.ones((3, 3), dtype=np.float32) * 10
        b = np.ones((3, 3), dtype=np.float32) * 5
        _create_band(tmp_path / "a.tif", a)
        _create_band(tmp_path / "b.tif", b)

        result = _run(raster_calc(
            "A + B",
            {"A": str(tmp_path / "a.tif"), "B": str(tmp_path / "b.tif")},
            str(tmp_path / "out.tif"),
        ))

        assert isinstance(result, RasterCalcResult)
        assert result.expression == "A + B"
        assert Path(result.output).exists()

        with rasterio.open(result.output) as src:
            data = src.read(1)
        np.testing.assert_array_almost_equal(data, 15.0)

    def test_ndvi(self, tmp_path: Path) -> None:
        nir = np.full((4, 4), 0.8, dtype=np.float32)
        red = np.full((4, 4), 0.2, dtype=np.float32)
        _create_band(tmp_path / "nir.tif", nir)
        _create_band(tmp_path / "red.tif", red)

        result = _run(raster_calc(
            "(B08 - B04) / (B08 + B04)",
            {"B08": str(tmp_path / "nir.tif"), "B04": str(tmp_path / "red.tif")},
            str(tmp_path / "ndvi.tif"),
        ))

        with rasterio.open(result.output) as src:
            data = src.read(1)
        np.testing.assert_array_almost_equal(data, 0.6, decimal=5)

    def test_output_metadata(self, tmp_path: Path) -> None:
        a = np.ones((3, 3), dtype=np.float32)
        _create_band(tmp_path / "a.tif", a)

        result = _run(raster_calc(
            "A * 2",
            {"A": str(tmp_path / "a.tif")},
            str(tmp_path / "out.tif"),
        ))

        assert result.width == 3
        assert result.height == 3
        assert result.dtype == "float32"
        assert result.crs == "EPSG:4326"
        assert result.file_size_bytes > 0


class TestErrors:
    def test_invalid_expression(self, tmp_path: Path) -> None:
        a = np.ones((3, 3), dtype=np.float32)
        _create_band(tmp_path / "a.tif", a)

        with pytest.raises(RasterError, match="Invalid expression"):
            _run(raster_calc("A +", {"A": str(tmp_path / "a.tif")}, str(tmp_path / "out.tif")))

    def test_missing_input(self, tmp_path: Path) -> None:
        a = np.ones((3, 3), dtype=np.float32)
        _create_band(tmp_path / "a.tif", a)

        with pytest.raises(RasterError, match="undefined variables"):
            _run(raster_calc("A + B", {"A": str(tmp_path / "a.tif")}, str(tmp_path / "out.tif")))

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        with pytest.raises(RasterError, match="Failed to read"):
            _run(raster_calc("A + 1", {"A": "/nonexistent.tif"}, str(tmp_path / "out.tif")))
