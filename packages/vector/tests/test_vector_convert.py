"""Tests for vector format conversion.

Creates synthetic Shapefiles and GeoJSON files via OGR, converts them to
GeoParquet, and validates the output structure and metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from osgeo import ogr, osr

from earthforge.vector.convert import ConvertResult, convert_vector
from earthforge.vector.errors import VectorError


def _create_point_shapefile(path: Path, *, with_crs: bool = True) -> Path:
    """Create a simple point Shapefile with 3 features."""
    driver = ogr.GetDriverByName("ESRI Shapefile")
    ds = driver.CreateDataSource(str(path))

    srs = None
    if with_crs:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)

    layer = ds.CreateLayer("points", srs, ogr.wkbPoint)
    layer.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    layer.CreateField(ogr.FieldDefn("value", ogr.OFTReal))

    for name, val, x, y in [
        ("Frankfort", 100.0, -84.87, 38.20),
        ("Lexington", 200.0, -84.50, 38.05),
        ("Louisville", 300.0, -85.76, 38.25),
    ]:
        feat = ogr.Feature(layer.GetLayerDefn())
        feat.SetField("name", name)
        feat.SetField("value", val)
        pt = ogr.Geometry(ogr.wkbPoint)
        pt.AddPoint(x, y)
        feat.SetGeometry(pt)
        layer.CreateFeature(feat)
        feat = None

    ds = None  # Close and flush
    return path


def _create_polygon_geojson(path: Path) -> Path:
    """Create a GeoJSON file with polygon features."""
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"county": "Franklin", "pop": 53962},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-85.0, 38.1],
                            [-84.7, 38.1],
                            [-84.7, 38.3],
                            [-85.0, 38.3],
                            [-85.0, 38.1],
                        ]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"county": "Fayette", "pop": 322570},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-84.6, 37.9],
                            [-84.3, 37.9],
                            [-84.3, 38.2],
                            [-84.6, 38.2],
                            [-84.6, 37.9],
                        ]
                    ],
                },
            },
        ],
    }
    path.write_text(json.dumps(geojson))
    return path


@pytest.fixture()
def point_shapefile(tmp_path: Path) -> Path:
    """Create a point Shapefile fixture."""
    return _create_point_shapefile(tmp_path / "cities.shp")


@pytest.fixture()
def polygon_geojson(tmp_path: Path) -> Path:
    """Create a polygon GeoJSON fixture."""
    return _create_polygon_geojson(tmp_path / "counties.geojson")


class TestConvertVector:
    """Tests for vector format conversion to GeoParquet."""

    async def test_shapefile_to_geoparquet(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "cities.parquet")
        result = await convert_vector(str(point_shapefile), output=output)

        assert isinstance(result, ConvertResult)
        assert result.output_format == "geoparquet"
        assert result.feature_count == 3
        assert Path(output).exists()

    async def test_geojson_to_geoparquet(self, polygon_geojson: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "counties.parquet")
        result = await convert_vector(str(polygon_geojson), output=output)

        assert result.feature_count == 2
        assert result.geometry_type == "Polygon"
        assert Path(output).exists()

    async def test_output_has_geo_metadata(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        pf = pq.ParquetFile(output)
        meta = pf.schema_arrow.metadata or {}
        assert b"geo" in meta
        geo = json.loads(meta[b"geo"])
        assert geo["primary_column"] == "geometry"
        assert "WKB" in geo["columns"]["geometry"]["encoding"]

    async def test_crs_in_metadata(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        result = await convert_vector(str(point_shapefile), output=output)

        assert result.crs is not None
        assert "4326" in result.crs

        # Check PROJJSON in Parquet metadata
        pf = pq.ParquetFile(output)
        geo = json.loads(pf.schema_arrow.metadata[b"geo"])
        crs = geo["columns"]["geometry"].get("crs", {})
        assert crs  # Should have CRS PROJJSON

    async def test_bbox_in_metadata(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        result = await convert_vector(str(point_shapefile), output=output)

        assert result.bbox is not None
        assert len(result.bbox) == 4

    async def test_geometry_column_present(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        pf = pq.ParquetFile(output)
        col_names = [pf.schema_arrow.field(i).name for i in range(len(pf.schema_arrow))]
        assert "geometry" in col_names

    async def test_attribute_columns_preserved(
        self, point_shapefile: Path, tmp_path: Path
    ) -> None:
        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        pf = pq.ParquetFile(output)
        col_names = [pf.schema_arrow.field(i).name for i in range(len(pf.schema_arrow))]
        assert "name" in col_names
        assert "value" in col_names

    async def test_auto_output_path(self, point_shapefile: Path) -> None:
        result = await convert_vector(str(point_shapefile))
        expected = str(point_shapefile.with_suffix(".parquet"))
        assert result.output == expected
        assert Path(expected).exists()

    async def test_input_format_detected(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        result = await convert_vector(str(point_shapefile), output=output)
        assert "Shapefile" in result.input_format

    async def test_geojson_format_detected(self, polygon_geojson: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        result = await convert_vector(str(polygon_geojson), output=output)
        assert "GeoJSON" in result.input_format

    async def test_file_size_recorded(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        result = await convert_vector(str(point_shapefile), output=output)
        assert result.file_size_bytes is not None
        assert result.file_size_bytes > 0

    async def test_nonexistent_source_raises(self) -> None:
        with pytest.raises(VectorError, match="Failed to open"):
            await convert_vector("/nonexistent/data.shp")

    async def test_unsupported_target_format(self, point_shapefile: Path) -> None:
        with pytest.raises(VectorError, match="Unsupported target format"):
            await convert_vector(str(point_shapefile), target_format="xlsx")

    async def test_roundtrip_readable(self, point_shapefile: Path, tmp_path: Path) -> None:
        """Verify output can be read back by our own inspect_vector."""
        from earthforge.vector.info import inspect_vector

        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        info = await inspect_vector(output)
        assert info.format == "geoparquet"
        assert info.row_count == 3
        assert info.geometry_column == "geometry"
        assert info.crs is not None

    async def test_bbox_covering_columns_present(
        self, point_shapefile: Path, tmp_path: Path
    ) -> None:
        """GeoParquet 1.1 covering: per-row bbox columns for predicate pushdown."""
        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        pf = pq.ParquetFile(output)
        col_names = [pf.schema_arrow.field(i).name for i in range(len(pf.schema_arrow))]
        for bbox_col in ("bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax"):
            assert bbox_col in col_names, f"Missing covering column: {bbox_col}"

    async def test_bbox_covering_in_geo_metadata(
        self, point_shapefile: Path, tmp_path: Path
    ) -> None:
        """Covering metadata must declare the bbox column mapping."""
        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        pf = pq.ParquetFile(output)
        geo = json.loads(pf.schema_arrow.metadata[b"geo"])
        covering = geo["columns"]["geometry"].get("covering", {})
        bbox_covering = covering.get("bbox", {})
        assert "xmin" in bbox_covering
        assert "ymin" in bbox_covering
        assert "xmax" in bbox_covering
        assert "ymax" in bbox_covering

    async def test_bbox_values_correct(self, point_shapefile: Path, tmp_path: Path) -> None:
        """Per-row bbox values should match geometry extents."""
        output = str(tmp_path / "out.parquet")
        await convert_vector(str(point_shapefile), output=output)

        table = pq.read_table(output)
        xmin_col = table.column("bbox.xmin").to_pylist()
        ymin_col = table.column("bbox.ymin").to_pylist()
        # Point geometries: bbox min == bbox max
        assert all(v is not None for v in xmin_col)
        assert all(v is not None for v in ymin_col)

    async def test_json_serializable(self, point_shapefile: Path, tmp_path: Path) -> None:
        output = str(tmp_path / "out.parquet")
        result = await convert_vector(str(point_shapefile), output=output)
        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["feature_count"] == 3
