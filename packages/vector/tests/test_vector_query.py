"""Tests for vector spatial and attribute queries.

Uses synthetic GeoParquet files with WKB point geometries to test bbox
filtering, column selection, limit, and predicate pushdown behavior.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from earthforge.vector.errors import VectorError
from earthforge.vector.query import QueryResult, query_features


def _make_wkb_point(x: float, y: float) -> bytes:
    """Create a WKB Point geometry."""
    return b"\x01" + (1).to_bytes(4, "little") + struct.pack("<dd", x, y)


@pytest.fixture()
def geo_points(tmp_path: Path) -> Path:
    """GeoParquet with 6 points spread across Kentucky."""
    points = [
        (-84.5, 38.0),  # Frankfort area
        (-84.3, 38.1),  # Lexington area
        (-85.7, 38.2),  # Louisville area
        (-83.0, 38.4),  # Eastern KY
        (-84.5, 37.0),  # Southern KY
        (-88.0, 37.0),  # Western KY (Paducah)
    ]
    names = ["Frankfort", "Lexington", "Louisville", "Ashland", "Somerset", "Paducah"]
    populations = [28602, 322570, 633045, 20000, 11352, 27137]

    geo_metadata = {
        "version": "1.0.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": ["Point"],
                "crs": {
                    "type": "GeographicCRS",
                    "name": "WGS 84",
                    "id": {"authority": "EPSG", "code": 4326},
                },
                "bbox": [-88.0, 37.0, -83.0, 38.4],
            }
        },
    }

    table = pa.table(
        {
            "name": pa.array(names, type=pa.string()),
            "population": pa.array(populations, type=pa.int64()),
            "geometry": pa.array([_make_wkb_point(x, y) for x, y in points], type=pa.binary()),
        }
    )

    existing = table.schema.metadata or {}
    existing[b"geo"] = json.dumps(geo_metadata).encode()
    table = table.replace_schema_metadata(existing)

    path = tmp_path / "ky_cities.parquet"
    pq.write_table(table, str(path))
    return path


@pytest.fixture()
def plain_parquet(tmp_path: Path) -> Path:
    """Plain Parquet with no geometry — for testing non-geo queries."""
    table = pa.table(
        {
            "id": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
            "category": pa.array(["A", "B", "A", "C", "B"], type=pa.string()),
            "value": pa.array([10.0, 20.0, 30.0, 40.0, 50.0], type=pa.float64()),
        }
    )
    path = tmp_path / "data.parquet"
    pq.write_table(table, str(path))
    return path


class TestQueryFeatures:
    """Tests for spatial and attribute queries."""

    async def test_query_all_features(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points))
        assert isinstance(result, QueryResult)
        assert result.feature_count == 6
        assert result.total_rows == 6

    async def test_bbox_filter_reduces_results(self, geo_points: Path) -> None:
        # Bbox around Frankfort/Lexington area
        result = await query_features(str(geo_points), bbox=[-85.0, 37.9, -84.0, 38.2])
        # Should get Frankfort (-84.5, 38.0) and Lexington (-84.3, 38.1)
        assert result.feature_count == 2
        names = [f["name"] for f in result.features]
        assert "Frankfort" in names
        assert "Lexington" in names

    async def test_bbox_filter_empty_result(self, geo_points: Path) -> None:
        # Bbox in the ocean — no points
        result = await query_features(str(geo_points), bbox=[-90.0, 40.0, -89.0, 41.0])
        assert result.feature_count == 0
        assert result.features == []

    async def test_bbox_filter_recorded(self, geo_points: Path) -> None:
        bbox = [-85.0, 37.5, -84.0, 38.5]
        result = await query_features(str(geo_points), bbox=bbox)
        assert result.bbox_filter == bbox

    async def test_column_selection(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points), columns=["name", "population"])
        assert result.feature_count == 6
        # Should have name, population, and geometry_wkt
        for f in result.features:
            assert "name" in f
            assert "population" in f

    async def test_limit(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points), limit=3)
        assert result.feature_count == 3

    async def test_limit_with_bbox(self, geo_points: Path) -> None:
        result = await query_features(
            str(geo_points),
            bbox=[-86.0, 37.0, -83.0, 39.0],  # Most of KY
            limit=2,
        )
        assert result.feature_count == 2

    async def test_no_geometry_in_output(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points), include_geometry=False, limit=1)
        assert result.feature_count == 1
        feat = result.features[0]
        assert "geometry_wkt" not in feat
        assert "name" in feat

    async def test_geometry_as_wkt(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points), limit=1)
        feat = result.features[0]
        assert "geometry_wkt" in feat
        # Should be a WKT string like "POINT (-84.5 38.0)"
        assert feat["geometry_wkt"] is not None
        assert "POINT" in feat["geometry_wkt"]

    async def test_plain_parquet_query(self, plain_parquet: Path) -> None:
        result = await query_features(str(plain_parquet))
        assert result.feature_count == 5
        assert result.total_rows == 5

    async def test_source_recorded(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points))
        assert result.source == str(geo_points)

    async def test_total_rows_vs_filtered(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points), bbox=[-85.0, 37.9, -84.0, 38.2])
        assert result.total_rows == 6
        assert result.feature_count < result.total_rows

    async def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(VectorError, match="Failed to open"):
            await query_features("/nonexistent/file.parquet")

    async def test_json_serializable(self, geo_points: Path) -> None:
        result = await query_features(str(geo_points), limit=2)
        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["feature_count"] == 2
