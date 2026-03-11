"""EarthForge ``info`` command — inspect a geospatial file.

Auto-detects the file format and returns structured metadata. This is the
first working command in EarthForge (Milestone 0) and demonstrates the full
architecture: CLI dispatch → async library call → structured output.

For M0, this command handles format detection and basic file metadata. Domain
packages (raster, vector) will extend it with format-specific deep inspection
in later milestones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer
from pydantic import BaseModel, Field

from earthforge.core.errors import EarthForgeError
from earthforge.core.formats import FormatType, detect
from earthforge.core.output import render_to_console


class FileInfo(BaseModel):
    """Structured result for the ``info`` command.

    Attributes:
        source: The file path or URL that was inspected.
        format: The detected format identifier.
        format_label: Human-readable format name.
        size_bytes: File size in bytes (local files only; ``None`` for remote).
        last_modified: Last modification time (local files only; ``None`` for remote).
    """

    source: str = Field(title="Source")
    format: FormatType = Field(title="Format")
    format_label: str = Field(title="Format Label")
    size_bytes: int | None = Field(default=None, title="Size (bytes)")
    last_modified: str | None = Field(default=None, title="Last Modified")


_FORMAT_LABELS: dict[FormatType, str] = {
    FormatType.COG: "Cloud Optimized GeoTIFF (COG)",
    FormatType.GEOTIFF: "GeoTIFF",
    FormatType.GEOPARQUET: "GeoParquet",
    FormatType.PARQUET: "Apache Parquet",
    FormatType.FLATGEOBUF: "FlatGeobuf",
    FormatType.ZARR: "Zarr",
    FormatType.NETCDF: "NetCDF",
    FormatType.COPC: "Cloud Optimized Point Cloud (COPC)",
    FormatType.STAC_ITEM: "STAC Item",
    FormatType.STAC_COLLECTION: "STAC Collection",
    FormatType.STAC_CATALOG: "STAC Catalog",
    FormatType.GEOJSON: "GeoJSON",
    FormatType.UNKNOWN: "Unknown",
}


_RASTER_FORMATS = {FormatType.COG, FormatType.GEOTIFF}
_VECTOR_FORMATS = {FormatType.GEOPARQUET, FormatType.PARQUET}


async def _info(source: str, profile: str) -> BaseModel:
    """Async implementation of the info command.

    Detects the file format, then dispatches to the appropriate domain-specific
    inspector if available (raster, vector). Falls back to basic file info for
    formats without a deep inspector.

    Parameters:
        source: Local file path or remote URL.
        profile: Config profile name (for remote URL auth).

    Returns:
        Structured file information (type depends on detected format).
    """
    from earthforge.core.config import load_profile

    prof = await load_profile(profile)
    fmt = await detect(source, profile=prof)

    # Dispatch to domain-specific deep inspection.
    # If the domain inspector fails (e.g. file has correct magic bytes but is
    # not a valid raster/vector), fall through to basic file info.
    if fmt in _RASTER_FORMATS:
        try:
            from earthforge.raster.info import inspect_raster

            return await inspect_raster(source)
        except (ImportError, EarthForgeError):
            pass  # package missing or file unreadable — fall through

    if fmt in _VECTOR_FORMATS:
        try:
            from earthforge.vector.info import inspect_vector

            return await inspect_vector(source)
        except (ImportError, EarthForgeError):
            pass  # package missing or file unreadable — fall through

    # Basic file info for formats without a deep inspector
    size_bytes: int | None = None
    last_modified: str | None = None

    if not source.startswith(("http://", "https://")):
        try:
            path = Path(source)
            stat = path.stat()
            size_bytes = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            last_modified = mtime.isoformat()
        except OSError:
            pass

    return FileInfo(
        source=source,
        format=fmt,
        format_label=_FORMAT_LABELS.get(fmt, fmt.value),
        size_bytes=size_bytes,
        last_modified=last_modified,
    )


def info(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path or URL to a geospatial file."),
) -> None:
    """Inspect a geospatial file and display its format and metadata."""
    from earthforge.cli.main import get_state, run_command

    state = get_state(ctx)
    result = run_command(ctx, _info(source, state.profile))

    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)
