"""Tests for vector tile generation module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from earthforge.vector.errors import VectorError
from earthforge.vector.tile import VectorTileResult, generate_vector_tiles


def _run(coro):
    return asyncio.run(coro)


def _create_test_geoparquet(path: Path, n: int = 20) -> None:
    """Create a test GeoParquet file with random points."""
    points = [Point(np.random.uniform(-180, 180), np.random.uniform(-85, 85)) for _ in range(n)]
    gdf = gpd.GeoDataFrame(
        {"id": range(n), "name": [f"feature_{i}" for i in range(n)]},
        geometry=points,
        crs="EPSG:4326",
    )
    gdf.to_parquet(str(path))


class TestGenerateVectorTiles:
    def test_generates_output(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(
            generate_vector_tiles(
                str(src),
                str(tmp_path / "tiles.pmtiles"),
                min_zoom=0,
                max_zoom=2,
            )
        )

        assert isinstance(result, VectorTileResult)
        assert result.feature_count == 20
        assert result.output_format == "PMTiles"
        assert Path(result.output).exists()
        assert result.file_size_bytes > 0

    def test_custom_layer_name(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(
            generate_vector_tiles(
                str(src),
                str(tmp_path / "tiles.pmtiles"),
                layer_name="buildings",
                min_zoom=0,
                max_zoom=1,
            )
        )

        assert result.feature_count == 20

    def test_zoom_range_in_result(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(
            generate_vector_tiles(
                str(src),
                str(tmp_path / "tiles.pmtiles"),
                min_zoom=2,
                max_zoom=8,
            )
        )

        assert result.zoom_range == "2-8"


class TestErrors:
    def test_nonexistent_source(self, tmp_path: Path) -> None:
        with pytest.raises(VectorError, match="Failed to read"):
            _run(
                generate_vector_tiles(
                    "/nonexistent.parquet",
                    str(tmp_path / "tiles.pmtiles"),
                )
            )
