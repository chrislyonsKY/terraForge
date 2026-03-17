"""Tests for raster tile generation module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from earthforge.raster.errors import RasterError
from earthforge.raster.tile import TileResult, _lng_lat_to_tile, _tile_bounds, generate_tiles


def _run(coro):
    return asyncio.run(coro)


def _create_test_raster(path: Path) -> None:
    """Create a small global-extent test raster."""
    data = np.random.randint(0, 1000, (64, 128), dtype=np.int16).astype(np.float32)
    transform = from_bounds(-180, -85, 180, 85, 128, 64)
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=64,
        width=128,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)


class TestTileMath:
    """Tests for inline tile math functions."""

    def test_origin_tile(self) -> None:
        x, y = _lng_lat_to_tile(-180.0, 85.0, 0)
        assert x == 0
        assert y == 0

    def test_tile_bounds_zoom_0(self) -> None:
        west, _south, east, north = _tile_bounds(0, 0, 0)
        assert west == -180.0
        assert east == 180.0
        assert north > 80  # Web Mercator clamps at ~85.05

    def test_tile_bounds_symmetry(self) -> None:
        """Tile at (0,0,1) should cover the NW quadrant."""
        w, _s, e, n = _tile_bounds(0, 0, 1)
        assert w == -180.0
        assert e == 0.0
        assert n > 0

    def test_zoom_2_quadrants(self) -> None:
        """At zoom 2, there should be 4x4 = 16 tiles."""
        n = 2**2
        for x in range(n):
            for y in range(n):
                w, s, e, nn = _tile_bounds(x, y, 2)
                assert w < e
                assert s < nn


class TestGenerateTiles:
    """Tests for tile generation."""

    def test_generates_tiles(self, tmp_path: Path) -> None:
        raster_path = tmp_path / "global.tif"
        _create_test_raster(raster_path)

        result = _run(
            generate_tiles(
                str(raster_path),
                str(tmp_path / "tiles"),
                zoom_range=(0, 1),
                tile_size=64,
            )
        )

        assert isinstance(result, TileResult)
        assert result.tile_count > 0
        assert result.zoom_min == 0
        assert result.zoom_max == 1
        assert result.tile_size == 64

    def test_tiles_are_png(self, tmp_path: Path) -> None:
        raster_path = tmp_path / "global.tif"
        _create_test_raster(raster_path)

        _run(
            generate_tiles(
                str(raster_path),
                str(tmp_path / "tiles"),
                zoom_range=(0, 0),
                tile_size=64,
            )
        )

        # Check z/x/y.png structure
        tile_file = tmp_path / "tiles" / "0" / "0" / "0.png"
        assert tile_file.exists()
        # Verify it's a valid PNG
        with open(tile_file, "rb") as f:
            header = f.read(4)
        assert header[:4] == b"\x89PNG"

    def test_output_dir_created(self, tmp_path: Path) -> None:
        raster_path = tmp_path / "global.tif"
        _create_test_raster(raster_path)

        out = tmp_path / "nested" / "tiles"
        _run(
            generate_tiles(
                str(raster_path),
                str(out),
                zoom_range=(0, 0),
                tile_size=64,
            )
        )

        assert out.exists()


class TestErrors:
    def test_nonexistent_source(self, tmp_path: Path) -> None:
        with pytest.raises(RasterError):
            _run(generate_tiles("/nonexistent.tif", str(tmp_path / "tiles")))
