"""Tests for GeoParquet validation module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from earthforge.vector.errors import VectorValidationError
from earthforge.vector.validate import VectorValidationResult, validate_geoparquet


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _write_geoparquet(path: Path, geo_meta: dict | None = None) -> None:
    """Write a minimal GeoParquet file with the given geo metadata."""
    # Create a simple table with a geometry column (WKB bytes)
    # A simple point WKB: POINT(0 0)
    wkb_point = bytes.fromhex("0101000000000000000000000000000000000000000000000000000000")

    geometry = pa.array([wkb_point, wkb_point], type=pa.binary())
    names = pa.array(["a", "b"], type=pa.string())

    table = pa.table({"geometry": geometry, "name": names})

    if geo_meta is not None:
        existing = table.schema.metadata or {}
        existing[b"geo"] = json.dumps(geo_meta).encode("utf-8")
        table = table.replace_schema_metadata(existing)

    pq.write_table(table, str(path))


class TestValidGeoParquet:
    """Tests for valid GeoParquet files."""

    def test_valid_geoparquet(self, tmp_path: Path) -> None:
        geo_meta = {
            "version": "1.1.0",
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
                    "bbox": [-180, -90, 180, 90],
                }
            },
        }
        path = tmp_path / "valid.parquet"
        _write_geoparquet(path, geo_meta)

        result = _run(validate_geoparquet(str(path)))

        assert isinstance(result, VectorValidationResult)
        assert result.is_valid is True
        assert result.geometry_column == "geometry"
        assert result.crs == "EPSG:4326"
        assert result.encoding == "WKB"
        assert "[PASS]" in result.summary

    def test_geoparquet_no_crs(self, tmp_path: Path) -> None:
        geo_meta = {
            "version": "1.0.0",
            "primary_column": "geometry",
            "columns": {
                "geometry": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                }
            },
        }
        path = tmp_path / "no_crs.parquet"
        _write_geoparquet(path, geo_meta)

        result = _run(validate_geoparquet(str(path)))

        assert result.is_valid is True
        assert result.crs == "OGC:CRS84"
        warn_checks = [c for c in result.checks if "[WARN]" in c.status]
        assert len(warn_checks) >= 1


class TestInvalidGeoParquet:
    """Tests for invalid or non-GeoParquet files."""

    def test_parquet_without_geo_metadata(self, tmp_path: Path) -> None:
        path = tmp_path / "plain.parquet"
        table = pa.table({"col": [1, 2, 3]})
        pq.write_table(table, str(path))

        result = _run(validate_geoparquet(str(path)))

        assert result.is_valid is False
        assert "[FAIL]" in result.summary

    def test_not_a_parquet_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.parquet"
        path.write_text("not a parquet file", encoding="utf-8")

        with pytest.raises(VectorValidationError, match="Cannot read Parquet"):
            _run(validate_geoparquet(str(path)))

    def test_missing_geometry_column_in_schema(self, tmp_path: Path) -> None:
        geo_meta = {
            "version": "1.0.0",
            "primary_column": "geom",
            "columns": {
                "geom": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                }
            },
        }
        path = tmp_path / "missing_col.parquet"
        _write_geoparquet(path, geo_meta)

        result = _run(validate_geoparquet(str(path)))

        assert result.is_valid is False
        fail_checks = [c for c in result.checks if "[FAIL]" in c.status]
        assert any("not found" in c.message for c in fail_checks)


class TestStatusMarkers:
    """Verify all check statuses include text markers."""

    def test_all_checks_have_text_markers(self, tmp_path: Path) -> None:
        geo_meta = {
            "version": "1.1.0",
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
                }
            },
        }
        path = tmp_path / "markers.parquet"
        _write_geoparquet(path, geo_meta)

        result = _run(validate_geoparquet(str(path)))

        for check in result.checks:
            assert any(
                marker in check.status
                for marker in ["[PASS]", "[FAIL]", "[WARN]", "[INFO]", "[SKIP]"]
            ), f"Check '{check.check}' missing text marker: {check.status}"
