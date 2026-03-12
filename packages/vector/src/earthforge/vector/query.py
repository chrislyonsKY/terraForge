"""Spatial and attribute queries against GeoParquet files.

Leverages pyarrow's row-group-level statistics and predicate pushdown to
read only the data that matches the query — critical for large files where
reading the full dataset would be impractical.

For bbox queries, the filter is applied against the ``bbox`` column covering
structure embedded in GeoParquet metadata. If per-row bounding box columns
(``bbox.xmin``, ``bbox.ymin``, etc.) are present, pyarrow can skip entire
row groups whose spatial extent doesn't intersect the query box.

Usage::

    from earthforge.vector.query import query_features

    result = await query_features("buildings.parquet", bbox=[-85, 37, -84, 38])
    print(result.feature_count)
"""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from earthforge.vector.errors import VectorError


class QueryResult(BaseModel):
    """Structured result from a vector spatial/attribute query.

    Attributes:
        source: The file that was queried.
        feature_count: Number of features matching the query.
        columns: Column names in the result.
        bbox_filter: The bounding box filter applied, if any.
        features: List of feature dicts (geometry as WKT if available).
        total_rows: Total rows in the source file (before filtering).
        row_groups_scanned: Number of Parquet row groups actually read.
        row_groups_total: Total row groups in the file.
    """

    source: str = Field(title="Source")
    feature_count: int = Field(title="Features")
    columns: list[str] = Field(title="Columns")
    bbox_filter: list[float] | None = Field(default=None, title="BBox Filter")
    features: list[dict[str, Any]] = Field(default_factory=list, title="Features")
    total_rows: int = Field(title="Total Rows")
    row_groups_scanned: int | None = Field(default=None, title="Row Groups Scanned")
    row_groups_total: int | None = Field(default=None, title="Row Groups Total")


def _parse_geo_metadata(metadata: dict[bytes, bytes]) -> dict[str, Any]:
    """Parse the GeoParquet ``geo`` metadata key.

    Parameters:
        metadata: Raw Parquet file-level metadata.

    Returns:
        Parsed geo metadata dict, or empty dict.
    """
    geo_bytes = metadata.get(b"geo")
    if geo_bytes is None:
        return {}
    try:
        result: dict[str, Any] = json.loads(geo_bytes)
        return result
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _build_bbox_filter(
    geo_meta: dict[str, Any],
    bbox: list[float],
    schema_names: set[str],
) -> Any:
    """Build a pyarrow filter expression for a bounding box query.

    Checks for GeoParquet bbox column covering (``covering.bbox``), which
    provides per-row min/max coordinates that pyarrow can use for predicate
    pushdown at the row-group level.

    Falls back to no filter if bbox covering is not present — the full scan
    result will then be post-filtered in Python.

    Parameters:
        geo_meta: Parsed GeoParquet metadata.
        bbox: Query bounding box ``[west, south, east, north]``.
        schema_names: Set of column names present in the file schema.

    Returns:
        A pyarrow compute expression, or ``None`` if no pushdown is possible.
    """
    import pyarrow.compute as pc

    west, south, east, north = bbox

    # Check for GeoParquet bbox covering metadata
    primary_col = geo_meta.get("primary_column", "geometry")
    col_meta = geo_meta.get("columns", {}).get(primary_col, {})
    covering = col_meta.get("covering", {})
    bbox_covering = covering.get("bbox", {})

    xmin_col = bbox_covering.get("xmin")
    ymin_col = bbox_covering.get("ymin")
    xmax_col = bbox_covering.get("xmax")
    ymax_col = bbox_covering.get("ymax")

    if all([xmin_col, ymin_col, xmax_col, ymax_col]):
        # Use covering columns for pushdown: feature bbox intersects query bbox
        return (
            (pc.field(xmin_col) <= east)
            & (pc.field(xmax_col) >= west)
            & (pc.field(ymin_col) <= north)
            & (pc.field(ymax_col) >= south)
        )

    # Check for common bbox struct columns (Overture Maps pattern)
    for col_set in [
        ("bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax"),
        ("bbox.minx", "bbox.miny", "bbox.maxx", "bbox.maxy"),
    ]:
        if all(c in schema_names for c in col_set):
            xmin_c, ymin_c, xmax_c, ymax_c = col_set
            return (
                (pc.field(xmin_c) <= east)
                & (pc.field(xmax_c) >= west)
                & (pc.field(ymin_c) <= north)
                & (pc.field(ymax_c) >= south)
            )

    # No pushdown columns available — caller will post-filter with geometry
    return None


def _geometry_intersects_bbox(
    wkb: bytes,
    west: float,
    south: float,
    east: float,
    north: float,
) -> bool:
    """Check if a WKB geometry's envelope intersects a bounding box.

    Uses shapely for full geometry intersection if available. Falls back to
    a minimal WKB point parser that checks if the point lies within the bbox.

    Parameters:
        wkb: Well-Known Binary geometry bytes.
        west: Query bbox west.
        south: Query bbox south.
        east: Query bbox east.
        north: Query bbox north.

    Returns:
        True if the geometry intersects the query bbox.
    """
    try:
        from shapely import from_wkb
        from shapely.geometry import box

        geom = from_wkb(wkb)
        query_box = box(west, south, east, north)
        return bool(geom.intersects(query_box))
    except ImportError:
        pass

    # Fallback: parse WKB point coordinates for simple containment check
    import struct

    if len(wkb) >= 21:
        try:
            byte_order = wkb[0]
            fmt = "<" if byte_order == 1 else ">"
            wkb_type = struct.unpack(f"{fmt}I", wkb[1:5])[0]
            if wkb_type == 1:  # Point
                x, y = struct.unpack(f"{fmt}dd", wkb[5:21])
                return bool(west <= x <= east and south <= y <= north)
        except (struct.error, IndexError):
            pass

    # For non-point geometries without shapely, include conservatively
    return True


def _wkb_to_wkt(wkb: bytes) -> str | None:
    """Convert WKB bytes to WKT string for output.

    Uses shapely if available; otherwise falls back to a minimal WKB parser
    that handles Point geometries (the most common case for tabular data).

    Parameters:
        wkb: Well-Known Binary geometry.

    Returns:
        WKT string, or None if conversion fails.
    """
    try:
        from shapely import from_wkb

        geom = from_wkb(wkb)
        return str(geom.wkt)
    except ImportError:
        pass
    except Exception:
        return None

    # Minimal fallback WKB parser for Point geometry
    return _parse_wkb_point(wkb)


def _parse_wkb_point(wkb: bytes) -> str | None:
    """Parse a WKB Point geometry to WKT without shapely.

    Parameters:
        wkb: Well-Known Binary bytes.

    Returns:
        WKT string if it's a Point, None otherwise.
    """
    import struct

    if len(wkb) < 21:
        return None
    try:
        byte_order = wkb[0]
        fmt = "<" if byte_order == 1 else ">"
        wkb_type = struct.unpack(f"{fmt}I", wkb[1:5])[0]
        if wkb_type == 1:  # Point
            x, y = struct.unpack(f"{fmt}dd", wkb[5:21])
            return f"POINT ({x} {y})"
    except (struct.error, IndexError):
        pass
    return None


def _query_features_sync(
    source: str,
    *,
    bbox: list[float] | None = None,
    columns: list[str] | None = None,
    limit: int | None = None,
    include_geometry: bool = True,
) -> QueryResult:
    """Execute a spatial/attribute query synchronously.

    Parameters:
        source: Path to a GeoParquet/Parquet file.
        bbox: Bounding box filter ``[west, south, east, north]`` in the file's CRS.
        columns: Columns to include in results. ``None`` returns all columns.
        limit: Maximum number of features to return.
        include_geometry: Whether to include geometry as WKT in results.

    Returns:
        Structured query result with matching features.

    Raises:
        VectorError: If the file cannot be read or query fails.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise VectorError(
            "pyarrow is required for vector queries: pip install earthforge[vector]"
        ) from exc

    try:
        pf = pq.ParquetFile(source)
    except Exception as exc:
        raise VectorError(f"Failed to open '{source}': {exc}") from exc

    schema = pf.schema_arrow
    file_metadata = schema.metadata or {}
    geo_meta = _parse_geo_metadata(file_metadata)
    primary_geom = geo_meta.get("primary_column", "geometry")
    total_rows = pf.metadata.num_rows
    num_row_groups = pf.metadata.num_row_groups

    # Build pyarrow filter for pushdown
    schema_names = {schema.field(i).name for i in range(len(schema))}
    pa_filter = None
    if bbox:
        pa_filter = _build_bbox_filter(geo_meta, bbox, schema_names)

    # Determine columns to read
    read_columns = columns
    if read_columns and include_geometry and primary_geom not in read_columns:
        read_columns = [*read_columns, primary_geom]

    # Read with filter pushdown via read_table (supports filters, unlike ParquetFile.read)
    try:
        table = pq.read_table(source, columns=read_columns, filters=pa_filter)
    except Exception as exc:
        raise VectorError(f"Query failed on '{source}': {exc}") from exc

    # Post-filter with geometry intersection if bbox provided but no pushdown
    if bbox and pa_filter is None and primary_geom in table.column_names:
        west, south, east, north = bbox
        geom_col = table.column(primary_geom)
        mask = []
        for val in geom_col:
            raw = val.as_py()
            if isinstance(raw, bytes):
                mask.append(_geometry_intersects_bbox(raw, west, south, east, north))
            else:
                mask.append(True)
        import pyarrow as pa

        table = table.filter(pa.array(mask))

    # Apply limit
    if limit is not None and len(table) > limit:
        table = table.slice(0, limit)

    # Convert to feature dicts
    features: list[dict[str, Any]] = []
    result_columns = table.column_names
    for i in range(len(table)):
        feature: dict[str, Any] = {}
        for col_name in result_columns:
            val = table.column(col_name)[i].as_py()
            if col_name == primary_geom and isinstance(val, bytes):
                if include_geometry:
                    wkt = _wkb_to_wkt(val)
                    feature["geometry_wkt"] = wkt if wkt else "(binary)"
            else:
                feature[col_name] = val
        features.append(feature)

    return QueryResult(
        source=source,
        feature_count=len(features),
        columns=[c for c in result_columns if c != primary_geom or include_geometry],
        bbox_filter=bbox,
        features=features,
        total_rows=total_rows,
        row_groups_scanned=num_row_groups if pa_filter is None else None,
        row_groups_total=num_row_groups,
    )


async def query_features(
    source: str,
    *,
    bbox: list[float] | None = None,
    columns: list[str] | None = None,
    limit: int | None = None,
    include_geometry: bool = True,
) -> QueryResult:
    """Query features from a GeoParquet file.

    Uses pyarrow predicate pushdown when GeoParquet bbox covering metadata
    is present, skipping row groups that don't intersect the query bbox.
    Falls back to post-read geometry filtering via shapely when covering
    is not available.

    Parameters:
        source: Path to a GeoParquet/Parquet file.
        bbox: Bounding box filter ``[west, south, east, north]``.
        columns: Columns to include. ``None`` returns all.
        limit: Maximum features to return.
        include_geometry: Include geometry as WKT in results.

    Returns:
        Structured query result.

    Raises:
        VectorError: If the file cannot be read or query fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _query_features_sync,
            source,
            bbox=bbox,
            columns=columns,
            limit=limit,
            include_geometry=include_geometry,
        ),
    )
