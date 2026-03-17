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
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


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
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


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
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


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
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def stats(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path or URL to a raster file."),
    bands_opt: str | None = typer.Option(
        None,
        "--bands",
        "-b",
        help="Comma-separated band indices (1-based). Default: all.",
    ),
    geometry: str | None = typer.Option(
        None,
        "--geometry",
        "-g",
        help="WKT geometry for zonal statistics.",
    ),
    histogram_bins: int = typer.Option(
        50,
        "--bins",
        help="Number of histogram bins.",
    ),
) -> None:
    """Compute raster statistics (min/max/mean/std/median/histogram)."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.stats import compute_stats

    state = get_state(ctx)
    band_list: list[int] | None = None
    if bands_opt:
        band_list = [int(b.strip()) for b in bands_opt.split(",")]

    result = run_command(
        ctx,
        compute_stats(
            source, bands=band_list,
            geometry_wkt=geometry, histogram_bins=histogram_bins,
        ),
    )
    if isinstance(result, BaseModel):
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def calc(
    ctx: typer.Context,
    expression: str = typer.Argument(
        help='Band math expression, e.g. "(B08 - B04) / (B08 + B04)".',
    ),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        help="Input as VAR=path, e.g. -i B04=red.tif -i B08=nir.tif.",
    ),
    output: str = typer.Option(
        ...,
        "--out",
        "-O",
        help="Output GeoTIFF path.",
    ),
    dtype: str = typer.Option(
        "float32",
        "--dtype",
        help="Output data type.",
    ),
) -> None:
    """Evaluate a band math expression across raster inputs."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.calc import raster_calc

    state = get_state(ctx)

    input_map: dict[str, str] = {}
    for inp in inputs:
        if "=" not in inp:
            typer.echo(f"Error: --input must be VAR=path, got: {inp}", err=True)
            raise typer.Exit(code=1)
        var, path = inp.split("=", 1)
        input_map[var.strip()] = path.strip()

    result = run_command(
        ctx,
        raster_calc(expression, input_map, output, dtype=dtype),
    )
    if isinstance(result, BaseModel):
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def tile(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path or URL to a raster file."),
    output_dir: str = typer.Option(
        ...,
        "--out",
        "-O",
        help="Output directory for tiles.",
    ),
    zoom: str = typer.Option(
        "0-5",
        "--zoom",
        "-z",
        help="Zoom range as min-max (e.g. 0-5).",
    ),
    tile_size: int = typer.Option(
        256,
        "--tile-size",
        help="Tile size in pixels.",
    ),
) -> None:
    """Generate XYZ/TMS static tiles from a raster."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.raster.tile import generate_tiles

    state = get_state(ctx)

    parts = zoom.split("-")
    if len(parts) != 2:
        typer.echo("Error: --zoom must be min-max (e.g. 0-5)", err=True)
        raise typer.Exit(code=1)
    zoom_range = (int(parts[0]), int(parts[1]))

    result = run_command(
        ctx,
        generate_tiles(source, output_dir, zoom_range=zoom_range, tile_size=tile_size),
    )
    if isinstance(result, BaseModel):
        render_to_console(
            result, state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


app.command(name="info", help="Inspect raster metadata.")(info)
app.command(name="validate", help="Validate COG compliance.")(validate)
app.command(name="preview", help="Generate a PNG quicklook.")(preview)
app.command(name="convert", help="Convert GeoTIFF to COG.")(convert)
app.command(name="stats", help="Compute raster statistics.")(stats)
app.command(name="calc", help="Band math calculator.")(calc)
app.command(name="tile", help="Generate XYZ tiles.")(tile)
