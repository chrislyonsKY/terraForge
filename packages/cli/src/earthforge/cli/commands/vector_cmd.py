"""EarthForge ``vector`` command group — vector file operations.

Provides commands for inspecting, querying, and converting vector files
(GeoParquet, Shapefile, GeoJSON). Query supports bbox spatial filtering
with predicate pushdown for large GeoParquet files.
"""

from __future__ import annotations

import typer
from pydantic import BaseModel

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="vector",
    help="Inspect, query, and convert vector files.",
    no_args_is_help=True,
)


def info(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a vector file (Parquet, GeoParquet)."),
) -> None:
    """Inspect vector file metadata (schema, CRS, feature count, bbox)."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.vector.info import inspect_vector

    state = get_state(ctx)
    result = run_command(ctx, inspect_vector(source))
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


def query(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a GeoParquet file."),
    bbox: str = typer.Option(
        None,
        "--bbox",
        help="Bounding box filter: west,south,east,north.",
    ),
    columns: str = typer.Option(
        None,
        "--columns",
        "-c",
        help="Comma-separated column names to include.",
    ),
    limit: int = typer.Option(
        None,
        "--limit",
        "-n",
        help="Maximum number of features to return.",
    ),
    no_geometry: bool = typer.Option(
        False,
        "--no-geometry",
        help="Exclude geometry from output.",
    ),
) -> None:
    """Query features from a GeoParquet file with optional bbox filter."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.vector.query import query_features

    state = get_state(ctx)

    # Parse bbox
    bbox_list: list[float] | None = None
    if bbox:
        parts = [float(v.strip()) for v in bbox.split(",")]
        if len(parts) != 4:
            typer.echo("Error: --bbox requires exactly 4 values: west,south,east,north", err=True)
            raise typer.Exit(code=1)
        bbox_list = parts

    # Parse columns
    col_list: list[str] | None = None
    if columns:
        col_list = [c.strip() for c in columns.split(",")]

    result = run_command(
        ctx,
        query_features(
            source,
            bbox=bbox_list,
            columns=col_list,
            limit=limit,
            include_geometry=not no_geometry,
        ),
    )
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


def convert(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a vector file (Shapefile, GeoJSON, GPKG)."),
    output: str = typer.Option(
        None,
        "--out",
        "-O",
        help="Output file path. Defaults to <source>.parquet.",
    ),
    compression: str = typer.Option(
        "snappy",
        "--compression",
        help="Parquet compression: snappy, zstd, gzip.",
    ),
) -> None:
    """Convert a vector file to GeoParquet."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.vector.convert import convert_vector

    state = get_state(ctx)
    result = run_command(
        ctx,
        convert_vector(source, output=output, compression=compression),
    )
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


app.command(name="info", help="Inspect vector file metadata.")(info)
app.command(name="query", help="Query features with spatial filter.")(query)
app.command(name="convert", help="Convert to GeoParquet.")(convert)
