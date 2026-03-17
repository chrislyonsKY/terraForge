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
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


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
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


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
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def validate(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a GeoParquet file."),
) -> None:
    """Validate GeoParquet schema compliance."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.vector.validate import validate_geoparquet

    state = get_state(ctx)
    result = run_command(ctx, validate_geoparquet(source))
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def tile(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a vector file."),
    output: str = typer.Option(..., "--out", "-O", help="Output path (.pmtiles or .mbtiles)."),
    min_zoom: int = typer.Option(0, "--min-zoom", help="Minimum zoom level."),
    max_zoom: int = typer.Option(14, "--max-zoom", help="Maximum zoom level."),
    layer_name: str | None = typer.Option(
        None,
        "--layer",
        help="Layer name. Default: input filename.",
    ),
) -> None:
    """Generate vector tiles (PMTiles or MBTiles) from a vector file."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.vector.tile import generate_vector_tiles

    state = get_state(ctx)
    result = run_command(
        ctx,
        generate_vector_tiles(
            source,
            output,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            layer_name=layer_name,
        ),
    )
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def clip(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a vector file."),
    output: str = typer.Option(
        None,
        "--out",
        "-O",
        help="Output path. Default: <source>_clipped.parquet.",
    ),
    bbox: str | None = typer.Option(
        None,
        "--bbox",
        help="Bounding box: west,south,east,north.",
    ),
    geometry_wkt: str | None = typer.Option(
        None,
        "--geometry",
        "-g",
        help="WKT geometry to clip to.",
    ),
) -> None:
    """Clip features to a bounding box or geometry."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.vector.clip import clip_features

    state = get_state(ctx)

    bbox_tuple: tuple[float, float, float, float] | None = None
    if bbox:
        parts = [float(v.strip()) for v in bbox.split(",")]
        if len(parts) != 4:
            typer.echo("Error: --bbox requires exactly 4 values", err=True)
            raise typer.Exit(code=1)
        bbox_tuple = (parts[0], parts[1], parts[2], parts[3])

    result = run_command(
        ctx,
        clip_features(source, output, bbox=bbox_tuple, geometry_wkt=geometry_wkt),
    )
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


app.command(name="info", help="Inspect vector file metadata.")(info)
app.command(name="query", help="Query features with spatial filter.")(query)
app.command(name="convert", help="Convert to GeoParquet.")(convert)
app.command(name="validate", help="Validate GeoParquet compliance.")(validate)
app.command(name="tile", help="Generate vector tiles (PMTiles).")(tile)
app.command(name="clip", help="Clip features to bbox or geometry.")(clip)
