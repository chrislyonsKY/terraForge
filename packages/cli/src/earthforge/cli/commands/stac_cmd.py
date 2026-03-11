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
        render_to_console(result, state.output, no_color=state.no_color)


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
        render_to_console(result, state.output, no_color=state.no_color)


app.command(name="search", help="Search a STAC catalog for items.")(search)
app.command(name="info", help="Inspect a STAC item or collection by URL.")(info)
