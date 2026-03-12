"""Vector format conversion.

Converts between vector geospatial formats with a focus on producing valid
GeoParquet output. Supports Shapefile, GeoJSON, and other OGR-readable
formats as input. Writes GeoParquet with proper ``geo`` metadata including
CRS, geometry types, encoding, and bounding box.

Uses GDAL/OGR for reading source formats and pyarrow for writing Parquet.
Falls back to geopandas if available, but does not require it.

Usage::

    from earthforge.vector.convert import convert_vector

    result = await convert_vector("buildings.shp", output="buildings.parquet")
"""

from __future__ import annotations

import asyncio
import json
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from earthforge.vector.errors import VectorError


class ConvertResult(BaseModel):
    """Structured result from a vector format conversion.

    Attributes:
        source: Input file path.
        output: Output file path.
        input_format: Source format name (e.g. ``"ESRI Shapefile"``).
        output_format: Target format (e.g. ``"geoparquet"``).
        feature_count: Number of features converted.
        geometry_type: Geometry type (e.g. ``"Polygon"``).
        crs: CRS identifier string.
        bbox: Bounding box ``[west, south, east, north]``.
        file_size_bytes: Output file size in bytes.
    """

    source: str = Field(title="Source")
    output: str = Field(title="Output")
    input_format: str = Field(title="Input Format")
    output_format: str = Field(title="Output Format")
    feature_count: int = Field(title="Features")
    geometry_type: str | None = Field(default=None, title="Geometry Type")
    crs: str | None = Field(default=None, title="CRS")
    bbox: list[float] | None = Field(default=None, title="BBox")
    file_size_bytes: int | None = Field(default=None, title="Size (bytes)")


def _ogr_type_to_arrow(ogr_type: int) -> str:
    """Map an OGR field type to a pyarrow type string.

    Parameters:
        ogr_type: OGR field type constant.

    Returns:
        Arrow type name string.
    """
    from osgeo import ogr

    mapping = {
        ogr.OFTInteger: "int32",
        ogr.OFTInteger64: "int64",
        ogr.OFTReal: "float64",
        ogr.OFTString: "string",
        ogr.OFTDate: "string",
        ogr.OFTDateTime: "string",
        ogr.OFTBinary: "binary",
    }
    return mapping.get(ogr_type, "string")


def _ogr_geom_type_name(ogr_geom_type: int) -> str:
    """Convert OGR geometry type constant to human-readable name.

    Parameters:
        ogr_geom_type: OGR geometry type constant.

    Returns:
        Geometry type name.
    """
    from osgeo import ogr

    mapping = {
        ogr.wkbPoint: "Point",
        ogr.wkbLineString: "LineString",
        ogr.wkbPolygon: "Polygon",
        ogr.wkbMultiPoint: "MultiPoint",
        ogr.wkbMultiLineString: "MultiLineString",
        ogr.wkbMultiPolygon: "MultiPolygon",
        ogr.wkbGeometryCollection: "GeometryCollection",
        ogr.wkbPoint25D: "Point",
        ogr.wkbLineString25D: "LineString",
        ogr.wkbPolygon25D: "Polygon",
        ogr.wkbMultiPoint25D: "MultiPoint",
        ogr.wkbMultiLineString25D: "MultiLineString",
        ogr.wkbMultiPolygon25D: "MultiPolygon",
    }
    return mapping.get(ogr_geom_type, "Unknown")


def _extract_crs_info(spatial_ref: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Extract CRS identifier and PROJJSON from an OGR SpatialReference.

    Parameters:
        spatial_ref: OGR SpatialReference object.

    Returns:
        Tuple of (crs_string, projjson_dict).
    """
    if spatial_ref is None:
        return None, None

    # Try to get authority:code
    auth_name = spatial_ref.GetAuthorityName(None)
    auth_code = spatial_ref.GetAuthorityCode(None)
    crs_string = f"{auth_name}:{auth_code}" if auth_name and auth_code else None

    # Build PROJJSON for GeoParquet metadata
    projjson: dict[str, Any] | None = None
    try:
        projjson_str = spatial_ref.ExportToPROJJSON()
        if projjson_str:
            projjson = json.loads(projjson_str)
    except Exception:
        # Fall back to building minimal PROJJSON
        if crs_string:
            projjson = {
                "type": "GeographicCRS" if spatial_ref.IsGeographic() else "ProjectedCRS",
                "name": spatial_ref.GetName() or crs_string,
                "id": {"authority": auth_name, "code": int(auth_code) if auth_code else 0},
            }

    if crs_string is None and spatial_ref.GetName():
        crs_string = spatial_ref.GetName()

    return crs_string, projjson


def _convert_vector_sync(
    source: str,
    *,
    output: str | None = None,
    target_format: str = "geoparquet",
    compression: str = "snappy",
) -> ConvertResult:
    """Convert a vector file to GeoParquet synchronously.

    Parameters:
        source: Path to the input vector file (Shapefile, GeoJSON, etc.).
        output: Output file path. If ``None``, derives from source name.
        target_format: Target format (currently only ``"geoparquet"``).
        compression: Parquet compression codec (``"snappy"``, ``"zstd"``, ``"gzip"``).

    Returns:
        Structured conversion result.

    Raises:
        VectorError: If the source cannot be read or conversion fails.
    """
    if target_format != "geoparquet":
        raise VectorError(f"Unsupported target format: {target_format}")

    try:
        from osgeo import ogr
    except ImportError as exc:
        raise VectorError(
            "GDAL/OGR is required for vector conversion: install GDAL Python bindings"
        ) from exc

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise VectorError(
            "pyarrow is required for GeoParquet output: pip install earthforge[vector]"
        ) from exc

    # Open source
    try:
        ds = ogr.Open(source)
    except RuntimeError as exc:
        raise VectorError(f"Failed to open vector file '{source}'") from exc
    if ds is None:
        raise VectorError(f"Failed to open vector file '{source}'")

    layer = ds.GetLayer(0)
    if layer is None:
        raise VectorError(f"No layers found in '{source}'")

    input_format = ds.GetDriver().GetName()
    layer_defn = layer.GetLayerDefn()
    feature_count = layer.GetFeatureCount()
    geom_type = _ogr_geom_type_name(layer.GetGeomType())

    # Extract CRS
    spatial_ref = layer.GetSpatialRef()
    crs_string, projjson = _extract_crs_info(spatial_ref)

    # Get extent
    extent = layer.GetExtent()  # (xmin, xmax, ymin, ymax)
    bbox = [extent[0], extent[2], extent[1], extent[3]] if extent else None

    # Build field definitions
    field_names: list[str] = []
    field_types: list[str] = []
    for i in range(layer_defn.GetFieldCount()):
        field_def = layer_defn.GetFieldDefn(i)
        field_names.append(field_def.GetName())
        field_types.append(_ogr_type_to_arrow(field_def.GetType()))

    # Read all features
    arrays: dict[str, list[Any]] = {name: [] for name in field_names}
    geometries: list[bytes | None] = []
    bbox_xmin: list[float | None] = []
    bbox_ymin: list[float | None] = []
    bbox_xmax: list[float | None] = []
    bbox_ymax: list[float | None] = []

    layer.ResetReading()
    feature = layer.GetNextFeature()
    actual_count = 0
    while feature is not None:
        # Read attribute fields
        for i, name in enumerate(field_names):
            if not feature.IsFieldSet(i) or feature.IsFieldNull(i):
                arrays[name].append(None)
            elif field_types[i] == "int32":
                arrays[name].append(feature.GetFieldAsInteger(i))
            elif field_types[i] == "int64":
                arrays[name].append(feature.GetFieldAsInteger64(i))
            elif field_types[i] == "float64":
                arrays[name].append(feature.GetFieldAsDouble(i))
            else:
                arrays[name].append(feature.GetFieldAsString(i))

        # Read geometry as WKB and extract per-row bbox
        geom = feature.GetGeometryRef()
        if geom is not None:
            geometries.append(bytes(geom.ExportToWkb()))
            env = geom.GetEnvelope()  # (xmin, xmax, ymin, ymax)
            bbox_xmin.append(env[0])
            bbox_ymin.append(env[2])
            bbox_xmax.append(env[1])
            bbox_ymax.append(env[3])
        else:
            geometries.append(None)
            bbox_xmin.append(None)
            bbox_ymin.append(None)
            bbox_xmax.append(None)
            bbox_ymax.append(None)

        actual_count += 1
        feature = layer.GetNextFeature()

    ds = None  # Close OGR dataset

    if feature_count < 0:
        feature_count = actual_count

    # Build pyarrow table
    pa_columns: dict[str, Any] = {}
    for name, arrow_type in zip(field_names, field_types, strict=True):
        type_map = {
            "int32": pa.int32(),
            "int64": pa.int64(),
            "float64": pa.float64(),
            "string": pa.string(),
            "binary": pa.binary(),
        }
        pa_type = type_map.get(arrow_type, pa.string())
        pa_columns[name] = pa.array(arrays[name], type=pa_type)

    pa_columns["geometry"] = pa.array(geometries, type=pa.binary())

    # Per-row bounding box columns for predicate pushdown (GeoParquet 1.1 covering)
    pa_columns["bbox.xmin"] = pa.array(bbox_xmin, type=pa.float64())
    pa_columns["bbox.ymin"] = pa.array(bbox_ymin, type=pa.float64())
    pa_columns["bbox.xmax"] = pa.array(bbox_xmax, type=pa.float64())
    pa_columns["bbox.ymax"] = pa.array(bbox_ymax, type=pa.float64())

    table = pa.table(pa_columns)

    # Build GeoParquet metadata
    geo_metadata: dict[str, Any] = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": [geom_type],
                "covering": {
                    "bbox": {
                        "xmin": ["bbox.xmin"],
                        "ymin": ["bbox.ymin"],
                        "xmax": ["bbox.xmax"],
                        "ymax": ["bbox.ymax"],
                    }
                },
            }
        },
    }

    if bbox:
        geo_metadata["columns"]["geometry"]["bbox"] = bbox
    if projjson:
        geo_metadata["columns"]["geometry"]["crs"] = projjson

    # Attach geo metadata to schema
    existing = table.schema.metadata or {}
    existing[b"geo"] = json.dumps(geo_metadata).encode("utf-8")
    table = table.replace_schema_metadata(existing)

    # Determine output path
    if output is None:
        output = str(Path(source).with_suffix(".parquet"))

    # Write GeoParquet with row group size optimized for spatial queries.
    # 128MB row groups balance between spatial locality and I/O efficiency.
    try:
        pq.write_table(table, output, compression=compression, row_group_size=128 * 1024 * 1024)
    except Exception as exc:
        raise VectorError(f"Failed to write GeoParquet '{output}': {exc}") from exc

    file_size: int | None = None
    try:
        file_size = Path(output).stat().st_size
    except OSError:
        pass

    return ConvertResult(
        source=source,
        output=output,
        input_format=input_format,
        output_format="geoparquet",
        feature_count=actual_count,
        geometry_type=geom_type,
        crs=crs_string,
        bbox=bbox,
        file_size_bytes=file_size,
    )


async def convert_vector(
    source: str,
    *,
    output: str | None = None,
    target_format: str = "geoparquet",
    compression: str = "snappy",
) -> ConvertResult:
    """Convert a vector file to GeoParquet.

    Reads the source using GDAL/OGR and writes GeoParquet with proper ``geo``
    metadata. Supports Shapefile, GeoJSON, GPKG, and any OGR-supported format.

    Parameters:
        source: Path to the input vector file.
        output: Output file path. If ``None``, replaces extension with ``.parquet``.
        target_format: Target format (default: ``"geoparquet"``).
        compression: Parquet compression codec (default: ``"snappy"``).

    Returns:
        Structured conversion result.

    Raises:
        VectorError: If the conversion fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _convert_vector_sync,
            source,
            output=output,
            target_format=target_format,
            compression=compression,
        ),
    )
