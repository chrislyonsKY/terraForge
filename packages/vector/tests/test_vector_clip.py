"""Tests for vector clip module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from earthforge.vector.clip import ClipResult, clip_features
from earthforge.vector.errors import VectorError


def _run(coro):
    return asyncio.run(coro)


def _create_test_geoparquet(path: Path) -> None:
    """Create a GeoParquet with scattered points."""
    points = [Point(x, y) for x in range(-90, -80) for y in range(30, 40)]
    gdf = gpd.GeoDataFrame(
        {"id": range(len(points)), "value": np.random.rand(len(points))},
        geometry=points,
        crs="EPSG:4326",
    )
    gdf.to_parquet(str(path))


class TestClipByBbox:
    def test_clip_reduces_features(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(
            clip_features(
                str(src),
                str(tmp_path / "clipped.parquet"),
                bbox=(-86, 34, -84, 36),
            )
        )

        assert isinstance(result, ClipResult)
        assert result.features_output < result.features_input
        assert result.clip_method == "bbox"
        assert Path(result.output).exists()

    def test_clip_all_inside(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(
            clip_features(
                str(src),
                str(tmp_path / "clipped.parquet"),
                bbox=(-100, 20, -70, 50),
            )
        )

        assert result.features_output == result.features_input

    def test_clip_none_inside(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(
            clip_features(
                str(src),
                str(tmp_path / "clipped.parquet"),
                bbox=(0, 0, 1, 1),
            )
        )

        assert result.features_output == 0


class TestClipByGeometry:
    def test_clip_with_wkt(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        wkt = "POLYGON((-86 34, -84 34, -84 36, -86 36, -86 34))"
        result = _run(
            clip_features(
                str(src),
                str(tmp_path / "clipped.parquet"),
                geometry_wkt=wkt,
            )
        )

        assert result.clip_method == "geometry"
        assert result.features_output < result.features_input


class TestDefaults:
    def test_default_output_name(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        result = _run(clip_features(str(src), bbox=(-86, 34, -84, 36)))

        assert "clipped" in result.output


class TestErrors:
    def test_no_clip_region(self, tmp_path: Path) -> None:
        src = tmp_path / "points.parquet"
        _create_test_geoparquet(src)

        with pytest.raises(VectorError, match="Either bbox or geometry_wkt"):
            _run(clip_features(str(src), str(tmp_path / "out.parquet")))

    def test_nonexistent_source(self, tmp_path: Path) -> None:
        with pytest.raises(VectorError, match="Failed to read"):
            _run(
                clip_features(
                    "/nonexistent.parquet",
                    str(tmp_path / "out.parquet"),
                    bbox=(0, 0, 1, 1),
                )
            )
