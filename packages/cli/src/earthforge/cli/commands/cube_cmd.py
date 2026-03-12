"""EarthForge ``cube`` command group — Zarr and NetCDF datacube operations.

Provides commands for inspecting and slicing multidimensional geospatial
datacubes stored as Zarr or NetCDF. Inspection reads only consolidated
metadata; slicing fetches only the chunks that intersect the requested
spatiotemporal extent.
"""

from __future__ import annotations

import typer
from pydantic import BaseModel

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="cube",
    help="Inspect and slice Zarr and NetCDF datacubes.",
    no_args_is_help=True,
)


def info(
    ctx: typer.Context,
    source: str = typer.Argument(
        help="Zarr store path/URL or NetCDF file path.",
    ),
) -> None:
    """Inspect datacube metadata (dimensions, variables, CRS, extent)."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.cube.info import inspect_cube

    state = get_state(ctx)
    result = run_command(ctx, inspect_cube(source))
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


def slice_cmd(
    ctx: typer.Context,
    source: str = typer.Argument(
        help="Zarr store path/URL or NetCDF file path.",
    ),
    output: str = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output path. Use .zarr suffix for Zarr output, .nc for NetCDF.",
    ),
    variables: str | None = typer.Option(
        None,
        "--var",
        help="Comma-separated variable names to include. Default: all.",
    ),
    bbox: str | None = typer.Option(
        None,
        "--bbox",
        help="Spatial filter: west,south,east,north (dataset CRS units).",
    ),
    time_range: str | None = typer.Option(
        None,
        "--time",
        help="Time range: YYYY-MM-DD/YYYY-MM-DD or YYYY-MM/YYYY-MM.",
    ),
) -> None:
    """Slice a datacube by variables, bounding box, and/or time range."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.cube.slice import slice_cube

    state = get_state(ctx)

    # Parse bbox
    bbox_tuple: tuple[float, float, float, float] | None = None
    if bbox:
        parts = [float(v.strip()) for v in bbox.split(",")]
        if len(parts) != 4:  # noqa: PLR2004
            typer.echo(
                "Error: --bbox requires exactly 4 values: west,south,east,north",
                err=True,
            )
            raise typer.Exit(code=1)
        bbox_tuple = (parts[0], parts[1], parts[2], parts[3])

    # Parse variables
    var_list: list[str] | None = None
    if variables:
        var_list = [v.strip() for v in variables.split(",")]

    result = run_command(
        ctx,
        slice_cube(
            source,
            variables=var_list,
            bbox=bbox_tuple,
            time_range=time_range,
            output=output,
        ),
    )
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


app.command(name="info", help="Inspect datacube metadata.")(info)
app.command(name="slice", help="Slice a datacube by variables, bbox, and time.")(slice_cmd)
