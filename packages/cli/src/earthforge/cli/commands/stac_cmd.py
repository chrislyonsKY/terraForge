"""EarthForge ``stac`` command group — STAC catalog interaction.

Provides commands for searching STAC catalogs and inspecting STAC items
and collections. Uses the profile's configured ``stac_api`` endpoint.
"""

from __future__ import annotations

import typer
from pydantic import BaseModel

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="stac",
    help="Search and inspect STAC catalogs.",
    no_args_is_help=True,
)


def search(
    ctx: typer.Context,
    collection: list[str] | None = typer.Option(
        None,
        "--collection",
        "-c",
        help="Collection ID(s) to search within.",
    ),
    bbox: str | None = typer.Option(
        None,
        "--bbox",
        help="Bounding box as west,south,east,north (WGS84).",
    ),
    datetime_range: str | None = typer.Option(
        None,
        "--datetime",
        help="Datetime filter (ISO 8601 or range, e.g. 2024-01-01/2024-06-30).",
    ),
    max_items: int = typer.Option(
        10,
        "--max-items",
        "-n",
        help="Maximum number of items to return.",
    ),
) -> None:
    """Search a STAC catalog for items matching spatial/temporal filters."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.stac.search import search_catalog

    state = get_state(ctx)

    # Parse bbox string to list of floats
    bbox_list: list[float] | None = None
    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox_list = parts
        except ValueError:
            typer.echo(
                "Error: --bbox must be four comma-separated numbers (west,south,east,north)",
                err=True,
            )
            raise typer.Exit(code=2) from None

    async def _run() -> BaseModel:
        from earthforge.core.config import load_profile

        profile = await load_profile(state.profile)
        return await search_catalog(
            profile,
            collections=collection,
            bbox=bbox_list,
            datetime_range=datetime_range,
            max_items=max_items,
        )

    result = run_command(ctx, _run())
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def info(
    ctx: typer.Context,
    url: str = typer.Argument(help="URL to a STAC item or collection."),
) -> None:
    """Inspect a STAC item or collection by URL."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.stac.info import inspect_stac_collection, inspect_stac_item

    state = get_state(ctx)

    async def _run() -> BaseModel:
        from earthforge.core.config import load_profile

        profile = await load_profile(state.profile)

        # Try item first, fall back to collection
        try:
            return await inspect_stac_item(profile, url)
        except Exception:
            return await inspect_stac_collection(profile, url)

    result = run_command(ctx, _run())
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def fetch(
    ctx: typer.Context,
    item_url: str = typer.Argument(help="URL to a STAC item JSON."),
    assets: str | None = typer.Option(
        None,
        "--assets",
        "-a",
        help="Comma-separated asset keys to download (default: all data assets).",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        "-d",
        help="Local directory to write files into (default: ./<item_id>/).",
    ),
    parallel: int = typer.Option(
        4,
        "--parallel",
        "-p",
        min=1,
        max=16,
        help="Maximum concurrent downloads.",
    ),
) -> None:
    """Download assets from a STAC item with resume support."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.stac.fetch import fetch_assets

    state = get_state(ctx)

    asset_list: list[str] | None = None
    if assets:
        asset_list = [a.strip() for a in assets.split(",") if a.strip()]

    async def _run() -> BaseModel:
        from earthforge.core.config import load_profile

        profile = await load_profile(state.profile)
        return await fetch_assets(
            profile,
            item_url,
            output_dir=output_dir,
            assets=asset_list,
            parallel=parallel,
        )

    result = run_command(ctx, _run())
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def validate(
    ctx: typer.Context,
    source: str = typer.Argument(help="URL or path to a STAC item or collection JSON."),
) -> None:
    """Validate a STAC item or collection against the STAC specification."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.stac.validate import validate_stac

    state = get_state(ctx)

    async def _run() -> BaseModel:
        from earthforge.core.config import load_profile

        profile = await load_profile(state.profile)
        return await validate_stac(profile, source)

    result = run_command(ctx, _run())
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def publish(
    ctx: typer.Context,
    source: str = typer.Argument(help="Path to a STAC item JSON file."),
    collection: str | None = typer.Option(
        None,
        "--collection",
        "-c",
        help="Target collection ID.",
    ),
    api_url: str | None = typer.Option(
        None,
        "--api-url",
        help="STAC API URL (overrides profile).",
    ),
) -> None:
    """Publish a STAC item to a writable STAC API."""
    import json
    from pathlib import Path

    from earthforge.cli.main import get_state, run_command
    from earthforge.stac.publish import publish_item

    state = get_state(ctx)

    source_path = Path(source)
    if not source_path.exists():
        typer.echo(f"Error: file not found: {source}", err=True)
        raise typer.Exit(code=2)

    try:
        item = json.loads(source_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        typer.echo(f"Error: failed to read STAC item JSON: {exc}", err=True)
        raise typer.Exit(code=2) from None

    async def _run() -> BaseModel:
        from earthforge.core.config import load_profile

        profile = await load_profile(state.profile)
        return await publish_item(
            profile,
            item,
            collection_id=collection,
            api_url=api_url,
        )

    result = run_command(ctx, _run())
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


app.command(name="search", help="Search a STAC catalog for items.")(search)
app.command(name="info", help="Inspect a STAC item or collection by URL.")(info)
app.command(name="fetch", help="Download assets from a STAC item.")(fetch)
app.command(name="validate", help="Validate a STAC item or collection.")(validate)
app.command(name="publish", help="Publish a STAC item to a writable API.")(publish)
