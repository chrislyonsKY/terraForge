"""EarthForge ``explore`` command — interactive STAC TUI.

Launches the Textual-based interactive terminal user interface for browsing
STAC catalogs. The TUI provides a three-panel layout:

- **Collections** — all collections at the STAC API endpoint
- **Items** — up to 50 items in the selected collection
- **Detail** — full metadata, assets, and links for the selected item

Keyboard shortcuts inside the TUI
----------------------------------
``q``
    Quit the explorer.
``r``
    Refresh the collection list.
``/``
    Show filter hint (bbox filtering is applied at launch).
``Tab`` / ``Shift+Tab``
    Cycle focus between the three panels.
``Enter``
    Select the focused collection or item.
``↑`` / ``↓``
    Navigate within a panel.
"""

from __future__ import annotations

import typer

app = typer.Typer(name="explore", help="Interactive STAC catalog explorer (TUI).")

_DEFAULT_API = "https://earth-search.aws.element84.com/v1"


@app.callback(invoke_without_command=True)
def explore(
    ctx: typer.Context,
    api: str = typer.Option(
        _DEFAULT_API,
        "--api",
        help="STAC API root URL to browse.",
        show_default=True,
    ),
    collection: str | None = typer.Option(
        None,
        "--collection",
        "-c",
        help="Pre-select and open this collection on startup.",
    ),
    bbox: str | None = typer.Option(
        None,
        "--bbox",
        help="Spatial filter: west,south,east,north (applied to item searches).",
    ),
) -> None:
    """Launch the interactive STAC catalog explorer.

    Opens a full-screen terminal UI connected to the given STAC API. Browse
    collections, inspect items, and view asset metadata — all without leaving
    the terminal.

    Parameters:
        ctx: Typer command context (for global state).
        api: STAC API endpoint URL.
        collection: Optional collection to open on startup.
        bbox: Optional bounding-box filter string.

    Raises:
        typer.Exit: With code 1 on invalid ``--bbox`` input.
    """
    try:
        from earthforge.cli.tui.app import ExploreApp
    except ImportError as exc:
        typer.echo(
            f"Error: textual is required for explore: {exc}\n"
            "Install with: pip install earthforge[cli]",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    bbox_tuple: tuple[float, float, float, float] | None = None
    if bbox:
        parts = [v.strip() for v in bbox.split(",")]
        if len(parts) != 4:
            typer.echo("Error: --bbox requires west,south,east,north", err=True)
            raise typer.Exit(code=1)
        try:
            w, s, e, n = (float(p) for p in parts)
        except ValueError:
            typer.echo("Error: --bbox values must be numeric", err=True)
            raise typer.Exit(code=1)  # noqa: B904
        bbox_tuple = (w, s, e, n)

    ExploreApp(
        api_url=api,
        initial_collection=collection,
        bbox=bbox_tuple,
    ).run()
