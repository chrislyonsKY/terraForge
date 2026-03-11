"""Tests for vector info inspection.

Uses synthetic Parquet and GeoParquet files created with pyarrow to avoid
external test data dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from earthforge.vector.errors import VectorError
from earthforge.vector.info import VectorInfo, inspect_vector


@pytest.fixture()
def sample_parquet(tmp_path: Path) -> Path:
    """Create a minimal Parquet file (no geometry)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "name": pa.array(["a", "b", "c"], type=pa.string()),
            "value": pa.array([1.1, 2.2, 3.3], type=pa.float64()),
        }
    )
    path = tmp_path / "data.parquet"
    pq.write_table(table, str(path), compression="snappy")
    return path


@pytest.fixture()
def sample_geoparquet(tmp_path: Path) -> Path:
    """Create a minimal GeoParquet file with WKB geometry and geo metadata."""
    import struct

    import pyarrow as pa
    import pyarrow.parquet as pq

    # Create simple WKB points: POINT(x, y)
    # WKB format: byte_order(1) + type(4) + x(8) + y(8) = 21 bytes
    def make_wkb_point(x: float, y: float) -> bytes:
        return struct.pack("<BId", 1, 1, 0) + struct.pack("<dd", x, y)

    # Fix: WKB point is byte_order(1) + wkb_type(4) + x(8) + y(8)
    def make_wkb_point_correct(x: float, y: float) -> bytes:
        return b"\x01" + (1).to_bytes(4, "little") + struct.pack("<dd", x, y)

    points = [
        make_wkb_point_correct(-85.0, 37.0),
        make_wkb_point_correct(-84.5, 37.5),
        make_wkb_point_correct(-84.0, 38.0),
    ]

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
                "bbox": [-85.0, 37.0, -84.0, 38.0],
            }
        },
    }

    table = pa.table(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "name": pa.array(["alpha", "beta", "gamma"], type=pa.string()),
            "geometry": pa.array(points, type=pa.binary()),
        }
    )

    # Attach geo metadata to schema
    existing_meta = table.schema.metadata or {}
    existing_meta[b"geo"] = json.dumps(geo_metadata).encode("utf-8")
    table = table.replace_schema_metadata(existing_meta)

    path = tmp_path / "data.geoparquet"
    pq.write_table(table, str(path), compression="snappy")
    return path


class TestInspectVector:
    """Tests for vector metadata inspection."""

    async def test_basic_parquet(self, sample_parquet: Path) -> None:
        info = await inspect_vector(str(sample_parquet))
        assert isinstance(info, VectorInfo)
        assert info.row_count == 3
        assert info.num_columns == 3
        assert info.format == "parquet"
        assert info.geometry_column is None

    async def test_parquet_columns(self, sample_parquet: Path) -> None:
        info = await inspect_vector(str(sample_parquet))
        assert len(info.columns) == 3
        names = [c.name for c in info.columns]
        assert "id" in names
        assert "name" in names
        assert "value" in names
        assert all(not c.is_geometry for c in info.columns)

    async def test_parquet_compression(self, sample_parquet: Path) -> None:
        info = await inspect_vector(str(sample_parquet))
        assert info.compression is not None
        assert "SNAPPY" in info.compression.upper()

    async def test_parquet_row_groups(self, sample_parquet: Path) -> None:
        info = await inspect_vector(str(sample_parquet))
        assert info.num_row_groups is not None
        assert info.num_row_groups >= 1

    async def test_geoparquet_format(self, sample_geoparquet: Path) -> None:
        info = await inspect_vector(str(sample_geoparquet))
        assert info.format == "geoparquet"
        assert info.geometry_column == "geometry"

    async def test_geoparquet_crs(self, sample_geoparquet: Path) -> None:
        info = await inspect_vector(str(sample_geoparquet))
        assert info.crs is not None
        assert "EPSG" in info.crs
        assert "4326" in info.crs

    async def test_geoparquet_bbox(self, sample_geoparquet: Path) -> None:
        info = await inspect_vector(str(sample_geoparquet))
        assert info.bbox is not None
        assert len(info.bbox) == 4
        assert info.bbox[0] == pytest.approx(-85.0)
        assert info.bbox[3] == pytest.approx(38.0)

    async def test_geoparquet_geometry_types(self, sample_geoparquet: Path) -> None:
        info = await inspect_vector(str(sample_geoparquet))
        assert "Point" in info.geometry_types

    async def test_geoparquet_encoding(self, sample_geoparquet: Path) -> None:
        info = await inspect_vector(str(sample_geoparquet))
        assert info.encoding == "WKB"

    async def test_geoparquet_geometry_column_flagged(self, sample_geoparquet: Path) -> None:
        info = await inspect_vector(str(sample_geoparquet))
        geo_cols = [c for c in info.columns if c.is_geometry]
        assert len(geo_cols) == 1
        assert geo_cols[0].name == "geometry"

    async def test_file_size(self, sample_parquet: Path) -> None:
        info = await inspect_vector(str(sample_parquet))
        assert info.file_size_bytes is not None
        assert info.file_size_bytes > 0

    async def test_nonexistent_raises(self) -> None:
        with pytest.raises(VectorError, match="Failed to read"):
            await inspect_vector("/nonexistent/file.parquet")

    async def test_json_serializable(self, sample_geoparquet: Path) -> None:
        """VectorInfo must be JSON-serializable for --output json."""
        import json as json_mod

        info = await inspect_vector(str(sample_geoparquet))
        dumped = info.model_dump(mode="json")
        json_str = json_mod.dumps(dumped)
        parsed = json_mod.loads(json_str)
        assert parsed["row_count"] == 3
        assert parsed["format"] == "geoparquet"
