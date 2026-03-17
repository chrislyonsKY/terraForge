"""GeoParquet schema compliance validation.

Validates GeoParquet files against the GeoParquet specification by checking:

- Presence of ``geo`` metadata key in Parquet file metadata
- CRS stored as PROJJSON in the ``geo`` metadata
- Geometry column declared and present in the schema
- Supported geometry encoding (WKB)
- Valid bounding box metadata

Usage::

    from earthforge.vector.validate import validate_geoparquet

    result = await validate_geoparquet("buildings.parquet")
"""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from earthforge.core.output import StatusMarker, format_status
from earthforge.vector.errors import VectorValidationError


class VectorValidationCheck(BaseModel):
    """Result of a single validation check.

    Attributes:
        check: Name of the validation check.
        status: Pass/fail/warn status with text marker.
        message: Human-readable detail.
    """

    check: str = Field(title="Check")
    status: str = Field(title="Status")
    message: str = Field(title="Message")


class VectorValidationResult(BaseModel):
    """Aggregate result of validating a GeoParquet file.

    Attributes:
        source: Path or URL that was validated.
        is_valid: Overall pass/fail.
        format_version: GeoParquet version if detected.
        geometry_column: Name of the primary geometry column.
        crs: CRS identifier (e.g. EPSG code) if found.
        encoding: Geometry encoding (e.g. WKB).
        checks: Individual check results.
        summary: Human-readable one-line summary.
    """

    source: str = Field(title="Source")
    is_valid: bool = Field(title="Valid")
    format_version: str | None = Field(default=None, title="GeoParquet Version")
    geometry_column: str | None = Field(default=None, title="Geometry Column")
    crs: str | None = Field(default=None, title="CRS")
    encoding: str | None = Field(default=None, title="Encoding")
    checks: list[VectorValidationCheck] = Field(default_factory=list, title="Checks")
    summary: str = Field(title="Summary")


async def validate_geoparquet(source: str) -> VectorValidationResult:
    """Validate a GeoParquet file against the specification.

    Parameters:
        source: Path or URL to a Parquet file.

    Returns:
        A :class:`VectorValidationResult` with detailed check results.

    Raises:
        VectorValidationError: If the file cannot be read or is not Parquet.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_validate_sync, source))


def _validate_sync(source: str) -> VectorValidationResult:
    """Synchronous GeoParquet validation implementation.

    Parameters:
        source: Path to a Parquet file.

    Returns:
        Validation result.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise VectorValidationError(
            "pyarrow is required for GeoParquet validation: pip install earthforge[vector]"
        ) from exc

    checks: list[VectorValidationCheck] = []
    geometry_column: str | None = None
    crs_id: str | None = None
    encoding: str | None = None
    format_version: str | None = None

    # --- Read Parquet metadata ---
    try:
        pf = pq.ParquetFile(source)
        metadata = pf.schema_arrow.metadata or {}
    except Exception as exc:
        raise VectorValidationError(f"Cannot read Parquet file {source}: {exc}") from exc

    checks.append(
        VectorValidationCheck(
            check="parquet_readable",
            status=format_status(StatusMarker.PASS),
            message="File is valid Parquet",
        )
    )

    # --- Check for geo metadata ---
    geo_bytes = metadata.get(b"geo")
    if geo_bytes is None:
        checks.append(
            VectorValidationCheck(
                check="geo_metadata",
                status=format_status(StatusMarker.FAIL),
                message="Missing 'geo' metadata key — not a GeoParquet file",
            )
        )
        return VectorValidationResult(
            source=source,
            is_valid=False,
            checks=checks,
            summary=format_status(
                StatusMarker.FAIL,
                "Not a GeoParquet file (missing 'geo' metadata)",
            ),
        )

    try:
        geo_meta: dict[str, Any] = json.loads(geo_bytes)
    except json.JSONDecodeError as exc:
        checks.append(
            VectorValidationCheck(
                check="geo_metadata",
                status=format_status(StatusMarker.FAIL),
                message=f"Invalid JSON in 'geo' metadata: {exc}",
            )
        )
        return VectorValidationResult(
            source=source,
            is_valid=False,
            checks=checks,
            summary=format_status(StatusMarker.FAIL, "Invalid 'geo' metadata JSON"),
        )

    checks.append(
        VectorValidationCheck(
            check="geo_metadata",
            status=format_status(StatusMarker.PASS),
            message="'geo' metadata key present and valid JSON",
        )
    )

    # --- GeoParquet version ---
    format_version = geo_meta.get("version")
    if format_version:
        checks.append(
            VectorValidationCheck(
                check="geoparquet_version",
                status=format_status(StatusMarker.PASS),
                message=f"GeoParquet version: {format_version}",
            )
        )
    else:
        checks.append(
            VectorValidationCheck(
                check="geoparquet_version",
                status=format_status(StatusMarker.WARN),
                message="No version field in geo metadata",
            )
        )

    # --- Primary geometry column ---
    primary_column = geo_meta.get("primary_column")
    columns_meta: dict[str, Any] = geo_meta.get("columns", {})

    if primary_column:
        geometry_column = primary_column
        checks.append(
            VectorValidationCheck(
                check="primary_column",
                status=format_status(StatusMarker.PASS),
                message=f"Primary geometry column: '{primary_column}'",
            )
        )
    elif columns_meta:
        geometry_column = next(iter(columns_meta))
        checks.append(
            VectorValidationCheck(
                check="primary_column",
                status=format_status(StatusMarker.WARN),
                message=f"No primary_column declared; using first column: '{geometry_column}'",
            )
        )
    else:
        checks.append(
            VectorValidationCheck(
                check="primary_column",
                status=format_status(StatusMarker.FAIL),
                message="No geometry columns defined in geo metadata",
            )
        )

    # --- Geometry column exists in schema ---
    schema_names = [field.name for field in pf.schema_arrow]
    if geometry_column and geometry_column in schema_names:
        checks.append(
            VectorValidationCheck(
                check="column_in_schema",
                status=format_status(StatusMarker.PASS),
                message=f"Geometry column '{geometry_column}' exists in Parquet schema",
            )
        )
    elif geometry_column:
        checks.append(
            VectorValidationCheck(
                check="column_in_schema",
                status=format_status(StatusMarker.FAIL),
                message=f"Geometry column '{geometry_column}' not found in schema",
            )
        )

    # --- CRS check ---
    if geometry_column and geometry_column in columns_meta:
        col_meta = columns_meta[geometry_column]
        crs_data = col_meta.get("crs")
        if crs_data is None:
            checks.append(
                VectorValidationCheck(
                    check="crs",
                    status=format_status(StatusMarker.WARN),
                    message="No CRS specified (defaults to OGC:CRS84 / WGS84)",
                )
            )
            crs_id = "OGC:CRS84"
        elif isinstance(crs_data, dict):
            # PROJJSON format
            crs_name = crs_data.get("name", "Unknown")
            crs_id_val = crs_data.get("id", {})
            if isinstance(crs_id_val, dict):
                authority = crs_id_val.get("authority", "")
                code = crs_id_val.get("code", "")
                crs_id = f"{authority}:{code}" if authority and code else crs_name
            else:
                crs_id = crs_name
            checks.append(
                VectorValidationCheck(
                    check="crs",
                    status=format_status(StatusMarker.PASS),
                    message=f"CRS in PROJJSON format: {crs_id}",
                )
            )
        else:
            checks.append(
                VectorValidationCheck(
                    check="crs",
                    status=format_status(StatusMarker.WARN),
                    message=f"CRS format not PROJJSON: {type(crs_data).__name__}",
                )
            )

        # --- Encoding check ---
        enc = col_meta.get("encoding", "WKB")
        encoding = enc
        valid_encodings = (
            "WKB",
            "POINT",
            "LINESTRING",
            "POLYGON",
            "MULTIPOINT",
            "MULTILINESTRING",
            "MULTIPOLYGON",
        )
        if enc.upper() in valid_encodings:
            checks.append(
                VectorValidationCheck(
                    check="encoding",
                    status=format_status(StatusMarker.PASS),
                    message=f"Geometry encoding: {enc}",
                )
            )
        else:
            checks.append(
                VectorValidationCheck(
                    check="encoding",
                    status=format_status(StatusMarker.WARN),
                    message=f"Unusual geometry encoding: {enc}",
                )
            )

        # --- Bbox check ---
        bbox = col_meta.get("bbox")
        if bbox and isinstance(bbox, list) and len(bbox) >= 4:
            checks.append(
                VectorValidationCheck(
                    check="bbox",
                    status=format_status(StatusMarker.PASS),
                    message=f"Bounding box: [{', '.join(str(v) for v in bbox)}]",
                )
            )
        elif bbox:
            checks.append(
                VectorValidationCheck(
                    check="bbox",
                    status=format_status(StatusMarker.WARN),
                    message=f"Invalid bbox format: {bbox}",
                )
            )

        # --- Geometry types ---
        geom_types = col_meta.get("geometry_types", [])
        if geom_types:
            checks.append(
                VectorValidationCheck(
                    check="geometry_types",
                    status=format_status(StatusMarker.PASS),
                    message=f"Geometry types: {', '.join(geom_types)}",
                )
            )

    # --- Summary ---
    fail_count = sum(1 for c in checks if StatusMarker.FAIL.value in c.status)
    warn_count = sum(1 for c in checks if StatusMarker.WARN.value in c.status)
    pass_count = sum(1 for c in checks if StatusMarker.PASS.value in c.status)
    is_valid = fail_count == 0

    if is_valid:
        summary = format_status(
            StatusMarker.PASS,
            f"Valid GeoParquet ({pass_count} checks passed"
            + (f", {warn_count} warning(s)" if warn_count else "")
            + ")",
        )
    else:
        summary = format_status(
            StatusMarker.FAIL,
            f"Invalid GeoParquet ({fail_count} failure(s), {warn_count} warning(s))",
        )

    return VectorValidationResult(
        source=source,
        is_valid=is_valid,
        format_version=format_version,
        geometry_column=geometry_column,
        crs=crs_id,
        encoding=encoding,
        checks=checks,
        summary=summary,
    )
