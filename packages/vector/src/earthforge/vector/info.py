"""Deep metadata extraction for vector geospatial formats.

Reads Parquet/GeoParquet file metadata via pyarrow without loading data into
memory. Extracts schema, row counts, geometry columns, CRS, bounding box, and
encoding information from GeoParquet ``geo`` metadata.

For non-Parquet vector formats (GeoJSON, FlatGeobuf), provides basic file-level
metadata. Deep inspection of those formats may be added in later milestones.
"""

from __future__ import annotations

import asyncio
import json
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from earthforge.vector.errors import VectorError


class ColumnInfo(BaseModel):
    """Metadata for a single column in a vector dataset.

    Attributes:
        name: Column name.
        type: Arrow type string (e.g. ``"int64"``, ``"binary"``).
        is_geometry: Whether this column contains geometry data.
    """

    name: str = Field(title="Column")
    type: str = Field(title="Type")
    is_geometry: bool = Field(default=False, title="Geometry")


class VectorInfo(BaseModel):
    """Structured metadata for a vector geospatial file.

    Attributes:
        source: The file path that was inspected.
        format: Detected vector format (e.g. ``"geoparquet"``, ``"parquet"``).
        row_count: Total number of rows/features.
        num_columns: Total number of columns.
        columns: Per-column metadata.
        geometry_column: Name of the primary geometry column, if any.
        geometry_types: List of geometry types found (e.g. ``["Point"]``).
        crs: CRS string from GeoParquet metadata, if available.
        bbox: Bounding box ``[west, south, east, north]``, if available.
        encoding: Geometry encoding (e.g. ``"WKB"``), if available.
        num_row_groups: Number of Parquet row groups.
        compression: Parquet compression codec, if applicable.
        file_size_bytes: File size in bytes.
    """

    source: str = Field(title="Source")
    format: str = Field(title="Format")
    row_count: int = Field(title="Rows")
    num_columns: int = Field(title="Columns")
    columns: list[ColumnInfo] = Field(title="Column Details")
    geometry_column: str | None = Field(default=None, title="Geometry Column")
    geometry_types: list[str] = Field(default_factory=list, title="Geometry Types")
    crs: str | None = Field(default=None, title="CRS")
    bbox: list[float] | None = Field(default=None, title="Bounding Box")
    encoding: str | None = Field(default=None, title="Encoding")
    num_row_groups: int | None = Field(default=None, title="Row Groups")
    compression: str | None = Field(default=None, title="Compression")
    file_size_bytes: int | None = Field(default=None, title="Size (bytes)")


def _read_parquet_info(source: str) -> VectorInfo:
    """Read metadata from a Parquet/GeoParquet file synchronously.

    Uses pyarrow to read only the file metadata and schema — no row data
    is loaded into memory. Parses the ``geo`` metadata key for GeoParquet-
    specific information (geometry column, CRS, bbox, encoding).

    Parameters:
        source: Path to a Parquet file.

    Returns:
        Structured vector metadata.

    Raises:
        VectorError: If the file cannot be read or is not a valid Parquet file.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        msg = "pyarrow is required for Parquet inspection: pip install pyarrow"
        raise VectorError(msg) from exc

    try:
        pf = pq.ParquetFile(source)  # type: ignore[no-untyped-call]
    except Exception as exc:
        msg = f"Failed to read Parquet file '{source}': {exc}"
        raise VectorError(msg) from exc

    schema = pf.schema_arrow
    metadata = schema.metadata or {}
    num_rows = pf.metadata.num_rows
    num_row_groups = pf.metadata.num_row_groups

    # Detect compression from the first row group's first column chunk
    compression: str | None = None
    if num_row_groups > 0 and schema:
        try:
            rg = pf.metadata.row_group(0)
            if rg.num_columns > 0:
                compression = rg.column(0).compression
        except Exception:  # noqa: S110 — best-effort metadata extraction
            pass

    # Parse GeoParquet metadata
    geo_meta = _parse_geo_metadata(metadata)
    geometry_column = geo_meta.get("primary_column")
    geometry_columns: set[str] = set()
    geometry_types: list[str] = []
    crs: str | None = None
    bbox: list[float] | None = None
    encoding: str | None = None

    if geometry_column and "columns" in geo_meta:
        geometry_columns.add(geometry_column)
        col_meta = geo_meta["columns"].get(geometry_column, {})
        geometry_types = col_meta.get("geometry_types", [])
        encoding = col_meta.get("encoding")
        bbox_raw = col_meta.get("bbox")
        if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
            bbox = [float(v) for v in bbox_raw]

        crs_obj = col_meta.get("crs")
        if isinstance(crs_obj, dict):
            # GeoParquet stores CRS as PROJJSON — extract the name or ID
            crs = _extract_crs_string(crs_obj)
        elif isinstance(crs_obj, str):
            crs = crs_obj

    # Also check for additional geometry columns
    if "columns" in geo_meta:
        geometry_columns.update(geo_meta["columns"].keys())

    # Build column info
    columns: list[ColumnInfo] = []
    for i in range(len(schema)):
        field = schema.field(i)
        columns.append(
            ColumnInfo(
                name=field.name,
                type=str(field.type),
                is_geometry=field.name in geometry_columns,
            )
        )

    # File size
    file_size: int | None = None
    try:
        file_size = Path(source).stat().st_size
    except OSError:
        pass

    fmt = "geoparquet" if geometry_column else "parquet"

    return VectorInfo(
        source=source,
        format=fmt,
        row_count=num_rows,
        num_columns=len(schema),
        columns=columns,
        geometry_column=geometry_column,
        geometry_types=geometry_types,
        crs=crs,
        bbox=bbox,
        encoding=encoding,
        num_row_groups=num_row_groups,
        compression=compression,
        file_size_bytes=file_size,
    )


def _parse_geo_metadata(metadata: dict[bytes, bytes]) -> dict[str, Any]:
    """Parse the ``geo`` key from Parquet file metadata.

    Parameters:
        metadata: Raw Parquet schema metadata (bytes keys and values).

    Returns:
        Parsed GeoParquet metadata dict, or empty dict if not present.
    """
    geo_bytes = metadata.get(b"geo")
    if geo_bytes is None:
        return {}
    try:
        result: dict[str, Any] = json.loads(geo_bytes)
        return result
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _extract_crs_string(crs_obj: dict[str, Any]) -> str:
    """Extract a human-readable CRS identifier from PROJJSON.

    Tries ``id.code`` (e.g. ``"EPSG:4326"``), then ``name``, then falls
    back to a truncated JSON representation.

    Parameters:
        crs_obj: PROJJSON CRS object.

    Returns:
        CRS identifier string.
    """
    # Try EPSG-style authority:code
    crs_id = crs_obj.get("id", {})
    if isinstance(crs_id, dict):
        authority = crs_id.get("authority")
        code = crs_id.get("code")
        if authority and code:
            return f"{authority}:{code}"

    # Fall back to name
    name = crs_obj.get("name")
    if isinstance(name, str):
        return name

    return json.dumps(crs_obj)[:100]


async def inspect_vector(source: str) -> VectorInfo:
    """Inspect a vector file and return structured metadata.

    Runs the synchronous pyarrow read in a thread executor to avoid blocking
    the event loop. Currently supports Parquet and GeoParquet files.

    Parameters:
        source: Path to a vector file.

    Returns:
        Structured vector metadata.

    Raises:
        VectorError: If the file cannot be read or format is unsupported.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_read_parquet_info, source))
