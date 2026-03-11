"""EarthForge ``raster`` command group — raster file operations.

Provides commands for inspecting, validating, and previewing raster files
(GeoTIFF, COG). Works with both local files and remote URLs.
"""

from __future__ import annotations

import typer
from pydantic import BaseModel

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="raster",
    help="Inspect, validate, and preview raster files.",
    no_args_is_help=True,
)


def info(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path or URL to a raster file."),
) -> None:
    """Inspect raster metadata (dimensions, CRS, bands, tiling)."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.info import inspect_raster

    state = get_state(ctx)
    result = run_command(ctx, inspect_raster(source))
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


def validate(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path or URL to a raster file."),
) -> None:
    """Validate COG compliance (tiling, overviews, IFD order)."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.validate import validate_cog

    state = get_state(ctx)
    result = run_command(ctx, validate_cog(source))
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


def preview(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path or URL to a raster file."),
    output: str = typer.Option(
        None,
        "--out",
        "-O",
        help="Output PNG file path. Defaults to <source_stem>_preview.png.",
    ),
    max_size: int = typer.Option(
        512,
        "--max-size",
        help="Maximum dimension (width or height) in pixels.",
    ),
) -> None:
    """Generate a PNG quicklook from a raster's overview level."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.preview import generate_preview

    state = get_state(ctx)
    result = run_command(ctx, generate_preview(source, output_path=output, max_size=max_size))
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


def convert(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a GeoTIFF file."),
    output: str = typer.Option(
        None,
        "--out",
        "-O",
        help="Output COG file path. Defaults to <source_stem>_cog.tif.",
    ),
    compression: str = typer.Option(
        "deflate",
        "--compression",
        help="Compression: deflate, lzw, zstd.",
    ),
    blocksize: int = typer.Option(
        512,
        "--blocksize",
        help="Tile size in pixels.",
    ),
    resampling: str = typer.Option(
        "nearest",
        "--resampling",
        help="Overview resampling: nearest, bilinear, cubic, average.",
    ),
) -> None:
    """Convert a GeoTIFF to Cloud-Optimized GeoTIFF (COG)."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.convert import convert_to_cog

    state = get_state(ctx)
    result = run_command(
        ctx,
        convert_to_cog(
            source,
            output=output,
            compression=compression,
            blocksize=blocksize,
            resampling=resampling,
        ),
    )
    if isinstance(result, BaseModel):
        render_to_console(result, state.output, no_color=state.no_color)


app.command(name="info", help="Inspect raster metadata.")(info)
app.command(name="validate", help="Validate COG compliance.")(validate)
app.command(name="preview", help="Generate a PNG quicklook.")(preview)
app.command(name="convert", help="Convert GeoTIFF to COG.")(convert)
