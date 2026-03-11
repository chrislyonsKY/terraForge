"""TerraForge ``info`` command — inspect a geospatial file.

Auto-detects the file format and returns structured metadata. This is the
first working command in TerraForge (Milestone 0) and demonstrates the full
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

from terraforge.core.formats import FormatType, detect
from terraforge.core.output import render_to_console


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


async def _info(source: str, profile: str) -> FileInfo:
    """Async implementation of the info command.

    Parameters:
        source: Local file path or remote URL.
        profile: Config profile name (for remote URL auth).

    Returns:
        Structured file information.
    """
    from terraforge.core.config import load_profile

    prof = await load_profile(profile)
    fmt = await detect(source, profile=prof)

    size_bytes: int | None = None
    last_modified: str | None = None

    # Get local file metadata if it's a local path
    if not source.startswith(("http://", "https://")):
        try:
            path = Path(source)
            stat = path.stat()
            size_bytes = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            last_modified = mtime.isoformat()
        except OSError:
            pass  # File metadata unavailable — not fatal for detection

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
    from terraforge.cli.main import get_state, run_command

    state = get_state(ctx)
    result = run_command(ctx, _info(source, state.profile))

    if isinstance(result, FileInfo):
        render_to_console(result, state.output, no_color=state.no_color)
